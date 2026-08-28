/**
 * The imperative driver behind the spoken dialogue screen (INT-233): owns
 * the turn reducer plus every side effect — clip synthesis/caching and
 * playback, the recorder, the single-question extract, and the audio
 * teardown. The screen (components/DialogueIntake.tsx) renders state and
 * stores answers; this hook never touches the session note or navigation.
 *
 * DISTURBABLE guarantee lives here: `bargeIn` calls `player.pause()` — a
 * synchronous call on the shared native object — before dispatching, so
 * playback halts in the same JS tick as the tap; one player ref, always
 * cleared before the next clip, means no overlapping audio ever.
 *
 * Audio hygiene: clips under cacheDirectory/dialogue/ are AGENT-voice
 * audio synthesized from catalog tr strings, deleted wholesale on unmount
 * AND on session end. PATIENT recordings keep lib/voice.ts's
 * delete-after-upload posture (invariant 3 governs those — untouched).
 * The numeral guard sits inside the synth path (invariant 22 mirror).
 */
import { useEffect, useReducer, useRef, useState } from "react";
import {
  AudioModule,
  RecordingPresets,
  createAudioPlayer,
  useAudioRecorder,
  type AudioPlayer,
} from "expo-audio";

import { configuredServiceCandidates } from "../dev/expoHosts";
import { EXTRACT_PORT, extractFromCandidates } from "../extract";
import type { IntakeQuestion } from "../intake/questions";
import { discardRecording, transcribeRecording } from "../voice";
import { clearDialogueClips, dialogueClipStore, reachableTtsBaseUrl } from "./clips";
import { confirmSpeechTr, questionSpeechTr } from "./speech";
import { clipName, type ClipStore } from "./tts";
import {
  dialogueReducer,
  initialDialogueState,
  type DialogueAction,
  type DialogueState,
} from "./turn";

export interface DialogueSessionOptions {
  questions: readonly IntakeQuestion[];
  /** The pack label the extract daemon receives (the visit's department). */
  packName: string;
  /** All steps committed — the caller routes onward. Clips already gone. */
  onDone: () => void;
  /** Hard service failure — the caller lands in the manual steps. */
  onFailed: () => void;
}

export interface DialogueSession {
  state: DialogueState;
  /** True only while a clip is audibly playing — the screen says
   * "preparing" honestly until then (no duration claim, 02 §5.2). */
  playing: boolean;
  /** Tap during agent speech: stop playback NOW, open the mic. */
  bargeIn: () => void;
  /** "Bitirdim" / tap-to-stop: single-shot close of one listen. */
  finishListening: () => Promise<void>;
  /** "Yazarak yanıtlayın": typed fallback for THIS step only. */
  typeThisStep: () => Promise<void>;
  /** Leave the whole dialogue by choice; resolves after audio cleanup. */
  leave: () => Promise<void>;
  /** Advance after the caller stored this step's answer. */
  advance: (kind: "confirm" | "commit") => void;
  /** From the confirm card: the patient speaks the correction instead. */
  speakCorrection: () => void;
}

export function useDialogueSession({
  questions,
  packName,
  onDone,
  onFailed,
}: DialogueSessionOptions): DialogueSession {
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const [state, dispatch] = useReducer(
    (s: DialogueState, a: DialogueAction) => dialogueReducer(questions, s, a),
    undefined,
    initialDialogueState,
  );
  const stateRef = useRef(state);
  stateRef.current = state;
  const [playing, setPlaying] = useState(false);

  const storeRef = useRef<Promise<ClipStore> | null>(null);
  const playerRef = useRef<AudioPlayer | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const closedRef = useRef(false);
  /** Single-shot guard for the two stop affordances on one listen. */
  const finishingRef = useRef(false);
  /** Set when the patient bails out of the voice loop mid-flight. */
  const cancelledRef = useRef(false);

  /** Mic permission + TTS probe, once per session; failure is terminal. */
  const clipStore = (): Promise<ClipStore> => {
    storeRef.current ??= (async () => {
      const permission = await AudioModule.requestRecordingPermissionsAsync();
      if (!permission.granted) {
        throw new Error("mic_denied");
      }
      const base = await reachableTtsBaseUrl();
      if (base === null) {
        throw new Error("tts_unreachable");
      }
      return dialogueClipStore(base);
    })();
    return storeRef.current;
  };

  /** Immediate, synchronous stop — the barge-in guarantee. One player ref,
   * always cleared before the next clip: no overlapping audio ever. */
  const stopPlayback = () => {
    const player = playerRef.current;
    playerRef.current = null;
    if (player !== null) {
      try {
        player.pause();
        player.remove();
      } catch {
        // already released — nothing left to stop
      }
    }
  };

  const stopAndDiscardRecording = async () => {
    try {
      await recorder.stop();
      const uri = recorder.uri;
      if (uri !== null) {
        // Patient audio: deleted immediately, same posture as lib/voice.ts.
        await discardRecording(uri);
      }
    } catch {
      // recorder was not running — nothing to discard
    }
  };

  // Speaking driver: ensure the clip (cache hit after the first ask of a
  // session), then play it; end of clip hands the turn over.
  const speaking = state.phase === "speaking" ? state : null;
  useEffect(() => {
    if (speaking === null) {
      return;
    }
    const question = questions[speaking.step];
    let stale = false;
    (async () => {
      try {
        const store = await clipStore();
        const speech =
          speaking.intent === "question"
            ? questionSpeechTr(question)
            : confirmSpeechTr(question, speaking.candidate.values);
        const name =
          speaking.intent === "question"
            ? clipName("question", question.id)
            : question.kind === "text"
              ? clipName("confirm", question.id) // generic clip — free text never names a file
              : clipName("confirm", question.id, speaking.candidate.values);
        const uri = await store.ensure(name, speech);
        if (stale) {
          return;
        }
        await AudioModule.setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true });
        if (stale) {
          return;
        }
        stopPlayback();
        const player = createAudioPlayer({ uri });
        playerRef.current = player;
        player.addListener("playbackStatusUpdate", (status) => {
          if (status.didJustFinish && !stale && playerRef.current === player) {
            stopPlayback();
            dispatch({ type: "speech_done" });
          }
        });
        player.play();
        setPlaying(true);
      } catch {
        if (!stale) {
          dispatch({ type: "failure" });
        }
      }
    })();
    return () => {
      stale = true;
      setPlaying(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- speaking is a fresh object per turn entry; questions is stable for the session
  }, [speaking]);

  // Listening driver: the mic opens when the machine says listen.
  const listening = state.phase === "listening" ? state : null;
  useEffect(() => {
    if (listening === null) {
      return;
    }
    finishingRef.current = false; // a fresh listen re-arms the stop guard
    cancelledRef.current = false; // and clears any earlier bail-out
    let stale = false;
    (async () => {
      try {
        await AudioModule.setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
        if (stale) {
          return;
        }
        await recorder.prepareToRecordAsync();
        if (stale) {
          return;
        }
        recorder.record();
      } catch {
        if (!stale) {
          dispatch({ type: "failure" });
        }
      }
    })();
    return () => {
      stale = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- listening is a fresh object per turn entry
  }, [listening]);

  // Session end: agent clips are deleted and the flow moves on.
  useEffect(() => {
    if (state.phase === "done") {
      closedRef.current = true;
      void clearDialogueClips();
      onDone();
    } else if (state.phase === "failed") {
      closedRef.current = true;
      void stopAndDiscardRecording();
      void clearDialogueClips();
      onFailed();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- terminal transitions only
  }, [state.phase]);

  // Unmount: stop audio both ways and delete the whole agent-clip cache.
  useEffect(() => {
    return () => {
      stopPlayback();
      abortRef.current?.abort();
      if (!closedRef.current && stateRef.current.phase === "listening") {
        void stopAndDiscardRecording();
      }
      void clearDialogueClips();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- unmount only
  }, []);

  /** "Bitirdim" / tap-to-stop: close the mic, transcribe, extract against
   * THIS single question (fast path), and let the reducer route the rest.
   * The ref guard makes the two stop affordances (surface tap and the
   * "Bitirdim" button) single-shot — the recording is processed once. */
  const finishListening = async () => {
    if (finishingRef.current || stateRef.current.phase !== "listening") {
      return;
    }
    finishingRef.current = true;
    const question = questions[stateRef.current.step];
    dispatch({ type: "stop" });
    try {
      await recorder.stop();
    } catch {
      dispatch({ type: "failure" });
      return;
    }
    const uri = recorder.uri;
    if (uri === null) {
      // Nothing was captured — not a service failure; this step falls to
      // typing via the empty-transcript rule.
      dispatch({ type: "transcript", text: "" });
      return;
    }
    let transcript = "";
    try {
      transcript = await transcribeRecording(uri); // deletes the file after upload
    } catch {
      dispatch({ type: "failure" });
      return;
    }
    if (cancelledRef.current) {
      return; // the patient already moved on (typed fallback or exit)
    }
    dispatch({ type: "transcript", text: transcript });
    if (transcript.trim().length === 0 || question.kind === "text") {
      return; // reducer handled it: typing fallback, or transcript-as-answer
    }
    const controller = new AbortController();
    abortRef.current = controller;
    const result = await extractFromCandidates(
      configuredServiceCandidates(EXTRACT_PORT),
      transcript,
      packName,
      [question], // single-question spec — the daemon accepts any subset
      { signal: controller.signal },
    );
    if (controller.signal.aborted) {
      return;
    }
    if (result.ok) {
      const candidate = result.candidates[question.id];
      dispatch(
        candidate !== undefined
          ? {
              type: "candidate",
              candidate: { values: [...candidate.values], quote: candidate.quote },
            }
          : { type: "no_candidate" },
      );
    } else if (result.reason !== "aborted") {
      dispatch({ type: "failure" });
    }
  };

  const bargeIn = () => {
    stopPlayback(); // synchronous — playback halts before anything else runs
    dispatch({ type: "barge_in" });
  };

  const typeThisStep = async () => {
    cancelledRef.current = true;
    stopPlayback();
    abortRef.current?.abort();
    if (stateRef.current.phase === "listening") {
      await stopAndDiscardRecording();
    }
    dispatch({ type: "type" });
  };

  const leave = async () => {
    closedRef.current = true;
    cancelledRef.current = true;
    stopPlayback();
    abortRef.current?.abort();
    if (stateRef.current.phase === "listening") {
      await stopAndDiscardRecording();
    }
    await clearDialogueClips();
  };

  return {
    state,
    playing,
    bargeIn,
    finishListening,
    typeThisStep,
    leave,
    advance: (kind) => dispatch({ type: kind }),
    speakCorrection: () => dispatch({ type: "speak" }),
  };
}

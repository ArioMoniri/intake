/**
 * The imperative driver behind the voice chat surface (INT-233 base,
 * INT-235 ask-ahead pass): owns the stream reducer plus every side
 * effect — clip synthesis/caching and playback, the recorder, the
 * background transcribe→extract pipelines, and the audio teardown. The
 * screen (components/DialogueIntake.tsx) renders state and stores
 * answers; this hook never touches the session note or navigation.
 *
 * ASK-AHEAD (owner feedback; the blueprint IntakeEngine pattern at dev
 * tier): the next question never waits for the previous answer's
 * pipeline — `utterance` advances the turn the moment the mic closes,
 * and each utterance's transcribe→extract runs detached, reconciling by
 * work id. The WHOLE session's question clips pre-warm in parallel at
 * mount, so "soru hazırlanıyor" is the exception, not the rhythm — and
 * the bubble always shows the question TEXT instantly regardless.
 * A typed composer submit is the same conversation: one utterance that
 * skips the ASR hop.
 *
 * DISTURBABLE guarantee lives here: `bargeIn` calls `player.pause()` — a
 * synchronous call on the shared native object — before dispatching, so
 * playback halts in the same JS tick as the tap; one player ref, always
 * cleared before the next clip, means no overlapping audio ever.
 *
 * Audio hygiene: clips under cacheDirectory/dialogue/ are AGENT-voice
 * audio synthesized from catalog tr strings, deleted wholesale on
 * unmount AND on session end. PATIENT recordings keep lib/voice.ts's
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
import { EXTRACT_PORT, extractFromCandidates, type ExtractCandidate } from "../extract";
import type { IntakeQuestion } from "../intake/questions";
import { discardRecording, transcribeRecording } from "../voice";
import { clearDialogueClips, createDialogueTtsLaneSelector, dialogueClipStore } from "./clips";
import { confirmSpeechTr, questionSpeechTr } from "./speech";
import {
  dialogueStreamReducer,
  initialDialogueStreamState,
  type DialogueStreamAction,
  type DialogueStreamState,
} from "./stream";
import { clipName, type ClipStore } from "./tts";
import type { DialogueCandidate } from "./turn";

export interface DialogueSessionOptions {
  questions: readonly IntakeQuestion[];
  /** The pack label the extract daemon receives (the visit's department). */
  packName: string;
  /** Every question answered — the caller routes onward. Clips gone. */
  onDone: () => void;
  /** Hard service failure — the caller lands in the manual steps. */
  onFailed: () => void;
  /** Dialogue settled with questions left: the caller hands the manual
   * steps whatever suggestions remain unconfirmed (may be empty). */
  onHandoff: (leftovers: Record<string, DialogueCandidate>) => void;
}

export interface DialogueSession {
  /** Turn + pending suggestions + committed answers + the chat log. */
  state: DialogueStreamState;
  /** True only while a clip is audibly playing — the bubble says
   * "preparing" honestly until then (no duration claim, 02 §5.2). */
  playing: boolean;
  /** Tap on the speaking bubble: stop playback NOW, open the mic. */
  bargeIn: () => void;
  /** "Bitirdim" / tap-to-stop: take the utterance, advance NOW; the
   * transcribe→extract pipeline reconciles behind by work id. */
  finishListening: () => Promise<void>;
  /** Composer submit: a typed utterance — the same conversation. */
  sendTyped: (text: string) => Promise<void>;
  /** Leave the whole dialogue by choice; resolves after audio cleanup. */
  leave: () => Promise<void>;
  /** Confirm the live turn's candidate with the on-screen values. */
  confirm: (values: string[]) => void;
  /** Panel-row confirm of one pending suggestion (caller stores it). */
  confirmPending: (questionId: string) => void;
  /** From the confirm card: the patient speaks the correction instead. */
  speakCorrection: () => void;
}

function toCandidates(
  candidates: Record<string, ExtractCandidate>,
): Record<string, DialogueCandidate> {
  const mapped: Record<string, DialogueCandidate> = {};
  for (const [questionId, candidate] of Object.entries(candidates)) {
    mapped[questionId] = { values: [...candidate.values], quote: candidate.quote };
  }
  return mapped;
}

export function useDialogueSession({
  questions,
  packName,
  onDone,
  onFailed,
  onHandoff,
}: DialogueSessionOptions): DialogueSession {
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const [state, dispatch] = useReducer(
    (s: DialogueStreamState, a: DialogueStreamAction) => dialogueStreamReducer(questions, s, a),
    questions,
    initialDialogueStreamState,
  );
  const stateRef = useRef(state);
  stateRef.current = state;
  const [playing, setPlaying] = useState(false);

  const storeRef = useRef<Promise<ClipStore> | null>(null);
  const playerRef = useRef<AudioPlayer | null>(null);
  /** One controller for every background extract of the session. */
  const abortRef = useRef<AbortController | null>(null);
  const closedRef = useRef(false);
  /** Single-shot guard for the stop affordances on one listen. */
  const finishingRef = useRef(false);
  /** Monotonic work id — the reconcile-behind address space. */
  const workRef = useRef(0);

  const sessionSignal = () => {
    abortRef.current ??= new AbortController();
    return abortRef.current.signal;
  };

  /**
   * Mic permission + the session's lane selector, once per session.
   *
   * INT-249: the store is bound to the SELECTOR, not to a base resolved
   * here. The lane is still probed once — probing costs a real synthesis and
   * must not happen per turn — but the probe now times that synthesis
   * against the blueprint's turn budget, and a lane that wedges later is
   * re-probed instead of blocking every remaining clip behind it. A mic
   * denial is still terminal; an unreachable ladder surfaces from the
   * selector on the first `ensure`.
   */
  const clipStore = (): Promise<ClipStore> => {
    storeRef.current ??= (async () => {
      const permission = await AudioModule.requestRecordingPermissionsAsync();
      if (!permission.granted) {
        throw new Error("mic_denied");
      }
      return dialogueClipStore(createDialogueTtsLaneSelector());
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

  // Pre-warm the session's scripted clips at mount, FIRST QUESTION FIRST
  // (INT-239): the opening turn is the one the patient waits on, so its
  // clip is ensured on its own before the rest go out in parallel — the
  // speaking driver then hits a warm cache and "soru hazırlanıyor" stays
  // the exception. Every question is warmed, gated or not: a gate can open
  // mid-conversation and a cold clip there is the same stall.
  // Failures stay silent here — the speaking driver re-ensures per turn and
  // surfaces a real store failure honestly there.
  useEffect(() => {
    let stale = false;
    (async () => {
      const warm = (store: ClipStore, question: IntakeQuestion): Promise<unknown>[] => {
        const clips = [store.ensure(clipName("question", question.id), questionSpeechTr(question))];
        if (question.kind === "text") {
          // The generic confirm line is scripted too — free text never
          // names a clip and patient words are never synthesized.
          clips.push(store.ensure(clipName("confirm", question.id), confirmSpeechTr(question, [])));
        }
        return clips;
      };
      try {
        const store = await clipStore();
        if (stale || questions.length === 0) {
          return;
        }
        await Promise.allSettled(warm(store, questions[0]));
        if (stale) {
          return;
        }
        await Promise.allSettled(questions.slice(1).flatMap((q) => warm(store, q)));
      } catch {
        // surfaced by the speaking driver on its own ensure
      }
    })();
    return () => {
      stale = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per session; questions is stable
  }, []);

  // Speaking driver: ensure the clip (pre-warm makes this a cache hit),
  // then play it; end of clip hands the turn over. Reconcile updates keep
  // the turn object's identity, so they never restart a clip.
  const speaking = state.turn.phase === "speaking" ? state.turn : null;
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
  const listening = state.turn.phase === "listening" ? state.turn : null;
  useEffect(() => {
    if (listening === null) {
      return;
    }
    finishingRef.current = false; // a fresh listen re-arms the stop guard
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

  // Session end: agent clips are deleted and the flow moves on. Handoff
  // carries the unconfirmed leftovers to the manual steps as prefill.
  useEffect(() => {
    if (state.turn.phase === "done") {
      closedRef.current = true;
      abortRef.current?.abort();
      void clearDialogueClips();
      onDone();
    } else if (state.turn.phase === "failed") {
      closedRef.current = true;
      abortRef.current?.abort();
      void stopAndDiscardRecording();
      void clearDialogueClips();
      onFailed();
    } else if (state.turn.phase === "handoff") {
      closedRef.current = true;
      abortRef.current?.abort();
      void clearDialogueClips();
      onHandoff(stateRef.current.pending);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- terminal transitions only
  }, [state.turn.phase]);

  // Unmount: stop audio both ways and delete the whole agent-clip cache.
  useEffect(() => {
    return () => {
      stopPlayback();
      abortRef.current?.abort();
      if (!closedRef.current && stateRef.current.turn.phase === "listening") {
        void stopAndDiscardRecording();
      }
      void clearDialogueClips();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- unmount only
  }, []);

  /** The reconcile tail every utterance shares: extract against every
   * remaining unanswered question (the daemon accepts any subset), then
   * settle the work id. Failures settle EMPTY — extraction is enrichment
   * in ask-ahead, never a reason to kill the conversation. A text-kind
   * question's own answer is the transcript verbatim, no model hop. */
  const runExtract = async (
    workId: number,
    transcript: string,
    utteranceQuestion: IntakeQuestion | null,
  ) => {
    const verbatimTextId =
      utteranceQuestion !== null && utteranceQuestion.kind === "text" ? utteranceQuestion.id : null;
    const verbatim: Record<string, DialogueCandidate> =
      verbatimTextId !== null
        ? { [verbatimTextId]: { values: [transcript], quote: transcript } }
        : {};
    const remaining = questions.filter(
      (q) => stateRef.current.answers[q.id] === undefined && q.id !== verbatimTextId,
    );
    if (remaining.length === 0) {
      dispatch({ type: "extract_settled", workId, candidates: verbatim });
      return;
    }
    const result = await extractFromCandidates(
      configuredServiceCandidates(EXTRACT_PORT),
      transcript,
      packName,
      remaining,
      { signal: sessionSignal() },
    );
    if (closedRef.current) {
      return;
    }
    dispatch({
      type: "extract_settled",
      workId,
      // The verbatim transcript outranks any model paraphrase of itself.
      candidates: result.ok ? { ...toCandidates(result.candidates), ...verbatim } : verbatim,
    });
  };

  /** "Bitirdim" / tap-to-stop: close the mic and advance NOW (ask-ahead);
   * transcription and extraction reconcile behind under this work id.
   * The ref guard keeps the stop affordances single-shot. */
  const finishListening = async () => {
    if (finishingRef.current || stateRef.current.turn.phase !== "listening") {
      return;
    }
    finishingRef.current = true;
    const question = questions[stateRef.current.turn.step];
    let uri: string | null = null;
    try {
      await recorder.stop();
      uri = recorder.uri;
    } catch {
      dispatch({ type: "failure" });
      return;
    }
    const workId = (workRef.current += 1);
    dispatch({ type: "utterance", workId }); // the next question speaks NOW
    if (uri === null) {
      // Nothing was captured — the bubble goes; the question falls to the
      // manual steps at the end if nothing else fills it.
      dispatch({ type: "transcript_ready", workId, text: "" });
      dispatch({ type: "extract_settled", workId, candidates: {} });
      return;
    }
    let transcript = "";
    try {
      transcript = await transcribeRecording(uri); // deletes the file after upload
    } catch {
      if (!closedRef.current) {
        dispatch({ type: "failure" }); // a broken ASR lane is a hard failure
      }
      return;
    }
    if (closedRef.current) {
      return;
    }
    dispatch({ type: "transcript_ready", workId, text: transcript });
    const trimmed = transcript.trim();
    if (trimmed.length === 0) {
      dispatch({ type: "extract_settled", workId, candidates: {} });
      return;
    }
    await runExtract(workId, trimmed, question);
  };

  /** Composer submit: voice and text are ONE conversation — a typed
   * utterance takes the same path as a spoken one, minus the ASR hop. */
  const sendTyped = async (raw: string) => {
    const text = raw.trim();
    const phase = stateRef.current.turn.phase;
    if (text.length === 0 || phase === "done" || phase === "failed" || phase === "handoff") {
      return;
    }
    stopPlayback(); // typing over agent speech is a barge-in
    const step = "step" in stateRef.current.turn ? stateRef.current.turn.step : -1;
    if (phase === "listening") {
      finishingRef.current = true; // the abandoned listen is never processed
      await stopAndDiscardRecording();
    }
    const workId = (workRef.current += 1);
    dispatch({ type: "typed", workId, text });
    // During the end wait there is no live question; enrich everything.
    await runExtract(workId, text, step >= 0 ? questions[step] : null);
  };

  const bargeIn = () => {
    stopPlayback(); // synchronous — playback halts before anything else runs
    dispatch({ type: "barge_in" });
  };

  const leave = async () => {
    closedRef.current = true;
    stopPlayback();
    abortRef.current?.abort();
    if (stateRef.current.turn.phase === "listening") {
      await stopAndDiscardRecording();
    }
    await clearDialogueClips();
  };

  return {
    state,
    playing,
    bargeIn,
    finishListening,
    sendTyped,
    leave,
    confirm: (values) => dispatch({ type: "confirm", values }),
    confirmPending: (questionId) => dispatch({ type: "confirm_pending", questionId }),
    speakCorrection: () => dispatch({ type: "speak" }),
  };
}

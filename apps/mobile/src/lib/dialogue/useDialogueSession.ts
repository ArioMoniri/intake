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
 * INT-291 gives that guarantee a second cause: the patient's VOICE. Until it,
 * the speaking driver set `allowsRecording: false` and started no recorder, so
 * while the agent talked there was NO MICROPHONE AT ALL and speaking over it
 * did nothing — a tap or a typed message were the only interrupts, and neither
 * is what a patient in pain reaches for. files/02 §8.2 budgets a barge-in stop
 * at 150 ms; before this there was no barge-in to budget unless a finger was
 * involved. Now the mic opens when the agent STARTS speaking rather than when
 * it stops, a level watcher feeds bargeIn.ts's onset detector, and an onset
 * calls the same `bargeIn` the tap calls: one reducer action, two causes, no
 * second state machine.
 *
 * The recording that hears the interruption IS the patient's answer. That is
 * the design, not an optimisation — a barge-in whose opening words are lost is
 * a patient made to repeat themselves — and it is also why nothing new reaches
 * disk: one `prepareToRecordAsync` per turn, exactly as before, started
 * earlier. The watcher reads the platform's own level meter, never a buffer,
 * so invariant 3's posture is unchanged.
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
import { BARGE_IN_SAMPLE_MS, createSpeechOnsetDetector } from "./bargeIn";
import { EXTRACT_PORT, extractFromCandidates, type ExtractCandidate } from "../extract";
import type { IntakeQuestion } from "../intake/questions";
import { appHaptics } from "../motion/appHaptics";
import { discardRecording, transcribeRecording } from "../voice";
import { clearDialogueClips, createDialogueTtsLaneSelector, dialogueClipStore } from "./clips";
import { confirmSpeechTr, questionSpeechTr } from "./speech";
import {
  dialogueStreamReducer,
  initialDialogueStreamState,
  shouldAttemptSpeech,
  type DialogueStreamAction,
  type DialogueStreamState,
} from "./stream";
import { clipDeadlineMs, clipName, withDeadline, type ClipStore } from "./tts";
import type { DialogueCandidate } from "./turn";

export interface DialogueSessionOptions {
  questions: readonly IntakeQuestion[];
  /** The pack label the extract daemon receives (the visit's department). */
  packName: string;
  /** Every question answered — the caller routes onward. Clips gone. */
  onDone: () => void;
  /** Hard service failure — the caller lands in the manual steps, carrying
   * the same unconfirmed suggestions a tidy hand-over would (INT-261): both
   * exits go to the same place, so both must arrive with what was said. */
  onFailed: (leftovers: Record<string, DialogueCandidate>) => void;
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
  /**
   * INT-336: the recorder's current metering in dBFS, or undefined when it has
   * none. One loudness scalar for the presence orb's halo, read by its
   * sampler while listening; never a buffer, and never stored or sent.
   */
  readLevel: () => number | undefined;
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
  // Metering is what the onset detector reads. HIGH_QUALITY leaves it off,
  // and without it every level comes back `undefined` and barge-in is deaf.
  const recorder = useAudioRecorder({ ...RecordingPresets.HIGH_QUALITY, isMeteringEnabled: true });
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
  /** The level watch armed for the clip currently playing, if any. */
  const watchRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const clearBargeInWatch = () => {
    if (watchRef.current !== null) {
      clearInterval(watchRef.current);
      watchRef.current = null;
    }
  };

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

  /**
   * Open the microphone. One `prepareToRecordAsync` per turn, wherever the
   * turn started it — the speaking driver when the clip begins, the listening
   * driver when there was no clip.
   */
  const openMicrophone = async () => {
    await AudioModule.setAudioModeAsync({
      allowsRecording: true,
      playsInSilentMode: true,
      shouldRouteThroughEarpiece: false,
    });
    await recorder.prepareToRecordAsync();
    recorder.record();
  };

  /**
   * Watch the level while the agent speaks and interrupt on a real onset.
   *
   * Every decision about WHETHER a level pattern is a barge-in lives in
   * `bargeIn.ts`, where it is a pure function and therefore testable without a
   * microphone; this closure only supplies samples and stops on `"fired"`.
   * `getStatus()` returns the platform's own meter reading — no buffer is read
   * here, and nothing new is written (invariant 3).
   *
   * The watch is torn down by the same `stale` flag the clip is: the effect's
   * cleanup runs on every turn change, so a timer can never outlive the clip
   * it was watching.
   */
  const armBargeInWatch = async (isStale: () => boolean) => {
    clearBargeInWatch(); // at most one watch is ever referenced
    if (!recorder.isRecording) {
      // A mic denial already ended the session upstream; a failure to open it
      // HERE costs barge-in and nothing else, so the turn goes on silently
      // interruptible by tap, which is where the product was before INT-291.
      try {
        await openMicrophone();
      } catch {
        return;
      }
    }
    if (isStale()) {
      // The turn moved on while the microphone was opening. Arming now would
      // leave a timer watching a clip that is no longer playing — it would
      // stop itself on its first tick, but only after the next turn's watch
      // had already been created, and then two detectors would be live.
      return;
    }
    const detector = createSpeechOnsetDetector();
    const timer = setInterval(() => {
      if (stateRef.current.turn.phase !== "speaking") {
        clearInterval(timer);
        return;
      }
      let level: number | undefined;
      try {
        level = recorder.getStatus().metering;
      } catch {
        clearInterval(timer);
        return;
      }
      if (detector.sample(level, Date.now()) === "fired") {
        clearInterval(timer);
        bargeIn();
      }
    }, BARGE_IN_SAMPLE_MS);
    watchRef.current = timer;
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
  //
  // INT-261 splits the two failures this loop can have, because they are not
  // the same failure. `clipStore()` asks for the MICROPHONE before it builds
  // anything, and a patient who has refused it cannot hold a conversation —
  // that is `failure`, and the typed steps take over. Everything after it is
  // about AUDIO OUTPUT: a TTS ladder that cannot admit a lane inside the turn
  // budget, a clip that comes back empty, a player that will not start. None
  // of that stops the patient answering, so it raises `speech_unavailable`
  // instead: the turn advances, the session goes silent, and the screen says
  // so. Before this, a clip failure on question two ended the whole intake
  // and the typed form re-asked question one.
  //
  // INT-294: "silent from here" was too strong. The silence is a report about
  // the last clip, so the driver tries again once the cooldown the reducer
  // set has been spent, and a clip that plays clears the caption. The retry
  // is affordable because admission is now bounded to ONE turn round-trip
  // (ttsLane.ts ADMISSION_BUDGET_MS) instead of one per (tier, host) pair.
  const speaking = state.turn.phase === "speaking" ? state.turn : null;
  const voiceMuted = state.voiceMuted;
  const voiceRetryIn = state.voiceRetryIn;
  useEffect(() => {
    if (speaking === null) {
      return;
    }
    const question = questions[speaking.step];
    let stale = false;
    (async () => {
      let store: ClipStore;
      try {
        store = await clipStore();
      } catch {
        // No microphone: this is the one that ends the conversation.
        if (!stale) {
          dispatch({ type: "failure" });
        }
        return;
      }
      if (stale) {
        return;
      }
      if (!shouldAttemptSpeech({ voiceMuted, voiceRetryIn })) {
        // Silent, and a cooldown is still owed: do not spend an admission on
        // this turn to rediscover it. The question text is on screen; move
        // the turn on, one turn closer to the next attempt.
        //
        // `speech_skipped`, NOT `speech_done` (INT-294). Until this split the
        // silent path dispatched the action that means "the clip played",
        // which is why the mute could only ever be a latch: the state had no
        // way to tell a turn that was heard from a turn that was never tried,
        // so clearing on `speech_done` would have cleared on the first silent
        // turn and the voice would have been declared back without evidence.
        dispatch({ type: "speech_skipped" });
        return;
      }
      try {
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
        // INT-261: the ladder may take as long as it likes; the patient may
        // not be made to wait more than this clip's own worth of work.
        const uri = await withDeadline(store.ensure(name, speech), clipDeadlineMs(speech));
        if (stale) {
          return;
        }
        // `allowsRecording: true` while the agent speaks is the whole change.
        // On iOS this is the `.playAndRecord` category, which is the only one
        // that admits simultaneous play and capture; `shouldRouteThroughEarpiece:
        // false` is stated rather than left to the default because the same
        // category is what puts audio on the receiver, and answering "the voice
        // sounds bad" with a quieter voice would be its own defect.
        await AudioModule.setAudioModeAsync({
          allowsRecording: true,
          playsInSilentMode: true,
          shouldRouteThroughEarpiece: false,
        });
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
        await armBargeInWatch(() => stale);
      } catch {
        // Audio output only — the conversation is unaffected and goes on.
        if (!stale) {
          dispatch({ type: "speech_unavailable" });
        }
      }
    })();
    return () => {
      stale = true;
      clearBargeInWatch();
      setPlaying(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- speaking is a fresh object per turn entry; questions is stable for the session, and the voice fields are set by the same dispatch that sets the turn, so this closure always reads the current values
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
        // Usually a no-op now: the speaking driver already opened this
        // recorder, and the words the patient said while interrupting are in
        // it. Re-preparing here would throw those words away, which is the
        // exact failure a barge-in exists to avoid — so the recorder is only
        // started when nothing is running (a `typed` turn, a clip that never
        // played, a session whose voice went silent).
        if (recorder.isRecording) {
          return;
        }
        await openMicrophone();
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
      onFailed(stateRef.current.pending);
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
      clearBargeInWatch();
      stopPlayback();
      abortRef.current?.abort();
      if (!closedRef.current && stateRef.current.turn.phase === "listening") {
        void stopAndDiscardRecording();
      }
      void clearDialogueClips();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- unmount only
  }, []);

  // INT-340: no haptic while this conversation holds the audio session or the
  // microphone. The gate asks at fire time: the session is open until it
  // closes, and the microphone is whatever the recorder reports at that
  // moment, never a guess from the route or the turn.
  useEffect(
    () =>
      appHaptics.register({
        voiceSessionActive: () => !closedRef.current,
        micHot: () => recorder.isRecording,
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per session; both probes read live values
    [],
  );

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
    clearBargeInWatch();
    stopPlayback(); // synchronous — playback halts before anything else runs
    dispatch({ type: "barge_in" });
  };

  const leave = async () => {
    closedRef.current = true;
    clearBargeInWatch();
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
    readLevel: () => {
      try {
        return recorder.getStatus().metering;
      } catch {
        // The recorder is not running: no reading, which the orb treats as silence.
        return undefined;
      }
    },
  };
}

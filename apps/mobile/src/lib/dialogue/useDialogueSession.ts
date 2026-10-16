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
 *
 * INT-414 speaks a question turn as its PLANNED utterances: the opening's
 * welcome, or at most one lead-in, transition or acknowledgement, and then the
 * question verbatim (delivery.ts, deliveryPlan.ts). Every delivery clip is a
 * catalogue line minted from its deck key (`scriptedDeliveryTr`), never a
 * patient's words; the cue that picks it is read from the patient's last
 * action on this device and never awaited; and a lead-in whose clip is not
 * made yet is dropped for that turn, so the question is never late for it.
 *
 * INT-497 is the owner's "no delay, no seams, nothing robotic", in four parts,
 * each in its own pure module and wired here:
 *   - the turn ends when the patient stops talking (endpointer.ts), not when
 *     they find "Bitirdim" — the tap still works, and a tap that lands just
 *     after the turn ended itself is read as that, never as a barge-in;
 *   - a turn's clips play as ONE queue (turnQueue.ts), so a lead-in and its
 *     question have no player switch between them, and every clip is stored
 *     finished — one loudness, the pause its place calls for (clipFinish.ts);
 *   - a question whose clip is not made yet is fronted by a holding
 *     acknowledgement that is (holdingLine.ts), never dead silence;
 *   - the audio mode is set once per session, not re-applied every turn.
 * The turn timeline (turnTimeline.ts) measures what the patient waited.
 */
import { useEffect, useReducer, useRef, useState } from "react";
import { AudioModule, RecordingPresets, createAudioPlaylist, useAudioRecorder } from "expo-audio";

import { configuredServiceCandidates } from "../dev/expoHosts";
import { BARGE_IN_SAMPLE_MS, createSpeechOnsetDetector } from "./bargeIn";
import { EXTRACT_PORT, extractFromCandidates, type ExtractCandidate } from "../extract";
import type { IntakeQuestion } from "../intake/questions";
import { discardRecording, transcribeRecording } from "../voice";
import { answerShapeOf, autoEndAllowed } from "./autoEnd";
import { clearDialogueClips, createDialogueTtsLaneSelector, dialogueClipStore } from "./clips";
import { lastDeliveryKey, readCue, type DeliveryCue, type Utterance } from "./delivery";
import { deliveryClipName, leadSources, settleTurnClips, shownDelivery } from "./deliveryClips";
import {
  ENDPOINT_SAMPLE_MS,
  createEndpointer,
  createHangoverPolicy,
  isLateFinishTap,
  isLikelyCutOff,
  type AnswerShape,
  type Endpointer,
} from "./endpointer";
import { HOLDING_AFTER_MS, holdingLine, withHolding } from "./holdingLine";
import { playTurnQueue, type TurnQueue } from "./turnQueue";
import { createTurnTimeline, type EndpointKind, type TimelineSummary } from "./turnTimeline";
import type { DeliveryContext } from "./deliveryContext";
import {
  DELIVERY_DECK,
  prewarmContextOf,
  VOICE_DELIVERY_KEYS,
  type DeliveryKey,
} from "./deliveryDeck";
import {
  HESITANT_OPTION_IDS,
  planDialogueDelivery,
  questionContextOf,
  questionDeliveryContextOf,
} from "./deliveryPlan";
import { scriptedDeliveryTr } from "./georgeClip";
import { confirmSpeechTr, questionSpeechTr } from "./speech";
import {
  dialogueStreamReducer,
  initialDialogueStreamState,
  shouldAttemptSpeech,
  type DialogueStreamAction,
  type DialogueStreamState,
  type StreamEntry,
} from "./stream";
import { clipDeadlineMs, clipName, withDeadline, type ClipStore } from "./tts";
import type { DialogueCandidate } from "./turn";

/** The stream index of the latest `agent_question` entry, or -1. */
function lastQuestionIndex(stream: readonly StreamEntry[]): number {
  for (let index = stream.length - 1; index >= 0; index -= 1) {
    if (stream[index].kind === "agent_question") {
      return index;
    }
  }
  return -1;
}

/** Whether `work` settles — either way — within `ms`. Never rejects. */
function settlesWithin(work: Promise<unknown>, ms: number): Promise<boolean> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  return Promise.race([
    work.then(
      () => true,
      () => true,
    ),
    new Promise<boolean>((resolve) => {
      timer = setTimeout(() => resolve(false), ms);
    }),
  ]).finally(() => clearTimeout(timer));
}

/** Whether the question asked before stream index `index` was RED-adjacent. */
function previousWasRed(
  pack: readonly IntakeQuestion[],
  stream: readonly StreamEntry[],
  index: number,
): boolean {
  for (let at = index - 1; at >= 0; at -= 1) {
    const entry = stream[at];
    if (entry.kind === "agent_question") {
      const asked = pack.find((candidate) => candidate.id === entry.questionId);
      return asked !== undefined && questionContextOf(asked) === "red";
    }
  }
  return false;
}

export interface DialogueSessionOptions {
  questions: readonly IntakeQuestion[];
  /** The pack label the extract daemon receives (the visit's department). */
  packName: string;
  /** A per-visit id (never PHI) seeding the delivery variation (INT-414), so
   * one visit always replays the same words. */
  sessionSeed: string;
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
  /**
   * INT-414: what is said around each asked question, keyed by the stream
   * index of its `agent_question` entry. It is the plan the clips are spoken
   * from, narrowed to what the voice actually said: a lead-in dropped for want
   * of a clip is absent here too, and a turn whose clips are still settling
   * shows none yet (deliveryClips.ts `shownDelivery`). The transcript and the
   * voice therefore cannot say different things.
   */
  delivery: ReadonlyMap<number, readonly Utterance[]>;
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
  /** INT-497: what this session's turns cost the patient — durations only. */
  timeline: TimelineSummary;
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

/** Whether the confirmed values say "don't know / prefer not to say", or
 * differ from what was suggested — the two confirm-time delivery cues. */
function confirmCue(values: readonly string[], suggested: readonly string[]): DeliveryCue {
  if (values.some((value) => HESITANT_OPTION_IDS.has(value))) {
    return "hesitant";
  }
  const same =
    values.length === suggested.length && values.every((value) => suggested.includes(value));
  return same ? "none" : "revised";
}

export function useDialogueSession({
  questions,
  packName,
  sessionSeed,
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
  /** The turn's one queue of clips (INT-497): stopping it stops all audio. */
  const playerRef = useRef<TurnQueue | null>(null);
  /** One controller for every background extract of the session. */
  const abortRef = useRef<AbortController | null>(null);
  const closedRef = useRef(false);
  /** Single-shot guard for the stop affordances on one listen. */
  const finishingRef = useRef(false);
  /** Monotonic work id — the reconcile-behind address space. */
  const workRef = useRef(0);
  /** The level watch armed for the clip currently playing, if any. */
  const watchRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // INT-497 — end-of-turn detection and what the turns cost. The policy is
  // the SESSION's: a premature end widens every later turn's wait, never one.
  const policyRef = useRef(createHangoverPolicy());
  const endpointerRef = useRef<Endpointer | null>(null);
  /** The level watch armed for the open listen, if any. */
  const endpointWatchRef = useRef<ReturnType<typeof setInterval> | null>(null);
  /** When the last turn ended ITSELF; null when the patient tapped. */
  const autoEndedAtRef = useRef<number | null>(null);
  /** When a voice barge-in opened the current listen — the patient is already
   * speaking, so the endpointer counts their first words. */
  const voiceBargeInAtRef = useRef<number | null>(null);
  const timelineRef = useRef(createTurnTimeline());
  /** The audio mode is the same for the whole session: applied once. */
  const audioModeSetRef = useRef(false);
  /** The last delivery line actually said, and the last holding line. */
  const lastLineKeyRef = useRef<string | null>(null);
  const lastHoldingKeyRef = useRef<string | null>(null);
  /** Holding lines said, by the stream index of their question — the
   * transcript shows what the voice said (holdingLine.withHolding). */
  const [heldLines, setHeldLines] = useState<ReadonlyMap<number, Utterance>>(() => new Map());

  // INT-414 — conversational delivery. The cue is what the patient's LAST
  // action looked like (a barge-in, a "don't know", a correction, an empty
  // turn), recorded by the handlers below from signals already on the device
  // and never from audio (invariants 3 and 11). Each asked question takes the
  // pending cue the first time its entry is seen and keeps it, so the plan is
  // fixed per entry and every re-render reads the same words. `readCue` turns
  // anything unexpected into "none" on the spot; nothing here is awaited.
  const pendingCueRef = useRef<DeliveryCue>("none");
  const cuesRef = useRef(new Map<number, DeliveryCue>());
  state.stream.forEach((entry, index) => {
    if (entry.kind === "agent_question" && !cuesRef.current.has(index)) {
      cuesRef.current.set(
        index,
        readCue(() => pendingCueRef.current),
      );
      pendingCueRef.current = "none";
    }
  });
  const delivery = planDialogueDelivery(questions, state.stream, cuesRef.current, sessionSeed);
  const deliveryRef = useRef(delivery);
  deliveryRef.current = delivery;
  // What each turn's voice actually said, per delivery line, once its clips
  // have settled (deliveryClips.ts). State, not a ref: the transcript has to
  // re-render the moment a lead-in turns out to have been dropped.
  const [spokenLines, setSpokenLines] = useState<ReadonlyMap<number, readonly boolean[]>>(
    () => new Map(),
  );
  // The turn being spoken right now has not settled its clips yet, so the
  // transcript claims no delivery line for it until it has.
  const settlingIndex =
    state.turn.phase === "speaking" &&
    state.turn.intent === "question" &&
    shouldAttemptSpeech({ voiceMuted: state.voiceMuted, voiceRetryIn: state.voiceRetryIn })
      ? lastQuestionIndex(state.stream)
      : -1;
  const shownLines = new Map(
    [...delivery].map(([index, utterances]) => {
      // INT-497: a turn that said a holding line shows that line, not the
      // lines it did not say — the voice and the transcript stay one plan.
      const held = heldLines.get(index);
      return [
        index,
        held !== undefined
          ? withHolding(utterances, held)
          : shownDelivery(utterances, spokenLines.get(index), index === settlingIndex),
      ];
    }),
  );
  /** Delivery clips this session already holds: name → file. A lead-in whose
   * clip is here plays without a race; one that is not yet made is dropped
   * for this turn rather than waited for (deliveryClips.ts). */
  const readyLeadsRef = useRef(new Map<string, string>());

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
    player?.stop(); // synchronous pause inside, before anything else runs
  };

  /**
   * The session's one audio mode, applied once (INT-497). Every call site asks
   * for the same mode, and re-applying it on every turn put a native category
   * change on the critical path of every question for nothing.
   */
  const ensureAudioMode = async (mode: Parameters<typeof AudioModule.setAudioModeAsync>[0]) => {
    if (audioModeSetRef.current) {
      return;
    }
    await AudioModule.setAudioModeAsync(mode);
    audioModeSetRef.current = true;
  };

  /**
   * Open the microphone. One `prepareToRecordAsync` per turn, wherever the
   * turn started it — the speaking driver when the clip begins, the listening
   * driver when there was no clip.
   */
  const openMicrophone = async () => {
    await ensureAudioMode({
      allowsRecording: true,
      playsInSilentMode: true,
      shouldRouteThroughEarpiece: false,
    });
    await recorder.prepareToRecordAsync();
    recorder.record();
  };

  /** Play one turn's clips as one queue (turnQueue.ts); `onFinish` once at
   * the end. The timeline is told when audio really started, and every join. */
  const playQueue = (uris: readonly string[], isStale: () => boolean, onFinish: () => void) => {
    stopPlayback();
    const queue = playTurnQueue(createAudioPlaylist, uris, {
      now: Date.now,
      onStart: (at) => timelineRef.current.firstAudio(at),
      onJoin: (gap) => timelineRef.current.join(gap),
      onFinish: () => {
        if (!isStale() && playerRef.current === queue) {
          onFinish();
        }
      },
    });
    playerRef.current = queue;
    return queue;
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
        bargeInByVoice();
      }
    }, BARGE_IN_SAMPLE_MS);
    watchRef.current = timer;
  };

  const clearEndpointWatch = () => {
    if (endpointWatchRef.current !== null) {
      clearInterval(endpointWatchRef.current);
      endpointWatchRef.current = null;
    }
  };

  /**
   * Watch the level while the patient has the floor and take the turn when
   * they stop (INT-497). Every decision about WHETHER they have stopped lives
   * in endpointer.ts as a pure function; this only supplies samples — the
   * platform's own meter reading, never a buffer (invariant 3) — and takes the
   * turn exactly as the "Bitirdim" tap does.
   */
  const armEndpointWatch = (
    isStale: () => boolean,
    speakingAt: number | null,
    shape: AnswerShape,
  ) => {
    clearEndpointWatch(); // at most one watch is ever referenced
    const endpointer = createEndpointer(
      policyRef.current,
      speakingAt === null ? { shape } : { speakingAt, shape },
    );
    endpointerRef.current = endpointer;
    const timer = setInterval(() => {
      if (isStale() || stateRef.current.turn.phase !== "listening") {
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
      if (endpointer.sample(level, Date.now()) === "ended") {
        clearInterval(timer);
        // Asked again: a suggestion that landed during the listen can change
        // what the taking leads to. If it no longer speaks, the tap ends it.
        if (autoEndAllowed(questions, stateRef.current)) {
          void takeTurn("auto");
        }
      }
    }, ENDPOINT_SAMPLE_MS);
    endpointWatchRef.current = timer;
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

  /** The planned utterances of the latest ask of `questionId`, and the stream
   * index they belong to (INT-414). */
  const plannedTurn = (
    questionId: string,
  ): { readonly index: number; readonly utterances: readonly Utterance[] } => {
    const stream = stateRef.current.stream;
    for (let index = stream.length - 1; index >= 0; index -= 1) {
      const entry = stream[index];
      if (entry.kind === "agent_question" && entry.questionId === questionId) {
        return { index, utterances: deliveryRef.current.get(index) ?? [] };
      }
    }
    return { index: -1, utterances: [] };
  };

  /** Make one delivery line's clip, in the context it will be said in
   * (INT-415). The text is minted from its deck key and nothing else, so no
   * patient word can reach a synthesizer this way. */
  const ensureLead = (
    store: ClipStore,
    key: DeliveryKey,
    context: DeliveryContext,
  ): Promise<string> => {
    const name = deliveryClipName(key, context);
    return store.ensure(name, scriptedDeliveryTr(key), context).then((uri) => {
      readyLeadsRef.current.set(name, uri);
      return uri;
    });
  };

  /** A turn's lead-in clips, one per delivery line: the file when this session
   * holds it, else the making of it (which `settleTurnClips` never lets hold
   * the question). The one-to-one order is what `turnClips.spoken` is read
   * against. */
  const leadClipsFor = (
    store: ClipStore,
    turnPlan: readonly Utterance[],
  ): (string | Promise<string>)[] =>
    leadSources(turnPlan, readyLeadsRef.current, (key, context) => ensureLead(store, key, context));

  /**
   * The holding line for a late question (INT-497, holdingLine.ts), or null.
   * A re-ask carries the repair line and nothing is added to it; everything
   * else reads the cue this entry was planned with.
   */
  const holdingFor = (
    question: IntakeQuestion,
    index: number,
    turnPlan: readonly Utterance[],
  ): Utterance | null => {
    const stream = stateRef.current.stream;
    const reask = index > 0 && stream[index - 1].kind === "agent_unclear";
    return holdingLine({
      plan: turnPlan,
      questionContext: questionContextOf(question),
      cue: reask ? "repeat_request" : (cuesRef.current.get(index) ?? "none"),
      afterRed: previousWasRed(questions, stream, index),
      previousLineKey: lastLineKeyRef.current,
      lastHoldingKey: lastHoldingKeyRef.current,
      sessionSeed,
      turnIndex: index,
      isReady: (key, context) => readyLeadsRef.current.has(deliveryClipName(key, context)),
    });
  };

  /**
   * Say the holding line now; the question joins the same queue the moment
   * its clip is made, so it follows with no seam. If the holding line has
   * already finished by then, the question plays on its own. A question clip
   * that fails stops the holding line too: the turn goes silent honestly
   * rather than leaving an acknowledgement playing into the patient's turn.
   */
  const speakWithHolding = async (
    holding: Utterance,
    index: number,
    questionClip: Promise<string>,
    isStale: () => boolean,
    done: () => void,
    onStarted: () => void,
  ): Promise<void> => {
    const uri = readyLeadsRef.current.get(
      deliveryClipName(holding.key as DeliveryKey, holding.deliveryContext),
    );
    if (uri === undefined) {
      throw new Error("holding_clip_missing"); // holdingLine only picks ready clips
    }
    lastHoldingKeyRef.current = holding.key;
    lastLineKeyRef.current = holding.key;
    setHeldLines((before) => new Map(before).set(index, holding));
    let questionQueued = false;
    const queue = playQueue([uri], isStale, () => {
      if (questionQueued) {
        done();
      }
    });
    // Runtime review: interruptible from the holding line's first word, not
    // from the late question's.
    onStarted();
    let questionUri: string;
    try {
      questionUri = await questionClip;
    } catch (error) {
      if (!isStale()) {
        stopPlayback();
      }
      throw error;
    }
    if (isStale()) {
      return;
    }
    if (queue.append(questionUri)) {
      questionQueued = true;
    } else {
      playQueue([questionUri], isStale, done);
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
  //
  // INT-414 adds the delivery lines on the same terms: the opening's welcome
  // with the first question, and the rest of the spoken deck only after every
  // question, so a lead-in never competes with a question for the lane and is
  // already made when a later turn picks it.
  useEffect(() => {
    let stale = false;
    (async () => {
      const warm = (store: ClipStore, question: IntakeQuestion): Promise<unknown>[] => {
        // A question's context follows from its declarations alone, so it is
        // the same here as on its turn and the warm clip is the one used.
        const context = questionDeliveryContextOf(question);
        const clips = [
          store.ensure(clipName("question", question.id), questionSpeechTr(question), context),
        ];
        if (question.kind === "text") {
          // The generic confirm line is scripted too — free text never
          // names a clip and patient words are never synthesized.
          clips.push(
            store.ensure(clipName("confirm", question.id), confirmSpeechTr(question, []), context),
          );
        }
        return clips;
      };
      try {
        const store = await clipStore();
        if (stale || questions.length === 0) {
          return;
        }
        const opening = leadClipsFor(store, deliveryRef.current.get(0) ?? []);
        await Promise.allSettled([...opening, ...warm(store, questions[0])]);
        if (stale) {
          return;
        }
        await Promise.allSettled(questions.slice(1).flatMap((q) => warm(store, q)));
        if (stale) {
          return;
        }
        // The other welcome variants are never said again in this visit.
        const openingOnly = new Set<string>([
          ...DELIVERY_DECK.welcome,
          ...DELIVERY_DECK.orientVoice,
        ]);
        await Promise.allSettled(
          VOICE_DELIVERY_KEYS.filter((key) => !openingOnly.has(key)).map((key) =>
            ensureLead(store, key, prewarmContextOf(key)),
          ),
        );
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
      // INT-497 runtime review: reopen the microphone FIRST. The turn before
      // this one may have ended itself, which stopped the recorder, and
      // anything the patient adds after that pause must land in the next
      // recording rather than in a closed microphone. A failure here costs
      // barge-in and nothing else, exactly as in armBargeInWatch; the
      // listening driver tries again and owns the hard failure.
      if (!recorder.isRecording) {
        try {
          await openMicrophone();
        } catch {
          // barge-in only — see above
        }
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
        // INT-414: a question turn is said as its planned utterances — the
        // lead-in or acknowledgement first, the question verbatim last. A
        // confirm turn is a read-back and carries none.
        const planned =
          speaking.intent === "question"
            ? plannedTurn(question.id)
            : { index: -1, utterances: [] as readonly Utterance[] };
        const turnPlan = planned.utterances;
        // INT-415: the question (and its read-back) is spoken in the
        // question's own context — the same one the pre-warm made it in.
        const questionContext = questionDeliveryContextOf(question);
        // INT-261: the ladder may take as long as it likes; the patient may
        // not be made to wait more than this clip's own worth of work. A
        // lead-in whose clip is not made yet is dropped for this turn rather
        // than waited for (deliveryClips.ts) — only the opening waits for its
        // own welcome, which IS that turn's content.
        const deadlineMs = clipDeadlineMs(speech);
        const questionClip = withDeadline(store.ensure(name, speech, questionContext), deadlineMs);
        questionClip.catch(() => undefined); // observed below, on every path
        const awaitLeads = turnPlan.some((utterance) => utterance.deliveryContext === "welcome");
        // `allowsRecording: true` while the agent speaks is the whole change.
        // On iOS this is the `.playAndRecord` category, which is the only one
        // that admits simultaneous play and capture; `shouldRouteThroughEarpiece:
        // false` is stated rather than left to the default because the same
        // category is what puts audio on the receiver, and answering "the voice
        // sounds bad" with a quieter voice would be its own defect. INT-497:
        // applied once per session, in parallel with the clip, not per turn.
        const audioMode = ensureAudioMode({
          allowsRecording: true,
          playsInSilentMode: true,
          shouldRouteThroughEarpiece: false,
        });
        audioMode.catch(() => undefined); // awaited below; never unhandled meanwhile
        // INT-497: a pre-warmed question settles inside HOLDING_AFTER_MS. One
        // that does not is still being made, and the patient who just finished
        // speaking hears a ready acknowledgement now instead of dead silence.
        const late =
          speaking.intent === "question" &&
          planned.index >= 0 &&
          !awaitLeads &&
          !(await settlesWithin(questionClip, HOLDING_AFTER_MS));
        const holding = late ? holdingFor(question, planned.index, turnPlan) : null;
        await audioMode;
        if (stale) {
          return;
        }
        const done = () => {
          stopPlayback();
          dispatch({ type: "speech_done" });
        };
        // The agent is audible from here: the caption says so and the barge-in
        // watch arms — for the holding line as for any first clip.
        const started = () => {
          setPlaying(true);
          void armBargeInWatch(() => stale);
        };
        if (holding !== null) {
          await speakWithHolding(holding, planned.index, questionClip, () => stale, done, started);
        } else {
          // Never the same line twice in a row: a planned line the previous
          // turn already said (as its holding line) is not said again.
          const fresh = turnPlan.map((utterance) =>
            utterance.kind !== "question" && utterance.key === lastLineKeyRef.current
              ? { ...utterance, key: "" }
              : utterance,
          );
          const turnClips = await settleTurnClips(questionClip, leadClipsFor(store, fresh), {
            awaitLeads,
            deadlineMs,
          });
          if (stale) {
            return;
          }
          // The transcript shows what is about to be said and nothing else: a
          // lead-in dropped above is dropped from the screen too.
          if (planned.index >= 0) {
            const said = turnClips.spoken;
            setSpokenLines((before) => new Map(before).set(planned.index, said));
          }
          if (speaking.intent === "question") {
            const saidLines = fresh.filter((utterance) => utterance.kind !== "question");
            lastLineKeyRef.current = lastDeliveryKey(
              saidLines.filter((_, at) => turnClips.spoken[at] === true),
            );
          }
          // One queue for the whole turn (turnQueue.ts): the utterances play
          // strictly in order with no player switch between them, and a
          // barge-in stops the queue — and so the turn — in one call.
          playQueue([...turnClips.leads, turnClips.question], () => stale, done);
          started();
        }
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
    // A voice barge-in opened this listen: the patient is already talking.
    const speakingAt = voiceBargeInAtRef.current;
    voiceBargeInAtRef.current = null;
    (async () => {
      try {
        // Usually a no-op now: the speaking driver already opened this
        // recorder, and the words the patient said while interrupting are in
        // it. Re-preparing here would throw those words away, which is the
        // exact failure a barge-in exists to avoid — so the recorder is only
        // started when nothing is running (a `typed` turn, a clip that never
        // played, a session whose voice went silent).
        if (!recorder.isRecording) {
          await openMicrophone();
        }
      } catch {
        if (!stale) {
          dispatch({ type: "failure" });
        }
        return;
      }
      // INT-497: the turn ends when they stop — but only where taking it leads
      // to a spoken turn, whose driver reopens the microphone (autoEnd.ts). On
      // the last question the tap ends the turn. A free-text or RED-adjacent
      // question gets the long wait from the first word.
      if (!stale && autoEndAllowed(questions, stateRef.current)) {
        armEndpointWatch(() => stale, speakingAt, answerShapeOf(questions[listening.step]));
      }
    })();
    return () => {
      stale = true;
      clearEndpointWatch();
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
      clearEndpointWatch();
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

  /** Take the patient's turn — "Bitirdim", tap-to-stop, or (INT-497) the
   * end of their speech: close the mic and advance NOW (ask-ahead);
   * transcription and extraction reconcile behind under this work id. The
   * ref guard keeps the affordances single-shot, whichever lands first. */
  const takeTurn = async (endpoint: EndpointKind) => {
    if (finishingRef.current || stateRef.current.turn.phase !== "listening") {
      return;
    }
    finishingRef.current = true;
    const question = questions[stateRef.current.turn.step];
    const endpointer = endpointerRef.current;
    endpointerRef.current = null;
    clearEndpointWatch();
    // The timeline measures from the last voiced sample, which the tap and
    // the endpointer both know: the tap often lands while the voice is still
    // in the air, and that is exactly the wait the gap must include.
    const takenAt = endpoint === "auto" ? (endpointer?.endedAt ?? Date.now()) : Date.now();
    autoEndedAtRef.current = endpoint === "auto" ? takenAt : null;
    timelineRef.current.turnTaken({
      endpoint,
      speechEndAt: endpointer?.lastVoicedAt ?? null,
      at: takenAt,
    });
    let uri: string | null = null;
    try {
      await recorder.stop();
      uri = recorder.uri;
    } catch {
      dispatch({ type: "failure" });
      return;
    }
    const workId = (workRef.current += 1);
    if (uri === null) {
      // INT-414: a turn that carried no words — the next question goes
      // gently. Set BEFORE the dispatch, which is what asks that question.
      pendingCueRef.current = "long_silence";
    }
    dispatch({ type: "utterance", workId }); // the next question speaks NOW
    if (uri === null) {
      // Nothing was captured — the bubble goes; the question falls to the
      // manual steps at the end if nothing else fills it.
      dispatch({ type: "transcript_ready", workId, text: "" });
      dispatch({ type: "extract_settled", workId, candidates: {} });
      return;
    }
    let transcript = "";
    const handedOverAt = Date.now();
    try {
      transcript = await transcribeRecording(uri); // deletes the file after upload
      timelineRef.current.asrSettled(Date.now() - handedOverAt);
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

  const finishListening = () => takeTurn("tap");

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

  /** Stop the agent NOW and give the patient the floor — the one interrupt
   * both causes share, so they cannot diverge into two state machines. */
  const interrupt = () => {
    clearBargeInWatch();
    stopPlayback(); // synchronous — playback halts before anything else runs
    // INT-414: they cut in, so the next question comes with less, not more.
    pendingCueRef.current = "barge_in";
    dispatch({ type: "barge_in" });
  };

  /** The tap on the speaking bubble. INT-497: one that lands just after the
   * turn ended ITSELF is the "Bitirdim" the patient was already reaching for,
   * and interrupting the question it would land on is not what they meant. */
  const bargeIn = () => {
    if (isLateFinishTap(autoEndedAtRef.current, Date.now())) {
      return;
    }
    interrupt();
  };

  /** The patient's voice over the agent. INT-497: right after an automatic
   * end, that is the turn having ended too early — every later turn of this
   * session waits a step longer (endpointer.ts), and this listen counts the
   * words already being said. */
  const bargeInByVoice = () => {
    const now = Date.now();
    if (isLikelyCutOff(autoEndedAtRef.current, now)) {
      policyRef.current.noteCutOff();
    }
    voiceBargeInAtRef.current = now;
    interrupt();
  };

  /** The confirm tap. Its values say whether the patient did not know, or
   * corrected the suggestion — each answered by the next question's line. */
  const confirm = (values: string[]) => {
    const turn = stateRef.current.turn;
    if (turn.phase === "confirming") {
      const cue = confirmCue(values, turn.candidate.values);
      if (cue !== "none") {
        pendingCueRef.current = cue;
      }
    }
    dispatch({ type: "confirm", values });
  };

  const leave = async () => {
    closedRef.current = true;
    clearBargeInWatch();
    clearEndpointWatch();
    stopPlayback();
    abortRef.current?.abort();
    if (stateRef.current.turn.phase === "listening") {
      await stopAndDiscardRecording();
    }
    await clearDialogueClips();
  };

  return {
    state,
    delivery: shownLines,
    playing,
    bargeIn,
    finishListening,
    sendTyped,
    leave,
    confirm,
    confirmPending: (questionId) => dispatch({ type: "confirm_pending", questionId }),
    speakCorrection: () => {
      pendingCueRef.current = "revised"; // they are correcting what we suggested
      dispatch({ type: "speak" });
    },
    timeline: timelineRef.current.summary(),
  };
}

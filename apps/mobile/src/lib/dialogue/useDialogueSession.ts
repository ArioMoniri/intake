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
 * The capture that hears the interruption IS the patient's answer. That is
 * the design, not an optimisation — a barge-in whose opening words are lost is
 * a patient made to repeat themselves. INT-559 changed what that capture IS:
 * no recorder and no file, but expo-audio's PCM stream into a bounded
 * in-memory buffer (lib/capture: ≤ 60 s, zeroed on finish, discard, RED,
 * leave and app background), handed to the dev ASR daemon as bytes. One
 * capture turn per dialogue turn, wherever the turn opened it. The watcher
 * reads a level computed from the chunk that just arrived, never a buffer
 * kept for it. On iOS the stream's session category silences playback, so
 * there the clip plays tap-interruptible and the microphone opens when the
 * turn becomes the patient's (lib/capture/policy.ts).
 *
 * Audio hygiene: clips under cacheDirectory/dialogue/ are AGENT-voice
 * audio synthesized from catalog tr strings, deleted wholesale on
 * unmount AND on session end. PATIENT audio never has a file to delete
 * (invariant 3, with no dev exception — INT-559). The numeral guard sits
 * inside the synth path (invariant 22 mirror).
 *
 * INT-414 speaks a question turn as its PLANNED utterances: the opening's
 * welcome, or at most one lead-in, transition or acknowledgement, and then the
 * question verbatim (delivery.ts, deliveryPlan.ts). Every delivery clip is a
 * catalogue line minted from its deck key (`scriptedDeliveryTr`), never a
 * patient's words; the cue that picks it is read from the patient's last
 * action on this device and never awaited; and a lead-in whose clip is not
 * made yet is dropped for that turn, so the question is never late for it.
 */
import { useEffect, useReducer, useRef, useState } from "react";
import { Platform } from "react-native";
import { AudioModule, createAudioPlayer, type AudioPlayer } from "expo-audio";

import { useAppStateChange } from "../capture/appState";
import { createExpoPcmStream } from "../capture/expoStream";
import { createMicrophone, type Microphone } from "../capture/microphone";
import { micMayOpenWhileSpeaking } from "../capture/policy";
import { createCaptureTurn } from "../capture/turn";
import { configuredServiceCandidates } from "../dev/expoHosts";
import { BARGE_IN_SAMPLE_MS, createSpeechOnsetDetector } from "./bargeIn";
import { EXTRACT_PORT, extractFromCandidates, type ExtractCandidate } from "../extract";
import type { IntakeQuestion } from "../intake/questions";
import { transcribeSegment } from "../voice";
import { clearDialogueClips, createDialogueTtsLaneSelector, dialogueClipStore } from "./clips";
import { readCue, type DeliveryCue, type Utterance } from "./delivery";
import { deliveryClipName, leadSources, settleTurnClips, shownDelivery } from "./deliveryClips";
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
  /** The dialogue's one microphone (INT-559, lib/capture/microphone.ts): a
   * capture turn per dialogue turn, never a recorder, wherever the turn opened
   * it. Two drivers asking at once share one open, and a discard reaches an
   * open at whichever await it is suspended in. Made on first use. */
  const microphoneRef = useRef<Microphone | null>(null);
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

  const microphone = (): Microphone => {
    microphoneRef.current ??= createMicrophone({
      prepare: () =>
        AudioModule.setAudioModeAsync({
          allowsRecording: true,
          playsInSilentMode: true,
          shouldRouteThroughEarpiece: false,
        }),
      createTurn: (closed) =>
        createCaptureTurn({
          createStream: createExpoPcmStream,
          transcribe: transcribeSegment,
          closed,
        }),
      closed: () => closedRef.current,
    });
    return microphoneRef.current;
  };
  /** Read through the ref: a microphone never made has never opened, and has nothing to discard. */
  const isCapturing = () => microphoneRef.current?.capturing === true;

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
    [...delivery].map(([index, utterances]) => [
      index,
      shownDelivery(utterances, spokenLines.get(index), index === settlingIndex),
    ]),
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
   * Open the microphone. One capture turn per dialogue turn, wherever the
   * turn started it — the speaking driver when the clip begins (Android), the
   * listening driver when there was no clip or the platform could not have
   * both (iOS, lib/capture/policy.ts). The microphone reads `closedRef` and
   * its own discards after every await (INT-551's pattern, carried up to the
   * audio-session switch by the review of #964): a RED, a typed answer, the
   * app leaving the foreground or an unmount that lands while the session
   * switches or the stream starts leaves no microphone behind it.
   */
  const openMicrophone = () => microphone().open();

  /** Close whatever microphone is open, or still opening, and zero its buffer; nothing is sent. */
  const discardCapture = () => microphoneRef.current?.discard();

  /**
   * Watch the level while the agent speaks and interrupt on a real onset.
   *
   * Every decision about WHETHER a level pattern is a barge-in lives in
   * `bargeIn.ts`, where it is a pure function and therefore testable without a
   * microphone; this closure only supplies samples and stops on `"fired"`.
   * `levelDbfs()` is computed from the chunk that just arrived — no buffer is
   * kept for it, and nothing is written (invariant 3).
   *
   * The watch is torn down by the same `stale` flag the clip is: the effect's
   * cleanup runs on every turn change, so a timer can never outlive the clip
   * it was watching.
   */
  const armBargeInWatch = async (isStale: () => boolean) => {
    clearBargeInWatch(); // at most one watch is ever referenced
    if (!isCapturing()) {
      if (!micMayOpenWhileSpeaking(Platform.OS)) {
        // iOS: expo-audio's stream would silence the clip (lib/capture/policy.ts),
        // so the clip plays tap-interruptible and the listening driver opens
        // the microphone — which is where the product was before INT-291.
        return;
      }
      // A mic denial already ended the session upstream; a failure to open it
      // HERE costs barge-in and nothing else, so the turn goes on silently
      // interruptible by tap, which is where the product was before INT-291.
      try {
        await openMicrophone();
      } catch {
        return;
      }
    }
    if (isStale() || !isCapturing()) {
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
      const level = microphoneRef.current?.current()?.levelDbfs();
      if (detector.sample(level, Date.now()) === "fired") {
        clearInterval(timer);
        bargeIn();
      }
    }, BARGE_IN_SAMPLE_MS);
    watchRef.current = timer;
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
        const turnClips = await settleTurnClips(
          withDeadline(store.ensure(name, speech, questionContext), clipDeadlineMs(speech)),
          leadClipsFor(store, turnPlan),
          {
            awaitLeads: turnPlan.some((utterance) => utterance.deliveryContext === "welcome"),
            deadlineMs: clipDeadlineMs(speech),
          },
        );
        const queue = [...turnClips.leads, turnClips.question];
        if (stale) {
          return;
        }
        // The transcript shows what is about to be said and nothing else: a
        // lead-in dropped above is dropped from the screen too.
        if (planned.index >= 0) {
          const said = turnClips.spoken;
          setSpokenLines((before) => new Map(before).set(planned.index, said));
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
        // One player at a time, always cleared before the next clip, so the
        // utterances of a turn play strictly in order and never overlap. A
        // barge-in clears `playerRef`, which is what stops the chain: the
        // finished clip's listener no longer owns the player and plays nothing.
        const playNext = () => {
          const uri = queue.shift();
          if (uri === undefined) {
            return;
          }
          const last = queue.length === 0;
          stopPlayback();
          const player = createAudioPlayer({ uri });
          playerRef.current = player;
          player.addListener("playbackStatusUpdate", (status) => {
            if (status.didJustFinish && !stale && playerRef.current === player) {
              if (last) {
                stopPlayback();
                dispatch({ type: "speech_done" });
              } else {
                playNext();
              }
            }
          });
          player.play();
        };
        playNext();
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
        // On Android usually a no-op: the speaking driver already opened this
        // capture, and the words the patient said while interrupting are in
        // it. Opening a second one would throw those words away, which is the
        // exact failure a barge-in exists to avoid — so the microphone is only
        // opened when nothing is capturing (iOS, a `typed` turn, a clip that
        // never played, a session whose voice went silent).
        if (isCapturing()) {
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
      discardCapture();
      void clearDialogueClips();
      onDone();
    } else if (state.turn.phase === "failed") {
      closedRef.current = true;
      abortRef.current?.abort();
      discardCapture();
      void clearDialogueClips();
      onFailed(stateRef.current.pending);
    } else if (state.turn.phase === "handoff") {
      closedRef.current = true;
      abortRef.current?.abort();
      discardCapture();
      void clearDialogueClips();
      onHandoff(stateRef.current.pending);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- terminal transitions only
  }, [state.turn.phase]);

  // Unmount: stop audio both ways and delete the whole agent-clip cache.
  // Whatever microphone is open is closed and zeroed, the speaking turn's
  // barge-in one included (INT-551's finding; before it only a listening
  // turn's was). The session closes first, as `leave` does: a driver that
  // resumes past an await after this opens nothing (the review of #964).
  useEffect(() => {
    return () => {
      closedRef.current = true;
      clearBargeInWatch();
      stopPlayback();
      abortRef.current?.abort();
      discardCapture();
      void clearDialogueClips();
    };
  }, []);

  // INT-559: the app leaving the foreground is a zeroing trigger (invariant
  // 3). Whatever microphone is open closes and its buffer zeroes; nothing is
  // sent. Back in the foreground mid-listen, the microphone reopens so the
  // patient can go on — what was said before is gone, and the turn does not
  // pretend otherwise.
  useAppStateChange((status) => {
    if (status !== "active") {
      discardCapture();
      return;
    }
    if (!closedRef.current && stateRef.current.turn.phase === "listening" && !isCapturing()) {
      openMicrophone().catch(() => undefined);
    }
  });

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
    // The microphone closes NOW, synchronously inside `finish`; the segments
    // it handed out at the cap are already with the ASR daemon and the tail
    // follows (lib/capture/turn.ts). Nothing of this turn's audio is held
    // past this line, and an open still in flight is abandoned by the
    // hand-over, so no microphone opens behind the patient's "done".
    const turn = microphoneRef.current?.take() ?? null;
    const heard = turn?.heard === true;
    const settling: Promise<string | null> = turn === null ? Promise.resolve(null) : turn.finish();
    settling.catch(() => undefined); // awaited below; never an unhandled rejection
    const workId = (workRef.current += 1);
    if (!heard) {
      // INT-414: a turn that carried no words — the next question goes
      // gently. Set BEFORE the dispatch, which is what asks that question.
      pendingCueRef.current = "long_silence";
    }
    dispatch({ type: "utterance", workId }); // the next question speaks NOW
    if (!heard) {
      // Nothing was captured — the bubble goes; the question falls to the
      // manual steps at the end if nothing else fills it.
      dispatch({ type: "transcript_ready", workId, text: "" });
      dispatch({ type: "extract_settled", workId, candidates: {} });
      return;
    }
    let transcript = "";
    try {
      transcript = (await settling) ?? "";
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
    }
    // The typed words are the answer: whatever the microphone held — an
    // abandoned listen, or the barge-in capture under the clip — is zeroed
    // now, never sent.
    discardCapture();
    const workId = (workRef.current += 1);
    dispatch({ type: "typed", workId, text });
    // During the end wait there is no live question; enrich everything.
    await runExtract(workId, text, step >= 0 ? questions[step] : null);
  };

  const bargeIn = () => {
    clearBargeInWatch();
    stopPlayback(); // synchronous — playback halts before anything else runs
    // INT-414: they cut in, so the next question comes with less, not more.
    pendingCueRef.current = "barge_in";
    dispatch({ type: "barge_in" });
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
    closedRef.current = true; // first: every driver past an await reads it before it acts
    clearBargeInWatch();
    stopPlayback();
    abortRef.current?.abort();
    // Whatever microphone is open — a listen, or the barge-in capture under
    // the clip — closes and zeroes here, synchronously, before anything is
    // awaited: a RED is what calls this (DialogueIntake), and the RED path
    // waits on nothing (invariants 9 and 21).
    discardCapture();
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
  };
}

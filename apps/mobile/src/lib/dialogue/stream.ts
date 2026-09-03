/**
 * Ask-ahead conversation engine (INT-235; deepened by INT-239). Dev-tier
 * mirror of the blueprint IntakeEngine's ask-ahead/reconcile-behind
 * pattern (02/INT-081): the next scripted question does NOT depend on the
 * previous answer's EXTRACTION — so the turn advances the instant an
 * utterance is taken, and transcribe→extract reconcile BEHIND, addressed
 * by work id. The one honest wait is `settling` at the END while
 * in-flight work drains.
 *
 * ANSWER-DRIVEN (INT-239): which questions exist at all IS decided by the
 * answers. `advance` walks only the APPLICABLE questions — `askIf`
 * evaluated against the CONFIRMED answers, exactly as the typed StepFlow
 * and the section panel do, so all three surfaces ask the same set. This
 * is the Kleene rule from files/13 §9.2 at dev tier: an unanswered gating
 * question is UNKNOWN and UNKNOWN does not open a gate, and a suggestion
 * is not an answer, so only a confirm can open one. A suggestion that
 * lands for a still-closed gate is kept, not dropped: it becomes that
 * question's quick confirm turn the moment the gate opens.
 *
 * Rules the tests pin:
 * - The chat log is stateful by workId: the patient bubble exists from
 *   the utterance on and the ASR text replaces it IN PLACE.
 * - Reconcile fills sections as pending SUGGESTIONS; per question the
 *   newest work id wins, late older results are dropped; a live turn is
 *   never moved by a reconcile.
 * - Advance skips answered AND already-asked questions; a question with
 *   a landed suggestion gets the quick spoken CONFIRM turn (candidate
 *   pre-selected, one tap, no wait) — retroactively too, from settling.
 * - Typed input is the SAME conversation: a typed utterance behaves
 *   exactly like a spoken one (voice and text are one flow).
 * - Completion (the owner's rule): every question answered → done, the
 *   caller lands on the review. Settled with unanswered left → handoff:
 *   leftovers go to the manual steps (with any remaining suggestions as
 *   prefill), and only those.
 *
 * SILENCE IS NOT FAILURE (INT-261): the agent's audio is an OUTPUT, not
 * the conversation. The question TEXT is in its bubble the moment the turn
 * opens, the mic records, the composer sends, extraction reconciles and the
 * confirm turn commits — none of that reads a byte of agent audio. So a clip
 * that cannot be synthesized raises `speech_unavailable`, which moves the
 * turn exactly where `speech_done` would have and latches `voiceMuted` for
 * the rest of the session; it never ends the conversation. `failure` is
 * reserved for what genuinely does end it: no microphone, no ASR.
 *
 * Invariant 1 posture: candidates are SUGGESTIONS — the only commit
 * paths are the confirm turn, the panel-row confirm and the manual steps
 * after handoff. Nothing auto-commits. Quotes are display-only
 * provenance; agent speech stays catalog-composed (speech.ts).
 *
 * The INT-233 single-question engine (turn.ts) remains the tested
 * reference for the blocking per-turn machine; this module supersedes it
 * on the app surface and reuses its candidate/turn vocabulary.
 */
import { askIfMet, type AnsweredValues, type IntakeQuestion } from "../intake/questions";
import type { DialogueCandidate } from "./turn";

export interface CommittedAnswer {
  values: string[];
  /** Verbatim patient words behind the answer; empty when typed fresh. */
  quote: string;
}

export type StreamTurn =
  | { phase: "speaking"; step: number; intent: "question" }
  | { phase: "speaking"; step: number; intent: "confirm"; candidate: DialogueCandidate }
  | { phase: "listening"; step: number }
  | { phase: "confirming"; step: number; candidate: DialogueCandidate }
  /** Everything asked; the one honest wait while in-flight work drains. */
  | { phase: "settling" }
  /** Settled with unanswered questions left → the manual steps take over. */
  | { phase: "handoff" }
  | { phase: "done" }
  | { phase: "failed" };

export type StreamEntry =
  | { kind: "agent_question"; questionId: string }
  | { kind: "agent_confirm"; questionId: string; values: string[] }
  /** One patient utterance; `transcribing` until the ASR text replaces
   * the bubble in place. Typed utterances are born as `text`. */
  | { kind: "patient"; workId: number; status: "transcribing" | "text"; text: string };

export interface DialogueStreamState {
  turn: StreamTurn;
  /** Reconciled suggestions awaiting the patient's confirm. */
  pending: Record<string, DialogueCandidate>;
  /** Answers the patient confirmed, with quote provenance. */
  answers: Record<string, CommittedAnswer>;
  /** Question ids whose utterance was taken — never re-asked. */
  asked: readonly string[];
  /** Work ids whose transcribe→extract pipeline has not settled. */
  inflight: readonly number[];
  /** Per-question work id behind the current suggestion (ordering). */
  seq: Record<string, number>;
  /** The chat transcript, oldest first. */
  stream: readonly StreamEntry[];
  /**
   * The agent has no voice RIGHT NOW (INT-261, corrected by INT-294).
   *
   * INT-261 latched this for the session and gave a cost argument for it:
   * re-probing the TTS ladder every turn would spend the turn budget twice
   * per question to arrive at the same answer. That was true of an admission
   * walk which cost the whole clip deadline, and it is not true of one bounded
   * to a single admission. What the latch cost instead was measured on 2 Sep
   * 2026: one slow FIRST turn, and the rest of the visit in silence with a
   * healthy Freya answering in 0.8 s throughout.
   *
   * So this is a report about the last clip, not a property of the session.
   * A clip that PLAYS clears it; a turn nobody attempted cannot.
   */
  voiceMuted: boolean;
  /**
   * Consecutive turns whose clip could not be produced. Only a clip that
   * played resets it, which is what makes recovery observable rather than
   * assumed.
   */
  voiceFailures: number;
  /**
   * Speaking turns still to pass before speech is attempted again.
   *
   * Each consecutive failure buys one further turn of silence
   * (`voiceRetryIn = voiceFailures - 1`), so the first failure retries at
   * once and a lane that is genuinely gone stops costing an admission per
   * question. No constant is chosen here: the schedule is the failure count.
   */
  voiceRetryIn: number;
}

export type DialogueStreamAction =
  | { type: "speech_done" }
  /**
   * The agent could not produce audio for this turn (INT-261). The turn
   * proceeds exactly as `speech_done` would have — the question is already
   * on screen — and the session is silent until a clip plays again.
   */
  | { type: "speech_unavailable" }
  /**
   * The driver did not attempt a clip this turn — the voice is silent and a
   * cooldown is still owed (INT-294). The turn advances exactly as
   * `speech_done` does, and the silence is one turn closer to its next
   * attempt. It can never clear the caption: a turn nobody tried is not
   * evidence that the voice came back.
   */
  | { type: "speech_skipped" }
  | { type: "barge_in" }
  /** From the confirm card: the patient speaks the correction instead. */
  | { type: "speak" }
  /** The spoken utterance is taken (mic closed) — advance NOW. */
  | { type: "utterance"; workId: number }
  /** Composer submit — the typed utterance, same conversation. */
  | { type: "typed"; workId: number; text: string }
  /** ASR finished for one utterance; empty text drops the bubble. */
  | { type: "transcript_ready"; workId: number; text: string }
  /** The utterance's extract pipeline is over (empty on soft failure). */
  | { type: "extract_settled"; workId: number; candidates: Record<string, DialogueCandidate> }
  /** Confirm the live turn's candidate with the on-screen values. */
  | { type: "confirm"; values: string[] }
  /** The panel-row confirm: accept one pending suggestion. */
  | { type: "confirm_pending"; questionId: string }
  /** Hard service failure (TTS/ASR) — terminal, falls to manual. */
  | { type: "failure" };

export function initialDialogueStreamState(pack: readonly IntakeQuestion[]): DialogueStreamState {
  return {
    turn: { phase: "speaking", step: 0, intent: "question" },
    pending: {},
    answers: {},
    asked: [],
    inflight: [],
    seq: {},
    stream: pack.length > 0 ? [{ kind: "agent_question", questionId: pack[0].id }] : [],
    voiceMuted: false,
    voiceFailures: 0,
    voiceRetryIn: 0,
  };
}

/**
 * Should the speaking driver ask for a clip on this turn?
 *
 * Pure, and exported, because it is the one decision the INT-261 driver took
 * inline and got wrong: it read a latched `voiceMuted` and never asked again.
 * A silent session retries as soon as its cooldown is spent, and the cooldown
 * exists only so that a lane which is genuinely gone costs a bounded
 * admission every few turns rather than one per question.
 */
export function shouldAttemptSpeech(
  state: Pick<DialogueStreamState, "voiceMuted" | "voiceRetryIn">,
): boolean {
  return !state.voiceMuted || state.voiceRetryIn === 0;
}

function currentQuestionId(pack: readonly IntakeQuestion[], turn: StreamTurn): string | undefined {
  return "step" in turn ? pack[turn.step]?.id : undefined;
}

/**
 * The confirmed answers as the gate evaluator wants them — the single
 * bridge between the conversation state and the pack's `askIf` layer.
 * Only CONFIRMED answers count: a pending suggestion is not an answer, so
 * it can never open a gate on its own (invariant 1 posture).
 */
export function committedAnswers(state: Pick<DialogueStreamState, "answers">): AnsweredValues[] {
  return Object.entries(state.answers).map(([questionId, answer]) => ({
    questionId,
    values: answer.values,
  }));
}

/**
 * Ask-ahead advance: in pack order over the APPLICABLE questions —
 * answered questions are skipped, a question whose gate the answers do not
 * meet is skipped entirely (never asked, never counted as left over), a
 * landed suggestion opens as its quick confirm turn (consumed from
 * pending), an asked-awaiting question is skipped (its result reconciles
 * behind), and the first untouched question is asked. Nothing left:
 * all answered → done; work in flight → settling; otherwise → handoff.
 */
function advance(
  pack: readonly IntakeQuestion[],
  state: Omit<DialogueStreamState, "turn">,
): DialogueStreamState {
  const { pending, answers, asked, inflight, seq, stream } = state;
  const committed = committedAnswers({ answers });
  let unansweredLeft = false;
  for (let step = 0; step < pack.length; step += 1) {
    const question = pack[step];
    if (answers[question.id] !== undefined) {
      continue;
    }
    if (!askIfMet(question.askIf, committed)) {
      continue; // the answers do not ask for this question at all
    }
    unansweredLeft = true;
    const candidate = pending[question.id];
    if (candidate !== undefined) {
      const rest = { ...pending };
      delete rest[question.id];
      return {
        ...state,
        pending: rest,
        turn: { phase: "speaking", step, intent: "confirm", candidate },
        stream: [
          ...stream,
          { kind: "agent_confirm", questionId: question.id, values: [...candidate.values] },
        ],
      };
    }
    if (asked.includes(question.id)) {
      continue; // awaiting reconcile (or settled empty) — never re-asked
    }
    return {
      ...state,
      turn: { phase: "speaking", step, intent: "question" },
      stream: [...stream, { kind: "agent_question", questionId: question.id }],
    };
  }
  if (!unansweredLeft) {
    return { ...state, turn: { phase: "done" } };
  }
  if (inflight.length > 0) {
    return { ...state, turn: { phase: "settling" }, seq };
  }
  return { ...state, turn: { phase: "handoff" } };
}

/** One utterance enters the conversation: bubble, asked-mark, pipeline
 * bookkeeping, and the ask-ahead advance. Shared by voice and typed. */
function takeUtterance(
  pack: readonly IntakeQuestion[],
  state: DialogueStreamState,
  entry: StreamEntry & { kind: "patient" },
): DialogueStreamState {
  const currentId = currentQuestionId(pack, state.turn);
  const asked =
    currentId !== undefined && !state.asked.includes(currentId)
      ? [...state.asked, currentId]
      : state.asked;
  const next: Omit<DialogueStreamState, "turn"> = {
    pending: state.pending,
    answers: state.answers,
    asked,
    inflight: [...state.inflight, entry.workId],
    seq: state.seq,
    stream: [...state.stream, entry],
    // The voice condition has to survive every rebuild of the state that is
    // not a spread of the whole thing — this is the one.
    voiceMuted: state.voiceMuted,
    voiceFailures: state.voiceFailures,
    voiceRetryIn: state.voiceRetryIn,
  };
  if (state.turn.phase === "settling") {
    // No live question — the note keeps enriching while the end settles.
    return { ...next, turn: { phase: "settling" } };
  }
  return advance(pack, next);
}

type VoiceOutcome = "speech_done" | "speech_unavailable" | "speech_skipped";

/**
 * What one clip's outcome says about the agent's voice.
 *
 *   speech_done        it PLAYED        → the voice is back, on the record
 *   speech_unavailable it FAILED        → silent, one turn further from the
 *                                          next attempt
 *   speech_skipped     NOT ATTEMPTED    → silent, one turn closer
 *
 * The asymmetry between the last two is the whole of INT-294: a turn that was
 * deliberately not attempted carries no information about the lane, so it may
 * move the cooldown and may not move the caption.
 */
function nextVoice(
  state: DialogueStreamState,
  outcome: VoiceOutcome,
): Pick<DialogueStreamState, "voiceMuted" | "voiceFailures" | "voiceRetryIn"> {
  if (outcome === "speech_done") {
    return { voiceMuted: false, voiceFailures: 0, voiceRetryIn: 0 };
  }
  if (outcome === "speech_unavailable") {
    const voiceFailures = state.voiceFailures + 1;
    return { voiceMuted: true, voiceFailures, voiceRetryIn: voiceFailures - 1 };
  }
  return {
    voiceMuted: state.voiceMuted,
    voiceFailures: state.voiceFailures,
    voiceRetryIn: Math.max(0, state.voiceRetryIn - 1),
  };
}

export function dialogueStreamReducer(
  pack: readonly IntakeQuestion[],
  state: DialogueStreamState,
  action: DialogueStreamAction,
): DialogueStreamState {
  const { turn } = state;
  // Terminal turns absorb everything: late async results never resurrect
  // a finished, failed or handed-over dialogue.
  if (turn.phase === "done" || turn.phase === "failed" || turn.phase === "handoff") {
    return state;
  }
  switch (action.type) {
    case "speech_done":
    case "speech_unavailable":
    case "speech_skipped": {
      // All three leave the turn in the same place: the patient has the
      // question either way (it is rendered from the same catalog string the
      // clip was synthesized from), so the only thing that differs between
      // them is what they say about the VOICE.
      const voice = nextVoice(state, action.type);
      if (turn.phase !== "speaking") {
        // Pre-warm and confirm clips can land while the patient is talking;
        // record the voice without touching a turn that is not the agent's,
        // and hand back the SAME state when nothing about the voice moved so
        // a late duplicate costs no re-render.
        const moved =
          voice.voiceMuted !== state.voiceMuted ||
          voice.voiceFailures !== state.voiceFailures ||
          voice.voiceRetryIn !== state.voiceRetryIn;
        return moved ? { ...state, ...voice } : state;
      }
      return {
        ...state,
        ...voice,
        turn:
          turn.intent === "question"
            ? { phase: "listening", step: turn.step }
            : { phase: "confirming", step: turn.step, candidate: turn.candidate },
      };
    }
    case "barge_in":
      // DISTURBABLE: only agent speech can be interrupted; interrupting
      // the confirm clip means "let me say it myself" — candidate dropped.
      return turn.phase === "speaking"
        ? { ...state, turn: { phase: "listening", step: turn.step } }
        : state;
    case "speak":
      return turn.phase === "confirming"
        ? { ...state, turn: { phase: "listening", step: turn.step } }
        : state;
    case "utterance":
      if (turn.phase !== "listening") {
        return state;
      }
      return takeUtterance(pack, state, {
        kind: "patient",
        workId: action.workId,
        status: "transcribing",
        text: "",
      });
    case "typed": {
      const text = action.text.trim();
      if (text.length === 0) {
        return state;
      }
      return takeUtterance(pack, state, {
        kind: "patient",
        workId: action.workId,
        status: "text",
        text,
      });
    }
    case "transcript_ready": {
      const text = action.text.trim();
      if (text.length === 0) {
        // Nothing usable was heard: the bubble goes; the question stays
        // asked (skipped) and falls to the manual steps if never filled.
        return {
          ...state,
          stream: state.stream.filter(
            (entry) => entry.kind !== "patient" || entry.workId !== action.workId,
          ),
        };
      }
      return {
        ...state,
        stream: state.stream.map((entry) =>
          entry.kind === "patient" && entry.workId === action.workId
            ? { ...entry, status: "text", text }
            : entry,
        ),
      };
    }
    case "extract_settled": {
      const currentId = currentQuestionId(pack, turn);
      const known = new Set(pack.map((q) => q.id));
      const pending = { ...state.pending };
      const seq = { ...state.seq };
      for (const [questionId, candidate] of Object.entries(action.candidates)) {
        if (
          !known.has(questionId) ||
          questionId === currentId || // the live turn owns its own question
          state.answers[questionId] !== undefined ||
          (seq[questionId] ?? -1) > action.workId // a newer utterance already spoke
        ) {
          continue;
        }
        pending[questionId] = { values: [...candidate.values], quote: candidate.quote };
        seq[questionId] = action.workId;
      }
      const next = {
        ...state,
        pending,
        seq,
        inflight: state.inflight.filter((workId) => workId !== action.workId),
      };
      // Only the end wait re-advances: fresh suggestions get their confirm
      // turns retroactively; fully settled ends resolve to done/handoff.
      return turn.phase === "settling" ? advance(pack, next) : next;
    }
    case "confirm": {
      if (turn.phase !== "confirming") {
        return state;
      }
      const question = pack[turn.step];
      return advance(pack, {
        ...state,
        answers: {
          ...state.answers,
          [question.id]: { values: [...action.values], quote: turn.candidate.quote },
        },
      });
    }
    case "confirm_pending": {
      const candidate = state.pending[action.questionId];
      const question = pack.find((q) => q.id === action.questionId);
      if (
        candidate === undefined ||
        question === undefined ||
        action.questionId === currentQuestionId(pack, turn) ||
        state.answers[action.questionId] !== undefined ||
        // A question the answers do not ask for is not confirmable: the
        // note never gains an answer the flow never asked (INT-239).
        !askIfMet(question.askIf, committedAnswers(state))
      ) {
        return state;
      }
      const pending = { ...state.pending };
      delete pending[action.questionId];
      const next = {
        ...state,
        pending,
        answers: {
          ...state.answers,
          [action.questionId]: { values: [...candidate.values], quote: candidate.quote },
        },
      };
      // A live turn is never interrupted; the end wait re-evaluates (the
      // panel confirm may have been the last missing answer → done).
      return turn.phase === "settling" ? advance(pack, next) : next;
    }
    case "failure":
      return { ...state, turn: { phase: "failed" } };
  }
}

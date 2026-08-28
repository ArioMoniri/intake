/**
 * Ask-ahead conversation engine (INT-235; owner feedback pass). Dev-tier
 * mirror of the blueprint IntakeEngine's ask-ahead/reconcile-behind
 * pattern (02/INT-081): the next scripted question comes from the pack
 * and does NOT depend on the previous answer's extraction — so the turn
 * advances the instant an utterance is taken, and transcribe→extract
 * reconcile BEHIND, addressed by work id. The dev packs carry no
 * answer-gated questions (no askIf), so nothing mid-flow ever blocks;
 * the one honest wait is `settling` at the END while in-flight work
 * drains.
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
 * Invariant 1 posture: candidates are SUGGESTIONS — the only commit
 * paths are the confirm turn, the panel-row confirm and the manual steps
 * after handoff. Nothing auto-commits. Quotes are display-only
 * provenance; agent speech stays catalog-composed (speech.ts).
 *
 * The INT-233 single-question engine (turn.ts) remains the tested
 * reference for the blocking per-turn machine; this module supersedes it
 * on the app surface and reuses its candidate/turn vocabulary.
 */
import type { IntakeQuestion } from "../intake/questions";
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
}

export type DialogueStreamAction =
  | { type: "speech_done" }
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
  };
}

function currentQuestionId(pack: readonly IntakeQuestion[], turn: StreamTurn): string | undefined {
  return "step" in turn ? pack[turn.step]?.id : undefined;
}

/**
 * Ask-ahead advance: in pack order — answered questions are skipped, a
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
  let unansweredLeft = false;
  for (let step = 0; step < pack.length; step += 1) {
    const question = pack[step];
    if (answers[question.id] !== undefined) {
      continue;
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
  };
  if (state.turn.phase === "settling") {
    // No live question — the note keeps enriching while the end settles.
    return { ...next, turn: { phase: "settling" } };
  }
  return advance(pack, next);
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
      if (turn.phase !== "speaking") {
        return state;
      }
      return {
        ...state,
        turn:
          turn.intent === "question"
            ? { phase: "listening", step: turn.step }
            : { phase: "confirming", step: turn.step, candidate: turn.candidate },
      };
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
      if (
        candidate === undefined ||
        action.questionId === currentQuestionId(pack, turn) ||
        state.answers[action.questionId] !== undefined
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

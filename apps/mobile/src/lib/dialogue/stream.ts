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
 * AN ANSWER IS NEVER SILENTLY DISCARDED (INT-293). The surface used to have
 * exactly one route from the patient's words to a declared option id — the
 * extract daemon — and no answer at all when that route produced nothing: the
 * question was marked asked, the agent moved on, and the note stayed empty
 * while three questions were answered on screen (docs/evidence/INT-293.md).
 * Two rules replace that. First, the patient's words are read HERE against the
 * question's own declared labels (intake/answerMatch.ts) the moment they are
 * known — with the typed composer that is the same tick, so the confirm turn
 * opens at once and nothing waits on a service. Second, an utterance that
 * neither the local read nor the extractor could place does not leave its
 * question behind: `unclear` un-asks it, the next advance asks it again with
 * an honest line in front, and only a second miss hands it to the typed
 * steps. Ask-ahead is untouched — the next question still never waits on a
 * pipeline, and a reconcile still never moves a live turn.
 *
 * Invariant 1 posture: candidates are SUGGESTIONS — the only commit
 * paths are the confirm turn, the panel-row confirm and the manual steps
 * after handoff. Nothing auto-commits, the local read included: it produces
 * the same kind of candidate the extractor does and the patient confirms it
 * exactly the same way. Quotes are display-only provenance; agent speech
 * stays catalog-composed (speech.ts).
 *
 * The INT-233 single-question engine (turn.ts) remains the tested
 * reference for the blocking per-turn machine; this module supersedes it
 * on the app surface and reuses its candidate/turn vocabulary.
 */
import { matchOptionsInWords } from "../intake/answerMatch";
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
  /** INT-293: the agent says, before asking again, that the words it was
   * given mapped to nothing. Always immediately followed by the question's
   * own `agent_question` entry — the line explains, the question asks, so
   * one turn still carries one question (invariant 2). */
  | { kind: "agent_unclear"; questionId: string }
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
   * The question each in-flight utterance answered (INT-293). Without it an
   * `extract_settled` cannot tell WHICH question came back empty, and an
   * answer that mapped to nothing anywhere is indistinguishable from an
   * utterance that was enrichment for a question asked three turns ago.
   * Dropped as each work id settles, and never set for an utterance taken
   * during the end wait, where there is no live question.
   */
  utteranceOf: Record<number, string>;
  /**
   * How many times the patient's words for a question mapped to nothing —
   * neither to a declared label here nor to a slot at the extractor. One
   * miss returns the question to the conversation (it is asked again, under
   * an honest line); a second leaves it for the typed steps, because a third
   * ask is a loop and the patient has already said twice that this is not
   * how they want to answer it.
   */
  unclear: Record<string, number>;
  /**
   * The agent has lost its voice for the rest of this session (INT-261).
   * Latched by `speech_unavailable` and never cleared: re-probing the TTS
   * ladder on every subsequent turn would spend the turn budget twice per
   * question to arrive at the same answer, so once is enough. The surface
   * says so once; the conversation carries on in text.
   */
  voiceMuted: boolean;
}

export type DialogueStreamAction =
  | { type: "speech_done" }
  /**
   * The agent could not produce audio for this turn (INT-261). The turn
   * proceeds exactly as `speech_done` would have — the question is already
   * on screen — and the session goes silent from here.
   */
  | { type: "speech_unavailable" }
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
    utteranceOf: {},
    unclear: {},
  };
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
 * The patient's own sentence as the note records it beside one answer
 * (INT-286): the quote travels with the values, except on a `text` step where
 * the value IS the words and repeating them would say the same thing twice.
 *
 * It lives here because both commit paths on the surface use it and the
 * hand-over test drives it: the rule that decides what a confirmed dialogue
 * turn writes into the note must be one rule, not the same ternary written
 * twice in a screen (INT-293).
 */
export function answerWords(question: IntakeQuestion, quote: string): string | undefined {
  return question.kind === "text" ? undefined : quote;
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
      continue; // awaiting reconcile — the result decides whether it returns
    }
    // A question the patient already answered once, whose words mapped to
    // nothing, is asked again rather than dropped (INT-293) — and the line
    // saying so goes in front of it, so being asked twice is explained
    // rather than merely repeated.
    const reask = (state.unclear[question.id] ?? 0) > 0;
    return {
      ...state,
      turn: { phase: "speaking", step, intent: "question" },
      stream: reask
        ? [
            ...stream,
            { kind: "agent_unclear", questionId: question.id },
            { kind: "agent_question", questionId: question.id },
          ]
        : [...stream, { kind: "agent_question", questionId: question.id }],
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

/**
 * The candidate the patient's own words make for the question they were asked
 * (INT-293). `answerMatch` recognises a declared option's own label and
 * nothing else — no synonym, no similarity, no guess — so this is a floor
 * under the extractor, never a replacement for it: an answer given in the
 * pack's own words binds with no network at all, and everything else is still
 * the extract lane's to map. What comes back is a SUGGESTION carrying the
 * patient's verbatim words; only a confirm commits it.
 */
function localCandidate(
  pack: readonly IntakeQuestion[],
  questionId: string,
  text: string,
): DialogueCandidate | null {
  const question = pack.find((item) => item.id === questionId);
  if (question === undefined) {
    return null;
  }
  const values = matchOptionsInWords(question, text);
  return values === null ? null : { values, quote: text.trim() };
}

/** One utterance enters the conversation: bubble, asked-mark, pipeline
 * bookkeeping, the local read of its words, and the ask-ahead advance.
 * Shared by voice and typed; `text` is null when the words are not known
 * yet, which is every spoken utterance until its ASR lands. */
function takeUtterance(
  pack: readonly IntakeQuestion[],
  state: DialogueStreamState,
  entry: StreamEntry & { kind: "patient" },
  text: string | null,
): DialogueStreamState {
  const currentId = currentQuestionId(pack, state.turn);
  const asked =
    currentId !== undefined && !state.asked.includes(currentId)
      ? [...state.asked, currentId]
      : state.asked;
  let pending = state.pending;
  let seq = state.seq;
  if (text !== null && currentId !== undefined && state.answers[currentId] === undefined) {
    const candidate = localCandidate(pack, currentId, text);
    if (candidate !== null) {
      // The suggestion is on this question before the turn advances, so the
      // ask-ahead walk opens its confirm turn at once instead of leaving the
      // answer to a service that may never answer.
      pending = { ...pending, [currentId]: candidate };
      seq = { ...seq, [currentId]: entry.workId };
    }
  }
  const next: Omit<DialogueStreamState, "turn"> = {
    pending,
    answers: state.answers,
    asked,
    inflight: [...state.inflight, entry.workId],
    seq,
    stream: [...state.stream, entry],
    // The mute is a session latch, so it has to survive every rebuild of
    // the state that is not a spread of the whole thing — this is the one.
    voiceMuted: state.voiceMuted,
    utteranceOf:
      currentId !== undefined
        ? { ...state.utteranceOf, [entry.workId]: currentId }
        : state.utteranceOf,
    unclear: state.unclear,
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
    case "speech_unavailable": {
      // A clip that failed and a clip that finished leave the turn in the
      // same place: the patient has the question either way (it is rendered
      // from the same catalog string the clip was synthesized from), so the
      // only difference the failure makes is that the session is now silent.
      const voiceMuted = state.voiceMuted || action.type === "speech_unavailable";
      if (turn.phase !== "speaking") {
        // Pre-warm and confirm clips can fail while the patient is talking;
        // latch the mute without touching a turn that is not the agent's.
        return voiceMuted === state.voiceMuted ? state : { ...state, voiceMuted };
      }
      return {
        ...state,
        voiceMuted,
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
      return takeUtterance(
        pack,
        state,
        { kind: "patient", workId: action.workId, status: "transcribing", text: "" },
        null, // spoken: the words arrive with `transcript_ready`
      );
    case "typed": {
      const text = action.text.trim();
      if (text.length === 0) {
        return state;
      }
      return takeUtterance(
        pack,
        state,
        { kind: "patient", workId: action.workId, status: "text", text },
        text,
      );
    }
    case "transcript_ready": {
      const text = action.text.trim();
      const answeredId = state.utteranceOf[action.workId];
      if (text.length === 0) {
        // Nothing usable was heard: the bubble goes; the question stays
        // asked (skipped) and falls to the manual steps if never filled.
        // Silence is not a misunderstanding — there were no words to fail to
        // map — so this utterance is dropped from the unclear bookkeeping.
        const utteranceOf = { ...state.utteranceOf };
        delete utteranceOf[action.workId];
        return {
          ...state,
          utteranceOf,
          stream: state.stream.filter(
            (entry) => entry.kind !== "patient" || entry.workId !== action.workId,
          ),
        };
      }
      const stream: StreamEntry[] = state.stream.map((entry) =>
        entry.kind === "patient" && entry.workId === action.workId
          ? { ...entry, status: "text" as const, text }
          : entry,
      );
      // The spoken half of the local read (INT-293): a voice utterance's
      // words exist only now, and they are read against the question they
      // answered on exactly the terms `takeUtterance` reads a typed one. The
      // suggestion lands; the live turn is never moved by a reconcile, so it
      // opens as a confirm turn on the next advance like any other.
      const candidate =
        answeredId !== undefined &&
        answeredId !== currentQuestionId(pack, turn) &&
        state.answers[answeredId] === undefined &&
        (state.seq[answeredId] ?? -1) < action.workId
          ? localCandidate(pack, answeredId, text)
          : null;
      if (candidate === null || answeredId === undefined) {
        return { ...state, stream };
      }
      return {
        ...state,
        stream,
        pending: { ...state.pending, [answeredId]: candidate },
        seq: { ...state.seq, [answeredId]: action.workId },
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
          // A NEWER utterance already spoke — `>` and not `>=`, so the
          // extractor is never locked out of the utterance it was given.
          // The local read (INT-293) records its own candidate under this
          // same work id, and it is a floor, not an authority: it recognises
          // a declared label's own words and refuses everything else, so on
          // the sentences it refuses — every negated one — the extractor's
          // reading of THIS utterance is the only reading there is. Letting
          // the local candidate outrank it at equal work ids would trade a
          // dropped answer for a wrong one.
          (seq[questionId] ?? -1) > action.workId
        ) {
          continue;
        }
        pending[questionId] = { values: [...candidate.values], quote: candidate.quote };
        seq[questionId] = action.workId;
      }
      // This utterance's whole fate is now known: the words were read here
      // and at the extractor, and if neither could place them the question is
      // NOT left behind as asked-and-answered. It goes back into the
      // conversation to be asked once more (INT-293) — the defect this
      // replaces is an answered question silently becoming an empty note
      // section. A second miss keeps it asked: the typed steps take it at the
      // hand-over rather than the agent asking a third time.
      const answeredId = state.utteranceOf[action.workId];
      const utteranceOf = { ...state.utteranceOf };
      delete utteranceOf[action.workId];
      let unclear = state.unclear;
      let asked = state.asked;
      if (
        answeredId !== undefined &&
        answeredId !== currentId &&
        state.answers[answeredId] === undefined &&
        pending[answeredId] === undefined
      ) {
        const misses = (state.unclear[answeredId] ?? 0) + 1;
        unclear = { ...state.unclear, [answeredId]: misses };
        if (misses === 1) {
          asked = state.asked.filter((questionId) => questionId !== answeredId);
        }
      }
      const next = {
        ...state,
        pending,
        seq,
        asked,
        unclear,
        utteranceOf,
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

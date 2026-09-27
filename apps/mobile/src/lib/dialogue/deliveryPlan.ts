/**
 * Planning conversational delivery over a whole sitting (INT-414).
 *
 * The composer (delivery.ts) decides one turn. This module supplies what one
 * turn cannot know about itself — which kind of question it is, which topic it
 * opens, what the previous turn said — by folding the composer over the
 * sitting in order. The same fold drives both lanes:
 *
 *   - the SPOKEN dialogue plans every `agent_question` entry of the stream, so
 *     the clip the patient hears and the bubble they read are one plan;
 *   - the TYPED steps plan the current step from the sitting's first step, so
 *     a re-render shows the same line and a revisit replays it.
 *
 * Classification reads what the pack DECLARES and never the wording of a
 * question: a pain question is one gated on the patient having named pain
 * (the INT-236 gate shape), a sensitive one is a 02 §33 deferral unit or a
 * files/13 §13 `text_first` step, and an instrument step carries its
 * instrument reference. Nothing here grades an answer — the only answer this
 * module reads is whether the patient said they do not know, and that selects
 * an acknowledgement, never a value.
 */
import type { InstrumentItem } from "../intake/instruments";
import { WRAPUP_QUESTION_ID, type AnsweredValues, type IntakeQuestion } from "../intake/questions";
import {
  composeDelivery,
  lastDeliveryKey,
  questionDeliveryContext,
  type DeliveryCue,
  type DeliveryLane,
  type DeliveryTopic,
  type QuestionContext,
  type Utterance,
  type VerbatimItem,
} from "./delivery";
import type { DeliveryContext } from "./deliveryContext";
import { questionSpeechTr } from "./speech";
import type { StreamEntry } from "./stream";

/**
 * The declared option ids that answer "I don't know", "I don't remember" or
 * "I'd rather not say". They select an acknowledgement and nothing else.
 */
export const HESITANT_OPTION_IDS: ReadonlySet<string> = new Set([
  "not_sure",
  "unknown",
  "dont_remember",
  "not_stated",
]);

/** The question's kind of moment, from its declarations only. */
export function questionContextOf(question: IntakeQuestion): QuestionContext {
  if (question.instrument !== undefined) {
    return "instrument";
  }
  if (question.deferrableAs !== undefined || question.delivery === "text_first") {
    return "sensitive";
  }
  if (question.askIf?.includesAny.includes("pain") === true) {
    return "pain";
  }
  return "routine";
}

/** How the question itself is spoken (INT-415 profile) — never its words. */
export function questionDeliveryContextOf(question: IntakeQuestion): DeliveryContext {
  return questionDeliveryContext(questionContextOf(question));
}

/** The note topic a question opens — its 04 §5 note section, or the HPI. */
export function deliveryTopicOf(question: IntakeQuestion): DeliveryTopic {
  if (question.id === WRAPUP_QUESTION_ID) {
    return "wrapup";
  }
  if (question.deferrableAs === "family_history") {
    return "family";
  }
  if (question.kind === "measure") {
    return "measurements";
  }
  switch (question.noteSection) {
    case "allergies":
      return "allergies";
    case "medications":
      return "medications";
    case "pmh":
      return "pmh";
    case "family_social":
      return "social";
    case undefined:
      return "hpi";
  }
}

/** A pack question as the voice lane asks it — its scripted composition. */
export function questionItem(question: IntakeQuestion): VerbatimItem {
  return { source: "question", key: question.titleKey, text: questionSpeechTr(question) };
}

/** A validated instrument item: its own verbatim `textTr`, never the app catalogue. */
export function instrumentItem(instrumentId: string, item: InstrumentItem): VerbatimItem {
  return { source: "instrument", key: `${instrumentId}:${item.id}`, text: item.textTr };
}

/** A pre-positioned RED script, exactly as the device holds it. */
export function redItem(scriptId: string, text: string): VerbatimItem {
  return { source: "red", key: scriptId, text };
}

/** One turn of a sitting, before its delivery is decided. */
export interface PlannedStep {
  readonly item: VerbatimItem;
  readonly context: QuestionContext;
  readonly topic: DeliveryTopic;
  readonly cue: DeliveryCue;
}

export function stepFor(question: IntakeQuestion, cue: DeliveryCue): PlannedStep {
  return {
    item: questionItem(question),
    context: questionContextOf(question),
    topic: deliveryTopicOf(question),
    cue,
  };
}

export interface PlanOptions {
  readonly sessionSeed: string;
  readonly lane: DeliveryLane;
  /** `opening` for a fresh intake; `first` when this sitting resumes one. */
  readonly start: "opening" | "first";
}

/** The composer folded over a sitting: each turn's utterances, in order. */
export function planDelivery(
  steps: readonly PlannedStep[],
  options: PlanOptions,
): readonly (readonly Utterance[])[] {
  const turns: (readonly Utterance[])[] = [];
  let previousKey: string | null = null;
  let previousTopic: DeliveryTopic | null = null;
  let previousContext: QuestionContext | null = null;
  steps.forEach((step, turnIndex) => {
    const phase =
      turnIndex === 0
        ? options.start
        : step.context === "sensitive" && previousContext !== "sensitive"
          ? "sensitive"
          : "mid";
    const out = composeDelivery({
      phase,
      questionContext: step.context,
      cue: step.cue,
      turnIndex,
      sessionSeed: options.sessionSeed,
      previousKey,
      lane: options.lane,
      topic: step.topic,
      previousTopic,
      previousContext,
      item: step.item,
    });
    turns.push(out);
    previousKey = lastDeliveryKey(out);
    previousTopic = step.topic;
    previousContext = step.context;
  });
  return turns;
}

/**
 * The spoken dialogue's plan: every `agent_question` entry of the stream,
 * keyed by its stream index. A question preceded by the reducer's
 * `agent_unclear` entry is a re-ask and carries the repair line; any other
 * entry carries the cue recorded for it when it first appeared (`cues`), or
 * none. Confirm turns are read-backs and are not decorated.
 */
export function planDialogueDelivery(
  pack: readonly IntakeQuestion[],
  stream: readonly StreamEntry[],
  cues: ReadonlyMap<number, DeliveryCue>,
  sessionSeed: string,
): ReadonlyMap<number, readonly Utterance[]> {
  const indices: number[] = [];
  const steps: PlannedStep[] = [];
  stream.forEach((entry, index) => {
    if (entry.kind !== "agent_question") {
      return;
    }
    const question = pack.find((candidate) => candidate.id === entry.questionId);
    if (question === undefined) {
      return;
    }
    const reask = index > 0 && stream[index - 1].kind === "agent_unclear";
    steps.push(stepFor(question, reask ? "repeat_request" : (cues.get(index) ?? "none")));
    indices.push(index);
  });
  const plan = planDelivery(steps, { sessionSeed, lane: "voice", start: "opening" });
  return new Map(indices.map((streamIndex, turn) => [streamIndex, plan[turn]]));
}

/** "I don't know" and its neighbours on the answer to `questionId`, as a cue. */
export function cueForAnswer(answers: readonly AnsweredValues[], questionId: string): DeliveryCue {
  const answer = answers.find((candidate) => candidate.questionId === questionId);
  return answer?.values.some((value) => HESITANT_OPTION_IDS.has(value)) === true
    ? "hesitant"
    : "none";
}

export interface TypedStepInput {
  /** The applicable questions, in flow order. */
  readonly applicable: readonly IntakeQuestion[];
  readonly answers: readonly AnsweredValues[];
  readonly currentId: string;
  /** The step this sitting started on — held by the screen, not re-derived. */
  readonly startId: string;
  /** A fresh intake opens with the welcome; anything else resumes. */
  readonly fresh: boolean;
  readonly sessionSeed: string;
}

/**
 * The delivery lines above the typed step on screen — never the question,
 * which the step renders from the catalogue itself, in the patient's locale.
 */
export function typedStepDelivery(input: TypedStepInput): readonly Utterance[] {
  const current = input.applicable.findIndex((q) => q.id === input.currentId);
  if (current < 0) {
    return [];
  }
  const found = input.applicable.findIndex((q) => q.id === input.startId);
  const start = found < 0 || found > current ? current : found;
  const sitting = input.applicable.slice(start, current + 1);
  const plan = planDelivery(
    sitting.map((question, i) =>
      stepFor(question, i === 0 ? "none" : cueForAnswer(input.answers, sitting[i - 1].id)),
    ),
    { sessionSeed: input.sessionSeed, lane: "typed", start: input.fresh ? "opening" : "first" },
  );
  return (plan.at(-1) ?? []).filter((utterance) => utterance.kind !== "question");
}

/** The closing line for a finished intake, stable for one visit's answers. */
export function closingDelivery(sessionSeed: string, turnIndex: number): readonly Utterance[] {
  return composeDelivery({
    phase: "closing",
    questionContext: "routine",
    cue: "none",
    turnIndex,
    sessionSeed,
    previousKey: null,
    lane: "typed",
    topic: "wrapup",
    previousTopic: null,
    previousContext: null,
    item: null,
  });
}

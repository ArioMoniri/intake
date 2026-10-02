/**
 * Conversational delivery (INT-414): the pure composer that decides what is
 * said AROUND one question — a welcome, a lead-in, a topic transition, an
 * acknowledgement, a closing — and hands the question itself through
 * untouched.
 *
 * The owner asked for questions that open warm, stay professional and never
 * sound robotic, and that follow the patient's state and the question's
 * context. Every word of that lives in the delivery layer. The item never
 * does: CLAUDE.md's clinical rule is "conversational delivery may paraphrase
 * the lead-in, never the item", and invariant 10 speaks scripted questions,
 * instrument items and red-flag scripts verbatim. So the composer's output
 * carries exactly one `question` utterance whose text IS the text it was
 * given — the same string, not an equal copy — and delivery.test.ts proves
 * that over every shipped question, every instrument row and every RED
 * string in the life-threat pack.
 *
 * Four rules sit on top of that, each with the invariant it answers to:
 *
 *  - **RED gets nothing** (invariant 21). A RED script, or anything the
 *    caller marks RED-adjacent, comes back alone: no welcome, no softening,
 *    no thanks. RED's bare imperative plural is correct because ambiguity is
 *    the harm, and a lead-in in front of it is ambiguity.
 *  - **One question per turn** (invariant 2). No delivery line asks anything;
 *    the tests hold every line free of `?` and of the mı/mi/mu/mü clitic, and
 *    tests/release/test_delivery_copy.py runs each through PolicyGuard.
 *  - **Cues are read, never awaited** (invariant 11). The composer is
 *    synchronous and takes a cue VALUE; `readCue` turns a missing, throwing,
 *    stalled or malformed source into `"none"` on the spot. A stalled lane
 *    therefore changes neither the words nor when they are available.
 *  - **Deterministic variation.** The variant is a hash of the session seed
 *    and the turn, never `Math.random`: the same visit replays the same
 *    words, the typed screen re-renders the same line, and the voice lane and
 *    the transcript can never disagree about what was said.
 *
 * And two about rhythm, because a line on every turn is exactly the robotic
 * register the owner asked to lose: a turn carries at most ONE delivery line
 * (the opening carries two), the same line is never used on two consecutive
 * turns, and a cadence line only follows a turn that had none.
 */
import type { DeliveryContext } from "./deliveryContext";
import {
  DELIVERY_DECK,
  deliveryTextTr,
  SLOT_CONTEXT,
  type DeliveryKey,
  type DeliverySlot,
} from "./deliveryDeck";

/** Where the session is. `first` is the first question of a sitting that did
 * not open the intake — a resume, or the typed steps after a voice hand-over. */
export const SESSION_PHASES = ["opening", "first", "mid", "sensitive", "closing"] as const;
export type SessionPhase = (typeof SESSION_PHASES)[number];

/** What kind of question this is. `red` is a RED script or anything adjacent to one. */
export const QUESTION_CONTEXTS = ["routine", "sensitive", "instrument", "pain", "red"] as const;
export type QuestionContext = (typeof QUESTION_CONTEXTS)[number];

/**
 * What the patient's last turn looked like, from signals already on the
 * device — never from audio (invariants 3 and 11; the acoustic lane is gated).
 *
 *   repeat_request  the question is being asked again (INT-293's unclear re-ask)
 *   hesitant        the last answer was "don't know / don't remember / prefer not to say"
 *   revised         the patient corrected a suggestion
 *   long_silence    the patient's last turn carried no words
 *   barge_in        the patient cut the agent off — they want it shorter
 */
export const DELIVERY_CUES = [
  "none",
  "repeat_request",
  "hesitant",
  "revised",
  "long_silence",
  "barge_in",
] as const;
export type DeliveryCue = (typeof DELIVERY_CUES)[number];

/** The note topic a question belongs to (04 §1 sections, 04 §5 note sections). */
export const DELIVERY_TOPICS = [
  "hpi",
  "allergies",
  "medications",
  "pmh",
  "family",
  "social",
  "measurements",
  "wrapup",
] as const;
export type DeliveryTopic = (typeof DELIVERY_TOPICS)[number];

export type DeliveryLane = "voice" | "typed";

export type UtteranceKind = "lead_in" | "transition" | "acknowledgement" | "question";

/**
 * The scripted item a turn asks. `text` is passed through byte for byte;
 * `key` names where it came from (a question's title key, an instrument item,
 * a RED script id). There is no field here for anything the patient said.
 */
export interface VerbatimItem {
  readonly source: "question" | "instrument" | "red";
  readonly key: string;
  readonly text: string;
}

export interface Utterance {
  readonly kind: UtteranceKind;
  readonly key: string;
  readonly text: string;
  readonly deliveryContext: DeliveryContext;
}

export interface DeliveryInput {
  readonly phase: SessionPhase;
  readonly questionContext: QuestionContext;
  readonly cue: DeliveryCue;
  /** Position of this turn in the sitting; half of the variation seed. */
  readonly turnIndex: number;
  /** A per-visit id (never PHI); the other half of the variation seed. */
  readonly sessionSeed: string;
  /** The previous turn's delivery line, or null when it had none. */
  readonly previousKey: string | null;
  readonly lane: DeliveryLane;
  readonly topic: DeliveryTopic;
  readonly previousTopic: DeliveryTopic | null;
  readonly previousContext: QuestionContext | null;
  /** The question; null on the closing turn, which asks nothing. */
  readonly item: VerbatimItem | null;
}

/** A cue source: whatever an observer or the session exposes, read synchronously. */
export type CueSource = () => unknown;

const CUE_SET: ReadonlySet<string> = new Set(DELIVERY_CUES);

/**
 * The cue a source reports RIGHT NOW, or `"none"`.
 *
 * Never awaits: a promise (a lane still thinking), a throw (a lane that is
 * down), `undefined` (nothing reported) and anything outside the closed cue
 * vocabulary all read as no cue, immediately. That closed vocabulary is also
 * why no patient word can ride in on a cue.
 */
export function readCue(source: CueSource | null | undefined): DeliveryCue {
  if (typeof source !== "function") {
    return "none";
  }
  let value: unknown;
  try {
    value = source();
  } catch {
    return "none";
  }
  return typeof value === "string" && CUE_SET.has(value) ? (value as DeliveryCue) : "none";
}

/** FNV-1a, 32-bit: small, stable across engines, and not a random source. */
function fnv1a(text: string): number {
  let hash = 0x811c9dc5;
  for (let i = 0; i < text.length; i += 1) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash >>> 0;
}

function roll(input: DeliveryInput, salt: string): number {
  return fnv1a(`${input.sessionSeed}\u0000${input.turnIndex}\u0000${salt}`);
}

/** One key from a slot, by hash — and never the key the previous turn used. */
function pick(input: DeliveryInput, slot: DeliverySlot): DeliveryKey {
  const pool: readonly DeliveryKey[] = DELIVERY_DECK[slot];
  const index = roll(input, slot) % pool.length;
  const chosen = pool[index];
  return chosen === input.previousKey ? pool[(index + 1) % pool.length] : chosen;
}

/** How the question itself is said: the context never changes its words. */
export function questionDeliveryContext(context: QuestionContext): DeliveryContext {
  switch (context) {
    case "sensitive":
      return "sensitive";
    case "instrument":
      return "instrument";
    case "red":
      return "red";
    case "routine":
    case "pain":
      return "routine";
  }
}

/** One line from `slot`, delivered in the slot's own context unless the
 * caller says otherwise (deliveryDeck.ts SLOT_CONTEXT). */
function line(
  input: DeliveryInput,
  slot: DeliverySlot,
  kind: Exclude<UtteranceKind, "question">,
  deliveryContext: DeliveryContext = SLOT_CONTEXT[slot],
): Utterance {
  const key = pick(input, slot);
  return { kind, key, text: deliveryTextTr(key), deliveryContext };
}

const TOPIC_SLOT: Record<DeliveryTopic, DeliverySlot | null> = {
  hpi: null, // the first question opens the HPI; there is nothing to announce
  allergies: "topicAllergies",
  medications: "topicMedications",
  pmh: "topicPmh",
  family: "topicFamily",
  social: "topicSocial",
  measurements: "topicMeasurements",
  wrapup: "topicWrapup",
};

/** The one delivery line a mid-session turn may carry, or null. */
function midLine(input: DeliveryInput): Utterance | null {
  const { cue, questionContext: context, previousContext } = input;
  const own = questionDeliveryContext(context);
  if (context === "instrument") {
    // Standardised administration: the instrument is introduced once, and
    // nothing — no thanks, no reassurance, no repair line for a re-asked item
    // — is said between its items. This comes before every other rule for
    // that reason: an instrument item is asked the same way every time.
    return previousContext === "instrument" ? null : line(input, "instrument", "lead_in");
  }
  // The turn after a RED-adjacent one is never thanked and never nudged: a
  // warm "continue" straight after a red-flag script is the tone-deaf line
  // the clinical review ruled out. It still announces a new topic and still
  // explains a repeat — those say where the sitting is, not how it went.
  const afterRed = previousContext === "red";
  if (cue === "repeat_request") {
    // Being asked twice is explained, not merely repeated (INT-293).
    return line(input, "repair", "lead_in", own);
  }
  if (input.phase === "sensitive") {
    return input.topic === "family"
      ? line(input, "topicFamily", "transition")
      : line(input, "sensitive", "transition");
  }
  const slot = TOPIC_SLOT[input.topic];
  if (slot !== null && input.previousTopic !== null && input.topic !== input.previousTopic) {
    return line(input, slot, "transition");
  }
  if (cue === "barge_in") {
    return null; // they cut in: say less, not more
  }
  if (context === "pain" && previousContext !== "pain") {
    return line(input, "pain", "lead_in");
  }
  if (!afterRed && (cue === "hesitant" || cue === "revised")) {
    return line(input, cue, "acknowledgement");
  }
  if (cue === "long_silence") {
    return line(input, "silence", "lead_in", own);
  }
  // Cadence: only after a quiet turn, and only on about half of those.
  if (afterRed || input.previousKey !== null || roll(input, "cadence") % 2 !== 0) {
    return null;
  }
  if (context === "sensitive") {
    return line(input, "sensitiveLead", "lead_in");
  }
  return roll(input, "cadence-slot") % 2 === 0
    ? line(input, "routine", "lead_in")
    : line(input, "thanks", "acknowledgement");
}

/**
 * The utterances for one turn, in the order they are said. The question, when
 * there is one, is last and is `input.item.text` itself.
 */
export function composeDelivery(input: DeliveryInput): readonly Utterance[] {
  const { item } = input;
  if (item?.source === "red" || input.questionContext === "red") {
    // Nothing before, after or around it — and nothing at all without it.
    return item === null
      ? []
      : [{ kind: "question", key: item.key, text: item.text, deliveryContext: "red" }];
  }
  if (input.phase === "closing") {
    return [line(input, "closing", "transition")];
  }
  const delivery: Utterance[] = [];
  if (input.phase === "opening") {
    delivery.push(line(input, "welcome", "lead_in"));
    delivery.push(
      line(input, input.lane === "voice" ? "orientVoice" : "orientTyped", "transition"),
    );
  } else if (input.phase === "first") {
    delivery.push(line(input, "resume", "lead_in"));
  } else {
    const mid = midLine(input);
    if (mid !== null) {
      delivery.push(mid);
    }
  }
  if (item === null) {
    return delivery;
  }
  return [
    ...delivery,
    {
      kind: "question",
      key: item.key,
      text: item.text,
      deliveryContext: questionDeliveryContext(input.questionContext),
    },
  ];
}

/** The key a turn hands to the next one as `previousKey`: its last delivery line. */
export function lastDeliveryKey(utterances: readonly Utterance[]): string | null {
  for (let i = utterances.length - 1; i >= 0; i -= 1) {
    if (utterances[i].kind !== "question") {
      return utterances[i].key;
    }
  }
  return null;
}

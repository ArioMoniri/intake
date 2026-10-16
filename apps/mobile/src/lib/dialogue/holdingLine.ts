/**
 * The holding line (INT-497): a short acknowledgement said the moment the
 * patient's turn ends, when the next question's clip is not ready to play.
 *
 * Ask-ahead (INT-235) makes the next question known the instant the turn is
 * taken, and the session pre-warms every clip — so on a warm turn the question
 * itself is the immediate answer and this module says nothing. It is for the
 * cold turn: a question whose clip is still being made, which used to mean
 * the patient finished speaking into dead silence and a "Soru hazırlanıyor…"
 * caption for as long as synthesis took. The owner's order is "no dead
 * silence"; the deck already has the words for it.
 *
 * It is the delivery deck's own acknowledgement, never new copy, and it keeps
 * every rule the composer keeps (delivery.ts):
 *   - nothing around RED, nothing inside an instrument's standardised
 *     administration, nothing in front of a sensitive section's own framing;
 *   - after a barge-in, less rather than more; before a repeat, the repair
 *     line is the turn's line and nothing is added;
 *   - one line per turn: a turn whose own line is ready says that instead;
 *   - never the line the previous turn ended on, never the last holding line;
 *   - only a line whose clip is ALREADY made — a filler that has to be
 *     synthesised first is a second wait, not an answer to the first.
 *
 * Deterministic like the composer: a hash of the visit seed and the turn,
 * never `Math.random`, so the transcript can show exactly what was said.
 */
import { fnv1a, type DeliveryCue, type QuestionContext, type Utterance } from "./delivery";
import type { DeliveryContext } from "./deliveryContext";
import { DELIVERY_DECK, deliveryTextTr, type DeliveryKey, type DeliverySlot } from "./deliveryDeck";

/**
 * How long a turn waits for its question's clip before it says a holding line.
 * A pre-warmed question is a cache hit — one file-existence check — and lands
 * well inside this; a clip still being synthesised takes a lane round trip,
 * hundreds of milliseconds at best (tts.ts). So the window tells the two apart
 * without making a warm turn wait for anything, and it is small against the
 * 800 ms first-audio target it protects.
 */
export const HOLDING_AFTER_MS = 120;

/** Question contexts a holding line may stand in front of. */
const HOLDS_BEFORE: ReadonlySet<QuestionContext> = new Set(["routine", "pain"]);

/** Cues after which nothing is added: they wanted less, or a repair is coming. */
const SAYS_LESS: ReadonlySet<DeliveryCue> = new Set(["barge_in", "repeat_request"]);

export interface HoldingInput {
  /** The turn's planned utterances (deliveryPlan.ts), question last. */
  readonly plan: readonly Utterance[];
  readonly questionContext: QuestionContext;
  readonly cue: DeliveryCue;
  /** The previous turn asked a RED-adjacent question. */
  readonly afterRed: boolean;
  /** The last delivery line the previous turn said, or null. */
  readonly previousLineKey: string | null;
  /** The last holding line said this session, or null. */
  readonly lastHoldingKey: string | null;
  readonly sessionSeed: string;
  readonly turnIndex: number;
  /** Whether this session already holds the line's clip, in that context. */
  readonly isReady: (key: DeliveryKey, context: DeliveryContext) => boolean;
}

function slotFor(cue: DeliveryCue): DeliverySlot {
  return cue === "hesitant" || cue === "revised" ? cue : "thanks";
}

/** The acknowledgement to say while the question is made, or null. */
export function holdingLine(input: HoldingInput): Utterance | null {
  const { plan, cue } = input;
  if (!HOLDS_BEFORE.has(input.questionContext) || input.afterRed || SAYS_LESS.has(cue)) {
    return null;
  }
  const lines = plan.filter((utterance) => utterance.kind !== "question");
  if (lines.some((line) => line.deliveryContext === "welcome")) {
    return null; // the opening waits for its own welcome — that IS its content
  }
  if (lines.some((line) => input.isReady(line.key as DeliveryKey, line.deliveryContext))) {
    return null; // the turn's own line is ready and is said instead
  }
  const pool: readonly DeliveryKey[] = DELIVERY_DECK[slotFor(cue)];
  const offset = fnv1a(`${input.sessionSeed}\u0000${input.turnIndex}\u0000holding`) % pool.length;
  for (let step = 0; step < pool.length; step += 1) {
    const key = pool[(offset + step) % pool.length];
    if (
      key === input.previousLineKey ||
      key === input.lastHoldingKey ||
      !input.isReady(key, "acknowledgement")
    ) {
      continue;
    }
    return {
      kind: "acknowledgement",
      key,
      text: deliveryTextTr(key),
      deliveryContext: "acknowledgement",
    };
  }
  return null;
}

/**
 * What the turn actually said, for the transcript: the holding line in place
 * of the turn's own lines (which were not said), the question last. The plan
 * itself when nothing was held.
 */
export function withHolding(
  plan: readonly Utterance[],
  holding: Utterance | null,
): readonly Utterance[] {
  if (holding === null) {
    return plan;
  }
  return [holding, ...plan.filter((utterance) => utterance.kind === "question")];
}

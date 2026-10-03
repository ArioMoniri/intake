/**
 * The delivery copy deck (INT-414): every slot the composer can fill, and the
 * `tr` resource keys it may fill that slot with.
 *
 * Keys, never strings. The words live in the catalogue (invariant 5: `tr` is
 * the source of truth, `en` its mirror), so this file decides WHICH line may
 * be said WHERE and nothing about what it says. Every slot carries at least
 * two variants so that consecutive turns never have to repeat a line; the one
 * exception to "new copy" is the repair slot, which reuses INT-293's
 * `dialogue.notUnderstood` as its first variant rather than inventing a
 * second apology for the same event.
 *
 * What is deliberately NOT a slot:
 *   - anything inside a question, an instrument item or a RED script — those
 *     are spoken verbatim (invariant 10) and never pass through this deck;
 *   - a line saying where the answers go. `docs/legal/strings.yaml` does not
 *     exist, and consent/legal wording renders only from there (invariant 18);
 *   - a "say 'tekrar' to hear it again" line. The dev dialogue has no spoken
 *     repeat command — a "tekrar" utterance is read as an answer that maps to
 *     nothing and is re-asked later — so the line would promise a behaviour
 *     the product does not have (docs/evidence/INT-414.md, owner ask).
 */
import { t, type MessageKey } from "../i18n";
import type { DeliveryContext } from "./deliveryContext";

export const DELIVERY_DECK = {
  /** Opening, first sentence pair: a warm welcome and what will happen. */
  welcome: [
    "dialogue.delivery.welcome.a",
    "dialogue.delivery.welcome.b",
    "dialogue.delivery.welcome.c",
  ],
  /** Opening, how this lane works — the spoken lane's true affordances. */
  orientVoice: ["dialogue.delivery.orientVoice.a", "dialogue.delivery.orientVoice.b"],
  /** Opening, how this lane works — the typed lane's. */
  orientTyped: ["dialogue.delivery.orientTyped.a", "dialogue.delivery.orientTyped.b"],
  /** The first question of a sitting that did not open the intake. */
  resume: ["dialogue.delivery.resume.a", "dialogue.delivery.resume.b"],
  /** Cadence lead-ins for a routine question. */
  routine: [
    "dialogue.delivery.lead.a",
    "dialogue.delivery.lead.b",
    "dialogue.delivery.lead.c",
    "dialogue.delivery.lead.d",
  ],
  /** Cadence acknowledgement of the previous answer. */
  thanks: [
    "dialogue.delivery.thanks.a",
    "dialogue.delivery.thanks.b",
    "dialogue.delivery.thanks.c",
  ],
  /** The previous answer was "don't know", "don't remember" or "prefer not to say". */
  hesitant: ["dialogue.delivery.hesitant.a", "dialogue.delivery.hesitant.b"],
  /** The patient corrected a suggestion. */
  revised: ["dialogue.delivery.revised.a", "dialogue.delivery.revised.b"],
  /** The patient's last turn carried no words. */
  silence: ["dialogue.delivery.silence.a", "dialogue.delivery.silence.b"],
  /** The question is asked again because the last answer mapped to nothing. */
  repair: ["dialogue.notUnderstood", "dialogue.delivery.repair.b"],
  /** Entering questions about a pain the patient has named. */
  pain: ["dialogue.delivery.pain.a", "dialogue.delivery.pain.b"],
  /** Entering a validated instrument: why its wording is fixed. */
  instrument: ["dialogue.delivery.instrument.a", "dialogue.delivery.instrument.b"],
  /** Entering a sensitive section. */
  sensitive: ["dialogue.delivery.sensitive.a", "dialogue.delivery.sensitive.b"],
  /** Cadence lead-ins inside a sensitive section. */
  sensitiveLead: ["dialogue.delivery.sensitiveLead.a", "dialogue.delivery.sensitiveLead.b"],
  topicAllergies: ["dialogue.delivery.topic.allergies.a", "dialogue.delivery.topic.allergies.b"],
  topicMedications: [
    "dialogue.delivery.topic.medications.a",
    "dialogue.delivery.topic.medications.b",
  ],
  topicPmh: ["dialogue.delivery.topic.pmh.a", "dialogue.delivery.topic.pmh.b"],
  /** Family history is a sensitive section AND a topic (02 §33). */
  topicFamily: ["dialogue.delivery.topic.family.a", "dialogue.delivery.topic.family.b"],
  topicSocial: ["dialogue.delivery.topic.social.a", "dialogue.delivery.topic.social.b"],
  topicMeasurements: [
    "dialogue.delivery.topic.measurements.a",
    "dialogue.delivery.topic.measurements.b",
  ],
  topicWrapup: ["dialogue.delivery.topic.wrapup.a", "dialogue.delivery.topic.wrapup.b"],
  /** After the last answer. */
  closing: ["dialogue.delivery.closing.a", "dialogue.delivery.closing.b"],
} as const satisfies Record<string, readonly MessageKey[]>;

export type DeliverySlot = keyof typeof DELIVERY_DECK;

/** A resource key the composer may emit. Narrower than `MessageKey` by type. */
export type DeliveryKey = (typeof DELIVERY_DECK)[DeliverySlot][number];

/** The empathic acknowledgements: files/03 §4.2 bounds these at five words. */
export const ACKNOWLEDGEMENT_SLOTS = [
  "thanks",
  "hesitant",
  "revised",
] as const satisfies readonly DeliverySlot[];

/**
 * Slots the voice lane never speaks. The typed orientation describes the typed
 * lane; the closing renders on the review screen, after the dialogue's audio
 * has been torn down by design (INT-233 audio hygiene); and measurements are
 * `text_only` steps the spoken pack drops (invariant 22), so their topic line
 * has no spoken question to introduce.
 */
const DISPLAY_ONLY_SLOTS: readonly DeliverySlot[] = ["orientTyped", "closing", "topicMeasurements"];

function keysOf(slots: readonly DeliverySlot[]): DeliveryKey[] {
  return slots.flatMap((slot) => [...DELIVERY_DECK[slot]]);
}

const ALL_SLOTS = Object.keys(DELIVERY_DECK) as DeliverySlot[];

/** Every key in the deck, in deck order. */
export const DELIVERY_KEYS: readonly DeliveryKey[] = keysOf(ALL_SLOTS);

/**
 * The keys the voice lane may SPEAK — and therefore the only delivery lines
 * the server's George route admits (services/api dev_voice_delivery.py, held
 * to this list by deliveryPlan.test.ts).
 */
export const VOICE_DELIVERY_KEYS: readonly DeliveryKey[] = keysOf(
  ALL_SLOTS.filter((slot) => !DISPLAY_ONLY_SLOTS.includes(slot)),
);

const KEY_SET: ReadonlySet<string> = new Set(DELIVERY_KEYS);

export function isDeliveryKey(key: string): key is DeliveryKey {
  return KEY_SET.has(key);
}

/** `key` as a deck key, or null — for callers holding an utterance's key. */
export function asDeliveryKey(key: string): DeliveryKey | null {
  return isDeliveryKey(key) ? key : null;
}

/**
 * How each slot's lines are delivered (INT-414 / INT-415) — the voice profile,
 * never the words. The composer tags a line with its slot's context, except
 * the two lines that stand in front of a question the patient is struggling
 * with (`repair`, `silence`), which take that question's own context so the
 * voice does not change register between the line and the question.
 */
export const SLOT_CONTEXT: Record<DeliverySlot, DeliveryContext> = {
  welcome: "welcome",
  orientVoice: "welcome",
  orientTyped: "welcome",
  resume: "routine",
  routine: "routine",
  thanks: "acknowledgement",
  hesitant: "acknowledgement",
  revised: "acknowledgement",
  silence: "routine",
  repair: "routine",
  pain: "routine",
  instrument: "instrument",
  sensitive: "sensitive",
  sensitiveLead: "sensitive",
  topicAllergies: "routine",
  topicMedications: "routine",
  topicPmh: "routine",
  topicFamily: "sensitive",
  topicSocial: "routine",
  topicMeasurements: "routine",
  topicWrapup: "routine",
  closing: "closing",
};

const SLOT_OF: ReadonlyMap<string, DeliverySlot> = new Map(
  ALL_SLOTS.flatMap((slot) => DELIVERY_DECK[slot].map((key) => [key, slot] as const)),
);

/** The slot a deck key belongs to. Keys are unique across slots, so this is total. */
export function slotOf(key: string): DeliverySlot | undefined {
  return SLOT_OF.get(key);
}

/**
 * The context a line's clip is made in ahead of time. Exactly the slot's
 * context, so every pre-warmed clip is the one a turn asks for; a repair or
 * silence line in front of a sensitive or instrument question is the one
 * miss, and a missed lead-in is dropped for its turn, never waited for.
 */
export function prewarmContextOf(key: string): DeliveryContext {
  const slot = slotOf(key);
  return slot === undefined ? "routine" : SLOT_CONTEXT[slot];
}

/** The Turkish line for a deck key — the voice is Turkish whatever the UI locale. */
export function deliveryTextTr(key: DeliveryKey): string {
  return t(key, "tr");
}

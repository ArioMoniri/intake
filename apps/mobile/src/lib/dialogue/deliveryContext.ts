/**
 * Delivery context for one spoken utterance (INT-414 / INT-415).
 *
 * The composer (delivery.ts) tags every utterance with one context; the voice
 * lane maps the context to a server-side delivery profile (ElevenLabs
 * voice_settings on the clip lane, the self-hosted TTS controls on
 * residency_tr). The context never changes the words — only how they are said.
 */
export const DELIVERY_CONTEXTS = [
  "welcome",
  "routine",
  "sensitive",
  "instrument",
  "acknowledgement",
  "red",
  "closing",
] as const;

export type DeliveryContext = (typeof DELIVERY_CONTEXTS)[number];

export const DEFAULT_DELIVERY_CONTEXT: DeliveryContext = "routine";

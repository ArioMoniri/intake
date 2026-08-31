/**
 * One-tap satisfaction after a sent note (INT-137; 02 §5.4 *"a one-tap 'Bu
 * görüşme nasıldı?' (1–5) with reason chips … never blocks sending"*).
 *
 * Pure state, so the two rules that matter are testable in node:
 *
 * 1. **Consent gates collection, closed.** A satisfaction score is personal
 *    data with a stated purpose, and files/06 §2 already names that purpose —
 *    `satisfaction`, açık rıza, default OFF. Nothing is collected until the
 *    patient has granted it against a loaded, hash-bound text, which is what
 *    `csatCollectable` asks the INT-132 ledger. No new purpose is invented
 *    here and no new data field is declared: the shape below is INT-240's
 *    landed `csat.v1` (score + reason enum), so the inventory annotation that
 *    covers it is the one that already exists.
 * 2. **It can never gate the send.** This module knows nothing about the note
 *    at all — no import, no reference — and the prompt renders only from the
 *    review screen's SENT branch. A patient who refuses the purpose, ignores
 *    the question or answers half of it has already sent.
 *
 * The reason ids are `packages/clinical-schemas` `CsatReason` verbatim; the
 * spec's own chip wording (02 §5.4: *çok uzundu · beni anlamadı · acele
 * ettirdi · yardımcı oldu · dinlendiğimi hissettim*) is the catalogue label
 * for each. `reason` is REQUIRED by csat.v1, so a score on its own is a
 * recorded tap and not yet a submittable event — see `csatResponse`.
 *
 * Invariant 20: nothing here renders a score back to the patient, and no
 * average, rate or target appears in any string this module names.
 */
import { viewOf, type LedgerState } from "../consent/ledger";
import type { MessageKey } from "../i18n";

/** `packages/clinical-schemas` `CsatReason`, mirrored key-for-key. */
export type CsatReasonId =
  "too_long" | "didnt_understand_me" | "felt_rushed" | "helpful" | "felt_heard";

/** csat.v1 constrains the score to 1–5 (files/08 §4 group F). */
export type CsatScore = 1 | 2 | 3 | 4 | 5;

export interface CsatChoice<Id> {
  readonly id: Id;
  readonly labelKey: MessageKey;
}

/**
 * The scale, as words rather than numerals. The score that reaches csat.v1 is
 * still 1–5; what the patient taps is a Turkish phrase, which is the same
 * ruling the intake packs already follow for severity (a bare digit is not a
 * B1 reading of "how was it", and this app renders no numeric scale to a
 * patient anywhere else).
 */
export const CSAT_SCORES: readonly (CsatChoice<string> & { readonly score: CsatScore })[] = [
  { id: "1", score: 1, labelKey: "csat.score.veryBad" },
  { id: "2", score: 2, labelKey: "csat.score.bad" },
  { id: "3", score: 3, labelKey: "csat.score.ok" },
  { id: "4", score: 4, labelKey: "csat.score.good" },
  { id: "5", score: 5, labelKey: "csat.score.veryGood" },
];

/** 02 §5.4's reason chips, in the enum's own order. */
export const CSAT_REASONS: readonly CsatChoice<CsatReasonId>[] = [
  { id: "too_long", labelKey: "csat.reason.tooLong" },
  { id: "didnt_understand_me", labelKey: "csat.reason.didntUnderstandMe" },
  { id: "felt_rushed", labelKey: "csat.reason.feltRushed" },
  { id: "helpful", labelKey: "csat.reason.helpful" },
  { id: "felt_heard", labelKey: "csat.reason.feltHeard" },
];

export interface CsatState {
  score: CsatScore | null;
  reason: CsatReasonId | null;
}

export type CsatAction =
  { type: "score"; score: CsatScore } | { type: "reason"; reason: CsatReasonId };

export function emptyCsat(): CsatState {
  return { score: null, reason: null };
}

export function csatReducer(state: CsatState, action: CsatAction): CsatState {
  switch (action.type) {
    case "score":
      return { ...state, score: action.score };
    case "reason":
      return { ...state, reason: action.reason };
  }
}

/** The csat.v1 body, or null while it is not yet a valid one. */
export interface CsatResponse {
  score: CsatScore;
  reason: CsatReasonId;
}

/**
 * `reason` is required by csat.v1, so a score alone does not form an event.
 * The tap is still recorded (the patient answered), and no reason is guessed
 * from it — a defaulted reason would be an invented data point in an
 * analytics table nobody could later tell apart from a real one.
 */
export function csatResponse(state: CsatState): CsatResponse | null {
  return state.score === null || state.reason === null
    ? null
    : { score: state.score, reason: state.reason };
}

/**
 * files/06 §2 `satisfaction`: açık rıza, default OFF, unbundled. Fails closed
 * on a fresh ledger, on a ledger with the text loaded but not granted, and on
 * any other purpose being granted instead.
 */
export function csatCollectable(ledger: LedgerState): boolean {
  return viewOf(ledger).some((purpose) => purpose.id === "satisfaction" && purpose.allowed);
}

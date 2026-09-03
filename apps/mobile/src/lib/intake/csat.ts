/**
 * One-tap satisfaction after a sent note (INT-137; 02 §5.4 *"a one-tap 'Bu
 * görüşme nasıldı?' (1–5) with reason chips … never blocks sending"*).
 *
 * Pure state, so the two rules that matter are testable in node.
 *
 * **1. Consent gates collection, closed.** A satisfaction score is personal
 * data with a stated purpose, and files/06 §2 already names that purpose —
 * `satisfaction`, açık rıza, default OFF. Nothing is collected until the
 * patient has granted it against a loaded, hash-bound text, which is what
 * `csatCollectable` asks the INT-132 ledger. No new purpose is invented and no
 * new data field is declared: the shape below is INT-240's landed `csat.v1`
 * (score + reason enum), so the files/06 inventory annotation that covers it
 * is the one that already exists.
 *
 * **Which record, and why it is not an İYS one.** Invariant 18 makes reminders
 * transactional-only absent an İYS record, and a satisfaction question is not
 * transactional. It is also not a *ticari elektronik ileti*: 6563 reaches
 * messages **sent** to a recipient over a channel, and this is a card on a
 * screen the patient is already looking at, one scroll below the button they
 * just pressed. Nothing is dispatched — this module and its component import
 * no notification port, no channel and no scheduler, and INT-242's cadence
 * deliberately excludes `csat` for the same reason (`surveys/cadence.py`:
 * CSAT is *"triggered by the session ending rather than by a clock, so it has
 * no cadence to own"*). The record that governs it is therefore the KVKK
 * m.6 açık rıza for `satisfaction`, not an İYS registration — and that record
 * cannot exist yet, because the consent-text catalogue is empty until INT-210
 * authors `satisfaction.tr.md`. So the prompt fails closed today, by the same
 * gate that will open it later. That is the mechanism wired and the content
 * left empty, not a gap worked around.
 *
 * **2. It can never gate the send.** This module knows nothing about the note
 * — no import, no reference — and the prompt renders only from the review
 * screen's already-SENT branch. A patient who refuses the purpose, ignores the
 * question or answers half of it has already sent.
 *
 * The reason ids are `packages/clinical-schemas` `CsatReason` verbatim; the
 * spec's own chip wording (02 §5.4: *çok uzundu · beni anlamadı · acele
 * ettirdi · yardımcı oldu · dinlendiğimi hissettim*) is the catalogue label for
 * each. `reason` is REQUIRED by csat.v1, so a score on its own is a recorded
 * tap and not yet a submittable event — see `csatResponse`.
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
 * The scale, as words rather than numerals. The score that would reach csat.v1
 * is still 1–5; what the patient taps is a Turkish phrase — invariant 22's
 * ruling, and the same one the intake packs already follow for severity. A
 * bare digit is not a B1 reading of "how was it", and this app renders no
 * numeric scale to a patient anywhere else.
 */
export const CSAT_SCORES: readonly (CsatChoice<string> & { readonly score: CsatScore })[] = [
  { id: "very_bad", score: 1, labelKey: "csat.score.veryBad" },
  { id: "bad", score: 2, labelKey: "csat.score.bad" },
  { id: "ok", score: 3, labelKey: "csat.score.ok" },
  { id: "good", score: 4, labelKey: "csat.score.good" },
  { id: "very_good", score: 5, labelKey: "csat.score.veryGood" },
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
 * The tap is still held (the patient answered), and no reason is guessed from
 * it — a defaulted reason would be an invented data point that nobody could
 * later tell apart from a real one, and it would be the patient's words put
 * into their mouth. INT-275 carries the spec's own contradiction here: §5.4
 * calls the prompt one-tap and csat.v1 requires the reason.
 */
export function csatResponse(state: CsatState): CsatResponse | null {
  return state.score === null || state.reason === null
    ? null
    : { score: state.score, reason: state.reason };
}

/**
 * files/06 §2 `satisfaction`: açık rıza, default OFF, unbundled. Fails closed
 * on a fresh ledger, on a ledger whose text has not landed, and on any other
 * purpose being granted instead — the ledger's own `grant` refuses without a
 * loaded text, so an ungranted purpose cannot become `allowed` by any path.
 */
export function csatCollectable(ledger: LedgerState): boolean {
  return viewOf(ledger).some((purpose) => purpose.id === "satisfaction" && purpose.allowed);
}

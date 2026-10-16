/**
 * INT-510 — the send's own state, and the one transition that makes a note
 * sent. Kept beside ./note (which embeds it in `NoteState` and dispatches to
 * it) so the note builder stays the note builder; type-only imports back, so
 * there is no runtime cycle.
 *
 * `status` says what the server confirmed; `delivery` says what is happening
 * to the send on the way there:
 *
 * - `sending` — in flight; the note is frozen so what goes is what was confirmed;
 * - `queued`  — the server could not be reached; the send waits in the sealed
 *   draft store (INT-142) and is retried, and the note is NOT sent;
 * - `refused` — the server said no, for the reason the review screen words.
 */
import type { NoteAction, NoteState } from "./note";

/**
 * Why a send did not reach the clinic. Each one is a different true sentence
 * on the review screen, so none of them collapses into another.
 */
export type SendRefusal =
  /** the server refused `share:previsit_note` (403 `consent_required`) */
  | "consent"
  /** the age/guardian gate refused the share (INT-223's three codes) */
  | "not_allowed"
  /** no session the server honours — a sign-in is the way on */
  | "session"
  /** every section is scoped off; there is nothing to send */
  | "nothing_shared"
  /** the synthetic dev session, which has no clinic to send to */
  | "synthetic"
  /** anything else the server refused; never retried behind the patient's back */
  | "failed";

export type NoteDelivery =
  | { phase: "idle" }
  | { phase: "sending" }
  | { phase: "queued" }
  | { phase: "refused"; reason: SendRefusal };

export const IDLE_DELIVERY: NoteDelivery = { phase: "idle" };

export type DeliveryAction = Extract<
  NoteAction,
  { type: "send" | "delivered" | "queued" | "refused" | "retry" }
>;

export function isDeliveryAction(action: NoteAction): action is DeliveryAction {
  return (
    action.type === "send" ||
    action.type === "delivered" ||
    action.type === "queued" ||
    action.type === "refused" ||
    action.type === "retry"
  );
}

/**
 * The send's transitions. The server's answer lands only on a send that is in
 * flight, so a late or duplicate answer cannot move a note the patient has
 * since changed — and only `delivered`, the server's 200, makes a note sent.
 */
export function deliveryStep(state: NoteState, action: DeliveryAction): NoteState {
  const inFlight = state.delivery.phase === "sending";
  switch (action.type) {
    case "send":
      // Never refused on the phone (02 §5.1), never doubled, never re-sent.
      return state.status === "sent" || inFlight
        ? state
        : { ...state, delivery: { phase: "sending" } };
    case "delivered":
      return inFlight ? { ...state, status: "sent", delivery: IDLE_DELIVERY } : state;
    case "queued":
      return inFlight ? { ...state, delivery: { phase: "queued" } } : state;
    case "refused":
      return inFlight ? { ...state, delivery: { phase: "refused", reason: action.reason } } : state;
    case "retry":
      return state.delivery.phase === "queued"
        ? { ...state, delivery: { phase: "sending" } }
        : state;
  }
}

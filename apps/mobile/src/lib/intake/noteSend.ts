/**
 * INT-510 — the patient's send, as pure rules: what the phone sends, how it
 * reads the server's answer, and how the session's outbox moves.
 *
 * Before this issue the review screen's Gönder flipped the note to `sent` and
 * nothing left the phone (the INT-498 audit, F07/F08/F11). Now a send is
 *
 *   1. resolve the SERVER visit for the local one (create it if missing);
 *   2. `PUT /v1/visits/{server id}/note` with `status: "sent"` and exactly the
 *      sections the patient left on;
 *   3. `sent` on the phone only when that PUT answered 200 with `status: "sent"`.
 *
 * The server owns the consent check and the audit (notes.py `write_note`:
 * `ensure_consent(share:previsit_note)`, then the share row, then
 * `api.note.share` — invariant 4). The phone's job is to not pretend: a refused
 * consent is a worded refusal, an unreachable server is a queued send that
 * waits in the sealed draft store (INT-142), and neither touches `status`.
 *
 * Nothing here touches the network, a clock or a log: the transport is
 * injected (`NoteSendPorts`, bound in ./noteSendClient), so the whole rule is
 * provable in node. Ids only ever leave as path segments; no section text, id
 * or answer is logged (invariant 6).
 */
import type { LineTone } from "../a11y/announce";
import { t, type MessageKey } from "../i18n";
import { isSyntheticSession, type SessionKind } from "../profile/badge";
import {
  buildNote,
  noteReducer,
  sentSections,
  type NoteAccount,
  type NoteAction,
  type NoteDelivery,
  type NoteState,
  type SendRefusal,
} from "./note";

/** One section as `NoteSection` on the server reads it. */
export interface NotePutSection {
  id: string;
  title: string;
  lines: string[];
}

/** The `NotePut` body (services/api schemas.py) for a send. */
export interface NotePutBody {
  sections: NotePutSection[];
  scopes: Record<string, boolean>;
  status: "sent";
}

/**
 * The body a send carries, or null when the patient shares nothing.
 *
 * `sections` is exactly the scoped-on set — a withheld section's content never
 * leaves the phone. `scopes` names every section the note built, `true` for
 * shared and `false` for withheld, so the server still records the withholding
 * as a fact (INT-304; `withheld_section_ids` reads `scopes`). Titles come from
 * the catalogue, as the lines already do (invariant 5).
 */
export function notePutBody(note: NoteState, account: NoteAccount): NotePutBody | null {
  const shared = sentSections(note, account);
  if (shared.length === 0) {
    return null;
  }
  const built = buildNote(note.answers, account, note.healthLines, note.deferred, note.factReview);
  const scopes: Record<string, boolean> = {};
  for (const section of built) {
    scopes[section.id] = note.scopes[section.id] !== false;
  }
  return {
    sections: shared.map((section) => ({
      id: section.id,
      title: t(section.titleKey),
      lines: [...section.lines],
    })),
    scopes,
    status: "sent",
  };
}

/** What one PUT answered, reduced to what the rule reads. */
export interface PutAnswer {
  status: number;
  /** The server's `error` code (`consent_required`, …), "" when none. */
  error: string;
  /** `NoteOut.status` on a 2xx, null otherwise. */
  noteStatus: string | null;
}

/** A PUT that answered, or the transport's reason it did not. */
export type PutResult = PutAnswer | "unreachable" | "session";

/**
 * The server visit for this local visit, or the reason there is none.
 * `consent`: creating the visit was refused for a missing consent — worded as
 * one, never folded into a generic failure.
 */
export type ResolveResult = { id: string } | "unreachable" | "session" | "consent" | "refused";

/** The transport a send runs over — bound to authedFetch in ./noteSendClient. */
export interface NoteSendPorts {
  /** Find the server visit for the local one, creating it when missing. */
  resolveServerVisit(): Promise<ResolveResult>;
  /** `PUT /v1/visits/{serverVisitId}/note`. */
  putNote(serverVisitId: string, body: NotePutBody): Promise<PutResult>;
}

/** How one send ended; `serverVisitId` is whatever id the session should now hold. */
export type SendOutcome =
  | { kind: "delivered"; serverVisitId: string }
  | { kind: "queued"; serverVisitId: string | null }
  | { kind: "refused"; reason: SendRefusal; serverVisitId: string | null };

/** The age/guardian gate's refusal codes (services/api errors.age_gate_refused). */
const AGE_GATE_CODES: ReadonlySet<string> = new Set([
  "guardian_consent_required",
  "dob_unverified",
  "jurisdiction_unsupported",
]);

/** Statuses that mean "not now", never "no": the send stays queued. */
const TRANSIENT: ReadonlySet<number> = new Set([408, 425, 429, 500, 502, 503, 504]);

/**
 * The rule that reads the server's answer. `delivered` needs BOTH halves — a
 * 200 and the note coming back `sent` — so no other answer can show "sent".
 * `stale` means the server does not know the visit id; the caller resolves
 * once more rather than reporting it.
 */
export function classifyPut(answer: PutAnswer): "delivered" | "queued" | "stale" | SendRefusal {
  if (answer.status === 200) {
    return answer.noteStatus === "sent" ? "delivered" : "failed";
  }
  if (answer.status === 403 && answer.error === "consent_required") {
    return "consent";
  }
  if (answer.status === 403 && AGE_GATE_CODES.has(answer.error)) {
    return "not_allowed";
  }
  if (answer.status === 401) {
    return "session";
  }
  if (answer.status === 404) {
    return "stale";
  }
  if (TRANSIENT.has(answer.status)) {
    return "queued";
  }
  return "failed";
}

export interface DeliverInput {
  note: NoteState;
  account: NoteAccount & SessionKind;
  /** The id the session's map already holds for this visit, if any. */
  knownServerVisitId: string | null;
}

/**
 * Send one note. Never throws: every way it can end is a `SendOutcome`.
 *
 * The synthetic dev session and a note with nothing shared reach no network at
 * all. A held server id is used as is; if the server no longer knows it, the
 * visit is resolved once more and the PUT repeated once — never a loop.
 */
export async function deliverNote(input: DeliverInput, ports: NoteSendPorts): Promise<SendOutcome> {
  if (isSyntheticSession(input.account)) {
    return { kind: "refused", reason: "synthetic", serverVisitId: null };
  }
  const body = notePutBody(input.note, input.account);
  if (body === null) {
    return { kind: "refused", reason: "nothing_shared", serverVisitId: null };
  }

  let serverVisitId = input.knownServerVisitId;
  let resolvedHere = false;
  for (;;) {
    if (serverVisitId === null) {
      const resolved = await ports.resolveServerVisit();
      if (resolved === "unreachable") {
        return { kind: "queued", serverVisitId: null };
      }
      if (resolved === "session") {
        return { kind: "refused", reason: "session", serverVisitId: null };
      }
      if (resolved === "consent") {
        return { kind: "refused", reason: "consent", serverVisitId: null };
      }
      if (resolved === "refused") {
        return { kind: "refused", reason: "failed", serverVisitId: null };
      }
      serverVisitId = resolved.id;
      resolvedHere = true;
    }

    const answer = await ports.putNote(serverVisitId, body);
    if (answer === "unreachable") {
      return { kind: "queued", serverVisitId };
    }
    if (answer === "session") {
      return { kind: "refused", reason: "session", serverVisitId };
    }
    const verdict = classifyPut(answer);
    if (verdict === "delivered") {
      return { kind: "delivered", serverVisitId };
    }
    if (verdict === "queued") {
      return { kind: "queued", serverVisitId };
    }
    if (verdict === "stale") {
      if (resolvedHere) {
        // freshly resolved and still unknown: the map must not keep it
        return { kind: "refused", reason: "failed", serverVisitId: null };
      }
      serverVisitId = null;
      continue;
    }
    return { kind: "refused", reason: verdict, serverVisitId };
  }
}

// --- the session's outbox, as pure rules ------------------------------------------------

/** How long a queued send waits before it is tried again. */
export const SEND_RETRY_MS = 30_000;

/** Visits whose send is in flight on the note and not yet being sent. */
export function sendsDue(
  notes: Readonly<Record<string, NoteState>>,
  inFlight: ReadonlySet<string>,
): string[] {
  return Object.keys(notes).filter(
    (visitId) => notes[visitId].delivery.phase === "sending" && !inFlight.has(visitId),
  );
}

export function hasQueuedSend(notes: Readonly<Record<string, NoteState>>): boolean {
  return Object.values(notes).some((note) => note.delivery.phase === "queued");
}

/** Every queued send back in flight; the same object when nothing was queued. */
export function retryQueuedSends(notes: Record<string, NoteState>): Record<string, NoteState> {
  if (!hasQueuedSend(notes)) {
    return notes;
  }
  const next: Record<string, NoteState> = {};
  for (const [visitId, note] of Object.entries(notes)) {
    next[visitId] = noteReducer(note, { type: "retry" });
  }
  return next;
}

function actionFor(outcome: SendOutcome): NoteAction {
  switch (outcome.kind) {
    case "delivered":
      return { type: "delivered" };
    case "queued":
      return { type: "queued" };
    case "refused":
      return { type: "refused", reason: outcome.reason };
  }
}

/**
 * Apply one send's outcome to the note it was for. A note the session wiped
 * while the send was in flight stays wiped — it is never recreated to carry a
 * status (the session also drops outcomes from an earlier sign-in).
 */
export function settleSend(
  notes: Record<string, NoteState>,
  visitId: string,
  outcome: SendOutcome,
): Record<string, NoteState> {
  const note = notes[visitId];
  if (note === undefined) {
    return notes;
  }
  const next = noteReducer(note, actionFor(outcome));
  return next === note ? notes : { ...notes, [visitId]: next };
}

// --- what the review screen says ------------------------------------------------------

const REFUSAL_KEY: Record<SendRefusal, MessageKey> = {
  consent: "review.delivery.consent",
  not_allowed: "review.delivery.notAllowed",
  session: "records.err.session",
  nothing_shared: "review.delivery.empty",
  synthetic: "review.delivery.synthetic",
  failed: "review.delivery.failed",
};

/** The line for a send's state, or null while nothing is happening. */
export function deliveryLine(
  delivery: NoteDelivery,
): { tone: Extract<LineTone, "status" | "error">; key: MessageKey } | null {
  switch (delivery.phase) {
    case "idle":
      return null;
    case "sending":
      return { tone: "status", key: "review.delivery.sending" };
    case "queued":
      return { tone: "status", key: "review.delivery.queued" };
    case "refused":
      return { tone: "error", key: REFUSAL_KEY[delivery.reason] };
  }
}

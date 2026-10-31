/**
 * INT-587 — the delivery state machine for one sent note. Pure and
 * node-testable; the store (./store) persists it and runs it.
 *
 * A note the patient sends is frozen on the phone and enters this machine
 * only once they have agreed to share it (a share-consent receipt — ./store).
 * From there it rests in one of four stages, and each stage has one rule:
 *
 * - `queued` — waiting to reach the server. Retried with exponential backoff
 *   up to a cap, honouring a server Retry-After, for as long as it takes. It
 *   is never dropped: no count of failures removes it.
 * - `awaiting_consent` — the server refused the share scope, or the patient
 *   withdrew the share consent on this phone. Never retried on its own: it
 *   waits for the patient to agree again, FOR THIS NOTE. Parking unbinds the
 *   note's grant, and only a fresh grant given for this note releases it — a
 *   later grant for another note never does (INT-587 legal review B1). A
 *   withdrawal parks refused notes too, so "Tekrar deneyin" cannot resend one.
 * - `refused` — the server answered with a 4xx that a retry cannot change, or
 *   the session is gone. Surfaced to the patient with its reason and never
 *   retried on its own; the patient's "Tekrar deneyin" is the only way back.
 * - `delivered` — the server confirmed the send (`status: "sent"`). The only
 *   stage from which the app may say the note was sent, and terminal. The
 *   note's text is dropped from the item here: the server holds it now, and
 *   the phone keeps only what it needs to address the share.
 */
import { isNotePutBody, type NotePutBody } from "./payload";

export type DeliveryStage = "queued" | "awaiting_consent" | "refused" | "delivered";

/** Why the server (or the phone, before sending) said no — one per true sentence. */
export type RefusalReason = "core_consent" | "session" | "not_found" | "invalid" | "rejected";

const STAGES: readonly DeliveryStage[] = ["queued", "awaiting_consent", "refused", "delivered"];
const REASONS: readonly RefusalReason[] = [
  "core_consent",
  "session",
  "not_found",
  "invalid",
  "rejected",
];

/** The visit as the server needs it to find or create its own row. */
export interface VisitIdentity {
  hospital: string;
  department: string;
  date: string | null;
  branchId: string | null;
  visitType: string | null;
}

/**
 * The share grant a note was queued (or released) under: the text it bound
 * and the instant it was given. Sealed with the note, so a restart keeps the
 * note bound to its own consent — or parked without one.
 */
export interface ShareGrantBinding {
  version: string;
  textHash: string;
  atIso: string;
}

export interface DeliveryItem {
  /** The app's id for the visit (a local, feed or server id). */
  visitId: string;
  /** The signed-in account that sent it; hydration never crosses accounts. */
  accountId: string;
  visit: VisitIdentity;
  /** The frozen PUT body; null once delivered. */
  body: NotePutBody | null;
  stage: DeliveryStage;
  attempts: number;
  /** Epoch ms before which a queued item is not attempted. */
  nextAttemptAt: number;
  refusal: RefusalReason | null;
  /** The server's visit id, once found — what the Doctor Link routes address. */
  serverVisitId: string | null;
  deliveredAt: number | null;
  /** This note's own share grant; null while parked for consent. */
  grant: ShareGrantBinding | null;
}

export const BACKOFF = { baseMs: 2_000, capMs: 15 * 60 * 1_000 } as const;

/** Exponential from the base, flat at the cap. `attempts` counts from 1. */
export function backoffMs(attempts: number): number {
  const exponent = Math.max(0, attempts - 1);
  if (exponent >= 30) {
    return BACKOFF.capMs;
  }
  return Math.min(BACKOFF.capMs, BACKOFF.baseMs * 2 ** exponent);
}

export function newItem(
  input: {
    visitId: string;
    accountId: string;
    visit: VisitIdentity;
    body: NotePutBody;
    grant: ShareGrantBinding;
  },
  now: number,
): DeliveryItem {
  return {
    visitId: input.visitId,
    accountId: input.accountId,
    visit: { ...input.visit },
    body: input.body,
    stage: "queued",
    attempts: 0,
    nextAttemptAt: now,
    refusal: null,
    serverVisitId: null,
    deliveredAt: null,
    grant: { ...input.grant },
  };
}

/** What one attempt came to — the engine's verdict, never an exception. */
export type AttemptOutcome =
  | { kind: "delivered"; serverVisitId: string }
  | { kind: "transient"; retryAfterMs: number | null; serverVisitId: string | null }
  | { kind: "consent"; serverVisitId: string | null }
  | { kind: "refused"; reason: RefusalReason; serverVisitId: string | null };

/** Apply one attempt's outcome. A delivered item is terminal. */
export function settle(item: DeliveryItem, outcome: AttemptOutcome, now: number): DeliveryItem {
  if (item.stage === "delivered") {
    return item;
  }
  const serverVisitId = outcome.serverVisitId ?? item.serverVisitId;
  const attempts = item.attempts + 1;
  switch (outcome.kind) {
    case "delivered":
      return {
        ...item,
        body: null,
        stage: "delivered",
        attempts,
        refusal: null,
        serverVisitId: outcome.serverVisitId,
        deliveredAt: now,
        // the server holds the grant row now; the phone keeps no copy
        grant: null,
      };
    case "transient": {
      const wait =
        outcome.retryAfterMs === null
          ? backoffMs(attempts)
          : Math.min(BACKOFF.capMs, Math.max(0, outcome.retryAfterMs));
      return {
        ...item,
        stage: "queued",
        attempts,
        nextAttemptAt: now + wait,
        refusal: null,
        serverVisitId,
      };
    }
    case "consent":
      return { ...item, stage: "awaiting_consent", attempts, refusal: null, serverVisitId };
    case "refused":
      return { ...item, stage: "refused", attempts, refusal: outcome.reason, serverVisitId };
  }
}

/** Only a queued item whose wait is over is attempted. */
export function isDue(item: DeliveryItem, now: number): boolean {
  return item.stage === "queued" && item.nextAttemptAt <= now;
}

/** The patient's "Tekrar deneyin" on a refused item — the only way back. */
export function retryNow(item: DeliveryItem, now: number): DeliveryItem {
  if (item.stage !== "refused") {
    return item;
  }
  return { ...item, stage: "queued", refusal: null, nextAttemptAt: now };
}

/** A fresh share-consent grant FOR THIS NOTE releases it, bound to that grant.
 * The store checks the receipt names this note before it calls this. */
export function reconfirm(item: DeliveryItem, grant: ShareGrantBinding, now: number): DeliveryItem {
  if (item.stage !== "awaiting_consent") {
    return item;
  }
  return { ...item, stage: "queued", nextAttemptAt: now, grant: { ...grant } };
}

/**
 * The patient withdrew the share consent on this phone: nothing unsent
 * leaves. Queued AND refused notes are parked — a refused note's "Tekrar
 * deneyin" must not resend it under a consent that has been taken back — and
 * the note's grant is unbound, so only a new grant for this note releases it
 * (INT-587 legal review B1).
 */
export function holdForConsent(item: DeliveryItem): DeliveryItem {
  if (item.stage !== "queued" && item.stage !== "refused") {
    return item;
  }
  return { ...item, stage: "awaiting_consent", refusal: null, grant: null };
}

/**
 * Whether the patient may take this note back to a draft. Only where nothing
 * can have reached the server: no item yet, one waiting for consent, or one
 * the server refused (a refusal rolls its transaction back). Never a queued
 * item — a PUT may be in flight, or its answer lost after the server wrote it —
 * and never a delivered one.
 */
export function reopenable(item: DeliveryItem | null): boolean {
  return item === null || item.stage === "awaiting_consent" || item.stage === "refused";
}

/**
 * INT-589 (1): whether a DELIVERED note lost its share to a withdrawal made
 * after it was delivered. The server revoked its share and every link then
 * (consents.py), so it can no longer be linked until it is shared again.
 * Instants are compared as instants; an unreadable one asks for nothing.
 */
export function needsReshare(item: DeliveryItem | null, withdrawnAt: string | null): boolean {
  if (item === null || item.stage !== "delivered" || item.deliveredAt === null) {
    return false;
  }
  if (withdrawnAt === null) {
    return false;
  }
  const withdrawn = Date.parse(withdrawnAt);
  return Number.isFinite(withdrawn) && withdrawn > item.deliveredAt;
}

/**
 * Share a delivered note again: the same frozen body, bound to a fresh grant
 * given FOR THIS NOTE, queued as a send of its own. The server recreates the
 * share in that PUT (notes.write_note). Only a delivered note is re-shared; a
 * note still on its way is reconfirmed instead (`reconfirm`).
 */
export function reshare(
  item: DeliveryItem,
  body: NotePutBody,
  grant: ShareGrantBinding,
  now: number,
): DeliveryItem {
  if (item.stage !== "delivered") {
    return item;
  }
  return {
    ...item,
    body,
    stage: "queued",
    attempts: 0,
    nextAttemptAt: now,
    refusal: null,
    deliveredAt: null,
    grant: { ...grant },
  };
}

/** INT-589 (2): every note a sign-out would shred before it reached anyone. */
export function unsentItems(items: Readonly<Record<string, DeliveryItem>>): DeliveryItem[] {
  return Object.values(items).filter((item) => item.stage !== "delivered");
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function parseGrant(raw: unknown): ShareGrantBinding | null {
  if (typeof raw !== "object" || raw === null) {
    return null;
  }
  const grant = raw as Record<string, unknown>;
  if (!isString(grant.version) || !isString(grant.textHash) || !isString(grant.atIso)) {
    return null;
  }
  return { version: grant.version, textHash: grant.textHash, atIso: grant.atIso };
}

function parseVisit(raw: unknown): VisitIdentity | null {
  if (typeof raw !== "object" || raw === null) {
    return null;
  }
  const visit = raw as Record<string, unknown>;
  if (
    !isString(visit.hospital) ||
    !isString(visit.department) ||
    !isNullableString(visit.date) ||
    !isNullableString(visit.branchId) ||
    !isNullableString(visit.visitType)
  ) {
    return null;
  }
  return {
    hospital: visit.hospital,
    department: visit.department,
    date: visit.date,
    branchId: visit.branchId,
    visitType: visit.visitType,
  };
}

/** A stored item, validated field by field. Anything off-shape is null —
 * never a half-trusted item that could be sent. */
export function parseItem(raw: unknown): DeliveryItem | null {
  if (typeof raw !== "object" || raw === null) {
    return null;
  }
  const item = raw as Record<string, unknown>;
  const stage = STAGES.find((s) => s === item.stage);
  const visit = parseVisit(item.visit);
  if (
    stage === undefined ||
    visit === null ||
    !isString(item.visitId) ||
    !isString(item.accountId) ||
    !isFiniteNumber(item.attempts) ||
    !isFiniteNumber(item.nextAttemptAt) ||
    !isNullableString(item.serverVisitId) ||
    !(item.deliveredAt === null || isFiniteNumber(item.deliveredAt))
  ) {
    return null;
  }
  const refusal = item.refusal === null ? null : (REASONS.find((r) => r === item.refusal) ?? null);
  if (item.refusal !== null && refusal === null) {
    return null;
  }
  let body: NotePutBody | null = null;
  if (stage === "delivered") {
    if (item.body !== null || !isString(item.serverVisitId)) {
      return null;
    }
  } else {
    if (!isNotePutBody(item.body)) {
      return null; // a note still to be sent must carry a body the server accepts
    }
    body = item.body;
  }
  const parsed: DeliveryItem = {
    visitId: item.visitId,
    accountId: item.accountId,
    visit,
    body,
    stage,
    attempts: item.attempts,
    nextAttemptAt: item.nextAttemptAt,
    refusal,
    serverVisitId: item.serverVisitId,
    deliveredAt: item.deliveredAt as number | null,
    grant: parseGrant(item.grant),
  };
  // A note that could still leave the phone but carries no valid grant of its
  // own comes back parked — kept, never sendable, never resurrected.
  if ((stage === "queued" || stage === "refused") && parsed.grant === null) {
    return holdForConsent(parsed);
  }
  return parsed;
}

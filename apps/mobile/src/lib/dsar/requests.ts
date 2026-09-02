/**
 * INT-140 — the data-subject request model behind *Profilim → Verileriniz*.
 *
 * KVKK m.11 is a right, not a preference: the server (INT-037) enforces it,
 * records every filing against the hash-chained audit and runs the m.13
 * clock. This module only READS what that server sends, which is why every
 * function here is total and refusing rather than forgiving:
 *
 * - the kind and the status come from closed sets, so a row carrying a word
 *   the router cannot produce is dropped rather than rendered as an unknown
 *   state;
 * - the grace is read from the instant the server sent, never re-derived
 *   from a duration held on the phone — the phone's clock is not the one the
 *   erasure runs on, and a locally computed deadline would disagree with it
 *   the moment a timezone or a rollout does;
 * - `overdue` is the server's verdict on its own m.13 window. An unreadable
 *   flag is a refusal to parse, not a quiet `false`, because "we are not
 *   late" is exactly the claim a reader must never invent.
 *
 * Nothing here holds patient content. A DSAR row is ids and clocks — files/10
 * §9 keeps it that way precisely so the tracker is safe to render and safe to
 * carry in memory (invariant 6).
 */
import type { MessageKey } from "../i18n";
import { formatFactDate } from "../intake/carriedFacts";

/** The three rights this surface exercises (files/06 §1 KVKK-11/13). */
export const DSAR_KINDS = ["export", "delete", "rectify"] as const;
export type DsarKind = (typeof DSAR_KINDS)[number];

/** The lifecycle the router publishes; nothing else is a state. */
export const DSAR_STATUSES = ["received", "scheduled", "completed", "cancelled"] as const;
export type DsarStatus = (typeof DSAR_STATUSES)[number];

export interface DsarRequest {
  id: string;
  kind: DsarKind;
  status: DsarStatus;
  /** When the controller received it — the instant the m.13 clock started. */
  receivedAt: string;
  /** The m.13 deadline, as the server computed it. */
  dueAt: string;
  /** Erasure only: when the files/06 §3 grace ends and the shred runs. */
  graceEndsAt: string | null;
  completedAt: string | null;
  /** The server's own verdict on its window. */
  overdue: boolean;
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function optionalText(value: unknown): string | null | undefined {
  if (value === null || value === undefined) {
    return null;
  }
  return text(value) ?? undefined;
}

function member<T extends string>(value: unknown, allowed: readonly T[]): T | null {
  return allowed.find((candidate) => candidate === value) ?? null;
}

/** One tracker row, or null when it is not a row this app can read. */
export function parseRequest(raw: unknown): DsarRequest | null {
  if (typeof raw !== "object" || raw === null) {
    return null;
  }
  const row = raw as Record<string, unknown>;
  const id = text(row.request_id);
  const kind = member(row.kind, DSAR_KINDS);
  const status = member(row.status, DSAR_STATUSES);
  const receivedAt = text(row.received_at);
  const dueAt = text(row.due_at);
  const graceEndsAt = optionalText(row.grace_ends_at);
  const completedAt = optionalText(row.completed_at);
  if (
    id === null ||
    kind === null ||
    status === null ||
    receivedAt === null ||
    dueAt === null ||
    graceEndsAt === undefined ||
    completedAt === undefined ||
    typeof row.overdue !== "boolean"
  ) {
    return null;
  }
  return { id, kind, status, receivedAt, dueAt, graceEndsAt, completedAt, overdue: row.overdue };
}

/** The tracker, newest first. Unreadable rows are dropped, never guessed. */
export function parseRequests(raw: unknown): DsarRequest[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw
    .map(parseRequest)
    .filter((request): request is DsarRequest => request !== null)
    .sort((a, b) => b.receivedAt.localeCompare(a.receivedAt));
}

/**
 * Whether the patient may still take an erasure back. This mirrors the
 * server's rule (`cancel_delete`: scheduled, and inside the grace) so the
 * screen does not offer a control that would 409 — it does not replace it.
 */
export function canWithdrawErasure(request: DsarRequest, nowIso: string): boolean {
  return (
    request.kind === "delete" &&
    request.status === "scheduled" &&
    request.graceEndsAt !== null &&
    request.graceEndsAt > nowIso
  );
}

/** The erasure that is still running its grace, if there is one. */
export function scheduledErasure(
  requests: readonly DsarRequest[],
  nowIso: string,
): DsarRequest | null {
  return requests.find((request) => canWithdrawErasure(request, nowIso)) ?? null;
}

/** The newest request of one kind — the row a screen section is about. */
export function latestRequest(
  requests: readonly DsarRequest[],
  kind: DsarKind,
): DsarRequest | null {
  return (
    [...requests]
      .sort((a, b) => b.receivedAt.localeCompare(a.receivedAt))
      .find((request) => request.kind === kind) ?? null
  );
}

const KIND_KEY: Record<DsarKind, MessageKey> = {
  export: "data.kind.export",
  delete: "data.kind.delete",
  rectify: "data.kind.rectify",
};

const STATUS_KEY: Record<DsarStatus, MessageKey> = {
  received: "data.status.received",
  scheduled: "data.status.scheduled",
  completed: "data.status.completed",
  cancelled: "data.status.cancelled",
};

export function kindLabelKey(kind: DsarKind): MessageKey {
  return KIND_KEY[kind];
}

/**
 * The word on the row. A missed m.13 window outranks the lifecycle state: it
 * is the one thing on this screen the patient can act on outside the app, so
 * it is never hidden behind "received".
 */
export function statusLabelKey(request: DsarRequest): MessageKey {
  return request.overdue ? "data.status.overdue" : STATUS_KEY[request.status];
}

/**
 * The day a clock lands on, with the month as a word. One date format in the
 * app: the ledger's, so a deadline and a learned fact read the same way.
 */
export function formatDsarDay(iso: string): string {
  return formatFactDate(iso);
}

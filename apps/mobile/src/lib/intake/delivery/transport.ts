/**
 * INT-587 — the one HTTP call that delivers a note:
 * `PUT /v1/visits/{visit_id}/note` with the `NotePut` body (services/api
 * notes.write_note), over the injected authenticated fetch (INT-131's
 * DPoP-bound `authedFetch` in production — ./native).
 *
 * The server's contract is unchanged and is what makes a retry safe: the PUT
 * is a replace. It upserts the one envelope-encrypted note row, revokes any
 * live share and, for `status: "sent"`, checks the share scope and creates
 * one share scoped to the sections the body marks shared — all in one
 * transaction that rolls back on any refusal. Re-sending the same body after
 * a lost answer therefore leaves the same note and one live share
 * (tests/api/test_note_delivery.py), and a refusal leaves nothing behind.
 *
 * Classification is the policy: a dropped connection, 408, 429 and 5xx are
 * worth a retry; every other 4xx is an answer, and a retry cannot change an
 * answer. A 2xx only counts as delivered when the body confirms `sent` — a
 * write the server did not confirm as a share is not evidence the note was
 * shared. Errors carry codes only; no body text is read into a message
 * (invariant 6).
 */
import type { RefusalReason } from "./outbox";
import type { NotePutBody } from "./payload";

/** The authenticated fetch, injected so the transport is node-testable. */
export type Fetcher = (path: string, init?: RequestInit) => Promise<Response>;

export type PutResult =
  | { kind: "delivered" }
  | { kind: "transient"; retryAfterMs: number | null }
  | { kind: "consent" }
  | { kind: "refused"; reason: RefusalReason };

/** The share purpose a send is checked against (notes.SHARE_SCOPE). */
const SHARE_PREFIX = "share:";

export function notePath(serverVisitId: string): string {
  return `/v1/visits/${encodeURIComponent(serverVisitId)}/note`;
}

async function bodyOf(response: Response): Promise<Record<string, unknown>> {
  try {
    const parsed: unknown = await response.json();
    return typeof parsed === "object" && parsed !== null ? (parsed as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

function retryAfterMs(response: Response): number | null {
  const raw = response.headers?.get?.("retry-after") ?? null;
  if (raw === null) {
    return null;
  }
  const seconds = Number.parseInt(raw, 10);
  return Number.isFinite(seconds) && seconds >= 0 ? seconds * 1_000 : null;
}

/** A refusal → the one verdict that lets the screen say a true sentence. */
export function classifyRefusal(
  status: number,
  error: unknown,
  scope: unknown,
  retryAfter: number | null,
): PutResult {
  if (status === 408 || status === 429 || status >= 500) {
    return { kind: "transient", retryAfterMs: retryAfter };
  }
  if (status === 403 && error === "consent_required") {
    if (typeof scope === "string" && scope.startsWith(SHARE_PREFIX)) {
      return { kind: "consent" };
    }
    return { kind: "refused", reason: scope === "core" ? "core_consent" : "rejected" };
  }
  if (status === 401) {
    return { kind: "refused", reason: "session" };
  }
  if (status === 404) {
    return { kind: "refused", reason: "not_found" };
  }
  if (status === 400 || status === 409 || status === 422) {
    return { kind: "refused", reason: "invalid" };
  }
  return { kind: "refused", reason: "rejected" };
}

/** An auth-layer throw that means "no session here" rather than "no network". */
function isSessionError(error: unknown): boolean {
  if (typeof error !== "object" || error === null) {
    return false;
  }
  const kind = (error as { kind?: unknown }).kind;
  return kind === "session" || kind === "unconfigured";
}

/** Deliver one note body. Never throws. */
export async function putNote(
  fetcher: Fetcher,
  serverVisitId: string,
  body: NotePutBody,
): Promise<PutResult> {
  let response: Response;
  try {
    response = await fetcher(notePath(serverVisitId), {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (error) {
    return isSessionError(error)
      ? { kind: "refused", reason: "session" }
      : { kind: "transient", retryAfterMs: null };
  }
  const parsed = await bodyOf(response);
  if (response.ok) {
    // Only the server's own word that a share now exists is a delivery.
    return parsed.status === "sent"
      ? { kind: "delivered" }
      : { kind: "transient", retryAfterMs: null };
  }
  return classifyRefusal(response.status, parsed.error, parsed.scope, retryAfterMs(response));
}

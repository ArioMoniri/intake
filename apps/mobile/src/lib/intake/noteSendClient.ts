/**
 * INT-510 — the send's transport: ./noteSend's ports bound to the real API.
 *
 * Loaded by the session through a lazy `import()` only, because the records
 * resolver it reuses reads picked files through expo-file-system; the session
 * stays node-importable (the INT-142 pattern).
 *
 * Two calls, in this order, and nothing else:
 *
 *   1. `ensureServerVisit(visit, { create: true })` — the server's id for the
 *      local visit, created on the INT-134 taxonomy path when missing. The one
 *      resolver the records screen already uses, so a visit a document was
 *      uploaded to and the visit a note is sent for are the same server row;
 *   2. `PUT /v1/visits/{server id}/note` with the body ./noteSend built.
 *
 * The PUT is bounded (`PUT_TIMEOUT_MS`): the note is frozen while its send is
 * in flight, so a request that never answers must become a queued send rather
 * than a note the patient can no longer edit. Errors come back as the port's
 * typed results, never as narrative, and nothing here logs (invariant 6).
 */
import { AuthApiError, authedFetch } from "@/lib/auth/api";
import { RecordsApiError, ensureServerVisit, type VisitIdentity } from "@/lib/records/api";

import {
  deliverNote,
  type DeliverInput,
  type NotePutBody,
  type NoteSendPorts,
  type PutResult,
  type ResolveResult,
  type SendOutcome,
} from "./noteSend";

/** How long one PUT may take before the send is queued instead. */
export const PUT_TIMEOUT_MS = 30_000;

async function resolve(visit: VisitIdentity): Promise<ResolveResult> {
  try {
    const id = await ensureServerVisit(visit, { create: true });
    return id === null ? "refused" : { id };
  } catch (error) {
    if (error instanceof RecordsApiError) {
      if (error.kind === "network") {
        return "unreachable";
      }
      if (error.kind === "session") {
        return "session";
      }
      if (error.kind === "consent") {
        return "consent";
      }
    }
    return "refused";
  }
}

async function readAnswer(response: Response): Promise<PutResult> {
  let body: Record<string, unknown> = {};
  try {
    body = (await response.json()) as Record<string, unknown>;
  } catch {
    body = {};
  }
  return {
    status: response.status,
    error: typeof body.error === "string" ? body.error : "",
    noteStatus: response.ok && typeof body.status === "string" ? body.status : null,
  };
}

async function put(serverVisitId: string, body: NotePutBody): Promise<PutResult> {
  const abort = new AbortController();
  const timer = setTimeout(() => abort.abort(), PUT_TIMEOUT_MS);
  try {
    const response = await authedFetch(`/v1/visits/${encodeURIComponent(serverVisitId)}/note`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: abort.signal,
    });
    return await readAnswer(response);
  } catch (error) {
    if (error instanceof AuthApiError && error.kind === "session") {
      return "session";
    }
    // a dropped connection, an abort on the bound, no reachable base: not now
    return "unreachable";
  } finally {
    clearTimeout(timer);
  }
}

/** The ports for one local visit. */
export function noteSendPorts(visit: VisitIdentity): NoteSendPorts {
  return {
    resolveServerVisit: () => resolve(visit),
    putNote: put,
  };
}

/**
 * Send one visit's note. A note whose visit the session no longer lists has no
 * server row to address, so it is refused without a request.
 */
export async function deliverVisitNote(
  input: DeliverInput & { visit: VisitIdentity | null },
): Promise<SendOutcome> {
  if (input.visit === null) {
    return { kind: "refused", reason: "failed", serverVisitId: null };
  }
  return deliverNote(input, noteSendPorts(input.visit));
}

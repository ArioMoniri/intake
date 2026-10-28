/**
 * INT-587 — one delivery attempt for one queued note.
 *
 * The order of the steps is the disclosure policy:
 *
 * 1. **A share consent withdrawn on this phone stops everything.** The item is
 *    parked for the patient and nothing reaches the network.
 * 2. **The consent queue is flushed first.** The patient's share grant travels
 *    through the consent outbox (lib/consent/store); `write_note` checks the
 *    share scope in the same transaction that creates the share, so a note
 *    sent ahead of its grant would be refused, and a note sent ahead of a
 *    WITHDRAWAL would be shared against the patient's last word. Nothing is
 *    sent while any consent change is still on the phone.
 * 3. **The server visit is found (or created) once** and remembered, so a
 *    retry does not look it up again and the Doctor Link routes have the id
 *    to address.
 * 4. **The note is PUT**, and the server's answer settles the item.
 *
 * Every dependency is injected (./native wires the real ones), every throw is a
 * transient failure, and the attempt itself never throws — the outbox is a
 * place a note waits, not a place it can be lost.
 */
import type { ShareStanding } from "../../consent/ledger";
import { settle, type DeliveryItem, type RefusalReason, type VisitIdentity } from "./outbox";
import type { NotePutBody } from "./payload";
import type { PutResult } from "./transport";

export type ResolveResult =
  | { kind: "resolved"; serverVisitId: string }
  | { kind: "transient" }
  | { kind: "refused"; reason: RefusalReason };

export interface DeliveryDeps {
  shareStanding(): ShareStanding;
  /** Push every queued consent change; true once none is left on the phone. */
  flushConsent(): Promise<boolean>;
  resolveServerVisit(visit: VisitIdentity, visitId: string): Promise<ResolveResult>;
  putNote(serverVisitId: string, body: NotePutBody): Promise<PutResult>;
}

const RETRY = { kind: "transient", retryAfterMs: null } as const;

/**
 * A failure of the server-visit lookup (records `ensureServerVisit`, whose
 * matching rule — hospital, department, date — the note shares with the
 * documents, so both hang off the same server visit) as a verdict. Read by
 * shape, so this module imports no native code: `{ kind, status }`.
 */
export function classifyVisitError(error: unknown): ResolveResult {
  if (typeof error !== "object" || error === null) {
    return { kind: "transient" };
  }
  const { kind, status } = error as { kind?: unknown; status?: unknown };
  switch (kind) {
    case "network":
      return { kind: "transient" };
    case "session":
      return { kind: "refused", reason: "session" };
    case "core_consent":
      return { kind: "refused", reason: "core_consent" };
    case "not_found":
      return { kind: "refused", reason: "not_found" };
    case "generic": {
      const answered =
        typeof status === "number" &&
        status >= 400 &&
        status < 500 &&
        status !== 408 &&
        status !== 429;
      return answered ? { kind: "refused", reason: "invalid" } : { kind: "transient" };
    }
    case undefined:
      return { kind: "transient" };
    default:
      return { kind: "refused", reason: "rejected" };
  }
}

export async function attemptDelivery(
  item: DeliveryItem,
  deps: DeliveryDeps,
  now: number,
): Promise<DeliveryItem> {
  if (item.stage !== "queued") {
    return item;
  }
  if (item.body === null) {
    return settle(item, { kind: "refused", reason: "invalid", serverVisitId: null }, now);
  }
  if (deps.shareStanding() === "withdrawn") {
    return { ...item, stage: "awaiting_consent" };
  }

  try {
    if (!(await deps.flushConsent())) {
      return settle(item, { ...RETRY, serverVisitId: null }, now);
    }
  } catch {
    return settle(item, { ...RETRY, serverVisitId: null }, now);
  }

  let serverVisitId = item.serverVisitId;
  if (serverVisitId === null) {
    let resolved: ResolveResult;
    try {
      resolved = await deps.resolveServerVisit(item.visit, item.visitId);
    } catch {
      resolved = { kind: "transient" };
    }
    if (resolved.kind === "transient") {
      return settle(item, { ...RETRY, serverVisitId: null }, now);
    }
    if (resolved.kind === "refused") {
      return settle(item, { kind: "refused", reason: resolved.reason, serverVisitId: null }, now);
    }
    serverVisitId = resolved.serverVisitId;
  }

  let result: PutResult;
  try {
    result = await deps.putNote(serverVisitId, item.body);
  } catch {
    result = RETRY;
  }
  switch (result.kind) {
    case "delivered":
      return settle(item, { kind: "delivered", serverVisitId }, now);
    case "transient":
      return settle(item, { ...result, serverVisitId }, now);
    case "consent":
      return settle(item, { kind: "consent", serverVisitId }, now);
    case "refused":
      return settle(item, { kind: "refused", reason: result.reason, serverVisitId }, now);
  }
}

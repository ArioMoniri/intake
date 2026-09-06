/**
 * INT-142 — offline-tolerant sync (acceptance clauses 2 + 3).
 *
 * Ties the encrypted store, the conflict rule and a transport together into
 * one honest pass, on the consent-store precedent (src/lib/consent/store.ts):
 * a network failure is not an error, it is "offline" — the local draft stays
 * queued, encrypted, and the next pass tries again. The transport is injected
 * so the airplane-mode journey is provable without a device or a network
 * (e2e/offline.spec.ts).
 *
 * The transport speaks to INT-197's /v1/visits/{id}/note when it exists and
 * is reachable; today no note-sync client ships (the server note carries no
 * version and the raw answer-draft has no server home yet — INT-137 evidence),
 * so a production transport reports unreachable and the draft stays local and
 * sealed. That is the fail-closed state, not a gap: the CONFLICT RULE this
 * issue owns is complete and tested regardless.
 */
import { loadDraft, persistConflictCopy, persistDraft, type DraftBackend } from "./draftStore";
import { reconcile, type DraftRecord, type SyncOutcome } from "./reconcile";

export interface DraftTransport {
  /** Fetch the server copy for a visit, or null if the server has none.
   * Throws (like `fetch`) when the network is unreachable. */
  pull(visitId: string): Promise<DraftRecord | null>;
  /** Push the local draft; returns the server-acknowledged record (its
   * revision advanced, dirty cleared). Throws when unreachable. */
  push(record: DraftRecord): Promise<DraftRecord>;
}

export interface SyncResult {
  /** "offline" is added to the rule's own outcomes: the pass could not reach
   * the server and the draft stayed queued. */
  outcome: SyncOutcome | "offline";
  winner: DraftRecord | null;
  loser: DraftRecord | null;
}

const offline: SyncResult = { outcome: "offline", winner: null, loser: null };

/**
 * Reconcile one visit's draft with the server and apply the result to the
 * encrypted store. Never throws for a network failure — it returns "offline"
 * and leaves the local draft exactly as it was.
 */
export async function syncVisit(
  backend: DraftBackend,
  transport: DraftTransport,
  visitId: string,
): Promise<SyncResult> {
  const local = await loadDraft(backend, visitId);

  let remote: DraftRecord | null;
  try {
    remote = await transport.pull(visitId);
  } catch {
    return offline;
  }

  if (local === null && remote === null) {
    return { outcome: "in-sync", winner: null, loser: null };
  }

  const resolution = reconcile(local, remote);

  switch (resolution.outcome) {
    case "in-sync":
      return { outcome: "in-sync", winner: resolution.winner, loser: null };

    case "take-remote": {
      const adopted: DraftRecord = { ...resolution.winner, dirty: false };
      await persistDraft(backend, adopted);
      return { outcome: "take-remote", winner: adopted, loser: null };
    }

    case "push": {
      let acked: DraftRecord;
      try {
        acked = await transport.push(resolution.winner);
      } catch {
        return offline;
      }
      await persistDraft(backend, acked);
      return { outcome: "push", winner: acked, loser: null };
    }

    case "conflict": {
      // No silent loss: the loser is preserved as a conflict copy the patient
      // can review, and the winner is rebased onto the remote revision so the
      // divergence is resolved and a later pass fast-forwards rather than
      // conflicting forever.
      await persistConflictCopy(backend, resolution.loser as DraftRecord);
      const rebased: DraftRecord = {
        ...resolution.winner,
        revision: (remote as DraftRecord).revision,
        dirty: resolution.winner === local,
      };
      await persistDraft(backend, rebased);
      return { outcome: "conflict", winner: rebased, loser: resolution.loser };
    }
  }
}

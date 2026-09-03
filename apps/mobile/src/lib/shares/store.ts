/**
 * INT-139 — the working copy behind *Paylaşımlarınız*, on the INT-140 store
 * pattern: a module singleton read through `useSyncExternalStore`, in memory
 * only.
 *
 * The register of record is the server, and here that is not a stylistic
 * preference — it is what the acceptance's revocation clause rests on. A
 * grant the server has stopped is stopped; a copy of it on this phone is at
 * best a photograph. So:
 *
 * - **nothing is written to disk.** There is no cache for a revocation to
 *   invalidate and no stale list that can outlive one;
 * - **there is no optimistic write.** A revoke shows as done only once the
 *   row comes back saying so. Everywhere else in this app an optimistic
 *   switch is the kinder choice; here it is the dangerous one, because a
 *   patient told their share is stopped stops checking;
 * - **a revoke costs exactly one round trip.** The route answers with the
 *   authoritative row, so re-listing afterwards would add a second network
 *   wait between the patient's tap and the screen agreeing with the record —
 *   latency this client would be adding to a clause about latency;
 * - **an unreachable server is not an empty list.** "Nobody has access" and
 *   "we could not ask" are different sentences and the screen prints the
 *   second one.
 */
import { useSyncExternalStore } from "react";

import { fetchAccessLog, fetchShareLinks, revokeShareLink } from "./api";
import type { AccessEntry, ShareLink } from "./links";

export interface ShareCentreState {
  /** Every grant over this visit's note, newest end first. */
  links: ShareLink[];
  /** The patient's access log for the same note, newest first. */
  log: AccessEntry[];
  /** False until the server has confirmed what is shown. */
  loaded: boolean;
  /** The last read did not reach the server; nothing here is a claim. */
  unreachable: boolean;
  /** The last revocation did not land. The share may still be open. */
  unsent: boolean;
}

const FRESH: ShareCentreState = {
  links: [],
  log: [],
  loaded: false,
  unreachable: false,
  unsent: false,
};

let state: ShareCentreState = FRESH;
let heldVisit: string | null = null;
const listeners = new Set<() => void>();

function commit(next: ShareCentreState): void {
  state = next;
  for (const listener of listeners) {
    listener();
  }
}

export function sharesSnapshot(): ShareCentreState {
  return state;
}

export function subscribeToShares(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useShareCentre(): ShareCentreState {
  return useSyncExternalStore(subscribeToShares, sharesSnapshot, sharesSnapshot);
}

/** Drop the working copy — another visit's grants are not this one's. */
export function resetShares(): void {
  heldVisit = null;
  commit(FRESH);
}

/** Newest end first, so a grant about to finish is not buried. */
function ordered(links: readonly ShareLink[]): ShareLink[] {
  return [...links].sort((a, b) => b.expiresAt.localeCompare(a.expiresAt));
}

/**
 * Read the whole centre for one visit: the grants and the log, in one pass,
 * so the screen never shows a log that describes grants it is not showing.
 */
export async function loadShareCentre(visitId: string): Promise<void> {
  if (heldVisit !== visitId) {
    heldVisit = visitId;
    commit(FRESH);
  }
  const [links, log] = await Promise.all([fetchShareLinks(visitId), fetchAccessLog(visitId)]);
  if (links === null || log === null) {
    commit({ ...state, links: [], log: [], loaded: false, unreachable: true });
    return;
  }
  commit({
    ...state,
    links: ordered(links),
    log: [...log].sort((a, b) => b.seq - a.seq),
    loaded: true,
    unreachable: false,
  });
}

/**
 * Stop one grant.
 *
 * Declared under `core` alone on the server (INT-150 §6), and this function
 * mirrors that: it takes a visit and a grant, and consults no consent value,
 * so a withdrawal of `share:previsit_note` cannot reach the decision to call
 * it. A refusal register a refusal can lock is not a refusal register.
 */
export async function revokeShare(visitId: string, linkId: string): Promise<void> {
  const row = await revokeShareLink(visitId, linkId);
  if (row === null) {
    commit({ ...state, unsent: true });
    return;
  }
  commit({
    ...state,
    links: ordered(state.links.map((link) => (link.id === row.id ? row : link))),
    unsent: false,
  });
}

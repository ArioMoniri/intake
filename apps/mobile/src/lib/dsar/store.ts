/**
 * INT-140 — the working copy behind *Verileriniz*, on the INT-141 store
 * pattern: a module singleton read through `useSyncExternalStore`, in memory
 * only.
 *
 * The register of record is the server. A DSAR request is an obligation the
 * controller owes, and an obligation that lives on one phone is not one — so
 * nothing here is written to disk, and nothing is shown as filed that the
 * server did not confirm.
 *
 * That last rule is why there are no optimistic writes. Everywhere else in
 * this app an optimistic switch is the kinder choice; here it is the
 * dangerous one. A patient who is told their erasure is scheduled stops
 * asking, and a filing that never left the phone would produce exactly that
 * silence. A write either lands or the state is unchanged and `unsent` says
 * so.
 */
import { useSyncExternalStore } from "react";

import {
  fetchDsarRequests,
  fileErasureWithStepUp,
  fileExportRequest,
  withdrawErasureRequest,
} from "./api";
import type { DsarRequest } from "./requests";

export interface DsarState {
  /** The patient's own m.13 clocks, newest first. */
  requests: DsarRequest[];
  /** False until the server has confirmed what is shown. */
  loaded: boolean;
  /** The last filing or withdrawal did not reach the controller. */
  unsent: boolean;
  /** The most recent erasure filing closed at least one live share. */
  sharesCancelled: boolean;
  /**
   * INT-582 (D36): the last erasure needed the patient's passkey and the
   * step-up was refused — the screen names the manual path (a person reviews
   * it, KVKK m.11(1)(g)) rather than only "not sent".
   */
  stepUpRefused: boolean;
}

const FRESH: DsarState = {
  requests: [],
  loaded: false,
  unsent: false,
  sharesCancelled: false,
  stepUpRefused: false,
};

let state: DsarState = FRESH;
let seededAccount: string | null = null;
const listeners = new Set<() => void>();

function commit(next: DsarState): void {
  state = next;
  for (const listener of listeners) {
    listener();
  }
}

export function dsarSnapshot(): DsarState {
  return state;
}

export function subscribeToDsar(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useDsarRequests(): DsarState {
  return useSyncExternalStore(subscribeToDsar, dsarSnapshot, dsarSnapshot);
}

/** Drop the working copy — another patient's clocks are not ours. */
export function resetDsar(): void {
  seededAccount = null;
  commit(FRESH);
}

/** Newest first, with a re-read of one row replacing it rather than doubling it. */
function merged(requests: readonly DsarRequest[], next: DsarRequest): DsarRequest[] {
  return [next, ...requests.filter((request) => request.id !== next.id)].sort((a, b) =>
    b.receivedAt.localeCompare(a.receivedAt),
  );
}

/**
 * Load one account's tracker. Keyed like the consent ledger's seeding: a
 * different account clears the copy BEFORE the server answers, so the
 * previous patient's requests are never on screen even for a frame.
 */
export async function loadDsarRequests(accountId: string): Promise<void> {
  if (seededAccount !== accountId) {
    seededAccount = accountId;
    commit(FRESH);
  }
  const server = await fetchDsarRequests();
  if (server === null) {
    return; // unreachable: keep showing what we have, claim nothing
  }
  commit({ ...state, requests: server, loaded: true, unsent: false });
}

export async function fileExport(): Promise<void> {
  const filed = await fileExportRequest();
  if (filed === null) {
    commit({ ...state, unsent: true });
    return;
  }
  commit({ ...state, requests: merged(state.requests, filed), unsent: false });
}

export async function fileErasure(): Promise<void> {
  const outcome = await fileErasureWithStepUp();
  if (outcome.kind === "cancelled") {
    // the patient closed the passkey sheet: nothing was filed, nothing failed
    commit({ ...state, unsent: false, stepUpRefused: false });
    return;
  }
  if (outcome.kind !== "filed") {
    commit({ ...state, unsent: true, stepUpRefused: outcome.kind === "step_up_refused" });
    return;
  }
  commit({
    ...state,
    requests: merged(state.requests, outcome.filing.request),
    unsent: false,
    stepUpRefused: false,
    sharesCancelled: outcome.filing.sharesCancelled,
  });
}

export async function withdrawErasure(id: string): Promise<void> {
  const withdrawn = await withdrawErasureRequest(id);
  if (withdrawn === null) {
    // The erasure still stands. Leaving it on screen is the honest state:
    // a withdrawal the server refused is not a withdrawal.
    commit({ ...state, unsent: true });
    return;
  }
  commit({ ...state, requests: merged(state.requests, withdrawn), unsent: false });
}

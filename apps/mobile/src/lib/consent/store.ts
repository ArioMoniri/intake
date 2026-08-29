/**
 * Module-level consent store (INT-132), following the flow.ts precedent:
 * in-memory ONLY. The consent ledger of record is the server (invariant 4);
 * what lives here is the session's working copy plus the honest offline
 * queue — never a disk write, because persisting consent state on-device
 * would be a new category of personal data (a stop-and-ask decision).
 */
import { useSyncExternalStore } from "react";

import { fetchConsentSnapshot, pushConsentOp } from "./api";
import {
  applyServerScopes,
  applyTexts,
  freshLedger,
  grant,
  seedFromSession,
  shiftQueue,
  withdraw,
  type LedgerState,
} from "./ledger";
import type { PurposeId } from "./purposes";

interface SessionConsentSeed {
  core: boolean;
  voice: boolean;
  wellbeing: boolean;
  documents: boolean;
  health: boolean;
}

let state: LedgerState = freshLedger();
let seededAccount: string | null = null;
const listeners = new Set<() => void>();

function commit(next: LedgerState): void {
  if (next === state) {
    return;
  }
  state = next;
  for (const listener of listeners) {
    listener();
  }
}

export function ledgerSnapshot(): LedgerState {
  return state;
}

export function subscribeToLedger(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** React binding for the screens. */
export function useConsentLedger(): LedgerState {
  return useSyncExternalStore(subscribeToLedger, ledgerSnapshot, ledgerSnapshot);
}

/**
 * Seed once per signed-in account: dev fixtures arrive as unbound grants
 * (server dev-seed semantics), an otp account starts fresh. Then ask the
 * server for the authoritative snapshot — if it is reachable.
 */
export function seedLedgerForAccount(accountId: string, consents: SessionConsentSeed | null): void {
  if (seededAccount === accountId) {
    return;
  }
  seededAccount = accountId;
  commit(consents !== null ? seedFromSession(consents) : freshLedger());
  void refreshLedgerFromServer();
}

/** Sign-out hygiene: drop the working copy with the session. */
export function resetLedger(): void {
  seededAccount = null;
  commit(freshLedger());
}

/**
 * Pull the loader payload (scopes + versioned texts) and reconcile. A null
 * snapshot means the dev tier has no consent routes or no connectivity —
 * the local state stands and the queue waits.
 */
export async function refreshLedgerFromServer(): Promise<void> {
  const snapshot = await fetchConsentSnapshot();
  if (snapshot === null) {
    return;
  }
  commit(applyServerScopes(applyTexts(state, snapshot.texts), snapshot.scopes));
  await flushConsentQueue();
}

/**
 * Honest queue semantics: ops flush strictly in order; the first failure
 * stops the pass and everything after it stays queued for the next attempt
 * (next screen visit or next local change). The queue is in-memory — after
 * an app restart the server snapshot is the truth and unsynced local flips
 * are gone, which is stated in the İzinleriniz queue notice.
 */
export async function flushConsentQueue(): Promise<void> {
  while (state.queue.length > 0) {
    const next = state.queue[0];
    if (!(await pushConsentOp(next))) {
      return;
    }
    commit(shiftQueue(state, 1));
  }
}

/** Grant locally (instant) and start a flush. Returns the flipped scopes so
 * the caller can mirror them into the session gate in the same handler. */
export function grantLocal(id: PurposeId, atIso?: string): readonly PurposeId[] {
  const result = grant(state, id, atIso ?? new Date().toISOString());
  commit(result.state);
  if (result.flipped.length > 0) {
    void flushConsentQueue();
  }
  return result.flipped;
}

/** Withdraw locally (instant, cascading) and start a flush. */
export function withdrawLocal(id: PurposeId, atIso?: string): readonly PurposeId[] {
  const result = withdraw(state, id, atIso ?? new Date().toISOString());
  commit(result.state);
  if (result.flipped.length > 0) {
    void flushConsentQueue();
  }
  return result.flipped;
}

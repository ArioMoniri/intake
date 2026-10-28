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

/**
 * Where the patient's own consent changes stand with the server (INT-397).
 *
 * - `clear`: nothing waits.
 * - `sending`: a change made on this device is on its way.
 * - `held`: a push did not land, so the change waits in the queue. This is
 *   what `consent.queue.note` says ("applied on this device; they will reach
 *   the server once a connection is available").
 *
 * The note is shown while the queue holds anything, so it is also on screen
 * while each change is in flight, and on every visit while one waits. Only a
 * move into `held` is announced. A retry that fails again stays `held` and is
 * not a new move; a new change goes through `sending` again, so it is one.
 */
export type ConsentOutbox = "clear" | "sending" | "held";

let state: LedgerState = freshLedger();
let outbox: ConsentOutbox = "clear";
let seededAccount: string | null = null;
const listeners = new Set<() => void>();

function notify(): void {
  for (const listener of listeners) {
    listener();
  }
}

function commit(next: LedgerState): void {
  if (next === state) {
    return;
  }
  state = next;
  notify();
}

function moveOutbox(next: ConsentOutbox): void {
  if (next === outbox) {
    return;
  }
  outbox = next;
  notify();
}

export function ledgerSnapshot(): LedgerState {
  return state;
}

export function consentOutbox(): ConsentOutbox {
  return outbox;
}

/**
 * Whether the working copy is this account's (INT-537). An unseeded ledger is
 * a fresh one, so a screen that refuses on it would refuse an account that
 * holds the consent. Seeding commits a new state, so a subscribed screen
 * re-renders the moment this turns true.
 */
export function ledgerSeededFor(accountId: string): boolean {
  return seededAccount === accountId;
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

/** React binding for the queue note (INT-397). */
export function useConsentOutbox(): ConsentOutbox {
  return useSyncExternalStore(subscribeToLedger, consentOutbox, consentOutbox);
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
  moveOutbox("clear"); // another account's waiting changes are not this one's
  void refreshLedgerFromServer();
}

/** Sign-out hygiene: drop the working copy with the session. */
export function resetLedger(): void {
  seededAccount = null;
  commit(freshLedger());
  moveOutbox("clear");
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
 *
 * A push that does not land leaves the outbox `held`; an emptied queue leaves
 * it `clear` (INT-397).
 */
export async function flushConsentQueue(): Promise<void> {
  while (state.queue.length > 0) {
    const next = state.queue[0];
    if (!(await pushConsentOp(next))) {
      moveOutbox("held");
      return;
    }
    commit(shiftQueue(state, 1));
  }
  moveOutbox("clear");
}

/** Grant locally (instant) and start a flush. Returns the flipped scopes so
 * the caller can mirror them into the session gate in the same handler. */
export function grantLocal(id: PurposeId, atIso?: string): readonly PurposeId[] {
  const result = grant(state, id, atIso ?? new Date().toISOString());
  commit(result.state);
  if (result.flipped.length > 0) {
    moveOutbox("sending");
    void flushConsentQueue();
  }
  return result.flipped;
}

/** Withdraw locally (instant, cascading) and start a flush. */
export function withdrawLocal(id: PurposeId, atIso?: string): readonly PurposeId[] {
  const result = withdraw(state, id, atIso ?? new Date().toISOString());
  commit(result.state);
  if (result.flipped.length > 0) {
    moveOutbox("sending");
    void flushConsentQueue();
  }
  return result.flipped;
}

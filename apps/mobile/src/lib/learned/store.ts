/**
 * INT-140 — the working copy behind *Hakkımda öğrendikleri*, on the INT-141
 * store pattern: a module singleton read through `useSyncExternalStore`, in
 * memory only.
 *
 * One rule governs every write: **a record fact is not removed from the
 * screen until the record has removed it, and a scope is not shown turned
 * until the record has turned it.** Optimism is the wrong default here in a
 * way it is not for a reminder window — a patient told a fact is deleted
 * stops asking, so an optimistic delete that failed is a lie the patient acts
 * on. A write that does not land changes nothing and `unsaved` says so.
 *
 * A device-held fact is the mirror image. It came out of this device's own
 * session (INT-247) and exists nowhere else, so removing it here removes it,
 * and no server is asked about a fact no server holds.
 */
import { useSyncExternalStore } from "react";

import type { CarriedFact } from "../intake/carriedFacts";
import { fetchLearnedFacts, forgetRecordFact, pushFactShared } from "./api";
import { ledgerFactFromCarried, withSharedFact, withoutFact, type LedgerFact } from "./facts";

export interface LearnedState {
  facts: LedgerFact[];
  /** False until the record's own facts have been read. */
  loaded: boolean;
  /** The last change did not reach the record; the screen says so. */
  unsaved: boolean;
}

const FRESH: LearnedState = { facts: [], loaded: false, unsaved: false };

let state: LearnedState = FRESH;
let seededAccount: string | null = null;
const listeners = new Set<() => void>();

function commit(next: LearnedState): void {
  state = next;
  for (const listener of listeners) {
    listener();
  }
}

export function learnedSnapshot(): LearnedState {
  return state;
}

export function subscribeToLearned(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useLearnedLedger(): LearnedState {
  return useSyncExternalStore(subscribeToLearned, learnedSnapshot, learnedSnapshot);
}

/** Drop the working copy — another patient's ledger is not ours. */
export function resetLearnedLedger(): void {
  seededAccount = null;
  commit(FRESH);
}

/**
 * Seed the device-held half for one account. Keyed like the consent ledger's
 * seeding, and for the same reason: a different account clears the copy
 * before anything else happens, so the previous patient's facts are never on
 * screen even for a frame.
 */
export function seedLearnedLedger(accountId: string, carried: readonly CarriedFact[]): void {
  if (seededAccount === accountId) {
    return;
  }
  seededAccount = accountId;
  commit({ ...FRESH, facts: carried.map(ledgerFactFromCarried) });
}

/** Read the record's own facts, keeping the device-held ones beside them. */
export async function loadLearnedLedger(): Promise<void> {
  const server = await fetchLearnedFacts();
  if (server === null) {
    return; // unreachable: keep showing what we have, claim nothing
  }
  const device = state.facts.filter((fact) => fact.origin === "device");
  commit({ facts: [...device, ...server], loaded: true, unsaved: false });
}

function find(id: string): LedgerFact | undefined {
  return state.facts.find((fact) => fact.id === id);
}

/** Turn one fact's share scope, once the record has turned it. */
export async function setFactShared(id: string, shared: boolean): Promise<void> {
  const fact = find(id);
  if (fact === undefined || fact.origin === "device") {
    // A device-held fact carries no share scope to turn (files/09 §3 scopes a
    // field of the overlay, and this fact is not in one).
    return;
  }
  if (!(await pushFactShared(id, shared))) {
    commit({ ...state, unsaved: true });
    return;
  }
  commit({ ...state, facts: withSharedFact(state.facts, id, shared), unsaved: false });
}

/** Delete one fact. A record fact goes only when the record lets it go. */
export async function forgetFact(id: string): Promise<void> {
  const fact = find(id);
  if (fact === undefined) {
    return;
  }
  if (fact.origin === "device") {
    commit({ ...state, facts: withoutFact(state.facts, id) });
    return;
  }
  if (!(await forgetRecordFact(id))) {
    commit({ ...state, unsaved: true });
    return;
  }
  commit({ ...state, facts: withoutFact(state.facts, id), unsaved: false });
}

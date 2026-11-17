/**
 * INT-141 — module-level notification-preference store, following the
 * consent/store.ts precedent: in-memory ONLY.
 *
 * The register of record is the server (it is what the scheduler reads, and
 * it is what has to survive a restart); what lives here is this session's
 * working copy. Nothing is written to disk — a device-local copy of a
 * preference would be a second source of truth and a second thing to erase.
 */
import { useSyncExternalStore } from "react";

import { fetchNotificationPrefs, pushNotificationPrefs } from "./api";
import { DEFAULT_PREFS, validatePrefs, type NotificationPrefs } from "./preferences";

/**
 * Where the patient's last change stands with the server (INT-397).
 *
 * - `idle`: nothing is waiting; the shown state is the server's, or has not
 *   been changed here.
 * - `saving`: a change is on its way.
 * - `failed`: the server did not take it; the change stays shown, and the
 *   screen says it is not saved yet.
 *
 * INT-141 held one flag for the last two, so the screen's "not saved yet"
 * line could not be announced without saying "Hata" on every toggle
 * (INT-362). Only `failed` is announced.
 */
export type SaveState = "idle" | "saving" | "failed";

export interface PrefsState {
  /** What the screen renders. */
  prefs: NotificationPrefs;
  /** False until a server read has confirmed the shown state. */
  loaded: boolean;
  /** Whether the last change is on its way, did not land, or nothing waits. */
  save: SaveState;
}

const FRESH: PrefsState = { prefs: DEFAULT_PREFS, loaded: false, save: "idle" };

let state: PrefsState = FRESH;
let seededAccount: string | null = null;
const listeners = new Set<() => void>();

function commit(next: PrefsState): void {
  if (next === state) {
    return;
  }
  state = next;
  for (const listener of listeners) {
    listener();
  }
}

export function prefsSnapshot(): PrefsState {
  return state;
}

export function subscribeToPrefs(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useNotificationPrefs(): PrefsState {
  return useSyncExternalStore(subscribeToPrefs, prefsSnapshot, prefsSnapshot);
}

/** Drop the working copy — a different account's state is not ours. */
export function resetNotificationPrefs(): void {
  seededAccount = null;
  commit(FRESH);
}

/**
 * Load for one account, keyed like the consent ledger's seeding: a different
 * account clears the working copy BEFORE the server answers, so the previous
 * patient's setting is never on screen even for a frame.
 */
export async function loadNotificationPrefs(accountId: string): Promise<void> {
  if (seededAccount !== accountId) {
    seededAccount = accountId;
    commit(FRESH);
  }
  const server = await fetchNotificationPrefs();
  if (server === null) {
    return; // unreachable: keep showing what we have, claim nothing
  }
  commit({ prefs: server, loaded: true, save: "idle" });
}

/**
 * Optimistic within the session, honest about the server: the switch moves
 * at once (a refusal the UI delays is a refusal the patient repeats). The
 * change is `saving` until the server answers, and `failed` if it does not
 * take it, with the patient's choice still shown.
 */
export async function saveNotificationPrefs(next: NotificationPrefs): Promise<void> {
  if (!validatePrefs(next).ok) {
    return; // the screen only produces valid combinations; refuse the rest
  }
  commit({ prefs: next, loaded: state.loaded, save: "saving" });
  const confirmed = await pushNotificationPrefs(next);
  if (confirmed === null) {
    commit({ prefs: next, loaded: state.loaded, save: "failed" });
    return;
  }
  commit({ prefs: confirmed, loaded: true, save: "idle" });
}

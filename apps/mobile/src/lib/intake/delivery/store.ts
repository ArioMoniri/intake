/**
 * INT-587 — the note-sync client as the app runs it: one outbox per signed-in
 * account, on the consent/share-centre store pattern (a module singleton read
 * through `useSyncExternalStore`), persisted sealed through ./persistence.
 *
 * What it promises, and where each promise is kept:
 *
 * - **offline send queues and survives a restart.** An item is persisted the
 *   moment it is queued and after every change; `startDelivery` restores this
 *   account's items from disk alone (store.test.ts kills the memory to prove
 *   it) and runs whatever is due.
 * - **it never drops a queued note.** Nothing here removes a queued item.
 *   Only the patient's own "take it back to a draft" removes an item, and only
 *   one nothing can have reached (`reopenable`); sign-out and the kiosk wipe
 *   end the session's data by design (./persistence).
 * - **retries with backoff.** One timer, set to the earliest queued item's
 *   wait; the app's foreground event (./native) and every patient action also
 *   run a pass.
 * - **a 4xx is surfaced and not retried forever.** A refused item is never
 *   due again until the patient retries it (./outbox).
 * - **no share without the grant — this note's grant.** An item is queued,
 *   and a parked item released, only against a share-scope receipt given for
 *   THAT note, which only a grant against a loaded share text produces
 *   (lib/consent/ledger `grantShare`). The moment the share consent is
 *   withdrawn on this phone — directly, through core, or from any future
 *   screen — every unsent note is parked and its grant unbound, in memory at
 *   once and then on disk, so neither a later grant for another note nor a
 *   restart can send it (`watchConsent`; INT-587 legal review B1).
 *
 * Nothing here logs, and nothing here reaches the network except through the
 * injected dependencies (invariant 6; ./native wires the real ones).
 */
import { useSyncExternalStore } from "react";

import { SHARE_SCOPE, type ShareGrantReceipt } from "../../consent/ledger";
import { attemptDelivery, type DeliveryDeps } from "./engine";
import {
  holdForConsent,
  isDue,
  newItem,
  reconfirm,
  reopenable,
  reshare,
  retryNow,
  type DeliveryItem,
  type ShareGrantBinding,
  type VisitIdentity,
} from "./outbox";
import type { NotePutBody } from "./payload";
import type { OutboxPersistence } from "./persistence";

export interface DeliveryRuntime {
  deps: DeliveryDeps;
  persistence: OutboxPersistence;
  now(): number;
  /** Run `run` once after `delayMs`; returns its cancel. */
  schedule(run: () => void, delayMs: number): () => void;
  /**
   * Subscribe to consent changes (the consent ledger's own subscription); the
   * outbox parks every unsent note whenever a new share withdrawal appears in
   * `deps.lastShareWithdrawal()`. Returns the unsubscribe.
   */
  watchConsent?(listener: () => void): () => void;
}

let runtime: DeliveryRuntime | null = null;
let unwatchConsent: (() => void) | null = null;
let seenWithdrawal: string | null = null;
let account: string | null = null;
let items: Readonly<Record<string, DeliveryItem>> = {};
let hydrated = false;
/** Bumped on stop, so a pass still in flight for a stopped run changes nothing. */
let generation = 0;
let running: Promise<void> | null = null;
let rerun = false;
let cancelTimer: (() => void) | null = null;
const listeners = new Set<() => void>();

function notify(): void {
  for (const listener of listeners) {
    listener();
  }
}

async function commit(next: DeliveryItem): Promise<void> {
  items = { ...items, [next.visitId]: next };
  notify();
  try {
    await runtime?.persistence.save(next);
  } catch {
    // the item stands in memory and the next change persists it again
  }
}

/** A share-scope receipt given for THIS note — never another note's. */
function isReceiptFor(receipt: unknown, visitId: string): receipt is ShareGrantReceipt {
  if (typeof receipt !== "object" || receipt === null) {
    return false;
  }
  const value = receipt as Record<string, unknown>;
  return (
    value.scope === SHARE_SCOPE &&
    value.visitId === visitId &&
    typeof value.version === "string" &&
    typeof value.textHash === "string" &&
    typeof value.atIso === "string"
  );
}

function bindingOf(receipt: ShareGrantReceipt): ShareGrantBinding {
  return { version: receipt.version, textHash: receipt.textHash, atIso: receipt.atIso };
}

/** A new share withdrawal on this phone parks every unsent note at once. */
function onConsentChange(): void {
  const rt = runtime;
  if (rt === null) {
    return;
  }
  const withdrawnAt = rt.deps.lastShareWithdrawal();
  if (withdrawnAt !== null && withdrawnAt !== seenWithdrawal) {
    seenWithdrawal = withdrawnAt;
    void holdDeliveriesForConsent();
  }
}

function scheduleNext(): void {
  cancelTimer?.();
  cancelTimer = null;
  const rt = runtime;
  if (rt === null) {
    return;
  }
  const waits = Object.values(items)
    .filter((item) => item.stage === "queued")
    .map((item) => item.nextAttemptAt);
  if (waits.length === 0) {
    return;
  }
  const delay = Math.max(0, Math.min(...waits) - rt.now());
  cancelTimer = rt.schedule(() => {
    void runDueDeliveries();
  }, delay);
}

async function pass(): Promise<void> {
  const rt = runtime;
  const gen = generation;
  if (rt === null) {
    return;
  }
  for (const visitId of Object.keys(items)) {
    const item = items[visitId];
    if (item === undefined || !isDue(item, rt.now())) {
      continue;
    }
    const next = await attemptDelivery(item, rt.deps, rt.now());
    if (gen !== generation) {
      return; // signed out or restarted meanwhile
    }
    if (items[visitId] !== item || next === item) {
      continue; // the patient acted on it meanwhile; their act stands
    }
    await commit(next);
  }
}

/** Attempt every due item once (again, if something was queued meanwhile). */
export function runDueDeliveries(): Promise<void> {
  if (running !== null) {
    rerun = true;
    return running;
  }
  const gen = generation;
  running = (async () => {
    do {
      rerun = false;
      await pass();
    } while (rerun && gen === generation);
  })().finally(() => {
    if (gen === generation) {
      running = null;
      scheduleNext();
    }
  });
  return running;
}

/** Restore this account's outbox from disk and run whatever is due. */
export async function startDelivery(accountId: string, rt: DeliveryRuntime): Promise<void> {
  stopDelivery();
  runtime = rt;
  account = accountId;
  // A withdrawal already on record parks older notes at their next attempt
  // (the engine's own check); only a NEW one parks everything at once.
  seenWithdrawal = rt.deps.lastShareWithdrawal();
  unwatchConsent = rt.watchConsent?.(onConsentChange) ?? null;
  const gen = generation;
  let loaded: DeliveryItem[] = [];
  try {
    loaded = await rt.persistence.loadAll();
  } catch {
    // an unreadable store starts empty; nothing is invented in its place
  }
  if (gen !== generation) {
    return;
  }
  const own: Record<string, DeliveryItem> = {};
  for (const item of loaded) {
    if (item.accountId === accountId) {
      own[item.visitId] = item;
    }
  }
  items = own;
  hydrated = true;
  notify();
  await runDueDeliveries();
}

/** Sign-out / restart: drop the working copy. Disk is the session's to shred. */
export function stopDelivery(): void {
  generation += 1;
  unwatchConsent?.();
  unwatchConsent = null;
  seenWithdrawal = null;
  cancelTimer?.();
  cancelTimer = null;
  runtime = null;
  account = null;
  items = {};
  hydrated = false;
  running = null;
  rerun = false;
  notify();
}

/**
 * Queue a sent note for delivery, bound to its own grant. Refused — nothing
 * queued, nothing written — without a share-scope receipt given for THIS
 * note, before the outbox has started, or when this visit already has an item
 * (the screen reconfirms or retries that one).
 */
export async function enqueueDelivery(
  input: { visitId: string; visit: VisitIdentity; body: NotePutBody },
  receipt: ShareGrantReceipt,
): Promise<boolean> {
  const rt = runtime;
  if (rt === null || account === null || !isReceiptFor(receipt, input.visitId)) {
    return false;
  }
  if (items[input.visitId] !== undefined) {
    return false;
  }
  await commit(newItem({ ...input, accountId: account, grant: bindingOf(receipt) }, rt.now()));
  await runDueDeliveries();
  return true;
}

/** The patient agreed again FOR THIS NOTE: release it, bound to that grant.
 * A receipt given for another note releases nothing. */
export async function reconfirmDelivery(
  visitId: string,
  receipt: ShareGrantReceipt,
): Promise<void> {
  const rt = runtime;
  const item = items[visitId];
  if (rt === null || item === undefined || !isReceiptFor(receipt, visitId)) {
    return;
  }
  const next = reconfirm(item, bindingOf(receipt), rt.now());
  if (next !== item) {
    await commit(next);
  }
  await runDueDeliveries();
}

/**
 * INT-589: share a delivered note again after a withdrawal took its share
 * away. The patient agreed again FOR THIS NOTE, and the frozen body goes out
 * once more bound to that grant. A receipt for another note, or a note that is
 * not delivered, re-shares nothing (false).
 */
export async function reshareDelivery(
  visitId: string,
  body: NotePutBody,
  receipt: ShareGrantReceipt,
): Promise<boolean> {
  const rt = runtime;
  const item = items[visitId];
  if (rt === null || item === undefined || !isReceiptFor(receipt, visitId)) {
    return false;
  }
  const next = reshare(item, body, bindingOf(receipt), rt.now());
  if (next === item) {
    return false;
  }
  await commit(next);
  await runDueDeliveries();
  return true;
}

/** The patient's "Tekrar deneyin" on a refused item. */
export async function retryDelivery(visitId: string): Promise<void> {
  const rt = runtime;
  const item = items[visitId];
  if (rt === null || item === undefined) {
    return;
  }
  const next = retryNow(item, rt.now());
  if (next !== item) {
    await commit(next);
  }
  await runDueDeliveries();
}

/**
 * The share consent was withdrawn on this phone: no unsent note may leave.
 * Every queued and refused note is parked IN MEMORY AT ONCE — before any await,
 * so no pass can pick one up in between — and then written to disk, so a
 * restart finds it parked.
 */
export async function holdDeliveriesForConsent(): Promise<void> {
  const parked: DeliveryItem[] = [];
  const next: Record<string, DeliveryItem> = { ...items };
  for (const item of Object.values(items)) {
    const held = holdForConsent(item);
    if (held !== item) {
      next[item.visitId] = held;
      parked.push(held);
    }
  }
  if (parked.length === 0) {
    return;
  }
  // captured now: a sign-out right after the withdrawal must not skip a write
  const persistence = runtime?.persistence;
  items = next;
  notify();
  for (const item of parked) {
    try {
      await persistence?.save(item);
    } catch {
      // the parked item stands in memory; its next change persists it again
    }
  }
}

/**
 * Take a note back to a draft: removes its item, only where nothing can have
 * reached the server. False means the note stays exactly as it is.
 */
export async function discardUndelivered(visitId: string): Promise<boolean> {
  const item = items[visitId] ?? null;
  if (!reopenable(item)) {
    return false;
  }
  if (item !== null) {
    const rest: Record<string, DeliveryItem> = { ...items };
    delete rest[visitId];
    items = rest;
    notify();
    try {
      await runtime?.persistence.remove(visitId);
    } catch {
      // a blob that could not be removed is re-read as this same item
    }
  }
  return true;
}

/** Kiosk wipe: the next patient inherits nothing (INT-143). */
export async function clearDeliveries(): Promise<void> {
  const visitIds = Object.keys(items);
  items = {};
  notify();
  for (const visitId of visitIds) {
    try {
      await runtime?.persistence.remove(visitId);
    } catch {
      // the session's shred removes whatever is left
    }
  }
}

export function deliveryOf(visitId: string): DeliveryItem | null {
  return items[visitId] ?? null;
}

/** The server's visit id for a DELIVERED note — what the Doctor Link routes
 * address. Null until the server has confirmed the send. */
export function serverVisitIdOf(visitId: string): string | null {
  const item = items[visitId];
  return item !== undefined && item.stage === "delivered" ? item.serverVisitId : null;
}

export function deliveryHydrated(): boolean {
  return hydrated;
}

export function subscribeToDeliveries(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** React binding: this visit's item, or null. */
export function useDelivery(visitId: string): DeliveryItem | null {
  return useSyncExternalStore(
    subscribeToDeliveries,
    () => deliveryOf(visitId),
    () => deliveryOf(visitId),
  );
}

/** Every item by visit id. Each change replaces the map, so one value is a
 * stable snapshot until the next change. */
export function allDeliveries(): Readonly<Record<string, DeliveryItem>> {
  return items;
}

/** React binding: every visit's item at once. Bugün reads several visits
 * (INT-594), and hooks cannot be called in a loop. */
export function useDeliveries(): Readonly<Record<string, DeliveryItem>> {
  return useSyncExternalStore(subscribeToDeliveries, allDeliveries, allDeliveries);
}

/** React binding: false until this account's outbox has been read from disk. */
export function useDeliveryHydrated(): boolean {
  return useSyncExternalStore(subscribeToDeliveries, deliveryHydrated, deliveryHydrated);
}

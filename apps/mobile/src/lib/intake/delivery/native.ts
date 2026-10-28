/**
 * INT-587 — the production wiring of the note outbox. Everything native or
 * networked that the pure modules take as an injected dependency is bound
 * here, and nowhere else (e2e/noteDelivery.spec.ts holds the line):
 *
 * - the transport is INT-131's DPoP-bound `authedFetch`;
 * - the server visit is found or created by records' `ensureServerVisit`, so
 *   the note and the patient's documents hang off the same server visit;
 * - the consent queue is the consent store's, flushed before every send;
 * - persistence is INT-142's sealed draft backend (keychain DEK + encrypted
 *   blobs), or memory only in kiosk mode (INT-143);
 * - a pass runs when the app comes back to the foreground, as well as on the
 *   outbox's own backoff timer.
 *
 * session.tsx loads this file only through a lazy `import()`, so the provider
 * stays node-importable and no native module reaches the vitest environment.
 */
import { AppState, type NativeEventSubscription } from "react-native";

import { authedFetch } from "@/lib/auth/api";
import { consentQueueClear, shareStanding } from "@/lib/consent/store";
import { ensureServerVisit } from "@/lib/records/api";

import { nativeDraftBackend } from "../offline/nativeBackend";
import { classifyVisitError, type DeliveryDeps, type ResolveResult } from "./engine";
import { memoryOutbox, sealedOutbox } from "./persistence";
import { clearDeliveries, runDueDeliveries, startDelivery, stopDelivery } from "./store";
import { putNote } from "./transport";

let foreground: NativeEventSubscription | null = null;

const deps: DeliveryDeps = {
  shareStanding,
  flushConsent: consentQueueClear,
  async resolveServerVisit(visit): Promise<ResolveResult> {
    try {
      const id = await ensureServerVisit(visit, { create: true });
      return id === null ? { kind: "transient" } : { kind: "resolved", serverVisitId: id };
    } catch (error) {
      return classifyVisitError(error);
    }
  },
  putNote: (serverVisitId, body) => putNote(authedFetch, serverVisitId, body),
};

/** Start (or restart) the outbox for the signed-in account. */
export async function startNativeDelivery(accountId: string, memoryOnly: boolean): Promise<void> {
  foreground?.remove();
  foreground = AppState.addEventListener("change", (status) => {
    if (status === "active") {
      void runDueDeliveries();
    }
  });
  await startDelivery(accountId, {
    deps,
    persistence: memoryOnly ? memoryOutbox() : sealedOutbox(nativeDraftBackend()),
    now: () => Date.now(),
    schedule(run, delayMs) {
      const handle = setTimeout(run, delayMs);
      return () => clearTimeout(handle);
    },
  });
}

/** Sign-out: drop the working copy. The session's shred clears the disk. */
export function stopNativeDelivery(): void {
  foreground?.remove();
  foreground = null;
  stopDelivery();
}

/** Kiosk wipe between patients (INT-143). */
export async function clearNativeDeliveries(): Promise<void> {
  await clearDeliveries();
}

/**
 * INT-133 — the companion declaration for the current session.
 *
 * In memory only, and deliberately: "a companion is answering for this
 * patient" is a fact about one sitting, not a saved preference. Persisting
 * it would (a) survive a handover of the phone and silently mislabel the
 * next session, and (b) make it a stored fact about a second person, which
 * is the category question `guardian_link_basis` leaves with counsel
 * (HB-L20). It resets with the app, which is the safe direction: the
 * default is always the patient answering for themselves.
 *
 * `useSyncExternalStore` over a module singleton, matching the INT-132
 * consent ledger — the screen and any producer of a visit read the same
 * snapshot.
 */
import { useSyncExternalStore } from "react";

import {
  resolveAttribution,
  SELF_ALONE,
  type AttributionInput,
  type AttributionOutcome,
} from "./attribution";

let declaration: AttributionInput = SELF_ALONE;
const listeners = new Set<() => void>();

function emit(): void {
  for (const listener of listeners) {
    listener();
  }
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function snapshot(): AttributionInput {
  return declaration;
}

/** The current declaration. */
export function companionDeclaration(): AttributionInput {
  return declaration;
}

/**
 * Replace the declaration. Changing the ROLE always clears the
 * acknowledgement: an acknowledgement given for one role is not evidence
 * for another, and a stale `true` here would let a companion session start
 * without anyone having said anything (files/06 §6).
 */
export function setCompanionDeclaration(next: Partial<AttributionInput>): void {
  const merged: AttributionInput = { ...declaration, ...next };
  if (next.role !== undefined && next.role !== declaration.role) {
    merged.acknowledged = false;
  }
  if (merged.role === "self") {
    // an incoherent pair the server would reject outright
    merged.speaker = "patient";
    merged.acknowledged = false;
  }
  declaration = merged;
  emit();
}

/** Back to the patient, alone. Called on sign-out and when a session ends. */
export function resetCompanionDeclaration(): void {
  declaration = SELF_ALONE;
  emit();
}

export function useCompanionDeclaration(): AttributionInput {
  return useSyncExternalStore(subscribe, snapshot, snapshot);
}

/** The derived consequences of the current declaration. */
export function useCompanionOutcome(): AttributionOutcome {
  return resolveAttribution(useCompanionDeclaration());
}

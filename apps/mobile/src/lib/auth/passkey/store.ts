/**
 * INT-582 (D36) — the passkey state behind *Verileriniz*, on the INT-141
 * store pattern: a module singleton read through `useSyncExternalStore`, in
 * memory only. The server is the register of record; nothing here is shown
 * as enrolled, removed, recovering or cancelled that the server did not
 * confirm.
 *
 * `enrolment` is the server's word: `enrolled`, `offered` (an OTP session
 * with no passkey — the offer the step-up gate also makes), or `unavailable`
 * (no passkey tier, or a session that cannot enrol). `null` = not asked yet.
 *
 * Removing the passkey and cancelling a recovery are step-ups of their own
 * (`passkey_remove`, `recovery_cancel`): the server refuses either from an
 * OTP-only session, so a SIM swap cannot take the passkey away.
 */
import { useSyncExternalStore } from "react";

import { passkeyApi } from "./api";
import { type EnrolFailure, type PasskeyPorts, enrol, stepUpFor } from "./ceremony";
import { defaultPasskeyPorts } from "./stepUp";

export type Enrolment = "enrolled" | "offered" | "unavailable";
export type PasskeyNotice =
  | "added"
  | EnrolFailure
  | "removed"
  | "remove_failed"
  | "recovery_started"
  | "recovery_failed"
  | "recovery_cancelled"
  | "cancel_failed";

export interface PasskeyState {
  enrolment: Enrolment | null;
  /** When a running recovery takes effect (ISO instant), or null. */
  recoveryEndsAt: string | null;
  /** The outcome of the patient's last tap, for one true sentence. */
  notice: PasskeyNotice | null;
  /** The server's ids for this patient's passkeys (to remove one). */
  passkeyIds: string[];
}

const FRESH: PasskeyState = {
  enrolment: null,
  recoveryEndsAt: null,
  notice: null,
  passkeyIds: [],
};

let state: PasskeyState = FRESH;
const listeners = new Set<() => void>();

function commit(next: PasskeyState): void {
  state = next;
  for (const listener of listeners) {
    listener();
  }
}

export function passkeySnapshot(): PasskeyState {
  return state;
}

export function subscribeToPasskeys(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function usePasskeys(): PasskeyState {
  return useSyncExternalStore(subscribeToPasskeys, passkeySnapshot, passkeySnapshot);
}

export function resetPasskeys(): void {
  commit(FRESH);
}

/** The rows *Verileriniz* shows, in order — pure, so the rule is testable. */
export type PasskeyRow =
  "add" | "enrolled" | "remove" | "lost" | "lostConfirm" | "recoveryEnds" | "cancelRecovery";

export function passkeyRows(current: PasskeyState, lostArmed: boolean): PasskeyRow[] {
  if (current.enrolment === "offered") {
    return ["add"];
  }
  if (current.enrolment !== "enrolled") {
    return [];
  }
  if (current.recoveryEndsAt !== null) {
    // the cancel the note promises — and only while there is one to cancel
    return ["enrolled", "recoveryEnds", "cancelRecovery"];
  }
  return ["enrolled", "remove", lostArmed ? "lostConfirm" : "lost"];
}

/** The server's list answer, reduced; null when it is not one. */
export function parsePasskeyList(
  body: unknown,
): { enrolment: Enrolment; recoveryEndsAt: string | null; passkeyIds: string[] } | null {
  if (typeof body !== "object" || body === null) {
    return null;
  }
  const row = body as Record<string, unknown>;
  const enrolment = row.enrolment;
  if (
    (enrolment !== "enrolled" && enrolment !== "offered" && enrolment !== "unavailable") ||
    !Array.isArray(row.passkeys)
  ) {
    return null;
  }
  const items = row.passkeys.map((item) => (item ?? {}) as Record<string, unknown>);
  const ends = items
    .map((item) => item.recovery_ends_at)
    .filter((value): value is string => typeof value === "string")
    .sort();
  const passkeyIds = items
    .map((item) => item.passkey_id)
    .filter((value): value is string => typeof value === "string" && value.length > 0);
  return { enrolment, recoveryEndsAt: ends[0] ?? null, passkeyIds };
}

export async function loadPasskeys(): Promise<void> {
  const answer = await passkeyApi.list();
  if (!answer.ok) {
    // 503: no passkey tier here; anything else: say nothing we cannot stand by
    commit({ ...state, enrolment: answer.status === 503 ? "unavailable" : state.enrolment });
    return;
  }
  const parsed = parsePasskeyList(answer.body);
  if (parsed !== null) {
    commit({ ...state, ...parsed });
  }
}

export async function addPasskey(ports: PasskeyPorts = defaultPasskeyPorts): Promise<void> {
  const result = await enrol(ports);
  if (!result.ok) {
    commit({ ...state, notice: result.reason });
    return;
  }
  commit({ ...state, enrolment: "enrolled", notice: "added" });
  await loadPasskeys();
}

/** Lost phone: start the OTP-tier recovery; the cool-off date comes back. */
export async function startPasskeyRecovery(): Promise<void> {
  const answer = await passkeyApi.startRecovery();
  const ends =
    answer.ok && typeof answer.body === "object" && answer.body !== null
      ? (answer.body as Record<string, unknown>).recovery_ends_at
      : null;
  if (typeof ends !== "string") {
    commit({ ...state, notice: "recovery_failed" });
    return;
  }
  commit({ ...state, recoveryEndsAt: ends, notice: "recovery_started" });
}

/** The holder withdraws a recovery: a recovery_cancel step-up, then the DELETE. */
export async function cancelPasskeyRecovery(
  ports: PasskeyPorts = defaultPasskeyPorts,
): Promise<void> {
  const stepped = await stepUpFor("recovery_cancel", ports);
  if (stepped.kind !== "passkey") {
    commit({ ...state, notice: stepped.kind === "cancelled" ? "cancelled" : "cancel_failed" });
    return;
  }
  const answer = await passkeyApi.cancelRecovery(stepped.grant);
  if (!answer.ok) {
    commit({ ...state, notice: "cancel_failed" });
    return;
  }
  commit({ ...state, recoveryEndsAt: null, notice: "recovery_cancelled" });
  await loadPasskeys();
}

/** Remove the first listed passkey: a passkey_remove step-up, then the DELETE. */
export async function removePasskey(ports: PasskeyPorts = defaultPasskeyPorts): Promise<void> {
  const passkeyId = state.passkeyIds[0];
  if (passkeyId === undefined) {
    commit({ ...state, notice: "remove_failed" });
    return;
  }
  const stepped = await stepUpFor("passkey_remove", ports);
  if (stepped.kind !== "passkey") {
    commit({ ...state, notice: stepped.kind === "cancelled" ? "cancelled" : "remove_failed" });
    return;
  }
  const answer = await passkeyApi.remove(passkeyId, stepped.grant);
  if (!answer.ok) {
    commit({ ...state, notice: "remove_failed" });
    return;
  }
  commit({ ...state, notice: "removed" });
  await loadPasskeys();
}

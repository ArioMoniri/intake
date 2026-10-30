/**
 * INT-582 (D36) — the passkey state behind *Verileriniz*, on the INT-141
 * store pattern: a module singleton read through `useSyncExternalStore`, in
 * memory only. The server is the register of record; nothing here is shown
 * as enrolled, or as recovering, that the server did not confirm.
 *
 * `enrolment` is the server's word: `enrolled`, `offered` (an OTP session
 * with no passkey — the offer the step-up gate also makes), or `unavailable`
 * (no passkey tier, or a session that cannot enrol). `null` = not asked yet.
 */
import { useSyncExternalStore } from "react";

import { passkeyApi } from "./api";
import { type EnrolFailure, type PasskeyPorts, enrol } from "./ceremony";
import { defaultPasskeyPorts } from "./stepUp";

export type Enrolment = "enrolled" | "offered" | "unavailable";
export type PasskeyNotice = "added" | EnrolFailure | "recovery_started" | "recovery_failed";

export interface PasskeyState {
  enrolment: Enrolment | null;
  /** When a running recovery takes effect (ISO instant), or null. */
  recoveryEndsAt: string | null;
  /** The outcome of the patient's last tap, for one true sentence. */
  notice: PasskeyNotice | null;
}

const FRESH: PasskeyState = { enrolment: null, recoveryEndsAt: null, notice: null };

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

/** The server's list answer, reduced; null when it is not one. */
export function parsePasskeyList(
  body: unknown,
): { enrolment: Enrolment; recoveryEndsAt: string | null } | null {
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
  const ends = row.passkeys
    .map((item) => (item as Record<string, unknown> | null)?.recovery_ends_at)
    .filter((value): value is string => typeof value === "string")
    .sort();
  return { enrolment, recoveryEndsAt: ends[0] ?? null };
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

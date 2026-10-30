/**
 * INT-583 — one registration run, over ports the native module supplies.
 *
 * Read the permission; ask only if the patient tapped the enable button;
 * when granted, read the native APNs device token and send it. Every native
 * failure stays inside the run and comes back as a state the screen can
 * explain: a refusal is never thrown at the patient.
 *
 * A session that predates device binding cannot carry a token (409
 * `session_unbound`). The run then stops trying until the next sign-in and
 * says nothing about it to anyone: there is nothing the patient can do, and
 * the next sign-in is bound.
 */
import type { PushTokenResult } from "./api";
import {
  isApnsDeviceToken,
  planAfterPrompt,
  planPushRegistration,
  type PushPermission,
} from "./plan";

export interface PushPorts {
  readPermission(): Promise<PushPermission>;
  /** The system prompt. Reached only on an explicit tap. */
  requestPermission(): Promise<PushPermission>;
  /** The native APNs device token, or null when the platform has none. */
  deviceToken(): Promise<string | null>;
  putToken(token: string): Promise<PushTokenResult>;
}

export type PushOutcome = "registered" | "skipped" | "denied" | "unbound" | "failed";

export interface PushSync {
  permission: PushPermission;
  outcome: PushOutcome;
}

export interface SyncOptions {
  /** The patient tapped the enable button. */
  asked: boolean;
  /** A shared clinic device in kiosk mode: never registers. */
  sharedDevice?: boolean;
  /**
   * Told the permission once it is final (after the prompt, when there is
   * one) and before any token work, so a screen can show it even while the
   * native token call is slow.
   */
  onPermission?: (permission: PushPermission) => void;
}

/** Set by a 409 `session_unbound`; cleared by sign-out. */
let unbound = false;

/** Sign-out: the next session is a new one, so it may try again. */
export function resetPushRegistration(): void {
  unbound = false;
}

async function settle<T>(attempt: () => Promise<T>, fallback: T): Promise<T> {
  try {
    return await attempt();
  } catch {
    return fallback;
  }
}

export async function syncPushRegistration(
  ports: PushPorts,
  options: SyncOptions,
): Promise<PushSync> {
  let permission = await settle(() => ports.readPermission(), "unavailable" as PushPermission);
  let step = planPushRegistration(permission, options.asked, {
    sharedDevice: options.sharedDevice,
  });
  if (step === "ask") {
    permission = await settle(() => ports.requestPermission(), "unavailable" as PushPermission);
    step = planAfterPrompt(permission);
  }
  options.onPermission?.(permission);
  if (step === "explain-denied") {
    return { permission, outcome: "denied" };
  }
  if (step !== "register") {
    return { permission, outcome: "skipped" };
  }
  if (unbound) {
    return { permission, outcome: "unbound" };
  }
  const token = await settle(() => ports.deviceToken(), null);
  if (!isApnsDeviceToken(token)) {
    return { permission, outcome: "failed" };
  }
  const sent = await settle(() => ports.putToken(token), {
    ok: false,
    error: "unreachable",
  } as PushTokenResult);
  if (sent.ok) {
    return { permission, outcome: "registered" };
  }
  if (sent.error === "session_unbound") {
    unbound = true;
    return { permission, outcome: "unbound" };
  }
  return { permission, outcome: "failed" };
}

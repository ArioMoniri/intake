/**
 * INT-583 — one registration run, over ports the native module supplies.
 *
 * Read the permission; ask only if the patient tapped the enable button;
 * when granted, read the native APNs device token and send it. Every native
 * failure stays inside the run and comes back as a state the screen can
 * explain: a refusal is never thrown at the patient. When notices are off on
 * the phone, the server's copy of the token is deleted, unless the caller
 * knows there is none.
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
  /** Drop this device's token on the server. Idempotent there. */
  deleteToken(): Promise<PushTokenResult>;
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
  /**
   * Whether the server holds a token for this device, from the sessions
   * list's current-device `push`. Left out when the caller does not know
   * (the app-start run): a denied permission then still deletes, because the
   * server's DELETE is idempotent and a stale token is the worse outcome.
   */
  registered?: boolean;
}

const NOT_SENT: PushTokenResult = { ok: false, error: "unreachable" };

/**
 * Set by a 409 `session_unbound`; cleared by sign-out. A 503
 * `push_unavailable` does not set it: the server has no channel yet, so the
 * run reports `failed` silently and the next run tries again.
 */
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
  if (permission === "denied" && options.registered !== false) {
    // Notices are off on this phone: a token left on the server would name a
    // device that asked not to be told anything.
    await settle(() => ports.deleteToken(), NOT_SENT);
  }
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
  const sent = await settle(() => ports.putToken(token), NOT_SENT);
  if (sent.ok) {
    return { permission, outcome: "registered" };
  }
  if (sent.error === "session_unbound") {
    unbound = true;
    return { permission, outcome: "unbound" };
  }
  return { permission, outcome: "failed" };
}

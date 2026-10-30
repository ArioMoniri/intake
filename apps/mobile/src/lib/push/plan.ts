/**
 * INT-583 — when this device asks for new-sign-in notices, and what a device
 * token must look like before it leaves the phone.
 *
 * D35: a sign-in from a new device is told to the patient's earlier devices
 * by push (APNs, direct, no relay), never by SMS. This device's part is to be
 * one of those earlier devices: hold the permission, and keep the server's
 * copy of its token fresh.
 *
 * The rule this module holds: the system prompt is reached only after the
 * patient taps the enable button. A cold prompt at launch is refused without
 * being read, and iOS never shows it a second time, so asking early spends
 * the only chance there is.
 *
 * Pure, so the whole matrix is proved in node; the native calls live in
 * native.ts.
 */

/** The OS permission as this app reads it. `unavailable`: this device cannot receive them. */
export type PushPermission = "granted" | "denied" | "undetermined" | "unavailable";

/** What a registration run does next. */
export type PushStep = "register" | "ask" | "explain-denied" | "skip";

export interface PlanContext {
  /**
   * A shared clinic device in kiosk mode (INT-143). It never registers: a
   * notice for one patient would land on a screen the next patient holds.
   */
  sharedDevice?: boolean;
}

/** The next step, given the permission and whether the patient asked. */
export function planPushRegistration(
  permission: PushPermission,
  asked: boolean,
  context: PlanContext = {},
): PushStep {
  if (context.sharedDevice === true) {
    return "skip";
  }
  switch (permission) {
    case "granted":
      return "register";
    case "undetermined":
      return asked ? "ask" : "skip";
    case "denied":
      return asked ? "explain-denied" : "skip";
    case "unavailable":
      return "skip";
  }
}

/** The step after the system prompt has answered. Never a second prompt. */
export function planAfterPrompt(permission: PushPermission): PushStep {
  if (permission === "granted") {
    return "register";
  }
  return permission === "denied" ? "explain-denied" : "skip";
}

/** The fields of the native permission answer this module reads. */
export interface NativePermissionReading {
  status: string;
  granted: boolean;
  canAskAgain: boolean;
}

/**
 * Read the native answer. Anything this module does not recognise fails
 * closed to `denied`: the screen then explains Settings instead of claiming
 * notices are on.
 */
export function toPushPermission(reading: NativePermissionReading): PushPermission {
  if (reading.granted) {
    return "granted";
  }
  if (reading.status === "undetermined" && reading.canAskAgain) {
    return "undetermined";
  }
  return "denied";
}

/** An APNs device token as the server accepts it: lowercase hex, 64 to 200 characters. */
const APNS_DEVICE_TOKEN = /^[0-9a-f]{64,200}$/;

export function isApnsDeviceToken(value: unknown): value is string {
  return typeof value === "string" && APNS_DEVICE_TOKEN.test(value);
}

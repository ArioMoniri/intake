/**
 * INT-583 — the native half of new-sign-in notices, and the ONE module in the
 * app that reaches the native notifications package (e2e/notifications.spec.ts
 * holds the tree to that).
 *
 * The package is loaded with a lazy `await import(...)`, so nothing that
 * imports this file at module scope pulls the native code in, and every
 * node-tested module stays free of it. What it is used for, and all it is
 * used for: read and request the permission, and read the NATIVE APNs device
 * token. No relay token is ever requested — the server sends to APNs
 * directly (D35) — and nothing here schedules or presents a notification, so
 * the app never assembles a notification body (INT-141).
 *
 * iOS only: Android cannot sign in on a real build (HB-A3), so on any other
 * platform the permission reads as unavailable and nothing is asked.
 */
import { Platform } from "react-native";

import { authedFetch } from "@/lib/auth/api";

import { deletePushToken, putPushToken } from "./api";
import { toPushPermission, type PushPermission } from "./plan";
import {
  resetPushRegistration,
  syncPushRegistration,
  type PushPorts,
  type PushSync,
} from "./registration";

async function nativeNotifications() {
  return await import("expo-notifications");
}

const ports: PushPorts = {
  async readPermission(): Promise<PushPermission> {
    if (Platform.OS !== "ios") {
      return "unavailable";
    }
    const native = await nativeNotifications();
    return toPushPermission(await native.getPermissionsAsync());
  },
  async requestPermission(): Promise<PushPermission> {
    if (Platform.OS !== "ios") {
      return "unavailable";
    }
    const native = await nativeNotifications();
    return toPushPermission(
      await native.requestPermissionsAsync({
        ios: { allowAlert: true, allowSound: true, allowBadge: false },
      }),
    );
  },
  async deviceToken(): Promise<string | null> {
    const native = await nativeNotifications();
    const token = await native.getDevicePushTokenAsync();
    return token.type === "ios" && typeof token.data === "string" ? token.data : null;
  },
  putToken: (token) => putPushToken(authedFetch, token),
};

/** App start, signed in: keep the server's token fresh. Never prompts. */
export function registerPushSilently(
  sharedDevice: boolean,
  onPermission?: (permission: PushPermission) => void,
): Promise<PushSync> {
  return syncPushRegistration(ports, { asked: false, sharedDevice, onPermission });
}

/** The patient tapped the enable button: the one path that may show the prompt. */
export function enablePush(
  sharedDevice: boolean,
  onPermission?: (permission: PushPermission) => void,
): Promise<PushSync> {
  return syncPushRegistration(ports, { asked: true, sharedDevice, onPermission });
}

/**
 * Sign-out: this device stops being told about new sign-ins. Best-effort: a
 * call that does not land leaves the server's registration in place, and
 * nothing here throws or tells the patient, because sign-out must not wait
 * on the network.
 */
export async function forgetPushRegistration(): Promise<void> {
  resetPushRegistration();
  await deletePushToken(authedFetch);
}

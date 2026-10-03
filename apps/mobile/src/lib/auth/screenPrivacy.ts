/**
 * Clinical-screen capture blocking (INT-131, files/10 §4 MASVS:
 * FLAG_SECURE / screenshot blocking on clinical screens).
 *
 * Android: preventScreenCaptureAsync sets FLAG_SECURE on the window —
 * screenshots and the recents thumbnail go black. iOS: the same call is
 * best-effort screen-recording protection (iOS has no FLAG_SECURE
 * equivalent for stills). Capability-detected: web has no capture surface
 * to flag, and any Expo Go limitation degrades to a no-op rather than a
 * crash — never a false claim of protection.
 *
 * INT-477 (ADR-039 amendment, owner: "solid"): the guard also holds the
 * window's capture-protection store, so every glass surface is solid while
 * the screen is protected (lib/auth/captureProtection `protectScreen`: held
 * before protection is asked for, let go after the release has settled).
 */
import * as ScreenCapture from "expo-screen-capture";
import { useEffect } from "react";
import { Platform } from "react-native";

import { captureProtection, protectScreen, type CaptureGuard } from "@/lib/auth/captureProtection";

const CAPTURE_KEY = "intake-clinical";

/**
 * The OS guard. A refused request is a no-op, not a crash; a refused release
 * leaves the stricter state, which is the safe direction.
 */
const NATIVE_GUARD: CaptureGuard = {
  prevent: () => ScreenCapture.preventScreenCaptureAsync(CAPTURE_KEY),
  allow: () => ScreenCapture.allowScreenCaptureAsync(CAPTURE_KEY),
};

/** Mount on every clinical screen; releases the flag on unmount. */
export function useClinicalScreenPrivacy(): void {
  useEffect(() => {
    const native = Platform.OS === "ios" || Platform.OS === "android";
    return protectScreen(native ? NATIVE_GUARD : null, captureProtection);
  }, []);
}

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
 * INT-478: every screen holds the app's one lock (lib/auth/captureLock), so
 * protection stays on while any protected screen is mounted and is released
 * only after the last one unmounts. It follows the mount, not the focus: a
 * tab screen kept mounted behind another stays protected (fail closed).
 */
import * as ScreenCapture from "expo-screen-capture";
import { useEffect } from "react";
import { Platform } from "react-native";

import { createCaptureLock, type CaptureGuard } from "@/lib/auth/captureLock";

const CAPTURE_KEY = "intake-clinical";

/**
 * The OS guard, asked only by the lock: once for the first protected screen,
 * released once after the last. A refused release leaves the stricter state,
 * which is the safe direction.
 */
const NATIVE_GUARD: CaptureGuard = {
  prevent: () => ScreenCapture.preventScreenCaptureAsync(CAPTURE_KEY),
  allow: () => ScreenCapture.allowScreenCaptureAsync(CAPTURE_KEY),
};

/** The app's one lock: every protected screen holds it while mounted. */
const clinicalCapture = createCaptureLock(NATIVE_GUARD);

/** Mount on every clinical screen; gives back its own hold on unmount. */
export function useClinicalScreenPrivacy(): void {
  useEffect(() => {
    if (Platform.OS !== "ios" && Platform.OS !== "android") {
      return undefined;
    }
    return clinicalCapture.acquire();
  }, []);
}

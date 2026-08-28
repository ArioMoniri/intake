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
 */
import * as ScreenCapture from "expo-screen-capture";
import { useEffect } from "react";
import { Platform } from "react-native";

const CAPTURE_KEY = "intake-clinical";

/** Mount on every clinical screen; releases the flag on unmount. */
export function useClinicalScreenPrivacy(): void {
  useEffect(() => {
    if (Platform.OS !== "ios" && Platform.OS !== "android") {
      return undefined;
    }
    ScreenCapture.preventScreenCaptureAsync(CAPTURE_KEY).catch(() => {
      // capability-detect: unavailable in this runtime → no-op, no crash
    });
    return () => {
      ScreenCapture.allowScreenCaptureAsync(CAPTURE_KEY).catch(() => {
        // symmetric release; failure here leaves the stricter state, which
        // is the safe direction
      });
    };
  }, []);
}

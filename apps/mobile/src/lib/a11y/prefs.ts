/**
 * The two OS accessibility signals the app reacts to (INT-144).
 *
 * Kept apart from ./motion so the policy stays unit-testable without a
 * React Native runtime: this file is the thin adapter that reads the
 * platform, ./motion is what the app does with the answer.
 */
import { useEffect, useRef, useState } from "react";
import { AccessibilityInfo } from "react-native";

import { nextAnnouncement } from "./announce";

/**
 * Whether the user asked the OS to reduce motion (iOS "Hareketi Azalt",
 * Android "Remove animations"). Re-reads on the OS event, so a change made
 * in Settings while the app is backgrounded takes effect on return without a
 * restart.
 */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    let live = true;
    void AccessibilityInfo.isReduceMotionEnabled().then((value) => {
      if (live) {
        setReduced(value);
      }
    });
    const subscription = AccessibilityInfo.addEventListener("reduceMotionChanged", setReduced);
    return () => {
      live = false;
      subscription.remove();
    };
  }, []);
  return reduced;
}

/**
 * Announce a changed status to the screen reader.
 *
 * Used for the states a sighted user perceives from a moving element and a
 * screen-reader user would otherwise never learn: the dialogue turn changing
 * between listening / speaking / transcribing, and a form error appearing
 * below the field the patient has already left.
 *
 * This is the CROSS-PLATFORM half of the announcement story and the only one
 * that reaches iOS. React Native's `accessibilityLiveRegion` is declared
 * `@platform android`, and `accessibilityRole="alert"` does not substitute —
 * iOS has no alert trait and RN posts no announcement notification for it. A
 * status that matters on both platforms must come through here.
 *
 * Only transitions are announced — passing the same message twice says it
 * once — and `null` says nothing at all, so a screen that has no status does
 * not interrupt the reader.
 *
 * PHI posture: callers pass strings that are already rendered on the screen
 * the patient is looking at. This function never composes a message and must
 * never be handed anything the screen does not display.
 */
export function useLiveAnnouncement(message: string | null): void {
  const previous = useRef<string | null>(null);
  useEffect(() => {
    const { speak, remember } = nextAnnouncement(previous.current, message);
    previous.current = remember;
    if (speak !== null) {
      AccessibilityInfo.announceForAccessibility(speak);
    }
  }, [message]);
}

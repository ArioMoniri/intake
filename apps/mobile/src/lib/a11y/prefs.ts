/**
 * The two OS accessibility signals the app reacts to (INT-144).
 *
 * Kept apart from ./motion so the policy stays unit-testable without a
 * React Native runtime: this file is the thin adapter that reads the
 * platform, ./motion is what the app does with the answer.
 */
import { useEffect, useRef, useSyncExternalStore } from "react";
import { AccessibilityInfo, Platform } from "react-native";

import { createReduceMotionStore, deferredReduceMotionSource } from "@/lib/motion/policyStore";
import { reducedMotion } from "@/lib/prefs/appearance";
import { useAppearance } from "@/lib/prefs/AppearanceProvider";

import { lineStep, nextAnnouncement, type Politeness } from "./announce";

/**
 * The app's one reduce-motion store (INT-331, MOTION-2): one OS read and one
 * OS listener, whatever the number of call sites. The device adapter is
 * loaded lazily, on the first subscription.
 */
const reduceMotionStore = createReduceMotionStore(
  deferredReduceMotionSource(() =>
    import("@/lib/motion/native/reduceMotionSource").then(
      (native) => native.nativeReduceMotionSource,
    ),
  ),
);

/**
 * Whether motion should be reduced: the OS signal (iOS "Hareketi Azalt",
 * Android "Remove animations") OR the app's own switch (INT-260). The store
 * follows the OS change event and re-reads on return to the foreground, so a
 * change made in Settings while the app is backgrounded takes effect on
 * return without a restart.
 *
 * Fail-closed (INT-331, motion S-2): until the OS has answered, or when its
 * read fails, the answer is reduced. The hook used to start every call site
 * at "motion" and animate until its own read came back.
 *
 * OR, deliberately, and in one direction only: the in-app switch can ADD
 * reduced motion for a patient the OS setting never reached, and can never
 * take it away from a patient who asked the OS for it. The call sites are
 * untouched — the policy moved, not the callers. Reanimated takes the same
 * answer through the root's ReducedMotionConfig (src/app/_layout.tsx).
 */
export function useReducedMotion(): boolean {
  const { prefs } = useAppearance();
  const os = useSyncExternalStore(
    reduceMotionStore.subscribe,
    reduceMotionStore.getSnapshot,
    // Static web rendering has no OS to ask: unknown, so reduced.
    reduceMotionStore.getSnapshot,
  );
  return reducedMotion(prefs.reduceMotion, os);
}

/**
 * Announce a changed status to the screen reader.
 *
 * Used for the states a sighted user perceives from a moving element and a
 * screen-reader user would otherwise never learn: the dialogue turn changing
 * between listening / speaking / transcribing.
 *
 * Such a state has NO line of its own to carry a live region, so this posts
 * on both platforms. An error or status that IS a line on screen goes
 * through `AnnouncedText` / `AnnouncedRegion` (src/components/Announced.tsx)
 * instead, which pairs the Android live region with `useLineAnnouncement`
 * below; using this hook beside a live region says the line twice.
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

/**
 * The iOS half of an error or status LINE (INT-362; WCAG 3.3.1, 4.1.3).
 *
 * React Native's `accessibilityLiveRegion` is declared `@platform android`,
 * and `accessibilityRole="alert"` does not substitute — iOS has no alert trait
 * and RN posts no announcement for it. So a line whose only channel is its
 * live region is silent under VoiceOver. This hook is the other half: on iOS
 * it posts the line when it appears or changes — assertive lines interrupt,
 * polite ones queue — and on Android it posts nothing, because the line's own
 * live region is already what TalkBack reads.
 *
 * Only transitions are announced, and an empty or absent message says
 * nothing (./announce `lineStep`, which decides all of it and is tested).
 *
 * Called only by src/components/Announced.tsx, which also sets the live
 * region, so the two halves cannot be separated at a call site.
 *
 * PHI posture: the message is the line the screen is showing, as spoken; it is
 * posted to the OS screen reader and nowhere else — never logged (invariant 6).
 */
export function useLineAnnouncement(message: string | null, politeness: Politeness): void {
  const previous = useRef<string | null>(null);
  useEffect(() => {
    const { post, remember } = lineStep(previous.current, message, Platform.OS, politeness);
    previous.current = remember;
    if (post !== null) {
      AccessibilityInfo.announceForAccessibilityWithOptions(post.text, post.options);
    }
  }, [message, politeness]);
}

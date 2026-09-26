/**
 * INT-331: the device half of the reduce-motion store (MOTION-2). It reads the
 * OS setting (iOS "Hareketi Azalt", Android "Remove animations") and reports
 * a return to the foreground. Every rule about the answer lives in
 * ../policyStore.ts, where the node suite can hold it.
 *
 * lib/a11y/prefs.ts reaches this file ONLY through a lazy `import()`, the
 * same pattern KioskGate uses for nativeKiosk.ts, so no node-tested import
 * path pulls react-native in through it. e2e/motion.spec.ts pins both that
 * and that this is the only file in the app that asks the OS.
 */
import { AccessibilityInfo, AppState, type AppStateStatus } from "react-native";

import type { ReduceMotionSource } from "../policyStore";

export const nativeReduceMotionSource: ReduceMotionSource = {
  read: () => AccessibilityInfo.isReduceMotionEnabled(),
  onChange(cb) {
    const subscription = AccessibilityInfo.addEventListener("reduceMotionChanged", cb);
    return () => subscription.remove();
  },
  onForeground(cb) {
    // A change made in Settings while the app was away may not arrive as an
    // event, so the store re-reads on every return to `active`.
    let previous: AppStateStatus = AppState.currentState;
    const subscription = AppState.addEventListener("change", (next) => {
      if (next === "active" && previous !== "active") {
        cb();
      }
      previous = next;
    });
    return () => subscription.remove();
  },
};

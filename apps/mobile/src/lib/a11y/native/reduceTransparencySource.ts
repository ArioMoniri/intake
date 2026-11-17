/**
 * The device half of the Reduce Transparency store
 * (docs/design/apple-native/spec.md §4). It reads the iOS setting
 * (Accessibility › Display & Text Size › Reduce Transparency) and reports a
 * return to the foreground. Every rule about
 * the answer lives in lib/motion/policyStore.ts and lib/a11y/glass.ts, where
 * the node suite can hold them.
 *
 * iOS-only in React Native: on Android `isReduceTransparencyEnabled()`
 * resolves `false` and the change event never fires, which is the truth there,
 * because Android has no such setting.
 *
 * lib/a11y/prefs.ts reaches this file ONLY through a lazy `import()`, the same
 * pattern as native/reduceMotionSource.ts. e2e/nativeChrome.spec.ts pins both
 * that and that this is the only file in the app that asks the OS.
 */
import { AccessibilityInfo, AppState, type AppStateStatus } from "react-native";

import type { OsSettingSource } from "@/lib/motion/policyStore";

export const nativeReduceTransparencySource: OsSettingSource = {
  read: () => AccessibilityInfo.isReduceTransparencyEnabled(),
  onChange(cb) {
    const subscription = AccessibilityInfo.addEventListener("reduceTransparencyChanged", cb);
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

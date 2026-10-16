/**
 * The device half of the Increase Contrast store (INT-422,
 * docs/design/system-refresh.md §3). It reads the OS request for more
 * contrast and reports a return to the foreground. Which palette the answer
 * selects lives in lib/a11y/contrast.ts, where the node suite holds it.
 *
 * - iOS: Accessibility › Display & Text Size › Increase Contrast, which
 *   UIKit reports as "Darker System Colors".
 * - Android: Accessibility › High contrast text.
 *
 * React Native answers each question on its own platform only and resolves
 * `false` on the other, so the two are ORed: whichever platform this is, the
 * one that can say yes is the one asked.
 *
 * lib/a11y/prefs.ts reaches this file ONLY through a lazy `import()`, the same
 * pattern as native/reduceTransparencySource.ts. e2e/designSystem.spec.ts pins
 * both that and that this is the only file in the app that asks the OS.
 */
import { AccessibilityInfo, AppState, Platform, type AppStateStatus } from "react-native";

import type { OsSettingSource } from "@/lib/motion/policyStore";

export const nativeIncreaseContrastSource: OsSettingSource = {
  read: () =>
    Platform.OS === "android"
      ? AccessibilityInfo.isHighTextContrastEnabled()
      : AccessibilityInfo.isDarkerSystemColorsEnabled(),
  onChange(cb) {
    const subscription =
      Platform.OS === "android"
        ? AccessibilityInfo.addEventListener("highTextContrastChanged", cb)
        : AccessibilityInfo.addEventListener("darkerSystemColorsChanged", cb);
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

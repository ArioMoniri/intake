/**
 * INT-492 (approval needed): the device half of the capsule's rolling digit.
 *
 * It turns the pure answer from ../micro.ts into the entrance Reanimated runs
 * on the UI thread. Every number comes from there: the rise is ADR-038 A1's,
 * the duration and curve are the app's one fade. A digit that changed is a
 * new element (lib/intake/progressCapsule.ts keys digits by place and value),
 * so it mounts and rises into place while it fades in; nothing else moves.
 *
 * It is a timing, not a spring, so the spring allow-list in
 * e2e/motion.spec.ts does not grow for it. There is no exit: the old digit
 * leaves in the commit that replaces it. `none` registers no entrance, so
 * under Reduce Motion, on RED and without the flag the digit is simply there.
 */
import { Easing, withTiming, type EntryExitAnimationFunction } from "react-native-reanimated";

import type { NumberRoll } from "../micro";

export function rollEntering(roll: NumberRoll): EntryExitAnimationFunction | undefined {
  if (roll.kind === "none") {
    return undefined;
  }
  const { rise, fade } = roll;
  const timing = { duration: fade.durationMs, easing: Easing.bezier(...fade.easing) };
  return () => {
    "worklet";
    return {
      initialValues: { opacity: 0, transform: [{ translateY: rise }] },
      animations: {
        opacity: withTiming(1, timing),
        transform: [{ translateY: withTiming(0, timing) }],
      },
    };
  };
}

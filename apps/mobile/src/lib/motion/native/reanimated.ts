/**
 * INT-339: the device half of a mount's fade (MOTION-10). It turns the pure
 * description from ../fade.ts (via ../transients.ts) into the layout animation
 * Reanimated runs on the UI thread. Every number comes from the policy; this
 * file writes none.
 *
 * Only components import it. A pure module or a node test never does,
 * because Reanimated does not load in node (motion-verification.md §2.3).
 *
 * There is no exit builder here, on purpose: exits are instant
 * (motion-verification.md §2.1 #3), and an exit animation is the one thing
 * that keeps a removed element on screen beside its replacement.
 */
import { Easing, FadeIn } from "react-native-reanimated";

import type { FadeSpec } from "../fade";

/**
 * A mount's `entering`: opacity from 0, for the spec's duration and curve,
 * with no delay. `undefined` (reduce-motion) registers no entrance at all, so
 * the element is simply there on its first frame.
 */
export function enteringFor(spec: FadeSpec | undefined): FadeIn | undefined {
  if (spec === undefined) {
    return undefined;
  }
  return FadeIn.duration(spec.durationMs)
    .delay(spec.delayMs)
    .easing(Easing.bezier(...spec.easing));
}

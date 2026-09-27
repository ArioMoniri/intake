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
 *
 * INT-342 (MOTION-13) adds the skeleton's half: its opacity, hidden for the
 * plan's delay and then shown in one step (../reveal.ts).
 */
import { useEffect } from "react";
import {
  Easing,
  FadeIn,
  ReduceMotion,
  useAnimatedStyle,
  useSharedValue,
  withDelay,
  withTiming,
} from "react-native-reanimated";

import type { FadeSpec } from "../fade";
import type { SkeletonPlan } from "../reveal";

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

/** The one style a skeleton drives. */
interface SkeletonOpacity {
  opacity: number;
}

/**
 * A skeleton's opacity: 0 on its first frame, then 1 in one step once the
 * plan's delay has passed. It runs on the UI thread: no JS timer, and no
 * React render when the skeleton appears. It never changes again, and nothing
 * waits for it: the host removes the skeleton in the commit that brings the
 * content, whether or not it has appeared yet.
 *
 * `ReduceMotion.Never` sits on the delay alone, and it is the app's policy
 * rather than an exception to it. Under reduced motion Reanimated skips a
 * `withDelay`'s wait (src/animation/delay.ts: `now - startTime >= delayMs ||
 * animation.reduceMotion`), so under the root's `ReducedMotionConfig` every
 * skeleton would show on its first frame, however fast the load. The plan
 * keeps the delay because a wait is not movement, and the step after it is
 * `motion.duration.instant`, so nothing moves at any setting.
 */
export function useSkeletonOpacity(
  plan: SkeletonPlan,
): ReturnType<typeof useAnimatedStyle<SkeletonOpacity>> {
  const shown = useSharedValue(0);
  useEffect(() => {
    shown.set(
      withDelay(plan.delayMs, withTiming(1, { duration: plan.stepMs }), ReduceMotion.Never),
    );
  }, [shown, plan.delayMs, plan.stepMs]);
  return useAnimatedStyle(() => ({ opacity: shown.get() }));
}

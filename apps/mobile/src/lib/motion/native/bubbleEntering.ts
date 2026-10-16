/**
 * ADR-038 A1 (INT-462): the device half of a bubble's entrance.
 *
 * It turns the pure answer from ../bubbles.ts into the entrance Reanimated
 * runs on the UI thread. Every number comes from there: the rise and the
 * spring are ADR-038's, the fade is the app's one fade. This is the one module
 * in src allowed a spring (e2e/motion.spec.ts pins that and its numbers).
 *
 * - `spring`: opacity 0 to 1 on the fade, and the rise settling to 0 on the
 *   critically damped spring, which cannot overshoot.
 * - `fade`: Reduce Motion's substitute, opacity only. It runs with
 *   `ReduceMotion.Never` because the root's ReducedMotionConfig would
 *   otherwise skip it, and ADR-038 keeps this one fade under Reduce Motion.
 * - `none`: no entrance; the bubble is simply there.
 *
 * There is no exit: a bubble leaves in the commit that removes it.
 */
import {
  Easing,
  FadeIn,
  ReduceMotion,
  withSpring,
  withTiming,
  type EntryExitAnimationFunction,
} from "react-native-reanimated";

import { BUBBLE_SPRING, type BubbleEntrance } from "../bubbles";

export function bubbleEntering(
  entrance: BubbleEntrance,
): FadeIn | EntryExitAnimationFunction | undefined {
  if (entrance.kind === "none") {
    return undefined;
  }
  const { fade } = entrance;
  const easing = Easing.bezier(...fade.easing);
  if (entrance.kind === "fade") {
    return FadeIn.duration(fade.durationMs)
      .delay(fade.delayMs)
      .easing(easing)
      .reduceMotion(ReduceMotion.Never);
  }
  const { rise } = entrance;
  // The spring only exists when the app's policy is not reduced (../bubbles),
  // so it runs as granted; MOTION-2 forbids following the OS alone.
  const spring = { ...BUBBLE_SPRING, reduceMotion: ReduceMotion.Never };
  const timing = { duration: fade.durationMs, easing, reduceMotion: ReduceMotion.Never };
  return () => {
    "worklet";
    return {
      initialValues: { opacity: 0, transform: [{ translateY: rise }] },
      animations: {
        opacity: withTiming(1, timing),
        transform: [{ translateY: withSpring(0, spring) }],
      },
    };
  };
}

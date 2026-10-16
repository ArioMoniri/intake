/**
 * ADR-038 A3 (INT-473): the device half of the detent sheet's motion.
 *
 * It turns the pure answers from ../sheet.ts into what Reanimated runs on the
 * UI thread, and writes no number of its own: the spring is A1's, the fade is
 * the app's one fade. It is the second module in src allowed a spring, as
 * ADR-038's consequences foresaw (e2e/motion.spec.ts names it).
 *
 * - `sheetEntering`: the sheet rises from below the frame on the spring, or,
 *   under Reduce Motion, fades in for 120 ms.
 * - `sheetExiting`: a patient's dismissal falls away on the spring; an
 *   instant close (privacy, RED, Reduce Motion) registers no exit. Reanimated
 *   reads the exit when the view mounts or updates, so DetentSheet hides the
 *   sheet in the commit that closes it, which registers this none, and
 *   unmounts it in the next (INT-551, ../sheet `sheetMount`).
 * - `settleTo`: after a drag, the sheet settles on the spring, or snaps.
 *
 * Every animation runs with `ReduceMotion.Never`: the policy in ../sheet.ts
 * has already decided what Reduce Motion keeps, and the root's
 * ReducedMotionConfig would otherwise drop the fade it keeps.
 */
import {
  Easing,
  FadeIn,
  ReduceMotion,
  withSpring,
  type EntryExitAnimationFunction,
  type SharedValue,
} from "react-native-reanimated";

import { SHEET_SPRING, type SheetPresent } from "../sheet";

const SPRING = { ...SHEET_SPRING, reduceMotion: ReduceMotion.Never };

export function sheetEntering(
  present: SheetPresent,
  below: number,
): FadeIn | EntryExitAnimationFunction {
  if (present.kind === "fade") {
    return FadeIn.duration(present.fade.durationMs)
      .easing(Easing.bezier(...present.fade.easing))
      .reduceMotion(ReduceMotion.Never);
  }
  return () => {
    "worklet";
    return {
      initialValues: { transform: [{ translateY: below }] },
      animations: { transform: [{ translateY: withSpring(0, SPRING) }] },
    };
  };
}

export function sheetExiting(
  close: "spring" | "instant",
  below: number,
): EntryExitAnimationFunction | undefined {
  if (close === "instant") {
    return undefined;
  }
  return () => {
    "worklet";
    return {
      initialValues: { transform: [{ translateY: 0 }] },
      animations: { transform: [{ translateY: withSpring(below, SPRING) }] },
    };
  };
}

export function settleTo(
  position: SharedValue<number>,
  target: number,
  settle: "spring" | "snap",
): void {
  position.set(settle === "spring" ? withSpring(target, SPRING) : target);
}

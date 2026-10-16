/**
 * ADR-037 P1 (INT-492): the device half of the press scale.
 *
 * The filled action scales to ../micro.ts's PRESS_SCALE while a finger is
 * down and returns to rest on release, on the app's one critically damped
 * spring, so a press released mid-travel carries its velocity and never
 * jumps or overshoots. The commit is unchanged: it happens on release, and
 * nothing waits on the spring. Every number comes from the pure module; the
 * one written here is the rest scale.
 *
 * `none` (no opt-in, Reduce Motion, RED) never springs and holds the rest
 * scale, so the press keeps only its instant opacity step. The spring runs
 * with `ReduceMotion.Never` because it exists only when the app's own policy
 * is not reduced (MOTION-2: never follow the OS alone).
 */
import type { ViewStyle } from "react-native";
import {
  ReduceMotion,
  useAnimatedStyle,
  useSharedValue,
  withSpring,
} from "react-native-reanimated";

import type { PressScale } from "../micro";

export function usePressScale(press: PressScale) {
  const scale = useSharedValue(1);
  const style = useAnimatedStyle<ViewStyle>(() => ({ transform: [{ scale: scale.value }] }));
  const settle = (to: number) => {
    if (press.kind === "none") {
      scale.value = 1;
      return;
    }
    scale.value = withSpring(to, { ...press.spring, reduceMotion: ReduceMotion.Never });
  };
  return {
    style,
    onPressIn: () => settle(press.kind === "scale" ? press.to : 1),
    onPressOut: () => settle(1),
  };
}

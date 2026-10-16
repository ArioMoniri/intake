/**
 * ADR-037 P1 (INT-492): the frame that lets a filled action give under the
 * finger. PrimaryButton renders its Pressable through it only when the call
 * site opts in (`pressScale`), and only the typed steps' actions and the send
 * do; e2e/progressMicro.spec.ts holds that no
 * consent, gate, RED or instrument control can.
 *
 * The frame scales; the Pressable inside keeps its own instant opacity step,
 * its role, its label and its commit-on-release. Under Reduce Motion the
 * policy answers `none`, so nothing scales and the opacity step is the press.
 * The typed lane has no RED channel of its own: a RED paints as the root
 * layer above every screen (ADR-033 §5), so `redPresented` is false here, as
 * it is for the dialogue's stage motion.
 */
import { type ReactNode } from "react";
import Animated from "react-native-reanimated";

import { useReducedMotion } from "@/lib/a11y/prefs";
import { pressScale } from "@/lib/motion/micro";
import { usePressScale } from "@/lib/motion/native/pressScale";

export interface PressHandlers {
  readonly onPressIn: () => void;
  readonly onPressOut: () => void;
}

export function PressScale({ children }: { children: (handlers: PressHandlers) => ReactNode }) {
  const reduce = useReducedMotion();
  const press = usePressScale(pressScale({ enabled: true, reduce, redPresented: false }));
  return (
    <Animated.View style={press.style}>
      {children({ onPressIn: press.onPressIn, onPressOut: press.onPressOut })}
    </Animated.View>
  );
}

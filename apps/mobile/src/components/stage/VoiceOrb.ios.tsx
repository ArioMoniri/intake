/**
 * The stage's voice orb, drawn natively in SwiftUI (chat redesign prototype).
 *
 * A living sphere made of two counter-turning angular gradients, softened by
 * blur, with a specular highlight. Unless transparency is reduced, it sits
 * under a clear Liquid Glass lens. How it moves comes from `stageOrbMotion`
 * (lib/stage/orb.ts), and every bound is pinned in orb.test.ts. SwiftUI runs
 * the loops on the render server, so a busy JS thread does not stall them.
 *
 * Decoration only: hidden from the accessibility tree. The stage's caption
 * carries the state in words.
 */
import { useEffect, useState } from "react";
import { Circle, Host, ZStack } from "@expo/ui/swift-ui";
import {
  Animation,
  animation,
  blur,
  foregroundStyle,
  frame,
  glassEffect,
  offset,
  opacity,
  rotationEffect,
  scaleEffect,
} from "@expo/ui/swift-ui/modifiers";
import { View } from "react-native";

import type { StageOrbMotion } from "@/lib/stage/orb";
import type { StagePalette } from "@/lib/stage/palette";

/** Loops run until the view goes away; SwiftUI needs a finite count. */
const FOREVER = 100_000;

interface VoiceOrbProps {
  readonly size: number;
  readonly motion: StageOrbMotion;
  readonly palette: StagePalette;
  /** The patient's voice level, 0 to 1 (listening only). */
  readonly level: number;
  /** False under Reduce Transparency: no glass lens. */
  readonly glass: boolean;
}

export function VoiceOrb({ size, motion, palette, level, glass }: VoiceOrbProps) {
  // Each loop starts by moving its value once the native view is on screen;
  // the animation modifier keyed on that value then repeats it. A change made
  // in the same frame as the mount reaches SwiftUI as the initial value, so
  // nothing animates. Hence the short wait.
  const [turn, setTurn] = useState(0);
  const [breath, setBreath] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => {
      setTurn(motion.rotationPeriodS === null ? 0 : 360);
      setBreath(motion.breathe !== null);
    }, 350);
    return () => clearTimeout(timer);
  }, [motion.rotationPeriodS, motion.breathe]);

  if (!motion.visible) {
    return null;
  }
  const box = size * 1.8;
  const levelScale = 1 + Math.min(1, Math.max(0, level)) * motion.levelGain;
  const breatheScale = breath && motion.breathe !== null ? motion.breathe.scale : 1;
  const spin =
    motion.rotationPeriodS === null
      ? []
      : [
          animation(
            Animation.linear({ duration: motion.rotationPeriodS }).repeat({
              repeatCount: FOREVER,
              autoreverses: false,
            }),
            turn,
          ),
        ];
  const counterSpin =
    motion.rotationPeriodS === null
      ? []
      : [
          animation(
            Animation.linear({ duration: motion.rotationPeriodS * 1.6 }).repeat({
              repeatCount: FOREVER,
              autoreverses: false,
            }),
            turn,
          ),
        ];
  const breathe =
    motion.breathe === null
      ? []
      : [
          animation(
            Animation.easeInOut({ duration: motion.breathe.periodS / 2 }).repeat({
              repeatCount: FOREVER,
              autoreverses: true,
            }),
            breath,
          ),
        ];
  const [a, b, c, d, e] = palette.orb;
  return (
    <View
      pointerEvents="none"
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={{ width: box, height: box }}
    >
      <Host style={{ width: box, height: box }}>
        <ZStack
          modifiers={[
            scaleEffect(levelScale),
            animation(Animation.spring({ response: 0.28, dampingFraction: 0.86 }), levelScale),
          ]}
        >
          <ZStack modifiers={[scaleEffect(breatheScale), ...breathe]}>
            {palette.glow !== null ? (
              <Circle
                modifiers={[
                  foregroundStyle({
                    type: "radialGradient",
                    colors: [palette.glow, `${palette.glow}00`],
                    center: { x: 0.5, y: 0.5 },
                    startRadius: 0,
                    endRadius: box / 2,
                  }),
                  frame({ width: box, height: box }),
                  blur(18),
                  opacity(motion.glowOpacity),
                ]}
              />
            ) : null}
            <Circle
              modifiers={[
                foregroundStyle({
                  type: "angularGradient",
                  colors: [a, b, c, d, e],
                  center: { x: 0.5, y: 0.5 },
                }),
                frame({ width: size, height: size }),
                blur(size * 0.06),
                rotationEffect(turn),
                ...spin,
              ]}
            />
            <Circle
              modifiers={[
                foregroundStyle({
                  type: "angularGradient",
                  colors: [d, `${b}00`, c, `${d}00`, b, d],
                  center: { x: 0.5, y: 0.5 },
                }),
                frame({ width: size * 0.82, height: size * 0.82 }),
                blur(size * 0.08),
                rotationEffect(-turn),
                ...counterSpin,
              ]}
            />
            <Circle
              modifiers={[
                foregroundStyle({
                  type: "radialGradient",
                  colors: ["#FFFFFFCC", "#FFFFFF00"],
                  center: { x: 0.5, y: 0.5 },
                  startRadius: 0,
                  endRadius: size * 0.32,
                }),
                frame({ width: size * 0.64, height: size * 0.64 }),
                offset({ x: -size * 0.12, y: -size * 0.14 }),
                blur(6),
                opacity(0.75),
              ]}
            />
            {glass ? (
              <Circle
                modifiers={[
                  foregroundStyle("#FFFFFF01"),
                  frame({ width: size, height: size }),
                  glassEffect({ glass: { variant: "clear" }, shape: "circle" }),
                ]}
              />
            ) : null}
          </ZStack>
        </ZStack>
      </Host>
    </View>
  );
}

/**
 * The stage orb's body, drawn natively in SwiftUI (ADR-039 S1 and S2,
 * INT-466). PresenceOrb renders it; it decides nothing itself.
 *
 * It is a sphere of two counter-turning angular gradients, softened by blur,
 * with a soft glow behind it, a still specular highlight and a clear Liquid
 * Glass lens over it. The lens is the one clear glass on the stage: it sits
 * on its own gradient with nothing on top.
 *
 * Every period comes from the S1 policy (`stageOrbMotion`), and none is a
 * literal of its own. SwiftUI runs the loops on the render server, so a busy
 * JS thread never stalls them. The voice level is not here: PresenceOrb
 * scales this whole body from the sampler's shared value, so a level sample
 * renders nothing.
 *
 * Decoration only: hidden from the accessibility tree. The turn state is
 * written on screen and announced.
 */
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
import { useState } from "react";
import { View } from "react-native";

import type { StageOrbMotion } from "@/lib/stage/orb";
import type { StagePalette } from "@/lib/stage/palette";

/** Loops run until the view goes away; SwiftUI takes a finite count. */
const FOREVER = 100_000;

/** The counter-turning layer turns this much slower than the front one. */
const COUNTER_TURN = 1.6;

interface VoiceOrbProps {
  readonly size: number;
  readonly motion: StageOrbMotion;
  readonly palette: StagePalette;
  /** False under Reduce Transparency: no lens, no glow. */
  readonly glass: boolean;
}

export function VoiceOrb(props: VoiceOrbProps) {
  // A SwiftUI loop runs from the moment its value first changes, with the
  // animation it had then; a later change of period, with the value already
  // moved, is not a change SwiftUI animates. So each motion (one set of
  // periods) is its own native view, and a new state starts its loops fresh.
  const { rotationPeriodS, breathe } = props.motion;
  const loops = `${rotationPeriodS ?? "still"}:${breathe?.periodS ?? "still"}`;
  return <OrbBody key={loops} {...props} />;
}

function OrbBody({ size, motion, palette, glass }: VoiceOrbProps) {
  // Each loop starts by moving its value once SwiftUI has laid the view out.
  // A value set in the pass that creates the native view reaches SwiftUI as
  // its initial value, and nothing animates; the Host reports its content's
  // first layout, which is SwiftUI's own "the view is there".
  const [appeared, setAppeared] = useState(false);
  const turn = appeared && motion.rotationPeriodS !== null ? 360 : 0;
  const breath = appeared && motion.breathe !== null;

  if (!motion.visible) {
    return null;
  }
  const box = size * 1.8;
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
            Animation.linear({ duration: motion.rotationPeriodS * COUNTER_TURN }).repeat({
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
      // The glow draws past the sphere; the layout box is the sphere's own
      // size, so the dock keeps the room the orb shows rather than its glow.
      style={{ width: box, height: box, margin: -(box - size) / 2 }}
    >
      <Host style={{ width: box, height: box }} onLayoutContent={() => setAppeared(true)}>
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
      </Host>
    </View>
  );
}

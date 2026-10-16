/**
 * The stage orb's body, drawn natively in SwiftUI (ADR-039 S1 and S2,
 * INT-466). PresenceOrb renders it; it decides nothing itself.
 *
 * The orb is the lens (ADR-039 amendment, INT-491; owner, 16 Oct 2026:
 * "orb=lens"): a deep sphere lit from the top left, a darker rim, a light that
 * travels round the rim and a fainter, slower one the same way, a crisp edge,
 * a still specular highlight, a soft glow behind it, and a clear Liquid Glass
 * lens over it. The lens is the one clear glass on the stage: it sits on its
 * own gradient with nothing on top, and only where the plan says glass.
 *
 * `classic` (a development build only, lib/stage/orbVariants) draws the
 * earlier sphere: two angular gradients, softened by blur, now turning the
 * same way (the owner's "FIXY"), so their pattern repeats below the 0.2 Hz
 * band S1 cites.
 *
 * Every period comes from the S1 policy (`stageOrbMotion`), and none is a
 * literal of its own. SwiftUI runs the loops on the render server, so a busy
 * JS thread never stalls them. The voice level is not here: PresenceOrb
 * scales this whole body from the sampler's shared value, so a level sample
 * renders nothing.
 *
 * Decoration only: hidden from the accessibility tree. The turn state is
 * written on screen and announced.
 *
 * The lens takes its plan from `lensPlan`, built from the same S1 motion, so
 * it is still whenever the sphere was (idle, rest, retry, Reduce Motion, a
 * RED) and keeps the same bounds; every period is the plan's.
 */
import { Circle, Host, Mask, ZStack } from "@expo/ui/swift-ui";
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
  strokeBorder,
} from "@expo/ui/swift-ui/modifiers";
import { useState } from "react";
import { View } from "react-native";

import { STAGE_ORB_SECOND_LAYER, type StageOrbMotion } from "@/lib/stage/orb";
import { ORB_VARIANT_DEFAULT, lensPlan, type OrbVariant, type Turn } from "@/lib/stage/orbVariants";
import type { StagePalette } from "@/lib/stage/palette";

/** Loops run until the view goes away; SwiftUI takes a finite count. */
const FOREVER = 100_000;

/** The glow's blur radius, in points. */
const GLOW_BLUR = 18;

interface VoiceOrbProps {
  readonly size: number;
  readonly motion: StageOrbMotion;
  readonly palette: StagePalette;
  /** False under Reduce Transparency: no lens, no glow. */
  readonly glass: boolean;
  /** INT-491: the build's body; absent is the lens, `classic` the earlier sphere. */
  readonly variant?: OrbVariant;
}

export function VoiceOrb(props: VoiceOrbProps) {
  // A SwiftUI loop runs from the moment its value first changes, with the
  // animation it had then; a later change of period, with the value already
  // moved, is not a change SwiftUI animates. So each motion (one set of
  // periods) is its own native view, and a new state starts its loops fresh.
  const { rotationPeriodS, breathe } = props.motion;
  const loops = `${rotationPeriodS ?? "still"}:${breathe?.periodS ?? "still"}`;
  const variant = props.variant ?? ORB_VARIANT_DEFAULT;
  if (variant === "classic") {
    return <OrbBody key={loops} {...props} />;
  }
  return <LensOrb key={`lens:${loops}`} {...props} />;
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
  // The glow is drawn inside a host with room around it for its blur: a blur
  // that reaches the host's edge is cut off there, and the cut shows as a
  // straight line in the wash (INT-464, found on the welcome capture).
  const glowBox = size * 1.8;
  const box = glowBox + GLOW_BLUR * 4;
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
  // The second layer turns the same way, slower (the owner's "FIXY"): turned
  // against the first, the pair repeated near 0.2 Hz.
  const secondSpin =
    motion.rotationPeriodS === null
      ? []
      : [
          animation(
            Animation.linear({
              duration: motion.rotationPeriodS * STAGE_ORB_SECOND_LAYER.periodFactor,
            }).repeat({
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
      {/* `ignoreSafeArea`: the host's frame runs past the sphere for the
          glow, and where it overlaps a safe-area inset (the status bar above
          the welcome mark, the home indicator below the dialogue's dock)
          SwiftUI would otherwise push the drawing off the sphere's centre. */}
      <Host
        style={{ width: box, height: box }}
        ignoreSafeArea="all"
        onLayoutContent={() => setAppeared(true)}
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
                  endRadius: glowBox / 2,
                }),
                frame({ width: glowBox, height: glowBox }),
                blur(GLOW_BLUR),
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
              rotationEffect(turn * STAGE_ORB_SECOND_LAYER.direction),
              ...secondSpin,
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

/** Loops of the lens: linear and endless, each period the plan's. */
function turnLoop(turn: Turn | null, value: number) {
  if (turn === null) {
    return [];
  }
  const { periodS } = turn;
  return [
    animation(
      Animation.linear({ duration: periodS }).repeat({
        repeatCount: FOREVER,
        autoreverses: false,
      }),
      value,
    ),
  ];
}

/** A breath: eased out and back, its full period the plan's. */
function breathLoop(periodS: number | null, value: boolean) {
  if (periodS === null) {
    return [];
  }
  return [
    animation(
      Animation.easeInOut({ duration: periodS / 2 }).repeat({
        repeatCount: FOREVER,
        autoreverses: true,
      }),
      value,
    ),
  ];
}

/** Where a light stands: at rest, or one full turn on once it moves. */
function angleOf(turn: Turn | null, appeared: boolean): number {
  return appeared && turn !== null ? 360 : 0;
}

const CENTRE = { x: 0.5, y: 0.5 };

/** INT-491: the lens, the orb ADR-039 names, drawn from its plan. */
function LensOrb({ size, motion, palette, glass }: VoiceOrbProps) {
  // The loops start once SwiftUI has laid the view out, as the sphere's do.
  const [appeared, setAppeared] = useState(false);
  const plan = lensPlan(motion, { glass });
  if (!plan.visible) {
    return null;
  }
  const glowBox = size * 1.8;
  const box = glowBox + GLOW_BLUR * 4;
  const breath = appeared && plan.breathe !== null;
  const [a, b, c, d] = palette.orb;
  const sweep = angleOf(plan.sweep, appeared);
  const caustic = angleOf(plan.caustic, appeared);
  const square = frame({ width: size, height: size });
  return (
    <View
      pointerEvents="none"
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={{ width: box, height: box, margin: -(box - size) / 2 }}
    >
      <Host
        style={{ width: box, height: box }}
        ignoreSafeArea="all"
        onLayoutContent={() => setAppeared(true)}
      >
        <ZStack
          modifiers={[
            scaleEffect(breath && plan.breathe !== null ? plan.breathe.scale : 1),
            ...breathLoop(plan.breathe?.periodS ?? null, breath),
          ]}
        >
          {palette.glow !== null ? (
            <Circle
              modifiers={[
                foregroundStyle({
                  type: "radialGradient",
                  colors: [palette.glow, `${palette.glow}00`],
                  center: CENTRE,
                  startRadius: 0,
                  endRadius: glowBox / 2,
                }),
                frame({ width: glowBox, height: glowBox }),
                blur(GLOW_BLUR),
                opacity(plan.glowOpacity),
              ]}
            />
          ) : null}
          <Circle
            modifiers={[
              foregroundStyle({
                type: "radialGradient",
                colors: [d, c, b, a],
                center: { x: 0.36, y: 0.3 },
                startRadius: 0,
                endRadius: size * 0.82,
              }),
              square,
            ]}
          />
          <Circle
            modifiers={[
              foregroundStyle({
                type: "radialGradient",
                colors: [`${a}00`, `${a}00`, `${a}66`],
                center: CENTRE,
                startRadius: 0,
                endRadius: size * 0.5,
              }),
              square,
            ]}
          />
          {/* The rim light rests low on the right, opposite the sheen, where a
              lit glass ball catches the light coming through it. */}
          <RimLight
            size={size}
            width={size * 0.08}
            colors={[
              "#FFFFFF00",
              "#FFFFFFD9",
              "#FFFFFF00",
              "#FFFFFF00",
              "#FFFFFF00",
              "#FFFFFF00",
              "#FFFFFF00",
            ]}
            angle={sweep}
            turn={plan.sweep}
          />
          <RimLight
            size={size}
            width={size * 0.05}
            colors={[`${d}00`, `${d}00`, `${d}00`, `${d}B3`, `${d}00`, `${d}00`]}
            angle={caustic}
            turn={plan.caustic}
          />
          <Sheen size={size} />
          <Circle
            modifiers={[
              foregroundStyle("#FFFFFF00"),
              square,
              strokeBorder({
                shape: "circle",
                color: "#FFFFFF8C",
                style: { lineWidth: size * plan.rim },
              }),
            ]}
          />
          {plan.lens ? (
            <Circle
              modifiers={[
                foregroundStyle("#FFFFFF01"),
                square,
                glassEffect({ glass: { variant: "clear" }, shape: "circle" }),
              ]}
            />
          ) : null}
        </ZStack>
      </Host>
    </View>
  );
}

/** A band of light on the rim: a turning gradient seen through a ring. */
function RimLight({
  size,
  width,
  colors,
  angle,
  turn,
}: {
  readonly size: number;
  readonly width: number;
  readonly colors: readonly string[];
  readonly angle: number;
  readonly turn: Turn | null;
}) {
  const square = frame({ width: size, height: size });
  return (
    <Mask modifiers={[square, blur(width * 0.3)]}>
      <Circle
        modifiers={[
          foregroundStyle({ type: "angularGradient", colors: [...colors], center: CENTRE }),
          square,
          rotationEffect(angle),
          ...turnLoop(turn, angle),
        ]}
      />
      <Mask.Content>
        <Circle
          modifiers={[
            foregroundStyle("#FFFFFF00"),
            square,
            strokeBorder({ shape: "circle", color: "#FFFFFF", style: { lineWidth: width } }),
          ]}
        />
      </Mask.Content>
    </Mask>
  );
}

/** The still specular highlight, up and to the left, as on the sphere. */
function Sheen({ size }: { readonly size: number }) {
  return (
    <Circle
      modifiers={[
        foregroundStyle({
          type: "radialGradient",
          colors: ["#FFFFFFCC", "#FFFFFF00"],
          center: CENTRE,
          startRadius: 0,
          endRadius: size * 0.32,
        }),
        frame({ width: size * 0.64, height: size * 0.64 }),
        offset({ x: -size * 0.12, y: -size * 0.14 }),
        blur(6),
        opacity(0.75),
      ]}
    />
  );
}

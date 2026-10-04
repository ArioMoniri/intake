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
 *
 * INT-491: behind the build's flag (lib/stage/orbVariants, off by default)
 * the same orb can draw one of three other bodies: a fluid blob, a particle
 * field or a refined glass lens. Each takes its plan from `orbVariantPlan`,
 * built from the same S1 motion, so each is still whenever the sphere is
 * (idle, rest, retry, Reduce Motion, a RED) and keeps the same bounds; every
 * period is the plan's. Off, the sphere is drawn exactly as before. Every
 * gradient, glow and lens of the variants is drawn here, so gradients stay in
 * the two stage drawing files (ADR-039 S2); their plain parts (the loops, a
 * lobe, a ring of points) are in VoiceOrbParts.tsx. Only the lens draws the
 * clear lens, and only where the plan says glass.
 */
import { Circle, Host, Mask, Rectangle, ZStack } from "@expo/ui/swift-ui";
import {
  Animation,
  animation,
  blur,
  contrast,
  foregroundStyle,
  frame,
  glassEffect,
  luminanceToAlpha,
  offset,
  opacity,
  rotationEffect,
  scaleEffect,
  strokeBorder,
} from "@expo/ui/swift-ui/modifiers";
import { useState } from "react";
import { View } from "react-native";

import type { StageOrbMotion } from "@/lib/stage/orb";
import {
  ORB_VARIANT_OFF,
  orbVariantPlan,
  type BlobBody as BlobPlan,
  type DrawnVariant,
  type FieldBody as FieldPlan,
  type LensBody as LensPlan,
  type OrbVariant,
  type Turn,
  type VariantPlan,
} from "@/lib/stage/orbVariants";
import type { StagePalette } from "@/lib/stage/palette";

import { Lobe, Orbit, angleOf, breathLoop, turnLoop } from "./VoiceOrbParts";

/** Loops run until the view goes away; SwiftUI takes a finite count. */
const FOREVER = 100_000;

/** The counter-turning layer turns this much slower than the front one. */
const COUNTER_TURN = 1.6;

/** The glow's blur radius, in points. */
const GLOW_BLUR = 18;

interface VoiceOrbProps {
  readonly size: number;
  readonly motion: StageOrbMotion;
  readonly palette: StagePalette;
  /** False under Reduce Transparency: no lens, no glow. */
  readonly glass: boolean;
  /** INT-491: the body the build's flag chose; absent or `classic` is the sphere. */
  readonly variant?: OrbVariant;
}

export function VoiceOrb(props: VoiceOrbProps) {
  // A SwiftUI loop runs from the moment its value first changes, with the
  // animation it had then; a later change of period, with the value already
  // moved, is not a change SwiftUI animates. So each motion (one set of
  // periods) is its own native view, and a new state starts its loops fresh.
  const { rotationPeriodS, breathe } = props.motion;
  const loops = `${rotationPeriodS ?? "still"}:${breathe?.periodS ?? "still"}`;
  const variant = props.variant ?? ORB_VARIANT_OFF;
  if (variant === ORB_VARIANT_OFF) {
    return <OrbBody key={loops} {...props} />;
  }
  return <VariantBody key={`${variant}:${loops}`} {...props} variant={variant} />;
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

const CENTRE = { x: 0.5, y: 0.5 };

interface PartProps {
  readonly size: number;
  readonly palette: StagePalette;
  readonly appeared: boolean;
}

/** INT-491: a variant's body, drawn from its plan. */
function VariantBody(props: VoiceOrbProps & { readonly variant: DrawnVariant }) {
  const { size, motion, palette, glass, variant } = props;
  // The loops start once SwiftUI has laid the view out, as the sphere's do.
  const [appeared, setAppeared] = useState(false);
  const plan = orbVariantPlan(variant, motion, { glass });
  if (!plan.visible) {
    return null;
  }
  const glowBox = size * 1.8;
  const box = glowBox + GLOW_BLUR * 4;
  const breathPeriodS = plan.breathe?.periodS ?? null;
  const breath = appeared && plan.breathe !== null;
  const part = { size, palette, appeared };
  const { body } = plan;
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
            ...breathLoop(breathPeriodS, breath),
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
          {body.kind === "blob" ? (
            <BlobBody body={body} breathPeriodS={breathPeriodS} {...part} />
          ) : body.kind === "field" ? (
            <FieldBody body={body} {...part} />
          ) : (
            <LensBody body={body} plan={plan} {...part} />
          )}
        </ZStack>
      </Host>
    </View>
  );
}

/**
 * The fluid blob: the sphere's turning colour, cut to a shape that flows.
 * The shape is a core and four lobes in white on black, melted by a blur and
 * cut again by a steep contrast, then read as the mask's alpha.
 */
function BlobBody({
  body,
  breathPeriodS,
  size,
  palette,
  appeared,
}: PartProps & { readonly body: BlobPlan; readonly breathPeriodS: number | null }) {
  const [a, b, c, d, e] = palette.orb;
  const fill = angleOf(body.fill, appeared);
  const second = angleOf(body.secondFill, appeared);
  const square = frame({ width: size, height: size });
  const core = size * body.core * 2;
  return (
    <Mask modifiers={[square]}>
      <ZStack modifiers={[square]}>
        <Circle
          modifiers={[
            foregroundStyle({ type: "angularGradient", colors: [a, b, c, d, e], center: CENTRE }),
            square,
            blur(size * 0.06),
            rotationEffect(fill),
            ...turnLoop(body.fill, fill),
          ]}
        />
        <Circle
          modifiers={[
            foregroundStyle({
              type: "angularGradient",
              colors: [d, `${b}00`, c, `${d}00`, b, d],
              center: CENTRE,
            }),
            frame({ width: size * 0.82, height: size * 0.82 }),
            blur(size * 0.08),
            rotationEffect(second),
            ...turnLoop(body.secondFill, second),
          ]}
        />
        <Sheen size={size} />
      </ZStack>
      <Mask.Content>
        <ZStack
          modifiers={[
            square,
            blur(size * body.softness),
            contrast(body.edge),
            luminanceToAlpha(),
            // SwiftUI blurs at a lower resolution, and the steep contrast
            // shows its steps; a hairline blur smooths the cut edge again.
            blur(size * body.smoothing),
          ]}
        >
          <Rectangle modifiers={[foregroundStyle("#000000"), square]} />
          <Circle modifiers={[foregroundStyle("#FFFFFF"), frame({ width: core, height: core })]} />
          {body.lobes.map((lobe) => (
            <Lobe
              key={lobe.angle}
              lobe={lobe}
              size={size}
              appeared={appeared}
              breathPeriodS={breathPeriodS}
            />
          ))}
        </ZStack>
      </Mask.Content>
    </Mask>
  );
}

/** The particle field: face-on rings of points turning round a soft nucleus. */
function FieldBody({ body, size, palette, appeared }: PartProps & { readonly body: FieldPlan }) {
  const [a, b, c, d] = palette.orb;
  // The ring inks are the orb's stops that hold up on both washes; the
  // palest stop is the nucleus's light.
  const inks = [c, b, c, a];
  const nucleus = size * body.nucleus;
  return (
    <ZStack modifiers={[frame({ width: size, height: size })]}>
      <Circle
        modifiers={[
          foregroundStyle({
            type: "radialGradient",
            colors: [d, `${b}B3`, `${a}00`],
            center: CENTRE,
            startRadius: 0,
            endRadius: nucleus,
          }),
          frame({ width: nucleus * 2, height: nucleus * 2 }),
          blur(size * 0.02),
        ]}
      />
      {body.orbits.map((orbit, i) => (
        <Orbit
          key={orbit.radius}
          orbit={orbit}
          ink={inks[i % inks.length]}
          size={size}
          appeared={appeared}
        />
      ))}
    </ZStack>
  );
}

/**
 * The refined lens: a deep sphere lit from above, a light that sweeps its rim
 * and a fainter, slower one, a crisp edge, and the clear lens over it.
 */
function LensBody({
  body,
  plan,
  size,
  palette,
  appeared,
}: PartProps & { readonly body: LensPlan; readonly plan: VariantPlan }) {
  const [a, b, c, d] = palette.orb;
  const sweep = angleOf(body.sweep, appeared);
  const caustic = angleOf(body.caustic, appeared);
  const square = frame({ width: size, height: size });
  return (
    <ZStack modifiers={[square]}>
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
        turn={body.sweep}
      />
      <RimLight
        size={size}
        width={size * 0.05}
        colors={[`${d}00`, `${d}00`, `${d}00`, `${d}B3`, `${d}00`, `${d}00`]}
        angle={caustic}
        turn={body.caustic}
      />
      <Sheen size={size} />
      <Circle
        modifiers={[
          foregroundStyle("#FFFFFF00"),
          square,
          strokeBorder({
            shape: "circle",
            color: "#FFFFFF8C",
            style: { lineWidth: size * body.rim },
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

/**
 * The orb variants' plain parts (INT-491): the loops, a blob's lobe and a
 * field's ring of points. iOS only: VoiceOrb.ios.tsx is the one importer, and
 * it draws every gradient, the glow and the lens itself (ADR-039 S2). Nothing
 * here is coloured by a gradient or made of glass.
 *
 * Every period is the plan's (lib/stage/orbVariants), never a number of its
 * own. SwiftUI runs the loops on the render server, and nothing here reports
 * back or is awaited.
 */
import { Circle, ZStack } from "@expo/ui/swift-ui";
import {
  Animation,
  animation,
  foregroundStyle,
  frame,
  offset,
  opacity,
  rotationEffect,
} from "@expo/ui/swift-ui/modifiers";

import { fieldDots, type BlobLobe, type FieldOrbit, type Turn } from "@/lib/stage/orbVariants";

/** Loops run until the view goes away; SwiftUI takes a finite count, as for the sphere. */
const FOREVER = 100_000;

/** A part that turns: linear and endless, its period the plan's. */
export function turnLoop(turn: Turn | null, value: number) {
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
export function breathLoop(periodS: number | null, value: boolean) {
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

/** Where a part stands: its resting angle, one full turn on once it moves. */
export function angleOf(turn: Turn | null, appeared: boolean, rest = 0): number {
  return appeared && turn !== null ? rest + 360 : rest;
}

/** One lobe of the blob's mask: white, orbiting, swelling with the breath. */
export function Lobe({
  lobe,
  size,
  appeared,
  breathPeriodS,
}: {
  readonly lobe: BlobLobe;
  readonly size: number;
  readonly appeared: boolean;
  readonly breathPeriodS: number | null;
}) {
  const angle = angleOf(lobe.turn, appeared, lobe.angle);
  const out = appeared && lobe.pulse !== null;
  const reach = out && lobe.pulse !== null ? lobe.pulse : lobe.offset;
  const width = size * lobe.radius * 2;
  return (
    <ZStack
      modifiers={[
        frame({ width: size, height: size }),
        rotationEffect(angle),
        ...turnLoop(lobe.turn, angle),
      ]}
    >
      <Circle
        modifiers={[
          foregroundStyle("#FFFFFF"),
          frame({ width, height: width }),
          offset({ x: size * reach }),
          ...breathLoop(lobe.pulse === null ? null : breathPeriodS, out),
        ]}
      />
    </ZStack>
  );
}

/** One face-on ring of the field's points, turning as a whole. */
export function Orbit({
  orbit,
  ink,
  size,
  appeared,
}: {
  readonly orbit: FieldOrbit;
  readonly ink: string;
  readonly size: number;
  readonly appeared: boolean;
}) {
  const angle = angleOf(orbit.turn, appeared);
  const square = frame({ width: size, height: size });
  return (
    <ZStack modifiers={[square, rotationEffect(angle), ...turnLoop(orbit.turn, angle)]}>
      {fieldDots(orbit).map((dot) => (
        <Circle
          key={`${dot.x}:${dot.y}`}
          modifiers={[
            foregroundStyle(ink),
            frame({ width: size * dot.radius * 2, height: size * dot.radius * 2 }),
            offset({ x: size * dot.x, y: size * dot.y }),
            opacity(dot.light),
          ]}
        />
      ))}
    </ZStack>
  );
}

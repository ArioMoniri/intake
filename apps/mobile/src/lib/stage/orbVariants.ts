/**
 * The stage orb's variant bodies (INT-491, GitHub #838), behind a flag.
 *
 * The owner asked for the orb to be explored (4 Oct 2026) against spaceui.one
 * and the voice orbs of Siri, ChatGPT and Gemini. Three bodies came out of it:
 *
 * - `blob`: a fluid blob. Four lobes orbit a core under one soft threshold, so
 *   the outline flows; while speaking the lobes swell out and back with the
 *   breath.
 * - `field`: a particle field. Four face-on rings of points turn round a soft
 *   nucleus, the inner ones a little faster, so the field slowly shears into
 *   a vortex.
 * - `lens`: a refined glass lens. A deep sphere with a light that sweeps its
 *   rim, a crisp edge and the clear lens over it.
 *
 * Nothing here decides a state or a speed. Each plan is built from the S1
 * motion (`stageOrbMotion`, ADR-039), so whatever that motion keeps still
 * (idle, rest, retry, Reduce Motion, a RED) every variant keeps still, and
 * whatever bound it keeps (breath ≤ 1.06×, swell ≤ +10 %, no breath under
 * 1.2 s, no turn under 3 s) every variant keeps too:
 *
 * - a turn is the S1 turn times a factor of at least 1, so no part turns
 *   faster than the sphere would in that state;
 * - the breath and the voice gain are the S1 ones, passed through;
 * - every part is drawn inside the orb's own circle (radius 0.5 of its size),
 *   so the breath is the only growth.
 *
 * The flag is off by default: `orbVariantFrom` reads anything it does not
 * know as `classic`, the ADR-039 sphere, drawn exactly as before.
 *
 * Pure: no React Native, Expo or Reanimated import, so node tests hold it.
 * The drawing is components/stage/VoiceOrb.ios.tsx.
 */
import { STAGE_ORB_BOUNDS, type StageOrbMotion } from "./orb";

export const ORB_VARIANTS = ["classic", "blob", "field", "lens"] as const;
export type OrbVariant = (typeof ORB_VARIANTS)[number];
export type DrawnVariant = Exclude<OrbVariant, "classic">;
export const DRAWN_VARIANTS: readonly DrawnVariant[] = ["blob", "field", "lens"];

/** Off: the ADR-039 S1 sphere. */
export const ORB_VARIANT_OFF = "classic" satisfies OrbVariant;

/** The flag's value as a variant; anything unknown is off. */
export function orbVariantFrom(value: unknown): OrbVariant {
  if (typeof value !== "string") {
    return ORB_VARIANT_OFF;
  }
  const name = value.trim().toLowerCase();
  const known = ORB_VARIANTS.find((variant) => variant === name);
  return known ?? ORB_VARIANT_OFF;
}

/** The ADR's bounds, plus how many points a field may draw. */
export const VARIANT_LIMITS = {
  ...STAGE_ORB_BOUNDS,
  /** Every point is a native view; past this the field costs frames. */
  maxDots: 48,
} as const;

/** The orb's own circle, as a fraction of its size: nothing is drawn past it. */
export const VARIANT_EXTENT = 0.5;

/**
 * One full turn of a part, clockwise. Every part turns the same way: two parts
 * turning against each other repeat their combined pattern at the sum of
 * their rates, which for the listening and speaking turns lands near the
 * 0.2 Hz Apple warns about; turning one way, they repeat at the difference.
 */
export interface Turn {
  readonly periodS: number;
}

/** Lengths are fractions of the orb's size; angles are degrees. */
export interface BlobLobe {
  readonly radius: number;
  /** The lobe's centre, from the orb's centre, at rest. */
  readonly offset: number;
  /** The lobe's centre at the top of a breath; null when it does not breathe. */
  readonly pulse: number | null;
  /** Where the lobe sits when it does not turn. */
  readonly angle: number;
  readonly turn: Turn | null;
}

export interface BlobBody {
  readonly kind: "blob";
  readonly core: number;
  readonly lobes: readonly BlobLobe[];
  /** The blur that melts the lobes together, before the threshold. */
  readonly softness: number;
  /** How sharply the melted shape is cut: a contrast multiplier. */
  readonly edge: number;
  /** A last, small blur that smooths the cut edge. */
  readonly smoothing: number;
  /** The colour inside the outline turns, as the sphere's gradient does. */
  readonly fill: Turn | null;
  readonly secondFill: Turn | null;
}

export interface FieldOrbit {
  readonly radius: number;
  readonly dotRadius: number;
  readonly dots: number;
  /** Where the ring's first point sits, in degrees, so rings do not line up. */
  readonly phase: number;
  /** How bright the ring's points are, 0 to 1 (drawn as their opacity). */
  readonly light: number;
  readonly turn: Turn | null;
}

export interface FieldBody {
  readonly kind: "field";
  /** The soft light at the centre. */
  readonly nucleus: number;
  readonly orbits: readonly FieldOrbit[];
}

export interface LensBody {
  readonly kind: "lens";
  /** The light that sweeps the rim. */
  readonly sweep: Turn | null;
  /** A fainter, slower light, so the rim never shows one fixed band. */
  readonly caustic: Turn | null;
  /** The crisp edge, as a fraction of the size. */
  readonly rim: number;
}

export type VariantBody = BlobBody | FieldBody | LensBody;

export interface VariantPlan {
  readonly visible: boolean;
  readonly body: VariantBody;
  /** The S1 breath, passed through; null is still. */
  readonly breathe: StageOrbMotion["breathe"];
  /** The S1 voice gain, passed through (PresenceOrb applies it). */
  readonly levelGain: number;
  readonly glowOpacity: number;
  /** The clear Liquid Glass lens: the lens variant's, and only over glass. */
  readonly lens: boolean;
}

/** The sphere's second layer turns this much slower (VoiceOrb.ios.tsx). */
const SECOND_LAYER = 1.6;

/**
 * Every factor is at least 1, so no part turns faster than the S1 turn, and
 * the factors sit close together, so two parts drift apart slowly: in the
 * fastest state (thinking, 3 s) no pair repeats faster than 0.15 Hz.
 */
function turnOf(periodS: number | null, factor: number): Turn | null {
  return periodS === null ? null : { periodS: periodS * factor };
}

const LOBES = [
  { radius: 0.15, offset: 0.18, pulse: 0.24, angle: 0, factor: 1 },
  { radius: 0.13, offset: 0.21, pulse: 0.27, angle: 105, factor: 1.25 },
  { radius: 0.16, offset: 0.16, pulse: 0.22, angle: 215, factor: 1.5 },
  { radius: 0.12, offset: 0.22, pulse: 0.28, angle: 300, factor: 1.8 },
] as const;

/** Inner rings turn faster, as a vortex does; the outer points are the finest. */
const ORBITS = [
  { radius: 0.2, dotRadius: 0.03, dots: 7, phase: 0, light: 1, factor: 1 },
  { radius: 0.295, dotRadius: 0.027, dots: 10, phase: 18, light: 0.9, factor: 1.15 },
  { radius: 0.385, dotRadius: 0.024, dots: 13, phase: 7, light: 0.8, factor: 1.3 },
  { radius: 0.475, dotRadius: 0.02, dots: 16, phase: 11, light: 0.7, factor: 1.45 },
] as const;

function blob(motion: StageOrbMotion): BlobBody {
  const turn = motion.rotationPeriodS;
  const breathing = motion.breathe !== null;
  return {
    kind: "blob",
    core: 0.22,
    lobes: LOBES.map((lobe) => ({
      radius: lobe.radius,
      offset: lobe.offset,
      pulse: breathing ? lobe.pulse : null,
      angle: lobe.angle,
      turn: turnOf(turn, lobe.factor),
    })),
    softness: 0.06,
    edge: 4,
    smoothing: 0.016,
    fill: turnOf(turn, 1),
    secondFill: turnOf(turn, SECOND_LAYER),
  };
}

function field(motion: StageOrbMotion): FieldBody {
  return {
    kind: "field",
    nucleus: 0.16,
    orbits: ORBITS.map((orbit) => ({
      radius: orbit.radius,
      dotRadius: orbit.dotRadius,
      dots: orbit.dots,
      phase: orbit.phase,
      light: orbit.light,
      turn: turnOf(motion.rotationPeriodS, orbit.factor),
    })),
  };
}

function lens(motion: StageOrbMotion): LensBody {
  return {
    kind: "lens",
    sweep: turnOf(motion.rotationPeriodS, 1),
    caustic: turnOf(motion.rotationPeriodS, SECOND_LAYER),
    rim: 0.012,
  };
}

/**
 * The variant's body for this motion. The motion is the S1 policy's answer
 * for `orbStateFor`'s state; `glass` is false under Reduce Transparency and
 * on a capture-protected screen, where nothing is glass.
 */
export function orbVariantPlan(
  variant: DrawnVariant,
  motion: StageOrbMotion,
  surface: { readonly glass: boolean },
): VariantPlan {
  const body =
    variant === "blob" ? blob(motion) : variant === "field" ? field(motion) : lens(motion);
  return {
    visible: motion.visible,
    body,
    breathe: motion.breathe,
    levelGain: motion.levelGain,
    glowOpacity: motion.glowOpacity,
    lens: variant === "lens" && surface.glass,
  };
}

/** Every turning part of a plan; empty when the orb is still. */
export function planTurns(plan: VariantPlan): Turn[] {
  const { body } = plan;
  const turns =
    body.kind === "blob"
      ? [body.fill, body.secondFill, ...body.lobes.map((lobe) => lobe.turn)]
      : body.kind === "field"
        ? body.orbits.map((orbit) => orbit.turn)
        : [body.sweep, body.caustic];
  return turns.filter((turn): turn is Turn => turn !== null);
}

/** One point of a ring, where it rests. */
export interface FieldDot {
  readonly x: number;
  readonly y: number;
  readonly radius: number;
  /** 0 to 1, drawn as the point's opacity. */
  readonly light: number;
}

/**
 * The ring's points, evenly spaced, each a little different in size and
 * light so the ring reads as particles rather than beads.
 */
export function fieldDots(orbit: FieldOrbit): FieldDot[] {
  return Array.from({ length: orbit.dots }, (_, i) => {
    const angle = ((orbit.phase + (360 * i) / orbit.dots) * Math.PI) / 180;
    return {
      x: orbit.radius * Math.cos(angle),
      y: orbit.radius * Math.sin(angle),
      radius: orbit.dotRadius * (0.6 + 0.1 * ((i * 7) % 5)),
      light: orbit.light * (0.55 + 0.15 * (i % 4)),
    };
  });
}

/** How far the body reaches from the centre, before any breath. */
export function bodyExtent(body: VariantBody): number {
  if (body.kind === "blob") {
    const lobes = body.lobes.map((lobe) => Math.max(lobe.offset, lobe.pulse ?? 0) + lobe.radius);
    return Math.max(body.core, ...lobes);
  }
  if (body.kind === "field") {
    const dots = body.orbits.flatMap((orbit) =>
      fieldDots(orbit).map((dot) => Math.hypot(dot.x, dot.y) + dot.radius),
    );
    return Math.max(body.nucleus, ...dots);
  }
  return VARIANT_EXTENT;
}

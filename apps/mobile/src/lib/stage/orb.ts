/**
 * The stage's voice orb: how it moves in each state (chat redesign prototype).
 *
 * The state comes from `orbStateFor` (lib/motion/orb.ts, INT-336), so the
 * stage orb answers exactly the question the presence orb answers: whose turn
 * it is. Only the drawing differs. It is a living gradient sphere that breathes,
 * turns, and while listening follows the patient's voice level.
 *
 * That movement is beyond ADR-033 and ADR-038 (scale and rotation, during a
 * voice session). So it runs only when `flag` is on. The flag is the
 * prototype's switch and stays off until the owner approves the bounds below.
 * With the flag off, under Reduce Motion, or while a RED is presented, the orb
 * is still.
 */
import type { OrbState } from "@/lib/motion/orb";

/** The limits the approval request names; orb.test.ts pins them. */
export const STAGE_ORB_BOUNDS = {
  /** The largest breathing scale, at the top of a breath. */
  maxBreatheScale: 1.06,
  /** The extra scale at full voice level while listening. */
  maxLevelGain: 0.1,
  /** No loop is shorter than a second, so nothing flashes (SC 2.3.1). */
  minPeriodS: 1,
} as const;

export interface StageOrbContext {
  readonly reduce: boolean;
  readonly redPresented: boolean;
  /** The prototype flag; off means ADR-033's stillness. */
  readonly flag: boolean;
}

export interface StageOrbMotion {
  readonly visible: boolean;
  /** Seconds for one full turn of the gradient; null is still. */
  readonly rotationPeriodS: number | null;
  /** An autoreversing breath; null is still. */
  readonly breathe: { readonly scale: number; readonly periodS: number } | null;
  /** Extra scale at full voice level (0 = does not follow the voice). */
  readonly levelGain: number;
  /** How strongly the glow behind the orb shows, 0 to 1. */
  readonly glowOpacity: number;
}

interface Live {
  readonly rotationPeriodS: number | null;
  readonly breathe: StageOrbMotion["breathe"];
  readonly levelGain: number;
  readonly glowOpacity: number;
}

const LIVE: Record<Exclude<OrbState, "hidden">, Live> = {
  idle: {
    rotationPeriodS: 18,
    breathe: { scale: 1.02, periodS: 4 },
    levelGain: 0,
    glowOpacity: 0.5,
  },
  rest: {
    rotationPeriodS: 24,
    breathe: { scale: 1.02, periodS: 5 },
    levelGain: 0,
    glowOpacity: 0.4,
  },
  listening: {
    rotationPeriodS: 10,
    breathe: { scale: 1.04, periodS: 2.4 },
    levelGain: 0.1,
    glowOpacity: 0.9,
  },
  speaking: {
    rotationPeriodS: 7,
    breathe: { scale: 1.06, periodS: 1.2 },
    levelGain: 0,
    glowOpacity: 1,
  },
  thinking: { rotationPeriodS: 3, breathe: null, levelGain: 0, glowOpacity: 0.6 },
  retry: { rotationPeriodS: null, breathe: null, levelGain: 0, glowOpacity: 0.25 },
};

export function stageOrbMotion(state: OrbState, context: StageOrbContext): StageOrbMotion {
  if (state === "hidden") {
    return { visible: false, rotationPeriodS: null, breathe: null, levelGain: 0, glowOpacity: 0 };
  }
  const live = LIVE[state];
  const still = context.reduce || context.redPresented || !context.flag;
  if (still) {
    return {
      visible: true,
      rotationPeriodS: null,
      breathe: null,
      levelGain: 0,
      glowOpacity: live.glowOpacity,
    };
  }
  return { visible: true, ...live };
}

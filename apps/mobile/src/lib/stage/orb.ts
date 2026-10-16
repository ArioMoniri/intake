/**
 * The stage's voice orb: how it moves in each state (ADR-039 S1, INT-466).
 *
 * The state comes from `orbStateFor` (lib/motion/orb.ts, INT-336), so the
 * stage orb answers exactly the question the presence orb always answered:
 * whose turn it is. Only the drawing is new. A gradient sphere breathes while
 * the agent speaks or the patient talks, turns while something is happening,
 * and follows the patient's voice level while listening.
 *
 * Idle, rest and retry are still. Apple's motion guidance warns against
 * sustained oscillation near 0.2 Hz, and a resting breath would sit right
 * there. Reduce Motion and RED make every state still. The turn state is
 * always written and announced as well, so the orb is never the only signal.
 */
import type { OrbState } from "@/lib/motion/orb";

/** ADR-039 S1's limits; orb.test.ts pins them. */
export const STAGE_ORB_BOUNDS = {
  /** The largest breathing scale, at the top of a breath. */
  maxBreatheScale: 1.06,
  /** The shortest breath, in seconds (well over SC 2.3.1's flash window). */
  minBreathePeriodS: 1.2,
  /** The extra scale at full voice level, while listening only. */
  maxLevelGain: 0.1,
  /** The fastest full turn of the gradient, in seconds. */
  minTurnPeriodS: 3,
} as const;

/**
 * The band S1 cites from Apple: sustained oscillation near 0.2 Hz. No two
 * turning layers of the orb may repeat their combined pattern inside it
 * (ADR-039 amendment, INT-491; owner, 16 Oct 2026: "FIXY").
 */
export const OSCILLATION_BAND_HZ = { low: 0.15, high: 0.25 } as const;

/**
 * The sphere's second gradient layer: 1.6× slower than the first, and the
 * same way. Turned against each other, the two layers repeated their pattern
 * every 6.2 s while listening (0.16 Hz) and every 4.3 s while speaking
 * (0.23 Hz), inside the band; one way, the slowest repeat is every 26.7 s and
 * the fastest every 8 s (thinking).
 */
export const STAGE_ORB_SECOND_LAYER = { periodFactor: 1.6, direction: 1 } as const;

/**
 * How often two layers with these full-turn periods (seconds) repeat their
 * combined pattern, in Hz: the difference of their rates when they turn the
 * same way, the sum when they turn against each other.
 */
export function layerBeatHz(periodA: number, periodB: number, sameWay: boolean): number {
  const a = 1 / periodA;
  const b = 1 / periodB;
  return sameWay ? Math.abs(a - b) : a + b;
}

export interface StageOrbContext {
  readonly reduce: boolean;
  readonly redPresented: boolean;
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

const STILL = { rotationPeriodS: null, breathe: null, levelGain: 0 } as const;

const LIVE: Record<Exclude<OrbState, "hidden">, Live> = {
  idle: { ...STILL, glowOpacity: 0.5 },
  rest: { ...STILL, glowOpacity: 0.4 },
  retry: { ...STILL, glowOpacity: 0.25 },
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
};

export function stageOrbMotion(state: OrbState, context: StageOrbContext): StageOrbMotion {
  if (state === "hidden") {
    return { visible: false, ...STILL, glowOpacity: 0 };
  }
  const live = LIVE[state];
  if (context.reduce || context.redPresented) {
    return { visible: true, ...STILL, glowOpacity: live.glowOpacity };
  }
  return { visible: true, ...live };
}

/**
 * The welcome mark (ADR-039 S7, INT-464): the same orb the dialogue shows at
 * rest, drawn still. The sign-in screens add no motion, and there is no turn
 * to show before a visit, so the mark never takes a live state.
 */
export function stillOrb(): StageOrbMotion {
  return { visible: true, ...STILL, glowOpacity: LIVE.idle.glowOpacity };
}

/**
 * The voice level (0 to 1, from INT-336's sampler) as the orb's scale. It is
 * a worklet: it runs on the UI thread inside the orb's animated style, so a
 * level sample re-renders nothing.
 */
export function levelScale(level: number, gain: number): number {
  "worklet";
  const clamped = Math.min(1, Math.max(0, level));
  return 1 + clamped * gain;
}

/**
 * The presence orb's policy (INT-336, MOTION-7;
 * docs/design/motion/motion-verification.md §1.1 O1–O8 as revised, §2.2,
 * §4 MOTION-7; intake-voice-motion-spec.md §4.2–§4.5; files/02 §5.2).
 *
 * Pure — no React Native, Reanimated or clock — so every state, visual,
 * transition and level step is node-testable. `components/PresenceOrb.tsx`
 * draws what this decides and writes no number of its own.
 *
 * - **State** comes from events alone: the lane, the turn phase, playback, the
 *   transport and a presented RED. Nothing here is a timer, so "thinking" ends
 *   when the audio starts, never after a duration (02 §5.2).
 * - **Visual** is opacity only. The owner has not answered ADR-033 Q5 (a
 *   scale of at most 1.06 on the orb alone), so every state's scale is the
 *   literal 1 and listening stays visible through its halo's opacity instead.
 * - **Level** is one loudness scalar from the recorder's own meter, turned
 *   into 0…1, smoothed (attack faster than release) and stepped, and written
 *   at 10 Hz or less. It is sampled only while listening and never under
 *   reduce-motion. It is never a buffer and never feeds affect (invariants 3,
 *   6 and 11).
 * - **A RED** reaches the orb as `redFirstPaint(…).yields.orb` (lib/motion/
 *   red.ts): a takeover unmounts it, SILENT holds it at idle, and a
 *   DEFERRED_CLINICIAN finding ("unchanged") changes nothing.
 */
import { motionMs } from "../a11y/motion";
import type { StreamTurn } from "../dialogue/stream";
import { motion, type Bezier } from "../theme";
import type { RedYield } from "./red";

export const ORB_STATES = [
  "hidden",
  "idle",
  "listening",
  "thinking",
  "speaking",
  "retry",
  "rest",
] as const;

export type OrbState = (typeof ORB_STATES)[number];

/** The events the orb's state follows. Nothing time-shaped belongs here. */
export interface OrbInputs {
  readonly lane: "voice" | "typed";
  readonly turnPhase: StreamTurn["phase"];
  /** The agent's clip is audibly playing. */
  readonly playing: boolean;
  /** The agent lost its voice for the session (a TTS outage, INT-261). */
  readonly voiceMuted: boolean;
  /** The media transport, where one exists; the dev lane is always connected. */
  readonly transport: "connected" | "reconnecting" | "interrupted";
  /** What a presented RED does to the orb, or null when none is presented. */
  readonly red: RedYield["orb"] | null;
}

/**
 * The orb's state. The first matching rule wins (intake-voice-motion-spec.md
 * §4.2): a hidden orb outranks everything, and the transport outranks a
 * SILENT RED because a lost connection is what the patient must see.
 */
export function orbStateFor(input: OrbInputs): OrbState {
  const { lane, turnPhase, playing, voiceMuted, transport, red } = input;
  if (lane === "typed" || red === "unmount") {
    return "hidden";
  }
  if (turnPhase === "failed" || turnPhase === "handoff") {
    return "hidden";
  }
  if (transport !== "connected") {
    return "retry";
  }
  if (red === "idle") {
    return "idle";
  }
  switch (turnPhase) {
    case "done":
      return "rest";
    case "settling":
      return "thinking";
    case "speaking":
      if (voiceMuted) {
        return "idle";
      }
      return playing ? "speaking" : "thinking";
    case "listening":
      return "listening";
    case "confirming":
      return "idle";
  }
}

export type OrbLoopKind = "breathe" | "speak" | "shimmer";

/** One layer's opacity, moving between two token values. No duration: it loops. */
export interface OrbLoop {
  readonly kind: OrbLoopKind;
  readonly layer: "core" | "halo";
  readonly from: number;
  readonly to: number;
  readonly easing: Bezier;
}

export interface OrbVisual {
  readonly mounted: boolean;
  /** Rest opacities, reached through `orbTransition` from wherever they are. */
  readonly coreOpacity: number;
  readonly haloOpacity: number;
  readonly retryCoreOpacity: number;
  /** Null for a still state, and for every state under reduce-motion. */
  readonly loop: OrbLoop | null;
  /** Whether the halo follows the patient's voice. Listening only. */
  readonly levelReactive: boolean;
  /** Opacity-only until ADR-033 Q5 is answered: the literal 1. */
  readonly scale: 1;
}

interface Rest {
  readonly core: number;
  readonly halo: number;
  readonly retry: number;
  readonly loop: Omit<OrbLoop, "easing"> | null;
}

const { orb } = motion;

const REST: Readonly<Record<OrbState, Rest>> = {
  hidden: { core: 0, halo: 0, retry: 0, loop: null },
  idle: { core: 1, halo: 0, retry: 0, loop: null },
  listening: {
    core: 1,
    halo: orb.haloOpacity,
    retry: 0,
    loop: { kind: "breathe", layer: "halo", from: orb.haloOpacity, to: orb.haloBreathLow },
  },
  thinking: {
    core: orb.shimmerOpacityHigh,
    halo: 0,
    retry: 0,
    loop: {
      kind: "shimmer",
      layer: "core",
      from: orb.shimmerOpacityHigh,
      to: orb.shimmerOpacityLow,
    },
  },
  speaking: {
    core: 1,
    halo: 0,
    retry: 0,
    loop: { kind: "speak", layer: "core", from: 1, to: orb.speakOpacityLow },
  },
  retry: { core: 0, halo: 0, retry: 1, loop: null },
  rest: { core: 1, halo: 0, retry: 0, loop: null },
};

export interface OrbContext {
  /** The patient's reduce-motion answer (`useReducedMotion`). */
  readonly reduce: boolean;
}

/** What the orb shows in a state. Under reduce-motion it is still. */
export function orbVisual(state: OrbState, { reduce }: OrbContext): OrbVisual {
  const rest = REST[state];
  return {
    mounted: state !== "hidden",
    coreOpacity: rest.core,
    haloOpacity: rest.halo,
    retryCoreOpacity: rest.retry,
    loop: reduce || rest.loop === null ? null : { ...rest.loop, easing: motion.easing.breath },
    levelReactive: state === "listening" && !reduce,
    scale: 1,
  };
}

export interface OrbTiming {
  readonly durationMs: number;
  /** A literal type: the orb never waits to change. */
  readonly delayMs: 0;
  readonly easing: Bezier;
}

/**
 * How the orb moves from one state to the next. It unmounts at once, arrives
 * with the one fade, and drops from speaking to listening in `duration.fast`
 * so the visual never lags the barge-in's audio stop. A looping value returns
 * to its rest from where it is, never from its start.
 */
export function orbTransition(from: OrbState, to: OrbState, { reduce }: OrbContext): OrbTiming {
  let ms: number = motion.duration.fade;
  if (to === "hidden" || from === to) {
    ms = motion.duration.instant;
  } else if (from === "speaking" && to === "listening") {
    ms = motion.duration.fast;
  }
  return { durationMs: motionMs(reduce, ms), delayMs: 0, easing: motion.easing.out };
}

/** The background-work ring: a static modifier that fades on once, never a loop. */
export function workRing(active: boolean, { reduce }: OrbContext) {
  return {
    opacity: active ? orb.workRingOpacity : 0,
    durationMs: motionMs(reduce, motion.duration.fade),
  } as const;
}

/** −50…−10 dBFS onto 0…1. No reading, or a meaningless one, is silence. */
export function normalizeLevel(dbfs: number | undefined): number {
  if (dbfs === undefined || Number.isNaN(dbfs)) {
    return 0;
  }
  const { floorDbfs, ceilDbfs } = motion.level;
  return Math.min(1, Math.max(0, (dbfs - floorDbfs) / (ceilDbfs - floorDbfs)));
}

/** One smoothing step: the level rises quickly and falls slowly. */
export function smoothLevel(prev: number, x: number): number {
  const k = x > prev ? motion.level.attack : motion.level.release;
  return prev + k * (x - prev);
}

/** Round to the level step, and say whether the written value changed. */
export function quantizeLevel(prev: number, x: number): { value: number; changed: boolean } {
  const perUnit = Math.round(1 / motion.level.step);
  const value = Math.round(x * perUnit) / perUnit;
  return { value, changed: value !== prev };
}

export interface LevelSamplerPlan {
  /** Sample at all. Listening only, and never under reduce-motion. */
  readonly run: boolean;
  /** At least `level.sampleMs` apart: 10 Hz or less. */
  readonly intervalMs: number;
}

/** When the level sampler runs. Every exit from listening stops it. */
export function levelSamplerPlan(state: OrbState, { reduce }: OrbContext): LevelSamplerPlan {
  return { run: state === "listening" && !reduce, intervalMs: motion.level.sampleMs };
}

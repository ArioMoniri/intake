/**
 * The presence orb's policy (INT-336, MOTION-7;
 * docs/design/motion/motion-verification.md §1.1 O1–O8 as revised, §2.2 and
 * §4 MOTION-7; intake-voice-motion-spec.md §4.2–§4.5; files/02 §5.2).
 *
 * Everything the orb shows is decided here, from events alone: the state from
 * the turn, the lane, playback, the transport and a presented RED; the
 * visual from the state and reduce-motion; the level from one loudness scalar.
 * No input is a clock, so the same inputs always give the same orb.
 *
 * Opacity-only until the owner answers ADR-033 Q5: no state scales, and the
 * listening state stays visible through its halo's opacity instead.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, expectTypeOf, it } from "vitest";

import type { StreamTurn } from "../dialogue/stream";
import { motion } from "../theme";
import {
  ORB_STATES,
  levelSamplerPlan,
  normalizeLevel,
  orbStateFor,
  orbTransition,
  orbVisual,
  quantizeLevel,
  smoothLevel,
  workRing,
  type OrbInputs,
  type OrbState,
  type OrbVisual,
} from "./orb";

const PHASES: readonly StreamTurn["phase"][] = [
  "speaking",
  "listening",
  "confirming",
  "settling",
  "handoff",
  "done",
  "failed",
];

const BASE: OrbInputs = {
  lane: "voice",
  turnPhase: "listening",
  playing: false,
  voiceMuted: false,
  transport: "connected",
  red: null,
};

/** Every combination of every input: 2 × 7 × 2 × 2 × 3 × 4 = 672 cases. */
const ALL_INPUTS: readonly OrbInputs[] = (["voice", "typed"] as const).flatMap((lane) =>
  PHASES.flatMap((turnPhase) =>
    [false, true].flatMap((playing) =>
      [false, true].flatMap((voiceMuted) =>
        (["connected", "reconnecting", "interrupted"] as const).flatMap((transport) =>
          ([null, "unmount", "idle", "unchanged"] as const).map((red) => ({
            lane,
            turnPhase,
            playing,
            voiceMuted,
            transport,
            red,
          })),
        ),
      ),
    ),
  ),
);

const REDUCE = [false, true] as const;

describe("presence orb policy (MOTION-7)", () => {
  it("orbStateFor maps speaking+playing to speaking and speaking+!playing to thinking", () => {
    expect(orbStateFor({ ...BASE, turnPhase: "speaking", playing: true })).toBe("speaking");
    expect(orbStateFor({ ...BASE, turnPhase: "speaking", playing: false })).toBe("thinking");
    // A muted agent is silent, not busy: its turn is idle.
    expect(orbStateFor({ ...BASE, turnPhase: "speaking", playing: true, voiceMuted: true })).toBe(
      "idle",
    );
    expect(orbStateFor({ ...BASE, turnPhase: "listening" })).toBe("listening");
    expect(orbStateFor({ ...BASE, turnPhase: "confirming" })).toBe("idle");
    expect(orbStateFor({ ...BASE, turnPhase: "done" })).toBe("rest");
  });

  it("orbStateFor is event-driven: no clock input, and the same input gives the same state", () => {
    // The input type has exactly these event fields and nothing time-shaped.
    expect(Object.keys(BASE).sort()).toEqual(
      ["lane", "playing", "red", "transport", "turnPhase", "voiceMuted"].sort(),
    );
    for (const input of ALL_INPUTS) {
      const first = orbStateFor(input);
      expect(ORB_STATES).toContain(first);
      expect(orbStateFor({ ...input })).toBe(first);
    }
    const source = readFileSync(join(__dirname, "orb.ts"), "utf8");
    const code = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
    expect(code).not.toMatch(
      /\bDate\b|\bperformance\b|\bsetTimeout\b|\bsetInterval\b|\brequestAnimationFrame\b|\bMath\.random\b/,
    );
  });

  it("typed lane, RED ALERT/CALM, failed and handoff hide the orb", () => {
    for (const input of ALL_INPUTS) {
      const hides =
        input.lane === "typed" ||
        input.red === "unmount" ||
        input.turnPhase === "failed" ||
        input.turnPhase === "handoff";
      expect(orbStateFor(input) === "hidden", JSON.stringify(input)).toBe(hides);
    }
  });

  it("RED SILENT maps to idle", () => {
    for (const turnPhase of ["speaking", "listening", "confirming", "settling"] as const) {
      expect(orbStateFor({ ...BASE, turnPhase, playing: true, red: "idle" }), turnPhase).toBe(
        "idle",
      );
    }
    // A DEFERRED_CLINICIAN finding changes nothing: the orb is as it was.
    for (const input of ALL_INPUTS.filter((i) => i.red === "unchanged")) {
      expect(orbStateFor(input), JSON.stringify(input)).toBe(orbStateFor({ ...input, red: null }));
    }
  });

  it("retry is driven by transport phase, never by voiceMuted", () => {
    for (const transport of ["reconnecting", "interrupted"] as const) {
      expect(orbStateFor({ ...BASE, transport })).toBe("retry");
    }
    // Near miss: a TTS outage is silence, not failure (INT-261).
    for (const input of ALL_INPUTS.filter((i) => i.transport === "connected")) {
      expect(orbStateFor(input), JSON.stringify(input)).not.toBe("retry");
    }
  });

  it("settling maps to thinking and carries no timer", () => {
    expect(orbStateFor({ ...BASE, turnPhase: "settling" })).toBe("thinking");
    // Thinking ends on an event, never on a duration: its visual has a loop
    // period and no length.
    const visual = orbVisual("thinking", { reduce: false });
    expect(visual.loop?.kind).toBe("shimmer");
    expect(Object.keys(visual.loop ?? {})).not.toContain("durationMs");
  });

  it("listening is the only level-reactive state", () => {
    for (const state of ORB_STATES) {
      for (const reduce of REDUCE) {
        expect(orbVisual(state, { reduce }).levelReactive, `${state} ${reduce}`).toBe(
          state === "listening" && !reduce,
        );
      }
    }
  });

  it("normalizeLevel clamps −50…−10 dBFS to 0…1 and maps undefined/NaN to 0", () => {
    expect(normalizeLevel(motion.level.floorDbfs)).toBe(0);
    expect(normalizeLevel(motion.level.ceilDbfs)).toBe(1);
    expect(normalizeLevel(-30)).toBeCloseTo(0.5, 10);
    expect(normalizeLevel(-80)).toBe(0);
    expect(normalizeLevel(0)).toBe(1);
    expect(normalizeLevel(undefined)).toBe(0);
    expect(normalizeLevel(Number.NaN)).toBe(0);
    expect(normalizeLevel(Number.POSITIVE_INFINITY)).toBe(1);
  });

  it("smoothLevel rises faster than it falls", () => {
    const rise = smoothLevel(0, 1);
    const fall = 1 - smoothLevel(1, 0);
    expect(rise).toBeCloseTo(motion.level.attack, 10);
    expect(fall).toBeCloseTo(motion.level.release, 10);
    expect(rise).toBeGreaterThan(fall);
    // It never overshoots its target.
    for (const [prev, x] of [
      [0.2, 0.9],
      [0.9, 0.2],
      [0.5, 0.5],
    ]) {
      const s = smoothLevel(prev, x);
      expect(s).toBeGreaterThanOrEqual(Math.min(prev, x));
      expect(s).toBeLessThanOrEqual(Math.max(prev, x));
    }
  });

  it("quantizeLevel snaps to 0.05 and reports unchanged writes", () => {
    expect(quantizeLevel(0, 0.52)).toEqual({ value: 0.5, changed: true });
    expect(quantizeLevel(0.5, 0.51)).toEqual({ value: 0.5, changed: false });
    expect(quantizeLevel(0.5, 0.53)).toEqual({ value: 0.55, changed: true });
    // Exact multiples, with no float residue a later comparison could trip on.
    for (let i = 0; i <= 20; i += 1) {
      const x = i * motion.level.step;
      expect(quantizeLevel(-1, x).value).toBe(Math.round(x * 20) / 20);
    }
  });

  it("levelSamplerPlan never runs under reduce-motion and stops on every exit from listening", () => {
    for (const state of ORB_STATES) {
      for (const reduce of REDUCE) {
        const plan = levelSamplerPlan(state, { reduce });
        expect(plan.run, `${state} ${reduce}`).toBe(state === "listening" && !reduce);
      }
    }
  });

  it("the level updates at 10 Hz or less", () => {
    const plan = levelSamplerPlan("listening", { reduce: false });
    expect(plan.intervalMs).toBe(motion.level.sampleMs);
    expect(1000 / plan.intervalMs).toBeLessThanOrEqual(10);
  });

  it("orbVisual animates opacity only until the scale exception is ratified", () => {
    expectTypeOf<OrbVisual["scale"]>().toEqualTypeOf<1>();
    for (const state of ORB_STATES) {
      for (const reduce of REDUCE) {
        const visual = orbVisual(state, { reduce });
        expect(visual.scale, state).toBe(1);
        if (visual.loop !== null) {
          // A loop moves one layer's opacity between two token values.
          expect(["core", "halo"]).toContain(visual.loop.layer);
          expect(visual.loop.from).toBeGreaterThanOrEqual(0);
          expect(visual.loop.to).toBeLessThanOrEqual(1);
        }
      }
    }
    // No scale token ships (motion-verification.md §2.2 "Not shipped").
    expect(Object.keys(motion.orb).filter((k) => /scale/i.test(k))).toEqual([]);
  });

  it("every loop amplitude stays within its token ceiling", () => {
    const listening = orbVisual("listening", { reduce: false }).loop!;
    expect([listening.from, listening.to].sort()).toEqual(
      [motion.orb.haloBreathLow, motion.orb.haloOpacity].sort(),
    );
    const speaking = orbVisual("speaking", { reduce: false }).loop!;
    expect([speaking.from, speaking.to].sort()).toEqual([motion.orb.speakOpacityLow, 1].sort());
    const thinking = orbVisual("thinking", { reduce: false }).loop!;
    expect([thinking.from, thinking.to].sort()).toEqual(
      [motion.orb.shimmerOpacityLow, motion.orb.shimmerOpacityHigh].sort(),
    );
    for (const loop of [listening, speaking, thinking]) {
      expect(loop.easing).toEqual(motion.easing.breath);
    }
  });

  it("the speaking→listening transition starts at delay 0 and lasts ≤ duration.fast", () => {
    const t = orbTransition("speaking", "listening", { reduce: false });
    expect(t.delayMs).toBe(0);
    expect(t.durationMs).toBe(motion.duration.fast);
    expect(t.durationMs).toBeLessThanOrEqual(motion.fadeMs);
    expect(orbTransition("speaking", "listening", { reduce: true }).durationMs).toBe(0);
  });

  it("every orb transition uses the out easing and lasts ≤ fadeMs", () => {
    for (const from of ORB_STATES) {
      for (const to of ORB_STATES) {
        for (const reduce of REDUCE) {
          const t = orbTransition(from, to, { reduce });
          const label = `${from}→${to} ${reduce}`;
          expect(t.easing, label).toEqual(motion.easing.out);
          expect(t.delayMs, label).toBe(0);
          expect(t.durationMs, label).toBeGreaterThanOrEqual(0);
          expect(t.durationMs, label).toBeLessThanOrEqual(motion.fadeMs);
          if (reduce || to === "hidden" || from === to) {
            expect(t.durationMs, label).toBe(0);
          }
        }
      }
    }
    // Arriving from nothing is the one fade the dialogue's mount shows.
    expect(orbTransition("hidden", "idle", { reduce: false }).durationMs).toBe(
      motion.duration.fade,
    );
  });

  it("background work is a static ring modifier, never a loop", () => {
    for (const reduce of REDUCE) {
      const on = workRing(true, { reduce });
      expect(on.opacity).toBe(motion.orb.workRingOpacity);
      expect(on.durationMs).toBe(reduce ? 0 : motion.duration.fade);
      expect(Object.keys(on)).not.toContain("loop");
      expect(workRing(false, { reduce }).opacity).toBe(0);
    }
  });

  it("idle, retry and rest carry no loop at any reduce-motion setting", () => {
    const still: readonly OrbState[] = ["hidden", "idle", "retry", "rest"];
    for (const state of still) {
      for (const reduce of REDUCE) {
        expect(orbVisual(state, { reduce }).loop, `${state} ${reduce}`).toBeNull();
      }
    }
    // Under reduce-motion nothing loops at all.
    for (const state of ORB_STATES) {
      expect(orbVisual(state, { reduce: true }).loop, state).toBeNull();
    }
    // Retry swaps cores; it never flashes or turns red.
    const retry = orbVisual("retry", { reduce: false });
    expect([retry.coreOpacity, retry.retryCoreOpacity]).toEqual([0, 1]);
  });

  it("hidden is unmounted, and every other state is mounted", () => {
    for (const state of ORB_STATES) {
      expect(orbVisual(state, { reduce: false }).mounted, state).toBe(state !== "hidden");
    }
  });
});

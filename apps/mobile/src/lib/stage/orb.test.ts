/**
 * The stage's voice orb motion (chat redesign prototype).
 *
 * This motion goes beyond ADR-033 and ADR-038: the orb scales with the voice
 * level and its gradient turns. It is built behind a flag for the owner to
 * judge, and these bounds are what the approval request names. Reduce Motion
 * and RED both make it still; nothing flashes (every period is a second or
 * more, SC 2.3.1).
 */
import { describe, expect, it } from "vitest";

import { ORB_STATES } from "@/lib/motion/orb";

import { STAGE_ORB_BOUNDS, stageOrbMotion } from "./orb";

const LIVE = { reduce: false, redPresented: false, flag: true } as const;

describe("stage orb motion", () => {
  it("every state stays inside the bounds the approval request names", () => {
    for (const state of ORB_STATES) {
      const m = stageOrbMotion(state, LIVE);
      if (m.breathe !== null) {
        expect(m.breathe.scale, state).toBeLessThanOrEqual(STAGE_ORB_BOUNDS.maxBreatheScale);
        expect(m.breathe.periodS, state).toBeGreaterThanOrEqual(STAGE_ORB_BOUNDS.minPeriodS);
      }
      if (m.rotationPeriodS !== null) {
        expect(m.rotationPeriodS, state).toBeGreaterThanOrEqual(STAGE_ORB_BOUNDS.minPeriodS);
      }
      expect(m.levelGain, state).toBeLessThanOrEqual(STAGE_ORB_BOUNDS.maxLevelGain);
    }
    expect(STAGE_ORB_BOUNDS).toEqual({ maxBreatheScale: 1.06, maxLevelGain: 0.1, minPeriodS: 1 });
  });

  it("only listening follows the voice level", () => {
    for (const state of ORB_STATES) {
      const gain = stageOrbMotion(state, LIVE).levelGain;
      expect(gain > 0, state).toBe(state === "listening");
    }
  });

  it("speaking breathes faster than listening, and thinking turns fastest", () => {
    const speaking = stageOrbMotion("speaking", LIVE);
    const listening = stageOrbMotion("listening", LIVE);
    const thinking = stageOrbMotion("thinking", LIVE);
    expect(speaking.breathe!.periodS).toBeLessThan(listening.breathe!.periodS);
    expect(thinking.rotationPeriodS!).toBeLessThan(listening.rotationPeriodS!);
    expect(thinking.rotationPeriodS!).toBeLessThan(speaking.rotationPeriodS!);
  });

  it("Reduce Motion makes every state still, but keeps it visible", () => {
    for (const state of ORB_STATES) {
      const m = stageOrbMotion(state, { ...LIVE, reduce: true });
      expect(m.rotationPeriodS, state).toBeNull();
      expect(m.breathe, state).toBeNull();
      expect(m.levelGain, state).toBe(0);
      expect(m.visible, state).toBe(state !== "hidden");
    }
  });

  it("a RED presentation makes it still at any setting", () => {
    for (const state of ORB_STATES) {
      const m = stageOrbMotion(state, { ...LIVE, redPresented: true });
      expect(m.rotationPeriodS, state).toBeNull();
      expect(m.breathe, state).toBeNull();
      expect(m.levelGain, state).toBe(0);
    }
  });

  it("with the flag off the orb keeps ADR-033's stillness: no scale, no turn", () => {
    for (const state of ORB_STATES) {
      const m = stageOrbMotion(state, { ...LIVE, flag: false });
      expect(m.rotationPeriodS, state).toBeNull();
      expect(m.breathe, state).toBeNull();
      expect(m.levelGain, state).toBe(0);
    }
  });

  it("near miss: the live listening orb does move", () => {
    const m = stageOrbMotion("listening", LIVE);
    expect(m.rotationPeriodS).not.toBeNull();
    expect(m.breathe).not.toBeNull();
    expect(m.levelGain).toBeGreaterThan(0);
  });

  it("hidden draws nothing; retry is dim and still", () => {
    expect(stageOrbMotion("hidden", LIVE).visible).toBe(false);
    const retry = stageOrbMotion("retry", LIVE);
    expect(retry.rotationPeriodS).toBeNull();
    expect(retry.breathe).toBeNull();
    expect(retry.glowOpacity).toBeLessThan(stageOrbMotion("idle", LIVE).glowOpacity);
  });
});

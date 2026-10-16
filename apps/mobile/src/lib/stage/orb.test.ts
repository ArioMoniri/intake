/**
 * The stage's voice orb motion (ADR-039 S1, INT-466).
 *
 * The owner approved these bounds ("yes to all"): the orb breathes, turns and,
 * while listening, follows the voice level. It moves only in the three
 * states where something is happening; idle, rest and retry are still (Apple
 * warns against sustained oscillation near 0.2 Hz). Reduce Motion and RED
 * make every state still. Nothing flashes: no period is under a second
 * (SC 2.3.1).
 */
import { describe, expect, it } from "vitest";

import { ORB_STATES } from "@/lib/motion/orb";

import {
  OSCILLATION_BAND_HZ,
  STAGE_ORB_BOUNDS,
  STAGE_ORB_SECOND_LAYER,
  layerBeatHz,
  levelScale,
  stageOrbMotion,
  stillOrb,
} from "./orb";

const LIVE = { reduce: false, redPresented: false } as const;
const MOVING = ["speaking", "listening", "thinking"] as const;

describe("stage orb motion (ADR-039 S1)", () => {
  it("the bounds are the ADR's", () => {
    expect(STAGE_ORB_BOUNDS).toEqual({
      maxBreatheScale: 1.06,
      minBreathePeriodS: 1.2,
      maxLevelGain: 0.1,
      minTurnPeriodS: 3,
    });
  });

  it("every state stays inside the bounds", () => {
    for (const state of ORB_STATES) {
      const m = stageOrbMotion(state, LIVE);
      if (m.breathe !== null) {
        expect(m.breathe.scale, state).toBeLessThanOrEqual(STAGE_ORB_BOUNDS.maxBreatheScale);
        expect(m.breathe.periodS, state).toBeGreaterThanOrEqual(STAGE_ORB_BOUNDS.minBreathePeriodS);
      }
      if (m.rotationPeriodS !== null) {
        expect(m.rotationPeriodS, state).toBeGreaterThanOrEqual(STAGE_ORB_BOUNDS.minTurnPeriodS);
      }
      expect(m.levelGain, state).toBeLessThanOrEqual(STAGE_ORB_BOUNDS.maxLevelGain);
    }
  });

  it("only speaking, listening and thinking move; idle, rest and retry are still", () => {
    for (const state of ORB_STATES) {
      const m = stageOrbMotion(state, LIVE);
      const moves = m.rotationPeriodS !== null || m.breathe !== null || m.levelGain > 0;
      expect(moves, state).toBe((MOVING as readonly string[]).includes(state));
    }
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
    expect(thinking.rotationPeriodS!).toBeLessThan(speaking.rotationPeriodS!);
    expect(speaking.rotationPeriodS!).toBeLessThan(listening.rotationPeriodS!);
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

  it("near miss: the live listening orb does move", () => {
    const m = stageOrbMotion("listening", LIVE);
    expect(m.rotationPeriodS).not.toBeNull();
    expect(m.breathe).not.toBeNull();
    expect(m.levelGain).toBeGreaterThan(0);
  });

  it("hidden draws nothing; retry is dim", () => {
    expect(stageOrbMotion("hidden", LIVE).visible).toBe(false);
    expect(stageOrbMotion("retry", LIVE).glowOpacity).toBeLessThan(
      stageOrbMotion("idle", LIVE).glowOpacity,
    );
  });
});

describe("one-way turns (ADR-039 amendment, INT-491, owner 16 Oct 2026: FIXY)", () => {
  it("the band is the one S1 cites from Apple: sustained oscillation near 0.2 Hz", () => {
    expect(OSCILLATION_BAND_HZ.low).toBeLessThan(0.2);
    expect(OSCILLATION_BAND_HZ.high).toBeGreaterThan(0.2);
    expect(OSCILLATION_BAND_HZ).toEqual({ low: 0.15, high: 0.25 });
  });

  it("the second layer turns the same way as the first, 1.6x slower", () => {
    expect(STAGE_ORB_SECOND_LAYER).toEqual({ periodFactor: 1.6, direction: 1 });
  });

  it("in every moving state the two layers repeat their pattern below the band", () => {
    for (const state of MOVING) {
      const turn = stageOrbMotion(state, LIVE).rotationPeriodS!;
      const beat = layerBeatHz(
        turn,
        turn * STAGE_ORB_SECOND_LAYER.periodFactor,
        STAGE_ORB_SECOND_LAYER.direction === 1,
      );
      expect(beat, state).toBeLessThan(OSCILLATION_BAND_HZ.low);
    }
  });

  it("near miss: turned against each other, listening and speaking fall inside the band", () => {
    for (const state of ["listening", "speaking"] as const) {
      const turn = stageOrbMotion(state, LIVE).rotationPeriodS!;
      const beat = layerBeatHz(turn, turn * STAGE_ORB_SECOND_LAYER.periodFactor, false);
      expect(beat, state).toBeGreaterThanOrEqual(OSCILLATION_BAND_HZ.low);
      expect(beat, state).toBeLessThanOrEqual(OSCILLATION_BAND_HZ.high);
    }
  });

  it("the beat is the difference of the rates one way and their sum the other", () => {
    expect(layerBeatHz(10, 16, true)).toBeCloseTo(1 / 10 - 1 / 16);
    expect(layerBeatHz(10, 16, false)).toBeCloseTo(1 / 10 + 1 / 16);
    expect(layerBeatHz(16, 10, true)).toBeCloseTo(1 / 10 - 1 / 16);
  });
});

describe("levelScale: the voice level as the orb's scale", () => {
  it("is 1 at silence and 1 + gain at full level", () => {
    expect(levelScale(0, 0.1)).toBe(1);
    expect(levelScale(1, 0.1)).toBeCloseTo(1.1);
  });

  it("clamps a level outside 0..1, so a metering spike never exceeds the bound", () => {
    expect(levelScale(4, 0.1)).toBeCloseTo(1.1);
    expect(levelScale(-2, 0.1)).toBe(1);
  });

  it("a zero gain never scales", () => {
    expect(levelScale(1, 0)).toBe(1);
  });
});

describe("stillOrb: the welcome mark (ADR-039 S7, INT-464)", () => {
  it("is visible and moves in no way: no turn, no breath, no voice level", () => {
    const mark = stillOrb();
    expect(mark.visible).toBe(true);
    expect(mark.rotationPeriodS).toBeNull();
    expect(mark.breathe).toBeNull();
    expect(mark.levelGain).toBe(0);
  });

  it("keeps the resting glow, so the mark is the same orb the dialogue shows at rest", () => {
    expect(stillOrb().glowOpacity).toBe(stageOrbMotion("idle", LIVE).glowOpacity);
  });

  it("near miss: a live listening orb would move, so the mark is not drawn from a live state", () => {
    expect(stageOrbMotion("listening", LIVE).rotationPeriodS).not.toBeNull();
  });
});

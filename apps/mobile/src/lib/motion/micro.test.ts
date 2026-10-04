/**
 * INT-492: the micro-interactions' motion, as numbers (GitHub #839).
 *
 * The redesign moves only what the ratified ADRs allow, and each rule here is
 * one of them:
 *
 * - the "Soru N / M" capsule swaps with the step and does not animate
 *   (ADR-033 §2: the question's 120 ms fade is the step's one animated
 *   element, C9); the rolling number is beyond the ADRs, so it exists only
 *   behind its own flag, which a release build never honours, and it is
 *   static under Reduce Motion and while a RED is presented;
 * - the filled action gives 0.97 under the finger on ADR-037 P1's critically
 *   damped spring, absent under Reduce Motion and on RED;
 * - the loading wait keeps the platform spinner, and under Reduce Motion the
 *   redesign shows a still glyph instead, so nothing on the screen moves.
 *
 * Each rule has its near miss: the same inputs with one switched.
 */
import { describe, expect, it } from "vitest";

import { motion } from "../theme";
import { BUBBLE_RISE, BUBBLE_SPRING } from "./bubbles";
import { fadeSpec } from "./fade";
import {
  PRESS_SCALE,
  PRESS_SPRING,
  ROLL_RISE,
  loadingIndicator,
  numberRoll,
  pressScale,
} from "./micro";

const ROLL_ON = { progressMicro: true, progressNumberRoll: true } as const;
const MICRO_ONLY = { progressMicro: true, progressNumberRoll: false } as const;
const OFF = { progressMicro: false, progressNumberRoll: false } as const;
const CALM = { reduce: false, redPresented: false } as const;

describe("the capsule's number swaps with the step", () => {
  it("flag off: no roll, the current screen", () => {
    expect(numberRoll({ flags: OFF, ...CALM })).toEqual({ kind: "none" });
  });

  it("the redesign alone does not roll: the question's fade keeps the one slot (C9)", () => {
    expect(numberRoll({ flags: MICRO_ONLY, ...CALM })).toEqual({ kind: "none" });
  });

  it("the roll flag (approval needed) rises 8 pt under the app's one fade", () => {
    expect(numberRoll({ flags: ROLL_ON, ...CALM })).toEqual({
      kind: "roll",
      rise: ROLL_RISE,
      fade: fadeSpec({ reduce: false }),
    });
    // One distance in the app: ADR-038 A1's rise, and no spring (the roll is
    // a timing, so the spring allow-list does not grow for it).
    expect(ROLL_RISE).toBe(BUBBLE_RISE);
    expect(fadeSpec({ reduce: false }).durationMs).toBe(motion.duration.fade);
  });

  it("near miss: Reduce Motion makes it static", () => {
    expect(numberRoll({ flags: ROLL_ON, reduce: true, redPresented: false })).toEqual({
      kind: "none",
    });
  });

  it("near miss: a presented RED makes it static, at any setting", () => {
    for (const reduce of [false, true]) {
      expect(numberRoll({ flags: ROLL_ON, reduce, redPresented: true })).toEqual({
        kind: "none",
      });
    }
  });
});

describe("the filled action gives under the finger (ADR-037 P1)", () => {
  it("is ADR-037 P1's 0.97 on the app's one spring, critically damped and clamped", () => {
    expect(PRESS_SCALE).toBe(0.97);
    expect(PRESS_SPRING).toEqual(BUBBLE_SPRING);
    const zeta = PRESS_SPRING.damping / (2 * Math.sqrt(PRESS_SPRING.stiffness * PRESS_SPRING.mass));
    expect(zeta).toBeGreaterThanOrEqual(1);
    expect(PRESS_SPRING.overshootClamping).toBe(true);
  });

  it("scales only when the call site opts in and the redesign is on", () => {
    expect(pressScale({ enabled: true, ...CALM })).toEqual({
      kind: "scale",
      to: PRESS_SCALE,
      spring: PRESS_SPRING,
    });
    expect(pressScale({ enabled: false, ...CALM })).toEqual({ kind: "none" });
  });

  it("near miss: Reduce Motion leaves only the instant opacity step", () => {
    expect(pressScale({ enabled: true, reduce: true, redPresented: false })).toEqual({
      kind: "none",
    });
  });

  it("near miss: never while a RED is presented", () => {
    expect(pressScale({ enabled: true, reduce: false, redPresented: true })).toEqual({
      kind: "none",
    });
  });

  it("never smaller than 0.97: a deeper press is a bounce by another name", () => {
    expect(PRESS_SCALE).toBeGreaterThanOrEqual(0.97);
    expect(PRESS_SCALE).toBeLessThan(1);
  });
});

describe("the loading wait", () => {
  it("flag off: the platform spinner, as today, at any setting", () => {
    expect(loadingIndicator({ micro: false, reduce: false })).toBe("spinner");
    expect(loadingIndicator({ micro: false, reduce: true })).toBe("spinner");
  });

  it("the redesign keeps the spinner while motion is allowed", () => {
    expect(loadingIndicator({ micro: true, reduce: false })).toBe("spinner");
  });

  it("near miss: under Reduce Motion the redesign shows a still glyph", () => {
    expect(loadingIndicator({ micro: true, reduce: true })).toBe("still");
  });
});

/**
 * INT-492: the micro-interactions' motion, as numbers (GitHub #839).
 *
 * The redesign moves only what the ratified ADRs allow, and each rule here is
 * one of them. The "Soru N / M" capsule moves nothing at all: it swaps with
 * the step, and the question's 120 ms fade stays the step's one animated
 * element (ADR-033 §2, C9). The owner declined the rolling number on
 * 16 Oct 2026, so none exists.
 *
 * - the filled action gives 0.97 under the finger on ADR-037 P1's critically
 *   damped spring, absent under Reduce Motion and on RED;
 * - the loading wait keeps the platform spinner, and under Reduce Motion it
 *   shows a still glyph instead, so nothing on the screen moves.
 *
 * Each rule has its near miss: the same inputs with one switched.
 */
import { describe, expect, it } from "vitest";

import { BUBBLE_SPRING } from "./bubbles";
import { PRESS_SCALE, PRESS_SPRING, loadingIndicator, pressScale } from "./micro";

const CALM = { reduce: false, redPresented: false } as const;

describe("the filled action gives under the finger (ADR-037 P1)", () => {
  it("is ADR-037 P1's 0.97 on the app's one spring, critically damped and clamped", () => {
    expect(PRESS_SCALE).toBe(0.97);
    expect(PRESS_SPRING).toEqual(BUBBLE_SPRING);
    const zeta = PRESS_SPRING.damping / (2 * Math.sqrt(PRESS_SPRING.stiffness * PRESS_SPRING.mass));
    expect(zeta).toBeGreaterThanOrEqual(1);
    expect(PRESS_SPRING.overshootClamping).toBe(true);
  });

  it("scales only when the call site opts in", () => {
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
  it("keeps the platform spinner while motion is allowed", () => {
    expect(loadingIndicator({ reduce: false })).toBe("spinner");
  });

  it("near miss: under Reduce Motion it shows a still glyph", () => {
    expect(loadingIndicator({ reduce: true })).toBe("still");
  });
});

/**
 * ADR-038 A3: the in-tree detent sheet (INT-473).
 *
 * Two detents, medium (half the frame) and large (just under the screen's
 * own bar, because an in-tree sheet lives below the native header). A drag
 * follows the finger; a release settles to the detent the throw points at,
 * or dismisses past the threshold. Presenting and settling use A1's
 * critically damped spring, so nothing overshoots.
 *
 * - A patient's dismissal settles with the same spring.
 * - A privacy close and a RED close are instant, at every setting: RED never
 *   waits for a sheet.
 * - Reduce Motion: the sheet appears with the 120 ms fade, closes at once,
 *   and a release snaps to its detent without a spring.
 */
import { describe, expect, it } from "vitest";

import { BUBBLE_SPRING } from "./bubbles";
import {
  SHEET_LARGE_GAP,
  SHEET_SPRING,
  detentOffsets,
  isTap,
  nextDetent,
  settleTarget,
  sheetClose,
  sheetPresent,
  sheetSettle,
} from "./sheet";

const FRAME = { height: 800, top: 100 } as const;

describe("detents", () => {
  it("medium is half the frame; large sits just under the screen's own bar", () => {
    const offsets = detentOffsets(FRAME);
    expect(offsets.medium).toBe(400);
    expect(offsets.large).toBe(FRAME.top + SHEET_LARGE_GAP);
    expect(offsets.large).toBeLessThan(offsets.medium);
  });

  it("large never sits below medium, however tall the bar", () => {
    const offsets = detentOffsets({ height: 300, top: 260 });
    expect(offsets.large).toBeLessThanOrEqual(offsets.medium);
  });
});

describe("settleTarget: where a release goes", () => {
  const offsets = detentOffsets(FRAME);

  it("a still release goes to the nearer detent", () => {
    expect(settleTarget({ offsets, height: FRAME.height, y: 380, velocity: 0 })).toBe("medium");
    expect(settleTarget({ offsets, height: FRAME.height, y: 150, velocity: 0 })).toBe("large");
  });

  it("a throw is followed: upward from medium reaches large, downward from large reaches medium", () => {
    expect(settleTarget({ offsets, height: FRAME.height, y: 390, velocity: -2 })).toBe("large");
    expect(settleTarget({ offsets, height: FRAME.height, y: 130, velocity: 2 })).toBe("medium");
  });

  it("past the dismiss threshold the sheet closes", () => {
    expect(settleTarget({ offsets, height: FRAME.height, y: 650, velocity: 0 })).toBe("closed");
    expect(settleTarget({ offsets, height: FRAME.height, y: 500, velocity: 3 })).toBe("closed");
  });

  it("near miss: a small pull below medium snaps back rather than closing", () => {
    expect(settleTarget({ offsets, height: FRAME.height, y: 450, velocity: 0 })).toBe("medium");
  });
});

describe("motion (ADR-038 A3)", () => {
  it("the spring is A1's critically damped spring, which cannot overshoot", () => {
    expect(SHEET_SPRING).toEqual(BUBBLE_SPRING);
    expect(SHEET_SPRING.overshootClamping).toBe(true);
    const zeta = SHEET_SPRING.damping / (2 * Math.sqrt(SHEET_SPRING.stiffness * SHEET_SPRING.mass));
    expect(zeta).toBeGreaterThanOrEqual(1);
  });

  it("presents on the spring, or with the 120 ms fade under Reduce Motion", () => {
    expect(sheetPresent({ reduce: false })).toEqual({ kind: "spring", spring: SHEET_SPRING });
    const reduced = sheetPresent({ reduce: true });
    expect(reduced.kind).toBe("fade");
    expect(reduced.kind === "fade" ? reduced.fade.durationMs : -1).toBe(120);
  });

  it("settles on the spring, or snaps under Reduce Motion", () => {
    expect(sheetSettle({ reduce: false })).toBe("spring");
    expect(sheetSettle({ reduce: true })).toBe("snap");
  });

  it("a patient's dismissal settles with the spring; under Reduce Motion it is instant", () => {
    expect(sheetClose("patient", { reduce: false })).toBe("spring");
    expect(sheetClose("patient", { reduce: true })).toBe("instant");
  });

  it("a privacy close and a RED close are instant at every setting", () => {
    for (const reduce of [false, true]) {
      expect(sheetClose("privacy", { reduce })).toBe("instant");
      expect(sheetClose("red", { reduce })).toBe("instant");
    }
  });
});

describe("the single-pointer alternative to the drag (SC 2.5.7)", () => {
  it("a tap on the grabber moves to the other detent", () => {
    expect(nextDetent("medium")).toBe("large");
    expect(nextDetent("large")).toBe("medium");
  });

  it("a release that barely moved is a tap; a drag is not", () => {
    expect(isTap({ dx: 1, dy: 2 })).toBe(true);
    expect(isTap({ dx: 0, dy: 12 })).toBe(false);
    expect(isTap({ dx: 12, dy: 0 })).toBe(false);
  });
});

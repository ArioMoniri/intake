import { describe, expect, it } from "vitest";

import { MIN_TAP, slopped, verticalSlop } from "./target";

describe("touch-target floor", () => {
  it("is 44 — above SC 2.5.8's 24 and at the platform guideline", () => {
    expect(MIN_TAP).toBe(44);
    expect(MIN_TAP).toBeGreaterThanOrEqual(24);
  });

  it("lifts a short pill to the floor", () => {
    // The consent state pill: caption 18 + 6 + 6 padding = 30.
    expect(verticalSlop(30)).toEqual({ top: 7, bottom: 7 });
    expect(slopped(30)).toBeGreaterThanOrEqual(MIN_TAP);
  });

  it("lifts a bare caption link to the floor", () => {
    // A lone `caption` line: 13 pt at 1.4 leading = 18.
    expect(verticalSlop(18)).toEqual({ top: 13, bottom: 13 });
    expect(slopped(18)).toBeGreaterThanOrEqual(MIN_TAP);
  });

  it("rounds up so an odd gap still clears the floor", () => {
    expect(slopped(21)).toBeGreaterThanOrEqual(MIN_TAP);
    expect(slopped(43)).toBeGreaterThanOrEqual(MIN_TAP);
  });

  it("adds nothing to an element that already clears the floor", () => {
    expect(verticalSlop(44)).toEqual({ top: 0, bottom: 0 });
    expect(verticalSlop(56)).toEqual({ top: 0, bottom: 0 });
  });

  it("treats a nonsense height as zero rather than producing negative slop", () => {
    expect(verticalSlop(-10)).toEqual({ top: 22, bottom: 22 });
  });
});

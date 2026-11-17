/**
 * INT-372: where the visit card's "›" sits. The measured half, in the shipped
 * title face, is e2e/visitCard.spec.ts; this file pins the policy itself.
 */
import { describe, expect, it } from "vitest";

import { APP_STEPS, LARGE_TEXT_SCALE, isLargeText } from "@/lib/prefs/appearance";
import { spacing } from "@/lib/theme";
import { CHEVRON_GAP, CHEVRON_SIZE, chevronPlacement } from "@/lib/visitCardLayout";

describe("the visit card's chevron placement", () => {
  it("takes a column beside the text below the large-text scale", () => {
    for (const scale of APP_STEPS.filter((step) => step < LARGE_TEXT_SCALE)) {
      expect(chevronPlacement(scale), `at ${scale}`).toBe("beside");
    }
  });

  it("rides the date line from the large-text scale up to the clamp", () => {
    for (const scale of [
      LARGE_TEXT_SCALE,
      ...APP_STEPS.filter((step) => step >= LARGE_TEXT_SCALE),
    ]) {
      expect(chevronPlacement(scale), `at ${scale}`).toBe("dateLine");
    }
    // The OS can report more than the app's own top step; the card must not
    // flip back to the column past the clamp.
    expect(chevronPlacement(3.1)).toBe("dateLine");
  });

  it("changes form at the one scale where the card itself tightens", () => {
    // Themed.tsx's Card drops to md padding at isLargeText; a second
    // threshold here would give the card two different ideas of "large".
    for (const scale of [0.9, 1.0, 1.3, 1.59, 1.6, 1.61, 2.0]) {
      expect(chevronPlacement(scale) === "dateLine", `at ${scale}`).toBe(isLargeText(scale));
    }
  });

  it("reserves the glyph plus a gap, and never less than the glyph", () => {
    expect(CHEVRON_SIZE).toBe(14);
    expect(CHEVRON_GAP).toBe(spacing.sm);
    expect(CHEVRON_GAP).toBeGreaterThan(0);
  });
});

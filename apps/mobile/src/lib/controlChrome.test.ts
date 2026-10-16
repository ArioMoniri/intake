/**
 * INT-492: the answer chip's check slot (GitHub #839).
 *
 * Today a selected chip draws its check by inserting a glyph in front of the
 * label, so selecting a chip widens it and the chips after it reflow: a tap
 * can push the next answer onto the next line, under the patient's finger.
 * The redesign reserves the slot in both states, the way the chat stage's
 * answer cards already do (components/stage/StageControls.tsx): a ring when
 * unselected, a filled disc with a check when selected. The chip keeps its
 * width, the state is never colour alone (SC 1.4.1), and nothing animates:
 * a selection indicator appears instantly (ADR-033 §4).
 */
import { describe, expect, it } from "vitest";

import { colorsFor, type ColorScheme, type Contrast } from "@/lib/theme";

import { CHIP_SLOT, chipChrome, chipSlot } from "./controlChrome";

function luminance(hex: string): number {
  const channel = (i: number) => {
    const c = parseInt(hex.slice(1 + 2 * i, 3 + 2 * i), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(0) + 0.7152 * channel(1) + 0.0722 * channel(2);
}

const ratio = (a: string, b: string) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};

const MODES = (["light", "dark"] as const).flatMap((scheme: ColorScheme) =>
  (["standard", "high"] as const).map((level: Contrast) => ({ scheme, level })),
);

describe("the check slot is reserved in both states", () => {
  it("is the same size selected and unselected, so a tap never reflows the chips", () => {
    const colors = colorsFor("light", "standard");
    expect(chipSlot(colors, true).size).toBe(CHIP_SLOT);
    expect(chipSlot(colors, false).size).toBe(CHIP_SLOT);
  });

  it("unselected is an empty ring; selected is a filled disc with a check", () => {
    const colors = colorsFor("light", "standard");
    expect(chipSlot(colors, false)).toMatchObject({
      fill: null,
      ring: colors.border,
      check: null,
    });
    expect(chipSlot(colors, true)).toMatchObject({
      fill: colors.primary,
      ring: null,
      check: colors.onPrimary,
    });
  });

  it("near miss: the current chip draws its check only when selected, which is the reflow", () => {
    const colors = colorsFor("light", "standard");
    expect(chipChrome(colors, false).check).toBe(false);
    expect(chipChrome(colors, true).check).toBe(true);
  });

  it("is at least the 12 pt the stage cards' check uses, and fits a 44 pt chip", () => {
    expect(CHIP_SLOT).toBeGreaterThanOrEqual(12);
    expect(CHIP_SLOT).toBeLessThan(44);
  });
});

describe("the slot clears the non-text contrast floor (SC 1.4.11)", () => {
  it.each(MODES)("$scheme / $level", (m) => {
    const colors = colorsFor(m.scheme, m.level);
    const off = chipSlot(colors, false);
    const on = chipSlot(colors, true);
    // The ring sits on the unselected chip's fill.
    expect(ratio(off.ring!, chipChrome(colors, false).backgroundColor)).toBeGreaterThanOrEqual(3);
    // The disc sits on the selected chip's tint, and the check on the disc.
    expect(ratio(on.fill!, chipChrome(colors, true).backgroundColor)).toBeGreaterThanOrEqual(3);
    expect(ratio(on.check!, on.fill!)).toBeGreaterThanOrEqual(3);
  });
});

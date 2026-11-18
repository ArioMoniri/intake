/**
 * INT-601 (design audit A4): a selected chip must differ from an unselected
 * one by more than hue. Before this, "selected" was a #EAF5F2 wash (1.05:1
 * against the white chip), a 1 pt teal border and a teal label — close to
 * invisible in sunlight or to a patient who cannot separate the two fills
 * (SC 1.4.1, mobile-ui.md §Status ladder).
 */
import { describe, expect, it } from "vitest";

import { APP_STEPS } from "../prefs/appearance";
import { scaledSize, spacing } from "../theme";
import { CHIP_BORDER, chipChrome, chipLook } from "./chip";

const SCHEMES = ["light", "dark"] as const;

describe("chipLook — selection is a shape, not only a colour", () => {
  it.each(SCHEMES)(
    "%s: a selected chip carries the check glyph and an unselected one none",
    (scheme) => {
      expect(chipLook(true, scheme).glyph).toBe("checkmark");
      expect(chipLook(false, scheme).glyph).toBeNull();
    },
  );

  it.each(SCHEMES)("%s: a selected chip has a heavier outline than an unselected one", (scheme) => {
    expect(chipLook(true, scheme).borderWidth).toBe(CHIP_BORDER.selected);
    expect(chipLook(true, scheme).borderWidth).toBeGreaterThan(chipLook(false, scheme).borderWidth);
  });

  it.each(SCHEMES)("%s: with every colour removed, the two states still differ", (scheme) => {
    // Strip each colour token and compare what is left. This is what a
    // greyscale screen, or a patient with a colour-vision deficiency, gets.
    const shape = (selected: boolean) => {
      const { glyph, borderWidth } = chipLook(selected, scheme);
      return { glyph, borderWidth };
    };
    expect(shape(true)).not.toEqual(shape(false));
  });

  it.each(SCHEMES)("%s: the accessibilityState names the selection, both ways", (scheme) => {
    // The chips are checkbox (multi) and radio (single) roles, whose state is
    // `checked`. `selected` beside it would be read twice ("seçili, işaretli")
    // on both platforms, so it is deliberately absent.
    expect(chipLook(true, scheme).accessibilityState).toEqual({ checked: true });
    expect(chipLook(false, scheme).accessibilityState).toEqual({ checked: false });
    expect(chipLook(true, scheme).accessibilityState).not.toHaveProperty("selected");
  });

  it("near miss: the colour cues are kept, the shape is added to them", () => {
    expect(chipLook(true, "light").fill).toBe("primarySoft");
    expect(chipLook(true, "light").border).toBe("primary");
    expect(chipLook(true, "light").labelColor).toBe("primary");
    expect(chipLook(false, "light").fill).toBe("surface");
    expect(chipLook(false, "light").border).toBe("border");
    // Dark chips stay filled and borderless when unselected (tonal register).
    expect(chipLook(false, "dark").border).toBe("transparent");
  });
});

describe("chipChrome — the horizontal room a chip takes besides its label", () => {
  it("counts the padding, both outlines at their heaviest, the glyph and its gap", () => {
    for (const step of APP_STEPS) {
      const glyph = scaledSize("label", step);
      expect(chipChrome(step)).toBe(2 * spacing.md + 2 * CHIP_BORDER.selected + glyph + spacing.xs);
    }
  });

  it("grows with the text, so the glyph never sits at its base size beside doubled words", () => {
    expect(chipChrome(2.0)).toBeGreaterThan(chipChrome(1.0));
  });
});

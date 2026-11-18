/**
 * The selectable chip's look (INT-601, design audit A4; library-patterns.md
 * P5): one rule for the typed lane's chips and the dialogue's confirm chips.
 *
 * Selection used to be a wash, a 1 pt teal border and a teal label: hue only,
 * and the wash measured 1.05 : 1 against the white chip. A selected chip now
 * also carries a leading check glyph and a heavier outline, so the state
 * survives greyscale, sunlight and a colour-vision deficiency (SC 1.4.1). The
 * colour cues stay; the shape is added to them.
 *
 * The accessibilityState is part of the rule so the look and what a screen
 * reader hears cannot drift apart. The chips are checkbox (multi-select) and
 * radio (single-select) roles, whose state is `checked`; `selected` beside it
 * would be announced a second time on both platforms.
 *
 * Pure: no react-native import, so it is unit-tested in node.
 */
import type { SymbolKey } from "../symbols";
import { scaledSize, spacing, type ColorScheme, type ThemeColors } from "../theme";

/** Outline weights: a hairline at rest, 1.5 pt when selected. */
export const CHIP_BORDER = { rest: 1, selected: 1.5 } as const;

export interface ChipLook {
  /** Leading glyph from the symbol registry; null when not selected. */
  readonly glyph: SymbolKey | null;
  readonly borderWidth: number;
  readonly border: keyof ThemeColors | "transparent";
  readonly fill: keyof ThemeColors;
  readonly labelColor: keyof ThemeColors;
  readonly accessibilityState: { readonly checked: boolean };
}

export function chipLook(selected: boolean, scheme: ColorScheme): ChipLook {
  if (selected) {
    return {
      glyph: "checkmark",
      borderWidth: CHIP_BORDER.selected,
      border: "primary",
      fill: "primarySoft",
      labelColor: "primary",
      accessibilityState: { checked: true },
    };
  }
  return {
    glyph: null,
    borderWidth: CHIP_BORDER.rest,
    // Dark chips are filled and borderless at rest (tonal separation); light
    // keeps the hairline (design pass 4).
    border: scheme === "dark" ? "transparent" : "border",
    fill: "surface",
    labelColor: "ink",
    accessibilityState: { checked: false },
  };
}

/** The glyph is drawn at the label's size, so it scales with the text. */
export function chipGlyphSize(fontScale: number): number {
  return scaledSize("label", fontScale);
}

/**
 * The horizontal room a chip takes besides its label at `fontScale`, measured
 * in its selected state, the wider one: padding, both outlines, the glyph and
 * the gap after it.
 */
export function chipChrome(fontScale: number): number {
  return 2 * spacing.md + 2 * CHIP_BORDER.selected + chipGlyphSize(fontScale) + spacing.xs;
}

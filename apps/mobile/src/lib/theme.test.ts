import { describe, expect, it } from "vitest";

import { lineHeight, palette, scaledSize, typeScale } from "./theme";

// WCAG 2.x relative luminance + contrast ratio, computed here so the
// accessibility floor (02 §8.2: body text AA) is a test, not a hope.
function channel(v: number): number {
  const s = v / 255;
  return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string): number {
  const n = parseInt(hex.slice(1), 16);
  return (
    0.2126 * channel((n >> 16) & 0xff) +
    0.7152 * channel((n >> 8) & 0xff) +
    0.0722 * channel(n & 0xff)
  );
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

describe("palette", () => {
  it("light and dark expose the same token set", () => {
    expect(Object.keys(palette.dark).sort()).toEqual(Object.keys(palette.light).sort());
  });

  it.each(["light", "dark"] as const)("%s body text meets WCAG AA (4.5:1)", (scheme) => {
    const c = palette[scheme];
    expect(contrast(c.ink, c.background)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(c.ink, c.surface)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(c.inkSoft, c.surface)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(c.primary, c.background)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(c.onPrimary, c.primary)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(c.amber, c.amberSoft)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(c.emergency, c.emergencySoft)).toBeGreaterThanOrEqual(4.5);
    // Kickers, sent chips and scope pills set primary text on the soft wash.
    expect(contrast(c.primary, c.primarySoft)).toBeGreaterThanOrEqual(4.5);
  });
});

describe("dynamic type", () => {
  it("body is 17 at fontScale 1.0", () => {
    expect(scaledSize("body", 1.0)).toBe(17);
  });

  it("follows the user's scale up to 2.0 and no further (02 §8.2)", () => {
    expect(scaledSize("body", 1.5)).toBe(Math.round(17 * 1.5));
    expect(scaledSize("body", 2.0)).toBe(34);
    expect(scaledSize("body", 3.0)).toBe(34);
  });

  it("never collapses below half scale", () => {
    expect(scaledSize("body", 0.1)).toBe(Math.round(17 * 0.5));
  });

  it("line height: display roles sit tight (1.2×), reading roles keep diacritic room (1.4×)", () => {
    // Design pass 3: the serif display collapses at book leading; body text
    // keeps 1.4 so Turkish diacritics (ğ, ş, İ) never clip at reading sizes.
    for (const role of Object.keys(typeScale) as (keyof typeof typeScale)[]) {
      const factor = role === "hero" || role === "title" ? 1.2 : 1.4;
      expect(lineHeight(role, 1.0)).toBe(Math.round(typeScale[role] * factor));
    }
  });
});

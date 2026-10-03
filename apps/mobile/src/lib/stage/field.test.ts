/**
 * The stage's filled field (ADR-039 S7, INT-464): INT-433's filled rule in the
 * stage palette. A field is a solid field fill with no resting outline; focus
 * draws a 2 pt accent ring; Increase Contrast gives the resting field its
 * boundary back. The ring is a non-text indicator, so it is held to 3:1
 * against the fill (SC 1.4.11) in every mode.
 */
import { describe, expect, it } from "vitest";

import { stageFieldChrome } from "./field";
import { stagePalette } from "./palette";

function channel(c: number): number {
  const s = c / 255;
  return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string): number {
  const v = hex.replace("#", "");
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(v.slice(i, i + 2), 16));
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/** True when some point of a gradient through `grounds` has `fill`'s luminance. */
function insideWash(fill: string, grounds: readonly string[]): boolean {
  const levels = grounds.map(luminance);
  const value = luminance(fill);
  return value >= Math.min(...levels) && value <= Math.max(...levels);
}

const SCHEMES = ["light", "dark"] as const;
const MODES = [
  { reduceTransparency: false, increasedContrast: false },
  { reduceTransparency: true, increasedContrast: false },
  { reduceTransparency: false, increasedContrast: true },
  { reduceTransparency: true, increasedContrast: true },
] as const;

describe("stage field chrome (ADR-039 S7)", () => {
  it("at rest: the solid field fill and no outline", () => {
    for (const scheme of SCHEMES) {
      const p = stagePalette(scheme, { reduceTransparency: false, increasedContrast: false });
      const chrome = stageFieldChrome(p, { focused: false });
      expect(chrome.backgroundColor).toBe(p.field);
      expect(chrome.borderWidth).toBe(0);
    }
  });

  it("a resting field stands apart from the whole wash, in every mode (at least 1.1:1)", () => {
    // With no resting outline, the fill is what shows where the field is. The
    // wash is a gradient, so it passes through every luminance between its
    // stops: the field must sit outside that range, then clear the nearest
    // stop. The bound matches the step iOS's own filled field takes from its
    // ground.
    for (const scheme of SCHEMES) {
      for (const mode of MODES) {
        const p = stagePalette(scheme, mode);
        const grounds = [p.base, ...p.wash];
        expect(insideWash(p.field, grounds), `${scheme} field inside the wash`).toBe(false);
        for (const ground of grounds) {
          expect(contrast(p.field, ground), `${scheme} field on ${ground}`).toBeGreaterThanOrEqual(
            1.1,
          );
        }
      }
    }
  });

  it("near miss: the dark answer card sits inside the wash's range, so a field has its own fill", () => {
    const p = stagePalette("dark", { reduceTransparency: false, increasedContrast: false });
    expect(insideWash(p.card, [p.base, ...p.wash])).toBe(true);
    expect(p.field).not.toBe(p.card);
  });

  it("focused: a 2 pt accent ring", () => {
    for (const scheme of SCHEMES) {
      const p = stagePalette(scheme, { reduceTransparency: false, increasedContrast: false });
      const chrome = stageFieldChrome(p, { focused: true });
      expect(chrome.borderWidth).toBe(2);
      expect(chrome.borderColor).toBe(p.accent);
      expect(chrome.backgroundColor).toBe(p.field);
    }
  });

  it("Increase Contrast gives the resting field its boundary back", () => {
    for (const scheme of SCHEMES) {
      const p = stagePalette(scheme, { reduceTransparency: false, increasedContrast: true });
      const chrome = stageFieldChrome(p, { focused: false });
      expect(chrome.borderWidth).toBe(1);
      expect(chrome.borderColor).toBe(p.cardBorder);
    }
  });

  it("near miss: without Increase Contrast the resting field has no boundary to show", () => {
    const p = stagePalette("light", { reduceTransparency: false, increasedContrast: false });
    expect(p.cardBorder).toBeNull();
    expect(stageFieldChrome(p, { focused: false }).borderColor).toBe("transparent");
  });

  it("the focus ring reaches 3:1 against the field's fill in every mode (SC 1.4.11)", () => {
    for (const scheme of SCHEMES) {
      for (const mode of MODES) {
        const p = stagePalette(scheme, mode);
        const chrome = stageFieldChrome(p, { focused: true });
        expect(contrast(chrome.borderColor, chrome.backgroundColor), scheme).toBeGreaterThanOrEqual(
          3,
        );
      }
    }
  });

  it("the typed text reaches AA on the field in every mode", () => {
    for (const scheme of SCHEMES) {
      for (const mode of MODES) {
        const p = stagePalette(scheme, mode);
        const chrome = stageFieldChrome(p, { focused: false });
        expect(contrast(p.ink, chrome.backgroundColor)).toBeGreaterThanOrEqual(7);
        expect(contrast(p.inkSoft, chrome.backgroundColor)).toBeGreaterThanOrEqual(4.5);
      }
    }
  });
});

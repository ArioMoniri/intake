/**
 * The conversation stage's palette (chat redesign prototype, INT-462 follow-up).
 *
 * Text sits directly on the ambient backdrop, so every text colour is held to
 * WCAG AA against EVERY stop of the wash, not only the base, and against the
 * solid answer cards. Reduce Transparency flattens the wash to the base and
 * drops the glow; Increase Contrast strengthens the secondary ink.
 */
import { describe, expect, it } from "vitest";

import { colorsFor } from "../theme";

import { stagePalette, type StagePalette } from "./palette";

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

const SCHEMES = ["light", "dark"] as const;
const MODES = [
  { reduceTransparency: false, increasedContrast: false },
  { reduceTransparency: true, increasedContrast: false },
  { reduceTransparency: false, increasedContrast: true },
  { reduceTransparency: true, increasedContrast: true },
] as const;

function every(fn: (p: StagePalette, label: string) => void): void {
  for (const scheme of SCHEMES) {
    for (const mode of MODES) {
      fn(stagePalette(scheme, mode), `${scheme} ${JSON.stringify(mode)}`);
    }
  }
}

/** Every RED colour token, in both schemes and both contrasts. */
const RED_COLOURS = new Set(
  SCHEMES.flatMap((scheme) =>
    (["standard", "high"] as const).flatMap((level) => {
      const colors = colorsFor(scheme, level);
      return [colors.emergency, colors.emergencySoft].map((c) => c.toUpperCase());
    }),
  ),
);

/** The RED colours a palette carries anywhere in its values. */
function redIn(value: unknown): string[] {
  if (typeof value === "string") {
    return RED_COLOURS.has(value.toUpperCase()) ? [value.toUpperCase()] : [];
  }
  if (value !== null && typeof value === "object") {
    return Object.values(value).flatMap(redIn);
  }
  return [];
}

describe("stage palette: text on the ambient backdrop", () => {
  it("ink and inkSoft reach AA on the base and on every wash stop", () => {
    every((p, label) => {
      for (const ground of [p.base, ...p.wash]) {
        expect(contrast(p.ink, ground), `${label} ink on ${ground}`).toBeGreaterThanOrEqual(7);
        expect(contrast(p.inkSoft, ground), `${label} inkSoft on ${ground}`).toBeGreaterThanOrEqual(
          4.5,
        );
      }
    });
  });

  it("answer cards are solid and their text reaches AA, selected or not", () => {
    every((p, label) => {
      expect(p.card, label).toMatch(/^#[0-9A-F]{6}$/i);
      expect(contrast(p.ink, p.card), `${label} ink on card`).toBeGreaterThanOrEqual(7);
      expect(contrast(p.inkSoft, p.card), `${label} inkSoft on card`).toBeGreaterThanOrEqual(4.5);
      expect(
        contrast(p.cardInkSelected, p.cardSelected),
        `${label} selected card text`,
      ).toBeGreaterThanOrEqual(4.5);
    });
  });

  it("the accent reaches 3:1 on the base, as a control boundary must", () => {
    every((p, label) => {
      expect(contrast(p.accent, p.base), label).toBeGreaterThanOrEqual(3);
    });
  });
});

/** A veil of `color` at `alpha` over `ground`: the colour a control's label sits on. */
function over(ground: string, veil: { color: string; alpha: number }): string {
  const parse = (hex: string) =>
    [0, 2, 4].map((i) => parseInt(hex.replace("#", "").slice(i, i + 2), 16));
  const [g, v] = [parse(ground), parse(veil.color)];
  return `#${g
    .map((c, i) => Math.round(c * (1 - veil.alpha) + v[i] * veil.alpha))
    .map((c) => c.toString(16).padStart(2, "0"))
    .join("")}`;
}

describe("stage palette: labels on the glass controls (ADR-039 S3)", () => {
  // System glass is modelled as the palette's control veil over each wash
  // stop. The model is a floor, not a measurement: the evidence records the
  // contrast measured on the simulator captures as well.
  it("a control label reaches AA on the veil over every wash stop", () => {
    every((p, label) => {
      for (const ground of [p.base, ...p.wash]) {
        const fill = over(ground, p.controlVeil);
        expect(contrast(p.ink, fill), `${label} ink on veil over ${ground}`).toBeGreaterThanOrEqual(
          4.5,
        );
      }
    });
  });

  it("the tinted primary action's label reaches AA on its tint", () => {
    every((p, label) => {
      expect(contrast(p.cardInkSelected, p.cardSelected), label).toBeGreaterThanOrEqual(4.5);
    });
  });

  it("near miss: a faint label on the light veil would fail", () => {
    const p = stagePalette("light", { reduceTransparency: false, increasedContrast: false });
    expect(contrast("#B8C2C0", over(p.base, p.controlVeil))).toBeLessThan(4.5);
  });
});

describe("stage palette: accessibility settings", () => {
  it("Reduce Transparency flattens the wash to the base and drops the glow", () => {
    for (const scheme of SCHEMES) {
      const p = stagePalette(scheme, { reduceTransparency: true, increasedContrast: false });
      expect(p.wash).toEqual([p.base, p.base, p.base]);
      expect(p.glow).toBeNull();
    }
  });

  it("near miss: without Reduce Transparency the wash is a real gradient with a glow", () => {
    for (const scheme of SCHEMES) {
      const p = stagePalette(scheme, { reduceTransparency: false, increasedContrast: false });
      expect(new Set(p.wash).size).toBeGreaterThan(1);
      expect(p.glow).not.toBeNull();
    }
  });

  it("Increase Contrast strengthens the secondary ink and gives cards a boundary", () => {
    for (const scheme of SCHEMES) {
      const base = stagePalette(scheme, { reduceTransparency: false, increasedContrast: false });
      const high = stagePalette(scheme, { reduceTransparency: false, increasedContrast: true });
      expect(contrast(high.inkSoft, high.base)).toBeGreaterThan(contrast(base.inkSoft, base.base));
      expect(base.cardBorder).toBeNull();
      expect(high.cardBorder).not.toBeNull();
    }
  });

  it("RED's colours are not in it, in either scheme or contrast (ADR-039 S6, invariant 21)", () => {
    every((p, label) => {
      expect(redIn(p), label).toEqual([]);
    });
  });

  it("near miss: a stage colour equal to a RED token would be found", () => {
    const p = stagePalette("light", { reduceTransparency: false, increasedContrast: false });
    const red = colorsFor("light", "standard").emergency;
    expect(redIn({ ...p, accent: red.toLowerCase() })).toEqual([red.toUpperCase()]);
  });

  it("the dark stage is a night palette, never pure black (Oura-like, not OLED-off)", () => {
    const dark = stagePalette("dark", { reduceTransparency: false, increasedContrast: false });
    expect(dark.base.toUpperCase()).not.toBe("#000000");
    expect(luminance(dark.base)).toBeLessThan(0.02);
  });
});

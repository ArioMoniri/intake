/**
 * INT-433: the question screen's presentation rules, as data.
 *
 * The owner's 2 Oct 2026 review of the store shot: the row of grey dots, the
 * outlined answer box and the outlined chips did not read as a native Apple
 * screen. The redesign replaces them with a thin determinate bar and a
 * "Soru N / M" line, a filled field with a focus ring, and filled capsule
 * chips with a check on the selected state. The rules behind each are pure,
 * so this suite holds them in node: what the bar and the line say, which
 * tokens each control is painted with, and that every pair it paints clears
 * its contrast floor in light, dark and Increase Contrast.
 */
import { describe, expect, it } from "vitest";

import { en } from "../i18n/en";
import { tr } from "../i18n/tr";
import { colorsFor, type ColorScheme, type Contrast, type ThemeColors } from "../theme";
import {
  FOCUS_RING,
  chipChrome,
  filledFieldChrome,
  positionLabel,
  positionSpoken,
  questionPosition,
} from "./questionScreen";

const ids = (...names: string[]) => names.map((id) => ({ id }));

function luminance(hex: string): number {
  const channel = (i: number) => {
    const c = parseInt(hex.slice(1 + 2 * i, 3 + 2 * i), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(0) + 0.7152 * channel(1) + 0.0722 * channel(2);
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const MODES: readonly { scheme: ColorScheme; level: Contrast }[] = (
  ["light", "dark"] as const
).flatMap((scheme) => (["standard", "high"] as const).map((level) => ({ scheme, level })));

describe("the progress position (Soru N / M)", () => {
  it("is the current question's place in the APPLICABLE list, never the pack", () => {
    const applicable = ids("a", "b", "c", "d");
    const position = questionPosition(applicable, "c", false);
    expect(position).toEqual({ position: 3, total: 4, fraction: 0.75, mayGrow: false });
  });

  it("carries the flow's growth flag, so the screen can say more may follow", () => {
    expect(questionPosition(ids("a", "b"), "a", true).mayGrow).toBe(true);
  });

  it("opens at the first question and fills the bar at the last", () => {
    const applicable = ids("a", "b", "c");
    expect(questionPosition(applicable, "a", false).fraction).toBeCloseTo(1 / 3);
    expect(questionPosition(applicable, "c", false).fraction).toBe(1);
  });

  it("an id outside the applicable list (an edit) sits at the first place, never at zero", () => {
    const position = questionPosition(ids("a", "b"), "zz", false);
    expect(position.position).toBe(1);
    expect(position.fraction).toBeGreaterThan(0);
  });

  it("an empty list still yields a finite bar (no division by zero)", () => {
    const position = questionPosition([], "a", false);
    expect(Number.isFinite(position.fraction)).toBe(true);
    expect(position.total).toBe(1);
  });
});

describe("the numerals are display-only (invariant 22)", () => {
  it("the visible line is the catalogue word plus the two numbers", () => {
    const position = questionPosition(ids("a", "b", "c", "d", "e", "f", "g", "h", "i"), "c", false);
    expect(positionLabel(position, tr["intake.progress.question"])).toBe("Soru 3 / 9");
    expect(positionLabel(position, en["intake.progress.question"])).toBe("Question 3 / 9");
  });

  it("no number is grouped: a long flow prints its digits as one run", () => {
    const many = Array.from({ length: 1200 }, (_, i) => ({ id: `q${i}` }));
    const label = positionLabel(questionPosition(many, "q1199", false), "Soru");
    expect(label).toBe("Soru 1200 / 1200");
    expect(label).not.toMatch(/\d[.,  ]\d{3}/u);
  });

  it("the reader hears one progress value, worded rather than slashed", () => {
    const position = questionPosition(ids("a", "b", "c", "d", "e", "f", "g", "h", "i"), "c", false);
    expect(positionSpoken(position, tr["intake.progress.question"], tr["intake.progress.of"])).toBe(
      "Soru 3, toplam 9",
    );
    expect(positionSpoken(position, en["intake.progress.question"], en["intake.progress.of"])).toBe(
      "Question 3, out of 9",
    );
  });

  it("the catalogue carries the words only; every numeral is inserted at render", () => {
    for (const key of [
      "intake.progress.name",
      "intake.progress.question",
      "intake.progress.of",
      "intake.progress.grows",
    ] as const) {
      expect(tr[key]?.trim().length, key).toBeGreaterThan(0);
      expect(en[key]?.trim().length, key).toBeGreaterThan(0);
      expect(tr[key], key).not.toMatch(/[0-9]/u);
      expect(en[key], key).not.toMatch(/[0-9]/u);
    }
  });

  it("the old answered-count line is gone from both catalogues", () => {
    expect(Object.keys(tr)).not.toContain("intake.progress.answered");
    expect(Object.keys(en)).not.toContain("intake.progress.answered");
  });
});

describe("the filled answer field", () => {
  const light = colorsFor("light", "standard");

  it("rests as a fill with no outline", () => {
    const rest = filledFieldChrome(light, { focused: false, increasedContrast: false });
    expect(rest.backgroundColor).toBe(light.surface);
    expect(rest.borderColor).toBe("transparent");
  });

  it("draws a tint-coloured focus ring while the patient is typing", () => {
    const focused = filledFieldChrome(light, { focused: true, increasedContrast: false });
    expect(focused.borderColor).toBe(light.primary);
    expect(focused.borderWidth).toBe(FOCUS_RING);
  });

  it("keeps one border width in every state, so focusing never moves the text", () => {
    const widths = [false, true].flatMap((focused) =>
      [false, true].map(
        (increasedContrast) => filledFieldChrome(light, { focused, increasedContrast }).borderWidth,
      ),
    );
    expect(new Set(widths)).toEqual(new Set([FOCUS_RING]));
  });

  it("under Increase Contrast the resting field gets the control boundary back", () => {
    const high = colorsFor("light", "high");
    const rest = filledFieldChrome(high, { focused: false, increasedContrast: true });
    expect(rest.borderColor).toBe(high.border);
  });
});

describe("the capsule choice chips", () => {
  const light = colorsFor("light", "standard");

  it("an unselected chip is a filled capsule with no outline and no mark", () => {
    const off = chipChrome(light, false);
    expect(off).toEqual({ backgroundColor: light.surface, textColor: "ink", check: false });
  });

  it("a selected chip is tinted AND carries a check, so the state is not colour alone", () => {
    const on = chipChrome(light, true);
    expect(on).toEqual({ backgroundColor: light.primarySoft, textColor: "primary", check: true });
  });
});

describe("every pair the redesign paints clears its floor (AA text, 3:1 graphics)", () => {
  const pairs = (c: ThemeColors) => ({
    // The selected chip's label (text, AA) and check (graphic, 3:1) on its tint.
    selectedLabel: [c.primary, c.primarySoft, 4.5],
    unselectedLabel: [c.ink, c.surface, 7],
    // The patient's own words in the filled field (clinical text, AAA).
    fieldText: [c.ink, c.surface, 7],
    // The focus ring against the page and against the field's own fill.
    focusOnPage: [c.primary, c.background, 3],
    focusOnField: [c.primary, c.surface, 3],
    // The bar's fill against its track, and the count line on the page.
    barFill: [c.primary, c.surfaceRaised, 3],
    count: [c.inkSoft, c.background, 7],
  });

  it.each(MODES)("$scheme/$level", ({ scheme, level }) => {
    const failing = Object.entries(pairs(colorsFor(scheme, level)))
      .filter(([, [fg, bg, floor]]) => contrast(fg as string, bg as string) < (floor as number))
      .map(([name, [fg, bg]]) => `${name}: ${contrast(fg as string, bg as string).toFixed(2)}`);
    expect(failing).toEqual([]);
  });
});

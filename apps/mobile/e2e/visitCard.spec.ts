/**
 * INT-372: a long department name wraps before the visit card's "›". It never
 * runs under the arrow, and the arrow's room never breaks a word mid-way where
 * the card could have held it.
 *
 * On main the chevron was painted at the card's right edge (`position:
 * "absolute"`, `top: "50%"`) while the text spanned the whole card, so
 * "Kadın Hastalıkları ve Doğum" wrapped straight under the arrow (int-demo
 * 01e224a2). The card now reserves the chevron's width. This file proves the
 * reservation is layout rather than paint, and measures what it costs the
 * department name with the INT-295 reader. Since INT-422 the title ships in
 * SF Pro Semibold, which is not redistributable; it is measured in Inter
 * SemiBold, whose advances run wider (docs/evidence/INT-422.md), so a word
 * that fits here fits on the device.
 *
 * React Native has no DOM, so, as in overflow.spec.ts, the tree proves the
 * wiring and arithmetic proves the fit. The card geometry the arithmetic uses
 * (screen gutter, border, padding at each scale) is read back out of
 * Themed.tsx, so a change there reddens this file instead of leaving it
 * measuring a card that no longer exists.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { readFontMetrics } from "./fontMetrics";
import { en } from "@/lib/i18n/en";
import { tr } from "@/lib/i18n/tr";
import { APP_STEPS, isLargeText } from "@/lib/prefs/appearance";
import { SEED_BRANCHES } from "@/lib/taxonomy/branches";
import { scaledSize, spacing } from "@/lib/theme";
import { CHEVRON_GAP, CHEVRON_SIZE, chevronPlacement } from "@/lib/visitCardLayout";

const MOBILE = join(__dirname, "..");

function source(name: string): string {
  return readFileSync(join(MOBILE, name), "utf8");
}

/** Code only, comments dropped: overflow.spec.ts's stripper, for the same reason. */
function code(text: string): string {
  return text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

/** WCAG 1.4.10's reflow width, and the bound the issue names. */
const NARROWEST = 320;
/** The narrowest iPhone the app supports (SE, 2nd and 3rd generation). */
const IPHONE_SE = 375;
/** Themed.tsx's card draws no border since INT-422 (asserted below). */
const CARD_BORDER = 0;

/** Themed.tsx's Card: the 16 pt content margin at every scale (asserted below). */
function cardPadding(): number {
  return spacing.md;
}

/** The card's content box on a screen `width` points wide. */
/** The card's content box: the same at every scale since INT-422. */
function contentWidth(width: number, _scale: number): number {
  return width - 2 * spacing.screen - 2 * CARD_BORDER - 2 * cardPadding();
}

/** What the department name may use once the chevron has its room. */
function titleMeasure(width: number, scale: number): number {
  const content = contentWidth(width, scale);
  return chevronPlacement(scale) === "beside" ? content - CHEVRON_SIZE - CHEVRON_GAP : content;
}

const titleFace = readFontMetrics(
  join(MOBILE, "node_modules/@expo-google-fonts/inter/600SemiBold/Inter_600SemiBold.ttf"),
);
const captionFace = readFontMetrics(
  join(MOBILE, "node_modules/@expo-google-fonts/inter/400Regular/Inter_400Regular.ttf"),
);

/** The name the owner saw run under the arrow. */
const LONG_NAME = "Kadın Hastalıkları ve Doğum";

/** Every word a department line can hold: the branch taxonomy plus that name. */
const WORDS = [
  ...new Set(
    [...SEED_BRANCHES.map((branch) => branch.nameTr), LONG_NAME].flatMap((name) =>
      name.split(/\s+/),
    ),
  ),
];

/** Words that fit a card with no chevron at all, and do not fit this one. */
function brokenByTheChevron(width: number, scale: number): string[] {
  const size = scaledSize("title", scale);
  return WORDS.filter((word) => {
    const advance = titleFace.advance(word, size);
    return advance <= contentWidth(width, scale) && advance > titleMeasure(width, scale);
  });
}

/**
 * Where the column beside the text still costs a long subspecialty word its
 * line: the one app step below the large-text scale, on a 320 pt screen,
 * where the card has 230 pt and the column takes 22. Measured upper bounds
 * (no kerning) at 31 pt: 221.0, 210.0 and 227.2 pt against 208. Such a word
 * breaks inside itself instead of hiding a letter under the arrow, which is
 * what main does. No supported iPhone width is affected (asserted below).
 * The owner can remove the case by choosing the date-line form at every
 * scale. This list may only shrink.
 */
const COLUMN_RESIDUAL: Readonly<Record<string, readonly string[]>> = {
  // Emptied by INT-422: the 16 pt margins and the Title 3 size give the
  // card 254 pt at 320 pt, and every subspecialty word now keeps its line.
};

describe("the visit card reserves the chevron's width", () => {
  it("lays the chevron out beside the text instead of painting it over the text", () => {
    const card = code(source("src/components/VisitCard.tsx"));
    // An absolutely positioned glyph takes no room from the text it sits on:
    // that is the defect, whatever offsets it is given.
    expect(card).not.toContain('position: "absolute"');
    expect(card).not.toContain('top: "50%"');
    expect(card).toContain("chevronPlacement(");
    expect(card).toContain("size={CHEVRON_SIZE}");
    // The text column is the flexible one; the chevron keeps its own width.
    expect(card).toMatch(/text: \{[^}]*flex: 1/);
    expect(card).toMatch(/column: \{[^}]*marginLeft: CHEVRON_GAP/);
    expect(card).toMatch(/dateLine: \{[^}]*flexDirection: "row"/);
  });

  it("measures the card Themed.tsx actually draws", () => {
    const themed = code(source("src/components/Themed.tsx"));
    expect(themed).toMatch(/ {2}card: \{[^}]*padding: spacing\.md,/);
    expect(themed).not.toMatch(/ {2}card: \{[^}]*borderWidth/);
    expect(themed).toContain("screen: { flex: 1, padding: spacing.screen }");
  });

  it("finds the words it is supposed to measure", () => {
    // A scan over an empty list passes for the wrong reason.
    expect(SEED_BRANCHES.length).toBeGreaterThan(50);
    expect(WORDS).toContain("Hastalıkları");
    expect(WORDS.length).toBeGreaterThan(80);
  });
});

describe("a long department name wraps at a space, never under the chevron", () => {
  it("at the largest step on a 320 pt screen the long name wraps, and every word keeps a line", () => {
    const size = scaledSize("title", 2.0);
    const measure = titleMeasure(NARROWEST, 2.0);
    // The case is real: the name cannot sit on one line here.
    expect(titleFace.advance(LONG_NAME, size)).toBeGreaterThan(measure);
    for (const word of LONG_NAME.split(" ")) {
      expect(titleFace.advance(word, size), `${word} at ${size} pt`).toBeLessThanOrEqual(measure);
    }
  });

  it("from the large-text scale up the chevron costs the name nothing", () => {
    // Beside the text at 2.0, "Hastalıkları" (245.2 pt) would lose the 0.8 pt
    // by which it fits a 320 pt card and break as "Hastalıkla / rı", the
    // mid-word break 00 §2 exists to prevent. On the date line it costs 0.
    for (const width of [NARROWEST, IPHONE_SE]) {
      for (const scale of [...APP_STEPS.filter(isLargeText), 3.1]) {
        expect(titleMeasure(width, scale)).toBe(contentWidth(width, scale));
        expect(brokenByTheChevron(width, scale), `${width} pt at ${scale}`).toEqual([]);
      }
    }
  });

  it("below it, the column breaks no word on a supported iPhone, and only the recorded ones at 320 pt", () => {
    for (const scale of APP_STEPS) {
      expect(brokenByTheChevron(IPHONE_SE, scale), `${IPHONE_SE} pt at ${scale}`).toEqual([]);
      const key = `${NARROWEST}@${scale}`;
      expect([...brokenByTheChevron(NARROWEST, scale)].sort(), key).toEqual(
        [...(COLUMN_RESIDUAL[key] ?? [])].sort(),
      );
    }
  });

  it("the date line keeps every date word whole beside the chevron at the largest step", () => {
    const size = scaledSize("caption", 2.0);
    const line = contentWidth(NARROWEST, 2.0) - CHEVRON_SIZE - CHEVRON_GAP;
    const days = Array.from({ length: 7 }, (_, i) => new Date(Date.UTC(2026, 0, 5 + i)));
    const months = Array.from({ length: 12 }, (_, i) => new Date(Date.UTC(2026, i, 15)));
    const words = new Set<string>();
    for (const locale of ["tr-TR", "en-GB"]) {
      for (const day of days) {
        words.add(
          new Intl.DateTimeFormat(locale, { weekday: "long", timeZone: "UTC" }).format(day),
        );
      }
      for (const month of months) {
        words.add(
          new Intl.DateTimeFormat(locale, { month: "long", timeZone: "UTC" }).format(month),
        );
      }
    }
    for (const text of [tr["visits.noDate"], en["visits.noDate"]]) {
      for (const word of text.split(/\s+/)) {
        words.add(word);
      }
    }
    expect(words.size).toBeGreaterThan(30);
    const tooWide = [...words].filter((word) => captionFace.advance(word, size) > line);
    expect(tooWide, `date-line words wider than ${line} pt at ${size} pt`).toEqual([]);
  });
});

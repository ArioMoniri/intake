/**
 * INT-422: the design system refresh as source facts
 * (docs/design/system-refresh.md).
 *
 * The owner's complaint was that the app "looks too AI-generated". The
 * refresh answers it in tokens (src/lib/theme.ts, held by theme.test.ts) and
 * in the shared components. This file keeps the AI-generic styling from
 * coming back through a screen or a component: no gradient, no glow or
 * shadow, no tracked eyebrow, no container rounder than iOS draws one, no
 * glass outside the functional chrome, no bundled display face, no emoji
 * standing in for an icon. It also proves the one layout claim the refresh
 * makes: at every Dynamic Type size, up to the accessibility sizes, no
 * question is truncated and no question word breaks mid-way on the
 * narrowest supported iPhone.
 *
 * React Native has no DOM, so, as in overflow.spec.ts and visitCard.spec.ts,
 * the tree proves the wiring and arithmetic proves the fit.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";

import { readFontMetrics } from "./fontMetrics";
import { en } from "@/lib/i18n/en";
import { tr } from "@/lib/i18n/tr";
import { allQuestions } from "@/lib/intake/questions";
import { scaledSize, spacing, typeScale } from "@/lib/theme";

const MOBILE = join(__dirname, "..");
const SRC = join(MOBILE, "src");

interface SourceFile {
  readonly name: string;
  readonly source: string;
}

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

/** Code only: the files explain what they avoid, and a guard must read what they do. */
const code = (source: string): string =>
  source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");

/** App code only; tests may name what the app must not. */
const TREE: readonly SourceFile[] = walk(SRC)
  .filter((path) => /\.tsx?$/.test(path) && !/\.test\.ts$/.test(path))
  .map((path) => ({
    name: relative(MOBILE, path).split(sep).join("/"),
    source: code(readFileSync(path, "utf8")),
  }))
  .sort((a, b) => a.name.localeCompare(b.name));

const COMPONENTS = TREE.filter((f) => f.name.startsWith("src/components/"));

function file(name: string): string {
  const found = TREE.find((f) => f.name === name);
  if (found === undefined) {
    throw new Error(`${name} is not in the app tree`);
  }
  return found.source;
}

/** Files that load `module` at runtime (a type-only import loads nothing). */
function importersOf(module: string): string[] {
  const quoted = module.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&");
  const pattern = new RegExp(`(from\\s+|import\\(\\s*)["']${quoted}["']`);
  const typeOnly = /import\s+type\s[^;]*?from\s+["'][^"']+["'];?/g;
  return TREE.filter((f) => pattern.test(f.source.replace(typeOnly, ""))).map((f) => f.name);
}

/** Every file whose code matches `pattern`. */
function offenders(pattern: RegExp, tree: readonly SourceFile[] = TREE): string[] {
  return tree.filter((f) => pattern.test(f.source)).map((f) => f.name);
}

it("the scanner sees the tree it polices", () => {
  expect(TREE.length).toBeGreaterThan(150);
  expect(COMPONENTS.length).toBeGreaterThan(30);
  expect(TREE.map((f) => f.name)).toContain("src/components/Themed.tsx");
});

describe("no AI-generic styling", () => {
  it("no gradient: nothing imports expo-linear-gradient or draws a LinearGradient", () => {
    expect(importersOf("expo-linear-gradient")).toEqual([]);
    expect(offenders(/\bLinearGradient\b/)).toEqual([]);
  });

  it("the gradient scan catches a gradient (near miss)", () => {
    const glow: SourceFile = {
      name: "src/components/Glow.tsx",
      source: '<LinearGradient colors={[a, "transparent"]} />',
    };
    expect(offenders(/\bLinearGradient\b/, [...TREE, glow])).toContain(glow.name);
  });

  it("no glow or drop shadow: depth is tonal, as in Apple's grouped lists", () => {
    expect(
      offenders(/\bshadow(?:Color|Opacity|Radius|Offset)\b|\belevation\s*:|\bboxShadow\b/),
    ).toEqual([]);
  });

  it("no tracked text: SF sets its own tracking at every optical size", () => {
    expect(offenders(/\bletterSpacing\b/)).toEqual([]);
  });

  it("no container is rounder than iOS draws one: every literal radius is at most 12", () => {
    const round: string[] = [];
    for (const f of TREE) {
      for (const m of f.source.matchAll(/borderRadius:\s*(\d+(?:\.\d+)?)/g)) {
        if (Number(m[1]) > 12) {
          round.push(`${f.name}: ${m[0]}`);
        }
      }
    }
    expect(round).toEqual([]);
  });

  it("every 12-pt component container draws the continuous iOS corner", () => {
    const square: string[] = [];
    for (const f of COMPONENTS) {
      for (const m of f.source.matchAll(
        /\{[^{}]*borderRadius: radius\.(?:card|group|control)[^{}]*\}/g,
      )) {
        if (!m[0].includes('borderCurve: "continuous"')) {
          square.push(`${f.name}: ${m[0].replace(/\s+/g, " ").slice(0, 80)}`);
        }
      }
    }
    expect(square).toEqual([]);
    // Non-vacuity: the shared containers are among what was checked.
    const checked = COMPONENTS.filter((f) =>
      /borderRadius: radius\.(?:card|group|control)/.test(f.source),
    ).map((f) => f.name);
    expect(checked).toEqual(
      expect.arrayContaining(["src/components/ListRow.tsx", "src/components/Themed.tsx"]),
    );
  });

  it("no emoji or pictograph stands in for an icon, in the catalogues or the code", () => {
    const pictograph = /\p{Extended_Pictographic}/u;
    const catalogued = [...Object.entries(tr), ...Object.entries(en)]
      .filter(([, text]) => pictograph.test(text))
      .map(([key]) => key);
    expect(catalogued).toEqual([]);
    expect(offenders(pictograph)).toEqual([]);
    // Near miss: the scan is not blind to one.
    expect(pictograph.test("Hazırsınız 🎉")).toBe(true);
    expect(pictograph.test("İç Hastalıkları › Kardiyoloji")).toBe(false);
  });

  it("no image asset is drawn as decoration: every glyph is a registry symbol", () => {
    expect(offenders(/require\(\s*["'][^"']+\.(?:png|jpe?g|svg|gif|webp)["']\s*\)/)).toEqual([]);
    expect(offenders(/<Image\b/)).toEqual([]);
    expect(importersOf("expo-symbols")).toEqual(["src/components/Icon.tsx"]);
  });
});

describe("the platform face, not a bundled one", () => {
  it("the root layout loads no font, so no line waits for one or flashes a fallback", () => {
    const layout = file("src/app/_layout.tsx");
    expect(layout).not.toMatch(/@expo-google-fonts|\buseFonts\b/);
    expect(offenders(/@expo-google-fonts/)).toEqual([]);
  });

  it("no module names a bundled face", () => {
    expect(offenders(/\b(?:Newsreader|Inter|Fraunces)_\d{3}/)).toEqual([]);
  });

  it("AppText sets the role's weight and the platform family; the title and numeral are rounded", () => {
    const themed = file("src/components/Themed.tsx");
    expect(themed).toContain("roleWeight[role]");
    expect(themed).toMatch(/Platform\.select\(fonts\.rounded\)/);
    expect(themed).toContain("ROUNDED_ROLES.includes(role)");
  });
});

describe("friendly empty states, no illustration (owner direction, INT-422)", () => {
  it("an empty list shows a tinted registry symbol, the existing line and its next step", () => {
    const empty = file("src/components/EmptyState.tsx");
    expect(empty).toContain("<Icon name={icon}");
    expect(empty).toContain("tintColor={theme.primary}");
    // The glyph is decoration; the line is what a screen reader reads.
    expect(empty).toContain('importantForAccessibility="no-hide-descendants"');
    expect(empty).not.toMatch(/\bt\("/);
    for (const name of ["src/app/(tabs)/today.tsx", "src/app/(tabs)/visits/index.tsx"]) {
      expect(file(name), name).toContain("<EmptyState");
    }
  });
});

describe("materials only on the functional layer (spec §0 rule 1)", () => {
  it("glass and blur are drawn by the tab rail and the bottom bar alone", () => {
    const glass = [
      ...new Set([...importersOf("expo-blur"), ...offenders(/<GlassView\b|<BlurView\b/)]),
    ].sort();
    expect(glass).toEqual(["src/components/FloatingTabBar.tsx", "src/components/GlassBar.tsx"]);
  });

  it("each of them has a solid answer for Reduce Transparency", () => {
    for (const name of ["src/components/FloatingTabBar.tsx", "src/components/GlassBar.tsx"]) {
      const host = file(name);
      expect(host, name).toContain("useGlassMode()");
      expect(host, name).toMatch(/mode === "solid"/);
      expect(host, name).toContain("theme.surface");
    }
  });
});

describe("Increase Contrast reaches every surface", () => {
  it("useTheme resolves the palette from the scheme AND the contrast request", () => {
    const themed = file("src/components/Themed.tsx");
    const useTheme = /export function useTheme\(\): ThemeColors \{([\s\S]*?)\n\}/.exec(themed);
    expect(useTheme).not.toBeNull();
    expect(useTheme![1]).toContain("useScheme()");
    expect(useTheme![1]).toContain("useIncreasedContrast()");
    expect(useTheme![1]).toContain("colorsFor(");
  });

  it("no component reads a palette object directly, around the contrast answer", () => {
    const direct = TREE.filter(
      (f) =>
        f.name !== "src/components/Themed.tsx" &&
        f.name !== "src/lib/theme.ts" &&
        /\b(?:palette|highContrastPalette|colorsFor)\b/.test(f.source),
    ).map((f) => f.name);
    expect(direct).toEqual([]);
  });

  it("only the native adapter asks the OS, and it is reached lazily", () => {
    const askers = offenders(
      /\bisDarkerSystemColorsEnabled\b|\bisHighTextContrastEnabled\b|["']darkerSystemColorsChanged["']|["']highTextContrastChanged["']/,
    );
    expect(askers).toEqual(["src/lib/a11y/native/increaseContrastSource.ts"]);
    const prefs = file("src/lib/a11y/prefs.ts");
    expect(prefs).toMatch(/import\(\s*["']@\/lib\/a11y\/native\/increaseContrastSource["']\s*\)/);
    expect(importersOf("@/lib/a11y/native/increaseContrastSource")).toEqual([
      "src/lib/a11y/prefs.ts",
    ]);
  });
});

describe("the shared controls carry the native register", () => {
  const themed = () => file("src/components/Themed.tsx");

  it("the focal CTA is the tinted, filled button (borderedProminent), not a neutral pill", () => {
    const button = /export function PrimaryButton\([\s\S]*?\n\}/.exec(themed());
    expect(button).not.toBeNull();
    expect(button![0]).toContain("theme.cta");
    expect(button![0]).toContain('color="onCta"');
    expect(themed()).toMatch(/primaryButton: \{[^}]*borderRadius: radius\.control/);
  });

  it("the secondary action is the grey button with a tinted label", () => {
    const button = /export function SecondaryButton\([\s\S]*?\n\}/.exec(themed());
    expect(button).not.toBeNull();
    expect(button![0]).toContain("theme.surfaceRaised");
    expect(button![0]).toContain('color="primary"');
  });

  it("a section header is a quiet footnote: no dot, no tracking, no case transform", () => {
    const kicker = file("src/components/Kicker.tsx");
    expect(kicker).toContain('role="caption"');
    expect(kicker).not.toMatch(/\bdot\b|letterSpacing|textTransform/);
  });

  it("list rows draw their glyph in the tint, bare, as UIKit list cells do", () => {
    const row = file("src/components/ListRow.tsx");
    expect(row).toMatch(/<Icon name=\{icon\}[^>]*tintColor=\{theme\.primary\}/);
    expect(row).not.toContain("iconWell");
  });

  it("the selected segment is a raised thumb, not an inverted slab", () => {
    const segmented = file("src/components/Segmented.tsx");
    expect(segmented).toContain("theme.thumb");
    expect(segmented).not.toContain("theme.cta");
  });
});

/* ------------------------------------------------------------------ */
/* Dynamic Type, up to the accessibility sizes                          */
/* ------------------------------------------------------------------ */

/**
 * The multipliers React Native itself applies for each iOS content size
 * category, read from the framework source rather than copied, so a change
 * upstream moves this test with it.
 */
const MULTIPLIERS: ReadonlyMap<string, number> = new Map(
  [
    ...readFileSync(
      join(MOBILE, "node_modules/react-native/React/CoreModules/RCTAccessibilityManager.mm"),
      "utf8",
    ).matchAll(/UIContentSizeCategory(\w+)\s*:\s*@([\d.]+)/g),
  ].map((m) => [m[1], Number(m[2])]),
);

/** The narrowest iPhone the app supports (SE, 2nd and 3rd generation). */
const IPHONE_SE = 375;

/**
 * The question's measure: the intake scroll content pads by the screen
 * margin on both sides (asserted below).
 */
const QUESTION_MEASURE = IPHONE_SE - 2 * spacing.screen;

/**
 * Measured in Inter SemiBold, the widest of the faces on hand, as an upper
 * bound for SF Pro Semibold. SF Pro is not redistributable, so it cannot be
 * read in CI; on the build Mac its advances measured 0.85 to 0.91 of Inter's
 * across all 1066 Turkish catalogue strings (docs/evidence/INT-422.md), so a
 * word that fits in Inter fits in SF. Kerning is ignored, which only ever
 * over-counts.
 */
const questionFace = readFontMetrics(
  join(MOBILE, "node_modules/@expo-google-fonts/inter/600SemiBold/Inter_600SemiBold.ttf"),
);

/** Every string the intake renders in the question role, in both catalogues. */
const QUESTION_KEYS = [
  ...new Set([
    ...allQuestions.map((q) => q.titleKey),
    "intake.mode.q" as const,
    "intake.privacy.q" as const,
  ]),
];

const QUESTION_WORDS = [
  ...new Set(
    QUESTION_KEYS.flatMap((key) => [tr[key], en[key]]).flatMap((text) => text.split(/\s+/)),
  ),
].filter((word) => word.length > 0);

/**
 * Words that would break inside themselves at `size` points. A hyphen is a
 * line-break opportunity (UAX #14), so "over-the-counter" is measured as the
 * pieces CoreText may set on separate lines.
 */
function breaking(size: number): string[] {
  return QUESTION_WORDS.flatMap((word) => word.split(/(?<=-)/))
    .filter((word) => questionFace.advance(word, size) > QUESTION_MEASURE)
    .map((word) => `${word} ${questionFace.advance(word, size).toFixed(1)} pt`);
}

describe("Dynamic Type up to AX5 never truncates a question", () => {
  it("reads React Native's own table, accessibility sizes included", () => {
    expect(MULTIPLIERS.size).toBe(12);
    expect(MULTIPLIERS.get("Large")).toBe(1);
    expect(MULTIPLIERS.get("AccessibilityMedium")).toBeGreaterThan(1.5);
    expect(MULTIPLIERS.get("AccessibilityExtraExtraExtraLarge")).toBeGreaterThan(3);
  });

  it("finds the questions it is supposed to measure", () => {
    expect(QUESTION_KEYS.length).toBeGreaterThan(60);
    expect(QUESTION_WORDS.length).toBeGreaterThan(200);
    expect(QUESTION_WORDS).toContain("görüşmenizden");
  });

  it("every question renders in the question role, at every site that asks one", () => {
    const intake = file("src/app/(tabs)/visits/[visitId]/intake.tsx");
    expect(intake).toMatch(/<AppText role="question" heading>\s*\{t\(question\.titleKey\)\}/);
    expect(intake).toMatch(/<AppText role="question" heading>\s*\{t\("intake\.mode\.q"\)\}/);
    expect(intake).toMatch(/<AppText role="question" heading>\s*\{t\("intake\.privacy\.q"\)\}/);
    const instrument = file("src/components/InstrumentStep.tsx");
    expect(instrument).toMatch(/<AppText role="question" heading>\s*\{item\.textTr\}/);
  });

  it("nothing on the question's path can cut a line short", () => {
    // AppText exposes no line limit, and neither the text primitive nor the
    // question sites ask for one or shrink the face to fit.
    const clip =
      /\bnumberOfLines\b|\bellipsizeMode\b|\badjustsFontSizeToFit\b|\bminimumFontScale\b/;
    for (const name of [
      "src/components/Themed.tsx",
      "src/app/(tabs)/visits/[visitId]/intake.tsx",
      "src/components/InstrumentStep.tsx",
    ]) {
      expect(file(name), name).not.toMatch(clip);
    }
    // The question scrolls with its step; the measure above is its box.
    const intake = file("src/app/(tabs)/visits/[visitId]/intake.tsx");
    expect(intake).toMatch(/content: \{ gap: spacing\.md, padding: spacing\.screen/);
    expect(intake).toContain("<ScrollView");
  });

  it.each([...MULTIPLIERS])(
    "%s (×%s): every question word keeps its line on a 375 pt iPhone",
    (_category, multiplier) => {
      const size = scaledSize("question", multiplier);
      // Non-vacuity: a missing role would measure at NaN, and nothing is
      // wider than NaN points.
      expect(size).toBeGreaterThanOrEqual(Math.round(typeScale.question * 0.8));
      expect(breaking(size)).toEqual([]);
    },
  );

  it("near miss: at the Large Title size the same words break at the largest steps", () => {
    // The role is a rung below the Large Title for exactly this reason.
    expect(typeScale.hero).toBeGreaterThan(typeScale.question);
    expect(breaking(scaledSize("hero", 2.0)).length).toBeGreaterThan(0);
  });
});

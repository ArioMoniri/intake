/**
 * INT-433: the question screen as source facts (docs/design/question-screen.md).
 *
 * - Progress is one native control, announced as a single progressbar with a
 *   value. The dot row is gone. Since INT-492 (owner, 16 Oct 2026) it draws
 *   as a solid segmented capsule with the "Soru N / M" count inside it.
 * - The numerals are display-only: the progress module is reachable from the
 *   typed screen alone, never from the spoken lane (invariant 22).
 * - The answer field is filled, with a focus ring and no resting outline.
 * - Chips are filled capsules; the selected one is tinted and carries a check.
 * - The chrome is Liquid Glass: the bottom bar holds "Devam edin" and the nav
 *   bar draws the same material, both with a solid answer for Reduce
 *   Transparency. The content stays on solid fills.
 * - The hierarchy follows the HIG: the question in Title 2, the hint in
 *   Footnote secondary.
 *
 * React Native has no DOM here, so the tree proves the wiring and
 * lib/intake/questionScreen.test.ts proves the rules.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";

const MOBILE = join(__dirname, "..");

/** Code only: comments explain what a file avoids, and a guard reads what it does. */
const code = (source: string): string =>
  source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");

const source = (name: string): string => code(readFileSync(join(MOBILE, name), "utf8"));

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

/** Every shipped script under src/, tests excluded, as `src/...` names. */
const TREE = walk(join(MOBILE, "src"))
  .filter((p) => /\.tsx?$/.test(p) && !/\.test\.tsx?$/.test(p))
  .map((p) => ({
    name: relative(MOBILE, p).split(sep).join("/"),
    source: code(readFileSync(p, "utf8")),
  }));

const importersOf = (module: string): string[] =>
  TREE.filter((f) =>
    new RegExp(`from\\s+["']${module.replace(/[/@]/g, "\\$&")}["']`).test(f.source),
  ).map((f) => f.name);

const INTAKE = "src/app/(tabs)/visits/[visitId]/intake.tsx";
const PROGRESS = "src/components/QuestionProgress.tsx";
const BARS = "src/components/GlassBar.tsx";

describe("progress is one native control, not a row of dots", () => {
  it("no dot-row progress remains anywhere in the app", () => {
    const dots = TREE.filter((f) => /\bprogressDot\b|\bprogressRail\b/.test(f.source)).map(
      (f) => f.name,
    );
    expect(dots).toEqual([]);
    // The near miss: the old rail was a View per applicable question.
    expect(source(INTAKE)).not.toMatch(/applicable\.map\(\s*\(item, i\)\s*=>\s*\(\s*<View/);
  });

  it("the typed screen renders the progress control from the pack's position", () => {
    const intake = source(INTAKE);
    expect(intake).toContain("<QuestionProgress");
    expect(intake).toMatch(/questionPosition\(applicable, question\.id, flowCanGrow\)/);
    expect(intake).toMatch(/<QuestionProgress\s+position=[\s\S]*?flow=\{applicable\}/);
  });

  it("is announced as one progressbar carrying a value", () => {
    const bar = source(PROGRESS);
    expect(bar).toContain('accessibilityRole="progressbar"');
    expect(bar).toMatch(/accessibilityValue=\{\{[^}]*min:[^}]*max:[^}]*now:[^}]*text:/s);
    expect(bar).toContain('accessibilityLabel={t("intake.progress.name")}');
    // One element: the bar and its line are grouped, not read twice.
    expect(bar).toMatch(/<View\s+accessible\b/);
  });

  it("the segments sit in a capsule, the count uses tabular figures", () => {
    const bar = source(PROGRESS);
    expect(bar).toMatch(/capsule:\s*\{[^}]*borderRadius:\s*radius\.chip/s);
    expect(bar).toMatch(/segment:\s*\{[^}]*height:\s*SEGMENT[^}]*borderRadius/s);
    expect(bar).toContain('fontVariant: ["tabular-nums"]');
    // The line wraps rather than leaving the screen: nothing clips it.
    expect(bar).not.toMatch(/numberOfLines|ellipsizeMode|adjustsFontSizeToFit/);
  });

  it("the growth line stays outside the progressbar, so the reader hears it too", () => {
    const bar = source(PROGRESS);
    const progressbar = bar.indexOf('accessibilityRole="progressbar"');
    const grows = bar.indexOf('t("intake.progress.grows")');
    expect(progressbar).toBeGreaterThan(-1);
    expect(grows).toBeGreaterThan(-1);
    // The grouped element closes before the growth line opens.
    const closing = bar.indexOf("</View>", bar.indexOf("<CapsuleBody"));
    expect(grows).toBeGreaterThan(closing);
  });
});

describe("the numerals are display-only (invariant 22)", () => {
  it("the progress module is reached from the typed screen alone", () => {
    expect(importersOf("@/lib/intake/questionScreen").sort()).toEqual([INTAKE, PROGRESS].sort());
    expect(importersOf("@/components/QuestionProgress")).toEqual([INTAKE]);
  });

  it("nothing on the spoken lane imports it", () => {
    const spoken = TREE.filter(
      (f) =>
        f.name === "src/components/DialogueIntake.tsx" ||
        f.name.startsWith("src/lib/dialogue/") ||
        f.name.startsWith("src/lib/livekit/"),
    );
    expect(spoken.length).toBeGreaterThan(3);
    for (const f of spoken) {
      expect(f.source, f.name).not.toMatch(/questionScreen|QuestionProgress|intake\.progress\./);
    }
  });
});

describe("the answer field is filled, with a focus ring", () => {
  it("no field on the screen draws a resting outline", () => {
    const intake = source(INTAKE);
    const field = /\n\s{2}textField:\s*\{[\s\S]*?\n\s{2}\}/.exec(intake);
    expect(field, "the textField style").not.toBeNull();
    expect(field![0]).not.toMatch(/borderWidth:\s*1\b/);
  });

  it("both fields take their chrome from the focus-aware rule", () => {
    const intake = source(INTAKE);
    const fields = [...intake.matchAll(/<TextInput\b[\s\S]*?\/>/g)].map((m) => m[0]);
    expect(fields.length).toBe(2);
    for (const field of fields) {
      expect(field).toContain("filledFieldChrome(theme");
      expect(field).toContain("onFocus=");
      expect(field).toContain("onBlur=");
    }
  });
});

describe("chips are filled capsules with a selected state", () => {
  const intake = source(INTAKE);
  const chip = /\n\s{2}chip:\s*\{[\s\S]*?\n\s{2}\}/.exec(intake)?.[0] ?? "";

  it("the chip is a capsule with no outline", () => {
    expect(chip).toContain("borderRadius: radius.chip");
    expect(chip).not.toContain("borderWidth");
    expect(chip).toContain("minHeight: MIN_TAP");
  });

  it("a selected chip says so to the reader and draws a check, not only a tint", () => {
    expect(intake).toMatch(
      /accessibilityRole="checkbox"[\s\S]{0,200}accessibilityState=\{\{ checked: on \}\}/,
    );
    expect(intake).toMatch(/const look = chipChrome\(theme, on\)/);
    // INT-492: the check sits in a slot reserved in both states.
    expect(intake).toMatch(/<ChipSlot selected=\{on\} \/>/);
    expect(intake).toContain("backgroundColor: look.backgroundColor");
  });
});

describe("Liquid Glass on the chrome, solid fills under the content", () => {
  it("Devam edin rides the bottom glass bar", () => {
    const intake = source(INTAKE);
    expect(intake).toMatch(/<GlassBar onHeight=\{setBarHeight\}>\s*<PrimaryButton/);
  });

  it("the nav bar is the one glass-nav helper over the scrolling content", () => {
    const intake = source(INTAKE);
    // INT-451 follow-up: the question takes the same helper as the visit's
    // other pushed screens, so iOS 26 gets the platform bar and its
    // scroll-edge effect rather than a full-bar GlassView.
    expect(intake).toMatch(/withGlassNav\(headerOptions\(""\), glass\)/);
    expect(intake).not.toContain("GlassNavBackground");
    // Content clears the bar by the header's own height, never a constant.
    expect(intake).toContain("useHeaderHeight()");
  });

  it("the nav background asks the one glass policy and has a solid answer", () => {
    const bars = source(BARS);
    const nav = bars.slice(bars.indexOf("export function GlassNavBackground"));
    expect(nav).toContain("useGlassMode()");
    expect(nav).toMatch(/mode === "solid"[\s\S]*?backgroundColor: theme\.background/);
    expect(nav).not.toMatch(/<GlassView\b/);
  });

  it("a warning banner keeps the solid bar, so nothing it says sits under glass", () => {
    const intake = source(INTAKE);
    expect(intake).toMatch(/const glassNav =[\s\S]*?!bannerShown/);
  });

  it("the screen itself draws no material: content sits on solid fills", () => {
    expect(source(INTAKE)).not.toMatch(/<GlassView\b|<BlurView\b|expo-blur|expo-glass-effect/);
  });
});

describe("the hierarchy follows the HIG type ramp", () => {
  it("the question is Title 2 and the hint is Footnote secondary", () => {
    const intake = source(INTAKE);
    expect(intake).toMatch(/<AppText role="question" heading>\s*\{t\(question\.titleKey\)\}/);
    expect(intake).toMatch(
      /<AppText role="caption" color="inkSoft">\s*\{t\("intake\.open\.hint"\)\}/,
    );
    expect(intake).toMatch(/<AppText role="caption" color="inkSoft">\s*\{t\(question\.hintKey\)\}/);
  });

  it("RED surfaces are untouched: the screen paints no emergency token", () => {
    expect(source(INTAKE)).not.toMatch(/theme\.emergency/);
  });
});

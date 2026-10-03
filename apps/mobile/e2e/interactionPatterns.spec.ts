/**
 * INT-451: interaction patterns from the owner's library list and Mobbin,
 * adapted within ADR-033 (docs/design/interaction-patterns.md).
 *
 * Two patterns ship, and both are state, not motion:
 *
 * - **Row press highlight.** A grouped-list row and a switch row show a press
 *   by stepping their fill to `rowPressFill`, as a UIKit cell and a Material 3
 *   list item do, instead of dimming the words. lib/a11y/rowPress.test.ts holds
 *   the contrast; this spec holds the wiring.
 * - **Glass navigation bar on the visit's pushed screens.** INT-433 put the
 *   typed question under a glass nav bar. Visit detail, the share centre, the
 *   review and the new-visit form now take the same material through one
 *   helper, `withGlassNav`, and clear the bar by the header's own height.
 *
 * Neither adds a duration, a curve, a spring, a scale or a translate, and
 * neither reaches RED, legal text or question text. Everything that would
 * move is in the ADR-037 amendment proposal and does not ship.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const MOBILE = join(__dirname, "..");

/** Code only: comments explain what a file avoids, and a guard reads what it does. */
const code = (text: string): string =>
  text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");

const source = (name: string): string => code(readFileSync(join(MOBILE, name), "utf8"));

const ROWS = ["src/components/ListRow.tsx", "src/components/SwitchRow.tsx"] as const;

const BARS = "src/components/GlassBar.tsx";

/** The visit's pushed screens that now ride the glass nav bar. */
const GLASS_NAV_SCREENS = [
  "src/app/(tabs)/visits/[visitId]/index.tsx",
  "src/app/(tabs)/visits/[visitId]/shares.tsx",
  "src/app/(tabs)/visits/[visitId]/review.tsx",
  "src/app/(tabs)/visits/new.tsx",
] as const;

/**
 * Screens that keep the solid bar. The Doctor Link screen renders a bearer
 * credential, and the auth screens are gates (ADR-033 §4): nothing there
 * scrolls under a material.
 */
const SOLID_NAV_SCREENS = [
  "src/app/(tabs)/visits/[visitId]/issue-link.tsx",
  "src/app/(auth)/phone.tsx",
  "src/app/(auth)/otp.tsx",
] as const;

/** The body of the first `({ pressed }) =>` style callback in `text`. */
function pressedCallback(text: string): string {
  const start = text.search(/\(\s*\{\s*pressed\s*\}\s*\)\s*=>/);
  expect(start, "a Pressable style callback").toBeGreaterThanOrEqual(0);
  const open = text.indexOf("[", start);
  let depth = 0;
  for (let i = open; i < text.length; i += 1) {
    if (text[i] === "[") depth += 1;
    if (text[i] === "]") depth -= 1;
    if (depth === 0) return text.slice(open, i + 1);
  }
  return text.slice(open);
}

describe("§3.1 row press: the fill highlights, the words keep their ink", () => {
  it.each(ROWS)("%s steps its fill to rowPressFill while pressed", (name) => {
    const callback = pressedCallback(source(name));
    expect(callback).toMatch(/pressed \? \{ backgroundColor: theme\[rowPressFill\] \} : null/);
  });

  it.each(ROWS)("%s no longer dims its text on a press", (name) => {
    const callback = pressedCallback(source(name));
    expect(callback).not.toMatch(/\bopacity\b/);
  });

  it("the near-miss shape is caught: a dimming row fails the guard", () => {
    const dimming =
      "style={({ pressed }) => [styles.row, { opacity: pressed ? motion.press.rowOpacity : 1 }]}";
    expect(pressedCallback(dimming)).toMatch(/\bopacity\b/);
  });

  it("the highlight is a token read, never a colour literal", () => {
    for (const name of ROWS) {
      expect(pressedCallback(source(name))).not.toMatch(/#[0-9A-Fa-f]{3,8}\b|rgba?\(/);
    }
  });
});

describe("§3.2 the glass nav bar: one helper, the visit's pushed screens", () => {
  it("withGlassNav lives in the glass host and draws GlassNavBackground", () => {
    const bars = source(BARS);
    const helper = bars.slice(bars.indexOf("export function withGlassNav"));
    expect(helper).toContain("headerTransparent: true");
    expect(helper).toContain('headerStyle: { backgroundColor: "transparent" }');
    expect(helper).toContain("headerBackground: () => <GlassNavBackground />");
  });

  it.each(GLASS_NAV_SCREENS)("%s rides the glass nav bar", (name) => {
    const screen = source(name);
    expect(screen).toMatch(/options=\{withGlassNav\(headerOptions\(/);
  });

  it.each(GLASS_NAV_SCREENS)("%s clears the bar by the header's own height", (name) => {
    const screen = source(name);
    expect(screen).toContain("useHeaderHeight()");
    expect(screen).toMatch(/paddingTop: headerHeight/);
  });

  it.each(SOLID_NAV_SCREENS)("%s keeps the solid bar", (name) => {
    const screen = source(name);
    expect(screen).not.toMatch(/withGlassNav|GlassNavBackground|headerTransparent/);
  });

  it("a screen's empty state keeps the solid bar: nothing to scroll under glass", () => {
    const review = source("src/app/(tabs)/visits/[visitId]/review.tsx");
    const empty = review.slice(
      review.indexOf('t("review.empty")') - 300,
      review.indexOf('t("review.empty")'),
    );
    expect(empty).toContain('options={headerOptions("")}');
  });
});

describe("INT-451 adds no motion and touches no RED surface", () => {
  const touched = [...ROWS, BARS, ...GLASS_NAV_SCREENS];

  it.each(touched)("%s carries no spring, scale, translate or timing", (name) => {
    const text = source(name);
    expect(text).not.toMatch(/\bwithSpring\b|\bwithTiming\b|\bwithDecay\b|\bAnimated\.\w+/);
    expect(text).not.toMatch(/\btransform\s*:|\bscale\s*:|\btranslate[XY]\s*:/);
    expect(text).not.toMatch(/\bisInteractive\b/);
  });

  it.each(touched)("%s paints no emergency token", (name) => {
    expect(source(name)).not.toMatch(/\bemergency(Soft)?\b/);
  });
});

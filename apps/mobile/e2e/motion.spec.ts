/**
 * INT-341 (MOTION-12; docs/design/motion/motion-verification.md §3 S-9,
 * §4 MOTION-12) — press feedback comes from one token set.
 *
 * A Pressable shows that it is pressed, or that it cannot be pressed, by an
 * instant opacity step. Those steps are `motion.press` in src/lib/theme.ts;
 * no component carries its own number, so a pressed row and a pressed button
 * cannot drift apart again (they were 0.6, 0.7 and 0.85 for the same event,
 * and a disabled control was 0.4 in one place and 0.5 in another).
 *
 * The press-retention area stays the platform's own. The one value ever
 * proposed (16, the rejected P16) is SMALLER than React Native's default of
 * 20/20/20/30, so it would cancel more presses under a tremor — the opposite
 * of what it was for.
 *
 * React Native has no DOM here, so these are source guards. Each detector is
 * first run on samples that prove it is not vacuous.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";

const MOBILE = join(__dirname, "..");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

interface Source {
  readonly name: string;
  readonly source: string;
}

/**
 * Every script the app, its tests and its config plugins are made of, except
 * this guard: its test titles are the spec's, and they name what they forbid.
 */
const TREE: readonly Source[] = ["src", "e2e", "plugins"]
  .flatMap((dir) => walk(join(MOBILE, dir)))
  .concat([join(MOBILE, "app.config.ts")])
  .filter((path) => /\.(ts|tsx|js|jsx|mjs|cjs)$/.test(path))
  .map((path) => ({
    name: relative(MOBILE, path).split(sep).join("/"),
    source: readFileSync(path, "utf8"),
  }))
  .filter((f) => f.name !== "e2e/motion.spec.ts")
  .sort((a, b) => a.name.localeCompare(b.name));

/** The app itself: what ships, without its tests. */
const APP_SOURCE = TREE.filter(
  (f) => f.name.startsWith("src/") && !/\.(test|spec)\.tsx?$/.test(f.name),
);

// ---------------------------------------------------------------------------
// MOTION-12 — press feedback
// ---------------------------------------------------------------------------

/** The token module: the one place a press opacity is a number. */
const TOKENS = "src/lib/theme.ts";

/**
 * Opacities that are not state feedback: a fixed property of a static shape,
 * never switched by a press or a disabled flag. Keyed by file and value, not
 * line. This list may only shrink.
 */
const STATIC_OPACITY: readonly { readonly name: string; readonly value: string }[] = [
  // The hairline divider's resting tone (`styles.hairline`).
  { name: "src/components/Themed.tsx", value: "0.9" },
];

/** A fractional opacity (`0.6`, `.4`). The rest states 0 and 1 are not feedback. */
const FRACTION = /(?<![\w.])0?\.\d+/;

/** An opacity written as a key, a prop, or `TouchableOpacity`'s own prop. */
const OPACITY_KEY = /(?<![\w$.])(?:opacity|activeOpacity)\s*[:=]\s*\{?/g;

/** A Pressable style callback: `({ pressed }) =>`, whatever else it destructures. */
const PRESSED_CALLBACK = /\(\s*\{[^}]*\bpressed\b[^}]*\}\s*\)\s*=>/g;

/** A value that switches on state rather than being a constant. */
const CONDITIONAL = /\?|&&|\|\|/;

/** A read of the press tokens. */
const FROM_TOKEN = /\bmotion\.press\.(?:opacity|rowOpacity|disabledOpacity)\b/;

interface OpacitySite {
  readonly name: string;
  readonly line: number;
  readonly value: string;
}

function lineOf(source: string, index: number): number {
  return source.slice(0, index).split("\n").length;
}

/** From `start`, where the expression ends: `,` or `;` at depth 0, or an unmatched closer. */
function expressionEnd(source: string, start: number): number {
  let depth = 0;
  for (let i = start; i < source.length; i += 1) {
    const ch = source[i];
    if (ch === "(" || ch === "[" || ch === "{") {
      depth += 1;
    } else if (ch === ")" || ch === "]" || ch === "}") {
      if (depth === 0) return i;
      depth -= 1;
    } else if (depth === 0 && (ch === "," || ch === ";")) {
      return i;
    }
  }
  return source.length;
}

/** Every opacity value written in `f` between `from` and `to`, with its line. */
function opacityValues(f: Source, from = 0, to = f.source.length): OpacitySite[] {
  const span = f.source.slice(0, to);
  const key = new RegExp(OPACITY_KEY.source, "g");
  key.lastIndex = from;
  const sites: OpacitySite[] = [];
  for (let m = key.exec(span); m !== null; m = key.exec(span)) {
    const start = m.index + m[0].length;
    const value = span.slice(start, expressionEnd(span, start)).replace(/\s+/g, " ").trim();
    sites.push({ name: f.name, line: lineOf(f.source, m.index), value });
  }
  return sites;
}

/** Every opacity carrying its own fractional number, outside the static list. */
function opacityLiterals(f: Source): OpacitySite[] {
  return opacityValues(f)
    .filter((site) => FRACTION.test(site.value))
    .filter((site) => !STATIC_OPACITY.some((s) => s.name === site.name && s.value === site.value));
}

/** Every state-switched opacity inside a Pressable style callback. */
function pressFeedback(f: Source): OpacitySite[] {
  const callbacks = new RegExp(PRESSED_CALLBACK.source, "g");
  return [...f.source.matchAll(callbacks)].flatMap((m) => {
    const body = m.index + m[0].length;
    return opacityValues(f, body, expressionEnd(f.source, body)).filter((site) =>
      CONDITIONAL.test(site.value),
    );
  });
}

function where(site: OpacitySite): string {
  return `${site.name}:${site.line} ${site.value}`;
}

function sample(source: string): Source {
  return { name: "sample.tsx", source };
}

const RETENTION = ["pressRetention", "Offset"].join("");

/** Any explicit retention area: the scope sets none, so every one is a narrowing risk. */
function setsRetention(source: string): boolean {
  return new RegExp(`\\b${RETENTION}\\b`).test(source);
}

describe("MOTION-12 — press feedback comes from motion.press", () => {
  it("every Pressable takes its pressed and disabled opacity from motion.press", () => {
    // Non-vacuity: each shape a literal could hide in is caught…
    for (const shape of [
      "style={({ pressed }) => [s.row, { opacity: pressed ? 0.6 : 1 }]}",
      "opacity: disabled ? 0.5 : pressed ? 0.85 : 1,",
      "opacity:\n  draft.length === 0\n    ? 0.4\n    : 1,",
      "style={[s.row, pressed && { opacity: .7 }]}",
      "<TouchableOpacity activeOpacity={0.7} />",
    ]) {
      expect(opacityLiterals(sample(shape)), shape).toHaveLength(1);
    }
    // …a token read is not…
    expect(opacityLiterals(sample("opacity: pressed ? motion.press.rowOpacity : 1,"))).toEqual([]);
    // …and a press callback cannot route around the tokens through a name.
    const local = "style={({ pressed }) => [{ opacity: pressed ? dim : 1 }]}";
    expect(pressFeedback(sample(local)).map((s) => s.value)).toEqual(["pressed ? dim : 1"]);
    expect(FROM_TOKEN.test("pressed ? dim : 1")).toBe(false);

    // No press or disabled number anywhere in the app but the token module.
    const literals = APP_SOURCE.filter((f) => f.name !== TOKENS).flatMap(opacityLiterals);
    expect(literals.map(where)).toEqual([]);

    // Every Pressable that dims on a press, or when disabled, reads the tokens.
    const sites = APP_SOURCE.flatMap(pressFeedback);
    expect(sites.filter((site) => !FROM_TOKEN.test(site.value)).map(where)).toEqual([]);

    // The scan found the sites it is about: every press-feedback component on
    // main, and the three disabled controls (both buttons and the composer's
    // send, whose 0.4 was normalised to the token's 0.5).
    expect(sites.length).toBeGreaterThanOrEqual(10);
    expect([...new Set(sites.map((s) => s.name))]).toEqual(
      expect.arrayContaining([
        "src/components/DialogueIntake.tsx",
        "src/components/ListRow.tsx",
        "src/components/SectionPanel.tsx",
        "src/components/Segmented.tsx",
        "src/components/SwitchRow.tsx",
        "src/components/Themed.tsx",
      ]),
    );
    const disabled = sites
      .filter((s) => /\bmotion\.press\.disabledOpacity\b/.test(s.value))
      .map((s) => s.name);
    expect(disabled).toEqual([
      "src/components/DialogueIntake.tsx",
      "src/components/Themed.tsx",
      "src/components/Themed.tsx",
    ]);
  });

  it("no Pressable narrows the platform's press-retention default", () => {
    for (const shape of [
      `<Pressable ${RETENTION}={16} />`,
      `const retention = { ${RETENTION}: { top: 16, left: 16, right: 16, bottom: 16 } };`,
      `<Pressable {...{ ${RETENTION} }} />`,
    ]) {
      expect(setsRetention(shape), shape).toBe(true);
    }
    // hitSlop widens the touch area; it is not the retention area.
    expect(setsRetention("<Pressable hitSlop={8} />")).toBe(false);

    const offenders = APP_SOURCE.filter((f) => setsRetention(f.source)).map((f) => f.name);
    expect(offenders).toEqual([]);
  });
});

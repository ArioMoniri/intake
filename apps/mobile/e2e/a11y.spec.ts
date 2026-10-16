/**
 * Accessibility acceptance (INT-144) — the automated half.
 *
 * Legal frame: Cumhurbaşkanlığı Genelgesi 2025/10 (RG 32933, 21.06.2025),
 * basis Law 5378, whose deadline for mobile applications of özel hastaneler
 * passed on ~20 June 2026 (HUMAN_BLOCKERS.md HB-L9). The Ministry audits
 * against its own "Kontrol Listesi — A Seviyesi" (31 Başarı Kriteri, 1:1 to
 * WCAG 2.2 Level A); our target is Level AA, which contains that floor.
 * `docs/compliance/accessibility-conformance.md` is the criterion-by-
 * criterion report and states, per criterion, what this file proves and what
 * only a device screen-reader run can.
 *
 * What this file is and is not. React Native has no DOM, so there is no axe
 * to run: the accessibility tree only exists on a device. What CAN be proven
 * without one is that the source declares the properties that tree is built
 * from — every interactive element has a role and a name, every name comes
 * from the tr-first catalog rather than a source literal, every looping
 * animation asks the OS about reduce-motion, every touch target reaches the
 * floor. Those are the assertions below. Everything that needs VoiceOver or
 * TalkBack to actually speak is listed as unverified in the report and in
 * docs/evidence/INT-144.md, never asserted here.
 *
 * The scanner is a small JSX opening-tag reader rather than a set of greps,
 * so an assertion is about one element's props and a failure names the
 * element and its line.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import type { ExpoConfig } from "expo/config";
import { describe, expect, it } from "vitest";

import { resolveAppConfig } from "../app.config";
import { MIN_TAP } from "../src/lib/a11y/target";
import { OTP_LENGTH } from "../src/lib/auth/phone";
import {
  KIOSK_IDLE_WARNING_MS,
  KIOSK_IDLE_WIPE_MS,
  kioskIdleDue,
  kioskIdleReducer,
  kioskIdleStart,
} from "../src/lib/kiosk";
import { CTA_MIN_HEIGHT } from "../src/lib/prefs/appearance";
import { buildEnvelopeBody } from "../src/lib/telemetry/envelope";
import { buildCrashReport, type TelemetryIdentity } from "../src/lib/telemetry/scrub";
import { motion } from "../src/lib/theme";
import { code, literalDurations, loops } from "./motionSource";

const MOBILE = join(__dirname, "..");
const SRC = join(MOBILE, "src");
const APP = join(SRC, "app");
const COMPONENTS = join(SRC, "components");

/* ------------------------------------------------------------------ */
/* A very small JSX reader                                             */
/* ------------------------------------------------------------------ */

interface Opening {
  readonly tag: string;
  /** Everything between the tag name and the closing `>` of the opening. */
  readonly props: string;
  readonly file: string;
  readonly line: number;
}

/** `<Tag` … `>` — brace-, string- and comment-aware so props may hold JS. */
function readOpenings(source: string, file: string, tags: readonly string[]): Opening[] {
  const found: Opening[] = [];
  for (const tag of tags) {
    const start = new RegExp(`<${tag}(?=[\\s/>])`, "g");
    let match = start.exec(source);
    while (match !== null) {
      const from = match.index + tag.length + 1;
      const end = endOfOpening(source, from);
      if (end > from) {
        found.push({
          tag,
          props: source.slice(from, end),
          file,
          line: source.slice(0, match.index).split("\n").length,
        });
      }
      match = start.exec(source);
    }
  }
  return found.sort((a, b) => a.line - b.line);
}

/** Index of the `>` that closes the opening tag beginning at `from`. */
function endOfOpening(source: string, from: number): number {
  let depth = 0;
  let i = from;
  while (i < source.length) {
    const c = source[i];
    if (c === "{") {
      depth += 1;
    } else if (c === "}") {
      depth -= 1;
    } else if (c === '"' || c === "'" || c === "`") {
      i = endOfString(source, i);
    } else if (c === "/" && source[i + 1] === "/") {
      i = source.indexOf("\n", i);
      if (i < 0) {
        return -1;
      }
    } else if (c === "/" && source[i + 1] === "*") {
      const close = source.indexOf("*/", i + 2);
      if (close < 0) {
        return -1;
      }
      i = close + 1;
    } else if (c === ">" && depth === 0) {
      return i;
    }
    i += 1;
  }
  return -1;
}

/** Index of the quote that closes the string opened at `open`. */
function endOfString(source: string, open: number): number {
  const quote = source[open];
  let i = open + 1;
  while (i < source.length) {
    if (source[i] === "\\") {
      i += 2;
      continue;
    }
    if (source[i] === quote) {
      return i;
    }
    i += 1;
  }
  return source.length;
}

/** The CONTENTS of every string literal in an expression. */
function stringLiterals(expr: string): string[] {
  const out: string[] = [];
  for (let i = 0; i < expr.length; i += 1) {
    const c = expr[i];
    if (c === '"' || c === "'" || c === "`") {
      const close = endOfString(expr, i);
      out.push(expr.slice(i + 1, close));
      i = close;
    }
  }
  return out;
}

function hasProp(props: string, name: string): boolean {
  return new RegExp(`(^|[\\s{])${name}(=|[\\s/>]|$)`).test(props);
}

/** The text of `name={…}` or `name="…"`, or null when the prop is absent. */
function propValue(props: string, name: string): string | null {
  const at = props.search(new RegExp(`(^|[\\s{])${name}=`));
  if (at < 0) {
    return null;
  }
  const eq = props.indexOf("=", at);
  const open = eq + 1;
  if (props[open] === '"' || props[open] === "'") {
    return props.slice(open, endOfString(props, open) + 1);
  }
  if (props[open] !== "{") {
    return null;
  }
  let depth = 0;
  for (let i = open; i < props.length; i += 1) {
    const c = props[i];
    if (c === '"' || c === "'" || c === "`") {
      i = endOfString(props, i);
      continue;
    }
    if (c === "{") {
      depth += 1;
    } else if (c === "}") {
      depth -= 1;
      if (depth === 0) {
        return props.slice(open, i + 1);
      }
    }
  }
  return null;
}

/* ------------------------------------------------------------------ */
/* Sources under test                                                  */
/* ------------------------------------------------------------------ */

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

const TSX: { path: string; name: string; source: string }[] = [...walk(APP), ...walk(COMPONENTS)]
  .filter((p) => p.endsWith(".tsx"))
  .map((path) => ({
    path,
    name: relative(MOBILE, path).split(sep).join("/"),
    source: readFileSync(path, "utf8"),
  }))
  .sort((a, b) => a.name.localeCompare(b.name));

const SCREENS = TSX.filter((f) => f.name.startsWith("src/app/"));

/** Every script the app ships, `.ts` included: a loop in src/lib is still a loop. */
const APP_SCRIPTS: { name: string; source: string }[] = walk(SRC)
  .filter((p) => /\.tsx?$/.test(p) && !/\.(test|spec)\.tsx?$/.test(p))
  .map((path) => ({
    name: relative(MOBILE, path).split(sep).join("/"),
    source: readFileSync(path, "utf8"),
  }))
  .sort((a, b) => a.name.localeCompare(b.name));

/**
 * A loop is gated when its file takes the app's reduce-motion answer — the
 * hook from `@/lib/a11y/prefs`, never Reanimated's, which sees only the OS —
 * calls it, and feeds it to `loopingDecorationEnabled`, the one rule that
 * decides whether a decorative loop may run.
 */
function gatedOnAppHook(source: string): boolean {
  const text = code(source);
  const imported =
    /import\s*\{[^}]*\buseReducedMotion\b[^}]*\}\s*from\s*["'](?:@\/lib\/a11y\/prefs|(?:\.\.?\/)+(?:[\w-]+\/)*a11y\/prefs)["']/.test(
      text,
    );
  return (
    imported &&
    /\buseReducedMotion\s*\(\s*\)/.test(text) &&
    /\bloopingDecorationEnabled\s*\(/.test(text)
  );
}

function where(o: Opening): string {
  return `${o.file}:${o.line} <${o.tag}>`;
}

/** Every `<Pressable>` in the app — the only touchable primitive in use. */
const PRESSABLES: Opening[] = TSX.flatMap((f) => readOpenings(f.source, f.name, ["Pressable"]));

const TEXT_INPUTS: Opening[] = TSX.flatMap((f) => readOpenings(f.source, f.name, ["TextInput"]));

const MODALS: Opening[] = TSX.flatMap((f) => readOpenings(f.source, f.name, ["Modal"]));

it("the scanner found the surfaces it is supposed to police", () => {
  // A silent zero here would make every assertion below vacuously true.
  expect(TSX.length).toBeGreaterThan(20);
  expect(PRESSABLES.length).toBeGreaterThan(20);
  expect(TEXT_INPUTS.length).toBeGreaterThan(5);
  expect(MODALS.length).toBeGreaterThan(0);
});

/* ------------------------------------------------------------------ */
/* BK31 · WCAG 2.2 SC 4.1.2 Name, Role, Value                          */
/* ------------------------------------------------------------------ */

describe("BK31 / SC 4.1.2 — every interactive element has a role and a name", () => {
  it("every Pressable declares accessibilityRole", () => {
    const missing = PRESSABLES.filter((o) => !hasProp(o.props, "accessibilityRole")).map(where);
    expect(missing).toEqual([]);
  });

  it("every Pressable declares accessibilityLabel", () => {
    // RN derives a name from Text children, but only when the subtree is
    // merged — and it derives the WRONG one whenever the visible text is a
    // state word ("Paylaşılıyor") that says nothing about what it belongs
    // to. An explicit name is the only one we can hold to a contract.
    const missing = PRESSABLES.filter((o) => !hasProp(o.props, "accessibilityLabel")).map(where);
    expect(missing).toEqual([]);
  });

  it("every TextInput declares accessibilityLabel", () => {
    const missing = TEXT_INPUTS.filter((o) => !hasProp(o.props, "accessibilityLabel")).map(where);
    expect(missing).toEqual([]);
  });

  it("a switch or checkbox declares its state, not just its role", () => {
    const stateful = PRESSABLES.filter((o) => {
      const role = propValue(o.props, "accessibilityRole") ?? "";
      return /switch|checkbox|radio/.test(role);
    });
    expect(stateful.length).toBeGreaterThan(4);
    const missing = stateful.filter((o) => !hasProp(o.props, "accessibilityState")).map(where);
    expect(missing).toEqual([]);
  });
});

/* ------------------------------------------------------------------ */
/* Invariant 5 · names come from the tr-first catalog                  */
/* ------------------------------------------------------------------ */

describe("invariant 5 — accessible names come from the catalog, never a literal", () => {
  it("no accessibilityLabel is a bare source string", () => {
    const literals = [...PRESSABLES, ...TEXT_INPUTS]
      .filter((o) => {
        const value = propValue(o.props, "accessibilityLabel");
        return value !== null && /^["']/.test(value);
      })
      .map(where);
    expect(literals).toEqual([]);
  });

  it("no accessibilityHint is a bare source string", () => {
    const literals = [...PRESSABLES, ...TEXT_INPUTS]
      .filter((o) => {
        const value = propValue(o.props, "accessibilityHint");
        return value !== null && /^["']/.test(value);
      })
      .map(where);
    expect(literals).toEqual([]);
  });

  it("no accessible name is assembled with an ad-hoc separator", () => {
    // ": ", " · " and " — " belong to lib/a11y/labels, which is the one
    // place a screen reader's rhythm is decided.
    const adHoc = [...PRESSABLES, ...TEXT_INPUTS]
      .filter((o) => {
        const value = propValue(o.props, "accessibilityLabel") ?? "";
        return stringLiterals(value).some((literal) => /(: |·|—|\/)/.test(literal));
      })
      .map(where);
    expect(adHoc).toEqual([]);
  });

  it("the composition helpers are what the screens actually use", () => {
    const users = TSX.filter((f) => /\blib\/a11y\/labels\b/.test(f.source)).map((f) => f.name);
    expect(users).toContain("src/components/DialogueIntake.tsx");
    expect(users).toContain("src/components/SectionPanel.tsx");
    expect(users).toContain("src/app/(tabs)/visits/[visitId]/review.tsx");
  });
});

/* ------------------------------------------------------------------ */
/* BK5 · SC 1.3.1 Info and Relationships — headings                    */
/* ------------------------------------------------------------------ */

describe("BK5 / SC 1.3.1 — a screen's title is a heading, not just big text", () => {
  it("every screen that renders a hero line marks one as a heading", () => {
    const unmarked = SCREENS.filter(
      (f) => /role="hero"/.test(f.source) && !/\bheading\b/.test(f.source),
    ).map((f) => f.name);
    expect(unmarked).toEqual([]);
  });

  it("AppText carries the heading semantic itself, so screens cannot spell it wrong", () => {
    const themed = readFileSync(join(COMPONENTS, "Themed.tsx"), "utf8");
    expect(themed).toContain("heading");
    expect(themed).toMatch(/accessibilityRole=\{heading \? "header"/);
  });

  it("guidance blocks title their own section", () => {
    const block = readFileSync(join(COMPONENTS, "GuidanceBlock.tsx"), "utf8");
    expect(block).toMatch(/role="title"\s+heading/);
  });
});

/* ------------------------------------------------------------------ */
/* BK5 / SC 1.4.4 · dynamic type                                       */
/* ------------------------------------------------------------------ */

describe("SC 1.4.4 — text scales once, never twice", () => {
  it("a TextInput that applies scaledSize disables the OS multiplier", () => {
    // AppText already does this (Themed.tsx). A TextInput that sets
    // fontSize: scaledSize(...) AND leaves allowFontScaling on multiplies
    // the user's setting by itself — 200 % becomes 400 % and the field
    // truncates, which is the failure 1.4.4 exists to prevent.
    const doubled = TEXT_INPUTS.filter(
      (o) => /scaledSize\(/.test(o.props) && !/allowFontScaling=\{false\}/.test(o.props),
    ).map(where);
    expect(doubled).toEqual([]);
  });

  it("every TextInput sizes from the shared scale rather than a literal", () => {
    const literal = TEXT_INPUTS.filter((o) => /fontSize:\s*\d/.test(o.props)).map(where);
    expect(literal).toEqual([]);
  });
});

/* ------------------------------------------------------------------ */
/* BK14 · SC 2.2.2 Pause, Stop, Hide — reduced motion                  */
/* ------------------------------------------------------------------ */

describe("BK14 / SC 2.2.2 — motion stops when the OS says to", () => {
  // INT-335 (MOTION-6, C-3). The gate used to find loops by `Animated.loop`
  // alone, in screens and components alone, so a Reanimated `withRepeat` — or
  // any loop in src/lib — was invisible to it. It now reads every script the
  // app ships, and "gated" means the app's own hook, imported from the app's
  // module and called, plus the loop decision that hook feeds.
  it("every looping animation, core or Reanimated, is gated on the app's reduce-motion hook", () => {
    // Non-vacuity: the detector sees each loop shape and each missing half.
    const hook = `import { useReducedMotion } from "@/lib/a11y/prefs";\nconst reduce = useReducedMotion();\nconst on = loopingDecorationEnabled(reduce);`;
    expect(loops(`${hook}\nAnimated.loop(seq).start();`)).toBe(true);
    expect(loops(`${hook}\nsv.value = withRepeat(withTiming(1), -1, true);`)).toBe(true);
    expect(loops(`const s = { animationName: k, animationIterationCount: "infinite" };`)).toBe(
      true,
    );
    expect(loops(`// no withRepeat and no Animated.loop here\nconst x = 1;`)).toBe(false);
    expect(gatedOnAppHook(hook)).toBe(true);
    expect(gatedOnAppHook(hook.replace("@/lib/a11y/prefs", "react-native-reanimated"))).toBe(false);
    expect(gatedOnAppHook(hook.replace("loopingDecorationEnabled(reduce)", "!reduce"))).toBe(false);
    expect(gatedOnAppHook(hook.replace("useReducedMotion();", "false;"))).toBe(false);

    const looping = APP_SCRIPTS.filter((f) => loops(f.source));
    expect(looping.length).toBeGreaterThan(0);
    const ungated = looping.filter((f) => !gatedOnAppHook(f.source)).map((f) => f.name);
    expect(ungated).toEqual([]);
  });

  // INT-330 (MOTION-1). A native stack that names only its animation fades
  // for the iOS default of 500 ms, and react-native-screens holds any push
  // requested mid-transition until that transition ends — long enough to
  // keep a RED behind it past 02 §8.1's 300 ms (motion-verification.md S-1).
  // So the duration travels with the animation, from one policy, keyed by
  // the route's path: a navigator that classified `consent` instead of
  // `(auth)/consent` would quietly fade legal text.
  const squash = (s: string) => s.replace(/\s+/g, "");
  /** `...transitionFor(routeClassOf(`(auth)/${route.name}`)` for src/app/(auth)/_layout.tsx. */
  function policySpread(fn: "transitionFor" | "tabTransition", layout: string): string {
    const dir = layout.replace(/^src\/app\/?/, "").replace(/\/?_layout\.tsx$/, "");
    const path = dir === "" ? "route.name" : `\`${dir}/\${route.name}\``;
    return `...${fn}(routeClassOf(${path})`;
  }

  it("every native stack takes its transition, duration included, from the motion policy", () => {
    const stacks = SCREENS.flatMap((f) => readOpenings(f.source, f.name, ["Stack"]));
    expect(stacks.map((o) => o.file).sort()).toEqual(
      [
        "src/app/_layout.tsx",
        "src/app/(auth)/_layout.tsx",
        "src/app/(tabs)/visits/_layout.tsx",
      ].sort(),
    );
    const unpinned = stacks
      .filter(
        (o) =>
          !squash(propValue(o.props, "screenOptions") ?? "").includes(
            policySpread("transitionFor", o.file),
          ),
      )
      .map(where);
    expect(unpinned).toEqual([]);
  });

  it("the JS tabs take theirs from the same policy", () => {
    const tabs = SCREENS.flatMap((f) => readOpenings(f.source, f.name, ["Tabs"]));
    expect(tabs.map((o) => o.file)).toEqual(["src/app/(tabs)/_layout.tsx"]);
    const unpinned = tabs
      .filter(
        (o) =>
          !squash(propValue(o.props, "screenOptions") ?? "").includes(
            policySpread("tabTransition", o.file),
          ),
      )
      .map(where);
    expect(unpinned).toEqual([]);
  });

  it("no navigator or screen writes a transition literal", () => {
    // Every transition key arrives by spreading the policy; none is written
    // in a TSX file, whatever its value — "fade", 500, a primitive call.
    const KEY =
      /\b(animation|animationDuration|transitionSpec|gestureEnabled|fullScreenGestureEnabled|presentation|animationTypeForReplace|sceneStyleInterpolator)\s*:/;
    const written = TSX.flatMap((f) =>
      f.source
        .split("\n")
        .map((line, i) => ({ line, at: `${f.name}:${i + 1}` }))
        .filter(({ line }) => KEY.test(line))
        .map(({ at }) => at),
    );
    expect(written).toEqual([]);
  });

  it("programmatic scrolling is instantaneous under reduce-motion", () => {
    const scrollers = TSX.filter((f) => /scrollToEnd\(/.test(f.source));
    expect(scrollers.length).toBeGreaterThan(0);
    const unguarded = scrollers
      .filter((f) => !/scrollAnimated\(/.test(f.source))
      .map((f) => f.name);
    expect(unguarded).toEqual([]);
  });
});

/* ------------------------------------------------------------------ */
/* BK15 · SC 2.3.1 Three Flashes or Below Threshold                    */
/* ------------------------------------------------------------------ */

describe("BK15 / SC 2.3.1 — nothing repeats three times a second or faster", () => {
  // INT-335 (MOTION-6, C-2). This used to read the `duration:` literals of
  // DialogueIntake.tsx and demand at least one: removing the pulse would have
  // failed it, and a 100 ms fade added beside the pulse would have broken its
  // minimum. The period now lives in one place, `motion.loop`, whose tokens
  // are FULL periods; the bound is checked there, and every file that loops
  // must read its period from there and write none of its own.
  it("every loop period comes from motion.loop, and every half-period exceeds 167 ms", () => {
    const periods = Object.entries(motion.loop);
    expect(periods.length).toBeGreaterThan(0);
    for (const [name, ms] of periods) {
      // One full cycle is two halves; 3 Hz would need a 167 ms half-cycle.
      expect(ms / 2, `motion.loop.${name}`).toBeGreaterThan(167);
    }

    const token = new RegExp(`\\bmotion\\.loop\\.(?:${Object.keys(motion.loop).join("|")})\\b`);
    // Non-vacuity: a literal period is refused, a token period accepted.
    const literal = "Animated.loop(Animated.timing(v, { toValue: 0.3, duration: 700 }))";
    expect(literalDurations(literal)).toEqual(["700"]);
    const sourced = `Animated.loop(Animated.timing(v, { toValue: 0.3, duration: motion.loop.${periods[0][0]} / 2 }))`;
    expect(token.test(sourced) && literalDurations(sourced).length === 0).toBe(true);

    const looping = APP_SCRIPTS.filter((f) => loops(f.source));
    expect(looping.length).toBeGreaterThan(0);
    const unsourced = looping
      .filter((f) => !token.test(code(f.source)) || literalDurations(f.source).length > 0)
      .map((f) => f.name);
    expect(unsourced).toEqual([]);
  });
});

/* ------------------------------------------------------------------ */
/* BK18 · SC 2.4.3 Focus Order — the modal                             */
/* ------------------------------------------------------------------ */

describe("BK18 / SC 2.4.3 — a sheet takes focus with it", () => {
  it("the flag sits on the sheet, not on <Modal>, where RN would drop it", () => {
    // React Native's Modal enumerates the props it forwards to the native
    // host view; `accessibilityViewIsModal` is not one of them, so setting
    // it there type-checks and does nothing. This test pins the working
    // placement AND forbids the plausible-looking one.
    const onModal = MODALS.filter((o) => hasProp(o.props, "accessibilityViewIsModal")).map(where);
    expect(onModal).toEqual([]);
    for (const modal of MODALS) {
      const file = TSX.find((f) => f.name === modal.file)!;
      const flagged = readOpenings(file.source, file.name, ["View"]).filter((o) =>
        hasProp(o.props, "accessibilityViewIsModal"),
      );
      expect(flagged.length, modal.file).toBeGreaterThan(0);
    }
  });

  it("a Modal's transition obeys reduce-motion", () => {
    const hardcoded = MODALS.filter((o) => /animationType="/.test(o.props)).map(where);
    expect(hardcoded).toEqual([]);
  });
});

/* ------------------------------------------------------------------ */
/* SC 2.5.8 Target Size (Minimum)                                      */
/* ------------------------------------------------------------------ */

/** The `{ … }` body of each `StyleSheet.create` rule in a file. */
function styleRules(source: string): Map<string, string> {
  const rules = new Map<string, string>();
  const at = source.indexOf("StyleSheet.create(");
  if (at < 0) {
    return rules;
  }
  let depth = 0;
  let start = -1;
  for (let i = at; i < source.length; i += 1) {
    const c = source[i];
    if (c === "{") {
      if (depth === 1) {
        start = i;
      }
      depth += 1;
    } else if (c === "}") {
      depth -= 1;
      if (depth === 1 && start >= 0) {
        // The rule's name is the identifier immediately before its brace.
        const named = /([A-Za-z0-9_]+)\s*:\s*$/.exec(source.slice(0, start));
        if (named !== null) {
          rules.set(named[1], source.slice(start, i + 1));
        }
        start = -1;
      }
      if (depth === 0) {
        break;
      }
    }
  }
  return rules;
}

/**
 * Named floors the tree is allowed to state instead of a literal, resolved to
 * the value the app actually renders. INT-284 moved the focal CTA's 56 into
 * lib/prefs/appearance.ts so the glass bar's height and the scroll room
 * reserved for it read one number; resolving the name here keeps this gate
 * reading a real height rather than falling through to 0 — and if anyone
 * lowers either constant under MIN_TAP, the comparison below reddens.
 */
const NAMED_FLOORS: Record<string, number> = {
  MIN_TAP,
  CTA_MIN_HEIGHT,
};

function declaredHeight(body: string): number {
  for (const [name, value] of Object.entries(NAMED_FLOORS)) {
    if (new RegExp(`\\b(?:minHeight|height)\\s*:\\s*${name}\\b`).test(body)) {
      return value;
    }
  }
  const heights = [...body.matchAll(/\b(?:minHeight|height)\s*:\s*(\d+)/g)].map((m) =>
    Number(m[1]),
  );
  return heights.length > 0 ? Math.max(...heights) : 0;
}

/**
 * The `styles.*` names a style expression resolves to, following one hop
 * through a local `const x = [styles.a, styles.b]` — the pattern the
 * dialogue bubbles and the form fields use.
 */
function referencedStyles(expr: string, source: string): string[] {
  const direct = [...expr.matchAll(/styles\.([A-Za-z0-9_]+)/g)].map((m) => m[1]);
  // `\b` rather than a "not a dot" guard: the speaking bubble SPREADS its
  // array (`...bubbleStyle`), and a leading dot must not hide it.
  const identifiers = [...expr.matchAll(/\b([a-z][A-Za-z0-9_]*Style)\b/g)].map((m) => m[1]);
  const indirect = identifiers.flatMap((id) => {
    const declared = new RegExp(`const ${id}\\s*=\\s*\\[([\\s\\S]*?)\\];`).exec(source);
    return declared === null
      ? []
      : [...declared[1].matchAll(/styles\.([A-Za-z0-9_]+)/g)].map((m) => m[1]);
  });
  return [...direct, ...indirect];
}

describe(`SC 2.5.8 — every target reaches ${MIN_TAP} pt, by box or by slop`, () => {
  const byFile = new Map(TSX.map((f) => [f.name, styleRules(f.source)]));

  it("no Pressable relies on its content happening to be tall enough", () => {
    const short = PRESSABLES.filter((o) => {
      if (hasProp(o.props, "hitSlop")) {
        return false;
      }
      const style = propValue(o.props, "style") ?? "";
      if (/\bminHeight:\s*(\d+)/.test(style)) {
        return Number(/\bminHeight:\s*(\d+)/.exec(style)![1]) < MIN_TAP;
      }
      const rules = byFile.get(o.file) ?? new Map<string, string>();
      const source = TSX.find((f) => f.name === o.file)?.source ?? "";
      const referenced = referencedStyles(style, source);
      const best = Math.max(0, ...referenced.map((name) => declaredHeight(rules.get(name) ?? "")));
      return best < MIN_TAP;
    }).map(where);
    expect(short).toEqual([]);
  });

  it("slop is vertical only — horizontal slop would swallow the next chip", () => {
    const horizontal = PRESSABLES.filter((o) => {
      const slop = propValue(o.props, "hitSlop") ?? "";
      return /\b(left|right)\s*:/.test(slop) || /^\{\s*\d+\s*\}$/.test(slop);
    }).map(where);
    expect(horizontal).toEqual([]);
  });

  it("slop sizes are computed from the laid-out height, not guessed", () => {
    const guessed = PRESSABLES.filter((o) => {
      const slop = propValue(o.props, "hitSlop");
      return slop !== null && !/verticalSlop\(/.test(slop);
    }).map(where);
    expect(guessed).toEqual([]);
  });
});

/* ------------------------------------------------------------------ */
/* BK28 · SC 3.3.1 Error Identification · SC 4.1.3 Status Messages     */
/* ------------------------------------------------------------------ */

/*
 * INT-362. React Native gives the two screen readers different channels.
 * `accessibilityLiveRegion` is @platform android; iOS has no live regions and
 * no alert trait, so VoiceOver hears a line only when the app posts it with
 * `announceForAccessibility`. A line that sets one half is silent on the
 * other phone. The INT-226 report found three such lines, and the check that
 * should have caught them listed its four screens by hand.
 *
 * So both halves now come from one module, src/components/Announced.tsx, and
 * this section FINDS the lines in the source tree instead of being told where
 * they are. A line is an error or status line when it
 *   - declares a live region itself (one platform's half, on its own),
 *   - is drawn in the error colour, `amber`, or
 *   - renders catalogue copy the catalogue marks as a failure (an `error` /
 *     `err` key segment, or a key ending failed, notSaved, unsaved, unsent,
 *     unreachable) or as a wait (a Turkish value ending in "…").
 * Every such line must sit inside an AnnouncedText or an AnnouncedRegion, or
 * be listed in ANNOUNCED_ELSEWHERE with the reason it needs neither.
 */

/** The catalogue is read for its values: the ellipsis is the catalogue's own mark for a wait. */
const { tr } = await import("../src/lib/i18n/tr");

const ANNOUNCER = "src/components/Announced.tsx";
const ANNOUNCED_TAGS = ["AnnouncedText", "AnnouncedRegion"] as const;

/** Every .tsx the app ships, wherever it lives — a new screen is walked, never listed. */
const LINE_SOURCES: { name: string; source: string }[] = walk(SRC)
  .filter((p) => p.endsWith(".tsx") && !/\.(test|spec)\.tsx$/.test(p))
  .map((path) => ({
    name: relative(MOBILE, path).split(sep).join("/"),
    source: readFileSync(path, "utf8"),
  }))
  // The mechanism itself: AppText maps `live` onto the platform props, and
  // the announcer is the one place both halves are put together.
  .filter((f) => f.name !== ANNOUNCER && f.name !== "src/components/Themed.tsx")
  .sort((a, b) => a.name.localeCompare(b.name));

const FAILURE_KEY =
  /(?:^|\.)(?:error|err)(?:\.|$)|(?:failed|Failed|notSaved|unsaved|unsent|unreachable)$/;

function waitCopy(key: string): boolean {
  const value: string | undefined = (tr as Record<string, string>)[key];
  return value !== undefined && value.trimEnd().endsWith("…");
}

/*
 * INT-397. Three lines report how the patient's own action stands — the note
 * was sent, a consent change waits for a connection, a setting did not save —
 * and stay on screen for as long as it is so, visit after visit. Their words
 * carry no mark the scan could read (no failure suffix, no ellipsis), so they
 * are named here, by key: every file that renders one is still found by
 * walking. Such a line is news when the outcome happens in front of the
 * patient and never on arrival, so it must sit in an AnnouncedText whose
 * `news` is a transition the file takes from `useNews(…)`.
 */
const OUTCOME_COPY: ReadonlySet<string> = new Set([
  "notifications.pending",
  "review.sentInfo",
  "consent.queue.note",
]);

/** `news={x}` where the same file sets `const x = useNews(…)` — a transition, never a literal. */
function newsFromHook(props: string, text: string): boolean {
  const value = propValue(props, "news");
  const name = value === null ? undefined : /^\{\s*([A-Za-z_$][\w$]*)\s*\}$/.exec(value)?.[1];
  return name !== undefined && new RegExp(`\\bconst\\s+${name}\\s*=\\s*useNews\\(`).test(text);
}

type Why =
  | "live region by hand"
  | "error colour"
  | "failure copy"
  | "wait copy"
  | "outcome copy"
  | "outcome announced on arrival";

interface LineFinding {
  readonly file: string;
  readonly line: number;
  readonly why: Why;
  /** The catalogue key the line renders, or the element that declares the region. */
  readonly subject: string;
}

/** [start, end) of every `<Tag … />` and `<Tag …>…</Tag>` in a comment-free source. */
function elementSpans(text: string, tag: string): [number, number][] {
  const spans: [number, number][] = [];
  const edge = new RegExp(`<${tag}(?=[\\s/>])|</${tag}>`, "g");
  const selfClosing = (at: number): boolean => {
    const end = endOfOpening(text, at + tag.length + 1);
    return end > 0 && text[end - 1] === "/";
  };
  for (const open of text.matchAll(new RegExp(`<${tag}(?=[\\s/>])`, "g"))) {
    if (selfClosing(open.index)) {
      spans.push([open.index, endOfOpening(text, open.index + tag.length + 1) + 1]);
      continue;
    }
    let depth = 0;
    let close = text.length;
    edge.lastIndex = open.index;
    for (let m = edge.exec(text); m !== null; m = edge.exec(text)) {
      if (m[0].startsWith("</")) {
        depth -= 1;
      } else if (!selfClosing(m.index)) {
        depth += 1;
      }
      if (depth === 0) {
        close = m.index + m[0].length;
        break;
      }
    }
    spans.push([open.index, close]);
  }
  return spans;
}

/** Every error or status line in one source that is NOT inside the announcer's elements. */
function unannouncedLines(source: string, file: string): LineFinding[] {
  const text = code(source);
  const lineAt = (at: number) => text.slice(0, at).split("\n").length;
  const announced = ANNOUNCED_TAGS.flatMap((tag) =>
    elementSpans(text, tag).map(([start, end]) => ({
      start,
      end,
      props: text.slice(start + tag.length + 1, endOfOpening(text, start + tag.length + 1)),
    })),
  );
  const inside = (at: number) => announced.some(({ start, end }) => at >= start && at < end);
  /** The innermost announcer element around `at`, or undefined. */
  const holderOf = (at: number) =>
    announced
      .filter(({ start, end }) => at >= start && at < end)
      .sort((a, b) => a.end - a.start - (b.end - b.start))[0];
  const found: LineFinding[] = [];

  // One platform's half, declared by hand: the defect INT-226 found.
  for (const m of text.matchAll(
    /(?<![\w.])(?:live|accessibilityLiveRegion)=|accessibilityRole="alert"/g,
  )) {
    const tag = /<([A-Za-z.]+)[^<]*$/.exec(text.slice(0, m.index))?.[1] ?? "?";
    found.push({ file, line: lineAt(m.index), why: "live region by hand", subject: `<${tag}>` });
  }
  // The error colour, on a line nothing announces.
  for (const [start, end] of elementSpans(text, "AppText")) {
    const props = text.slice(
      start + "<AppText".length,
      endOfOpening(text, start + "<AppText".length),
    );
    const colour = propValue(props, "color") ?? "";
    const amber = stringLiterals(colour).includes("amber") || /\btheme\.amber\b/.test(props);
    if (amber && !inside(start)) {
      const key =
        /\bt\(\s*"([A-Za-z0-9_.]+)"/.exec(text.slice(start, end))?.[1] ?? "(runtime copy)";
      found.push({ file, line: lineAt(start), why: "error colour", subject: key });
    }
  }
  // Failure and wait copy, wherever it is rendered from — a prop, a helper, a line.
  for (const m of text.matchAll(/\bt\(\s*"([A-Za-z0-9_.]+)"/g)) {
    const key = m[1];
    if (OUTCOME_COPY.has(key)) {
      // INT-397: announced, and announced only as news.
      const holder = holderOf(m.index);
      if (holder === undefined) {
        found.push({ file, line: lineAt(m.index), why: "outcome copy", subject: key });
      } else if (!newsFromHook(holder.props, text)) {
        found.push({
          file,
          line: lineAt(m.index),
          why: "outcome announced on arrival",
          subject: key,
        });
      }
      continue;
    }
    const why: Why | null = FAILURE_KEY.test(key)
      ? "failure copy"
      : waitCopy(key)
        ? "wait copy"
        : null;
    if (why !== null && !inside(m.index)) {
      found.push({ file, line: lineAt(m.index), why, subject: key });
    }
  }
  return found;
}

const findingId = (f: LineFinding): string => `${f.file} › ${f.subject}`;

/**
 * Lines the discovery reaches that are announced another way, or that are
 * not a status at all — each with its reason. Every entry must still match a
 * finding (tested below), so this list can only shrink.
 */
const ANNOUNCED_ELSEWHERE: Record<string, string> = {
  "src/components/DialogueIntake.tsx › dialogue.preparing":
    "the dialogue's turn state, announced once on both platforms by its own useLiveAnnouncement " +
    "(a11y.dialogue.preparing); a live region on the bubble would say it twice",
  "src/components/DialogueIntake.tsx › dialogue.transcribing":
    "the dialogue's turn state, announced by its own useLiveAnnouncement (a11y.dialogue.transcribing)",
  "src/components/DialogueIntake.tsx › voiceFirst.preparing":
    "the dialogue's settling state, announced by its own useLiveAnnouncement (a11y.dialogue.settling)",
  "src/components/ConfirmCard.tsx › records.card.unitConflict":
    "part of the card from the moment the card exists, not a change; its words say what the colour shows",
  "src/app/(tabs)/records.tsx › records.uploading":
    "the upload button's own label while it works; the outcome is the records notice, which is announced",
  "src/components/VoiceNote.tsx › voice.processing":
    "the label of the dev-only voice-note button (INT-194), rendered under __DEV__ only",
  "src/components/VoiceNote.tsx › voice.unreachable":
    "the label of the dev-only voice-note button (INT-194), rendered under __DEV__ only",
};

const LINE_FINDINGS: LineFinding[] = LINE_SOURCES.flatMap((f) =>
  unannouncedLines(f.source, f.name),
);

/** Every file that renders an error or status line, announced or not — found by walking. */
const LINE_FILES: string[] = LINE_SOURCES.filter(
  (f) =>
    ANNOUNCED_TAGS.some((tag) => new RegExp(`<${tag}[\\s/>]`).test(code(f.source))) ||
    LINE_FINDINGS.some((finding) => finding.file === f.name),
).map((f) => f.name);

describe("BK28 / SC 3.3.1 · SC 4.1.3 — every error and status line announces itself on both platforms", () => {
  it("the discovery walks the tree and reaches every line the INT-226 report named", () => {
    // Non-vacuity. None of these is listed to the scan; each is FOUND.
    for (const named of [
      "src/app/(tabs)/visits/[visitId]/issue-link.tsx",
      "src/components/ConfirmCard.tsx",
      "src/components/RecordReading.tsx",
      "src/components/KioskGate.tsx",
      "src/app/(auth)/phone.tsx",
      "src/app/(auth)/otp.tsx",
      "src/app/(tabs)/visits/new.tsx",
      "src/app/(tabs)/records.tsx",
    ]) {
      expect(LINE_FILES, named).toContain(named);
    }
    expect(LINE_FILES.length).toBeGreaterThan(15);
  });

  it.each(LINE_FILES)("%s announces its error on BOTH platforms", (name) => {
    // Every error or status line in the file goes through the announcer,
    // which sets the Android live region AND posts the iOS announcement.
    const open = LINE_FINDINGS.filter(
      (f) => f.file === name && !(findingId(f) in ANNOUNCED_ELSEWHERE),
    ).map((f) => `${f.file}:${f.line} ${f.why} (${f.subject})`);
    expect(open).toEqual([]);
  });

  it("a newly added unannounced error line is caught — the near-miss control", () => {
    const screen = (line: string) =>
      [
        'import { AppText, Screen } from "@/components/Themed";',
        "export default function Fresh() {",
        "  return (",
        "    <Screen>",
        '      <AppText role="body" color="inkSoft">{t("auth.phone.why")}</AppText>',
        `      {problem !== null ? ${line} : null}`,
        "    </Screen>",
        "  );",
        "}",
      ].join("\n");
    const whys = (line: string) =>
      unannouncedLines(screen(line), "src/app/fresh.tsx").map((f) => f.why);
    // The fixed line, and an ordinary one beside it, are silent to the scan.
    expect(
      whys('<AnnouncedText tone="error" role="body" color="amber" message={t(problem)} />'),
    ).toEqual([]);
    // Each way a line can be missed is found, and named.
    expect(whys('<AppText role="body" color="amber">{t(problem)}</AppText>')).toEqual([
      "error colour",
    ]);
    expect(whys('<AppText role="body" live="assertive">{t(problem)}</AppText>')).toEqual([
      "live region by hand",
    ]);
    expect(
      whys('<View accessibilityLiveRegion="polite"><AppText>{t(problem)}</AppText></View>'),
    ).toEqual(["live region by hand"]);
    expect(
      whys('<AppText role="caption" color="inkSoft">{t("health.readFailed")}</AppText>'),
    ).toEqual(["failure copy"]);
    expect(whys('<AppText role="caption">{t("health.loading")}</AppText>')).toEqual(["wait copy"]);
    // A region's children are inside it, and so announced by it.
    expect(
      whys(
        '<AnnouncedRegion tone="status" message={t("voiceFirst.checking")}><AppText>{t("voiceFirst.checking")}</AppText></AnnouncedRegion>',
      ),
    ).toEqual([]);
  });

  it("the exceptions are still real — the list can only shrink", () => {
    const ids = new Set(LINE_FINDINGS.map(findingId));
    const stale = Object.keys(ANNOUNCED_ELSEWHERE).filter((id) => !ids.has(id));
    expect(stale).toEqual([]);
  });

  it("an outcome line announced on arrival, or not at all, is caught — the near-miss control (INT-397)", () => {
    const screen = (line: string) =>
      [
        'import { AnnouncedText, useNews } from "@/components/Announced";',
        'import { AppText, Screen } from "@/components/Themed";',
        "export default function Sent() {",
        "  const sentNews = useNews(sent);",
        "  const other = sent;",
        "  return (",
        "    <Screen>",
        '      <AppText role="body" color="inkSoft">{t("review.intro")}</AppText>',
        `      {sent ? ${line} : null}`,
        "    </Screen>",
        "  );",
        "}",
      ].join("\n");
    const whys = (line: string) =>
      unannouncedLines(screen(line), "src/app/sent.tsx").map((f) => `${f.why} (${f.subject})`);
    // The fixed line: announced, and news only when the note has just gone.
    expect(
      whys(
        '<AnnouncedText tone="status" news={sentNews} role="body" message={t("review.sentInfo")} />',
      ),
    ).toEqual([]);
    // The line as INT-362 left it: a plain caption, silent on both platforms.
    expect(whys('<AppText role="body" color="inkSoft">{t("review.sentInfo")}</AppText>')).toEqual([
      "outcome copy (review.sentInfo)",
    ]);
    // Announced, but on every arrival at the screen — old news.
    expect(whys('<AnnouncedText tone="status" message={t("review.sentInfo")} />')).toEqual([
      "outcome announced on arrival (review.sentInfo)",
    ]);
    // Muted with a literal, or with a value that is not a transition.
    expect(
      whys('<AnnouncedText tone="status" news={false} message={t("review.sentInfo")} />'),
    ).toEqual(["outcome announced on arrival (review.sentInfo)"]);
    expect(
      whys('<AnnouncedText tone="status" news={other} message={t("review.sentInfo")} />'),
    ).toEqual(["outcome announced on arrival (review.sentInfo)"]);
    // A region has no notion of news, so it is arrival too.
    expect(
      whys(
        '<AnnouncedRegion tone="status" message={t("consent.queue.note")}><AppText>{t("consent.queue.note")}</AppText></AnnouncedRegion>',
      ),
    ).toEqual([
      "outcome announced on arrival (consent.queue.note)",
      "outcome announced on arrival (consent.queue.note)",
    ]);
  });

  it("the three outcome lines MC-26 named are found by the walk, and each is announced only as news", () => {
    for (const key of OUTCOME_COPY) {
      expect((tr as Record<string, string>)[key], key).toBeTruthy();
    }
    const sites = LINE_SOURCES.flatMap((f) =>
      [...code(f.source).matchAll(/\bt\(\s*"([A-Za-z0-9_.]+)"/g)]
        .filter((m) => OUTCOME_COPY.has(m[1]))
        .map((m) => `${f.name} › ${m[1]}`),
    );
    // MC-26 (2026-09-27) is the oracle: five renderings of the three keys.
    expect(sites).toEqual(
      expect.arrayContaining([
        "src/app/(tabs)/me/notifications.tsx › notifications.pending",
        "src/app/(tabs)/visits/[visitId]/review.tsx › review.sentInfo",
        "src/app/(tabs)/visits/[visitId]/index.tsx › review.sentInfo",
        "src/app/(tabs)/me/consents/index.tsx › consent.queue.note",
        "src/app/(tabs)/me/consents/[purpose].tsx › consent.queue.note",
      ]),
    );
    const open = LINE_FINDINGS.filter((f) => OUTCOME_COPY.has(f.subject)).map(
      (f) => `${f.file}:${f.line} ${f.why} (${f.subject})`,
    );
    expect(open).toEqual([]);
  });

  it("a line's news is always a transition from useNews — no line is muted with a literal", () => {
    const withNews = LINE_SOURCES.flatMap((f) =>
      readOpenings(code(f.source), f.name, ["AnnouncedText"])
        .filter((o) => propValue(o.props, "news") !== null)
        .map((o) => ({ opening: o, text: code(f.source) })),
    );
    // The five outcome lines at least; a line with no `news` is news whenever shown.
    expect(withNews.length).toBeGreaterThanOrEqual(5);
    const muted = withNews
      .filter(({ opening, text }) => !newsFromHook(opening.props, text))
      .map(({ opening }) => where(opening));
    expect(muted).toEqual([]);
  });

  it("no outcome line is excused, and the exceptions have not grown (INT-397)", () => {
    const excused = Object.keys(ANNOUNCED_ELSEWHERE).filter((id) =>
      OUTCOME_COPY.has(id.slice(id.indexOf(" › ") + 3)),
    );
    expect(excused).toEqual([]);
    // INT-362 left seven; the list only shrinks.
    expect(Object.keys(ANNOUNCED_ELSEWHERE).length).toBeLessThanOrEqual(7);
  });

  it("no live region is declared anywhere but the announcer", () => {
    const byHand = LINE_FINDINGS.filter((f) => f.why === "live region by hand").map(
      (f) => `${f.file}:${f.line} ${f.subject}`,
    );
    expect(byHand).toEqual([]);
  });

  it("every announced line states its tone, and the announcer — not the call site — picks the politeness", () => {
    const openings = LINE_SOURCES.flatMap((f) =>
      readOpenings(code(f.source), f.name, [...ANNOUNCED_TAGS]),
    );
    expect(openings.length).toBeGreaterThan(20);
    // The literal itself, or the two branches of a conditional — never a
    // literal the condition merely compares against.
    const tonesOf = (expr: string): string[] =>
      /^"[^"]*"$/.test(expr)
        ? stringLiterals(expr)
        : [...expr.matchAll(/[?:]\s*"([^"]*)"/g)].map((m) => m[1]);
    expect(tonesOf('{cond === "filled" ? "status" : "error"}')).toEqual(["status", "error"]);
    // INT-363 adds the third: a warning is assertive like an error and is
    // spoken as shown like a status (lib/a11y/announce.ts).
    const TONES = new Set(["error", "warning", "status"]);
    const toneless = openings
      .filter((o) => {
        const tones = tonesOf(propValue(o.props, "tone") ?? "");
        return tones.length === 0 || tones.some((tone) => !TONES.has(tone));
      })
      .map(where);
    expect(toneless).toEqual([]);
    const overridden = openings
      .filter((o) => /\b(?:live|politeness|accessibilityLiveRegion)=/.test(o.props))
      .map(where);
    expect(overridden).toEqual([]);
  });

  it("the announcer puts both halves on every line: Android's live region and iOS's announcement", () => {
    const announcer = readFileSync(join(MOBILE, ANNOUNCER), "utf8");
    // Politeness comes from the tone, in one place: error and warning →
    // assertive, status → polite.
    expect(announcer.match(/politenessOf\(tone\)/g)?.length).toBe(2);
    // Android: the live region, on the line and on the region. A line is news
    // unless its screen says otherwise (INT-397), so every line INT-362
    // routed keeps both halves exactly as before.
    expect(announcer).toMatch(/\bnews = true\b/);
    expect(announcer).toContain("live={news ? politeness : undefined}");
    expect(announcer).toContain("accessibilityLiveRegion={politeness}");
    // iOS: the announcement, posted by both components on every change —
    // by the line while it is news.
    expect(
      announcer.match(/useLineAnnouncement\(news \? spoken : null, politeness\)/g)?.length,
    ).toBe(1);
    expect(announcer.match(/useLineAnnouncement\(spoken, politeness\)/g)?.length).toBe(1);
    // SC 3.3.1: an error is heard as one — the error word, from the catalogue.
    expect(announcer.match(/spokenLine\(tone, message, t\("a11y\.error"\)\)/g)?.length).toBe(2);
    const prefs = readFileSync(join(SRC, "lib", "a11y", "prefs.ts"), "utf8");
    expect(prefs).toMatch(/lineStep\(previous\.current, message, Platform\.OS, politeness\)/);
    expect(prefs).toContain("AccessibilityInfo.announceForAccessibilityWithOptions(");
    // The iOS half is never taken on its own: only the announcer calls it.
    const halfOnly = LINE_SOURCES.filter((f) => /\buseLineAnnouncement\b/.test(code(f.source))).map(
      (f) => f.name,
    );
    expect(halfOnly).toEqual([]);
  });

  it("a line that is not news is shown without either half, and turning into news makes it anew (INT-397)", () => {
    const announcer = code(readFileSync(join(MOBILE, ANNOUNCER), "utf8"));
    // TalkBack speaks a live region when it appears or changes; a line whose
    // words stay put while it turns into news is made again, with its region.
    expect(announcer).toContain('key={news ? "news" : "shown"}');
    // What is news is the tested rule (lib/a11y/announce.ts newsStep):
    // whatever stands on arrival is old news, and "in front" is the
    // navigator's own focus, so a screen under another one stays quiet.
    expect(announcer).toContain("useState(() => arrivedAt(standing))");
    expect(announcer).toContain("newsStep(memory, standing, inFront)");
    expect(announcer).toContain("const inFront = useIsFocused()");
    // SC 3.3.1 still holds on arrival: an error found standing is named as
    // one when the reader reaches it, news or not.
    expect(announcer).toContain("spokenAs={spoken === message ? undefined : spoken}");
  });

  it("the announcement path writes nothing to a log (invariant 6)", () => {
    // What is announced is what the screen already shows; it must not also
    // reach a console, a metric or a crash report.
    for (const name of [ANNOUNCER, "src/lib/a11y/prefs.ts", "src/lib/a11y/announce.ts"]) {
      const source = code(readFileSync(join(MOBILE, name), "utf8"));
      expect(source, name).not.toMatch(/\bconsole\s*\./);
      expect(source, name).not.toMatch(
        /from\s+"[^"]*(?:telemetry|metrics|analytics|logger)[^"]*"/i,
      );
    }
  });

  it("AppText maps `live` onto the platform's own announcement props", () => {
    const themed = readFileSync(join(COMPONENTS, "Themed.tsx"), "utf8");
    expect(themed).toContain("accessibilityLiveRegion={live}");
    expect(themed).toContain('"alert"');
    // What TalkBack reads out of the live region is the spoken form — the
    // error word included — while the visible words stay as they are.
    expect(themed).toContain("accessibilityLabel={spokenAs}");
  });

  it("an error is never carried by colour alone", () => {
    // Every amber error line must also be announced; the colour is the
    // sighted redundancy, never the signal (02 §8.2, SC 1.4.1).
    // Both spellings: the `color="amber"` prop AND the raw `theme.amber`
    // token, so a warning styled the other way cannot slip past.
    const amberOnly = TSX.filter(
      (f) =>
        /color="amber"|theme\.amber\b/.test(f.source) &&
        !/\blive=|<Announced(?:Text|Region)\b|accessibilityLabel/.test(f.source),
    ).map((f) => f.name);
    expect(amberOnly).toEqual([]);
  });
});

/* ------------------------------------------------------------------ */
/* SC 3.3.8 Accessible Authentication (Minimum) — INT-361              */
/* ------------------------------------------------------------------ */

describe("SC 3.3.8 — a delivered code fills the boxes without transcription", () => {
  const OTP_SCREEN = "src/app/(auth)/otp.tsx";
  const otp = TSX.find((f) => f.name === OTP_SCREEN)!;
  const registers = TEXT_INPUTS.filter((o) => o.file === OTP_SCREEN);

  it("the six boxes are one TextInput rendered once per register", () => {
    // One opening tag inside the digits map is what makes each assertion
    // below hold for EVERY box, not just the first.
    expect(otp, OTP_SCREEN).toBeDefined();
    expect(registers).toHaveLength(1);
    const mapped = otp.source.indexOf("digits.map(");
    expect(mapped).toBeGreaterThan(-1);
    expect(otp.source.indexOf("<TextInput")).toBeGreaterThan(mapped);
    expect(otp.source).toMatch(/Array\.from\(\{ length: OTP_LENGTH \}/);
    expect(OTP_LENGTH).toBe(6);
  });

  it("every box asks the OS for the one-time code on each platform", () => {
    const [box] = registers;
    // iOS: the "From Messages" suggestion above the keyboard.
    expect(propValue(box.props, "textContentType")).toBe('"oneTimeCode"');
    // Android: the SMS-code autofill hint; web: the HTML autocomplete token.
    const hints = stringLiterals(propValue(box.props, "autoComplete") ?? "");
    expect(hints).toContain("sms-otp");
    expect(hints).toContain("one-time-code");
  });

  it("no field cap cuts a pasted or autofilled code down to its first digit", () => {
    // The platform applies maxLength BEFORE onChangeText sees the text, so a
    // cap of one silently kept only the first digit of a paste or of the OS
    // autofill. One digit per register is now kept by the entry state.
    expect(propValue(registers[0].props, "maxLength")).toBeNull();
  });

  it("every box hands its whole new text to the shared distributor", () => {
    expect(propValue(registers[0].props, "onChangeText")).toMatch(/enterOtp\(digits, index, /);
    expect(otp.source).toMatch(/import \{[^}]*\benterOtp\b[^}]*\} from "@\/lib\/auth\/phone";/);
  });

  it("each box keeps its catalog name: which digit of the code it holds", () => {
    expect(propValue(registers[0].props, "accessibilityLabel")).toBe(
      '{labelled(t("a11y.otp.digit"), `${index + 1}`)}',
    );
  });

  it("the code stays masked while it is on screen", () => {
    expect(hasProp(registers[0].props, "secureTextEntry")).toBe(true);
  });
});

/* ------------------------------------------------------------------ */
/* Invariant 6 — the code never reaches a log, analytics or a report   */
/* ------------------------------------------------------------------ */

describe("invariant 6 — the one-time code reaches no log line, analytics event or error report", () => {
  const AUTH_LIB = join(SRC, "lib", "auth");
  const onPath = [
    TSX.find((f) => f.name === "src/app/(auth)/otp.tsx")!,
    ...readdirSync(AUTH_LIB)
      .filter((n) => n.endsWith(".ts") && !n.endsWith(".test.ts"))
      .map((n) => ({
        name: `src/lib/auth/${n}`,
        source: readFileSync(join(AUTH_LIB, n), "utf8"),
      })),
  ];

  it("the scan covers the screen, the distributor and the verify client", () => {
    const names = onPath.map((f) => f.name);
    expect(names).toContain("src/app/(auth)/otp.tsx");
    expect(names).toContain("src/lib/auth/phone.ts");
    expect(names).toContain("src/lib/auth/api.ts");
  });

  it.each(["src/app/(auth)/otp.tsx", "src/lib/auth/phone.ts", "src/lib/auth/api.ts"])(
    "%s writes nothing to the console",
    (name) => {
      const file = onPath.find((f) => f.name === name)!;
      expect(file.source).not.toMatch(/\bconsole\s*\./);
    },
  );

  it("nothing on the entry path imports a telemetry, metrics or analytics sink", () => {
    const sinks = onPath.flatMap((f) =>
      [...f.source.matchAll(/from\s+"([^"]+)"|import\(\s*"([^"]+)"\s*\)/g)]
        .map((m) => m[1] ?? m[2])
        .filter((spec) => /telemetry|metrics|analytics|sentry|glitchtip|logger/i.test(spec))
        .map((spec) => `${f.name} → ${spec}`),
    );
    expect(sinks).toEqual([]);
  });

  it("a crash event that carries the code reports none of it", () => {
    // If the SafeError boundary were ever missed on the verify path, the
    // crash scrubber is the last wall: plant the code in every limb a
    // reporter fills and read the bytes the transport would send.
    const CODE = "730418";
    const identity: TelemetryIdentity = {
      appVersion: "0.1.0",
      buildId: "eas-1841",
      sbomDigest: `sha256:${"ab".repeat(32)}`,
      platform: "android",
      osVersion: "15",
      deviceModel: "Pixel8",
      environment: "dev",
      releaseChannel: "preview",
      tenantId: "acibadem-maslak",
    };
    const report = buildCrashReport(identity, {
      message: `verify failed for code ${CODE}`,
      errorCode: "otp_verify_failed",
      exception: {
        values: [
          {
            type: "AuthApiError",
            value: `code ${CODE} rejected`,
            stacktrace: {
              frames: [
                {
                  module: "src/app/(auth)/otp.tsx",
                  function: "submit",
                  lineno: 111,
                  colno: 7,
                  vars: { code: CODE, digits: CODE.split("") },
                  context_line: `const patientId = await verifyOtp(phone, "${CODE}");`,
                },
              ],
            },
          },
        ],
      },
      breadcrumbs: {
        values: [
          {
            category: "network",
            event: "request_failed",
            status: 401,
            url: `https://api.example.test/v1/auth/otp/verify?code=${CODE}`,
            data: { body: JSON.stringify({ code: CODE }) },
          },
          { category: "user_input", event: "pasted", message: CODE },
        ],
      },
      tags: { screen_id: "auth_otp", otp: CODE, prompt_version: CODE },
      extra: { code: CODE },
      request: { data: { code: CODE } },
    });
    const body = buildEnvelopeBody(
      { publicKey: "f00d", projectId: "1", envelopeUrl: "http://127.0.0.1:8010/api/1/envelope/" },
      report,
    );
    expect(body).not.toContain(CODE);
    // NEAR-MISS CONTROL: the report is not simply empty — the legitimate,
    // allow-listed values of the same event do come through.
    expect(report.errorCode).toBe("otp_verify_failed");
    expect(report.tags.screen_id).toBe("auth_otp");
    expect(report.exceptionType).toBe("AuthApiError");
  });
});

/* ------------------------------------------------------------------ */
/* The voice dialogue — the surface the whole product turns on         */
/* ------------------------------------------------------------------ */

describe("voice dialogue — a screen-reader user can follow the conversation", () => {
  const dialogue = TSX.find((f) => f.name === "src/components/DialogueIntake.tsx")!;

  it("every turn is attributed to a speaker", () => {
    // Left/right alignment is the sighted cue for who said what, and no
    // screen reader conveys alignment. `spoken()` puts the speaker first.
    expect(dialogue.source).toContain("spoken(");
    expect(dialogue.source).toContain('t("a11y.speaker.agent")');
    expect(dialogue.source).toContain('t("a11y.speaker.patient")');
  });

  it("the agent's words stay in the agent bubble's name while it is speaking", () => {
    // The barge-in affordance is a HINT. Putting it in the label (as the
    // pre-INT-144 source did) replaced the question with "tap to stop" and
    // made the question unreachable to a screen reader.
    const bubbles = readOpenings(dialogue.source, dialogue.name, ["Pressable"]).filter((o) =>
      /bargeIn/.test(o.props),
    );
    expect(bubbles.length).toBe(1);
    // The name is the composed turn (`name` = spoken(agent, …question…));
    // the affordance is a hint beside it, never instead of it.
    expect(dialogue.source).toContain("const name = spoken(");
    expect(propValue(bubbles[0].props, "accessibilityLabel")).toContain("name");
    expect(hasProp(bubbles[0].props, "accessibilityHint")).toBe(true);
  });

  it("listening / speaking / transcribing are announced, not just animated", () => {
    expect(dialogue.source).toContain("useLiveAnnouncement(");
  });

  it("the turn state is announced ONCE — not by a hook and a live region both", () => {
    // A live region on a bubble re-reads the bubble's whole label when it
    // changes, and these labels contain the entire question. Combined with
    // the hook it says the state twice, the second time glued to a
    // paragraph of clinical text.
    expect(dialogue.source).not.toContain("accessibilityLiveRegion");
  });

  it("a bubble's name ends in the words the bubble actually shows", () => {
    // SC 2.5.3. The a11y catalog's status strings are for the ANNOUNCEMENT;
    // a bubble's name must use the visible copy, or a voice-control user
    // reading the screen aloud cannot reach the control.
    expect(dialogue.source).toContain('t("voiceFirst.listening")');
    expect(dialogue.source).toContain('t("dialogue.speakingHint")');
    expect(dialogue.source).toContain('t("dialogue.transcribing")');
  });

  it("the transcript itself is a named region", () => {
    expect(dialogue.source).toContain('t("a11y.dialogue.transcript")');
  });

  it("the composer is reachable and described", () => {
    const inputs = readOpenings(dialogue.source, dialogue.name, ["TextInput"]);
    expect(inputs.length).toBe(1);
    expect(hasProp(inputs[0].props, "accessibilityLabel")).toBe(true);
    expect(hasProp(inputs[0].props, "accessibilityHint")).toBe(true);
  });

  it("the send button is icon-only, so its name and disabled state are explicit", () => {
    const send = readOpenings(dialogue.source, dialogue.name, ["Pressable"]).filter((o) =>
      /styles\.sendButton/.test(o.props),
    );
    expect(send.length).toBe(1);
    expect(hasProp(send[0].props, "accessibilityLabel")).toBe(true);
    expect(hasProp(send[0].props, "accessibilityState")).toBe(true);
  });

  it("a single-choice turn offers radios, not checkboxes", () => {
    // A checkbox tells the reader "you may pick several"; a single-select
    // question means the opposite, and the chip handler enforces it.
    expect(dialogue.source).toContain('"radio"');
  });
});

/* ------------------------------------------------------------------ */
/* SC 1.4.1 Use of Colour — decoration is hidden, state is spoken      */
/* ------------------------------------------------------------------ */

describe("BK8 / SC 1.4.1 — nothing is carried by colour alone", () => {
  it("the intake progress dots are decoration and are hidden from the reader", () => {
    const intake = TSX.find((f) => f.name === "src/app/(tabs)/visits/[visitId]/intake.tsx")!;
    const dots = readOpenings(intake.source, intake.name, ["View"]).filter((o) =>
      /styles\.progressDot/.test(o.props),
    );
    expect(dots.length).toBe(1);
    expect(hasProp(dots[0].props, "accessibilityElementsHidden")).toBe(true);
    expect(hasProp(dots[0].props, "importantForAccessibility")).toBe(true);
  });

  it("the status ladder speaks which rungs are reached", () => {
    const ladder = readFileSync(join(COMPONENTS, "StatusLadder.tsx"), "utf8");
    expect(ladder).toContain("accessibilityLabel");
    expect(ladder).toContain('t("a11y.ladder.reached")');
    expect(ladder).toContain('t("a11y.ladder.pending")');
  });

  it("the prep gauge reports a value, not only a rendered arc", () => {
    const gauge = readFileSync(join(COMPONENTS, "PrepGauge.tsx"), "utf8");
    expect(gauge).toContain("accessibilityValue");
  });
});

/* ------------------------------------------------------------------ */
/* Nested controls inside a merged element                             */
/* ------------------------------------------------------------------ */

describe("BK31 / SC 4.1.2 — a control nested in a pressable row stays reachable", () => {
  it("ListRow forwards a secondary action for its trailing control", () => {
    // A pressable row is `accessible` by default, so RN merges its whole
    // subtree into one element and a Pressable in the trailing slot is not
    // focusable at all on iOS. A custom action is the platform's answer.
    const row = readFileSync(join(COMPONENTS, "ListRow.tsx"), "utf8");
    expect(row).toContain("accessibilityActions");
    expect(row).toContain("onAccessibilityAction");
  });

  it("the consent switch — the withdrawal path — uses it", () => {
    // Withdrawal must be at least as easy as grant. Without this, a
    // screen-reader user could read a purpose but never turn it off.
    const list = readFileSync(join(COMPONENTS, "ConsentList.tsx"), "utf8");
    expect(list).toContain("secondaryAction");
  });

  it("no control nested in a pressable row grows its target with slop", () => {
    // Slop on a child inside a parent Pressable steals the parent's taps.
    // On the consent list that turned "open the text" into "withdraw the
    // consent" for a 7 pt band above and below the pill.
    const list = readFileSync(join(COMPONENTS, "ConsentList.tsx"), "utf8");
    expect(list).not.toContain("hitSlop");
  });
});

/* ------------------------------------------------------------------ */
/* BK24 · SC 3.1.1 Language of Page                                    */
/* ------------------------------------------------------------------ */

describe("BK24 / SC 3.1.1 — text declares the language it is written in", () => {
  it("every line carries a BCP-47 tag matching the active catalog", () => {
    // The locale is an in-app switch and need not match the device's, so
    // "the OS knows" is not an answer: a Turkish sentence read by an
    // English voice is unintelligible, not accented.
    const themed = readFileSync(join(COMPONENTS, "Themed.tsx"), "utf8");
    expect(themed).toContain("accessibilityLanguage={SPEECH_LANGUAGE[getLocale()]}");
    expect(themed).toContain('tr: "tr-TR"');
    expect(themed).toContain('en: "en-GB"');
  });

  it("no screen renders a bare react-native Text, bypassing that declaration", () => {
    const bare = TSX.filter(
      (f) => /<Text[\s/>]/.test(f.source) && f.name !== "src/components/Themed.tsx",
    ).map((f) => f.name);
    expect(bare).toEqual([]);
  });
});

/* ------------------------------------------------------------------ */
/* Criteria met by ABSENCE — provable, and worth pinning               */
/* ------------------------------------------------------------------ */

describe("criteria the app satisfies by not having the feature", () => {
  const ALL = TSX.map((f) => f.source).join("\n");

  it("BK12 / SC 2.1.4 — no character key shortcuts exist", () => {
    expect(ALL).not.toMatch(/onKeyPress|KeyboardEvent|hardwareBackPress/);
  });

  it("BK20 / SC 2.5.1 — no path-based or multipoint gesture is required", () => {
    // Scroll and pinch-to-zoom are the platform's own and exempt; what the
    // criterion forbids is an app-authored gesture with no single-pointer
    // alternative. There is none: every action is a tap.
    expect(ALL).not.toMatch(/PanResponder|GestureDetector|Swipeable|onGestureEvent/);
    expect(ALL).not.toMatch(/onLongPress/);
  });

  it("BK23 / SC 2.5.4 — nothing is actuated by moving the device", () => {
    expect(ALL).not.toMatch(/Accelerometer|DeviceMotion|Gyroscope|Magnetometer/);
  });
});

/* ------------------------------------------------------------------ */
/* BK13 · SC 2.2.1 Timing Adjustable — INT-363                         */
/* ------------------------------------------------------------------ */

/*
 * A time limit the patient meets must warn before it acts and let the patient
 * extend it with one action, with at least 20 seconds to do so, as many times
 * as needed (WCAG 2.2 SC 2.2.1, "Extend"). The INT-226 report found that this
 * check read screens and components only, while kiosk mode's 60 s idle wipe
 * sat in src/lib with no warning at all. So the scan walks every script under
 * src — `.ts` included, tests excluded — and every timer it finds must be one
 * of two things:
 *   - in NOT_A_TIME_LIMIT: it limits nothing the patient does (a request
 *     deadline, a retry delay, a meter), with the reason; or
 *   - in WARNED_TIME_LIMITS: a time limit whose every timer is the scheduler
 *     it hands to its warning machine. It arms no timer of its own.
 * A timer anywhere else is a finding, and so is a time limit's timer armed
 * outside its machine.
 */

/**
 * WCAG 2.2 SC 2.2.1 "Extend": at least 20 seconds. Written out here rather
 * than imported, so the constant under test cannot vouch for itself.
 */
const WCAG_EXTEND_FLOOR_MS = 20_000;

/** Timers that take nothing from the patient when they run out, each with its reason. */
const NOT_A_TIME_LIMIT: Record<string, string> = {
  "src/app/(auth)/otp.tsx":
    "the resend cooldown: a server rate limit that OFFERS a resend when it runs out and takes nothing away",
  "src/lib/auth/expoApiBase.ts": "a deadline on the dev API health probe",
  "src/lib/dev/hosts.ts": "a deadline on the dev host probe",
  "src/lib/dialogue/georgeClip.ts": "a request deadline on a scripted clip fetch",
  "src/lib/dialogue/tts.ts":
    "request deadlines on synthesis; a late lane is skipped, nothing is taken from the patient",
  "src/lib/dialogue/ttsLane.ts": "deadlines on the TTS lane's health probe and synthesis request",
  "src/lib/dialogue/useDialogueSession.ts":
    "the barge-in level meter's sampling interval: it listens, it limits nothing",
  "src/lib/extract.ts": "a request deadline and the one retry delay of the extraction call",
  "src/lib/intake/noteSendClient.ts":
    "a request deadline on the note's send (INT-510): a send that runs out is queued and tried again, the note stays as it was",
  "src/lib/intake/useNoteOutbox.ts":
    "the pause before a queued send is tried again (INT-510): it re-sends, it limits nothing the patient does",
  "src/lib/livekit/session.ts": "the reconnect backoff's sleep",
  "src/lib/records/extraction.ts":
    "the backoff between asks about a document still being read: when it stops, the reading line stays and nothing is taken",
};

/** Time limits the patient meets → the warning machine each one's timer is handed to. */
const WARNED_TIME_LIMITS: Record<string, string> = {
  "src/lib/kiosk/nativeKiosk.ts": "startKioskIdleClock",
};

type TimingWhy = "unclassified timer" | "time limit without a warning";

interface TimingFinding {
  readonly file: string;
  readonly line: number;
  readonly why: TimingWhy;
}

/** A call that arms a timer. A type such as `ReturnType<typeof setInterval>` is not one. */
const TIMER_CALL = /\bset(?:Timeout|Interval)\s*\(/g;

function hasTimer(source: string): boolean {
  return [...code(source).matchAll(TIMER_CALL)].length > 0;
}

/** [start, end) of every call `name(…)` in a comment-free source, strings skipped. */
function callSpans(text: string, name: string): [number, number][] {
  const spans: [number, number][] = [];
  for (const m of text.matchAll(new RegExp(`\\b${name}\\s*\\(`, "g"))) {
    let depth = 0;
    let i = m.index + m[0].length - 1;
    for (; i < text.length; i += 1) {
      const c = text[i];
      if (c === '"' || c === "'" || c === "`") {
        i = endOfString(text, i);
      } else if (c === "(") {
        depth += 1;
      } else if (c === ")") {
        depth -= 1;
        if (depth === 0) {
          break;
        }
      }
    }
    spans.push([m.index, i + 1]);
  }
  return spans;
}

/** Every timer in one script that is neither harmless nor handed to a warning. */
function timingFindings(file: string, source: string): TimingFinding[] {
  const text = code(source);
  const lineAt = (at: number) => text.slice(0, at).split("\n").length;
  const timers = [...text.matchAll(TIMER_CALL)].map((m) => m.index);
  if (timers.length === 0 || file in NOT_A_TIME_LIMIT) {
    return [];
  }
  const machine = WARNED_TIME_LIMITS[file];
  if (machine === undefined) {
    return timers.map((at) => ({ file, line: lineAt(at), why: "unclassified timer" }));
  }
  const handed = callSpans(text, machine);
  return timers
    .filter((at) => !handed.some(([start, end]) => at >= start && at < end))
    .map((at) => ({ file, line: lineAt(at), why: "time limit without a warning" }));
}

const TIMED_SCRIPTS: string[] = APP_SCRIPTS.filter((f) => hasTimer(f.source)).map((f) => f.name);

describe("BK13 / SC 2.2.1 — a time limit warns before it acts and can be extended", () => {
  it("BK13 / SC 2.2.1 — every timer under src, lib included, limits nothing or warns before it acts", () => {
    const findings = APP_SCRIPTS.flatMap((f) => timingFindings(f.name, f.source)).map(
      (f) => `${f.file}:${f.line} ${f.why}`,
    );
    expect(findings).toEqual([]);
  });

  it("the scan reaches src/lib, where the kiosk idle wipe lives", () => {
    // Non-vacuity: the timers outside a screen are FOUND by the walk.
    expect(TIMED_SCRIPTS).toContain("src/lib/kiosk/nativeKiosk.ts");
    expect(TIMED_SCRIPTS).toContain("src/app/(auth)/otp.tsx");
    expect(TIMED_SCRIPTS.filter((name) => name.startsWith("src/lib/")).length).toBeGreaterThan(5);
  });

  it("every classified timer still exists — the register holds no stale entry", () => {
    const named = [...Object.keys(NOT_A_TIME_LIMIT), ...Object.keys(WARNED_TIME_LIMITS)];
    expect(named.filter((name) => !TIMED_SCRIPTS.includes(name))).toEqual([]);
  });

  it("no screen or component owns a timer but the resend cooldown", () => {
    // A timer belongs in a .ts module, where the scan above classifies it and
    // a unit test can drive it on a fake clock; a screen only renders.
    const timed = TSX.filter((f) => /setTimeout|setInterval/.test(f.source)).map((f) => f.name);
    expect(timed).toEqual(["src/app/(auth)/otp.tsx"]);
  });

  it("the kiosk warning gives at least 20 seconds to extend, and the wipe still falls at 60 s", () => {
    expect(KIOSK_IDLE_WARNING_MS).toBeGreaterThanOrEqual(WCAG_EXTEND_FLOOR_MS);
    expect(KIOSK_IDLE_WIPE_MS).toBe(60_000);
    // The machine the adapter's timer is handed to warns before it wipes, and
    // the grace it then gives is the whole warning interval.
    const start = kioskIdleStart(0);
    const warned = kioskIdleReducer(start, { type: "tick", at: kioskIdleDue(start)! });
    expect(warned.phase).toBe("warning");
    expect(kioskIdleDue(warned)! - warned.since).toBeGreaterThanOrEqual(WCAG_EXTEND_FLOOR_MS);
  });

  it("a timer planted outside a screen, or a time limit that skips the warning, is caught — the near-miss control", () => {
    const whys = (file: string, source: string) => timingFindings(file, source).map((f) => f.why);
    // A bare idle wipe dropped into src/lib: not a screen, and still found.
    expect(
      whys(
        "src/lib/fresh/idle.ts",
        "export const arm = (wipe: () => void) => setTimeout(wipe, 60_000);",
      ),
    ).toEqual(["unclassified timer"]);
    // The kiosk adapter as it stood before INT-363: its own wipe timer, no warning.
    const before = [
      'import { KIOSK_IDLE_WIPE_MS } from "./kioskState";',
      "export function watchKiosk(handlers: { onIdle: () => void }) {",
      "  const timer = setTimeout(handlers.onIdle, KIOSK_IDLE_WIPE_MS);",
      "  return { stop: () => clearTimeout(timer) };",
      "}",
    ].join("\n");
    expect(whys("src/lib/kiosk/nativeKiosk.ts", before)).toEqual(["time limit without a warning"]);
    // Handing the timer to the warning machine is what clears it...
    const handed = [
      "const clock = startKioskIdleClock(onPhase, {",
      "  now: () => Date.now(),",
      "  schedule: (fire: () => void, ms: number) => setTimeout(fire, ms),",
      "  cancel: (h: ReturnType<typeof setTimeout>) => clearTimeout(h),",
      "});",
    ].join("\n");
    expect(whys("src/lib/kiosk/nativeKiosk.ts", handed)).toEqual([]);
    // ...and a second timer armed beside the machine is caught all the same.
    expect(
      whys("src/lib/kiosk/nativeKiosk.ts", `${handed}\nconst wipe = setTimeout(onIdle, 60_000);`),
    ).toEqual(["time limit without a warning"]);
    // A comment that names a timer is not one.
    expect(
      whys("src/lib/fresh/doc.ts", "// setTimeout(wipe, 60_000)\nexport const x = 1;"),
    ).toEqual([]);
  });
});

/* ------------------------------------------------------------------ */
/* SC 1.3.4 Orientation — INT-360                                      */
/* ------------------------------------------------------------------ */

/*
 * The app follows the device. app.json used to say `"orientation": "portrait"`,
 * which writes a portrait-only UISupportedInterfaceOrientations on iOS and
 * `android:screenOrientation="portrait"` on Android: every screen locked, for
 * an intake whose orientation is not essential (the INT-226 finding, MC-04).
 *
 * A lock can come back without anyone touching app.json, so the scan reads
 * every script under src, the config plugins, app.json and app.config.ts, and
 * knows each way this code base could lock a screen:
 *   - an orientation setting: the app config's `orientation`, a navigator's
 *     `orientation` / `screenOrientation` option, or a manifest attribute,
 *     set to a portrait or landscape value;
 *   - the orientation API: expo-screen-orientation, lockAsync, lockPlatformAsync;
 *   - a native orientation key a plugin writes (UISupportedInterfaceOrientations,
 *     requestedOrientation);
 *   - a `<Modal>` that does not rotate. On an iPhone React Native presents a
 *     Modal portrait-only unless it names its orientations (RCTModalHostView:
 *     an empty list is UIInterfaceOrientationMaskPortrait), so a sheet opened
 *     in landscape turns the screen under the patient.
 * A lock the scan finds must be registered in the SC 1.3.4 row of
 * docs/compliance/accessibility-conformance.yaml (`essential_locks`), with the
 * reason its orientation is essential; the rendered report names it. The
 * register is empty: the records camera is the OS's own capture screen and a
 * photo's upright travels in its EXIF tag (lib/records/jpeg.ts), so no screen
 * of this app needs one orientation.
 */

const CONFORMANCE = join(
  MOBILE,
  "..",
  "..",
  "docs",
  "compliance",
  "accessibility-conformance.yaml",
);

type LockKind =
  | "orientation setting"
  | "orientation API"
  | "native orientation key"
  | "portrait-only modal"
  | "restricted modal";

interface OrientationLock {
  readonly file: string;
  readonly line: number;
  readonly kind: LockKind;
}

const ORIENTATION_VALUE =
  "(?:portrait|landscape|sensorPortrait|sensorLandscape|reversePortrait|reverseLandscape|userPortrait|userLandscape)";

const LOCK_PATTERNS: readonly (readonly [LockKind, RegExp])[] = [
  [
    "orientation setting",
    // A type alias spelling the values out (`type Orientation = "portrait" | …`)
    // names them; it sets nothing.
    new RegExp(
      `(?<!\\btype\\s+)\\b(?:screen)?[oO]rientation[\\]"']*\\s*[:=]\\s*["']${ORIENTATION_VALUE}`,
      "g",
    ),
  ],
  ["orientation API", /["']expo-screen-orientation["']|\block(?:Platform)?Async\s*\(/g],
  [
    "native orientation key",
    /\bUISupportedInterfaceOrientations\b|\b(?:set)?[rR]equestedOrientation\b/g,
  ],
];

/** Every way one file locks the orientation, comments ignored. */
function orientationLocks(file: string, source: string): OrientationLock[] {
  const text = code(source);
  const lineAt = (at: number) => text.slice(0, at).split("\n").length;
  const found: OrientationLock[] = [];
  for (const [kind, pattern] of LOCK_PATTERNS) {
    for (const m of text.matchAll(pattern)) {
      found.push({ file, line: lineAt(m.index), kind });
    }
  }
  for (const modal of readOpenings(text, file, ["Modal"])) {
    const named = propValue(modal.props, "supportedOrientations");
    if (named === null) {
      found.push({ file, line: modal.line, kind: "portrait-only modal" });
    } else if (named !== "{ALL_ORIENTATIONS}") {
      found.push({ file, line: modal.line, kind: "restricted modal" });
    }
  }
  return found.sort((a, b) => a.line - b.line);
}

const lockId = (lock: OrientationLock): string => `${lock.file} › ${lock.kind}`;

/**
 * The SC 1.3.4 row's `essential_locks` register: lock id → the reason that
 * orientation is essential. Read with a small line reader (the suite has no
 * YAML parser), which refuses an entry with no reason and a row with no
 * register at all.
 */
function essentialLocks(yaml: string): Map<string, string> {
  const row = /\n {2}- sc: "1\.3\.4"\n([\s\S]*?)(?=\n {2}- |\n#)/.exec(yaml);
  if (row === null) {
    throw new Error('the conformance source has no `- sc: "1.3.4"` row');
  }
  const lines = row[1].split("\n");
  const start = lines.findIndex((l) => /^ {4}essential_locks:/.test(l));
  if (start < 0) {
    throw new Error("the SC 1.3.4 row has no essential_locks register");
  }
  const inline = lines[start].replace(/^ {4}essential_locks:\s*/, "");
  if (inline === "[]") {
    return new Map();
  }
  if (inline !== "") {
    throw new Error(`essential_locks is [] or a block list, not ${inline}`);
  }
  const block: string[] = [];
  for (const l of lines.slice(start + 1)) {
    if (/^ {0,4}\S/.test(l)) {
      break;
    }
    block.push(l);
  }
  const register = new Map<string, string>();
  for (const entry of block.join("\n").split(/\n(?= {6}- )/)) {
    if (entry.trim() === "") {
      continue;
    }
    const lock = /^ {6}- lock: "([^"]+)"/m.exec(entry)?.[1];
    if (lock === undefined) {
      throw new Error(`an essential_locks entry names no lock: ${entry.trim()}`);
    }
    const reason = (/^ {8}reason:(?:\s*>-)?\s*([\s\S]*)$/m.exec(entry)?.[1] ?? "")
      .replace(/\s+/g, " ")
      .trim();
    if (reason === "") {
      throw new Error(`${lock}: an essential lock without a reason`);
    }
    register.set(lock, reason);
  }
  return register;
}

/** Everything that can lock: the scripts the app ships, its config plugins and its config. */
const ORIENTATION_SOURCES: { name: string; source: string }[] = [
  ...APP_SCRIPTS,
  ...readdirSync(join(MOBILE, "plugins"))
    .filter((n) => n.endsWith(".js"))
    .map((n) => ({
      name: `plugins/${n}`,
      source: readFileSync(join(MOBILE, "plugins", n), "utf8"),
    })),
  ...["app.json", "app.config.ts"].map((n) => ({
    name: n,
    source: readFileSync(join(MOBILE, n), "utf8"),
  })),
];

const ORIENTATION_LOCKS: OrientationLock[] = ORIENTATION_SOURCES.flatMap((f) =>
  orientationLocks(f.name, f.source),
);

describe("SC 1.3.4 — the app is not locked to one orientation", () => {
  it("SC 1.3.4 — app.json follows the device in every build profile", () => {
    const expo = (
      JSON.parse(readFileSync(join(MOBILE, "app.json"), "utf8")) as { expo: ExpoConfig }
    ).expo;
    // "default" writes all four interface orientations on iOS and
    // `unspecified` on Android (@expo/config-plugins, Orientation).
    expect(expo.orientation).toBe("default");
    for (const profile of [undefined, "development", "preview", "production"]) {
      const env = profile === undefined ? {} : { EAS_BUILD_PROFILE: profile };
      expect(resolveAppConfig(expo, env).orientation, profile ?? "local").toBe("default");
    }
  });

  it("the lock scan reads the config, the plugins and every script under src", () => {
    // Non-vacuity: each place a lock could live is read, not listed by hand.
    const names = ORIENTATION_SOURCES.map((f) => f.name);
    expect(names).toContain("app.json");
    expect(names).toContain("app.config.ts");
    expect(names).toContain("plugins/withVoiceAudio.js");
    expect(names).toContain("src/components/SectionPanel.tsx");
    expect(names.filter((n) => n.startsWith("src/lib/")).length).toBeGreaterThan(50);
  });

  it("SC 1.3.4 — every orientation lock in the app is registered as essential, with its reason", () => {
    const register = essentialLocks(readFileSync(CONFORMANCE, "utf8"));
    const unregistered = ORIENTATION_LOCKS.filter((l) => !register.has(lockId(l))).map(
      (l) => `${l.file}:${l.line} ${l.kind}`,
    );
    expect(unregistered).toEqual([]);
  });

  it("the register names only locks that still exist — it can only shrink", () => {
    const register = essentialLocks(readFileSync(CONFORMANCE, "utf8"));
    const live = new Set(ORIENTATION_LOCKS.map(lockId));
    expect([...register.keys()].filter((id) => !live.has(id))).toEqual([]);
  });

  it("a planted lock that is not registered is caught — the near-miss control", () => {
    const kinds = (file: string, source: string) =>
      orientationLocks(file, source).map((l) => l.kind);
    // The config as it stood before INT-360, and as it stands now.
    expect(kinds("app.json", '{ "expo": { "orientation": "portrait" } }')).toEqual([
      "orientation setting",
    ]);
    expect(kinds("app.json", '{ "expo": { "orientation": "default" } }')).toEqual([]);
    // A screen that locks itself, statically or behind the lazy import a
    // native module needs in this suite.
    expect(
      kinds(
        "src/app/fresh.tsx",
        'import * as ScreenOrientation from "expo-screen-orientation";\n' +
          "void ScreenOrientation.lockAsync(ScreenOrientation.OrientationLock.PORTRAIT_UP);",
      ),
    ).toEqual(["orientation API", "orientation API"]);
    expect(
      kinds("src/app/fresh.tsx", 'const o = await import("expo-screen-orientation");'),
    ).toEqual(["orientation API"]);
    // A navigator option, and a plugin writing the manifest attribute.
    expect(
      kinds("src/app/_layout.tsx", '<Stack screenOptions={{ orientation: "portrait_up" }} />'),
    ).toEqual(["orientation setting"]);
    expect(
      kinds("plugins/withLock.js", 'activity.$["android:screenOrientation"] = "portrait";'),
    ).toEqual(["orientation setting"]);
    expect(
      kinds(
        "plugins/withLock.js",
        'plist.UISupportedInterfaceOrientations = ["UIInterfaceOrientationPortrait"];',
      ),
    ).toEqual(["native orientation key"]);
    // A Modal: silent, restricted, and rotating.
    expect(kinds("src/components/Sheet.tsx", "<Modal visible={open} transparent>")).toEqual([
      "portrait-only modal",
    ]);
    expect(
      kinds(
        "src/components/Sheet.tsx",
        '<Modal visible={open} supportedOrientations={["portrait"]}>',
      ),
    ).toEqual(["restricted modal"]);
    expect(
      kinds(
        "src/components/Sheet.tsx",
        "<Modal visible={open} supportedOrientations={ALL_ORIENTATIONS}>",
      ),
    ).toEqual([]);
    // A comment that names a lock is not one; neither is the JPEG orientation tag.
    expect(
      kinds(
        "src/app/fresh.tsx",
        "// ScreenOrientation.lockAsync(PORTRAIT_UP) is NOT done here\nexport const x = 1;",
      ),
    ).toEqual([]);
    expect(
      kinds(
        "src/lib/records/fresh.ts",
        "function seg(orientation: number) { return orientation; }",
      ),
    ).toEqual([]);
    // Nor is a type that spells the values out: lib/a11y/orientation.ts has one.
    expect(
      kinds("src/lib/a11y/fresh.ts", 'export type Orientation = "portrait" | "landscape-left";'),
    ).toEqual([]);
    // Registering the lock, with a reason, is the one thing that clears it.
    const planted = orientationLocks(
      "src/app/fresh.tsx",
      "void ScreenOrientation.lockAsync(PORTRAIT_UP);",
    );
    expect(planted.filter((l) => !new Map<string, string>().has(lockId(l)))).toHaveLength(1);
    const registered = new Map([["src/app/fresh.tsx › orientation API", "the reason"]]);
    expect(planted.filter((l) => !registered.has(lockId(l)))).toEqual([]);
  });

  it("the register reader refuses an entry with no reason, and a row with no register", () => {
    const yaml = (register: string) =>
      [
        "wcag:",
        '  - sc: "1.3.4"',
        "    name: Orientation",
        "    status: Supports",
        `${register}    remarks: The row's remarks.`,
        "",
        '  - sc: "1.3.5"',
        "    name: Identify Input Purpose",
        "",
      ].join("\n");
    expect(essentialLocks(yaml("    essential_locks: []\n")).size).toBe(0);
    expect([
      ...essentialLocks(
        yaml(
          '    essential_locks:\n      - lock: "src/app/scan.tsx › orientation API"\n' +
            "        reason: >-\n          The capture guide is drawn for a\n          portrait page.\n",
        ),
      ),
    ]).toEqual([
      ["src/app/scan.tsx › orientation API", "The capture guide is drawn for a portrait page."],
    ]);
    expect(() =>
      essentialLocks(
        yaml('    essential_locks:\n      - lock: "src/app/scan.tsx › orientation API"\n'),
      ),
    ).toThrow(/without a reason/);
    expect(() => essentialLocks(yaml(""))).toThrow(/no essential_locks register/);
  });

  it("every Modal rotates with the device — iOS presents one portrait-only unless told otherwise", () => {
    expect(MODALS.length).toBeGreaterThan(0);
    const fixed = MODALS.filter(
      (o) => propValue(o.props, "supportedOrientations") !== "{ALL_ORIENTATIONS}",
    ).map(where);
    expect(fixed).toEqual([]);
    for (const file of new Set(MODALS.map((o) => o.file))) {
      const source = TSX.find((f) => f.name === file)!.source;
      expect(source, file).toMatch(
        /import \{[^}]*\bALL_ORIENTATIONS\b[^}]*\} from "@\/lib\/a11y\/orientation";/,
      );
      // A Modal is its own window: the Screen's safe edges do not reach it, so
      // its content takes the side insets itself (the notch is at a side in
      // landscape).
      expect(code(source), file).toMatch(
        /\binsets\.left\b[\s\S]*\binsets\.right\b|\binsets\.right\b[\s\S]*\binsets\.left\b/,
      );
    }
  });
});

/*
 * The layout half (acceptance line 2): every screen lays out in landscape at
 * the largest text size with no clipped control and no horizontal scroll of
 * body text. The landscape windows it is held to are a 6.1-inch phone
 * (844 × 390 pt) and the smallest iPhone (568 × 320 pt).
 *
 * What the tree can prove is the absence of the shapes that break there:
 *   - a fixed height taller than a control, or a floor taller than half the
 *     shortest landscape window: a box decided in portrait that the landscape
 *     window cannot hold;
 *   - a percentage height: a full-height assumption;
 *   - a window size read once (`Dimensions.get`, stale after a rotation) or
 *     from one axis without `shortSide` (the portrait width is the landscape
 *     LONG side, so a figure sized from it outgrows the height);
 *   - chrome pinned to both side edges (`position: "absolute"`, `left: 0`,
 *     `right: 0`) that does not read the side insets: in landscape the notch
 *     and the rounded corners are at the sides;
 *   - a horizontal scroller.
 * Each finding is fixed, or listed below with the reason it is safe. The list
 * can only shrink. What the tree cannot prove — that each screen renders
 * clear in landscape at the largest step — is the owner's device audit, DA-05.
 */

const LANDSCAPE_WINDOWS = [
  { name: "6.1-inch phone", width: 844, height: 390 },
  { name: "smallest iPhone", width: 568, height: 320 },
] as const;

const SHORTEST_LANDSCAPE = Math.min(...LANDSCAPE_WINDOWS.map((w) => w.height));

/** A control-sized box (the primer badge is 56); anything taller is a floor or scrolls. */
const FIXED_HEIGHT_MAX = 64;

/** A floor may take up to half of the shortest landscape window. */
const FLOOR_MAX = SHORTEST_LANDSCAPE / 2;

type LandscapeRisk =
  | "fixed height taller than a control"
  | "floor taller than half the shortest landscape window"
  | "percentage height"
  | "one-time window read"
  | "size from the long side"
  | "edge-pinned chrome without the side insets"
  | "horizontal scroller";

interface LandscapeFinding {
  readonly file: string;
  readonly line: number;
  readonly why: LandscapeRisk;
  readonly subject: string;
}

/** `name: { … }` StyleSheet rules at two-space indent, braces counted, with their line. */
function namedRules(text: string): { name: string; body: string; at: number }[] {
  const rules: { name: string; body: string; at: number }[] = [];
  const head = /\n {2}([A-Za-z0-9_]+): \{/g;
  for (let m = head.exec(text); m !== null; m = head.exec(text)) {
    let depth = 1;
    let i = head.lastIndex;
    for (; i < text.length && depth > 0; i += 1) {
      if (text[i] === "{") {
        depth += 1;
      } else if (text[i] === "}") {
        depth -= 1;
      }
    }
    rules.push({ name: m[1], body: text.slice(head.lastIndex, i - 1), at: m.index + 1 });
    head.lastIndex = i;
  }
  return rules;
}

/** Every landscape-risk shape in one script, comments ignored. */
function landscapeRisks(file: string, source: string): LandscapeFinding[] {
  const text = code(source);
  const lineAt = (at: number) => text.slice(0, at).split("\n").length;
  const found: LandscapeFinding[] = [];
  const add = (line: number, why: LandscapeRisk, subject: string) =>
    found.push({ file, line, why, subject });

  for (const m of text.matchAll(/\b(height|maxHeight|minHeight):\s*(\d+(?:\.\d+)?)\b/g)) {
    const value = Number(m[2]);
    if (m[1] === "minHeight" ? value > FLOOR_MAX : value > FIXED_HEIGHT_MAX) {
      add(
        lineAt(m.index),
        m[1] === "minHeight"
          ? "floor taller than half the shortest landscape window"
          : "fixed height taller than a control",
        m[0],
      );
    }
  }
  for (const m of text.matchAll(/\b(?:height|maxHeight|minHeight):\s*["']\d+(?:\.\d+)?%["']/g)) {
    add(lineAt(m.index), "percentage height", m[0]);
  }
  for (const m of text.matchAll(/\bDimensions\s*\.\s*get\s*\(/g)) {
    add(lineAt(m.index), "one-time window read", "Dimensions.get");
  }
  if (!/\bshortSide\s*\(/.test(text)) {
    for (const m of text.matchAll(/\buseWindowDimensions\(\)(?!\s*\.\s*fontScale\b)/g)) {
      add(lineAt(m.index), "size from the long side", "useWindowDimensions()");
    }
  }
  const readsSideInsets = /\binsets\.left\b/.test(text) && /\binsets\.right\b/.test(text);
  for (const rule of namedRules(text)) {
    const pinned =
      /position: "absolute"/.test(rule.body) &&
      /\bleft: 0\b/.test(rule.body) &&
      /\bright: 0\b/.test(rule.body);
    if (pinned && !readsSideInsets) {
      add(lineAt(rule.at), "edge-pinned chrome without the side insets", rule.name);
    }
  }
  for (const o of readOpenings(text, file, ["ScrollView", "FlatList", "SectionList"])) {
    if (hasProp(o.props, "horizontal")) {
      add(o.line, "horizontal scroller", `<${o.tag}>`);
    }
  }
  return found.sort((a, b) => a.line - b.line);
}

const riskId = (f: LandscapeFinding): string => `${f.file} › ${f.subject}`;

/**
 * Shapes the scan reaches that hold in landscape, each with its reason. Every
 * entry must still match a finding (tested below), so this list can only shrink.
 */
const LANDSCAPE_SAFE: Record<string, string> = {
  'src/components/SectionPanel.tsx › maxHeight: "78%"':
    "a cap, not a height, on a sheet whose rows scroll inside it: in a 320 pt window it " +
    "shows fewer rows and clips none",
  "src/components/GlassBar.tsx › floating":
    "every host renders the bar inside a Screen that keeps its left and right safe edges " +
    "(FLOW_EDGES), so it spans the inset content box, not the window",
  "src/components/DialogueIntake.tsx › bottomStack":
    "pinned inside the intake Screen, which keeps its left and right safe edges; capped at " +
    "the height of its frame, and the bar's upper part scrolls",
};

const LANDSCAPE_FINDINGS: LandscapeFinding[] = APP_SCRIPTS.flatMap((f) =>
  landscapeRisks(f.name, f.source),
);

describe("SC 1.3.4 — every screen lays out in landscape at the largest text size", () => {
  it("no layout decides a height the landscape window cannot hold", () => {
    const open = LANDSCAPE_FINDINGS.filter((f) => !(riskId(f) in LANDSCAPE_SAFE)).map(
      (f) => `${f.file}:${f.line} ${f.why} (${f.subject})`,
    );
    expect(open).toEqual([]);
  });

  it("the landscape exceptions are still real — the list can only shrink", () => {
    const ids = new Set(LANDSCAPE_FINDINGS.map(riskId));
    expect(Object.keys(LANDSCAPE_SAFE).filter((id) => !ids.has(id))).toEqual([]);
  });

  it("the landscape scan catches each shape it names — the near-miss control", () => {
    const whys = (source: string) => landscapeRisks("src/app/fresh.tsx", source).map((f) => f.why);
    expect(whys("const s = StyleSheet.create({\n  box: { height: 240 },\n});")).toEqual([
      "fixed height taller than a control",
    ]);
    expect(whys("const s = StyleSheet.create({\n  badge: { width: 56, height: 56 },\n});")).toEqual(
      [],
    );
    expect(whys("const s = StyleSheet.create({\n  field: { minHeight: 200 },\n});")).toEqual([
      "floor taller than half the shortest landscape window",
    ]);
    expect(whys("const s = StyleSheet.create({\n  field: { minHeight: 120 },\n});")).toEqual([]);
    expect(whys('const s = StyleSheet.create({\n  sheet: { maxHeight: "60%" },\n});')).toEqual([
      "percentage height",
    ]);
    expect(whys('const { height } = Dimensions.get("window");')).toEqual(["one-time window read"]);
    // PrepGauge as it stood before INT-360, and as it stands now.
    expect(whys("const { width } = useWindowDimensions();\nconst size = width - 40;")).toEqual([
      "size from the long side",
    ]);
    expect(whys("const size = shortSide(useWindowDimensions()) - 40;")).toEqual([]);
    expect(whys("const os = useWindowDimensions().fontScale;")).toEqual([]);
    // Chrome pinned to both sides, with and without the side insets.
    const bar =
      'const s = StyleSheet.create({\n  wrap: { position: "absolute", left: 0, right: 0, bottom: 0 },\n});';
    expect(whys(bar)).toEqual(["edge-pinned chrome without the side insets"]);
    expect(
      whys(`const insets = useSafeAreaInsets();\nconst pad = [insets.left, insets.right];\n${bar}`),
    ).toEqual([]);
    expect(whys("<ScrollView horizontal>{row}</ScrollView>")).toEqual(["horizontal scroller"]);
    // A comment that names a shape is not one.
    expect(whys("// height: 400 would clip here\nexport const x = 1;")).toEqual([]);
  });

  it("the landscape windows are the ones the pass was held to", () => {
    expect(SHORTEST_LANDSCAPE).toBe(320);
    expect(FLOOR_MAX).toBe(160);
    // The primer badge, the largest fixed box in the tree, is a control-sized 56.
    expect(FIXED_HEIGHT_MAX).toBeGreaterThanOrEqual(56);
  });
});

/**
 * Element spans of `<Tag>` as JSX only. `useRef<ScrollView>(null)` is a type
 * argument, not an element, and read as one it would open a span that runs to
 * the end of the file.
 */
function jsxSpans(text: string, tag: string): [number, number][] {
  return elementSpans(text, tag).filter(([start]) => !/[\w$.]/.test(text[start - 1] ?? ""));
}

describe("SC 1.3.4 — a text field stays above the keyboard in landscape", () => {
  // In landscape the keyboard takes about half of the window, so a field the
  // keyboard covers is a control the patient cannot see while using it.
  const fieldScrollers = TSX.flatMap((f) => {
    const text = code(f.source);
    return jsxSpans(text, "ScrollView")
      .filter(([start, end]) => /<TextInput\b/.test(text.slice(start, end)))
      .map(([start]) => {
        const from = start + "<ScrollView".length;
        return {
          tag: "ScrollView",
          file: f.name,
          line: text.slice(0, start).split("\n").length,
          props: text.slice(from, endOfOpening(text, from)),
        };
      });
  });

  it("every scroller that holds a text field keeps it above the keyboard", () => {
    // Non-vacuity: phone, OTP, new visit, Doctor Link, the typed intake, the kiosk PIN.
    expect(fieldScrollers.length).toBeGreaterThan(5);
    const bare = fieldScrollers
      .filter((o) => !hasProp(o.props, "automaticallyAdjustKeyboardInsets"))
      .map(where);
    expect(bare).toEqual([]);
  });

  it("a text field outside any scroller sits inside a KeyboardAvoidingView", () => {
    const loose = TSX.flatMap((f) => {
      const text = code(f.source);
      const scrollers = jsxSpans(text, "ScrollView");
      const avoiding = jsxSpans(text, "KeyboardAvoidingView");
      const inside = (spans: [number, number][], at: number) =>
        spans.some(([start, end]) => at >= start && at < end);
      return [...text.matchAll(/<TextInput\b/g)]
        .filter((m) => !inside(scrollers, m.index) && !inside(avoiding, m.index))
        .map((m) => `${f.name}:${text.slice(0, m.index).split("\n").length}`);
    });
    expect(loose).toEqual([]);
  });

  it("the dialogue's bottom stack pins to the keyboard's edge and never outgrows its frame", () => {
    const dialogue = TSX.find((f) => f.name === "src/components/DialogueIntake.tsx")!;
    const text = code(dialogue.source);
    // The KeyboardAvoidingView measures from its own top, and a header sits
    // above it: the offset is the header's height.
    const [avoiding] = readOpenings(text, dialogue.name, ["KeyboardAvoidingView"]);
    expect(propValue(avoiding.props, "keyboardVerticalOffset")).toBe("{headerHeight}");
    expect(text).toMatch(/const headerHeight = useHeaderHeight\(\);/);
    // It lifts its content with PADDING, and an absolutely positioned child
    // ignores its parent's padding (Yoga places it against the border box):
    // pinned in the KeyboardAvoidingView itself, the composer sat behind the
    // keyboard. It is pinned inside a frame that ends where the keyboard begins.
    const frames = jsxSpans(text, "View").filter(([start]) => {
      const from = start + "<View".length;
      return /setFrameHeight\(/.test(text.slice(from, endOfOpening(text, from)));
    });
    expect(frames).toHaveLength(1);
    const [frameStart, frameEnd] = frames[0];
    const stackAt = text.indexOf("styles.bottomStack");
    expect(stackAt > frameStart && stackAt < frameEnd).toBe(true);
    // Capped at that frame, so no control is pushed above the top of it...
    const stack = readOpenings(text, dialogue.name, ["View"]).find((o) =>
      /styles\.bottomStack/.test(o.props),
    )!;
    expect(propValue(stack.props, "style")).toMatch(/maxHeight: frameHeight/);
    // ...and what does not fit scrolls, while the composer stays in view.
    const barAt = text.indexOf("<GlassBar", stackAt);
    const scrollAt = text.indexOf("<ScrollView", barAt);
    const composerAt = text.indexOf("styles.composerRow", barAt);
    expect(scrollAt > barAt && scrollAt < composerAt).toBe(true);
  });

  it("the glass bar yields height to a host that caps it", () => {
    const rules = new Map(
      namedRules(code(TSX.find((f) => f.name === "src/components/GlassBar.tsx")!.source)).map(
        (r) => [r.name, r.body],
      ),
    );
    expect(rules.get("bar")).toMatch(/flexShrink: 1/);
    expect(rules.get("inner")).toMatch(/flexShrink: 1/);
  });

  it("the kiosk's own chrome keeps the safe edges and scrolls rather than push the exit off-screen", () => {
    // KioskGate draws its warning and staff bar OUTSIDE any Screen, under the
    // home indicator and, in landscape, beside the notch.
    const gate = code(TSX.find((f) => f.name === "src/components/KioskGate.tsx")!.source);
    const chrome = readOpenings(gate, "src/components/KioskGate.tsx", ["SafeAreaView"]);
    expect(chrome).toHaveLength(1);
    const edges = stringLiterals(propValue(chrome[0].props, "edges") ?? "");
    expect(edges.sort()).toEqual(["bottom", "left", "right"]);
    const [start, end] = jsxSpans(gate, "SafeAreaView")[0];
    const inside = gate.slice(start, end);
    expect(inside).toMatch(/<ScrollView\b/);
    expect(inside).toContain("styles.idleWarning");
    expect(inside).toContain("styles.staffBar");
  });
});

/* ------------------------------------------------------------------ */
/* Catalog coverage — invariant 5                                      */
/* ------------------------------------------------------------------ */

describe("the a11y strings live in the tr-first catalog", () => {
  const tr = readFileSync(join(SRC, "lib", "i18n", "tr.ts"), "utf8");
  const en = readFileSync(join(SRC, "lib", "i18n", "en.ts"), "utf8");

  it("every a11y.* key referenced in a screen exists in both catalogs", () => {
    const used = new Set<string>();
    for (const f of TSX) {
      for (const m of f.source.matchAll(/"(a11y\.[A-Za-z0-9_.]+)"/g)) {
        used.add(m[1]);
      }
    }
    expect(used.size).toBeGreaterThan(10);
    const missing = [...used].filter((k) => !tr.includes(`"${k}"`) || !en.includes(`"${k}"`));
    expect(missing).toEqual([]);
  });
});

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
import { describe, expect, it } from "vitest";

import { MIN_TAP } from "../src/lib/a11y/target";
import { OTP_LENGTH } from "../src/lib/auth/phone";
import { CTA_MIN_HEIGHT } from "../src/lib/prefs/appearance";
import { buildEnvelopeBody } from "../src/lib/telemetry/envelope";
import { buildCrashReport, type TelemetryIdentity } from "../src/lib/telemetry/scrub";

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
  it("every looping animation is gated on the reduce-motion preference", () => {
    const loops = TSX.filter((f) => /Animated\.loop/.test(f.source));
    expect(loops.length).toBeGreaterThan(0);
    const ungated = loops
      .filter(
        (f) => !/loopingDecorationEnabled/.test(f.source) || !/useReducedMotion/.test(f.source),
      )
      .map((f) => f.name);
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
/* BK28 · SC 3.3.1 Error Identification                                */
/* ------------------------------------------------------------------ */

describe("BK28 / SC 3.3.1 — an error announces itself", () => {
  const withErrors = [
    "src/app/(auth)/phone.tsx",
    "src/app/(auth)/otp.tsx",
    "src/app/(tabs)/visits/new.tsx",
    "src/app/(tabs)/records.tsx",
  ];

  it.each(withErrors)("%s announces its error on BOTH platforms", (name) => {
    const file = TSX.find((f) => f.name === name);
    expect(file, name).toBeDefined();
    // `accessibilityLiveRegion` is @platform android in React Native and
    // `accessibilityRole="alert"` does not substitute on iOS — there is no
    // alert trait and RN posts no announcement for it. A screen that relies
    // on the live region alone is silent under VoiceOver, so both halves
    // are required.
    // Either the literal prop or the conditional form records.tsx needs,
    // because one of its notices is progress rather than an error.
    expect(file!.source, `${name}: android half`).toMatch(/live=(\{[^}]*)?"assertive"/);
    expect(file!.source, `${name}: ios half`).toContain("useLiveAnnouncement(");
  });

  it("AppText maps `live` onto the platform's own announcement props", () => {
    const themed = readFileSync(join(COMPONENTS, "Themed.tsx"), "utf8");
    expect(themed).toContain("accessibilityLiveRegion={live}");
    expect(themed).toContain('"alert"');
  });

  it("an error is never carried by colour alone", () => {
    // Every amber error line must also be announced; the colour is the
    // sighted redundancy, never the signal (02 §8.2, SC 1.4.1).
    // Both spellings: the `color="amber"` prop AND the raw `theme.amber`
    // token, so a warning styled the other way cannot slip past.
    const amberOnly = TSX.filter(
      (f) =>
        /color="amber"|theme\.amber\b/.test(f.source) &&
        !/\blive=|accessibilityLabel/.test(f.source),
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

  it("BK15 / SC 2.3.1 — the only repeating animation is far below 3 Hz", () => {
    const dialogue = TSX.find((f) => f.name === "src/components/DialogueIntake.tsx")!;
    const durations = [...dialogue.source.matchAll(/duration:\s*(\d+)/g)].map((m) => Number(m[1]));
    expect(durations.length).toBeGreaterThan(0);
    // One full cycle is two of these; 3 Hz would need a 167 ms half-cycle.
    expect(Math.min(...durations)).toBeGreaterThan(167);
  });

  it("BK13 / SC 2.2.1 — the only timer is the resend cooldown, and it takes nothing away", () => {
    const timed = TSX.filter((f) => /setTimeout|setInterval/.test(f.source)).map((f) => f.name);
    expect(timed).toEqual(["src/app/(auth)/otp.tsx"]);
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

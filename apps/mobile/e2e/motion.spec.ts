/**
 * INT-331 (MOTION-2; docs/design/motion/motion-verification.md §3 S-2,
 * §4 MOTION-2) — Reanimated follows the app's reduce-motion policy, never its
 * own.
 *
 * Reanimated ships two fail-open paths the app's policy cannot see:
 *
 * - its own reduce-motion hook reads the OS setting only, so a patient who
 *   turned motion off in the app's Görünüm screen would still see movement;
 * - its "follow the system" mode is captured ONCE, when the module loads
 *   (react-native-reanimated/src/ReducedMotion.ts), and never sees the in-app
 *   switch or a later change in Settings.
 *
 * The bridge is one `ReducedMotionConfig` at the root, driven by the app's
 * `useReducedMotion()`, so every Reanimated animation takes the combined,
 * fail-closed answer and follows it live. React Native has no DOM here, so
 * these are source guards; the store's behaviour is proved in
 * src/lib/motion/policyStore.test.ts.
 *
 * The literals the MOTION-2 guards forbid, and the samples that prove each
 * detector is not vacuous, are assembled from parts, so the code below never
 * spells what it scans for.
 *
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

import { animatable, animatedStyleKeys, code, literalDurations, loops } from "./motionSource";
import {
  RED_CONTRACT,
  WAITS,
  arrowBody,
  firstPaintViolations,
  isRedSurface,
  specifiers,
} from "./redSurface";

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

function file(name: string): string {
  const found = TREE.find((f) => f.name === name);
  expect(found, `${name} is missing`).toBeDefined();
  return found!.source;
}

const REANIMATED = ["react-native", "reanimated"].join("-");
const HOOK = ["useReduced", "Motion"].join("");
const ENUM = ["Reduce", "Motion"].join("");
const FOLLOW_OS = ["Sys", "tem"].join("");

/** `import { … } from "<module>"` and `export { … } from "<module>"`, with the clause. */
const FROM = /\b(?:import|export)\s+(?:type\s+)?([^;]*?)\s*\bfrom\s*["']([^"']+)["']/g;

function clausesFrom(source: string, module: string): string[] {
  return [...source.matchAll(FROM)]
    .filter((m) => m[2] === module || m[2].startsWith(`${module}/`))
    .map((m) => m[1]);
}

/** Every way a file could reach Reanimated's own reduce-motion hook. */
function takesReanimatedHook(source: string): boolean {
  const hook = new RegExp(`\\b${HOOK}\\b`);
  const named = clausesFrom(source, REANIMATED).some((clause) => hook.test(clause));
  const required = new RegExp(
    `\\{[^}]*\\b${HOOK}\\b[^}]*\\}\\s*=\\s*require\\(\\s*["']${REANIMATED}`,
  ).test(source);
  // A member access through a namespace or default import; the app's own
  // hook is only ever called bare.
  const member = new RegExp(`\\.\\s*${HOOK}\\b`).test(source);
  return named || required || member;
}

/** `ReduceMotion.System`, however it is spelled. */
const FOLLOWS_OS = new RegExp(
  `\\b${ENUM}\\s*(?:\\?\\.|\\.)\\s*${FOLLOW_OS}\\b|\\b${ENUM}\\s*\\[\\s*["'\`]${FOLLOW_OS}["'\`]\\s*\\]`,
);

describe("MOTION-2 — Reanimated reads the app's reduce-motion policy", () => {
  it("nothing imports useReducedMotion from react-native-reanimated", () => {
    // Non-vacuity: the detector catches each shape it claims to.
    const named = `import { withTiming, ${HOOK} } from "${REANIMATED}";`;
    const required = `const { ${HOOK} } = require("${REANIMATED}");`;
    const member = `import Animated from "${REANIMATED}";\nconst r = Animated.${HOOK}();`;
    const reexport = `export { ${HOOK} } from "${REANIMATED}";`;
    for (const sample of [named, required, member, reexport]) {
      expect(takesReanimatedHook(sample), sample).toBe(true);
    }
    expect(takesReanimatedHook(`import { ${HOOK} } from "@/lib/a11y/prefs";`)).toBe(false);

    const offenders = TREE.filter((f) => takesReanimatedHook(f.source)).map((f) => f.name);
    expect(offenders).toEqual([]);
  });

  it("no ReduceMotion.System anywhere", () => {
    for (const sample of [
      `${ENUM}.${FOLLOW_OS}`,
      `${ENUM} . ${FOLLOW_OS}`,
      `${ENUM}["${FOLLOW_OS}"]`,
      `${ENUM}?.${FOLLOW_OS}`,
    ]) {
      expect(FOLLOWS_OS.test(sample), sample).toBe(true);
    }
    expect(FOLLOWS_OS.test(`${ENUM}.Always`)).toBe(false);

    const offenders = TREE.filter((f) => FOLLOWS_OS.test(f.source)).map((f) => f.name);
    expect(offenders).toEqual([]);
  });

  it("the root mounts ReducedMotionConfig from the app policy", () => {
    const layout = file("src/app/_layout.tsx");

    // Both names come from Reanimated itself.
    const reanimatedClause = clausesFrom(layout, REANIMATED).join(",");
    expect(reanimatedClause).toMatch(/\bReducedMotionConfig\b/);
    expect(reanimatedClause).toMatch(new RegExp(`\\b${ENUM}\\b`));

    // The mode is the app's answer, both ways, and nothing else.
    const mount = new RegExp(
      `<ReducedMotionConfig\\s+mode=\\{\\s*(\\w+)\\s*\\?\\s*${ENUM}\\.Always\\s*:\\s*${ENUM}\\.Never\\s*\\}\\s*/>`,
    ).exec(layout);
    expect(mount, "ReducedMotionConfig mode={reduce ? Always : Never}").not.toBeNull();
    const flag = mount![1];

    // …and that answer is the app's hook, from the app's module.
    const hookClause = clausesFrom(layout, "@/lib/a11y/prefs").join(",");
    expect(hookClause).toMatch(new RegExp(`\\b${HOOK}\\b`));
    expect(layout).toMatch(new RegExp(`const\\s+${flag}\\s*=\\s*${HOOK}\\(\\)`));

    // It renders under AppearanceProvider, or the in-app switch never
    // reaches it: the component that mounts it is itself mounted inside the
    // provider, by a different component.
    const components = [...layout.matchAll(/function\s+(\w+)\s*\(/g)].filter(
      (m) => (m.index ?? 0) < mount!.index,
    );
    const host = components[components.length - 1]?.[1];
    expect(host, "the component that mounts ReducedMotionConfig").toBeDefined();
    const provider = /<AppearanceProvider>([\s\S]*?)<\/AppearanceProvider>/.exec(layout);
    expect(provider, "the root renders AppearanceProvider").not.toBeNull();
    expect(provider![1]).toMatch(new RegExp(`<${host}\\s*/>`));

    // One bridge: a second config deeper in the tree would override it.
    const mounts = APP_SOURCE.filter((f) => /<ReducedMotionConfig\b/.test(f.source)).map(
      (f) => f.name,
    );
    expect(mounts).toEqual(["src/app/_layout.tsx"]);
  });

  it("the app hook reads the one store, and only the native source asks the OS", () => {
    // One OS read and one listener whatever the consumer count: one store in
    // the whole app, and nothing else calls the OS for this answer.
    const created = /(?<!function\s+)\bcreateReduceMotionStore\(/g;
    const stores = APP_SOURCE.flatMap((f) => [...f.source.matchAll(created)].map(() => f.name));
    expect(stores).toEqual(["src/lib/a11y/prefs.ts"]);

    const askers = APP_SOURCE.filter((f) =>
      /\bisReduceMotionEnabled\b|["']reduceMotionChanged["']/.test(f.source),
    ).map((f) => f.name);
    expect(askers).toEqual(["src/lib/motion/native/reduceMotionSource.ts"]);

    // The hook subscribes to the store; it no longer starts from a local
    // `false` that animates until the OS answers.
    const prefs = file("src/lib/a11y/prefs.ts");
    const body = new RegExp(`export function ${HOOK}\\(\\): boolean \\{([\\s\\S]*?)\\n\\}`).exec(
      prefs,
    );
    expect(body, `${HOOK} in src/lib/a11y/prefs.ts`).not.toBeNull();
    expect(body![1]).toContain("useSyncExternalStore(");
    expect(body![1]).not.toContain("useState(");

    // The native adapter stays off every static import path, so nothing a
    // node test imports can pull react-native in through it.
    const staticImporters = APP_SOURCE.filter((f) =>
      [...f.source.matchAll(FROM)].some((m) => /native\/reduceMotionSource$/.test(m[2])),
    ).map((f) => f.name);
    expect(staticImporters).toEqual([]);
    expect(prefs).toMatch(/import\(\s*["']@\/lib\/motion\/native\/reduceMotionSource["']\s*\)/);
  });
});

/* ------------------------------------------------------------------ */
/* INT-335 (MOTION-6) — Reanimated hygiene, before its first consumer  */
/* ------------------------------------------------------------------ */

/*
 * docs/design/motion/motion-verification.md §4 MOTION-6, with the rules of
 * intake-voice-motion-spec.md §3.2 P0 and §3.4: animate opacity and transform
 * only, never a layout property; no layout transition, no spring, no hop to
 * the RN runtime from a worklet; a CSS transition takes its timing from the
 * one fade policy. These guards land while nothing in src uses Reanimated to
 * animate, so the first consumer meets them instead of setting precedent.
 */

/** Everything under src/, tests included: "in src" means all of it. */
const SRC_TREE = TREE.filter((f) => f.name.startsWith("src/"));

const FADE_MODULE = "src/lib/motion/fade.ts";

/** Forbidden APIs, spelled from parts so this file never names them whole. */
const LINEAR = ["Linear", "Transition"].join("");
const SPRING = ["with", "Spring"].join("");
const TO_JS = ["run", "On", "JS"].join("");
const TO_RN = ["schedule", "On", "RN"].join("");
const LAYOUT_ANIMATION = ["Layout", "Animation"].join("");

/** What each forbidden API looks like in code, by the name the spec gives it. */
function forbiddenApis(source: string): string[] {
  const text = code(source);
  const checks: readonly (readonly [string, boolean])[] = [
    [LINEAR, new RegExp(`\\b${LINEAR}\\b`).test(text)],
    [
      "layout transition",
      /\b(?:Fading|Sequenced|Jumping|Curved|EntryExit)Transition\b/.test(text) ||
        /\slayout\s*=\s*\{/.test(text) ||
        /\bLayout\s*\.\s*\w+\s*\(/.test(text) ||
        clausesFrom(text, REANIMATED).some((clause) => /\bLayout\b/.test(clause)),
    ],
    // React Native's own layout animation; Reanimated's LayoutAnimationConfig
    // (skipEntering on a first mount, MOTION-8) is a different name.
    [LAYOUT_ANIMATION, new RegExp(`\\b${LAYOUT_ANIMATION}\\b`).test(text)],
    [
      SPRING,
      new RegExp(`\\b${SPRING}\\b`).test(text) ||
        /\bAnimated\s*\.\s*spring\b/.test(text) ||
        /\.\s*springify\s*\(/.test(text),
    ],
    [TO_JS, new RegExp(`\\b(?:${TO_JS}|${TO_RN})\\b`).test(text)],
  ];
  return checks.filter(([, hit]) => hit).map(([name]) => name);
}

/** Any Reanimated CSS transition key, shorthand included. */
const CSS_TRANSITION = /\btransition(?:Property|Duration|TimingFunction|Delay|Behavior)?\??\s*:/;

describe("MOTION-6 — Reanimated hygiene gates", () => {
  it("no file that loops carries a literal duration", () => {
    // Non-vacuity: every way to write a period down is caught, and the two
    // ways to read one (a token, a policy result) are not.
    const cases: readonly (readonly [string, readonly string[]])[] = [
      ["Animated.loop(Animated.timing(v, { toValue: 0.3, duration: 700 }))", ["700"]],
      ["v.value = withRepeat(withTiming(0.3, { duration: 700 }), -1, true)", ["700"]],
      ["const HALF = 700;\nv.value = withRepeat(withTiming(1, { duration: HALF }), -1)", ["HALF"]],
      ['const s = { animationDuration: "1.4s", animationIterationCount: "infinite" }', ['"1.4s"']],
      ["withRepeat(x, -1);\nconst e = FadeIn.duration(700)", ["700"]],
      ["withRepeat(withTiming(0, { duration: motion.loop.pulsePeriodMs / 2 }), -1, true)", []],
      ["withRepeat(withTiming(0, { duration: t.durationMs }), -1, true)", []],
    ];
    for (const [sample, literal] of cases) {
      expect(loops(sample), sample).toBe(true);
      expect(literalDurations(sample), sample).toEqual(literal);
    }

    const looping = APP_SOURCE.filter((f) => loops(f.source));
    expect(looping.map((f) => f.name)).toContain("src/components/DialogueIntake.tsx");
    const offenders = looping.flatMap((f) =>
      literalDurations(f.source).map((value) => `${f.name}: ${value}`),
    );
    expect(offenders).toEqual([]);
  });

  it("app-authored animated styles touch only opacity and transform", () => {
    const refused: readonly (readonly [string, string])[] = [
      ["const s = useAnimatedStyle(() => ({ opacity: o.value, height: h.value }));", "height"],
      ['const s = useAnimatedStyle(() => { "worklet"; return { width: w.value }; });', "width"],
      [
        "const a = useRef(new Animated.Value(0)).current;\n<Animated.View style={[x, { marginTop: a }]} />",
        "marginTop",
      ],
      [
        "const a = new Animated.Value(0);\nconst tint = a.interpolate(r);\n<Animated.View style={{ backgroundColor: tint }} />",
        "backgroundColor",
      ],
      ["const top = useSharedValue(0);\n<Animated.View style={{ top }} />", "top"],
      ["const s = { animationName: { from: { width: 0 }, to: { width: 9 } } };", "width"],
      ["const k = new Keyframe({ 0: { height: 0 }, 100: { height: 9 } });", "height"],
      ["const e = () => ({ initialValues: { height: 0 }, animations: { opacity: o } });", "height"],
    ];
    for (const [sample, key] of refused) {
      const keys = animatedStyleKeys(sample).map((k) => k.key);
      expect(keys, sample).toContain(key);
      expect(animatable(key), key).toBe(false);
    }
    const allowed = [
      "const s = useAnimatedStyle(() => ({ opacity: o.value, transform: [{ scale: s.value }] }));",
      "const opacity = useRef(new Animated.Value(1)).current;\n<Animated.View style={[a, { backgroundColor: c, opacity }]} />",
      "const x = useSharedValue(0);\n<Animated.View style={{ transform: [{ translateX: x }] }} />",
    ];
    for (const sample of allowed) {
      const keys = animatedStyleKeys(sample).map((k) => k.key);
      expect(keys.length, sample).toBeGreaterThan(0);
      expect(
        keys.filter((k) => !animatable(k)),
        sample,
      ).toEqual([]);
    }

    const found = APP_SOURCE.flatMap((f) =>
      animatedStyleKeys(f.source).map((k) => ({ ...k, file: f.name })),
    );
    // The dialogue's pulse drives opacity today; a silent zero would make
    // this vacuous.
    expect(found.length).toBeGreaterThan(0);
    const offenders = found
      .filter((k) => !animatable(k.key))
      .map((k) => `${k.file} ${k.site} ${k.key}`);
    expect(offenders).toEqual([]);
  });

  it("no LinearTransition, Layout animation, withSpring or runOnJS in src", () => {
    const samples: readonly (readonly [string, string])[] = [
      [`<Animated.View layout={${LINEAR}} />`, LINEAR],
      ["<Animated.View layout={FadingTransition.duration(d)} />", "layout transition"],
      [`import { Layout } from "${REANIMATED}";`, "layout transition"],
      [`${LAYOUT_ANIMATION}.configureNext(p);`, LAYOUT_ANIMATION],
      [`import { ${SPRING} as bounce } from "${REANIMATED}";`, SPRING],
      ["Animated.spring(v, { toValue: 1 }).start();", SPRING],
      ["const e = FadeIn.springify();", SPRING],
      [`${TO_JS}(done)();`, TO_JS],
      [`${TO_RN}(done);`, TO_JS],
    ];
    for (const [sample, name] of samples) {
      expect(forbiddenApis(sample), sample).toContain(name);
    }
    // Reanimated's LayoutAnimationConfig, a comment, and a plain fade pass.
    expect(
      forbiddenApis(`import { ${LAYOUT_ANIMATION}Config, FadeIn } from "${REANIMATED}";`),
    ).toEqual([]);
    expect(forbiddenApis(`// never ${SPRING} or ${TO_JS} here\nconst x = 1;`)).toEqual([]);

    expect(SRC_TREE.length).toBeGreaterThan(100);
    const offenders = SRC_TREE.flatMap((f) =>
      forbiddenApis(f.source).map((name) => `${f.name}: ${name}`),
    );
    expect(offenders).toEqual([]);
  });

  it("Reanimated CSS transitions take their duration from cssFade", () => {
    for (const sample of [
      "const s = { transitionProperty: p, transitionDuration: 120 };",
      'const s = { transition: "opacity 120ms ease-out" };',
      '<Animated.View style={{ transitionTimingFunction: "ease-out" }} />',
    ]) {
      expect(CSS_TRANSITION.test(code(sample)), sample).toBe(true);
    }
    // The navigators' `transitionSpec` and a comment are not CSS transitions.
    expect(CSS_TRANSITION.test(code("const o = { transitionSpec: s };"))).toBe(false);
    expect(CSS_TRANSITION.test(code("// the tab transition: spread it"))).toBe(false);

    // The one place a CSS transition is written, and its duration is read
    // from the tokens there, never written down.
    const fade = file(FADE_MODULE);
    expect(CSS_TRANSITION.test(code(fade))).toBe(true);
    expect(code(fade)).toMatch(/\bmotion\.duration\.fade\b/);
    expect(literalDurations(fade)).toEqual([]);

    const writers = APP_SOURCE.filter(
      (f) => f.name !== FADE_MODULE && CSS_TRANSITION.test(code(f.source)),
    ).map((f) => f.name);
    expect(writers).toEqual([]);
  });
});

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
  // Empty since INT-422: the hairline's resting 0.9 went when it took the
  // separator token.
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

// ---------------------------------------------------------------------------
// MOTION-4 — the RED path paints first, and nothing on it moves
// ---------------------------------------------------------------------------

/*
 * INT-333 (docs/design/motion/motion-verification.md §4 MOTION-4, §3 S-1;
 * ADR-033 §5, Proposed). The pure contract is src/lib/motion/red.ts and its
 * suite. What this adds is the source half: every file on the RED path is
 * named here, and none of them reaches an animation, a haptic, a Modal or the
 * router. The list is exact, so the RED UI's files (INT-135) are found by the
 * detector and must be added to it, which puts them under the same scan.
 */

/** Every RED surface file on main. Grow it only with a file that paints or carries RED. */
const RED_SURFACE_FILES: readonly string[] = [
  "src/lib/livekit/events.ts",
  "src/lib/livekit/index.ts",
  "src/lib/livekit/red.ts",
  "src/lib/livekit/session.ts",
  "src/lib/livekit/types.ts",
  "src/lib/motion/red.ts",
];

describe("MOTION-4 — the RED path paints first, with no motion", () => {
  it("RED surface files are pinned and use no animation API, no expo-haptics, no Modal and no router call on the first-paint path", () => {
    // Non-vacuity: each route into the RED path is detected…
    for (const shape of [
      'import { resolveRed } from "./red";',
      'import { redFirstPaint } from "@/lib/motion/red";',
      'import type { RedPresentation } from "@/lib/livekit";',
      'if (event.type === "red") { show(event.presentation); }',
      "<View style={{ backgroundColor: colors.light.emergencySoft }} />",
    ]) {
      expect(isRedSurface(shape), shape).toBe(true);
    }
    expect(isRedSurface('import { fadeSpec } from "./fade";\nconst c = colors.light.ink;')).toBe(
      false,
    );
    // …and each thing a first paint must not touch is caught.
    const reanimated = ["react-native", "reanimated"].join("-");
    const haptics = ["expo", "haptics"].join("-");
    const samples: readonly (readonly [string, string])[] = [
      [`import { FadeIn } from "${reanimated}";`, "animation API"],
      ["Animated.timing(v, t).start();", "animation API"],
      ["<Animated.View entering={enteringFor(s)} />", "animation API"],
      [`const H = await import("${haptics}");`, "haptics"],
      ["Haptics.notificationAsync(t);", "haptics"],
      ["<Modal visible transparent />", "Modal"],
      ["router.push(`/visits/${id}/emergency`);", "router call"],
      [`import { useRouter } from "${["expo", "router"].join("-")}";`, "router call"],
    ];
    for (const [shape, name] of samples) {
      expect(firstPaintViolations(shape), shape).toContain(name);
    }
    expect(
      firstPaintViolations("// Animated, Modal and router are named only here\nconst x = 1;"),
    ).toEqual([]);

    // The pin is exact: a RED file nobody named fails, and so does a name
    // that no longer carries RED.
    const contract: readonly string[] = RED_CONTRACT;
    const found = APP_SOURCE.filter((f) => contract.includes(f.name) || isRedSurface(f.source)).map(
      (f) => f.name,
    );
    expect(found).toEqual([...RED_SURFACE_FILES].sort());
    for (const name of contract) {
      expect(RED_SURFACE_FILES).toContain(name);
    }

    const offenders = RED_SURFACE_FILES.flatMap((name) =>
      firstPaintViolations(file(name)).map((what) => `${name}: ${what}`),
    );
    expect(offenders).toEqual([]);
  });

  it("RED render is not awaited on audio, haptics, navigation or the arbiter", () => {
    // Non-vacuity: every way of waiting is caught, and a plain call is not.
    for (const shape of [
      "await adapter.stop();",
      "void speak(x).then(() => emit(e));",
      "setTimeout(() => emit(e), 0);",
      "await sleep(10);",
      "requestAnimationFrame(() => emit(e));",
    ]) {
      expect(WAITS.test(shape), shape).toBe(true);
    }
    expect(WAITS.test('const p = resolveRed(t, c);\nemit({ type: "red", presentation: p });')).toBe(
      false,
    );

    // The data-channel handler decodes, resolves and emits in one synchronous
    // pass: it waits on nothing and calls no media, haptic, route or arbiter.
    const session = file("src/lib/livekit/session.ts");
    const handler = arrowBody(session, "handleData");
    expect(handler, "handleData in src/lib/livekit/session.ts").not.toBeNull();
    expect(handler!).toMatch(/\bdecodeRedTrigger\(/);
    expect(handler!).toMatch(/\bresolveRed\(/);
    expect(handler!).toMatch(/\bemit\(\s*\{\s*type:\s*"red"/);
    expect(WAITS.test(handler!)).toBe(false);
    expect(handler!).not.toMatch(/\badapter\s*\.|\bdeps\s*\.\s*(?!redScripts\b)\w+\s*\(/);
    expect(handler!).not.toMatch(/\b(?:arbitrate|hapticFor|router|navigation)\b/);

    // The motion contract that sizes the first paint imports nothing that
    // could make it wait: only the RED types.
    expect(specifiers(file("src/lib/motion/red.ts"))).toEqual(["../livekit/red"]);
  });
});

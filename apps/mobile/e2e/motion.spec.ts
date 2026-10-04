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

/** ADR-038 A1 (INT-462): the bubble entrance, allowed a spring. */
const BUBBLE_ENTERING = "src/lib/motion/native/bubbleEntering.ts";
/** ADR-038 A3 (INT-473): the detent sheet, the second module allowed a spring. */
const SHEET_MOTION = "src/lib/motion/native/sheetMotion.ts";
/**
 * ADR-037 P1 (INT-492): the press scale, the third. ADR-037's guard table
 * names this change ("admits that one module, and a new guard pins its
 * numbers"), and ADR-038's consequences count P1's press module among the
 * springs it expected.
 */
const PRESS_SCALE_NATIVE = "src/lib/motion/native/pressScale.ts";
const SPRING_ALLOWED: readonly string[] = [BUBBLE_ENTERING, SHEET_MOTION, PRESS_SCALE_NATIVE];

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
    // INT-336: the orb carries the dialogue's loops; the pulse it replaced is gone.
    expect(looping.map((f) => f.name)).toContain("src/components/PresenceOrb.tsx");
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
    // The presence orb drives opacity (INT-336); a silent zero would make
    // this vacuous.
    expect(found.length).toBeGreaterThan(0);
    expect(found.map((k) => k.file)).toContain("src/components/PresenceOrb.tsx");
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
      forbiddenApis(f.source)
        // ADR-038 A1 and A3: the bubble entrance and the sheet may spring.
        .filter((name) => !(name === SPRING && SPRING_ALLOWED.includes(f.name)))
        .map((name) => `${f.name}: ${name}`),
    );
    expect(offenders).toEqual([]);
  });

  it("ADR-038 A1: the bubble entrance springs, and every number it uses is the ADR's", () => {
    // The allow-list may only shrink after ADR-037 P1 and ADR-038: A1's
    // bubble, A3's sheet and P1's press scale (INT-492).
    expect(SPRING_ALLOWED).toEqual([BUBBLE_ENTERING, SHEET_MOTION, PRESS_SCALE_NATIVE]);
    const native = file(BUBBLE_ENTERING);
    expect(forbiddenApis(native)).toEqual([SPRING]);
    // The rise and the spring are read from the pure module the ADR pins
    // (lib/motion/bubbles.test.ts), never written here.
    expect(code(native)).toMatch(/import \{[^}]*\bBUBBLE_SPRING\b[^}]*\} from "\.\.\/bubbles"/);
    // Opacity runs from 0 to 1 and the rise settles at 0; any other number
    // would be a timing or a distance of the module's own.
    const numbers = [...code(native).matchAll(/(?<![\w.])\d+(?:\.\d+)?(?![\w.])/g)].map(
      (m) => m[0],
    );
    expect(numbers.filter((n) => n !== "0" && n !== "1")).toEqual([]);
    // Only translateY and opacity move: no scale, no other transform.
    expect(code(native)).not.toMatch(/\bscale[XY]?\b|\btranslateX\b|\brotate\b/);
    // Nothing else in src springs: the near miss is any third module.
    const springing = SRC_TREE.filter((f) => forbiddenApis(f.source).includes(SPRING)).map(
      (f) => f.name,
    );
    expect(springing.sort()).toEqual([...SPRING_ALLOWED].sort());
  });

  it("ADR-038 A3: the sheet's spring is A1's, read from the pure module, with no number of its own", () => {
    const native = file(SHEET_MOTION);
    expect(forbiddenApis(native)).toEqual([SPRING]);
    expect(code(native)).toMatch(/import \{[^}]*\bSHEET_SPRING\b[^}]*\} from "\.\.\/sheet"/);
    const numbers = [...code(native).matchAll(/(?<![\w.])\d+(?:\.\d+)?(?![\w.])/g)].map(
      (m) => m[0],
    );
    expect(numbers.filter((n) => n !== "0")).toEqual([]);
    // Only translateY and opacity move: no scale, no other transform.
    expect(code(native)).not.toMatch(/\bscale[XY]?\b|\btranslateX\b|\brotate\b/);
  });

  it("ADR-037 P1: the press scale springs on A1's spring, to 0.97, with no number of its own", () => {
    const native = file(PRESS_SCALE_NATIVE);
    expect(forbiddenApis(native)).toEqual([SPRING]);
    // The target and the spring come from the pure module the ADR pins
    // (lib/motion/micro.test.ts); the only number here is the rest scale.
    expect(code(native)).toMatch(
      /import (?:type )?\{[^}]*\bPressScale\b[^}]*\} from "\.\.\/micro"/,
    );
    const numbers = [...code(native).matchAll(/(?<![\w.])\d+(?:\.\d+)?(?![\w.])/g)].map(
      (m) => m[0],
    );
    expect(numbers.filter((n) => n !== "1")).toEqual([]);
    // Only the scale moves: no translate, no rotation, no opacity tween (the
    // press keeps its instant opacity step from motion.press).
    expect(code(native)).not.toMatch(/\btranslate[XY]\b|\brotate\b|\bopacity\b/);
    const micro = code(file("src/lib/motion/micro.ts"));
    expect(micro).toMatch(/PRESS_SPRING = BUBBLE_SPRING/);
    expect(micro).toMatch(/PRESS_SCALE = 0\.97/);
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
    // send, whose 0.4 was normalised to the token's 0.5). The grouped-list
    // rows (ListRow, SwitchRow) left this scan in INT-451: they show a press
    // with the `rowPressFill` highlight instead of a dim, which
    // e2e/interactionPatterns.spec.ts holds. A row that dims again comes back
    // here and must read the token.
    expect(sites.length).toBeGreaterThanOrEqual(10);
    expect([...new Set(sites.map((s) => s.name))]).toEqual(
      expect.arrayContaining([
        "src/components/DialogueIntake.tsx",
        "src/components/SectionPanel.tsx",
        "src/components/Segmented.tsx",
        "src/components/Themed.tsx",
        "src/components/VisitCalendar.tsx",
      ]),
    );
    const disabled = sites
      .filter((s) => /\bmotion\.press\.disabledOpacity\b/.test(s.value))
      .map((s) => s.name);
    expect(disabled).toEqual(["src/components/Themed.tsx", "src/components/Themed.tsx"]);
    // INT-466: the composer's control and the turn actions moved into the
    // stage controls, which dim a disabled control with the token too (as a
    // static style, so the press-callback scan above does not list them).
    const stage = APP_SOURCE.find((f) => f.name === "src/components/stage/StageControls.tsx");
    expect(stage?.source.match(/opacity: motion\.press\.disabledOpacity/g)).toHaveLength(2);
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
  // INT-414: the delivery composer hands a RED script through bare, in the
  // `red` delivery context — it is on the RED path, so it is held here too.
  "src/lib/dialogue/delivery.ts",
  "src/lib/livekit/events.ts",
  "src/lib/livekit/index.ts",
  "src/lib/livekit/red.ts",
  "src/lib/livekit/session.ts",
  "src/lib/livekit/types.ts",
  // INT-336: the orb's policy reads a RED's yield (unmount, idle, unchanged).
  "src/lib/motion/orb.ts",
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

// ---------------------------------------------------------------------------
// MOTION-7 — one presence orb carries the dialogue's state
// ---------------------------------------------------------------------------

/*
 * INT-336 (docs/design/motion/motion-verification.md §4 MOTION-7; ADR-033 Q5,
 * open, so opacity-only). The policy is src/lib/motion/orb.ts and its suite;
 * these guards hold the wiring: the dialogue draws no spinner and no loop of
 * its own, the orb's state comes only from the policy, the orb is decoration,
 * nothing waits on it, and the level is sampled outside every screen and
 * component. Every name this block needs is declared inside it, so other
 * blocks appended to this file cannot collide with it.
 */

describe("MOTION-7 — one presence orb carries the dialogue's state", () => {
  const DIALOGUE = "src/components/DialogueIntake.tsx";
  const ORB = "src/components/PresenceOrb.tsx";
  const POLICY = "src/lib/motion/orb.ts";
  const SAMPLER = "src/lib/motion/native/useLevelSampler.ts";
  const SPINNER = ["Activity", "Indicator"].join("");

  /** Every JSX opening `<Name …>` in `source`, with its props text up to the tag's own `>`. */
  function openings(source: string, name: string): string[] {
    const text = code(source);
    return [...text.matchAll(new RegExp(`<${name}\\b`, "g"))].map((m) => {
      const from = m.index + m[0].length;
      let depth = 0;
      let end = from;
      for (; end < text.length; end += 1) {
        const ch = text[end];
        if (ch === "{") depth += 1;
        else if (ch === "}") depth -= 1;
        else if (ch === ">" && depth === 0) break;
      }
      return text.slice(from, end);
    });
  }

  /** The argument count of every call to `callee` in `source`. */
  function arities(source: string, callee: string): number[] {
    const text = code(source);
    return [...text.matchAll(new RegExp(`\\b${callee}\\s*\\(`, "g"))].map((m) => {
      let depth = 0;
      let commas = 0;
      let empty = true;
      for (let i = m.index + m[0].length; i < text.length; i += 1) {
        const ch = text[i];
        if (ch === "(" || ch === "[" || ch === "{") {
          depth += 1;
        } else if (ch === ")" || ch === "]" || ch === "}") {
          if (depth === 0) break;
          depth -= 1;
        } else if (depth === 0 && ch === ",") {
          commas += 1;
        }
        if (!/\s/.test(ch)) empty = false;
      }
      return empty ? 0 : commas + 1;
    });
  }

  it("the dialogue has no ActivityIndicator and no core Animated loop", () => {
    // Non-vacuity: both shapes are seen when present.
    expect(new RegExp(`\\b${SPINNER}\\b`).test(`<${SPINNER} size="small" />`)).toBe(true);
    expect(loops("Animated.loop(Animated.timing(v, t)).start();")).toBe(true);

    const dialogue = code(file(DIALOGUE));
    expect(dialogue).not.toMatch(new RegExp(`\\b${SPINNER}\\b`));
    expect(loops(dialogue)).toBe(false);
    expect(dialogue).not.toMatch(/\bAnimated\s*\.\s*(?:loop|timing|sequence)\b/);
    // The orb is what it shows instead.
    expect(openings(file(DIALOGUE), "PresenceOrb")).toHaveLength(1);
  });

  it("PresenceOrb takes its state only from orbStateFor", () => {
    const [props] = openings(file(DIALOGUE), "PresenceOrb");
    expect(props).toMatch(/\bstate=\{\s*orbState\s*\}/);
    expect(code(file(DIALOGUE))).toMatch(/const\s+orbState\s*=\s*orbStateFor\(/);
    // The orb itself decides no state: it reads no turn, lane or RED.
    const orb = code(file(ORB));
    expect(orb).not.toMatch(/\bturn\b|\bphase\b|\bplaying\b|\bvoiceMuted\b|\bred\b/);
    expect(orb).toMatch(/\borbVisual\(/);
    expect(orb).toMatch(/\borbTransition\(/);
  });

  it("the orb writes no number of its own: periods are motion.loop tokens, durations are policy results", () => {
    // BK15 and the MOTION-6 scan read `duration:` values; a helper that
    // returns a literal period would pass both, so the orb is held to the
    // stronger rule its header states. The numbers left are structural: a
    // shared value's start (0), a full period halved (2), and withRepeat's
    // "forever" (-1).
    const STRUCTURAL = new Set(["0", "2", "-1"]);
    const numbers = (source: string): string[] =>
      [...code(source).matchAll(/(?<![\w$.])-?\d+(?:\.\d+)?(?![\w$])/g)].map((m) => m[0]);
    // Non-vacuity: a literal period in a helper is seen; the structural ones pass.
    expect(numbers("function half() { return 2000; }")).toEqual(["2000"]);
    expect(numbers("withRepeat(withTiming(0, b), -1, true); x / 2;")).toEqual(["0", "-1", "2"]);

    const orb = file(ORB);
    expect(numbers(orb).filter((n) => !STRUCTURAL.has(n))).toEqual([]);
    for (const kind of ["breathePeriodMs", "speakPeriodMs", "shimmerPeriodMs"]) {
      expect(code(orb), kind).toMatch(new RegExp(`\\bmotion\\.loop\\.${kind}\\s*/\\s*2\\b`));
    }
  });

  it("the orb is hidden from the accessibility tree and is not pressable", () => {
    const orb = code(file(ORB));
    expect(orb).toMatch(/\baccessibilityElementsHidden\b/);
    expect(orb).toMatch(/importantForAccessibility="no-hide-descendants"/);
    expect(orb).toMatch(/pointerEvents="none"/);
    expect(orb).not.toMatch(/\bPressable\b|\bTouchable\w*|\bonPress\b|\baccessibilityRole\b/);
    // It adds no live region, and the dialogue keeps exactly one barge-in
    // control (e2e/a11y.spec.ts pins both on the dialogue itself).
    expect(orb).not.toMatch(/\baccessibilityLiveRegion\b|\bannounceForAccessibility\b/);
  });

  it("the level sampler lives under src/lib, never in a screen or component", () => {
    const TIMER = /\bset(?:Interval|Timeout)\s*\(/;
    expect(TIMER.test("const t = setInterval(tick, ms);")).toBe(true);
    const sampler = code(file(SAMPLER));
    expect(sampler).toMatch(TIMER);
    // It writes one shared value and never React state: zero renders per sample.
    expect(sampler).not.toMatch(/\buseState\b|\buseReducer\b|\bsetState\b|\bdispatch\(/);
    expect(sampler).toMatch(/\.set\(/);
    // Its rate is the policy's, never a number of its own.
    expect(literalDurations(sampler)).toEqual([]);
    expect(sampler).toMatch(/\bplan\.intervalMs\b/);
    // Neither the orb nor the dialogue owns a timer.
    for (const name of [ORB, DIALOGUE]) {
      expect(code(file(name)), name).not.toMatch(TIMER);
    }
  });

  it("nothing waits on the orb: it reports nothing back, and its policy reaches no device module", () => {
    // Non-vacuity: a completion callback and a callback prop are both seen.
    expect(arities("v.set(withTiming(1, t, (done) => next()));", "withTiming")).toEqual([3]);
    expect(arities("v.set(withTiming(1, { duration: d }));", "withTiming")).toEqual([2]);
    expect("<PresenceOrb state={s} onSettled={go} />").toMatch(/\bon[A-Z]\w*=/);

    // No animation of the orb carries a completion callback, so no turn,
    // commit or navigation can be chained to one (ADR-033 §2, Proposed: no
    // app logic waits on an animation). withRepeat's third argument is its
    // `reverse` flag; a fourth would be the callback.
    const orb = file(ORB);
    const timings = arities(orb, "withTiming");
    expect(timings.length).toBeGreaterThan(0);
    expect(Math.max(...timings)).toBeLessThanOrEqual(2);
    const repeats = arities(orb, "withRepeat");
    expect(repeats.length).toBeGreaterThan(0);
    expect(Math.max(...repeats)).toBeLessThanOrEqual(3);
    // The dialogue hands the orb no callback, and the orb's props take none.
    const [props] = openings(file(DIALOGUE), "PresenceOrb");
    expect(props).not.toMatch(/\bon[A-Z]\w*=/);
    expect(code(orb)).not.toMatch(/\bon[A-Z]\w*\??\s*:/);

    // The policy is pure: node-testable, and it reaches Reanimated and the
    // recorder only through the native adapter the component owns.
    const reached = specifiers(file(POLICY));
    expect(reached.length).toBeGreaterThan(0);
    expect(reached.filter((s) => /native\/|reanimated|^react-native|^expo/.test(s))).toEqual([]);
    expect(specifiers(file(SAMPLER))).toContain("../orb");
  });
});
// ---------------------------------------------------------------------------
// MOTION-8 — the dialogue's transients go through the arbiter
// ---------------------------------------------------------------------------

/*
 * INT-337 (docs/design/motion/motion-verification.md §4 MOTION-8). The policy
 * is lib/motion/transients.ts and its suite; these guards hold the wiring:
 * every entrance in the dialogue is the arbiter's fade and nothing else moves
 * there, history does not fade in, the selection never reaches the motion
 * layer, and the one timer that reports a fade's end lives under src/lib.
 * Every name this block needs is declared inside it.
 */

describe("MOTION-8 — the dialogue's transients go through the arbiter", () => {
  const DIALOGUE = "src/components/DialogueIntake.tsx";
  const HOOK = "src/lib/motion/native/useDialogueMotion.ts";

  /** The value of every `entering={…}` prop in `source`. */
  function enterings(source: string): string[] {
    const text = code(source);
    return [...text.matchAll(/\bentering=\{/g)].map((m) => {
      const from = m.index + m[0].length;
      return text.slice(from, expressionEnd(text, from)).trim();
    });
  }

  it("the stream skips entering on its initial mount", () => {
    const dialogue = code(file(DIALOGUE));
    const config =
      /<LayoutAnimationConfig\s+skipEntering\s*>([\s\S]*?)<\/LayoutAnimationConfig>/.exec(dialogue);
    expect(config, "LayoutAnimationConfig skipEntering in the dialogue").not.toBeNull();
    expect(config![1]).toMatch(/\bstate\.stream\.map\(/);
  });

  it("every entrance in the dialogue is the arbiter's fade, and nothing else moves there", () => {
    // Non-vacuity: the reader finds an entrance and its value.
    expect(enterings("<Animated.View entering={enteringFor(fadeOf(m, id, ctx))} />")).toEqual([
      "enteringFor(fadeOf(m, id, ctx))",
    ]);
    const dialogue = file(DIALOGUE);
    const found = enterings(dialogue);
    // The bubbles, a revealed transcript and the confirm chips.
    expect(found.length).toBeGreaterThanOrEqual(3);
    // ADR-038 A1 (INT-462): a stream bubble enters through the A1 spring, but
    // only as the arbiter grants it; everything else is the arbiter's fade.
    const granted =
      /^bubbleEntering\(\s*bubbleEntrance\(\{\s*granted: bubbleGranted\(transients, key, reduceMotion\),/;
    expect(found.filter((v) => granted.test(v))).toHaveLength(1);
    expect(found.filter((v) => !/^enteringFor\(\s*fadeOf\(/.test(v) && !granted.test(v))).toEqual(
      [],
    );
    // The decisions come from the arbiter's reducer, fed the scene.
    expect(code(dialogue)).toMatch(/\bconst\s+scene\s*=\s*dialogueScene\(/);
    expect(code(dialogue)).toMatch(/\buseDialogueMotion\(\s*scene\s*,/);
    expect(code(dialogue)).not.toMatch(
      /\b(?:withTiming|withRepeat|withSequence|useAnimatedStyle|useSharedValue)\b|\bAnimated\s*\.\s*(?:timing|loop|sequence)\b/,
    );
  });

  it("the selection never reaches the motion layer", () => {
    const dialogue = code(file(DIALOGUE));
    const call = /\bdialogueScene\(/.exec(dialogue);
    expect(call).not.toBeNull();
    const from = call!.index + call![0].length;
    // The whole argument list: up to the bracket that closes the call.
    let depth = 0;
    let end = from;
    for (; end < dialogue.length && depth >= 0; end += 1) {
      if ("([{".includes(dialogue[end])) depth += 1;
      else if (")]}".includes(dialogue[end])) depth -= 1;
    }
    const args = dialogue.slice(from, end);
    expect(args).toMatch(/\bcomposerFocused\b/);
    expect(args).not.toMatch(/\bselected\b/);
  });

  it("a fade's end is reported by a timer under src/lib, never by the animation", () => {
    const hook = code(file(HOOK));
    expect(hook).toMatch(/\bsetTimeout\s*\(/);
    expect(hook).toMatch(/\breleaseDialogueMotion\(/);
    // The delay is the fade the policy granted, never a number of its own.
    expect(literalDurations(hook)).toEqual([]);
    expect(hook).toMatch(/\bconst\s+fadeMs\s*=[^;]*\bfadeOf\(/);
    expect(hook).toMatch(/\bsetTimeout\(\s*\(\)\s*=>[^;]*?,\s*fadeMs\s*,?\s*\)/);
    // No animation calls back into JS; the dialogue owns no timer.
    for (const name of [HOOK, DIALOGUE]) {
      expect(code(file(name)), name).not.toMatch(/\bwithCallback\b/);
    }
    expect(code(file(DIALOGUE))).not.toMatch(/\bset(?:Interval|Timeout)\s*\(/);
  });
});

// ---------------------------------------------------------------------------
// MOTION-11 — haptics (INT-340)
// ---------------------------------------------------------------------------

/*
 * docs/design/motion/motion-verification.md §4 MOTION-11 and ADR-033 §6. The
 * policy itself is proved in src/lib/motion/haptics.test.ts. These guards hold
 * what only the source and the build config can show: where the native module
 * is reached from, which Android permission the build refuses, which handlers
 * ask for a haptic at all, and that every microphone reports itself to the
 * gate. The module's name is assembled from parts, so no scan here finds it
 * spelled in this file.
 */

const HAPTICS_MODULE = ["expo", "haptics"].join("-");
const HAPTICS_ENGINE = "src/lib/motion/native/hapticsEngine.ts";
const APP_HAPTICS = "src/lib/motion/appHaptics.ts";
const VIBRATE = ["android", "permission", "VIBRATE"].join(".");
const VIBRATION = ["Vibra", "tion"].join("");

/** Every string literal naming the haptics module, split by how it is reached. */
function hapticsSpecifiers(source: string): { readonly lazy: number; readonly other: number } {
  const text = code(source);
  const specifier = new RegExp(`(["'\`])${HAPTICS_MODULE}(?:/[^"'\`]*)?\\1`, "g");
  let lazy = 0;
  let other = 0;
  for (const m of text.matchAll(specifier)) {
    if (/\bimport\s*\(\s*$/.test(text.slice(0, m.index))) {
      lazy += 1;
    } else {
      other += 1;
    }
  }
  return { lazy, other };
}

/** Index just past the bracket that closes the one opened at `open`; strings are skipped. */
function pastClosing(text: string, open: number): number {
  let depth = 0;
  for (let i = open; i < text.length; i += 1) {
    const c = text[i];
    if (c === '"' || c === "'" || c === "`") {
      for (i += 1; i < text.length && text[i] !== c; i += 1) {
        if (text[i] === "\\") {
          i += 1;
        }
      }
    } else if ("([{".includes(c)) {
      depth += 1;
    } else if (")]}".includes(c)) {
      depth -= 1;
      if (depth === 0) {
        return i + 1;
      }
    }
  }
  return text.length;
}

/** The argument list of every call to `callee(`, from its `(` to its `)`. */
function callSpansOf(source: string, callee: RegExp): string[] {
  const text = code(source);
  return [...text.matchAll(new RegExp(callee.source, "g"))].map((m) => {
    const open = m.index + m[0].length - 1;
    return text.slice(open, pastClosing(text, open));
  });
}

const HAPTIC_EVENT_NAMES = ["select", "toggleOn", "toggleOff", "arm", "success"];

/** Each haptic a file asks for: the events and surfaces named in its requests. */
function hapticRequests(source: string): {
  readonly events: string[];
  readonly surfaces: string[];
} {
  const spans = callSpansOf(source, /(?<![\w.])haptic\s*\(|\bappHaptics\s*\.\s*request\s*\(/);
  const events = new Set<string>();
  const surfaces = new Set<string>();
  for (const span of spans) {
    for (const m of span.matchAll(/["'](\w+)["']/g)) {
      if (HAPTIC_EVENT_NAMES.includes(m[1])) {
        events.add(m[1]);
      }
    }
    for (const m of span.matchAll(/\bsurface\s*:\s*["'](\w+)["']/g)) {
      surfaces.add(m[1]);
    }
  }
  return { events: [...events].sort(), surfaces: [...surfaces].sort() };
}

/** The handlers wired by INT-340, each with what it may ask for. This list may only change with a test. */
const WIRED_HAPTICS: Record<string, { events: string[]; surfaces: string[] }> = {
  "src/app/(tabs)/me/appearance.tsx": {
    events: ["select", "toggleOff", "toggleOn"],
    surfaces: ["settings"],
  },
  "src/app/(tabs)/me/data.tsx": { events: ["arm", "success"], surfaces: ["dsar"] },
  "src/app/(tabs)/visits/[visitId]/issue-link.tsx": {
    events: ["success"],
    surfaces: ["shareIssue"],
  },
  "src/app/(tabs)/visits/[visitId]/shares.tsx": {
    events: ["arm", "success"],
    surfaces: ["shareRevoke"],
  },
  "src/app/(tabs)/visits/index.tsx": { events: ["select"], surfaces: ["visits"] },
  // ADR-038 A2 (INT-462): the selection tick on an answer chip, in both lanes,
  // and on the composer mic. Instrument options never ask.
  "src/app/(tabs)/visits/[visitId]/intake.tsx": { events: ["select"], surfaces: ["intakeChip"] },
  "src/components/DialogueIntake.tsx": {
    events: ["select"],
    surfaces: ["dialogueMic", "intakeChip"],
  },
};

/** Every recorder in the app, each registered with the gate for as long as it lives. */
const MICROPHONE_OWNERS = [
  "src/components/VoiceNote.tsx",
  "src/lib/dialogue/useDialogueSession.ts",
];

describe("MOTION-11 — haptics reach the device through one lazy adapter", () => {
  it("expo-haptics is imported only by the engine adapter, and only via import()", () => {
    // Non-vacuity: every static shape is caught, both lazy shapes are
    // accepted, and a comment is not an import.
    const statics = [
      `import * as Haptics from "${HAPTICS_MODULE}";`,
      `import { impactAsync } from '${HAPTICS_MODULE}';`,
      `import type { AndroidHaptics } from "${HAPTICS_MODULE}";`,
      `import "${HAPTICS_MODULE}";`,
      `const h = require("${HAPTICS_MODULE}");`,
      `export { selectionAsync } from "${HAPTICS_MODULE}";`,
      `import x from "${HAPTICS_MODULE}/build/Haptics";`,
    ];
    for (const sample of statics) {
      expect(hapticsSpecifiers(sample), sample).toEqual({ lazy: 0, other: 1 });
    }
    for (const sample of [
      `const h = await import("${HAPTICS_MODULE}");`,
      `type H = typeof import('${HAPTICS_MODULE}');`,
      `loaded ??= import(\n  "${HAPTICS_MODULE}"\n);`,
    ]) {
      expect(hapticsSpecifiers(sample), sample).toEqual({ lazy: 1, other: 0 });
    }
    expect(hapticsSpecifiers(`// ${HAPTICS_MODULE} is reached lazily`)).toEqual({
      lazy: 0,
      other: 0,
    });

    // The dependency is real, at the version the Expo SDK pins.
    const pkg = JSON.parse(readFileSync(join(MOBILE, "package.json"), "utf8")) as {
      dependencies: Record<string, string>;
    };
    expect(pkg.dependencies[HAPTICS_MODULE]).toMatch(/^~57\.0\.\d+$/);

    // One file names the module, and only inside import().
    const reaching = TREE.filter((f) => {
      const { lazy, other } = hapticsSpecifiers(f.source);
      return lazy + other > 0;
    }).map((f) => f.name);
    expect(reaching).toEqual([HAPTICS_ENGINE]);
    const engine = hapticsSpecifiers(file(HAPTICS_ENGINE));
    expect(engine.other).toBe(0);
    expect(engine.lazy).toBeGreaterThanOrEqual(1);

    // The adapter is itself reached only lazily, from the one app gate, so no
    // node-tested import path pulls react-native in through it.
    const staticImporters = TREE.filter((f) =>
      [...code(f.source).matchAll(FROM)].some((m) => /native\/hapticsEngine$/.test(m[2])),
    ).map((f) => f.name);
    expect(staticImporters).toEqual([]);
    expect(code(file(APP_HAPTICS))).toMatch(/import\(\s*["']\.\/native\/hapticsEngine["']\s*\)/);

    // The policy and the gate stay pure: no platform, no adapter, no loader.
    for (const pure of ["src/lib/motion/haptics.ts", "src/lib/motion/hapticGate.ts"]) {
      const source = code(file(pure));
      const specifiers = [...source.matchAll(FROM)].map((m) => m[2]);
      expect(
        specifiers.filter((s) => /react-native|native\/|^expo/.test(s)),
        pure,
      ).toEqual([]);
      expect(source, pure).not.toMatch(/\bimport\s*\(|\brequire\s*\(/);
    }
  });

  it("the Android build blocks VIBRATE", async () => {
    const { resolveAppConfig } = await import("../app.config");
    type Config = import("expo/config").ExpoConfig;
    const appJson = (JSON.parse(readFileSync(join(MOBILE, "app.json"), "utf8")) as { expo: Config })
      .expo;
    const qualified = (p: string): string => (p.includes(".") ? p : `android.permission.${p}`);
    const profiles = [
      {},
      { EAS_BUILD_PROFILE: "development" },
      { EAS_BUILD_PROFILE: "preview" },
      { EAS_BUILD_PROFILE: "production" },
    ];
    // Non-vacuity: a config that asks for the permission, in either
    // spelling, and one that already blocks something else.
    const asking: Config = {
      ...appJson,
      android: {
        ...appJson.android,
        permissions: [...(appJson.android?.permissions ?? []), "VIBRATE", VIBRATE],
      },
    };
    const otherBlock = ["android", "permission", "READ_CONTACTS"].join(".");
    const blocking: Config = {
      ...appJson,
      android: { ...appJson.android, blockedPermissions: [otherBlock] },
    };
    for (const config of [appJson, asking, blocking]) {
      for (const env of profiles) {
        const android = resolveAppConfig(config, env).android;
        const blocked = android?.blockedPermissions ?? [];
        expect(
          blocked.filter((p) => qualified(p) === VIBRATE),
          JSON.stringify(env),
        ).toHaveLength(1);
        expect((android?.permissions ?? []).map(qualified)).not.toContain(VIBRATE);
      }
    }
    expect(resolveAppConfig(blocking, {}).android?.blockedPermissions).toContain(otherBlock);
    // The block removes one permission and adds none: the inventory app.json
    // declares resolves unchanged.
    expect(resolveAppConfig(appJson, {}).android?.permissions).toEqual(
      appJson.android?.permissions,
    );

    // Without the block the permission would arrive anyway: the haptics
    // library's own manifest declares it, and the Gradle merge carries it in.
    const libraryManifest = readFileSync(
      join(MOBILE, "node_modules", HAPTICS_MODULE, "android", "src", "main", "AndroidManifest.xml"),
      "utf8",
    );
    expect(libraryManifest).toContain(`android:name="${VIBRATE}"`);

    // Nothing in the app needs what the block removes: react-native's own
    // vibration API requires the permission and would throw without it.
    const takesVibration = (source: string): boolean =>
      clausesFrom(code(source), "react-native").some((c) =>
        new RegExp(`\\b${VIBRATION}\\b`).test(c),
      );
    expect(takesVibration(`import { View, ${VIBRATION} } from "react-native";`)).toBe(true);
    expect(takesVibration(`import { View } from "react-native";`)).toBe(false);
    expect(APP_SOURCE.filter((f) => takesVibration(f.source)).map((f) => f.name)).toEqual([]);
  });
});

describe("MOTION-11 — who asks for a haptic, and who reports the microphone", () => {
  it("only the wired handlers ask, never a consent, legal, error or instrument surface", () => {
    // Non-vacuity: both call forms, a conditional event and the surface.
    expect(
      hapticRequests(`haptic(next ? "toggleOn" : "toggleOff", { surface: "settings" });`),
    ).toEqual({ events: ["toggleOff", "toggleOn"], surfaces: ["settings"] });
    expect(
      hapticRequests(`void appHaptics.request("arm", { surface: "dsar", actionId: a });`),
    ).toEqual({ events: ["arm"], surfaces: ["dsar"] });
    expect(hapticRequests(`const haptic = "select"; hapticFor("success", c);`)).toEqual({
      events: [],
      surfaces: [],
    });

    const asking = Object.fromEntries(
      APP_SOURCE.map((f) => [f.name, hapticRequests(f.source)] as const).filter(
        ([, r]) => r.events.length + r.surfaces.length > 0,
      ),
    );
    expect(asking).toEqual(WIRED_HAPTICS);

    // A success states the server's answer; it never asserts one.
    for (const name of Object.keys(WIRED_HAPTICS)) {
      const successes = callSpansOf(file(name), /(?<![\w.])haptic\s*\(/).filter((s) =>
        s.includes('"success"'),
      );
      for (const span of successes) {
        expect(span, name).toMatch(/\bserverConfirmed\s*:/);
        expect(span, name).not.toMatch(/\bserverConfirmed\s*:\s*true\b/);
      }
    }
  });

  it("every microphone owner reports itself to the haptic gate for as long as it lives", () => {
    const owners = APP_SOURCE.filter((f) => /\buseAudioRecorder\s*\(/.test(code(f.source))).map(
      (f) => f.name,
    );
    expect(owners).toEqual(MICROPHONE_OWNERS);
    const registration =
      /useEffect\(\s*\(\)\s*=>\s*appHaptics\.register\(\{([\s\S]*?)\}\)\s*,\s*(?:\/\/[^\n]*\n\s*)*\[\s*\]\s*,?\s*\)/;
    for (const name of MICROPHONE_OWNERS) {
      const found = registration.exec(code(file(name)));
      expect(found, `${name} registers with the gate in a mount effect`).not.toBeNull();
      // Read live from the recorder at fire time, never from the route or a turn.
      expect(found![1], name).toMatch(/\bmicHot\s*:\s*\(\)\s*=>\s*\w+\.isRecording\b/);
    }
    const dialogue = registration.exec(code(file("src/lib/dialogue/useDialogueSession.ts")));
    expect(dialogue![1]).toMatch(/\bvoiceSessionActive\s*:\s*\(\)\s*=>/);
    // ADR-038 A2: for the gate the dialogue is active while the agent's speech
    // plays or is prepared (its speaking phase); a silent confirm turn is not.
    expect(dialogue![1]).toMatch(
      /\bvoiceSessionActive\s*:\s*\(\)\s*=>\s*!closedRef\.current\s*&&\s*stateRef\.current\.turn\.phase === "speaking"/,
    );
  });
});

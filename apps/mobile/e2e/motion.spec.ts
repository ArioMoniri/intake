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
 * The literals these guards forbid, and the samples that prove each detector
 * is not vacuous, are assembled from parts, so the code below never spells
 * what it scans for.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";

import { animatable, animatedStyleKeys, code, literalDurations, loops } from "./motionSource";

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

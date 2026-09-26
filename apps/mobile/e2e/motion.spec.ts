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

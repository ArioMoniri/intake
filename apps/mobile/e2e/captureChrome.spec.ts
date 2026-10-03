/**
 * INT-477 (GitHub #817; ADR-039 amendment, owner, 4 Oct 2026: "solid"):
 * every capture-protected screen draws solid chrome, never Liquid Glass and
 * never a blur, in both themes. The glass components fall back to their solid
 * variant whenever capture protection is active.
 *
 * The policy and the routes are proved in lib/auth/captureProtection.test.ts
 * and lib/a11y/glass.test.ts. This spec holds the wiring the source alone can
 * show:
 *
 * - the one glass policy hook hears capture protection from the route a
 *   surface sits under and from the window;
 * - every navigator that shows a protected route scopes its screens by route
 *   name, and the tab rail is scoped by the route it sits over;
 * - the guard holds the window before it asks for protection;
 * - the glass hosts are a closed list, each asks the policy, and each solid
 *   branch mounts no glass and no blur.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";

import { CAPTURE_PROTECTED_ROUTES } from "@/lib/auth/captureProtection";

const MOBILE = join(__dirname, "..");
const APP = join(MOBILE, "src", "app");

/** Code only: comments explain what a file avoids, and a guard reads what it does. */
const code = (text: string): string =>
  text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");

const source = (name: string): string => code(readFileSync(join(MOBILE, name), "utf8"));

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

/** App code only; tests may name what the app must not. */
const TREE = walk(join(MOBILE, "src"))
  .filter((path) => /\.tsx?$/.test(path) && !/\.test\.ts$/.test(path))
  .map((path) => ({
    name: relative(MOBILE, path).split(sep).join("/"),
    source: code(readFileSync(path, "utf8")),
  }));

const GLASS_MODE = "src/components/glassMode.tsx";
const BARS = "src/components/GlassBar.tsx";
const RAIL = "src/components/FloatingTabBar.tsx";
const CONTROLS = "src/components/stage/StageControls.tsx";
const ORB_IOS = "src/components/stage/VoiceOrb.ios.tsx";
const DIALOGUE = "src/components/DialogueIntake.tsx";
const GUARD = "src/lib/auth/screenPrivacy.ts";

/** Anything that draws a material: system glass, a glass group, or a blur view. */
const MATERIAL = /<GlassView\b|<GlassContainer\b|<BlurView\b|glassEffect\(/;

/** One exported or local function's source, up to the next top-level declaration. */
function fn(text: string, name: string): string {
  const at = text.search(new RegExp(`function ${name}\\b`));
  expect(at, name).toBeGreaterThanOrEqual(0);
  const next = text.slice(at + 1).search(/\n(export )?(function|const) /);
  return next < 0 ? text.slice(at) : text.slice(at, at + 1 + next);
}

/** The block an `if (<condition>) {` opens, to its closing brace at the same indent. */
function branch(text: string, condition: string): string {
  const head = `if (${condition}) {`;
  const at = text.indexOf(head);
  expect(at, head).toBeGreaterThanOrEqual(0);
  const indent = text.slice(text.lastIndexOf("\n", at) + 1, at);
  const end = text.indexOf(`\n${indent}}`, at);
  expect(end, `${head} closes`).toBeGreaterThan(at);
  return text.slice(at, end);
}

describe("the one glass policy hears capture protection", () => {
  it("useGlassMode passes the route's scope and the window's hold to the policy", () => {
    const hook = fn(source(GLASS_MODE), "useGlassMode");
    expect(hook).toMatch(/const routeProtected = useContext\(CaptureScope\)/);
    expect(hook).toMatch(
      /const windowProtected = useSyncExternalStore\(\s*captureProtection\.subscribe,\s*captureProtection\.getSnapshot,\s*captureProtection\.getSnapshot,?\s*\)/,
    );
    expect(hook).toMatch(/captureProtected: routeProtected \|\| windowProtected/);
  });

  it("a scope adds the route's protection to its parent's, and never removes it", () => {
    const scope = fn(source(GLASS_MODE), "CaptureProtectedScope");
    expect(scope).toMatch(/const outer = useContext\(CaptureScope\)/);
    expect(scope).toMatch(/<CaptureScope\.Provider value=\{captureScope\(outer, route\)\}>/);
  });

  it("near miss: a hook that asked only the OS would be caught", () => {
    const bad =
      "function useGlassMode() {\n  return glassMode({ liquidGlass, reduceTransparency: useReducedTransparency() });\n}\n";
    expect(bad).not.toMatch(/captureProtected: routeProtected \|\| windowProtected/);
  });
});

/** The deepest `_layout.tsx` above a route: the navigator that shows it. */
function owningLayout(route: string): { layout: string; prefix: string } {
  let dir = dirname(join(APP, route));
  while (dir.startsWith(APP)) {
    const layout = join(dir, "_layout.tsx");
    try {
      statSync(layout);
      const prefix = relative(APP, dir).split(sep).join("/");
      return { layout: relative(MOBILE, layout).split(sep).join("/"), prefix };
    } catch {
      dir = dirname(dir);
    }
  }
  throw new Error(`no layout above ${route}`);
}

describe("every protected route is scoped from its first frame", () => {
  const owners = [...CAPTURE_PROTECTED_ROUTES].map((route) => ({ route, ...owningLayout(route) }));

  it("non-vacuity: the protected routes sit under the tabs shell and the visits stack", () => {
    expect([...new Set(owners.map((o) => o.layout))].sort()).toEqual([
      "src/app/(tabs)/_layout.tsx",
      "src/app/(tabs)/visits/_layout.tsx",
    ]);
  });

  it.each(owners)(
    "$route: its navigator wraps each screen in the scope, named as transitions name it",
    ({ layout, prefix }) => {
      const text = source(layout);
      expect(text).toContain('import { CaptureProtectedScope } from "@/components/glassMode"');
      const scoped = new RegExp(
        `screenLayout=\\{\\(\\{ route, children \\}\\) => \\(\\s*<CaptureProtectedScope route=\\{\`${prefix.replace(/[()[\]]/g, "\\$&")}/\\$\\{route\\.name\\}\`\\}>\\s*\\{children\\}\\s*</CaptureProtectedScope>`,
      );
      expect(text).toMatch(scoped);
    },
  );

  it("near miss: a navigator without the scope would be caught", () => {
    const bare = "<Stack screenOptions={({ route }) => ({ headerShown: false })} />";
    expect(bare).not.toMatch(/screenLayout=/);
  });

  it("the tab rail is scoped by the route it sits over", () => {
    const rail = source(RAIL);
    expect(rail).toMatch(
      /<CaptureProtectedScope route=\{focusedRoutePath\(TABS_GROUP, state\.routes\[state\.index\]\)\}>\s*<RailPill>[\s\S]*<\/RailPill>\s*<\/CaptureProtectedScope>/,
    );
    expect(rail).toMatch(/const TABS_GROUP = "\(tabs\)"/);
  });
});

describe("the guard holds the window before it asks for protection", () => {
  it("the screen guard runs through protectScreen with the app's one window store", () => {
    const guard = source(GUARD);
    expect(guard).toMatch(
      /useEffect\(\(\) => \{[\s\S]*?return protectScreen\(native \? NATIVE_GUARD : null, captureProtection\);[\s\S]*?\}, \[\]\)/,
    );
    expect(guard).toMatch(
      /prevent: \(\) => ScreenCapture\.preventScreenCaptureAsync\(CAPTURE_KEY\)/,
    );
    expect(guard).toMatch(/allow: \(\) => ScreenCapture\.allowScreenCaptureAsync\(CAPTURE_KEY\)/);
  });

  it("nothing else asks expo-screen-capture for protection", () => {
    const askers = TREE.filter((f) =>
      /preventScreenCaptureAsync|usePreventScreenCapture/.test(f.source),
    );
    expect(askers.map((f) => f.name)).toEqual([GUARD]);
  });
});

describe("the glass hosts: a closed list, each asking the policy", () => {
  it("only these files draw a material", () => {
    const hosts = TREE.filter((f) => MATERIAL.test(f.source)).map((f) => f.name);
    expect(hosts.sort()).toEqual([CONTROLS, ORB_IOS, RAIL, BARS].sort());
  });

  it.each([RAIL, BARS, CONTROLS])("%s takes its material from useGlassMode()", (name) => {
    expect(source(name)).toContain("useGlassMode()");
  });

  it("the orb's clear lens is drawn only when the dialogue's live mode is liquid", () => {
    const orb = source(ORB_IOS);
    expect(orb).toMatch(/\{glass \? \(\s*<Circle[\s\S]*?glassEffect\(/);
    const dialogue = source(DIALOGUE);
    expect(dialogue).toMatch(/const glassMode = useGlassMode\(\)/);
    expect(dialogue).toMatch(/glass: glassMode === "liquid"/);
  });

  // Each host's solid answer, by the function and the condition that opens it.
  const SOLID_BRANCHES: [file: string, fnName: string, condition: string][] = [
    [BARS, "GlassBar", 'mode === "solid"'],
    [BARS, "GlassNavBackground", 'mode === "solid"'],
    [RAIL, "RailPill", 'mode === "solid"'],
    [CONTROLS, "Pane", 'mode !== "liquid"'],
    [CONTROLS, "StageGlassGroup", 'mode !== "liquid"'],
  ];

  it.each(SOLID_BRANCHES)(
    "%s %s: the solid branch mounts no glass and no blur",
    (file, name, cond) => {
      const solid = branch(fn(source(file), name), cond);
      expect(solid).toMatch(/return/);
      expect(solid).not.toMatch(MATERIAL);
    },
  );

  it("near miss: a solid branch that kept a blur view would be caught", () => {
    const bad =
      'function GlassBar() {\n  if (mode === "solid") {\n    return <View><BlurView intensity={55} /></View>;\n  }\n  return null;\n}\n';
    expect(branch(fn(bad, "GlassBar"), 'mode === "solid"')).toMatch(MATERIAL);
  });

  it("the stage bar without Liquid Glass is a solid bar: no material, no scroll-edge effect", () => {
    const stageNav = branch(fn(source(BARS), "withStageNav"), 'mode !== "liquid"');
    expect(stageNav).toMatch(/headerTransparent: false/);
    expect(stageNav).not.toMatch(/headerBlurEffect|scrollEdgeEffects|headerTransparent: true/);
  });
});

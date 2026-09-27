/**
 * The Apple-native pass as source facts (docs/design/apple-native/spec.md).
 *
 * Four things this spec keeps true:
 * - every glyph goes through the symbol registry, so no call site can hand
 *   expo-symbols a bare SF name again (a bare name draws nothing on Android);
 * - every glass surface asks one policy for its material, and that policy has
 *   a solid answer for Reduce Transparency;
 * - system glass follows the in-app theme, not only the OS one;
 * - the motion budget still holds on the new chrome: no symbol animations, no
 *   interactive glass, and no glass on the kiosk's own screens.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";

import { SYMBOLS } from "@/lib/symbols";

const ROOT = join(__dirname, "..");
const SRC = join(ROOT, "src");

interface SourceFile {
  readonly name: string;
  readonly source: string;
}

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

/**
 * Source with comments removed: the files explain what they avoid, and a
 * guard must read what they do. Block comments, and line comments that
 * start a line (a `//` inside a string such as a URL is left alone).
 */
const code = (source: string): string =>
  source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

/** App code only: tests may name what the app must not. */
const TREE: SourceFile[] = walk(SRC)
  .filter((path) => /\.tsx?$/.test(path) && !/\.test\.ts$/.test(path))
  .map((path) => ({
    name: relative(ROOT, path).split(sep).join("/"),
    source: code(readFileSync(path, "utf8")),
  }));

const file = (name: string): string => {
  const found = TREE.find((f) => f.name === name);
  if (found === undefined) {
    throw new Error(`${name} is not in the app tree`);
  }
  return found.source;
};

/**
 * Files that load the given module at runtime, statically or lazily. A
 * type-only import is erased at build time and loads nothing, so the pure
 * registry may take its name types from expo-symbols.
 */
function importersOf(tree: readonly SourceFile[], module: string): string[] {
  const quoted = module.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&");
  const pattern = new RegExp(`(from\\s+|import\\(\\s*)["']${quoted}["']`);
  const typeOnly = /import\s+type\s[^;]*?from\s+["'][^"']+["'];?/g;
  return tree.filter((f) => pattern.test(f.source.replace(typeOnly, ""))).map((f) => f.name);
}

const GLASS_HOSTS = [
  "src/components/FloatingTabBar.tsx",
  "src/components/GlassBar.tsx",
  "src/components/GlassCard.tsx",
];

describe("every glyph goes through the symbol registry", () => {
  it("only Icon.tsx imports expo-symbols", () => {
    expect(importersOf(TREE, "expo-symbols")).toEqual(["src/components/Icon.tsx"]);
  });

  it("the import scan catches a call site that goes around the registry (near miss)", () => {
    const bypass: SourceFile = {
      name: "src/components/Bypass.tsx",
      source:
        'import type { SFSymbol } from "expo-symbols";\nimport { SymbolView } from "expo-symbols";\n',
    };
    const typesOnly: SourceFile = {
      name: "src/lib/TypesOnly.ts",
      source: 'import type { SFSymbol } from "expo-symbols";\n',
    };
    const found = importersOf([...TREE, bypass, typesOnly], "expo-symbols");
    expect(found).toContain(bypass.name);
    expect(found).not.toContain(typesOnly.name);
  });

  it("Icon hands SymbolView the per-platform name and a box that holds the size", () => {
    const icon = file("src/components/Icon.tsx");
    expect(icon).toMatch(/name=\{symbolName\(/);
    expect(icon).toContain("fallback=");
    // The motion budget: SF symbol effects are animation, and there are none.
    expect(icon).not.toContain("animationSpec");
  });

  it("every registry row is drawn somewhere: a token ships only when something consumes it", () => {
    const app = TREE.filter((f) => f.name !== "src/lib/symbols.ts");
    const unused = Object.keys(SYMBOLS).filter(
      (key) => !app.some((f) => f.source.includes(`"${key}"`)),
    );
    expect(unused).toEqual([]);
  });

  it("the rail draws the filled variant for the active section", () => {
    const rail = file("src/components/FloatingTabBar.tsx");
    expect(rail).toContain("<Icon");
    expect(rail).toContain("selected={active}");
  });

  it("no SF symbol effect anywhere in the app (motion budget, spec §0 rule 5)", () => {
    for (const f of TREE) {
      expect(f.source, f.name).not.toContain("animationSpec");
    }
  });
});

describe("every glass surface asks one policy for its material", () => {
  it.each(GLASS_HOSTS)("%s renders the mode useGlassMode() decides, solid included", (name) => {
    const host = file(name);
    expect(host).toContain("useGlassMode()");
    expect(host).toMatch(/mode === "liquid"/);
    expect(host).toMatch(/mode === "solid"/);
  });

  it("availability is read in one place, never per host", () => {
    const readers = TREE.filter((f) => /\bisLiquidGlassAvailable\(\)/.test(f.source)).map(
      (f) => f.name,
    );
    expect(readers).toEqual(["src/components/glassMode.tsx"]);
  });

  it("only the native adapter asks the OS about Reduce Transparency", () => {
    const askers = TREE.filter((f) =>
      /\bisReduceTransparencyEnabled\b|["']reduceTransparencyChanged["']/.test(f.source),
    ).map((f) => f.name);
    expect(askers).toEqual(["src/lib/a11y/native/reduceTransparencySource.ts"]);
  });

  it("the adapter is reached lazily, so node-tested imports never pull react-native in", () => {
    const prefs = file("src/lib/a11y/prefs.ts");
    expect(prefs).toMatch(/import\(\s*["']@\/lib\/a11y\/native\/reduceTransparencySource["']\s*\)/);
    expect(importersOf(TREE, "@/lib/a11y/native/reduceTransparencySource")).toEqual([
      "src/lib/a11y/prefs.ts",
    ]);
  });
});

describe("system glass follows the app, and stays inert", () => {
  const glassViews = TREE.flatMap((f) =>
    [...f.source.matchAll(/<GlassView\b[^>]*>/gs)].map((m) => ({ name: f.name, tag: m[0] })),
  );

  it("there is system glass to check", () => {
    expect(glassViews.length).toBeGreaterThanOrEqual(GLASS_HOSTS.length);
  });

  it("every GlassView takes the resolved scheme, so a Görünüm override reaches the material", () => {
    for (const { name, tag } of glassViews) {
      expect(tag, name).toContain("colorScheme={scheme}");
    }
  });

  it("no GlassView is interactive: its press response scales, and presses are opacity only", () => {
    for (const { name, tag } of glassViews) {
      expect(tag, name).not.toContain("isInteractive");
    }
  });

  it("the kiosk's own screens carry no glass (a translucent rest screen could show the last patient)", () => {
    const kiosk = file("src/components/KioskGate.tsx");
    expect(kiosk).not.toMatch(/GlassView|BlurView|GlassBar|GlassCard|useGlassMode/);
  });
});

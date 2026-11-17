/**
 * The symbol registry (docs/design/apple-native/spec.md §1.2).
 *
 * Every glyph in the app is one registry row: an SF Symbol for iOS and a
 * Material Symbol for Android and web. Before the registry, every call site
 * handed `SymbolView` a bare SF name. expo-symbols treats a string as an
 * iOS-only name and renders `fallback` everywhere else, so on Android the tab
 * rail, every chevron and the send arrow drew nothing
 * (expo-symbols/build/SymbolView.js). SF Symbols are licensed for Apple
 * platforms only, so the Android half cannot be the SF glyph either.
 *
 * These tests check the names against the sets the app actually ships, not a
 * copy of them. The Material set is the font map expo-symbols bundles. The SF
 * set is `sf-symbols-typescript`, the type package expo-symbols types its
 * `name` prop with, which groups each name under the SF Symbols release that
 * introduced it and that release's iOS minimum. The iOS floor is read from the
 * podspec Expo builds with, so raising it moves this test with it.
 */
import { readFileSync, realpathSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { describe, expect, it } from "vitest";

import { SYMBOLS, symbolName, type SymbolKey } from "./symbols";

const requireHere = createRequire(__filename);
const symbolsEntry = realpathSync(requireHere.resolve("expo-symbols"));
const expoRoot = dirname(realpathSync(requireHere.resolve("expo/package.json")));

/** Material Symbols names → code points, as expo-symbols renders them. */
const MATERIAL: Record<string, number> = JSON.parse(
  readFileSync(join(dirname(symbolsEntry), "android", "symbols.json"), "utf8"),
);

/** The SF name declarations, read from expo-symbols' own dependency. */
const SF_DTS = readFileSync(
  join(dirname(createRequire(symbolsEntry).resolve("sf-symbols-typescript")), "index.d.ts"),
  "utf8",
);

type Version = readonly number[];

const parseVersion = (text: string): Version => text.split(".").map(Number);

function atMost(a: Version, b: Version): boolean {
  for (let i = 0; i < Math.max(a.length, b.length); i += 1) {
    const x = a[i] ?? 0;
    const y = b[i] ?? 0;
    if (x !== y) {
      return x < y;
    }
  }
  return true;
}

/** Each SF name → the iOS version of the release that introduced it. */
function sfIntroductions(dts: string): Map<string, { release: string; ios: Version }> {
  const found = new Map<string, { release: string; ios: Version }>();
  for (const section of dts.split("@name SF Symbols ").slice(1)) {
    const release = /^(\d+\.\d+)/.exec(section)?.[1];
    const ios = /iOS v(\d+(?:\.\d+)*)\+/.exec(section)?.[1];
    if (release === undefined || ios === undefined) {
      continue;
    }
    for (const match of section.matchAll(/\|\s*'([^']+)'/g)) {
      if (!found.has(match[1])) {
        found.set(match[1], { release, ios: parseVersion(ios) });
      }
    }
  }
  return found;
}

const SF = sfIntroductions(SF_DTS);

/** The deployment floor Expo's own pod declares for iOS. */
const IOS_FLOOR: Version = parseVersion(
  /:ios\s*=>\s*'(\d+(?:\.\d+)*)'/.exec(readFileSync(join(expoRoot, "Expo.podspec"), "utf8"))?.[1] ??
    "",
);

/** The checks the registry must pass, as functions the near-miss controls reuse. */
const isMaterial = (name: string): boolean => Object.hasOwn(MATERIAL, name);
const isShippableSf = (name: string): boolean => {
  const introduced = SF.get(name);
  return introduced !== undefined && atMost(introduced.ios, IOS_FLOOR);
};

const KEYS = Object.keys(SYMBOLS) as SymbolKey[];

describe("the sets the registry is checked against are the real ones", () => {
  it("reads a Material map, an SF catalogue and an iOS floor", () => {
    expect(Object.keys(MATERIAL).length).toBeGreaterThan(1000);
    expect(SF.size).toBeGreaterThan(1000);
    expect(IOS_FLOOR.length).toBeGreaterThanOrEqual(2);
    expect(IOS_FLOOR[0]).toBeGreaterThanOrEqual(15);
  });

  it("rejects the near misses: an SF name on Android, a made-up name, a too-new SF name", () => {
    // An SF name is not a Material name, even for the same idea.
    expect(isMaterial("chevron.right")).toBe(false);
    expect(isMaterial("chevron_right")).toBe(true);
    // A name that exists nowhere.
    expect(isShippableSf("chevron.rightt")).toBe(false);
    // A real SF Symbols 7 name needs iOS 26, above our floor.
    const newest = [...SF].find(([, at]) => !atMost(at.ios, IOS_FLOOR));
    expect(newest).toBeDefined();
    expect(isShippableSf(newest![0])).toBe(false);
  });
});

describe("every registry row draws on every platform", () => {
  it.each(KEYS)("%s has a Material Symbol that expo-symbols ships", (key) => {
    expect(isMaterial(SYMBOLS[key].android), SYMBOLS[key].android).toBe(true);
  });

  it.each(KEYS)("%s is a real SF Symbol available at the iOS floor", (key) => {
    const { ios } = SYMBOLS[key];
    expect(SF.has(ios), `${ios} is not an SF Symbol`).toBe(true);
    expect(isShippableSf(ios), `${ios} is newer than iOS ${IOS_FLOOR.join(".")}`).toBe(true);
  });

  it("every selected variant is a real SF Symbol at the floor, and differs from its outline", () => {
    for (const key of KEYS) {
      const entry: { ios: string; selected?: string } = SYMBOLS[key];
      if (entry.selected === undefined) {
        continue;
      }
      expect(isShippableSf(entry.selected), entry.selected).toBe(true);
      expect(entry.selected, key).not.toBe(entry.ios);
    }
  });

  it("the key IS the iOS name, so a call site reads as the glyph it draws", () => {
    for (const key of KEYS) {
      expect(SYMBOLS[key].ios).toBe(key);
    }
  });
});

describe("symbolName hands SymbolView a name for each platform", () => {
  it("never a bare string, which Android would render as nothing", () => {
    for (const key of KEYS) {
      const name = symbolName(key);
      expect(typeof name).toBe("object");
      expect(name.ios).toBe(SYMBOLS[key].ios);
      expect(name.android).toBe(SYMBOLS[key].android);
    }
  });

  it("web takes the Material twin: SF glyphs are licensed for Apple platforms only", () => {
    for (const key of KEYS) {
      expect(symbolName(key).web).toBe(SYMBOLS[key].android);
    }
  });

  it("the selected state swaps in the filled SF variant where one exists", () => {
    expect(symbolName("folder", true).ios).toBe("folder.fill");
    expect(symbolName("folder", false).ios).toBe("folder");
    // SF has no filled calendar: selected keeps the outline, and the rail's
    // ink, weight and well still carry the state.
    expect(symbolName("calendar", true).ios).toBe("calendar");
  });

  it("the selected state never changes the Android glyph", () => {
    for (const key of KEYS) {
      expect(symbolName(key, true).android).toBe(symbolName(key, false).android);
    }
  });
});

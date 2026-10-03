/**
 * INT-478 (GitHub #820): the clinical screen guard as source facts.
 *
 * The counting is proved in src/lib/auth/captureLock.test.ts. This spec holds
 * what only the source can show:
 *
 * - every OS capture call goes through the app's one lock, so no screen can
 *   release protection another screen still holds;
 * - nothing else in the app talks to expo-screen-capture, and the app-switcher
 *   snapshot blur is not used: on Android the recents thumbnail is covered by
 *   the same FLAG_SECURE call the lock counts;
 * - protection is held for as long as a screen is mounted, not while it is
 *   focused (fail closed: a tab screen kept mounted stays protected);
 * - which screens are protected is unchanged.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";

const MOBILE = join(__dirname, "..");
const SRC = join(MOBILE, "src");
const GUARD = "src/lib/auth/screenPrivacy.ts";

/** Code only: comments explain what a file avoids, and a guard reads what it does. */
const code = (text: string): string =>
  text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

/** App code only; tests may name what the app must not. */
const TREE = walk(SRC)
  .filter((path) => /\.tsx?$/.test(path) && !/\.test\.ts$/.test(path))
  .map((path) => ({
    name: relative(MOBILE, path).split(sep).join("/"),
    source: code(readFileSync(path, "utf8")),
  }));

const guard = (): string => {
  const found = TREE.find((f) => f.name === GUARD);
  expect(found, GUARD).toBeDefined();
  return found?.source ?? "";
};

const count = (text: string, pattern: RegExp): number => text.match(pattern)?.length ?? 0;

describe("every OS capture call goes through the one lock", () => {
  it("the guard builds the app's one lock over expo-screen-capture", () => {
    const text = guard();
    expect(text).toMatch(/const clinicalCapture = createCaptureLock\(NATIVE_GUARD\)/);
    expect(text).toMatch(
      /prevent: \(\) => ScreenCapture\.preventScreenCaptureAsync\(CAPTURE_KEY\)/,
    );
    expect(text).toMatch(/allow: \(\) => ScreenCapture\.allowScreenCaptureAsync\(CAPTURE_KEY\)/);
  });

  it("the OS is asked and released in exactly one place each: the lock's guard", () => {
    const text = guard();
    expect(count(text, /preventScreenCaptureAsync\(/g)).toBe(1);
    expect(count(text, /allowScreenCaptureAsync\(/g)).toBe(1);
  });

  it("each screen holds the lock and gives back only its own hold", () => {
    expect(guard()).toMatch(
      /useEffect\(\(\) => \{[\s\S]*?return clinicalCapture\.acquire\(\);\s*\}, \[\]\)/,
    );
  });

  it("near miss: the old per-screen call, which released every screen's protection, would be caught", () => {
    const old =
      "useEffect(() => {\n  ScreenCapture.preventScreenCaptureAsync(CAPTURE_KEY);\n  return () => { ScreenCapture.allowScreenCaptureAsync(CAPTURE_KEY); };\n}, []);";
    expect(old).not.toMatch(/return clinicalCapture\.acquire\(\);/);
  });
});

describe("nothing else talks to expo-screen-capture", () => {
  it("only the guard imports it", () => {
    const importers = TREE.filter((f) =>
      /from\s+["']expo-screen-capture["']|import\(\s*["']expo-screen-capture["']/.test(f.source),
    );
    expect(importers.map((f) => f.name)).toEqual([GUARD]);
  });

  it("no hook of the library's own and no app-switcher blur, which would hold protection outside the lock", () => {
    for (const f of TREE) {
      expect(f.source, f.name).not.toMatch(
        /usePreventScreenCapture|enableAppSwitcherProtectionAsync|disableAppSwitcherProtectionAsync/,
      );
    }
  });
});

describe("fail closed: protection follows the mount, not the focus", () => {
  it("the guard is a mount effect, never a focus effect", () => {
    const text = guard();
    expect(text).toMatch(/useEffect\(/);
    expect(text).not.toMatch(/useFocusEffect|useIsFocused|addListener\(\s*["'](focus|blur)["']/);
  });
});

describe("which screens are protected is unchanged", () => {
  it("the guard's callers are the six clinical routes and the kiosk PIN screen", () => {
    const callers = TREE.filter((f) =>
      /(?<!function\s)\buseClinicalScreenPrivacy\(\)/.test(f.source),
    )
      .map((f) => f.name)
      .sort();
    expect(callers).toEqual(
      [
        "src/app/(tabs)/records.tsx",
        "src/app/(tabs)/wellbeing.tsx",
        "src/app/(tabs)/visits/[visitId]/intake.tsx",
        "src/app/(tabs)/visits/[visitId]/issue-link.tsx",
        "src/app/(tabs)/visits/[visitId]/review.tsx",
        "src/app/(tabs)/visits/[visitId]/shares.tsx",
        "src/components/KioskGate.tsx",
      ].sort(),
    );
  });
});

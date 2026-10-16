/**
 * INT-492 (GitHub #839): the question progress and the micro-interactions
 * around it, as source facts. The rules themselves are pure and live in
 * src/lib/intake/progressCapsule.test.ts, src/lib/motion/micro.test.ts and
 * src/lib/controlChrome.test.ts; React Native has no DOM here, so this file
 * proves the wiring.
 *
 * The owner kept the parts inside ADR-033, ADR-037 and ADR-039 and declined
 * every approval-needed one, in chat on 16 Oct 2026 ("P1N P2N P3N P4N P5N").
 * So the shipped design is on for everyone, with no flag, and:
 *
 * 1. The progress is ONE accessible value: the capsule draws inside the one
 *    progressbar, its parts are never read on their own, and nothing in it
 *    announces itself, so a reader hears "Soru 3, toplam 9" once.
 * 2. The numerals are display-only (invariant 22): the capsule's module is
 *    reached from the progress control alone, and nothing on the spoken lane
 *    imports it.
 * 3. The capsule moves nothing, and no rolling number exists anywhere. The
 *    one new movement is ADR-037 P1's press, on the opted-in actions only,
 *    never on consent, a gate, RED or an instrument.
 * 4. The intake is capture-protected (INT-477), so the capsule is solid.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";

import { describe, expect, it } from "vitest";

import { code } from "./motionSource";

const MOBILE = join(__dirname, "..");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

/** Every shipped script under src/, tests excluded, comments removed. */
const TREE = walk(join(MOBILE, "src"))
  .filter((p) => /\.tsx?$/.test(p) && !/\.test\.tsx?$/.test(p))
  .map((p) => ({
    name: relative(MOBILE, p).split(sep).join("/"),
    source: code(readFileSync(p, "utf8")),
  }));

function source(name: string): string {
  const found = TREE.find((f) => f.name === name);
  expect(found, `${name} is missing`).toBeDefined();
  return found!.source;
}

/** Files importing `module` (an `@/` path), by alias or by a relative path ending in it. */
function importersOf(module: string): string[] {
  const tail = module.split("/").pop()!;
  const alias = new RegExp(`from\\s+["']${module.replace(/[/@.]/g, "\\$&")}["']`);
  const rel = new RegExp(`from\\s+["']\\.{1,2}/(?:[\\w.]+/)*${tail}["']`);
  return TREE.filter((f) => alias.test(f.source) || rel.test(f.source))
    .map((f) => f.name)
    .sort();
}

/** The body of a top-level function, from its signature's `) {` to its closing brace. */
function body(text: string, name: string): string {
  const start = text.indexOf(`function ${name}(`);
  expect(start, name).toBeGreaterThan(-1);
  const open = text.indexOf(") {\n", start);
  return text.slice(open, text.indexOf("\n}\n", open));
}

const INTAKE = "src/app/(tabs)/visits/[visitId]/intake.tsx";
const REVIEW = "src/app/(tabs)/visits/[visitId]/review.tsx";
const PROGRESS = "src/components/QuestionProgress.tsx";
const GATE = "src/components/DialogueGate.tsx";
const THEMED = "src/components/Themed.tsx";
const PRESS_COMPONENT = "src/components/PressScale.tsx";
const CHIP_SLOT = "src/components/ChipSlot.tsx";
const CAPSULE = "src/lib/intake/progressCapsule.ts";
const MICRO = "src/lib/motion/micro.ts";
const PRESS_NATIVE = "src/lib/motion/native/pressScale.ts";

describe("0 · shipped for everyone, with no flag", () => {
  it("no feature-flag reader remains in the app or its config", () => {
    const config = readFileSync(join(MOBILE, "app.config.ts"), "utf8");
    const readers = TREE.filter((f) =>
      /extra\??\.flags\b|featureFlags|resolveFlags/.test(f.source),
    );
    expect(readers.map((f) => f.name)).toEqual([]);
    expect(code(config)).not.toMatch(/\bflags\b|INTAKE_FLAGS/);
  });

  it("the typed screen always renders the capsule from the pack's position and flow", () => {
    expect(source(INTAKE)).toMatch(
      /<QuestionProgress\s+position=\{questionPosition\(applicable, question\.id, flowCanGrow\)\}\s+flow=\{applicable\}\s*\/>/,
    );
  });

  it("every answer chip draws the reserved check slot", () => {
    const intake = source(INTAKE);
    expect(intake).toMatch(/<ChipSlot selected=\{on\} \/>/);
    // Near miss: the check that widened the chip on select is gone.
    expect(intake).not.toMatch(/look\.check \? \(/);
  });

  it("the gate's wait follows Reduce Motion alone", () => {
    const gate = source(GATE);
    expect(gate).toMatch(/loadingIndicator\(\{ reduce: reduceMotion \}\)/);
    expect(gate).toMatch(/waiting === "still" \? \([\s\S]*?<Icon name="ellipsis"/);
    expect(gate).toContain("<ActivityIndicator color={theme.primary} />");
  });
});

describe("1 · a reader hears one value", () => {
  const progress = () => source(PROGRESS);

  it("the capsule sits inside the one progressbar, whose value is the worded position", () => {
    const text = progress();
    expect(text.match(/accessibilityRole="progressbar"/g)).toHaveLength(1);
    expect(text).toMatch(/text: positionSpoken\(position, word, t\("intake\.progress\.of"\)\)/);
    const bar = text.indexOf('accessibilityRole="progressbar"');
    const capsule = text.indexOf("<CapsuleBody");
    const grows = text.indexOf('t("intake.progress.grows")');
    expect(capsule).toBeGreaterThan(bar);
    expect(grows).toBeGreaterThan(capsule);
  });

  it("no part of the capsule speaks for itself", () => {
    for (const part of ["CapsuleBody", "Segment", "Count"]) {
      expect(body(progress(), part), part).not.toMatch(
        /accessibilityLabel|accessibilityValue|accessibilityRole|accessible\b/,
      );
    }
    expect(source(CHIP_SLOT)).toContain('importantForAccessibility="no-hide-descendants"');
  });

  it("nothing announces a change: no live region and no announcement call", () => {
    expect(progress()).not.toMatch(
      /accessibilityLiveRegion|announceForAccessibility|useLiveAnnouncement|useLineAnnouncement|AnnouncedRegion/,
    );
  });
});

describe("2 · the numerals are display-only (invariant 22)", () => {
  it("the capsule module is reached from the progress control alone", () => {
    expect(importersOf("@/lib/intake/progressCapsule")).toEqual([PROGRESS]);
    const counters = TREE.filter((f) => /\bcapsuleCount\s*\(/.test(f.source)).map((f) => f.name);
    expect(counters.sort()).toEqual([CAPSULE, PROGRESS].sort());
  });

  it("nothing on the spoken lane reaches it", () => {
    const spoken = TREE.filter(
      (f) =>
        f.name === "src/components/DialogueIntake.tsx" ||
        f.name.startsWith("src/components/stage/") ||
        f.name.startsWith("src/lib/dialogue/") ||
        f.name.startsWith("src/lib/livekit/"),
    );
    expect(spoken.length).toBeGreaterThan(5);
    for (const f of spoken) {
      expect(f.source, f.name).not.toMatch(/progressCapsule|capsuleCount|QuestionProgress/);
    }
  });
});

describe("3 · motion stays inside the ratified bounds", () => {
  it("the capsule moves nothing at all", () => {
    expect(source(PROGRESS)).not.toMatch(
      /react-native-reanimated|withTiming|withSpring|useAnimatedStyle|useSharedValue|entering=|transition/,
    );
  });

  it("no rolling number exists anywhere: the owner declined it (P1N)", () => {
    const rolling = TREE.filter((f) =>
      /\brollDigits\b|\brollGranted\b|\bnumberRoll\b|\brollEntering\b|progressNumberRoll|NumberFlow|NumberTicker/.test(
        f.source,
      ),
    ).map((f) => f.name);
    expect(rolling).toEqual([]);
  });

  it("the press scale is ADR-037 P1's, read from the pure module", () => {
    const native = source(PRESS_NATIVE);
    expect(native).toMatch(/import (?:type )?\{[^}]*\bPressScale\b[^}]*\} from "\.\.\/micro"/);
    expect(native).not.toMatch(/translate|rotate|withRepeat|withTiming/);
    const numbers = [...native.matchAll(/(?<![\w.])\d+(?:\.\d+)?(?![\w.])/g)].map((m) => m[0]);
    expect(numbers.filter((n) => n !== "1")).toEqual([]);
    expect(source(MICRO)).toMatch(/PRESS_SCALE = 0\.97/);
  });

  it("only the typed steps' actions and the send opt in; never consent, a gate, RED or an instrument", () => {
    const opted = TREE.filter((f) => /<PrimaryButton\b[^>]*\bpressScale\b/s.test(f.source)).map(
      (f) => f.name,
    );
    expect(opted.sort()).toEqual([INTAKE, REVIEW].sort());
    // The step's four actions and the one send, each a bare opt-in.
    expect(source(INTAKE).match(/^\s*pressScale$/gm)).toHaveLength(4);
    expect(source(REVIEW).match(/^\s*pressScale$/gm)).toHaveLength(1);
    expect(source("src/components/InstrumentStep.tsx")).not.toMatch(/pressScale|PressScale/);
    expect(importersOf("@/components/PressScale")).toEqual([THEMED]);
    expect(source(PRESS_COMPONENT)).toMatch(
      /pressScale\(\{ enabled: true, reduce, redPresented: false \}\)/,
    );
  });

  it("no INT-492 file paints a RED token", () => {
    for (const name of [PROGRESS, PRESS_COMPONENT, CHIP_SLOT, CAPSULE, MICRO, PRESS_NATIVE]) {
      expect(source(name), name).not.toMatch(/\bemergency(Soft)?\b/);
    }
  });
});

describe("4 · the capsule is solid on a capture-protected screen", () => {
  it("draws no material", () => {
    expect(source(PROGRESS)).not.toMatch(
      /<GlassView\b|<BlurView\b|expo-blur|expo-glass-effect|useGlassMode|GlassContainer/,
    );
  });

  it("paints with the pure chrome, whose colours are opaque theme hexes", () => {
    expect(source(PROGRESS)).toContain("capsuleChrome(theme)");
  });
});

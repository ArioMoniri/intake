/**
 * INT-492 (GitHub #839): the question progress and micro-interaction
 * redesign, as source facts. The rules themselves are pure and live in
 * src/lib/flags.test.ts, src/lib/intake/progressCapsule.test.ts,
 * src/lib/motion/micro.test.ts and src/lib/controlChrome.test.ts; React
 * Native has no DOM here, so this file proves the wiring.
 *
 * 1. One flag, off by default: a build nobody configured renders today's
 *    screens. Each flagged site keeps today's expression on its off branch.
 * 2. The progress is ONE accessible value in both looks: the capsule and the
 *    rolling glyphs are children of the one progressbar, hidden, with no
 *    live region, so a reader hears "Soru 3, toplam 9" once, never a digit
 *    and never a frame.
 * 3. The numerals are display-only (invariant 22): the capsule's module is
 *    reached from the progress control alone, and nothing on the spoken lane
 *    imports it.
 * 4. Motion stays inside ADR-033, ADR-037 P1 and ADR-038: the capsule moves
 *    nothing; the roll (approval needed) is opacity and an 8 pt rise on the
 *    app's one fade; the press scale is ADR-037 P1's, on the opted-in
 *    actions only, never on consent, a gate, RED or an instrument.
 * 5. The intake is capture-protected (INT-477), so the capsule is solid.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";

import type { ConfigContext, ExpoConfig } from "expo/config";
import { afterEach, describe, expect, it, vi } from "vitest";

import appConfig, { FLAGS_ENV, resolveAppConfig } from "../app.config";
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
  const tail = module.replace(/^@\//, "").replace(/^lib\//, "");
  const alias = new RegExp(`from\\s+["']${module.replace(/[/@.]/g, "\\$&")}["']`);
  const rel = new RegExp(`from\\s+["']\\.{1,2}/(?:[\\w.]+/)*${tail.split("/").pop()}["']`);
  return TREE.filter((f) => alias.test(f.source) || rel.test(f.source))
    .map((f) => f.name)
    .sort();
}

const INTAKE = "src/app/(tabs)/visits/[visitId]/intake.tsx";
const REVIEW = "src/app/(tabs)/visits/[visitId]/review.tsx";
const PROGRESS = "src/components/QuestionProgress.tsx";
const GATE = "src/components/DialogueGate.tsx";
const THEMED = "src/components/Themed.tsx";
const PRESS_COMPONENT = "src/components/PressScale.tsx";
const FLAGS_EXPO = "src/lib/featureFlags.ts";
const CAPSULE = "src/lib/intake/progressCapsule.ts";
const MICRO = "src/lib/motion/micro.ts";
const ROLL_NATIVE = "src/lib/motion/native/numberRoll.ts";
const PRESS_NATIVE = "src/lib/motion/native/pressScale.ts";

afterEach(() => {
  vi.unstubAllEnvs();
});

function appJson(): ExpoConfig {
  return (JSON.parse(readFileSync(join(MOBILE, "app.json"), "utf8")) as { expo: ExpoConfig }).expo;
}

describe("1 · one flag, off unless a build asks", () => {
  it("app.config copies the build variable into extra.flags, and nothing else fills it", () => {
    expect(FLAGS_ENV).toBe("INTAKE_FLAGS");
    expect(resolveAppConfig(appJson(), {}).extra?.flags).toBe("");
    expect(resolveAppConfig(appJson(), { [FLAGS_ENV]: " progressMicro " }).extra?.flags).toBe(
      "progressMicro",
    );
    // Near miss: app.json cannot switch a flag on by itself.
    const smuggled = { ...appJson(), extra: { ...appJson().extra, flags: "progressMicro" } };
    expect(resolveAppConfig(smuggled, {}).extra?.flags).toBe("");
    expect(JSON.stringify(appJson())).not.toMatch(/progressMicro|progressNumberRoll/);
  });

  it("the default export reads the real process environment", () => {
    vi.stubEnv(FLAGS_ENV, "progressMicro");
    expect(appConfig({ config: appJson() } as ConfigContext).extra?.flags).toBe("progressMicro");
  });

  it("one Expo-bound reader resolves the flags, with the build's __DEV__", () => {
    const reader = source(FLAGS_EXPO);
    expect(reader).toMatch(/resolveFlags\(\s*extra\.flags,\s*\{\s*dev:\s*__DEV__\s*\}\s*\)/);
    const readers = TREE.filter((f) => /extra\??\.flags\b|\.flags\s*\?\?/.test(f.source)).map(
      (f) => f.name,
    );
    expect(readers).toEqual([FLAGS_EXPO]);
  });

  it("only the three redesigned screens read a flag; the progress takes them as a prop", () => {
    expect(importersOf("@/lib/featureFlags")).toEqual([GATE, INTAKE, REVIEW].sort());
  });
});

describe("1 · flag off keeps today's screens", () => {
  it("the progress keeps today's bar and line on its off branch", () => {
    const progress = source(PROGRESS);
    expect(progress).toMatch(
      /capsule === undefined \? \(\s*<>\s*<View style=\{\[styles\.track, \{ backgroundColor: theme\.surfaceRaised \}\]\}>\s*<View style=\{\[styles\.fill, \{ width: filled, backgroundColor: theme\.primary \}\]\} \/>\s*<\/View>\s*<AppText role="caption" color="inkSoft" style=\{styles\.count\}>\s*\{positionLabel\(position, word\)\}\s*<\/AppText>\s*<\/>/,
    );
  });

  it("the typed screen passes the capsule only under the flag", () => {
    expect(source(INTAKE)).toMatch(
      /<QuestionProgress\s+position=\{questionPosition\(applicable, question\.id, flowCanGrow\)\}\s+capsule=\{flags\.progressMicro \? \{ flow: applicable, flags \} : undefined\}/,
    );
  });

  it("the chips keep today's check on the off branch", () => {
    expect(source(INTAKE)).toMatch(
      /flags\.progressMicro \? \(\s*<ChipSlot\b[\s\S]{0,400}?\) : look\.check \? \(\s*<Icon\s+name="checkmark"/,
    );
  });

  it("an action without the opt-in is today's bare Pressable", () => {
    const themed = source(THEMED);
    const button = /export function PrimaryButton\([\s\S]*?\n\}/.exec(themed)![0];
    expect(button).toMatch(/pressScale \? <PressScale>\{render\}<\/PressScale> : render\(\)/);
    expect(button).toContain("pressScale = false");
  });

  it("the gate keeps its spinner unless the flag and Reduce Motion both say otherwise", () => {
    expect(source(GATE)).toMatch(
      /loadingIndicator\(\{ micro: flags\.progressMicro, reduce: reduceMotion \}\)/,
    );
    expect(source(GATE)).toContain("<ActivityIndicator color={theme.primary} />");
  });
});

describe("2 · a reader hears one value", () => {
  const progress = () => source(PROGRESS);

  it("both looks sit inside the one progressbar, whose value is the worded position", () => {
    const text = progress();
    expect(text.match(/accessibilityRole="progressbar"/g)).toHaveLength(1);
    expect(text).toMatch(/text: positionSpoken\(position, word, t\("intake\.progress\.of"\)\)/);
    const bar = text.indexOf('accessibilityRole="progressbar"');
    const capsule = text.indexOf("<CapsuleBody");
    const grows = text.indexOf('t("intake.progress.grows")');
    expect(capsule).toBeGreaterThan(bar);
    expect(grows).toBeGreaterThan(capsule);
  });

  it("the rolling glyphs are hidden and say nothing of their own", () => {
    const text = progress();
    // The function's body: from its signature's `) {` to the brace that
    // closes it at the start of a line.
    const start = text.indexOf("function RollingCount(");
    expect(start, "RollingCount").toBeGreaterThan(-1);
    const open = text.indexOf(") {\n", start);
    const body = text.slice(open, text.indexOf("\n}\n", open));
    expect(body).toContain("accessibilityElementsHidden");
    expect(body).toContain('importantForAccessibility="no-hide-descendants"');
    expect(body).toContain("<LayoutAnimationConfig skipEntering>");
    expect(body).not.toMatch(/accessibilityLabel|accessibilityValue|accessibilityRole/);
  });

  it("nothing announces a change: no live region and no announcement call", () => {
    expect(progress()).not.toMatch(
      /accessibilityLiveRegion|announceForAccessibility|useLiveAnnouncement|useLineAnnouncement|AnnouncedRegion/,
    );
  });
});

describe("3 · the numerals are display-only (invariant 22)", () => {
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
      expect(f.source, f.name).not.toMatch(
        /progressCapsule|capsuleCount|rollDigits|QuestionProgress|featureFlags/,
      );
    }
  });
});

describe("4 · motion stays inside the ratified bounds", () => {
  it("the capsule moves nothing of its own", () => {
    const text = source(PROGRESS);
    expect(text).not.toMatch(/withTiming|withSpring|useAnimatedStyle|useSharedValue|transition/);
    // Its one motion is the roll's entrance, granted by the policy, on glyphs
    // that skip it on the first mount.
    expect(text).toMatch(/numberRoll\(\{ flags: capsule\.flags, reduce, redPresented: false \}\)/);
    expect(text).toMatch(/<LayoutAnimationConfig skipEntering>[\s\S]*?entering=\{/);
  });

  it("the roll is opacity and the rise on the one fade, with no number of its own", () => {
    const native = source(ROLL_NATIVE);
    expect(native).toMatch(/import (?:type )?\{[^}]*\bNumberRoll\b[^}]*\} from "\.\.\/micro"/);
    expect(native).not.toMatch(/withSpring|withRepeat|scale|translateX|rotate/);
    const numbers = [...native.matchAll(/(?<![\w.])\d+(?:\.\d+)?(?![\w.])/g)].map((m) => m[0]);
    expect(numbers.filter((n) => n !== "0" && n !== "1")).toEqual([]);
    expect(importersOf("@/lib/motion/native/numberRoll")).toEqual([PROGRESS]);
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
    const opted = TREE.filter((f) => /\bpressScale=\{/.test(f.source)).map((f) => f.name);
    expect(opted.sort()).toEqual([INTAKE, REVIEW].sort());
    for (const name of opted) {
      for (const m of source(name).matchAll(/pressScale=\{([^}]*)\}/g)) {
        expect(m[1], name).toBe("flags.progressMicro");
      }
    }
    // The instrument commits on its own option, which never takes the prop.
    expect(source("src/components/InstrumentStep.tsx")).not.toMatch(/pressScale|PressScale/);
    expect(importersOf("@/components/PressScale")).toEqual([THEMED]);
    expect(source(PRESS_COMPONENT)).toMatch(
      /pressScale\(\{ enabled: true, reduce, redPresented: false \}\)/,
    );
  });

  it("no new file is a RED surface or paints a RED token", () => {
    for (const name of [PROGRESS, PRESS_COMPONENT, CAPSULE, MICRO, ROLL_NATIVE, PRESS_NATIVE]) {
      expect(source(name), name).not.toMatch(/\bemergency(Soft)?\b/);
    }
  });
});

describe("5 · the capsule is solid on a capture-protected screen", () => {
  it("draws no material", () => {
    expect(source(PROGRESS)).not.toMatch(
      /<GlassView\b|<BlurView\b|expo-blur|expo-glass-effect|useGlassMode|GlassContainer/,
    );
  });

  it("paints with the pure chrome, whose colours are opaque theme hexes", () => {
    expect(source(PROGRESS)).toContain("capsuleChrome(theme)");
  });
});

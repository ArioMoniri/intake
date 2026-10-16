/**
 * INT-499 (GitHub #849): ADR-039 and the Liquid Glass research on the
 * remaining screens, the visits list, documents, the share centre and
 * settings, as source facts. The pure policy is proved in
 * src/lib/stage/screens.test.ts; React Native has no DOM here, so this file
 * proves the wiring.
 *
 * 1. Each screen renders its new chrome: the stage palette and chrome from
 *    `useStageScreen`, the stage base under it, the large title in the stage
 *    ink, its content on the solid stage surface, its page actions as stage
 *    capsules.
 * 2. Capture-protected screens never mount glass (INT-477: documents and the
 *    share centre): no wash, no glass host, every action forced solid, and a
 *    solid bar. Near miss: the two unprotected screens do mount glass.
 * 3. Reduce Transparency and Increase Contrast draw solid: the screens read
 *    both through the one hook, and the policy answers solid for them.
 * 4. Reduce Motion: nothing on these screens moves, so there is nothing to
 *    stop. No Reanimated, no press scale, no interactive glass.
 * 5. No new string, no new glass host, and RED never reads the stage.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";

import { STAGE_SCREENS, type StageScreen } from "@/lib/stage/screens";

const MOBILE = join(__dirname, "..");

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
const TREE = walk(join(MOBILE, "src"))
  .filter((p) => /\.tsx?$/.test(p) && !/\.test\.ts$/.test(p))
  .map((p) => ({
    name: relative(MOBILE, p).split(sep).join("/"),
    source: code(readFileSync(p, "utf8")),
  }));

function source(name: string): string {
  const found = TREE.find((f) => f.name === name);
  expect(found, `${name} is missing`).toBeDefined();
  return found!.source;
}

/** The file a stage screen's route renders. */
const FILE = (screen: StageScreen): string => `src/app/${STAGE_SCREENS[screen].route}.tsx`;

const ALL: readonly StageScreen[] = ["visits", "records", "shares", "settings"];
const PROTECTED = ALL.filter((s) => STAGE_SCREENS[s].captureProtected);
const UNPROTECTED = ALL.filter((s) => !STAGE_SCREENS[s].captureProtected);

/**
 * The screens with a page action. The share centre has none: issuing a link
 * and stopping one are rows, and stay rows (INT-140's two-tap idiom).
 */
const WITH_ACTIONS: readonly StageScreen[] = ["visits", "records", "settings"];

/** Every `<Tag ...>` opening in `text`, props and all. */
function openings(text: string, tag: string): string[] {
  const found: string[] = [];
  const pattern = new RegExp(`<${tag}\\b`, "g");
  for (let m = pattern.exec(text); m !== null; m = pattern.exec(text)) {
    let depth = 0;
    let end = m.index;
    for (let i = m.index; i < text.length; i += 1) {
      const ch = text[i];
      if (ch === "{") depth += 1;
      if (ch === "}") depth -= 1;
      if (ch === ">" && depth === 0) {
        end = i;
        break;
      }
    }
    found.push(text.slice(m.index, end + 1));
  }
  return found;
}

/** Anything that draws, or asks for, a material. */
const GLASS =
  /expo-glass-effect|expo-blur|<GlassView\b|<GlassContainer\b|<BlurView\b|\bGlassBar\b|\bwithGlassNav\b|\bGlassNavBackground\b|\bwithStageNav\b|\bStageGlassGroup\b|\bGlassComposer\b|\bAmbientBackdrop\b/;

/** A protected screen's whole contract, as one predicate the near miss can reuse. */
function protectedViolations(text: string): string[] {
  const found: string[] = [];
  const glass = GLASS.exec(text);
  if (glass !== null) {
    found.push(`mounts ${glass[0]}`);
  }
  for (const button of openings(text, "StageButton")) {
    if (!/\ssolid(?=[\s/>])/.test(button)) {
      found.push(`an action that is not forced solid: ${button.replace(/\s+/g, " ")}`);
    }
  }
  if (!text.includes("useClinicalScreenPrivacy()")) {
    found.push("holds no capture protection");
  }
  return found;
}

describe("the screens and their capture protection agree with the source", () => {
  it("a stage screen is marked protected exactly when it calls useClinicalScreenPrivacy()", () => {
    for (const screen of ALL) {
      const calls = source(FILE(screen)).includes("useClinicalScreenPrivacy()");
      expect(calls, screen).toBe(STAGE_SCREENS[screen].captureProtected);
    }
    expect(PROTECTED).toEqual(["records", "shares"]);
    expect(UNPROTECTED).toEqual(["visits", "settings"]);
  });
});

describe.each(ALL)("%s renders its new chrome", (screen) => {
  const name = FILE(screen);

  it("resolves its palette and chrome from the one hook, by its own name", () => {
    expect(source(name)).toContain(`useStageScreen("${screen}")`);
  });

  it("paints the stage base under the screen", () => {
    expect(source(name)).toMatch(/<Screen\b[^>]*backgroundColor: palette\.base/);
  });

  it("draws the large title, a heading, in the stage ink", () => {
    expect(source(name)).toMatch(
      /<AppText\s+role="hero"\s+heading\s+style=\{\[styles\.heroLine, \{ color: palette\.ink \}\]\}/,
    );
  });

  it("sets its content on the solid stage surface", () => {
    expect(source(name)).toMatch(/<StageSurfaceProvider palette=\{palette\}>/);
  });

  it("its page actions are stage capsules: inert, untinted, never the old buttons", () => {
    const text = source(name);
    const buttons = openings(text, "StageButton");
    expect(buttons.length > 0, screen).toBe(WITH_ACTIONS.includes(screen));
    for (const button of buttons) {
      // ADR-039 S4: interactive glass is the dialogue's alone.
      expect(button, button).toContain("interactive={false}");
      // None of these is a forward step, so none is tinted (S3).
      expect(button, button).not.toMatch(/\bprominent\b/);
      expect(button, button).toContain("palette={palette}");
    }
    expect(text).not.toMatch(/<(?:PrimaryButton|SecondaryButton)\b/);
  });

  it("adds no motion, so Reduce Motion has nothing to stop", () => {
    const text = source(name);
    expect(text).not.toMatch(
      /react-native-reanimated|withSpring|withTiming|\bAnimated\.|PressScale|pressScale|isInteractive/,
    );
  });

  it("adds no visible string: every line is an existing catalogue key or a value", () => {
    expect(source(name)).not.toMatch(/<AppText\b[^>]*>\s*[A-Za-zÇĞİÖŞÜçğıöşü]/);
  });
});

describe.each(PROTECTED)("%s is capture-protected and never mounts glass", (screen) => {
  it("no wash, no glass host, every action forced solid", () => {
    expect(protectedViolations(source(FILE(screen)))).toEqual([]);
  });
});

describe("near miss: the unprotected screens do mount glass", () => {
  it.each(UNPROTECTED)("%s draws the wash and lets its actions be glass", (screen) => {
    const text = source(FILE(screen));
    expect(text).toMatch(/\{chrome\.backdrop \? <AmbientBackdrop palette=\{palette\} \/> : null\}/);
    const buttons = openings(text, "StageButton");
    expect(buttons.length).toBeGreaterThan(0);
    for (const button of buttons) {
      expect(button, button).toContain("solid={!chrome.glass}");
    }
    // The protected contract would refuse this screen.
    expect(protectedViolations(text).length).toBeGreaterThan(0);
  });
});

describe("the share centre's bar is solid", () => {
  const shares = () => source(FILE("shares"));

  it("rides the protected stage bar: opaque, the back chevron only, the title in the content", () => {
    expect(shares()).toContain(
      'options={withProtectedStageBar(headerOptions(t("shares.title")), palette)}',
    );
  });

  it("nothing scrolls under the bar, so the content no longer clears a transparent one", () => {
    expect(shares()).not.toMatch(/useHeaderHeight|paddingTop: headerHeight|headerTransparent/);
    expect(shares()).not.toContain("useGlassMode()");
  });
});

describe("the shared surface and controls follow the stage", () => {
  const HOOK = "src/components/stage/useStageScreen.ts";
  const SURFACE = "src/components/stage/StageSurface.tsx";

  it("useStageScreen reads the glass mode, the scheme and Increase Contrast, then asks the policy", () => {
    const hook = source(HOOK);
    expect(hook).toContain("useGlassMode()");
    expect(hook).toContain("useScheme()");
    expect(hook).toContain("useIncreasedContrast()");
    expect(hook).toMatch(/captureProtected: STAGE_SCREENS\[screen\]\.captureProtected/);
    expect(hook).toMatch(
      /stagePalette\(scheme, \{ reduceTransparency: chrome\.flat, increasedContrast \}\)/,
    );
  });

  it("the provider hands down the pure stageSurface, and draws nothing itself", () => {
    const surface = source(SURFACE);
    expect(surface).toContain("stageSurface(palette)");
    expect(surface).not.toMatch(GLASS);
  });

  it.each([
    ["src/components/Themed.tsx", "Card"],
    ["src/components/Themed.tsx", "SecondaryButton"],
    ["src/components/ListRow.tsx", "ListGroup"],
    ["src/components/Segmented.tsx", "Segmented"],
  ])("%s %s reads the stage surface", (file, fn) => {
    const text = source(file);
    const at = text.search(new RegExp(`export function ${fn}\\b`));
    expect(at, fn).toBeGreaterThanOrEqual(0);
    const next = text.slice(at + 1).search(/\nexport /);
    const body = next < 0 ? text.slice(at) : text.slice(at, at + 1 + next);
    expect(body).toContain("useStageSurface()");
  });

  it("an empty group draws no boundary, so Increase Contrast leaves no stray line", () => {
    // Found on the simulator: the share centre's empty groups are zero-height,
    // and their boundary drew as a 2 pt rule under each header.
    expect(source("src/components/ListRow.tsx")).toMatch(/stage === null \|\| rows\.length === 0/);
  });

  it("a stage action can be forced solid: the pane's solid branch takes `solid`", () => {
    const controls = source("src/components/stage/StageControls.tsx");
    expect(controls).toMatch(/if \(mode !== "liquid" \|\| solid\) \{/);
    expect(controls).toMatch(/solid=\{solid\}/);
  });

  it("the surface and the hook add no motion and no material", () => {
    for (const name of [HOOK, SURFACE]) {
      expect(source(name), name).not.toMatch(
        /react-native-reanimated|withSpring|withTiming|\bAnimated\.|<GlassView\b|<BlurView\b/,
      );
    }
  });
});

describe("RED never reads the stage (invariant 21)", () => {
  it("none of the four screens names a RED register or location", () => {
    for (const screen of ALL) {
      expect(source(FILE(screen)), screen).not.toMatch(/"ALERT"|"ON_SITE"|"DEFERRED_CLINICIAN"/);
    }
  });
});

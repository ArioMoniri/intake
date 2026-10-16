/**
 * INT-491: the orb's body, wired (GitHub #838; ADR-039 amendment, owner
 * 16 Oct 2026: "orb=lens … FIXY").
 *
 * The bounds are proved on the pure plans in lib/stage/orb.test.ts and
 * lib/stage/orbVariants.test.ts. This spec holds what the source alone can
 * show:
 *
 * - the lens is the orb: the default body, on the dialogue and on the welcome
 *   mark, and the only one a production build can draw; `classic` names the
 *   earlier sphere for development only;
 * - the sphere's two layers turn one way, read from the policy, and its body
 *   is pinned by its sha256;
 * - the flag is read in one place, through the pure parser, from build-time
 *   config;
 * - the lens draws only from its plan: every period is the plan's, the clear
 *   lens is drawn only where the plan says, and it is decoration nothing waits
 *   on;
 * - the blob and the particle field the exploration built left no runtime
 *   code; their captures live in docs/design/orb-variants/;
 * - every gradient stays in the two stage drawing files (ADR-039 S2).
 */
import { createHash } from "node:crypto";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";

const MOBILE = join(__dirname, "..");
const REPO = join(MOBILE, "..", "..");

/** Code only: comments explain what a file avoids, and a guard reads what it does. */
const code = (text: string): string =>
  text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");

const raw = (name: string): string => readFileSync(join(MOBILE, name), "utf8");
const source = (name: string): string => code(raw(name));

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
    source: readFileSync(path, "utf8"),
  }));

const ORB_IOS = "src/components/stage/VoiceOrb.ios.tsx";
const ORB_OTHER = "src/components/stage/VoiceOrb.tsx";
const PRESENCE = "src/components/PresenceOrb.tsx";
const DIALOGUE = "src/components/DialogueIntake.tsx";
const WELCOME = "src/app/(auth)/welcome.tsx";
const POLICY = "src/lib/stage/orbVariants.ts";
const FLAG = "src/lib/stage/expoOrbVariant.ts";
const ARCHIVE = join(REPO, "docs", "design", "orb-variants");

/**
 * The top-level function `name` in `text`, through its closing line: up to a
 * blank line before column-0 text, or the next top-level declaration.
 */
function topLevel(text: string, name: string): string {
  const at = text.search(new RegExp(`\\n(?:export )?function ${name}\\(`));
  expect(at, name).toBeGreaterThanOrEqual(0);
  const rest = text.slice(at + 1);
  const next = rest.slice(1).search(/\n\n(?=\S)|\n(?:export |function |const |interface |type )/);
  return next < 0 ? rest : rest.slice(0, next + 2);
}

const sha256 = (text: string): string => createHash("sha256").update(text).digest("hex");

describe("the lens is the orb (ADR-039 amendment: orb=lens)", () => {
  it("an absent variant is the lens; only `classic` draws the sphere", () => {
    const voice = topLevel(source(ORB_IOS), "VoiceOrb");
    expect(voice).toMatch(/props\.variant \?\? ORB_VARIANT_DEFAULT/);
    expect(voice).toMatch(
      /if \(variant === "classic"\) \{\s*return <OrbBody key=\{loops\} \{\.\.\.props\} \/>;/,
    );
    expect(voice).toMatch(/return <LensOrb key=\{`lens:\$\{loops\}`\} \{\.\.\.props\} \/>;/);
    expect(voice).toMatch(
      /const loops = `\$\{rotationPeriodS \?\? "still"\}:\$\{breathe\?\.periodS \?\? "still"\}`;/,
    );
  });

  it("the dialogue hands the orb the S1 motion untouched, and the build's body beside it", () => {
    const dialogue = source(DIALOGUE);
    expect(dialogue).toMatch(
      /const stageMotion = stageOrbMotion\(orbState, \{\s*reduce: reduceMotion,\s*redPresented: stopsDialogue,?\s*\}\)/,
    );
    expect(dialogue).toMatch(/stage=\{\{[\s\S]*?motion: stageMotion,[\s\S]*?variant: ORB_VARIANT,/);
    expect(dialogue).toMatch(/import \{ ORB_VARIANT \} from "@\/lib\/stage\/expoOrbVariant";/);
    expect(source(PRESENCE)).toMatch(/variant=\{stage\.variant\}/);
  });

  it("the welcome mark is the same orb drawn still (ADR-039 S7)", () => {
    const welcome = source(WELCOME);
    expect(welcome).toMatch(/<VoiceOrb\b[^>]*motion=\{stillOrb\(\)\}[^>]*variant=\{ORB_VARIANT\}/);
    expect(welcome).toMatch(/import \{ ORB_VARIANT \} from "@\/lib\/stage\/expoOrbVariant";/);
  });

  it("off iOS the orb stays the still disc, whatever the body", () => {
    const other = source(ORB_OTHER);
    expect(other).not.toMatch(/lensPlan|\bvariant ===/);
    expect(other).toMatch(/backgroundColor: palette\.orb\[1\]/);
  });
});

describe("the sphere's layers turn one way (ADR-039 amendment: FIXY)", () => {
  it("the second layer reads its factor and its direction from the policy", () => {
    const sphere = topLevel(source(ORB_IOS), "OrbBody");
    expect(sphere).not.toMatch(/rotationEffect\(-/);
    expect(sphere).toMatch(/rotationEffect\(turn \* STAGE_ORB_SECOND_LAYER\.direction\)/);
    expect(sphere).toMatch(
      /duration: motion\.rotationPeriodS \* STAGE_ORB_SECOND_LAYER\.periodFactor/,
    );
    expect(source(ORB_IOS)).not.toMatch(/\bCOUNTER_TURN\b/);
  });

  it("near miss: a counter-turn written back would be caught", () => {
    const bad = "rotationEffect(-turn),";
    expect(bad).toMatch(/rotationEffect\(-/);
  });

  it("the sphere's body is pinned: a change to it is a change to ADR-039 S1", () => {
    // Pinned after the owner's FIXY (16 Oct 2026). Update this hash only with
    // an ADR-039 decision.
    const body = topLevel(raw(ORB_IOS), "OrbBody");
    expect(sha256(body)).toBe("02373dde5bcac515d041c9fecfd13f7e61233a68462a320114b664c68ebdd304");
    const orb = source(ORB_IOS);
    expect(orb).toMatch(/const FOREVER = 100_000;/);
    expect(orb).toMatch(/const GLOW_BLUR = 18;/);
  });
});

describe("the flag is read once, from build-time config, through the pure parser", () => {
  it("one module reads extra.orbVariant, and parses it with orbVariantFrom", () => {
    const flag = source(FLAG);
    expect(flag).toMatch(/Constants\.expoConfig\?\.extra/);
    expect(flag).toMatch(/export const ORB_VARIANT: OrbVariant = orbVariantFrom\(/);
    const readers = TREE.filter((f) => /\borbVariant\b/.test(code(f.source))).map((f) => f.name);
    expect(readers).toEqual([FLAG]);
  });

  it("no app file reads the variable itself: app.config.ts is its only reader", () => {
    const VAR = ["EXPO_PUBLIC_ORB", "VARIANT"].join("_");
    expect(TREE.filter((f) => code(f.source).includes(VAR)).map((f) => f.name)).toEqual([]);
    expect(raw("app.config.ts")).toContain(VAR);
  });

  it("the policy is pure: no React Native, Expo or Reanimated import", () => {
    const policy = source(POLICY);
    const from = [...policy.matchAll(/from "([^"]+)"/g)].map((m) => m[1]);
    expect(from.length).toBeGreaterThan(0);
    expect(from.filter((s) => /react|expo|native/.test(s))).toEqual([]);
  });
});

describe("the lens draws only from its plan", () => {
  it("it takes its plan from lensPlan and the S1 motion", () => {
    const lens = topLevel(source(ORB_IOS), "LensOrb");
    expect(lens).toMatch(/lensPlan\(motion, \{ glass \}\)/);
    expect(lens).toMatch(/if \(!plan\.visible\) \{\s*return null;/);
  });

  it("every loop's period is read from the policy or the plan, never written", () => {
    const orb = source(ORB_IOS);
    expect(orb).not.toMatch(/duration:\s*\d/);
    const durations = [...orb.matchAll(/duration:\s*([^,}\n]+)/g)].map((m) => m[1].trim());
    expect(durations.length).toBeGreaterThan(2);
    for (const value of durations) {
      expect(value).toMatch(
        /^(?:motion\.rotationPeriodS(?: \* STAGE_ORB_SECOND_LAYER\.periodFactor)?|motion\.breathe\.periodS \/ 2|periodS(?: \/ 2)?)$/,
      );
    }
  });

  it("the clear lens is drawn by the sphere under `glass` and by the lens only under plan.lens", () => {
    const orb = source(ORB_IOS);
    expect(orb.match(/glassEffect\(/g)).toHaveLength(2);
    expect(topLevel(orb, "OrbBody")).toMatch(/\{glass \? \(\s*<Circle[\s\S]*?glassEffect\(/);
    expect(topLevel(orb, "LensOrb")).toMatch(/\{plan\.lens \? \(\s*<Circle[\s\S]*?glassEffect\(/);
  });

  it("the lens is decoration: hidden from the accessibility tree, not pressable, nothing waits on it", () => {
    const lens = topLevel(source(ORB_IOS), "LensOrb");
    expect(lens).toMatch(/pointerEvents="none"/);
    expect(lens).toMatch(/\baccessibilityElementsHidden\b/);
    expect(lens).toMatch(/importantForAccessibility="no-hide-descendants"/);
    const orb = source(ORB_IOS);
    expect(orb).not.toMatch(/\bPressable\b|\bonPress\b|\bawait\b|\.then\(|\bPromise\b/);
    // The only callback is the Host's first layout, which starts the loops.
    const callbacks = [...orb.matchAll(/\b(on[A-Z]\w*)=/g)].map((m) => m[1]);
    expect(new Set(callbacks)).toEqual(new Set(["onLayoutContent"]));
  });

  it("gradients stay in the two stage drawing files (ADR-039 S2)", () => {
    const GRADIENT = /\b(?:linear|radial|angular)Gradient\b|\bLinearGradient\b/;
    const drawing = TREE.filter((f) => GRADIENT.test(code(f.source))).map((f) => f.name);
    expect(drawing.sort()).toEqual(
      ["src/components/stage/AmbientBackdrop.ios.tsx", ORB_IOS].sort(),
    );
  });
});

describe("the blob and the particle field are not shipped (owner: O2-O9 N)", () => {
  it("no runtime code is left for them", () => {
    const LEFTOVER =
      /\b(?:BlobBody|FieldBody|fieldDots|FieldOrbit|BlobLobe|VoiceOrbParts)\b|"blob"|"field"/;
    expect(TREE.filter((f) => LEFTOVER.test(code(f.source))).map((f) => f.name)).toEqual([]);
    expect(existsSync(join(MOBILE, "src/components/stage/VoiceOrbParts.tsx"))).toBe(false);
  });

  it("near miss: a leftover body would be found", () => {
    expect(/\bBlobBody\b/.test("function BlobBody() {}")).toBe(true);
  });

  it("their captures are archived in the docs, and library-patterns §6 points at them", () => {
    for (const name of [
      "blob-listening-light.jpg",
      "blob-listening-dark.jpg",
      "field-listening-light.jpg",
      "field-listening-dark.jpg",
      "blob-cycle-dark.gif",
      "field-cycle-dark.gif",
    ]) {
      expect(existsSync(join(ARCHIVE, name)), name).toBe(true);
    }
    const map = readFileSync(join(REPO, "docs", "design", "library-patterns.md"), "utf8");
    expect(map).toContain("docs/design/orb-variants/");
  });
});

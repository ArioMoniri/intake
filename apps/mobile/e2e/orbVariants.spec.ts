/**
 * INT-491: the orb variants' wiring (GitHub #838).
 *
 * The bounds are proved on the pure plan in lib/stage/orbVariants.test.ts.
 * This spec holds what the source alone can show:
 *
 * - flag off, the orb is unchanged: the sphere's body is byte-for-byte the
 *   ADR-039 one, the dialogue still passes the S1 motion untouched, and the
 *   welcome mark never takes a variant;
 * - the flag is read in one place, through the pure parser, from build-time
 *   config;
 * - a variant body draws only from its plan: every period is the plan's,
 *   the clear lens is drawn only where the plan says, and it is decoration
 *   that nothing waits on;
 * - every gradient of the variants is drawn in the one orb drawing file, so
 *   the gradient allow-list (ADR-039 S2) does not grow; their plain parts
 *   (VoiceOrbParts.tsx) draw no gradient and no glass, and only the iOS orb
 *   imports them.
 */
import { createHash } from "node:crypto";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";

const MOBILE = join(__dirname, "..");

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
const PARTS = "src/components/stage/VoiceOrbParts.tsx";
const PRESENCE = "src/components/PresenceOrb.tsx";
const DIALOGUE = "src/components/DialogueIntake.tsx";
const WELCOME = "src/app/(auth)/welcome.tsx";
const POLICY = "src/lib/stage/orbVariants.ts";
const FLAG = "src/lib/stage/expoOrbVariant.ts";

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

describe("flag off: the orb is the ADR-039 sphere, unchanged", () => {
  it("the sphere's body is byte-for-byte the one ADR-039 shipped", () => {
    // Pinned on INT-491's base (#808). A change to the sphere is a change to
    // ADR-039 S1, not a side effect of a variant: update this hash only with
    // that decision.
    const body = topLevel(raw(ORB_IOS), "OrbBody");
    expect(sha256(body)).toBe("18d54e06da8767e031d1fdf478f8f2e2718dee961157fa556ce65ad994ecb758");
    const orb = source(ORB_IOS);
    expect(orb).toMatch(/const FOREVER = 100_000;/);
    expect(orb).toMatch(/const COUNTER_TURN = 1\.6;/);
    expect(orb).toMatch(/const GLOW_BLUR = 18;/);
  });

  it("the classic variant renders that body, keyed as before, with the motion it was given", () => {
    const voice = topLevel(source(ORB_IOS), "VoiceOrb");
    expect(voice).toMatch(/props\.variant \?\? ORB_VARIANT_OFF/);
    expect(voice).toMatch(
      /if \(variant === ORB_VARIANT_OFF\) \{\s*return <OrbBody key=\{loops\} \{\.\.\.props\} \/>;/,
    );
    expect(voice).toMatch(
      /const loops = `\$\{rotationPeriodS \?\? "still"\}:\$\{breathe\?\.periodS \?\? "still"\}`;/,
    );
  });

  it("the dialogue still hands the orb the S1 motion untouched, and the variant beside it", () => {
    const dialogue = source(DIALOGUE);
    expect(dialogue).toMatch(
      /const stageMotion = stageOrbMotion\(orbState, \{ reduce: reduceMotion, redPresented: false \}\)/,
    );
    expect(dialogue).toMatch(/stage=\{\{[\s\S]*?motion: stageMotion,[\s\S]*?variant: ORB_VARIANT,/);
    expect(dialogue).toMatch(/import \{ ORB_VARIANT \} from "@\/lib\/stage\/expoOrbVariant";/);
    expect(source(PRESENCE)).toMatch(/variant=\{stage\.variant\}/);
  });

  it("the welcome mark never takes a variant: it is the sphere drawn still (ADR-039 S7)", () => {
    const welcome = source(WELCOME);
    expect(welcome).toMatch(/<VoiceOrb\b/);
    expect(welcome).not.toMatch(/\bvariant\b|orbVariant|ORB_VARIANT/);
  });

  it("off iOS the orb stays the still disc for every variant", () => {
    const other = source(ORB_OTHER);
    expect(other).not.toMatch(/orbVariantPlan|\bvariant ===/);
    expect(other).toMatch(/backgroundColor: palette\.orb\[1\]/);
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

describe("a variant draws only from its plan", () => {
  it("the variant body takes its plan from orbVariantPlan and the S1 motion", () => {
    const body = topLevel(source(ORB_IOS), "VariantBody");
    expect(body).toMatch(/orbVariantPlan\(variant, motion, \{ glass \}\)/);
    expect(body).toMatch(/if \(!plan\.visible\) \{\s*return null;/);
  });

  it("every loop's period is read from the plan, never written", () => {
    const orb = source(ORB_IOS) + source(PARTS);
    expect(orb).not.toMatch(/duration:\s*\d/);
    const durations = [...orb.matchAll(/duration:\s*([^,}\n]+)/g)].map((m) => m[1].trim());
    expect(durations.length).toBeGreaterThan(2);
    for (const value of durations) {
      expect(value).toMatch(
        /^(?:motion\.rotationPeriodS(?: \* COUNTER_TURN)?|motion\.breathe\.periodS \/ 2|periodS(?: \/ 2)?)$/,
      );
    }
  });

  it("the clear lens is drawn by the sphere under `glass` and by a variant only under plan.lens", () => {
    const orb = source(ORB_IOS);
    expect(orb.match(/glassEffect\(/g)).toHaveLength(2);
    const sphere = topLevel(orb, "OrbBody");
    expect(sphere).toMatch(/\{glass \? \(\s*<Circle[\s\S]*?glassEffect\(/);
    const lens = topLevel(orb, "LensBody");
    expect(lens).toMatch(/\{plan\.lens \? \(\s*<Circle[\s\S]*?glassEffect\(/);
    for (const name of ["BlobBody", "FieldBody"]) {
      expect(topLevel(orb, name), name).not.toMatch(/glassEffect\(/);
    }
    expect(source(PARTS)).not.toMatch(/glassEffect\(/);
  });

  it("a variant is decoration: hidden from the accessibility tree, not pressable, and nothing waits on it", () => {
    const body = topLevel(source(ORB_IOS), "VariantBody");
    expect(body).toMatch(/pointerEvents="none"/);
    expect(body).toMatch(/\baccessibilityElementsHidden\b/);
    expect(body).toMatch(/importantForAccessibility="no-hide-descendants"/);
    const orb = source(ORB_IOS) + source(PARTS);
    expect(orb).not.toMatch(/\bPressable\b|\bonPress\b|\bawait\b|\.then\(|\bPromise\b/);
    // The only callback is the Host's first layout, which starts the loops.
    const callbacks = [...orb.matchAll(/\b(on[A-Z]\w*)=/g)].map((m) => m[1]);
    expect(new Set(callbacks)).toEqual(new Set(["onLayoutContent"]));
  });

  it("every variant gradient is drawn in the orb's one drawing file, so the gradient allow-list does not grow", () => {
    const GRADIENT = /\b(?:linear|radial|angular)Gradient\b|\bLinearGradient\b/;
    const drawing = TREE.filter((f) => GRADIENT.test(code(f.source))).map((f) => f.name);
    expect(drawing.sort()).toEqual(
      ["src/components/stage/AmbientBackdrop.ios.tsx", ORB_IOS].sort(),
    );
    expect(GRADIENT.test(source(PARTS))).toBe(false);
  });

  it("the plain parts are the iOS orb's alone", () => {
    const importers = TREE.filter((f) =>
      /from "\.\/VoiceOrbParts"|stage\/VoiceOrbParts"/.test(code(f.source)),
    ).map((f) => f.name);
    expect(importers).toEqual([ORB_IOS]);
  });
});

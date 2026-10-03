/**
 * INT-466: the chat stage (ADR-039; docs/design/liquid-glass-research.md).
 *
 * The pure bounds are proved in lib/stage/{orb,palette,shape}.test.ts. This
 * spec holds the wiring the source alone can show:
 *
 * - the live dialogue paints the ambient backdrop from the stage palette,
 *   and the palette follows Reduce Transparency and Increase Contrast;
 * - the one presence orb takes the stage body, with motion from the S1
 *   policy keyed on `orbStateFor`'s state;
 * - glass is on the control layer only: the composer, its control and the
 *   turn actions share one GlassContainer; content (messages, answer cards,
 *   the question) is never glass;
 * - only the primary action is tinted; interactive glass lives in the stage
 *   controls; Reduce Transparency draws every glass surface solid;
 * - gradients live in the two stage drawing files alone;
 * - the note's progress is a native bar item that shows its count;
 * - the dev prototype route is gone.
 */
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";

const MOBILE = join(__dirname, "..");

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
    source: readFileSync(path, "utf8"),
  }));

const DIALOGUE = "src/components/DialogueIntake.tsx";
const CONTROLS = "src/components/stage/StageControls.tsx";
const BACKDROP_IOS = "src/components/stage/AmbientBackdrop.ios.tsx";
const ORB_IOS = "src/components/stage/VoiceOrb.ios.tsx";
const PRESENCE = "src/components/PresenceOrb.tsx";

/** The source of the exported function `name` in `text`, to the next export. */
function exported(text: string, name: string): string {
  const at = text.search(new RegExp(`export function ${name}\\b`));
  expect(at, name).toBeGreaterThanOrEqual(0);
  const next = text.slice(at + 1).search(/\nexport /);
  return next < 0 ? text.slice(at) : text.slice(at, at + 1 + next);
}

describe("the stage under the live dialogue", () => {
  it("the dialogue paints the ambient backdrop from the stage palette", () => {
    const dialogue = source(DIALOGUE);
    expect(dialogue).toMatch(/<AmbientBackdrop palette=\{palette\} \/>/);
    expect(dialogue).toMatch(
      /const palette = stagePalette\(scheme, \{\s*reduceTransparency: glassMode !== "liquid",\s*increasedContrast,?\s*\}\)/,
    );
  });

  it("the one presence orb takes the stage body, its motion keyed on orbStateFor's state", () => {
    const dialogue = source(DIALOGUE);
    expect(dialogue.match(/<PresenceOrb\b/g)).toHaveLength(1);
    expect(dialogue).toMatch(
      /const stageMotion = stageOrbMotion\(orbState, \{ reduce: reduceMotion, redPresented: false \}\)/,
    );
    expect(dialogue).toMatch(/<PresenceOrb\b[\s\S]*?stage=\{\{[\s\S]*?motion: stageMotion/);
    // The level reaches the stage orb as the sampler's shared value, through a
    // worklet, so a sample renders no React tree (MOTION-7).
    expect(source(PRESENCE)).toMatch(/levelScale\(level\.get\(\)/);
  });

  it("the dialogue no longer rides the old glass bar", () => {
    expect(source(DIALOGUE)).not.toMatch(/<GlassBar\b/);
  });
});

describe("ADR-039 S3: glass on the control layer, never on content", () => {
  it("the dialogue itself draws no glass: content stays solid", () => {
    expect(source(DIALOGUE)).not.toMatch(/<GlassView\b|<GlassContainer\b|glassEffect\(/);
  });

  it("answer cards are solid: no glass in the card", () => {
    const card = exported(source(CONTROLS), "AnswerCard");
    expect(card).not.toMatch(/<GlassView\b|<Pane\b|glassEffect/);
    expect(card).toMatch(/backgroundColor: selected \? palette\.cardSelected : palette\.card/);
  });

  it("the composer, its control and the turn actions share one GlassContainer", () => {
    const controls = source(CONTROLS);
    expect(exported(controls, "StageGlassGroup")).toMatch(/<GlassContainer\b/);
    const dialogue = source(DIALOGUE);
    expect(dialogue).toMatch(/<StageGlassGroup\b[\s\S]*<GlassComposer\b[\s\S]*<\/StageGlassGroup>/);
    expect(dialogue).toMatch(/<StageGlassGroup\b[\s\S]*<StageButton\b[\s\S]*<\/StageGlassGroup>/);
    // The field and its control are two glass shapes that merge, never a
    // glass disc on a glass capsule (no glass on glass).
    const composer = exported(controls, "GlassComposer");
    expect(composer.match(/<Pane\b/g)).toHaveLength(2);
  });

  it("only the primary action is tinted", () => {
    const button = exported(source(CONTROLS), "StageButton");
    expect(button).toMatch(/tint=\{prominent \? palette\.cardSelected : undefined\}/);
    const composer = exported(source(CONTROLS), "GlassComposer");
    expect(composer).toMatch(/tint=\{control === "send" \? palette\.cardSelected : undefined\}/);
  });

  it("every glass surface has a solid answer for Reduce Transparency", () => {
    const controls = source(CONTROLS);
    expect(controls).toContain("useGlassMode()");
    expect(controls).toMatch(/mode !== "liquid"/);
    expect(controls).toMatch(/backgroundColor: tint \?\? palette\.card/);
  });

  it("near miss: a GlassView in the answer card would be caught", () => {
    const bad =
      "export function AnswerCard() { return <GlassView style={s} />; }\nexport const x = 1;";
    expect(exported(bad, "AnswerCard")).toMatch(/<GlassView\b/);
  });
});

describe("ADR-039 S2: gradients live in the two stage drawing files alone", () => {
  it("no other file draws a gradient", () => {
    const GRADIENT = /\b(?:linear|radial|angular)Gradient\b|\bLinearGradient\b/;
    const drawing = TREE.filter((f) => GRADIENT.test(code(f.source)))
      .map((f) => f.name)
      .sort();
    expect(drawing).toEqual([BACKDROP_IOS, ORB_IOS].sort());
  });

  it("the orb's loops take their periods from the S1 policy, never a literal", () => {
    const orb = source(ORB_IOS);
    expect(orb).toMatch(/duration: motion\.rotationPeriodS/);
    expect(orb).toMatch(/duration: motion\.breathe\.periodS \/ 2/);
    expect(orb).not.toMatch(/duration:\s*\d/);
  });
});

describe("the native top bar", () => {
  it("the note's progress is a native bar item: its visible count, and a spoken name that holds it", () => {
    const dialogue = source(DIALOGUE);
    expect(dialogue).toMatch(/unstable_headerRightItems:/);
    // The count is the item's label, so the system draws it in the bar's
    // own glass; an icon would replace the words (UIKit shows one or the
    // other), and the count is what the patient reads.
    expect(dialogue).toMatch(/label: stripTitle,/);
    expect(dialogue).toMatch(/accessibilityLabel: stripLabel/);
    // SC 2.5.3: the spoken name contains the visible label.
    expect(dialogue).toMatch(
      /const stripLabel = joinParts\(t\("dialogue\.noteForming"\), stripTitle\)/,
    );
  });
});

describe("RED never reads the stage (ADR-039 S6, invariant 21)", () => {
  /** A file on the RED path names a RED register or location. */
  const RED_PATH = /"ALERT"|"ON_SITE"|"DEFERRED_CLINICIAN"/;
  const STAGE_IMPORT = /from "@\/lib\/stage\/|from "\.\.?\/(?:lib\/)?stage\//;

  it("no file on the RED path imports the stage's palette, motion or shapes", () => {
    const red = TREE.filter((f) => RED_PATH.test(code(f.source)));
    expect(red.length).toBeGreaterThan(0);
    expect(red.filter((f) => STAGE_IMPORT.test(f.source)).map((f) => f.name)).toEqual([]);
  });

  it("near miss: a RED-path file that imported the stage palette would be found", () => {
    const fake = 'import { stagePalette } from "@/lib/stage/palette";\nconst r = "ALERT";';
    expect(RED_PATH.test(fake) && STAGE_IMPORT.test(fake)).toBe(true);
  });
});

describe("the prototype is gone", () => {
  it("no dev route draws the stage any more: the live dialogue does", () => {
    expect(existsSync(join(MOBILE, "src/app/prototype"))).toBe(false);
  });
});

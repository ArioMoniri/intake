/**
 * INT-462: the native chat (docs/design/library-patterns.md P1–P5; ADR-038 A1
 * and A2).
 *
 * The pure rules are proved in lib/dialogue/composer.test.ts,
 * lib/motion/bubbles.test.ts, lib/motion/haptics.test.ts and
 * lib/intake/questionScreen.test.ts. This spec holds the wiring the source
 * alone can show:
 *
 * - the composer is one filled capsule on the glass bar, with its one trailing
 *   control inside it, chosen by `composerTrailing`;
 * - the mic opens the microphone only from that control's press, through the
 *   session's own paths, and asks for its tick before it does;
 * - the confirm chips are INT-433's filled, checked capsules, and a change
 *   asks for the selection tick;
 * - a new agent bubble enters through the A1 spring, the arbiter deciding;
 * - nothing here paints RED, and the new copy carries no numeral.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { en } from "../src/lib/i18n/en";
import { tr } from "../src/lib/i18n/tr";

const MOBILE = join(__dirname, "..");

/** Code only: comments explain what a file avoids, and a guard reads what it does. */
const code = (text: string): string =>
  text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");

const source = (name: string): string => code(readFileSync(join(MOBILE, name), "utf8"));

const DIALOGUE = "src/components/DialogueIntake.tsx";
const INTAKE = "src/app/(tabs)/visits/[visitId]/intake.tsx";

const CONTROLS = "src/components/stage/StageControls.tsx";

/** The source of one exported stage control, to the next export. */
function control(name: string): string {
  const text = source(CONTROLS);
  const at = text.indexOf(`export function ${name}`);
  expect(at, name).toBeGreaterThanOrEqual(0);
  const next = text.indexOf("\nexport ", at + 1);
  return next < 0 ? text.slice(at) : text.slice(at, next);
}

describe("P1/P2 on the stage (INT-466, ADR-039 S3): the field and its control", () => {
  it("the composer is the stage's field and its one control, in the stage's glass group", () => {
    const dialogue = source(DIALOGUE);
    expect(dialogue).toMatch(/<StageGlassGroup>[\s\S]*<GlassComposer\b[\s\S]*<\/StageGlassGroup>/);
    const composer = control("GlassComposer");
    expect(composer.match(/<TextInput\b/g)).toHaveLength(1);
    expect(composer).toMatch(/styles\.controlTarget/);
  });

  it("the field shows the accent ring while focused, and no outline at rest", () => {
    expect(control("GlassComposer")).toMatch(
      /borderWidth: focused \? 2 : 0, borderColor: palette\.accent/,
    );
    expect(source(DIALOGUE)).toMatch(/focused=\{composerFocused\}/);
  });

  it("the trailing control is chosen by composerTrailing, in a 44 pt target box", () => {
    const dialogue = source(DIALOGUE);
    expect(dialogue).toMatch(
      /const trailing = composerTrailing\(\{ draft, phase: turn\.phase \}\)/,
    );
    expect(dialogue).toMatch(/control=\{trailing\.kind\}/);
    expect(dialogue).toMatch(/onControl=\{pressTrailing\}/);
    // The control's own target box (the app's slop is vertical only).
    expect(source(CONTROLS)).toMatch(
      /controlTarget: \{\s*width: STAGE_SIZE\.composer,\s*height: STAGE_SIZE\.composer,\s*minHeight: MIN_TAP,/,
    );
  });

  it("the transcript follows the newest turn again when the bar re-measures", () => {
    // Found on the simulator: a confirm turn adds two CTAs to the bar, the
    // bar reports its new height after the follow already ran, and the last
    // chip row sat under the bar until the patient scrolled.
    const dialogue = source(DIALOGUE);
    const follow = dialogue.match(
      /useEffect\(\(\) => \{\s*const frame = requestAnimationFrame\(\(\) =>\s*scrollRef\.current\?\.scrollToEnd[\s\S]*?\}, \[([^\]]*)\]\);/,
    );
    expect(follow, "the follow effect").not.toBeNull();
    const deps = (follow?.[1] ?? "").split(",").map((dep) => dep.trim());
    expect(deps).toEqual(expect.arrayContaining(["streamLength", "turn.phase", "barClearance"]));
  });
});

describe("P3: the mic opens only on tap, through the session's own paths", () => {
  it("the mic's press asks for the tick, then barges in or takes the correction", () => {
    const dialogue = source(DIALOGUE);
    const press = dialogue.slice(dialogue.indexOf("const pressTrailing"));
    const body = press.slice(0, press.indexOf("\n  };\n"));
    expect(body).toMatch(
      /haptic\("select", \{ surface: "dialogueMic", valueChanged: true \}\);[\s\S]*?session\.bargeIn\(\)/,
    );
    expect(body).toMatch(/session\.speakCorrection\(\)/);
    expect(body).toMatch(/void session\.finishListening\(\)/);
  });

  it("near miss: no effect opens the microphone on the composer's behalf", () => {
    const dialogue = source(DIALOGUE);
    for (const effect of dialogue.split("useEffect(").slice(1)) {
      const body = effect.slice(0, effect.indexOf("\n  }, ["));
      expect(body).not.toMatch(/bargeIn|speakCorrection|pressTrailing/);
    }
  });

  it("the trailing control names itself for each kind, and the mic carries its hint", () => {
    const dialogue = source(DIALOGUE);
    for (const key of [
      "dialogue.send",
      "dialogue.mic",
      "voiceFirst.stop",
      "a11y.dialogue.micHint",
    ]) {
      expect(dialogue).toContain(`"${key}"`);
    }
  });
});

describe("P5: the confirm chips are filled, checked answer cards", () => {
  it("each chip is the stage's answer card, filled and checked when selected", () => {
    const dialogue = source(DIALOGUE);
    expect(dialogue).toMatch(/<AnswerCard\b[\s\S]*?selected=\{on\}/);
    const card = control("AnswerCard");
    expect(card).toMatch(/\{selected \? <Icon name="checkmark"/);
    expect(card).toContain("backgroundColor: selected ? palette.cardSelected : palette.card");
    expect(card).toMatch(/accessibilityState=\{\{ checked: selected \}\}/);
    expect(dialogue).not.toMatch(/borderColor: on \? theme\.primary/);
  });

  it("a chip change asks for the selection tick, in the dialogue and on the question screen", () => {
    expect(source(DIALOGUE)).toMatch(
      /haptic\("select", \{ surface: "intakeChip", valueChanged: true \}\)/,
    );
    const intake = source(INTAKE);
    expect(intake).toMatch(/haptic\("select", \{ surface: "intakeChip", valueChanged: true \}\)/);
    // A validated instrument's options never ask (ADR-038 A2).
    expect(source("src/components/InstrumentStep.tsx")).not.toMatch(/\bhaptic\s*\(/);
  });
});

describe("ADR-038 A1: a new agent bubble springs in, the arbiter deciding", () => {
  it("stream entries enter through bubbleEntering, granted by the arbiter", () => {
    const dialogue = source(DIALOGUE);
    expect(dialogue).toMatch(
      /entering=\{bubbleEntering\(\s*bubbleEntrance\(\{\s*granted: bubbleGranted\(transients, key, reduceMotion\),/,
    );
  });

  it("the chips keep the one fade; only bubbles spring", () => {
    const dialogue = source(DIALOGUE);
    expect(dialogue).toMatch(
      /key=\{nodeKey\(transients, scene\.chips\)\}\s*entering=\{enteringFor\(fadeOf\(transients, scene\.chips, motionContext\)\)\}/,
    );
  });
});

describe("unchanged and safe", () => {
  it("the dialogue paints no RED token", () => {
    expect(source(DIALOGUE)).not.toMatch(/\bemergency(Soft)?\b/);
  });

  it("the new copy is siz-register, carries no numeral, and exists in both catalogues", () => {
    for (const key of ["dialogue.mic", "a11y.dialogue.micHint"] as const) {
      expect(tr[key], key).toBeTruthy();
      expect(en[key], key).toBeTruthy();
      expect(tr[key]).not.toMatch(/\d/);
      expect(en[key]).not.toMatch(/\d/);
      // siz: never the informal imperative or pronoun.
      expect(tr[key]).not.toMatch(/\bsen\b|\bsana\b|\bseni\b/i);
    }
    expect(tr["dialogue.mic"]).toBe("Konuşarak yanıtlayın");
  });
});

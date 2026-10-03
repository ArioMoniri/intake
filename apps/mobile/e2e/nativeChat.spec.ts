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

/** The JSX from `<Tag` that opens the first match of `marker`, to its closing tag. */
function element(text: string, tag: string, marker: RegExp): string {
  const at = text.search(marker);
  expect(at, String(marker)).toBeGreaterThanOrEqual(0);
  const open = text.lastIndexOf(`<${tag}`, at);
  let depth = 0;
  const pattern = new RegExp(`<${tag}\\b|</${tag}>`, "g");
  pattern.lastIndex = open;
  for (let m = pattern.exec(text); m !== null; m = pattern.exec(text)) {
    depth += m[0].startsWith("</") ? -1 : 1;
    if (depth === 0) {
      return text.slice(open, m.index + m[0].length);
    }
  }
  return text.slice(open);
}

describe("P1/P2: the composer is one capsule on the glass bar", () => {
  it("the field and the trailing control share the capsule row", () => {
    const dialogue = source(DIALOGUE);
    const capsule = element(dialogue, "View", /style=\{\[\s*styles\.composerRow/);
    expect(capsule).toContain("<TextInput");
    expect(capsule).toMatch(/styles\.sendButton/);
    expect(dialogue).toMatch(/<GlassBar\b[^>]*>[\s\S]*styles\.composerRow[\s\S]*<\/GlassBar>/);
  });

  it("the capsule is INT-433's filled field: solid fill, tint ring when focused, no resting outline", () => {
    const dialogue = source(DIALOGUE);
    expect(dialogue).toMatch(
      /filledFieldChrome\(theme, \{ focused: composerFocused, increasedContrast \}\)/,
    );
    expect(dialogue).toMatch(/composerRow: \{[^}]*borderRadius: radius\.chip/);
    // The old separate field with its own resting outline is gone.
    expect(dialogue).not.toMatch(/composerField: \{[^}]*borderWidth: 1/);
  });

  it("the trailing control is chosen by composerTrailing, and stays one Pressable", () => {
    const dialogue = source(DIALOGUE);
    expect(dialogue).toMatch(
      /const trailing = composerTrailing\(\{ draft, phase: turn\.phase \}\)/,
    );
    const send = dialogue.match(/styles\.sendButton/g) ?? [];
    expect(send.length).toBeGreaterThanOrEqual(1);
    // A 44 pt target box of its own (the app's slop is vertical only), with
    // the 32 pt disc drawn inside it.
    expect(dialogue).toMatch(/sendButton: \{\s*width: MIN_TAP,\s*height: MIN_TAP,/);
    expect(dialogue).toMatch(
      /trailingDisc: \{\s*width: TRAILING_SIZE,\s*height: TRAILING_SIZE,\s*borderRadius: radius\.chip/,
    );
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

describe("P5: the confirm chips are filled, checked capsules", () => {
  it("each chip takes chipChrome and draws the check when selected", () => {
    const dialogue = source(DIALOGUE);
    expect(dialogue).toMatch(/const look = chipChrome\(theme, on\)/);
    expect(dialogue).toMatch(/look\.check \? \(\s*<Icon\s+name="checkmark"/);
    expect(dialogue).toContain("backgroundColor: look.backgroundColor");
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

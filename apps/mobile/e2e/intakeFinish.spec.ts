/**
 * INT-371 (INT-354 slice S4, int-demo 20aca9e2 + the speech.ts aside of
 * b2301f8e). Acceptance, verbatim: "Bitirdim ends the dialogue and lands on
 * review; the open-invite hint shows once per session; the typed → handoff
 * path is covered by a test".
 *
 * INT-321 relabelled the dialogue bar's button to "Bitirdim" but left it a
 * per-turn stop: it called `finishListening()`, it existed only while the mic
 * was open, and with a silent microphone it did nothing, so a patient who had
 * said enough could not leave. These are source-slice assertions, the
 * intakeMode.spec.ts technique (the tree cannot be rendered under the node
 * runner): they prove the new wiring exists and the old one is gone. The
 * once-per-session rule is proved on data in src/lib/intake/openHint.test.ts,
 * and the typed → handoff path in src/lib/intake/typedFlow.test.ts.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { en } from "@/lib/i18n/en";
import { tr } from "@/lib/i18n/tr";

const MOBILE = join(__dirname, "..");
const DIALOGUE = readFileSync(join(MOBILE, "src/components/DialogueIntake.tsx"), "utf8");
const INTAKE = readFileSync(join(MOBILE, "src/app/(tabs)/visits/[visitId]/intake.tsx"), "utf8");

/** The JSX element that carries `label={t("voiceFirst.stop")}`, from its tag to its end. */
function stopButton(source: string): { element: string; before: string } {
  const at = source.indexOf('label={t("voiceFirst.stop")}');
  expect(at, "the dialogue no longer renders a Bitirdim button").toBeGreaterThan(-1);
  const open = source.lastIndexOf("<", at);
  const close = source.indexOf("/>", at);
  return {
    element: source.slice(open, close + 2),
    before: source.slice(Math.max(0, open - 400), open),
  };
}

describe("Bitirdim ends the dialogue and lands on review", () => {
  it("the dialogue renders exactly one Bitirdim", () => {
    expect(DIALOGUE.split('label={t("voiceFirst.stop")}').length - 1).toBe(1);
  });

  it("Bitirdim leaves the conversation and replaces the screen with the review", () => {
    // Synchronous: INT-339's MOTION-10 guard (transients.test.ts) requires
    // every review navigation in the dialogue to sit in a non-async handler,
    // in the tick that finishes.
    const at = DIALOGUE.indexOf("const finishToReview = () => {");
    expect(at, "finishToReview is missing, or it waits before navigating").toBeGreaterThan(-1);
    const finish = DIALOGUE.slice(at);
    const body = finish.slice(0, finish.indexOf("};"));
    // Leave first, so no mic, playback or pending turn outlives the screen;
    // answers are already committed at each confirm, so nothing is lost.
    expect(body).toContain("void session.leave();");
    expect(body).toContain("router.replace(`/(tabs)/visits/${visitId}/review`)");
    expect(body.indexOf("session.leave")).toBeLessThan(body.indexOf("router.replace"));
  });

  it("the button calls finishToReview, not the per-turn stop, and says so to a screen reader", () => {
    const { element } = stopButton(DIALOGUE);
    expect(element).toContain("onPress={finishToReview}");
    expect(element).not.toContain("finishListening");
    expect(element).toContain('hint={t("a11y.dialogue.finishHint")}');
  });

  it("the button is always reachable, not only while the microphone is open", () => {
    const { before } = stopButton(DIALOGUE);
    expect(before).not.toMatch(
      /turn\.phase === "listening" \? \(\s*<View style=\{styles\.barItem\}>\s*$/,
    );
  });

  it("the per-turn 'done speaking' stays on the listening bubble", () => {
    const bubble = DIALOGUE.slice(DIALOGUE.indexOf("styles.listeningBubble") - 1200);
    expect(bubble.slice(0, 1200)).toContain("onPress={() => void session.finishListening()}");
  });
});

describe("the open-question invitation shows once per session", () => {
  it("the typed step renders intake.open.hint only where showsOpenHint says so", () => {
    expect(INTAKE).toContain("showsOpenHint(");
    expect(INTAKE).toContain("openHintAnchor(");
    // A visible rendering is the key as a JSX child; the attribute form
    // (`accessibilityHint={t(…)}`) is the spoken hint, not a line on screen.
    const visible = [...INTAKE.matchAll(/(?<!=)\{t\("intake\.open\.hint"\)\}/g)];
    expect(visible.length, "exactly one line on screen carries the invitation").toBe(1);
    const hint = visible[0].index;
    // The guard sits directly above that one rendering.
    expect(INTAKE.slice(Math.max(0, hint - 300), hint)).toContain("showsOpenHint(");
    // The answer field keeps the same text as its accessibility hint, so a
    // later open step is not left unexplained.
    expect(INTAKE).toContain('accessibilityHint={t("intake.open.hint")}');
  });
});

describe("INT-371 copy: tr source of truth + en mirror (invariant 5)", () => {
  it("the finish hint exists non-empty in tr and in the en mirror", () => {
    const key = "a11y.dialogue.finishHint" as keyof typeof tr;
    expect(tr[key]?.trim().length).toBeGreaterThan(0);
    expect(en[key]?.trim().length).toBeGreaterThan(0);
  });

  it("the finish hint carries no numeral (invariant 22 posture)", () => {
    const key = "a11y.dialogue.finishHint" as keyof typeof tr;
    expect(tr[key] ?? "").not.toMatch(/\d/);
    expect(en[key] ?? "").not.toMatch(/\d/);
  });
});

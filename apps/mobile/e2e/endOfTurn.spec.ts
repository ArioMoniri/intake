/**
 * INT-497 runtime review — the wiring the end-of-turn detector needs, pinned
 * on the source.
 *
 * Like e2e/bargeIn.spec.ts, these scans stand in for a render test, because
 * this suite cannot mount the hook and the one simulator records silence. They
 * pin the three facts the pure modules cannot see:
 *   1. the next turn reopens the microphone BEFORE anything else, so a word the
 *      patient adds after an automatic end lands in the next recording rather
 *      than in a closed microphone;
 *   2. the detector is armed only where taking the turn leads to a spoken turn
 *      (autoEnd.ts) — on the last question the tap ends the turn;
 *   3. the barge-in watch starts with the holding line, not after the late
 *      question it fronts.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const ROOT = join(__dirname, "..");
const HOOK = readFileSync(join(ROOT, "src/lib/dialogue/useDialogueSession.ts"), "utf8");

function between(source: string, from: string, to: string): string {
  const start = source.indexOf(from);
  const end = source.indexOf(to, start);
  expect(start, from).toBeGreaterThanOrEqual(0);
  expect(end, to).toBeGreaterThan(start);
  return source.slice(start, end);
}

describe("an automatic end loses no word to a closed microphone", () => {
  it("the speaking driver reopens the microphone before it makes or plays a clip", () => {
    const speaking = between(HOOK, "const speaking =", "// Listening driver");
    const reopen = speaking.indexOf("openMicrophone()");
    expect(reopen).toBeGreaterThanOrEqual(0);
    expect(reopen).toBeLessThan(speaking.indexOf("store.ensure("));
    expect(reopen).toBeLessThan(speaking.indexOf("shouldAttemptSpeech("));
  });

  it("still opens it through the one call site (bargeIn.spec.ts's pin)", () => {
    expect(HOOK.split("recorder.prepareToRecordAsync(").length - 1).toBe(1);
  });
});

describe("the detector is armed only where the turn's taking speaks again", () => {
  it("the listening driver asks autoEndAllowed before it arms the endpointer", () => {
    const listening = between(HOOK, "// Listening driver", "// Session end:");
    const gate = listening.indexOf("autoEndAllowed(");
    expect(gate).toBeGreaterThanOrEqual(0);
    expect(gate).toBeLessThan(listening.indexOf("armEndpointWatch("));
  });

  it("asks again when the detector fires — the next turn may have changed meanwhile", () => {
    const watch = between(HOOK, "const armEndpointWatch", "const stopAndDiscardRecording");
    const fired = watch.indexOf('"ended"');
    expect(fired).toBeGreaterThanOrEqual(0);
    expect(watch.indexOf("autoEndAllowed(", fired)).toBeGreaterThan(fired);
  });
});

describe("the holding line is interruptible from its first word", () => {
  it("speakWithHolding arms the barge-in watch when the holding queue starts", () => {
    const holding = between(HOOK, "const speakWithHolding", "// Pre-warm the session's");
    const started = holding.indexOf("playQueue([uri]");
    expect(started).toBeGreaterThanOrEqual(0);
    expect(holding.indexOf("onStarted()", started)).toBeGreaterThan(started);
    expect(holding.indexOf("onStarted()", started)).toBeLessThan(
      holding.indexOf("await questionClip"),
    );
  });
});

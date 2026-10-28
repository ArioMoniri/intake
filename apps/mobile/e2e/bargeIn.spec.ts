/**
 * INT-291 — the wiring the detector needs, pinned on the source.
 *
 * There are no React Native render tests in this app (every `e2e/*.spec.ts`
 * is a static source scanner), and the one simulator available records
 * silence, so a regression that quietly closed the microphone during agent
 * speech would pass the whole suite. These scans are what stands in for the
 * render test: they pin the four facts the pure detector cannot see.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const ROOT = join(__dirname, "..");
const HOOK = readFileSync(join(ROOT, "src/lib/dialogue/useDialogueSession.ts"), "utf8");

/** Code only, comments dropped — the comments NAME what the code must not do. */
function code(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

describe("the microphone is open WHILE the agent speaks", () => {
  it("the speaking driver sets an audio mode that permits recording", () => {
    // The defect: `allowsRecording: false` during playback meant no
    // microphone existed while the agent spoke, so speaking over the agent
    // did nothing at all. Tapping the bubble was the only interrupt.
    const speaking = HOOK.slice(
      HOOK.indexOf("const speaking ="),
      HOOK.indexOf("// Listening driver"),
    );
    expect(speaking).toContain("allowsRecording: true");
    expect(speaking).not.toContain("allowsRecording: false");
  });

  it("routes playback to the speaker, not the earpiece", () => {
    // iOS puts a `.playAndRecord` session on the receiver unless told
    // otherwise. Getting this wrong would answer "make the voice better"
    // with a quieter voice.
    expect(HOOK).toContain("shouldRouteThroughEarpiece: false");
  });

  it("reads the level from the chunk that just arrived — there is no recorder to meter (INT-559)", () => {
    expect(HOOK).toContain(".levelDbfs()");
    expect(HOOK).not.toContain("isMeteringEnabled");
  });

  it("feeds the detector and calls the SAME barge-in the tap calls", () => {
    // One reducer action for both causes: the tap and the voice must not
    // diverge into two state machines (INT-233's DISTURBABLE property).
    expect(HOOK).toContain("createSpeechOnsetDetector");
    const listener = HOOK.slice(HOOK.indexOf("createSpeechOnsetDetector"));
    expect(listener).toContain("bargeIn");
  });
});

describe("invariant 3 — the watcher reads a level, never audio, and never a file (INT-559)", () => {
  it("the detector is fed from the capture's level and nothing else", () => {
    expect(HOOK).toContain(".levelDbfs()");
    // No recorder, no platform meter, no file: the level is computed from
    // the chunk that just arrived and nothing is kept to compute it from later.
    expect(code(HOOK)).not.toContain("getStatus()");
    expect(code(HOOK)).not.toMatch(/recorder/i);
  });

  it("one capture per turn — the watch does not open a second one", () => {
    // The capture that heard the barge-in IS the patient's answer, so there
    // is exactly one place a turn is created, and it is guarded by
    // `isCapturing()` before the create.
    expect(HOOK.split("createCaptureTurn(").length - 1).toBe(1);
    const open = HOOK.slice(HOOK.indexOf("const openMicrophone = async"));
    expect(open.slice(0, open.indexOf("createCaptureTurn("))).toContain("isCapturing()");
  });

  it("on iOS the clip plays without the microphone: expo-audio's stream would silence it", () => {
    expect(HOOK).toContain("micMayOpenWhileSpeaking(Platform.OS)");
  });
});

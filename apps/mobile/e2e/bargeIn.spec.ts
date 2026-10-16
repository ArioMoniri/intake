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
// INT-440: the mode the hook applies lives in one contract, applied once per
// session through a latch, rather than inline before every clip.
const AUDIO_SESSION = readFileSync(join(ROOT, "src/lib/dialogue/audioSession.ts"), "utf8");

describe("the microphone is open WHILE the agent speaks", () => {
  it("the speaking driver sets an audio mode that permits recording", () => {
    // The defect: `allowsRecording: false` during playback meant no
    // microphone existed while the agent spoke, so speaking over the agent
    // did nothing at all. Tapping the bubble was the only interrupt.
    const speaking = HOOK.slice(
      HOOK.indexOf("const speaking ="),
      HOOK.indexOf("// Listening driver"),
    );
    expect(speaking).toContain("audioMode().ensure()");
    expect(speaking).not.toContain("allowsRecording: false");
    expect(AUDIO_SESSION).toContain("allowsRecording: true");
    expect(AUDIO_SESSION).not.toContain("allowsRecording: false");
  });

  it("routes playback to the speaker, not the earpiece", () => {
    // iOS puts a `.playAndRecord` session on the receiver unless told
    // otherwise. Getting this wrong would answer "make the voice better"
    // with a quieter voice.
    expect(AUDIO_SESSION).toContain("shouldRouteThroughEarpiece: false");
    expect(HOOK).not.toContain("shouldRouteThroughEarpiece: true");
  });

  it("enables metering on the recorder, or every level reads undefined", () => {
    expect(HOOK).toContain("isMeteringEnabled: true");
  });

  it("feeds the detector and calls the SAME barge-in the tap calls", () => {
    // One reducer action for both causes: the tap and the voice must not
    // diverge into two state machines (INT-233's DISTURBABLE property).
    expect(HOOK).toContain("createSpeechOnsetDetector");
    const listener = HOOK.slice(HOOK.indexOf("createSpeechOnsetDetector"));
    expect(listener).toContain("bargeIn");
  });
});

describe("invariant 3 — the watcher reads a level, never audio", () => {
  it("the detector is fed from getStatus metering and nothing else", () => {
    expect(HOOK).toContain("getStatus()");
    // No new read of recorded bytes: the only URI handling stays the
    // existing transcribe-then-delete path.
    const uses = HOOK.split("recorder.uri").length - 1;
    expect(uses).toBe(2); // finishListening and stopAndDiscardRecording
  });

  it("one recording per turn — the watch does not open a second one", () => {
    // The recording that detected the barge-in IS the patient's answer, so
    // there is exactly one `prepareToRecordAsync` call site.
    expect(HOOK.split("recorder.prepareToRecordAsync(").length - 1).toBe(1);
  });
});

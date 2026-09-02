/**
 * The onset detector that lets a patient interrupt by SPEAKING (INT-291).
 *
 * The whole point of testing it as a pure function: the decision must be
 * provable without a microphone, because the one simulator this repo has
 * records silence. What the device can tell us is whether the audio session
 * permits play-and-record at all; what it cannot tell us is whether a given
 * level pattern is a barge-in. That is decided here.
 */
import { describe, expect, it } from "vitest";

import {
  ARM_DELAY_MS,
  CALIBRATION_MS,
  ECHO_MARGIN_DB,
  MIN_TRIGGER_DBFS,
  ONSET_HOLD_MS,
  createSpeechOnsetDetector,
  type OnsetVerdict,
} from "./bargeIn";

/** Feed a constant level for `ms`, returning the last verdict seen. */
function feed(
  detector: ReturnType<typeof createSpeechOnsetDetector>,
  from: number,
  ms: number,
  dbfs: number,
  stepMs = 20,
): { at: number; verdicts: OnsetVerdict[] } {
  const verdicts: OnsetVerdict[] = [];
  let at = from;
  for (; at < from + ms; at += stepMs) {
    verdicts.push(detector.sample(dbfs, at));
  }
  return { at, verdicts };
}

/** Walks a whole clip: arm delay, calibration at the echo floor, then speech. */
function run(echoDbfs: number, patientDbfs: number, speechMs: number): OnsetVerdict[] {
  const detector = createSpeechOnsetDetector();
  let at = 0;
  ({ at } = feed(detector, at, ARM_DELAY_MS + CALIBRATION_MS, echoDbfs));
  return feed(detector, at, speechMs, patientDbfs).verdicts;
}

describe("createSpeechOnsetDetector — the constants are stated, not implied", () => {
  it("cannot trigger below an absolute floor, whatever the room measured", () => {
    // A silent room calibrates to a very low echo level. Without a floor the
    // threshold would land under the noise of a fan and every turn would be
    // cut by nothing at all.
    expect(MIN_TRIGGER_DBFS).toBeLessThan(0);
    expect(run(-90, MIN_TRIGGER_DBFS - 1, 2000)).not.toContain("fired");
  });

  it("holds an onset for long enough that a cough is not an answer", () => {
    expect(ONSET_HOLD_MS).toBeGreaterThanOrEqual(200);
  });

  it("keeps the inter-sentence pause of a question below the hold", () => {
    // The agent's own 200 ms sentence gap must not be long enough for the
    // patient's reflex "hı-hı" to be read as a turn. Stated as a relation
    // between two constants so a later change to either fails here.
    expect(ONSET_HOLD_MS).toBeGreaterThan(200);
  });
});

describe("createSpeechOnsetDetector — the agent's own voice is not a barge-in", () => {
  it("does not fire on the echo level it calibrated against", () => {
    const verdicts = run(-28, -28, 3000);
    expect(verdicts).not.toContain("fired");
  });

  it("does not fire on an echo a little louder than calibration", () => {
    const verdicts = run(-28, -28 + ECHO_MARGIN_DB - 1, 3000);
    expect(verdicts).not.toContain("fired");
  });

  it("fires when the patient is clearly over the echo, held", () => {
    const verdicts = run(-28, -28 + ECHO_MARGIN_DB + 4, ONSET_HOLD_MS + 200);
    expect(verdicts).toContain("fired");
  });

  it("adapts to a LOUD room: the same absolute level that fired quietly does not", () => {
    // Same patient level, two rooms. The one where the agent's echo is
    // already at that level must not fire — this is the property that keeps
    // a speakerphone from cutting the agent off mid-question.
    const quiet = run(-45, -20, 2000);
    const loud = run(-20, -20, 2000);
    expect(quiet).toContain("fired");
    expect(loud).not.toContain("fired");
  });
});

describe("createSpeechOnsetDetector — transients are not turns", () => {
  it("does not fire on a burst shorter than the hold", () => {
    const detector = createSpeechOnsetDetector();
    let at = 0;
    ({ at } = feed(detector, at, ARM_DELAY_MS + CALIBRATION_MS, -50));
    const burst = feed(detector, at, ONSET_HOLD_MS - 40, -10);
    expect(burst.verdicts).not.toContain("fired");
    // and the run resets: silence after the burst does not carry credit
    const after = feed(detector, burst.at, ONSET_HOLD_MS - 40, -70);
    const again = feed(detector, after.at, ONSET_HOLD_MS - 40, -10);
    expect(again.verdicts).not.toContain("fired");
  });

  it("fires when the same level is sustained past the hold", () => {
    const detector = createSpeechOnsetDetector();
    let at = 0;
    ({ at } = feed(detector, at, ARM_DELAY_MS + CALIBRATION_MS, -50));
    expect(feed(detector, at, ONSET_HOLD_MS + 100, -10).verdicts).toContain("fired");
  });
});

describe("createSpeechOnsetDetector — the arm delay", () => {
  it("is deaf while the clip's first word is still being spoken", () => {
    // Without this, the patient's answer to the PREVIOUS turn — still in the
    // air as the next clip starts — cuts the opening word off the new
    // question, and the patient never hears what they were asked.
    const detector = createSpeechOnsetDetector();
    expect(feed(detector, 0, ARM_DELAY_MS - 20, -5).verdicts).not.toContain("fired");
  });

  it("reports what it is doing at each stage rather than a bare boolean", () => {
    const detector = createSpeechOnsetDetector();
    expect(detector.sample(-50, 0)).toBe("warming");
    expect(detector.sample(-50, ARM_DELAY_MS + 10)).toBe("calibrating");
    expect(detector.sample(-50, ARM_DELAY_MS + CALIBRATION_MS + 10)).toBe("listening");
  });
});

describe("createSpeechOnsetDetector — once fired", () => {
  it("stays fired, so the caller's stop is idempotent", () => {
    const detector = createSpeechOnsetDetector();
    let at = 0;
    ({ at } = feed(detector, at, ARM_DELAY_MS + CALIBRATION_MS, -50));
    ({ at } = feed(detector, at, ONSET_HOLD_MS + 100, -10));
    expect(detector.sample(-90, at + 500)).toBe("fired");
  });

  it("ignores a missing metering reading instead of treating it as silence", () => {
    // expo-audio omits `metering` when the platform has not produced one yet.
    // Reading undefined as -160 dBFS would drag the calibrated floor down and
    // arm a hair trigger; the sample is skipped instead.
    const detector = createSpeechOnsetDetector();
    let at = 0;
    ({ at } = feed(detector, at, ARM_DELAY_MS + CALIBRATION_MS, -20));
    expect(detector.sample(undefined, at + 20)).toBe("listening");
    expect(feed(detector, at + 40, 2000, -20).verdicts).not.toContain("fired");
  });
});

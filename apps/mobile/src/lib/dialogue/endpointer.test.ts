/**
 * INT-497 — the end-of-turn detector that lets a patient stop talking instead
 * of tapping "Bitirdim".
 *
 * Pure, like bargeIn.ts, for the same reason: the one simulator this repo has
 * records silence, so whether a level pattern is the END of an answer has to
 * be provable without a microphone. The device supplies samples; this decides.
 */
import { describe, expect, it } from "vitest";

import {
  CUT_OFF_WINDOW_MS,
  ENDPOINT_SAMPLE_MS,
  HANGOVER_LONG_MS,
  HANGOVER_MAX_MS,
  HANGOVER_SHORT_MS,
  HANGOVER_STEP_MS,
  LATE_TAP_GRACE_MS,
  ONSET_MIN_MS,
  SHORT_ANSWER_MS,
  VOICED_CEILING_DBFS,
  VOICED_FLOOR_DBFS,
  createEndpointer,
  createHangoverPolicy,
  isLateFinishTap,
  isLikelyCutOff,
  type Endpointer,
  type EndpointVerdict,
} from "./endpointer";

const ROOM = -58;
const SPEECH = -24;

/** Feed `dbfs` from `from` for `ms`, one sample per ENDPOINT_SAMPLE_MS. */
function feed(
  endpointer: Endpointer,
  from: number,
  ms: number,
  dbfs: number | undefined,
): { at: number; verdicts: EndpointVerdict[] } {
  const verdicts: EndpointVerdict[] = [];
  let at = from;
  for (; at < from + ms; at += ENDPOINT_SAMPLE_MS) {
    verdicts.push(endpointer.sample(dbfs, at));
  }
  return { at, verdicts };
}

/** Room tone, then an answer of `speechMs`, then room tone until it ends. */
function answer(speechMs: number, policy = createHangoverPolicy()) {
  const endpointer = createEndpointer(policy);
  let at = 0;
  ({ at } = feed(endpointer, at, 600, ROOM));
  const speechStart = at;
  ({ at } = feed(endpointer, at, speechMs, SPEECH));
  const speechEnd = at - ENDPOINT_SAMPLE_MS; // the last voiced sample
  const tail = feed(endpointer, at, 3000, ROOM);
  return { endpointer, speechStart, speechEnd, verdicts: tail.verdicts };
}

describe("the constants are stated, and they agree with each other", () => {
  it("samples often enough that the hangover is a real duration", () => {
    expect(ENDPOINT_SAMPLE_MS).toBeLessThanOrEqual(50);
    expect(HANGOVER_SHORT_MS / ENDPOINT_SAMPLE_MS).toBeGreaterThanOrEqual(8);
  });

  it("waits longer after a long answer than after a short one", () => {
    // A narrative carries hesitation pauses a one-word answer does not; a
    // single hangover would either cut the first off or make the second wait.
    expect(HANGOVER_LONG_MS).toBeGreaterThan(HANGOVER_SHORT_MS);
    expect(SHORT_ANSWER_MS).toBeGreaterThan(ONSET_MIN_MS);
  });

  it("never waits longer than the cap, however often it widened", () => {
    expect(HANGOVER_MAX_MS).toBeGreaterThan(HANGOVER_LONG_MS);
    expect(HANGOVER_STEP_MS).toBeGreaterThan(0);
  });

  it("asks less of a voice in a loud room than a quiet one, within bounds", () => {
    expect(VOICED_FLOOR_DBFS).toBeLessThan(VOICED_CEILING_DBFS);
  });
});

describe("createEndpointer — a short answer ends on the short hangover", () => {
  it("fires once the silence after the last voiced sample reaches the hangover", () => {
    const run = answer(600);
    expect(run.verdicts).toContain("ended");
    const ended = run.endpointer.endedAt!;
    expect(ended - run.speechEnd).toBeGreaterThanOrEqual(HANGOVER_SHORT_MS);
    expect(ended - run.speechEnd).toBeLessThan(HANGOVER_SHORT_MS + 2 * ENDPOINT_SAMPLE_MS);
  });

  it("reports when speech was last heard, which is where the turn really ended", () => {
    const run = answer(600);
    expect(run.endpointer.lastVoicedAt).toBe(run.speechEnd);
  });

  it("uses the long hangover after an answer longer than SHORT_ANSWER_MS", () => {
    const run = answer(SHORT_ANSWER_MS + 1500);
    const waited = run.endpointer.endedAt! - run.speechEnd;
    expect(waited).toBeGreaterThanOrEqual(HANGOVER_LONG_MS);
    expect(waited).toBeLessThan(HANGOVER_LONG_MS + 2 * ENDPOINT_SAMPLE_MS);
  });

  it("stays ended — a late sound does not reopen a turn already taken", () => {
    const run = answer(600);
    expect(run.endpointer.sample(SPEECH, 99_999)).toBe("ended");
  });
});

describe("createEndpointer — it never ends a turn nobody has spoken in", () => {
  it("waits through room tone forever: silence alone is the tap's job", () => {
    const endpointer = createEndpointer(createHangoverPolicy());
    expect(feed(endpointer, 0, 20_000, ROOM).verdicts).not.toContain("ended");
  });

  it("does not count a click shorter than ONSET_MIN_MS as speech", () => {
    const endpointer = createEndpointer(createHangoverPolicy());
    let at = feed(endpointer, 0, 600, ROOM).at;
    at = feed(endpointer, at, ONSET_MIN_MS - ENDPOINT_SAMPLE_MS, SPEECH).at;
    expect(feed(endpointer, at, 5000, ROOM).verdicts).not.toContain("ended");
    expect(endpointer.lastVoicedAt).toBeNull();
  });

  it("skips a missing reading rather than reading it as silence", () => {
    // expo-audio returns `undefined` until the platform has a level. Reading
    // that as -160 dBFS would end every turn whose meter was late.
    const endpointer = createEndpointer(createHangoverPolicy(), { speakingAt: 0 });
    expect(feed(endpointer, 0, 5000, undefined).verdicts).not.toContain("ended");
  });
});

describe("createEndpointer — it does not cut a hesitation off", () => {
  it("keeps the turn open through a pause shorter than the hangover", () => {
    const endpointer = createEndpointer(createHangoverPolicy());
    let at = feed(endpointer, 0, 600, ROOM).at;
    at = feed(endpointer, at, 2000, SPEECH).at;
    // "…şey…" — a 500 ms hesitation inside a long answer
    const pause = feed(endpointer, at, 500, ROOM);
    expect(pause.verdicts).not.toContain("ended");
    at = feed(endpointer, pause.at, 800, SPEECH).at;
    expect(endpointer.endedAt).toBeNull();
    feed(endpointer, at, 3000, ROOM);
    expect(endpointer.endedAt).not.toBeNull();
  });

  it("hears a loud room as the room: voice above it counts, the room ends the turn on time", () => {
    // Waiting-room noise at -38 dBFS. The voiced threshold is capped, so the
    // patient's -24 dBFS still counts as voice; the room itself is the floor,
    // so it neither ends the turn early nor holds it open forever.
    const endpointer = createEndpointer(createHangoverPolicy());
    let at = feed(endpointer, 0, 600, -38).at;
    at = feed(endpointer, at, 800, SPEECH).at;
    const early = feed(endpointer, at, HANGOVER_SHORT_MS - 2 * ENDPOINT_SAMPLE_MS, -38);
    expect(early.verdicts).not.toContain("ended");
    expect(feed(endpointer, early.at, 1000, -38).verdicts).toContain("ended");
  });

  it("never asks more than the ceiling of a voice, however far above the room", () => {
    // Floor + margin would ask -30 dBFS of a voice in a -40 room; the cap
    // asks the ceiling, so a quiet speaker in a noisy room is still heard.
    const endpointer = createEndpointer(createHangoverPolicy());
    const at = feed(endpointer, 0, 600, -40).at;
    feed(endpointer, at, 800, VOICED_CEILING_DBFS + 1);
    expect(endpointer.lastVoicedAt).not.toBeNull();
  });

  it("never hears the quiet room itself as a voice, however quiet it is", () => {
    const endpointer = createEndpointer(createHangoverPolicy());
    const at = feed(endpointer, 0, 600, -90).at;
    feed(endpointer, at, 800, VOICED_FLOOR_DBFS - 1);
    expect(endpointer.lastVoicedAt).toBeNull();
  });

  it("starts already speaking after a barge-in, so the first words count", () => {
    const endpointer = createEndpointer(createHangoverPolicy(), { speakingAt: 0 });
    const at = feed(endpointer, 0, 400, SPEECH).at;
    const verdicts = feed(endpointer, at, 2000, ROOM).verdicts;
    expect(verdicts).toContain("ended");
  });
});

describe("createHangoverPolicy — a session that was cut off waits longer", () => {
  it("widens by one step per cut-off, up to the cap", () => {
    const policy = createHangoverPolicy();
    expect(policy.hangoverMs(400, "short")).toBe(HANGOVER_SHORT_MS);
    policy.noteCutOff();
    expect(policy.hangoverMs(400, "short")).toBe(HANGOVER_SHORT_MS + HANGOVER_STEP_MS);
    for (let i = 0; i < 20; i += 1) {
      policy.noteCutOff();
    }
    expect(policy.hangoverMs(400, "short")).toBe(HANGOVER_MAX_MS);
    expect(policy.hangoverMs(SHORT_ANSWER_MS + 1, "short")).toBe(HANGOVER_MAX_MS);
  });

  it("gives a free-text question the long wait from the first word", () => {
    const policy = createHangoverPolicy();
    expect(policy.hangoverMs(400, "narrative")).toBe(HANGOVER_LONG_MS);
    expect(policy.hangoverMs(400, "short")).toBe(HANGOVER_SHORT_MS);
  });

  it("reads the question's shape from the endpointer's options", () => {
    const endpointer = createEndpointer(createHangoverPolicy(), { shape: "narrative" });
    let at = feed(endpointer, 0, 600, ROOM).at;
    at = feed(endpointer, at, 600, SPEECH).at;
    const speechEnd = at - ENDPOINT_SAMPLE_MS;
    feed(endpointer, at, 3000, ROOM);
    expect(endpointer.endedAt! - speechEnd).toBeGreaterThanOrEqual(HANGOVER_LONG_MS);
  });

  it("is applied by the endpointer it is handed", () => {
    const policy = createHangoverPolicy();
    policy.noteCutOff();
    const run = answer(600, policy);
    expect(run.endpointer.endedAt! - run.speechEnd).toBeGreaterThanOrEqual(
      HANGOVER_SHORT_MS + HANGOVER_STEP_MS,
    );
  });
});

describe("isLikelyCutOff — speaking over the next question right after an auto end", () => {
  it("is a cut-off inside the window after an automatic endpoint", () => {
    expect(isLikelyCutOff(1000, 1000 + CUT_OFF_WINDOW_MS - 1)).toBe(true);
  });

  it("is an ordinary interruption after the window, or after a tap", () => {
    expect(isLikelyCutOff(1000, 1000 + CUT_OFF_WINDOW_MS + 1)).toBe(false);
    expect(isLikelyCutOff(null, 1200)).toBe(false);
  });
});

describe("isLateFinishTap — the 'Bitirdim' tap that lands after the turn ended itself", () => {
  it("is the late finish tap inside the grace, never a barge-in", () => {
    expect(isLateFinishTap(5000, 5000 + LATE_TAP_GRACE_MS - 1)).toBe(true);
  });

  it("is a real tap after the grace, or when the turn ended by a tap", () => {
    expect(isLateFinishTap(5000, 5000 + LATE_TAP_GRACE_MS + 1)).toBe(false);
    expect(isLateFinishTap(null, 5100)).toBe(false);
  });
});

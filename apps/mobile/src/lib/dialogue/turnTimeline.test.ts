/**
 * INT-497 — the turn timeline: what the patient waited, measured on the device.
 *
 * Three quantities, the ones the owner's order names:
 *   - end of the patient's speech → the agent's first audio (the turn gap);
 *   - dead air between two consecutive clips of one turn (the join);
 *   - ASR finalisation: the recording handed over → its transcript back.
 *
 * Only durations are kept — no text, no audio, no id beyond a turn counter —
 * so nothing here can carry what the patient said (invariants 3 and 6). A
 * missing measurement is ABSENT, never zero (invariant 20's posture).
 */
import { describe, expect, it } from "vitest";

import { TIMELINE_WINDOW, createTrackClock, createTurnTimeline, percentile } from "./turnTimeline";

describe("percentile — nearest rank, and nothing from nothing", () => {
  it("is null on no readings", () => {
    expect(percentile([], 50)).toBeNull();
  });

  it("takes the nearest-rank value", () => {
    const values = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100];
    expect(percentile(values, 50)).toBe(50);
    expect(percentile(values, 95)).toBe(100);
    expect(percentile([7], 95)).toBe(7);
  });
});

describe("createTurnTimeline — the turn gap", () => {
  it("is measured from the last voiced sample, not from when the turn was taken", () => {
    const timeline = createTurnTimeline();
    timeline.turnTaken({ endpoint: "auto", speechEndAt: 1000, at: 1450 });
    timeline.firstAudio(1700);
    const summary = timeline.summary();
    expect(summary.turns).toBe(1);
    expect(summary.firstAudioP50Ms).toBe(700);
    expect(summary.endpointP50Ms).toBe(450);
  });

  it("charges only the first audio of a turn; later clips are joins, not the gap", () => {
    const timeline = createTurnTimeline();
    timeline.turnTaken({ endpoint: "auto", speechEndAt: 0, at: 500 });
    timeline.firstAudio(640);
    timeline.firstAudio(2900);
    expect(timeline.summary().firstAudioP50Ms).toBe(640);
  });

  it("does not invent a gap for a tapped turn in which no voice was heard", () => {
    const timeline = createTurnTimeline();
    timeline.turnTaken({ endpoint: "tap", speechEndAt: null, at: 500 });
    timeline.firstAudio(640);
    const summary = timeline.summary();
    expect(summary.turns).toBe(1);
    expect(summary.firstAudioP50Ms).toBeNull();
    expect(summary.tappedTurns).toBe(1);
  });

  it("ignores audio that arrives before any turn was taken (the opening)", () => {
    const timeline = createTurnTimeline();
    timeline.firstAudio(100);
    expect(timeline.summary().firstAudioP50Ms).toBeNull();
  });

  it("drops a reading that is not a finite, non-negative duration", () => {
    const timeline = createTurnTimeline();
    timeline.turnTaken({ endpoint: "auto", speechEndAt: 900, at: 800 });
    timeline.firstAudio(700);
    expect(timeline.summary().firstAudioP50Ms).toBeNull();
  });

  it("keeps a bounded window — a long session does not grow without end", () => {
    const timeline = createTurnTimeline();
    for (let i = 0; i < TIMELINE_WINDOW + 50; i += 1) {
      const t = i * 10_000;
      timeline.turnTaken({ endpoint: "auto", speechEndAt: t, at: t + 450 });
      timeline.firstAudio(t + 600 + (i % 2));
    }
    expect(timeline.summary().turns).toBe(TIMELINE_WINDOW);
  });
});

describe("createTurnTimeline — joins and ASR", () => {
  it("reports the worst and the p95 join", () => {
    const timeline = createTurnTimeline();
    [0, 2, 1, 118].forEach((gap) => timeline.join(gap));
    const summary = timeline.summary();
    expect(summary.joinMaxMs).toBe(118);
    expect(summary.joinP95Ms).toBe(118);
  });

  it("reports ASR finalisation per utterance", () => {
    const timeline = createTurnTimeline();
    timeline.asrSettled(820);
    timeline.asrSettled(640);
    expect(timeline.summary().asrP50Ms).toBe(640);
  });
});

describe("createTrackClock — first audio and joins from a playlist's own status", () => {
  it("back-dates the start by the position, so a coarse status is still exact", () => {
    const clock = createTrackClock();
    // status seen 120 ms after the start: position 0.12 s
    const seen = clock.observe({
      index: 0,
      positionS: 0.12,
      durationS: 1.5,
      playing: true,
      atMs: 10_120,
    });
    expect(seen.started).toBe(10_000);
    expect(seen.join).toBeUndefined();
  });

  it("reports the dead air between the end of one track and the start of the next", () => {
    const clock = createTrackClock();
    clock.observe({ index: 0, positionS: 0.1, durationS: 1.5, playing: true, atMs: 1_100 });
    const next = clock.observe({
      index: 1,
      positionS: 0.05,
      durationS: 2,
      playing: true,
      atMs: 2_650,
    });
    // track 0: 1000 → 2500; track 1 started at 2600
    expect(next.join).toBeCloseTo(100, 6);
  });

  it("reports each track's start once, and nothing for a paused or unstarted status", () => {
    const clock = createTrackClock();
    expect(clock.observe({ index: 0, positionS: 0, durationS: 1, playing: true, atMs: 5 })).toEqual(
      {},
    );
    expect(
      clock.observe({ index: 0, positionS: 0.2, durationS: 1, playing: false, atMs: 400 }),
    ).toEqual({});
    expect(
      clock.observe({ index: 0, positionS: 0.1, durationS: 1, playing: true, atMs: 600 }).started,
    ).toBe(500);
    expect(
      clock.observe({ index: 0, positionS: 0.3, durationS: 1, playing: true, atMs: 800 }),
    ).toEqual({});
  });
});

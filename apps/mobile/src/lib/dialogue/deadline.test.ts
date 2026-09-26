/**
 * INT-259 — the one timer on the voice surface.
 *
 * SC 2.2.1 posture, asserted rather than asserted-about: the deadline fires
 * once, it is keyed on turn identity so re-entering a turn restarts it and
 * leaving clears it, and a disarmed key never fires at all. What it does on
 * expiry is the caller's business — but nothing here advances a turn, arms a
 * mic or removes a control, and `stance.test.ts` pins that on the frame side.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { armDeadline, WORK_DEADLINE_MS } from "./deadline";
import { FIRST_AUDIO_DEADLINE_MS, SYNTHESIZE_TIMEOUT_MS } from "./tts";
import { PROBE_TIMEOUT_MS } from "../dev/hosts";

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("R3 — the deadlines are derived from their inputs, never written as literals", () => {
  it("first audio is two synthesis attempts plus the write-and-start tail", () => {
    expect(FIRST_AUDIO_DEADLINE_MS).toBe(2 * SYNTHESIZE_TIMEOUT_MS + 500);
  });

  it("the work deadline is the ASR walk plus one whole time-to-first-audio", () => {
    expect(WORK_DEADLINE_MS).toBe(PROBE_TIMEOUT_MS + FIRST_AUDIO_DEADLINE_MS);
  });

  it("both exceed one synthesis attempt, so a lane having a bad sentence is not a silence", () => {
    expect(FIRST_AUDIO_DEADLINE_MS).toBeGreaterThan(SYNTHESIZE_TIMEOUT_MS);
    expect(WORK_DEADLINE_MS).toBeGreaterThan(FIRST_AUDIO_DEADLINE_MS);
  });
});

describe("armDeadline — keyed on turn identity", () => {
  it("fires once, after the stated time and not before", () => {
    const onExpire = vi.fn();
    armDeadline("turn-1", 1000, onExpire);
    vi.advanceTimersByTime(999);
    expect(onExpire).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(onExpire).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(10_000);
    expect(onExpire).toHaveBeenCalledTimes(1);
  });

  it("a null key arms nothing — disarming is expressible, not an omission", () => {
    const onExpire = vi.fn();
    const disarm = armDeadline(null, 1000, onExpire);
    vi.advanceTimersByTime(10_000);
    expect(onExpire).not.toHaveBeenCalled();
    disarm();
  });

  it("T-6 — disarming before expiry cancels it: playback runs the clip to its end", () => {
    const onExpire = vi.fn();
    const disarm = armDeadline("turn-1", 1000, onExpire);
    vi.advanceTimersByTime(400); // first playbackStatusUpdate lands here
    disarm();
    vi.advanceTimersByTime(60_000); // a two-sentence clip plays on
    expect(onExpire).not.toHaveBeenCalled();
  });

  it("re-entering the same turn restarts the clock rather than inheriting it", () => {
    const onExpire = vi.fn();
    const first = armDeadline("turn-1", 1000, onExpire);
    vi.advanceTimersByTime(900);
    first();
    const second = armDeadline("turn-1", 1000, onExpire);
    vi.advanceTimersByTime(900);
    expect(onExpire).not.toHaveBeenCalled();
    vi.advanceTimersByTime(100);
    expect(onExpire).toHaveBeenCalledTimes(1);
    second();
  });
});

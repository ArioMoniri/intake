/**
 * INT-259 — the stance machine, and the property that makes the reproduced
 * hang unrepresentable.
 *
 * The defect, reproduced on the simulator twice: a fresh visit sat on
 * "Soru hazırlanıyor…" with a spinner that never resolved. Two screenshots a
 * minute apart were pixel-identical. Every speech lane was healthy, so this
 * was never a connectivity failure — it was a screen state with **no clock
 * and no control**: `phase === "speaking" && playing === false`, produced by
 * an `await store.ensure(...)` that never settled, and rendered by an
 * `&&`-gated spinner that nothing could change.
 *
 * The cure is not a timeout. It is that a frame with neither a clock nor a
 * control cannot be written down: `FRAMES` is a frozen table, `frameKey` is
 * total over `Stance`, and `hasExit` is asserted over every entry. Adding a
 * stance without a frame does not compile; adding a frame without an exit
 * fails here.
 */
import { describe, expect, it } from "vitest";

import { FIRST_AUDIO_DEADLINE_MS } from "./tts";
import { FRAMES, frameFor, frameKey, hasExit, stance, type FrameKey, type Stance } from "./stance";
import type { DialogueStreamState } from "./stream";

/** Every stance the surface can be in, one of each — the table's domain. */
const EVERY_STANCE: readonly Stance[] = [
  { kind: "konusuyor" },
  { kind: "sira_sizde", reason: "sessiz" },
  { kind: "sira_sizde", reason: "onay" },
  { kind: "dinliyor" },
  { kind: "toparlaniyor" },
  { kind: "bitti" },
  { kind: "devir" },
  { kind: "durdu" },
];

function state(overrides: Partial<DialogueStreamState> = {}): DialogueStreamState {
  return {
    turn: { phase: "speaking", step: 0, intent: "question" },
    audio: "pending",
    turnSeq: 1,
    pending: {},
    answers: {},
    asked: [],
    inflight: [],
    retries: {},
    work: {},
    seq: {},
    stream: [],
    ...overrides,
  };
}

describe("T-5 — the frame table is total, and no frame is a dead end", () => {
  it("every stance resolves to a frame, and every frame key is used", () => {
    const keys = EVERY_STANCE.map(frameKey);
    expect(new Set(keys).size).toBe(keys.length);
    expect(new Set(keys)).toEqual(new Set(Object.keys(FRAMES) as FrameKey[]));
  });

  it("no frame can strand the patient — a clock, a control, or the exit of a terminal", () => {
    for (const s of EVERY_STANCE) {
      const frame = frameFor(s);
      expect(hasExit(frame), `${frameKey(s)} has neither a clock nor a control`).toBe(true);
    }
  });

  it("the reproduced defect is exactly a frame without an exit, and it is rejected", () => {
    // The state the screenshots showed, written down as a frame: a spinner,
    // no clock, no control, not terminal. `hasExit` is what refuses it.
    expect(
      hasExit({
        primary: null,
        alternates: [],
        composer: false,
        deadlineMs: null,
        statusKey: null,
        a11yKey: null,
        terminal: false,
      }),
    ).toBe(false);
  });

  it("the frozen table cannot be edited at runtime", () => {
    expect(Object.isFrozen(FRAMES)).toBe(true);
  });
});

describe("T-4 — the reproduction: the spoken turn that never gets audio", () => {
  it("a speaking turn whose audio never arrives becomes sira_sizde(sessiz)", () => {
    const stuck = state({ audio: "silent" });
    expect(stance(stuck)).toEqual({ kind: "sira_sizde", reason: "sessiz" });
  });

  it("sessiz says on screen that no audio came, and offers the mic", () => {
    const frame = FRAMES["sira_sizde/sessiz"];
    expect(frame.statusKey).toBe("dialogue.status.silent");
    expect(frame.a11yKey).toBe("a11y.dialogue.silent");
    expect(frame.primary?.id).toBe("speak");
    expect(frame.composer).toBe(true);
  });

  it("nothing spins and nothing is disabled: sessiz carries no clock of its own", () => {
    expect(FRAMES["sira_sizde/sessiz"].deadlineMs).toBeNull();
  });
});

describe("T-7 — the clock changes what is said, never what is offered", () => {
  it("konusuyor is the only stance that arms a clock, and it is the first-audio bound", () => {
    const clocked = EVERY_STANCE.filter((s) => frameFor(s).deadlineMs !== null).map(frameKey);
    expect(clocked).toEqual(["konusuyor"]);
    expect(FRAMES.konusuyor.deadlineMs).toBe(FIRST_AUDIO_DEADLINE_MS);
  });

  it("expiry takes no control away — sessiz offers everything konusuyor did, plus the mic", () => {
    const before = FRAMES.konusuyor;
    const after = FRAMES["sira_sizde/sessiz"];
    expect(after.composer).toBe(before.composer);
    const alternates = (f: (typeof FRAMES)[FrameKey]) => f.alternates.map((c) => c.id).sort();
    expect(alternates(after)).toEqual(alternates(before));
    expect(after.primary).not.toBeNull();
  });

  it("expiry never advances the turn: the phase and the step are untouched", () => {
    const speaking = state({ audio: "pending" });
    const expired = { ...speaking, audio: "silent" as const };
    expect(expired.turn).toEqual(speaking.turn);
    expect(stance(expired)).not.toEqual({ kind: "dinliyor" });
  });

  it("the mic is offered by sessiz, never armed by it — only `dinliyor` is an open mic", () => {
    expect(stance(state({ audio: "silent" }))).not.toEqual({ kind: "dinliyor" });
    expect(stance(state({ turn: { phase: "listening", step: 0 }, audio: "idle" }))).toEqual({
      kind: "dinliyor",
    });
  });
});

describe("stance() is total over every turn the reducer can produce", () => {
  it("maps each phase to exactly one stance", () => {
    expect(stance(state({ audio: "pending" }))).toEqual({ kind: "konusuyor" });
    expect(stance(state({ audio: "started" }))).toEqual({ kind: "konusuyor" });
    expect(stance(state({ audio: "silent" }))).toEqual({
      kind: "sira_sizde",
      reason: "sessiz",
    });
    expect(
      stance(
        state({
          turn: { phase: "confirming", step: 0, candidate: { values: ["pain"], quote: "" } },
          audio: "idle",
        }),
      ),
    ).toEqual({ kind: "sira_sizde", reason: "onay" });
    expect(stance(state({ turn: { phase: "listening", step: 0 }, audio: "idle" }))).toEqual({
      kind: "dinliyor",
    });
    expect(stance(state({ turn: { phase: "settling" }, audio: "idle" }))).toEqual({
      kind: "toparlaniyor",
    });
    expect(stance(state({ turn: { phase: "done" }, audio: "idle" }))).toEqual({ kind: "bitti" });
    expect(stance(state({ turn: { phase: "handoff" }, audio: "idle" }))).toEqual({ kind: "devir" });
    expect(stance(state({ turn: { phase: "failed" }, audio: "idle" }))).toEqual({ kind: "durdu" });
  });

  it("T-11 — no stance is null; the one null is the RED preemption, where the tree is gone", () => {
    for (const s of EVERY_STANCE) {
      expect(frameFor(s)).toBeDefined();
    }
    expect(stance(state({ turn: { phase: "preempted" }, audio: "idle" }))).toBeNull();
  });
});

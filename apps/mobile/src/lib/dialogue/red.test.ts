/**
 * INT-259 — the RED preempt contract (T-12).
 *
 * The RED *presentation* is deliberately not here: it inherits register ×
 * location with no defaults, the ON_SITE absence of the 112 affordance and
 * the UNKNOWN disambiguation branch, and it must not ride in a UI PR. What
 * ships here is the door and its lock.
 *
 * The lock is invariant 9: only a rules-engine RED result may carry
 * `priority: preempt`. A model-produced `candidate_flag` cannot reach the
 * decoder's accept branch, and neither can a payload that omits the register
 * or the location — invariant 21 gives those no permitted default.
 */
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { decodeRedTrigger } from "./red";
import { dialogueStreamReducer, initialDialogueStreamState, type StreamTurn } from "./stream";
import { intakeQuestions } from "../intake/questions";
import { stance } from "./stance";

const VALID = {
  ruleId: "rf.chest_pain_cardiac_features",
  source: "rules_engine",
  priority: "preempt",
  register: "ALERT",
  location: "ON_SITE",
};

describe("decodeRedTrigger — fails closed on everything but a rules-engine preempt", () => {
  it("accepts the one shape it is allowed to accept", () => {
    expect(decodeRedTrigger(VALID)).toEqual(VALID);
  });

  it("invariant 9 — an LLM candidate flag can never preempt", () => {
    expect(decodeRedTrigger({ ...VALID, source: "llm" })).toBeNull();
    expect(decodeRedTrigger({ ...VALID, source: "talker" })).toBeNull();
    expect(decodeRedTrigger({ ...VALID, priority: "normal" })).toBeNull();
  });

  it("invariant 21 — register and location have no permitted default", () => {
    const { register: _r, ...noRegister } = VALID;
    const { location: _l, ...noLocation } = VALID;
    expect(decodeRedTrigger(noRegister)).toBeNull();
    expect(decodeRedTrigger(noLocation)).toBeNull();
    expect(decodeRedTrigger({ ...VALID, register: "LOUD" })).toBeNull();
    expect(decodeRedTrigger({ ...VALID, location: "HOSPITAL" })).toBeNull();
  });

  it("every register and every location the rules engine may state is accepted", () => {
    for (const register of ["ALERT", "CALM", "SILENT", "DEFERRED_CLINICIAN"]) {
      for (const location of ["REMOTE", "ON_SITE", "UNKNOWN"]) {
        expect(decodeRedTrigger({ ...VALID, register, location })).not.toBeNull();
      }
    }
  });

  it("junk, absence and near-misses all decode to nothing", () => {
    for (const payload of [null, undefined, "", 0, [], {}, { ...VALID, ruleId: "" }]) {
      expect(decodeRedTrigger(payload)).toBeNull();
    }
  });
});

describe("T-12 — a decoded trigger preempts from every stance, unconditionally", () => {
  const EVERY_TURN: readonly StreamTurn[] = [
    { phase: "speaking", step: 0, intent: "question" },
    { phase: "listening", step: 0 },
    { phase: "confirming", step: 0, candidate: { values: ["pain"], quote: "ağrı" } },
    { phase: "settling" },
    { phase: "done" },
    { phase: "handoff" },
    { phase: "failed" },
  ];

  it("every turn — including the terminal ones that absorb everything else — preempts", () => {
    for (const turn of EVERY_TURN) {
      const before = { ...initialDialogueStreamState(intakeQuestions), turn };
      const after = dialogueStreamReducer(intakeQuestions, before, { type: "preempt" });
      expect(after.turn, `${turn.phase} did not preempt`).toEqual({ phase: "preempted" });
    }
  });

  it("the stance tree is gone: a preempted session has no stance to render", () => {
    const after = dialogueStreamReducer(
      intakeQuestions,
      initialDialogueStreamState(intakeQuestions),
      { type: "preempt" },
    );
    expect(stance(after)).toBeNull();
  });

  it("it is not dismissible: nothing brings the conversation back", () => {
    const preempted = dialogueStreamReducer(
      intakeQuestions,
      initialDialogueStreamState(intakeQuestions),
      { type: "preempt" },
    );
    for (const action of [
      { type: "speech_done" },
      { type: "barge_in" },
      { type: "audio_started" },
      { type: "speak" },
      { type: "confirm", values: ["pain"] },
      { type: "typed", workId: 9, text: "merhaba" },
    ] as const) {
      expect(dialogueStreamReducer(intakeQuestions, preempted, action).turn).toEqual({
        phase: "preempted",
      });
    }
  });

  it("no deadline gates it — the RED path arms no clock", () => {
    const source = readFileSync(join(__dirname, "red.ts"), "utf8");
    expect(source).not.toMatch(/setTimeout|setInterval|Deadline/);
  });
});

describe("the preempt path tears media down before it hands over", () => {
  const hook = readFileSync(join(__dirname, "useDialogueSession.ts"), "utf8");
  const preempt = hook.slice(hook.indexOf("const preempt ="), hook.indexOf("const leave ="));

  it("stops playback, drops the recording, aborts in-flight work and clears the clips", () => {
    expect(preempt).toMatch(/stopPlayback\(\)/);
    expect(preempt).toMatch(/stopAndDiscardRecording\(\)/);
    expect(preempt).toMatch(/abortRef\.current\?\.abort\(\)/);
    expect(preempt).toMatch(/clearDialogueClips\(\)/);
    expect(preempt).toMatch(/Keyboard\.dismiss\(\)/);
  });

  it("and only then calls the caller's handler", () => {
    expect(preempt.indexOf("stopPlayback()")).toBeLessThan(preempt.indexOf("onRedTrigger("));
  });

  it("no RED component is created here — the presentation is its own issue", () => {
    expect(() =>
      readFileSync(join(__dirname, "..", "..", "components", "RedScript.tsx")),
    ).toThrow();
  });
});

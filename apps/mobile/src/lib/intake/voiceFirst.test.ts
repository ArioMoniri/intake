/**
 * INT-239 intake entry: the spoken dialogue (karşılıklı konuşma) is the
 * ONLY voice entry. The machine holds exactly three phases — probe the
 * voice lane, run the dialogue, run the typed steps — so there is no
 * chooser to land on and no one-shot "record it all at once" path left.
 * Typed intake stays reachable from every phase (accessibility, and the
 * `typed` profile in files/03 §4.9.1), and every failure or skip lands in
 * the exact manual flow — never a dead end. Candidates are ANSWER
 * SUGGESTIONS only (invariant 1 posture: no triage, no diagnosis).
 */
import { describe, expect, it } from "vitest";

import { en } from "../i18n/en";
import { tr, type MessageKey } from "../i18n/tr";
import {
  initialVoiceIntakeState,
  resolveAnswer,
  voiceIntakeReducer,
  type VoiceIntakeAction,
  type VoiceIntakeState,
} from "./voiceFirst";

function run(state: VoiceIntakeState, ...actions: VoiceIntakeAction[]): VoiceIntakeState {
  return actions.reduce(voiceIntakeReducer, state);
}

const STEPS: VoiceIntakeState = { phase: "steps", prefill: {}, failed: false };

describe("voiceIntakeReducer — the dialogue is the only voice entry (INT-239)", () => {
  it("a ready voice lane goes STRAIGHT into the dialogue — no offer, no chooser", () => {
    const gate = initialVoiceIntakeState(true);
    expect(gate).toEqual({ phase: "gate" });
    expect(run(gate, { type: "voice_ready" })).toEqual({ phase: "dialogue" });
  });

  it("the machine has exactly three reachable phases", () => {
    const actions: VoiceIntakeAction[] = [
      { type: "voice_ready" },
      { type: "voice_unavailable" },
      { type: "candidates", prefill: {} },
      { type: "failure", prefill: {} },
      { type: "skip" },
    ];
    const seen = new Set<string>();
    const frontier: VoiceIntakeState[] = [initialVoiceIntakeState(true)];
    while (frontier.length > 0) {
      const state = frontier.pop()!;
      if (seen.has(state.phase)) {
        continue;
      }
      seen.add(state.phase);
      for (const action of actions) {
        frontier.push(voiceIntakeReducer(state, action));
      }
    }
    expect([...seen].sort()).toEqual(["dialogue", "gate", "steps"]);
  });

  it("ineligible sessions start straight in the manual steps", () => {
    expect(initialVoiceIntakeState(false)).toEqual(STEPS);
  });

  it("a failed probe falls back to the manual steps without a failure notice", () => {
    expect(run(initialVoiceIntakeState(true), { type: "voice_unavailable" })).toEqual(STEPS);
  });

  it("typed intake stays reachable from the probe and from inside the dialogue", () => {
    expect(run({ phase: "gate" }, { type: "skip" })).toEqual(STEPS);
    expect(run({ phase: "dialogue" }, { type: "skip" })).toEqual(STEPS);
  });

  it("a dialogue failure lands in the manual steps WITH the notice — answers are already committed", () => {
    expect(run({ phase: "dialogue" }, { type: "failure", prefill: {} })).toEqual({
      phase: "steps",
      prefill: {},
      failed: true,
    });
  });

  // INT-261. A failure and a hand-over land the patient in the SAME typed
  // steps, so they must arrive carrying the same thing. Before this issue the
  // failure branch hard-coded `prefill: {}`, which meant a suggestion the
  // dialogue had already extracted from the patient's own words survived a
  // tidy exit and was thrown away by an unlucky one — the patient then
  // answered, in text, a question they had already answered out loud.
  it("a failure carries the leftover suggestions too — nothing said is lost", () => {
    const prefill = { complaint: { values: ["pain"], quote: "göğsümde baskı var" } };
    expect(run({ phase: "dialogue" }, { type: "failure", prefill })).toEqual({
      phase: "steps",
      prefill,
      failed: true,
    });
  });

  it("the ask-ahead hand-over lands in steps with the leftover suggestions as prefill", () => {
    const prefill = { duration: { values: ["days"], quote: "birkaç gündür böyle" } };
    expect(run({ phase: "dialogue" }, { type: "candidates", prefill })).toEqual({
      phase: "steps",
      prefill,
      failed: false,
    });
    // Empty leftovers are NOT a failure: the dialogue committed what it
    // could and the patient answers the remaining questions fresh, quietly.
    expect(run({ phase: "dialogue" }, { type: "candidates", prefill: {} })).toEqual(STEPS);
  });

  it("steps is absorbing: late async results never yank the patient out of the flow", () => {
    expect(
      run(STEPS, { type: "candidates", prefill: { a: { values: ["x"], quote: "q" } } }),
    ).toEqual(STEPS);
    expect(run(STEPS, { type: "failure", prefill: {} })).toEqual(STEPS);
    expect(run(STEPS, { type: "voice_ready" })).toEqual(STEPS);
  });

  it("out-of-order actions are no-ops", () => {
    const gate: VoiceIntakeState = { phase: "gate" };
    expect(run(gate, { type: "candidates", prefill: {} })).toEqual(gate);
    const dialogue: VoiceIntakeState = { phase: "dialogue" };
    expect(run(dialogue, { type: "voice_ready" })).toEqual(dialogue);
    expect(run(dialogue, { type: "voice_unavailable" })).toEqual(dialogue);
  });
});

describe("resolveAnswer (per-question confirm / change / skip)", () => {
  const prefill = { values: ["pain", "dyspnoea"], quote: "göğsümde baskı var" };

  it("confirm keeps the suggested values", () => {
    expect(resolveAnswer(prefill, { type: "confirm" })).toEqual(["pain", "dyspnoea"]);
  });

  it("confirm returns a fresh array, not the prefill reference", () => {
    const resolved = resolveAnswer(prefill, { type: "confirm" });
    resolved.push("fever");
    expect(prefill.values).toEqual(["pain", "dyspnoea"]);
  });

  it("confirm without a suggestion yields an empty answer", () => {
    expect(resolveAnswer(undefined, { type: "confirm" })).toEqual([]);
  });

  it("change always wins over the suggestion", () => {
    expect(resolveAnswer(prefill, { type: "change", values: ["fever"] })).toEqual(["fever"]);
  });

  it("skip clears the answer", () => {
    expect(resolveAnswer(prefill, { type: "skip" })).toEqual([]);
  });
});

describe("intake entry copy (tr source of truth + en mirror, invariant 5)", () => {
  const entryKeys = [
    "dialogue.kicker",
    "dialogue.entryTitle",
    "dialogue.entryBody",
    "voiceFirst.checking",
    "voiceFirst.listening",
    "voiceFirst.stop",
    "voiceFirst.preparing",
    "voiceFirst.typeInstead",
    "voiceFirst.saidLabel",
    "voiceFirst.suggested",
    "voiceFirst.failed",
    "dialogue.voiceMuted",
    "intake.progress.answered",
    "intake.progress.grows",
  ] as const satisfies readonly MessageKey[];

  it("every key exists non-empty in tr and in the en mirror", () => {
    for (const key of entryKeys) {
      expect(tr[key]?.trim().length, key).toBeGreaterThan(0);
      expect(en[key]?.trim().length, key).toBeGreaterThan(0);
    }
  });

  it("no numeral reaches the patient-facing entry copy (invariant 22 posture)", () => {
    for (const key of entryKeys) {
      expect(tr[key], key).not.toMatch(/[0-9]/u);
      expect(en[key], key).not.toMatch(/[0-9]/u);
    }
  });

  it("the entry names the conversation and offers typing as the quiet second door", () => {
    expect(tr["dialogue.kicker"]).toBe("Karşılıklı konuşma");
    expect(tr["voiceFirst.typeInstead"]).toBe("Yazarak devam edin");
    expect(tr["voiceFirst.saidLabel"].startsWith("Söylediğiniz")).toBe(true);
  });

  it("the one-shot 'record it all at once' copy is gone from both catalogs", () => {
    const removed = ["voiceFirst.title", "voiceFirst.start", "voiceFirst.cancel", "dialogue.start"];
    for (const key of removed) {
      expect((tr as Record<string, string>)[key], key).toBeUndefined();
      expect((en as Record<string, string>)[key], key).toBeUndefined();
    }
  });

  it("candidates are framed as suggestions to confirm, never findings (invariant 1 posture)", () => {
    expect(tr["voiceFirst.suggested"].toLocaleLowerCase("tr-TR")).toContain("öneri");
    for (const key of entryKeys) {
      expect(tr[key].toLocaleLowerCase("tr-TR"), key).not.toContain("tanı");
      expect(tr[key].toLocaleLowerCase("tr-TR"), key).not.toContain("teşhis");
    }
  });
});

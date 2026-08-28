/**
 * INT-199 voice-first intake: pure state machine for the entry flow
 * (offer → record → transcribe → extract → prefilled confirm steps), the
 * transcript→prefill mapping for a pack, and the per-question
 * confirm/change/skip resolution. Every failure or skip lands in the exact
 * manual flow — never a dead end. Candidates are ANSWER SUGGESTIONS only
 * (invariant 1 posture: no triage, no diagnosis leaves this module).
 */
import { describe, expect, it } from "vitest";

import { en } from "../i18n/en";
import { tr, type MessageKey } from "../i18n/tr";
import { toQuestionSpecs, validateExtractResponse } from "../extract";
import { packForDepartment } from "./questions";
import {
  initialVoiceIntakeState,
  prefillForPack,
  resolveAnswer,
  voiceIntakeReducer,
  type VoiceIntakeAction,
  type VoiceIntakeState,
} from "./voiceFirst";

const cardio = packForDepartment("Kardiyoloji");

function run(state: VoiceIntakeState, ...actions: VoiceIntakeAction[]): VoiceIntakeState {
  return actions.reduce(voiceIntakeReducer, state);
}

describe("voiceIntakeReducer", () => {
  it("ineligible sessions start straight in the manual steps", () => {
    expect(initialVoiceIntakeState(false)).toEqual({
      phase: "steps",
      prefill: {},
      failed: false,
    });
  });

  it("eligible sessions gate on the ASR probe, then offer voice first", () => {
    const gate = initialVoiceIntakeState(true);
    expect(gate).toEqual({ phase: "gate" });
    expect(run(gate, { type: "voice_ready" })).toEqual({ phase: "offer" });
  });

  it("a failed probe falls back to the manual steps without a failure notice", () => {
    expect(run(initialVoiceIntakeState(true), { type: "voice_unavailable" })).toEqual({
      phase: "steps",
      prefill: {},
      failed: false,
    });
  });

  it("walks the happy path: offer → recording → transcribing → extracting → prefilled steps", () => {
    const prefill = { complaint: { values: ["pain"], quote: "ağrım var" } };
    let state = run(initialVoiceIntakeState(true), { type: "voice_ready" });
    state = run(state, { type: "record" });
    expect(state).toEqual({ phase: "recording" });
    state = run(state, { type: "stop" });
    expect(state).toEqual({ phase: "transcribing" });
    state = run(state, { type: "transcript" });
    expect(state).toEqual({ phase: "extracting" });
    state = run(state, { type: "candidates", prefill });
    expect(state).toEqual({ phase: "steps", prefill, failed: false });
  });

  it("failure from any voice phase lands in the manual steps with the notice", () => {
    for (const phase of [
      { phase: "recording" },
      { phase: "transcribing" },
      { phase: "extracting" },
    ] as const) {
      expect(run(phase, { type: "failure" })).toEqual({
        phase: "steps",
        prefill: {},
        failed: true,
      });
    }
  });

  it("skip from any voice phase lands in the manual steps quietly", () => {
    for (const phase of [
      { phase: "offer" },
      { phase: "recording" },
      { phase: "extracting" },
    ] as const) {
      expect(run(phase, { type: "skip" })).toEqual({ phase: "steps", prefill: {}, failed: false });
    }
  });

  it("steps is absorbing: late async results never yank the patient out of the flow", () => {
    const steps: VoiceIntakeState = { phase: "steps", prefill: {}, failed: false };
    expect(run(steps, { type: "transcript" })).toEqual(steps);
    expect(
      run(steps, { type: "candidates", prefill: { complaint: { values: ["pain"], quote: "q" } } }),
    ).toEqual(steps);
    expect(run(steps, { type: "failure" })).toEqual(steps);
    expect(run(steps, { type: "voice_ready" })).toEqual(steps);
  });

  it("out-of-order actions are no-ops (stop before record, candidates before extracting)", () => {
    const offer: VoiceIntakeState = { phase: "offer" };
    expect(run(offer, { type: "stop" })).toEqual(offer);
    expect(run(offer, { type: "transcript" })).toEqual(offer);
    expect(run(offer, { type: "candidates", prefill: {} })).toEqual(offer);
  });
});

describe("prefillForPack (transcript → intake state, cardio pack fixture)", () => {
  const candidates = {
    complaint: { values: ["pain", "dyspnoea"], quote: "Göğsümde baskı var, nefesim daralıyor" },
    duration: { values: ["days"], quote: "birkaç gündür böyle" },
    onset: { values: ["sudden"], quote: "aniden başladı" },
    extra: { values: ["Merdiven çıkarken artıyor"], quote: "merdiven çıkarken artıyor" },
  };

  it("keeps only questions that exist in the pack, in pack order", () => {
    const prefill = prefillForPack(cardio, candidates);
    expect(Object.keys(prefill)).toEqual(["complaint", "duration", "extra"]);
  });

  it("carries values and the verbatim quote as provenance", () => {
    const prefill = prefillForPack(cardio, candidates);
    expect(prefill.complaint).toEqual({
      values: ["pain", "dyspnoea"],
      quote: "Göğsümde baskı var, nefesim daralıyor",
    });
    expect(prefill.extra).toEqual({
      values: ["Merdiven çıkarken artıyor"],
      quote: "merdiven çıkarken artıyor",
    });
  });

  it("copies values — mutating the prefill never touches the wire result", () => {
    const prefill = prefillForPack(cardio, candidates);
    prefill.complaint.values.push("fever");
    expect(candidates.complaint.values).toEqual(["pain", "dyspnoea"]);
  });

  it("composes with the validated wire response end-to-end", () => {
    const specs = toQuestionSpecs(cardio);
    const validated = validateExtractResponse(
      {
        candidates: {
          complaint: { values: ["pain", "not_an_option"], quote: "göğsümde baskı var" },
          duration: { values: ["days", "week"], quote: "birkaç gündür, belki daha uzun" },
          extra: { values: ["Merdiven çıkarken artıyor"], quote: "merdiven çıkarken artıyor" },
        },
        dropped: [],
        model: "qwen3.5-9b",
      },
      specs,
    );
    expect(validated.ok).toBe(true);
    if (validated.ok) {
      const prefill = prefillForPack(cardio, validated.candidates);
      // the ambiguous single was dropped by validation, never guessed
      expect(Object.keys(prefill)).toEqual(["complaint", "extra"]);
      expect(prefill.complaint.values).toEqual(["pain"]);
    }
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

describe("voice-first copy (tr source of truth + en mirror, invariant 5)", () => {
  const newKeys = [
    "voiceFirst.kicker",
    "voiceFirst.title",
    "voiceFirst.body",
    "voiceFirst.checking",
    "voiceFirst.start",
    "voiceFirst.listening",
    "voiceFirst.stop",
    "voiceFirst.transcribing",
    "voiceFirst.preparing",
    "voiceFirst.preparingHint",
    "voiceFirst.typeInstead",
    "voiceFirst.cancel",
    "voiceFirst.saidLabel",
    "voiceFirst.suggested",
    "voiceFirst.failed",
  ] as const satisfies readonly MessageKey[];

  it("every key exists non-empty in tr and in the en mirror", () => {
    for (const key of newKeys) {
      expect(tr[key]?.trim().length, key).toBeGreaterThan(0);
      expect(en[key]?.trim().length, key).toBeGreaterThan(0);
    }
  });

  it("no numeral reaches the patient-facing voice copy (invariant 22 posture)", () => {
    for (const key of newKeys) {
      expect(tr[key], key).not.toMatch(/[0-9]/u);
      expect(en[key], key).not.toMatch(/[0-9]/u);
    }
  });

  it("the opener asks for the patient's own words and provenance is 'Söylediğiniz'", () => {
    expect(tr["voiceFirst.title"]).toBe("Şikâyetinizi kendi cümlelerinizle anlatın");
    expect(tr["voiceFirst.saidLabel"].startsWith("Söylediğiniz")).toBe(true);
  });

  it("candidates are framed as suggestions to confirm, never findings (invariant 1 posture)", () => {
    expect(tr["voiceFirst.suggested"].toLocaleLowerCase("tr-TR")).toContain("öneri");
    expect(tr["voiceFirst.body"].toLocaleLowerCase("tr-TR")).toContain("onay");
    for (const key of newKeys) {
      expect(tr[key].toLocaleLowerCase("tr-TR"), key).not.toContain("tanı");
      expect(tr[key].toLocaleLowerCase("tr-TR"), key).not.toContain("teşhis");
    }
  });
});

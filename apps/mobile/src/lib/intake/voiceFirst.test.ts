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

describe("voiceIntakeReducer — spoken dialogue entry (INT-233)", () => {
  it("the offer's second path opens the dialogue mode", () => {
    expect(run({ phase: "offer" }, { type: "dialogue" })).toEqual({ phase: "dialogue" });
  });

  it("dialogue is only reachable from the offer", () => {
    expect(run({ phase: "gate" }, { type: "dialogue" })).toEqual({ phase: "gate" });
    expect(run({ phase: "recording" }, { type: "dialogue" })).toEqual({ phase: "recording" });
    const steps: VoiceIntakeState = { phase: "steps", prefill: {}, failed: false };
    expect(run(steps, { type: "dialogue" })).toEqual(steps);
  });

  it("a dialogue failure lands in the manual steps WITH the notice — answers are already committed per step", () => {
    expect(run({ phase: "dialogue" }, { type: "failure" })).toEqual({
      phase: "steps",
      prefill: {},
      failed: true,
    });
  });

  it("leaving the dialogue by choice lands in the manual steps quietly", () => {
    expect(run({ phase: "dialogue" }, { type: "skip" })).toEqual({
      phase: "steps",
      prefill: {},
      failed: false,
    });
  });

  it("stale one-shot actions never move the dialogue", () => {
    const dialogue: VoiceIntakeState = { phase: "dialogue" };
    expect(run(dialogue, { type: "record" })).toEqual(dialogue);
    expect(run(dialogue, { type: "transcript" })).toEqual(dialogue);
    expect(run(dialogue, { type: "voice_ready" })).toEqual(dialogue);
  });

  it("the ask-ahead hand-over (INT-235) lands in steps with the leftover suggestions as prefill", () => {
    // The dialogue already committed every confirmed answer; what could not
    // be confirmed in-conversation arrives as prefill for the manual steps.
    const dialogue: VoiceIntakeState = { phase: "dialogue" };
    const prefill = { duration: { values: ["days"], quote: "birkaç gündür böyle" } };
    expect(run(dialogue, { type: "candidates", prefill })).toEqual({
      phase: "steps",
      prefill,
      failed: false,
    });
    // Empty leftovers are NOT a failure here (unlike the one-shot extract):
    // the patient simply answers the remaining questions fresh, quietly.
    expect(run(dialogue, { type: "candidates", prefill: {} })).toEqual({
      phase: "steps",
      prefill: {},
      failed: false,
    });
  });
});

describe("prefillForPack (transcript → intake state, cardio pack fixture)", () => {
  const candidates = {
    complaint: { values: ["pain", "dyspnoea"], quote: "Göğsümde baskı var, nefesim daralıyor" },
    duration: { values: ["days"], quote: "birkaç gündür böyle" },
    onset: { values: ["sudden"], quote: "aniden başladı" },
    // derm_character belongs to another pack — must be dropped, not reordered.
    derm_character: { values: ["itchy"], quote: "kaşınıyor" },
    extra: { values: ["Merdiven çıkarken artıyor"], quote: "merdiven çıkarken artıyor" },
  };

  it("keeps only questions that exist in the pack, in pack order", () => {
    const prefill = prefillForPack(cardio, candidates);
    expect(Object.keys(prefill)).toEqual(["complaint", "duration", "onset", "extra"]);
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

describe("empty extract is a FAILED voice run (live silent-prefill bug, coordinator repro)", () => {
  const specs = toQuestionSpecs(cardio);
  const extracting: VoiceIntakeState = { phase: "extracting" };

  // Captured verbatim from the live daemon (warm) for the exact repro
  // transcript — the proven-good contract: eight of nine questions prefill,
  // onset dropped by the daemon itself.
  const capturedWarmResponse = {
    candidates: {
      complaint: { values: ["pain"], quote: "göğsümde baskınca baskı var" },
      duration: { values: ["days"], quote: "üç günü" },
      pain_character: { values: ["pressure"], quote: "göğsümde baskınca baskı var" },
      radiation: { values: ["no_radiation"], quote: "göğsümde baskınca baskı var" },
      trigger: { values: ["exertion"], quote: "merdiven çiyor" },
      associated: { values: ["sweating"], quote: "terleme de oluyor" },
      severity: { values: ["moderate"], quote: "merdiven çiyor" },
      extra: {
        values: ["düzenli metoprolol kullanıyorum"],
        quote: "düzenli metoprolol kullanıyorum",
      },
    },
    dropped: ["onset"],
    model: "qwen3.5-9b",
  };

  // The same daemon inside its restart window: /health keeps answering 200
  // (llm_upstream is reported separately) and /extract answers a VALID
  // envelope carrying zero usable candidates. The flow must land this in
  // manual WITH the failure notice — an extract that yields no suggestion is
  // a failed voice attempt, never a silent success that renders exactly like
  // typed entry.
  const warmingWindowResponse = {
    candidates: {},
    dropped: [
      "complaint",
      "duration",
      "onset",
      "pain_character",
      "radiation",
      "trigger",
      "associated",
      "severity",
      "extra",
    ],
    model: "qwen3.5-9b",
  };

  it("a valid envelope with zero surviving candidates lands in manual WITH the notice", () => {
    const validated = validateExtractResponse(warmingWindowResponse, specs);
    expect(validated.ok).toBe(true);
    if (validated.ok) {
      const prefill = prefillForPack(cardio, validated.candidates);
      expect(prefill).toEqual({});
      expect(run(extracting, { type: "candidates", prefill })).toEqual({
        phase: "steps",
        prefill: {},
        failed: true,
      });
    }
  });

  it("empty candidates outside extracting stay no-ops, and steps stays absorbing", () => {
    const offer: VoiceIntakeState = { phase: "offer" };
    expect(run(offer, { type: "candidates", prefill: {} })).toEqual(offer);
    const steps: VoiceIntakeState = { phase: "steps", prefill: {}, failed: false };
    expect(run(steps, { type: "candidates", prefill: {} })).toEqual(steps);
  });

  it("the captured live response prefills eight questions end-to-end (proven contract)", () => {
    const validated = validateExtractResponse(capturedWarmResponse, specs);
    expect(validated.ok).toBe(true);
    if (validated.ok) {
      const prefill = prefillForPack(cardio, validated.candidates);
      expect(Object.keys(prefill)).toEqual([
        "complaint",
        "duration",
        "pain_character",
        "radiation",
        "trigger",
        "associated",
        "severity",
        "extra",
      ]);
      const landed = run(extracting, { type: "candidates", prefill });
      expect(landed).toEqual({ phase: "steps", prefill, failed: false });
      if (landed.phase === "steps") {
        expect(landed.prefill.complaint).toEqual({
          values: ["pain"],
          quote: "göğsümde baskınca baskı var",
        });
        expect(landed.prefill.severity?.values).toEqual(["moderate"]);
      }
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

// ---- INT-236: prefill filtered by askIf (adaptive flow, DSL-mirrored) ------

describe("prefillForPack askIf filtering (INT-236)", () => {
  it("drops a gated suggestion when the suggested complaint does not meet its gate", () => {
    const prefill = prefillForPack(cardio, {
      complaint: { values: ["fever"], quote: "ateşim var" },
      pain_character: { values: ["pressure"], quote: "baskı gibi" },
    });
    expect(Object.keys(prefill)).toEqual(["complaint"]);
  });

  it("keeps the gated suggestion when the suggested complaint meets the gate", () => {
    const prefill = prefillForPack(cardio, {
      complaint: { values: ["pain"], quote: "göğsümde ağrı var" },
      pain_character: { values: ["pressure"], quote: "baskı gibi" },
    });
    expect(Object.keys(prefill)).toEqual(["complaint", "pain_character"]);
  });

  it("drops a gated suggestion when the gating question itself has no suggestion", () => {
    // The gate cannot be established from the transcript alone: the
    // question will surface (or not) once the patient answers the gating
    // question in the confirm flow — an unprovable suggestion never shows.
    const prefill = prefillForPack(cardio, {
      pain_character: { values: ["pressure"], quote: "baskı gibi" },
      duration: { values: ["days"], quote: "birkaç gündür" },
    });
    expect(Object.keys(prefill)).toEqual(["duration"]);
  });
});

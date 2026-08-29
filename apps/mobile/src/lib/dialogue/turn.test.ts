/**
 * INT-233 spoken dialogue mode: pure turn engine over a department pack.
 * Per step the agent SPEAKS the question (catalog tr text only), LISTENS,
 * transcribes, extracts against that single question, then speaks a short
 * confirmation with the candidate pre-selected. The engine is DISTURBABLE:
 * a barge-in during agent speech drops straight to listening. Every step
 * offers the typed fallback ("Yazarak yanıtlayın") for that step only, and
 * a hard service failure lands the whole flow in the existing manual steps
 * without losing prior answers (the component maps `failed` to the outer
 * voiceFirst failure action; answers are committed per step).
 *
 * DEV-TIER honesty: this is the in-app dev dialogue, not the production
 * LiveKit Talker (files/03 §4.9, files/13) — same posture as INT-199.
 */
import { describe, expect, it } from "vitest";

import { packForDepartment } from "../intake/questions";
import {
  dialogueReducer,
  initialDialogueState,
  type DialogueAction,
  type DialogueState,
} from "./turn";

const cardio = packForDepartment("Kardiyoloji");
const LAST = cardio.length - 1;

function run(state: DialogueState, ...actions: DialogueAction[]): DialogueState {
  return actions.reduce((s, a) => dialogueReducer(cardio, s, a), state);
}

const candidate = { values: ["days"], quote: "birkaç gündür böyle" };

describe("dialogueReducer — turn cycle", () => {
  it("starts by speaking the first question", () => {
    expect(initialDialogueState()).toEqual({ phase: "speaking", step: 0, intent: "question" });
  });

  it("walks one option turn: speak → listen → transcribe → extract → confirm speech → confirming", () => {
    let state = initialDialogueState();
    state = run(state, { type: "speech_done" });
    expect(state).toEqual({ phase: "listening", step: 0 });
    state = run(state, { type: "stop" });
    expect(state).toEqual({ phase: "transcribing", step: 0 });
    state = run(state, { type: "transcript", text: "göğsümde baskı var" });
    expect(state).toEqual({ phase: "extracting", step: 0 });
    state = run(state, { type: "candidate", candidate });
    expect(state).toEqual({ phase: "speaking", step: 0, intent: "confirm", candidate });
    state = run(state, { type: "speech_done" });
    expect(state).toEqual({ phase: "confirming", step: 0, candidate });
  });

  it("confirm advances to speaking the next question", () => {
    const confirming: DialogueState = { phase: "confirming", step: 0, candidate };
    expect(run(confirming, { type: "confirm" })).toEqual({
      phase: "speaking",
      step: 1,
      intent: "question",
    });
  });

  it("confirm on the last step completes the dialogue", () => {
    const confirming: DialogueState = { phase: "confirming", step: LAST, candidate };
    expect(run(confirming, { type: "confirm" })).toEqual({ phase: "done" });
  });

  it("a text-kind step takes the transcript as the candidate with NO extract hop", () => {
    // `extra` is the pack's free-text step: the patient's transcribed words
    // ARE the answer — no extract call, and the confirm speech for a text
    // step is the generic catalog line (patient words are never synthesized).
    const transcribing: DialogueState = { phase: "transcribing", step: LAST };
    expect(run(transcribing, { type: "transcript", text: "merdiven çıkarken artıyor" })).toEqual({
      phase: "speaking",
      step: LAST,
      intent: "confirm",
      candidate: { values: ["merdiven çıkarken artıyor"], quote: "merdiven çıkarken artıyor" },
    });
  });

  it("an empty transcript falls to typing for this step only — dialogue continues after commit", () => {
    const transcribing: DialogueState = { phase: "transcribing", step: 2 };
    const typed = run(transcribing, { type: "transcript", text: "" });
    expect(typed).toEqual({ phase: "typing", step: 2, prefill: null });
    expect(run(typed, { type: "commit" })).toEqual({
      phase: "speaking",
      step: 3,
      intent: "question",
    });
  });

  it("no usable candidate falls to typing for this step only", () => {
    const extracting: DialogueState = { phase: "extracting", step: 1 };
    expect(run(extracting, { type: "no_candidate" })).toEqual({
      phase: "typing",
      step: 1,
      prefill: null,
    });
  });
});

describe("dialogueReducer — barge-in (DISTURBABLE)", () => {
  it("a tap during question speech opens the mic immediately", () => {
    const speaking: DialogueState = { phase: "speaking", step: 3, intent: "question" };
    expect(run(speaking, { type: "barge_in" })).toEqual({ phase: "listening", step: 3 });
  });

  it("a tap during confirm speech is a spoken correction: back to listening, candidate dropped", () => {
    const speaking: DialogueState = { phase: "speaking", step: 3, intent: "confirm", candidate };
    expect(run(speaking, { type: "barge_in" })).toEqual({ phase: "listening", step: 3 });
  });

  it("from confirming the patient can speak the correction", () => {
    const confirming: DialogueState = { phase: "confirming", step: 3, candidate };
    expect(run(confirming, { type: "speak" })).toEqual({ phase: "listening", step: 3 });
  });

  it("barge-in outside agent speech is a no-op", () => {
    const listening: DialogueState = { phase: "listening", step: 3 };
    expect(run(listening, { type: "barge_in" })).toEqual(listening);
    const typing: DialogueState = { phase: "typing", step: 3, prefill: null };
    expect(run(typing, { type: "barge_in" })).toEqual(typing);
  });
});

describe("dialogueReducer — per-step typed fallback", () => {
  it("'Yazarak yanıtlayın' works from speaking and listening, with no prefill", () => {
    for (const state of [
      { phase: "speaking", step: 2, intent: "question" },
      { phase: "listening", step: 2 },
    ] as const) {
      expect(run(state, { type: "type" })).toEqual({ phase: "typing", step: 2, prefill: null });
    }
  });

  it("typing from a confirm context keeps the candidate as prefill", () => {
    const confirming: DialogueState = { phase: "confirming", step: 2, candidate };
    expect(run(confirming, { type: "type" })).toEqual({
      phase: "typing",
      step: 2,
      prefill: candidate,
    });
    const speakingConfirm: DialogueState = {
      phase: "speaking",
      step: 2,
      intent: "confirm",
      candidate,
    };
    expect(run(speakingConfirm, { type: "type" })).toEqual({
      phase: "typing",
      step: 2,
      prefill: candidate,
    });
  });

  it("commit from typing advances; on the last step it completes", () => {
    expect(run({ phase: "typing", step: 0, prefill: null }, { type: "commit" })).toEqual({
      phase: "speaking",
      step: 1,
      intent: "question",
    });
    expect(run({ phase: "typing", step: LAST, prefill: null }, { type: "commit" })).toEqual({
      phase: "done",
    });
  });
});

describe("dialogueReducer — failure continuity", () => {
  it("failure from any voice-loop phase is terminal (component falls to the manual steps)", () => {
    for (const state of [
      { phase: "speaking", step: 0, intent: "question" },
      { phase: "listening", step: 1 },
      { phase: "transcribing", step: 1 },
      { phase: "extracting", step: 1 },
      { phase: "confirming", step: 1, candidate },
    ] as const) {
      expect(run(state, { type: "failure" })).toEqual({ phase: "failed" });
    }
  });

  it("a late async failure NEVER ejects a patient who is already typing this step", () => {
    const typing: DialogueState = { phase: "typing", step: 1, prefill: null };
    expect(run(typing, { type: "failure" })).toEqual(typing);
  });

  it("done and failed are absorbing", () => {
    for (const terminal of [{ phase: "done" }, { phase: "failed" }] as const) {
      expect(run(terminal, { type: "speech_done" })).toEqual(terminal);
      expect(run(terminal, { type: "candidate", candidate })).toEqual(terminal);
      expect(run(terminal, { type: "failure" })).toEqual(terminal);
      expect(run(terminal, { type: "commit" })).toEqual(terminal);
    }
  });
});

describe("dialogueReducer — out-of-order actions are no-ops", () => {
  it("stale async results never move the machine", () => {
    const speaking: DialogueState = { phase: "speaking", step: 1, intent: "question" };
    expect(run(speaking, { type: "candidate", candidate })).toEqual(speaking);
    expect(run(speaking, { type: "transcript", text: "x" })).toEqual(speaking);
    expect(run(speaking, { type: "stop" })).toEqual(speaking);

    const listening: DialogueState = { phase: "listening", step: 1 };
    expect(run(listening, { type: "speech_done" })).toEqual(listening);
    expect(run(listening, { type: "transcript", text: "x" })).toEqual(listening);

    const typing: DialogueState = { phase: "typing", step: 1, prefill: null };
    expect(run(typing, { type: "candidate", candidate })).toEqual(typing);
    expect(run(typing, { type: "transcript", text: "x" })).toEqual(typing);

    const confirming: DialogueState = { phase: "confirming", step: 1, candidate };
    expect(run(confirming, { type: "transcript", text: "x" })).toEqual(confirming);
    expect(run(confirming, { type: "no_candidate" })).toEqual(confirming);
  });
});

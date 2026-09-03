/**
 * INT-235 ask-ahead conversation engine (owner feedback: kill the
 * "soru hazırlanıyor" wait). The blueprint IntakeEngine pattern
 * (02/INT-081) mirrored at dev tier: the next scripted question NEVER
 * waits for the previous answer's transcription/extraction — the turn
 * advances the moment the utterance is taken, and transcribe→extract
 * reconcile BEHIND, addressed by work id:
 *
 * - the patient bubble appears at once and the ASR text replaces it IN
 *   PLACE when transcription lands (the chat log is stateful by workId);
 * - extract results fill sections as pending SUGGESTIONS; out-of-order
 *   results resolve by work id (newest utterance wins per question);
 * - advance skips answered AND already-asked questions; a question whose
 *   suggestion has landed gets a quick spoken CONFIRM turn (one tap, no
 *   wait) instead of being re-asked — including retroactively, once its
 *   result arrives;
 * - typed input is the same conversation: a typed utterance behaves
 *   exactly like a spoken one (no mode switch);
 * - the honest wait exists only at the END (settling) while in-flight
 *   work drains; then: all answered → done (the owner's completion
 *   rule), anything left → handoff to the manual steps.
 *
 * Invariant 1 posture: candidates are SUGGESTIONS — the only commit
 * paths are the confirm turn, the panel-row confirm, and the manual
 * steps after handoff. Nothing auto-commits.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { intakeQuestions, packForDepartment } from "../intake/questions";
import {
  dialogueStreamReducer,
  initialDialogueStreamState,
  shouldAttemptSpeech,
  type DialogueStreamAction,
  type DialogueStreamState,
} from "./stream";
import type { DialogueCandidate } from "./turn";

const cardio = packForDepartment("Kardiyoloji");
const general = intakeQuestions; // complaint → duration → extra

function runCardio(state: DialogueStreamState, ...actions: DialogueStreamAction[]) {
  return actions.reduce((s, a) => dialogueStreamReducer(cardio, s, a), state);
}

function runGeneral(state: DialogueStreamState, ...actions: DialogueStreamAction[]) {
  return actions.reduce((s, a) => dialogueStreamReducer(general, s, a), state);
}

/** Convenience literal for states the tests construct directly. */
function state(overrides: Partial<DialogueStreamState>): DialogueStreamState {
  return {
    turn: { phase: "speaking", step: 0, intent: "question" },
    pending: {},
    answers: {},
    asked: [],
    inflight: [],
    seq: {},
    stream: [],
    voiceMuted: false,
    voiceFailures: 0,
    voiceRetryIn: 0,
    ...overrides,
  };
}

const painCandidate: DialogueCandidate = { values: ["pain"], quote: "göğsümde baskı var" };
const daysCandidate: DialogueCandidate = { values: ["days"], quote: "birkaç gündür böyle" };
const weekCandidate: DialogueCandidate = { values: ["week"], quote: "bir haftadır" };
const suddenCandidate: DialogueCandidate = { values: ["sudden"], quote: "aniden başladı" };

describe("dialogueStreamReducer — ask-ahead: the next question never waits", () => {
  it("starts by speaking the first question and logging it", () => {
    expect(initialDialogueStreamState(general)).toEqual(
      state({ stream: [{ kind: "agent_question", questionId: "complaint" }], voiceMuted: false }),
    );
  });

  it("the utterance advances the turn IMMEDIATELY — extraction still in flight", () => {
    let s = initialDialogueStreamState(general);
    s = runGeneral(s, { type: "speech_done" });
    expect(s.turn).toEqual({ phase: "listening", step: 0 });
    s = runGeneral(s, { type: "utterance", workId: 1 });
    expect(s.turn).toEqual({ phase: "speaking", step: 1, intent: "question" });
    expect(s.asked).toEqual(["complaint"]);
    expect(s.inflight).toEqual([1]);
    expect(s.stream).toEqual([
      { kind: "agent_question", questionId: "complaint" },
      { kind: "patient", workId: 1, status: "transcribing", text: "" },
      { kind: "agent_question", questionId: "duration" },
    ]);
  });

  it("the ASR text replaces the right earlier bubble IN PLACE, later turns untouched", () => {
    const before = state({
      turn: { phase: "speaking", step: 1, intent: "question" },
      asked: ["complaint"],
      inflight: [1],
      stream: [
        { kind: "agent_question", questionId: "complaint" },
        { kind: "patient", workId: 1, status: "transcribing", text: "" },
        { kind: "agent_question", questionId: "duration" },
      ],
    });
    const after = runGeneral(before, {
      type: "transcript_ready",
      workId: 1,
      text: "  göğsümde baskı var  ",
    });
    expect(after.turn).toEqual(before.turn);
    expect(after.stream).toEqual([
      { kind: "agent_question", questionId: "complaint" },
      { kind: "patient", workId: 1, status: "text", text: "göğsümde baskı var" },
      { kind: "agent_question", questionId: "duration" },
    ]);
  });

  it("an empty transcript removes the pending bubble; the question is never re-asked", () => {
    const before = state({
      turn: { phase: "speaking", step: 1, intent: "question" },
      asked: ["complaint"],
      inflight: [1],
      stream: [
        { kind: "agent_question", questionId: "complaint" },
        { kind: "patient", workId: 1, status: "transcribing", text: "" },
        { kind: "agent_question", questionId: "duration" },
      ],
    });
    let s = runGeneral(before, { type: "transcript_ready", workId: 1, text: "   " });
    expect(s.stream).toEqual([
      { kind: "agent_question", questionId: "complaint" },
      { kind: "agent_question", questionId: "duration" },
    ]);
    expect(s.asked).toEqual(["complaint"]);
    s = runGeneral(
      s,
      { type: "extract_settled", workId: 1, candidates: {} },
      { type: "speech_done" },
      { type: "utterance", workId: 2 },
    );
    // complaint stays skipped (asked, no answer) — extra is next, not a re-ask
    expect(s.turn).toEqual({ phase: "speaking", step: 2, intent: "question" });
  });
});

describe("dialogueStreamReducer — reconcile behind, ordered by work id", () => {
  it("extract results fill earlier sections as suggestions and drain inflight", () => {
    const before = state({
      turn: { phase: "speaking", step: 1, intent: "question" },
      asked: ["complaint"],
      inflight: [1],
      answers: { severity: { values: ["mild"], quote: "hafif" } },
    });
    const after = runCardio(before, {
      type: "extract_settled",
      workId: 1,
      candidates: {
        complaint: painCandidate, // asked earlier, unanswered → absorbs
        duration: daysCandidate, // CURRENT question — the turn owns it
        severity: { values: ["severe"], quote: "çok şiddetli" }, // answered
        bogus_question: daysCandidate, // not in the pack
        onset: suddenCandidate, // ahead of the turn → absorbs
      },
    });
    expect(after.pending).toEqual({ complaint: painCandidate, onset: suddenCandidate });
    expect(after.seq).toEqual({ complaint: 1, onset: 1 });
    expect(after.inflight).toEqual([]);
    expect(after.turn).toEqual(before.turn); // reconcile never moves a live turn
  });

  it("out-of-order results: a late OLDER result never overwrites a newer suggestion", () => {
    const before = state({
      turn: { phase: "speaking", step: 2, intent: "question" },
      asked: ["complaint", "duration"],
      inflight: [1, 2],
    });
    let s = runCardio(before, {
      type: "extract_settled",
      workId: 2,
      candidates: { duration: weekCandidate },
    });
    expect(s.pending.duration).toEqual(weekCandidate);
    s = runCardio(s, {
      type: "extract_settled",
      workId: 1,
      candidates: { duration: daysCandidate },
    });
    expect(s.pending.duration).toEqual(weekCandidate); // newest utterance wins
    expect(s.seq.duration).toBe(2);
    expect(s.inflight).toEqual([]);
  });
});

describe("dialogueStreamReducer — skip and the quick confirm turn", () => {
  it("advance skips answered AND asked-awaiting questions", () => {
    const before = state({
      turn: { phase: "listening", step: 0 },
      answers: { duration: { values: ["today"], quote: "" } },
    });
    const after = runGeneral(before, { type: "utterance", workId: 1 });
    expect(after.turn).toEqual({ phase: "speaking", step: 2, intent: "question" });
  });

  it("a landed suggestion opens as the spoken confirm turn instead of a re-ask", () => {
    const before = state({
      turn: { phase: "listening", step: 0 },
      pending: { duration: daysCandidate },
      seq: { duration: 1 },
      inflight: [],
    });
    const after = runCardio(before, { type: "utterance", workId: 2 });
    expect(after.turn).toEqual({
      phase: "speaking",
      step: 1,
      intent: "confirm",
      candidate: daysCandidate,
    });
    expect(after.pending).toEqual({});
    expect(after.stream[after.stream.length - 1]).toEqual({
      kind: "agent_confirm",
      questionId: "duration",
      values: ["days"],
    });
  });

  it("a result landing during the end wait gets its confirm turn retroactively", () => {
    const before = state({
      turn: { phase: "settling" },
      asked: ["complaint", "duration", "extra"],
      inflight: [3],
    });
    const after = runGeneral(before, {
      type: "extract_settled",
      workId: 3,
      candidates: { duration: daysCandidate },
    });
    expect(after.turn).toEqual({
      phase: "speaking",
      step: 1,
      intent: "confirm",
      candidate: daysCandidate,
    });
    expect(after.pending).toEqual({});
    expect(after.inflight).toEqual([]);
  });
});

describe("dialogueStreamReducer — typed input is the same conversation", () => {
  it("a typed utterance from a question turn behaves exactly like a spoken one", () => {
    const before = initialDialogueStreamState(general);
    const after = runGeneral(before, { type: "typed", workId: 1, text: " ateşim var " });
    expect(after.turn).toEqual({ phase: "speaking", step: 1, intent: "question" });
    expect(after.asked).toEqual(["complaint"]);
    expect(after.inflight).toEqual([1]);
    expect(after.stream).toEqual([
      { kind: "agent_question", questionId: "complaint" },
      { kind: "patient", workId: 1, status: "text", text: "ateşim var" },
      { kind: "agent_question", questionId: "duration" },
    ]);
  });

  it("typing over a confirm turn drops the candidate and moves on; the fresh result re-suggests", () => {
    const before = state({
      turn: { phase: "confirming", step: 1, candidate: daysCandidate },
      answers: { complaint: { values: ["pain"], quote: "göğsümde baskı var" } },
    });
    let s = runCardio(before, { type: "typed", workId: 2, text: "aslında bir haftadır" });
    expect(s.turn).toEqual({ phase: "speaking", step: 4, intent: "question" });
    expect(s.asked).toEqual(["duration"]);
    s = runCardio(s, {
      type: "extract_settled",
      workId: 2,
      candidates: { duration: weekCandidate },
    });
    expect(s.pending).toEqual({ duration: weekCandidate }); // its confirm turn comes back around
  });

  it("typing during the end wait logs and keeps waiting; empty typed text is ignored", () => {
    const settling = state({
      turn: { phase: "settling" },
      asked: ["complaint", "duration", "extra"],
      inflight: [1],
    });
    const typed = runGeneral(settling, { type: "typed", workId: 2, text: "ek bir notum var" });
    expect(typed.turn).toEqual({ phase: "settling" });
    expect(typed.inflight).toEqual([1, 2]);
    expect(typed.stream).toEqual([
      { kind: "patient", workId: 2, status: "text", text: "ek bir notum var" },
    ]);
    expect(runGeneral(settling, { type: "typed", workId: 3, text: "   " })).toEqual(settling);
  });
});

describe("dialogueStreamReducer — confirm commits, panel confirm, completion", () => {
  it("confirm records the on-screen values with the candidate's quote, then skips ahead", () => {
    const before = state({
      turn: { phase: "confirming", step: 0, candidate: painCandidate },
      answers: { duration: { values: ["days"], quote: "birkaç gündür böyle" } },
      asked: ["complaint"],
    });
    const after = runCardio(before, { type: "confirm", values: ["pain", "fatigue"] });
    expect(after.answers.complaint).toEqual({
      values: ["pain", "fatigue"],
      quote: "göğsümde baskı var",
    });
    expect(after.turn).toEqual({ phase: "speaking", step: 4, intent: "question" });
  });

  it("confirming the last unanswered question completes the previsit — even with work in flight", () => {
    const before = state({
      turn: { phase: "confirming", step: 0, candidate: painCandidate },
      answers: {
        duration: { values: ["days"], quote: "" },
        extra: { values: [], quote: "" },
      },
      inflight: [9],
    });
    expect(runGeneral(before, { type: "confirm", values: ["pain"] }).turn).toEqual({
      phase: "done",
    });
  });

  it("panel confirm moves the suggestion into answers; guards hold", () => {
    const base = state({
      turn: { phase: "speaking", step: 0, intent: "question" },
      pending: { duration: daysCandidate },
      seq: { duration: 1 },
      stream: [{ kind: "agent_question", questionId: "complaint" }],
    });
    const confirmed = runCardio(base, { type: "confirm_pending", questionId: "duration" });
    expect(confirmed.answers.duration).toEqual({
      values: ["days"],
      quote: "birkaç gündür böyle",
    });
    expect(confirmed.pending).toEqual({});
    expect(confirmed.turn).toEqual(base.turn);

    // unknown id, the current question, an answered question: no-ops
    expect(runCardio(base, { type: "confirm_pending", questionId: "onset" })).toEqual(base);
    const currentPending = { ...base, pending: { complaint: painCandidate } };
    expect(runCardio(currentPending, { type: "confirm_pending", questionId: "complaint" })).toEqual(
      currentPending,
    );
    const answered = { ...base, answers: { duration: { values: ["today"], quote: "" } } };
    expect(runCardio(answered, { type: "confirm_pending", questionId: "duration" })).toEqual(
      answered,
    );
  });

  it("a panel confirm during the end wait can complete the previsit", () => {
    const before = state({
      turn: { phase: "settling" },
      answers: {
        complaint: { values: ["pain"], quote: "" },
        duration: { values: ["days"], quote: "" },
      },
      pending: { extra: { values: ["merdivende artıyor"], quote: "merdivende artıyor" } },
      asked: ["complaint", "duration", "extra"],
      inflight: [4],
    });
    const after = runGeneral(before, { type: "confirm_pending", questionId: "extra" });
    expect(after.turn).toEqual({ phase: "done" });
  });
});

describe("dialogueStreamReducer — the honest wait exists only at the end", () => {
  it("nothing left to ask + work in flight → settling", () => {
    const before = state({
      turn: { phase: "listening", step: 2 },
      asked: ["complaint", "duration"],
      inflight: [1, 2],
    });
    const after = runGeneral(before, { type: "utterance", workId: 3 });
    expect(after.turn).toEqual({ phase: "settling" });
    expect(after.inflight).toEqual([1, 2, 3]);
    expect(after.stream).toEqual([
      { kind: "patient", workId: 3, status: "transcribing", text: "" },
    ]);
  });

  it("settled with unanswered questions left → handoff to the manual steps", () => {
    const before = state({
      turn: { phase: "settling" },
      asked: ["complaint", "duration", "extra"],
      answers: { complaint: { values: ["pain"], quote: "" } },
      inflight: [3],
    });
    const after = runGeneral(before, { type: "extract_settled", workId: 3, candidates: {} });
    expect(after.turn).toEqual({ phase: "handoff" });
  });

  it("settled with everything answered → done", () => {
    const before = state({
      turn: { phase: "settling" },
      asked: ["complaint", "duration", "extra"],
      answers: {
        complaint: { values: ["pain"], quote: "" },
        duration: { values: ["days"], quote: "" },
        extra: { values: [], quote: "" },
      },
      inflight: [5],
    });
    const after = runGeneral(before, { type: "extract_settled", workId: 5, candidates: {} });
    expect(after.turn).toEqual({ phase: "done" });
  });
});

// ---- INT-239: the conversation follows the answers, not the file order ----

describe("dialogueStreamReducer — answer-driven advance (INT-239)", () => {
  /** cardio: pain_character and radiation are gated on complaint ⊇ pain. */
  it("a question whose gate is unmet is never spoken", () => {
    const before = state({
      turn: { phase: "confirming", step: 0, candidate: { values: ["fever"], quote: "ateşim var" } },
      answers: {
        duration: { values: ["days"], quote: "" },
        onset: { values: ["sudden"], quote: "" },
      },
    });
    const after = runCardio(before, { type: "confirm", values: ["fever"] });
    // trigger is next: both pain dimensions are skipped, not asked-and-empty
    expect(after.turn).toEqual({ phase: "speaking", step: 10, intent: "question" });
    expect(after.stream[after.stream.length - 1]).toEqual({
      kind: "agent_question",
      questionId: "trigger",
    });
  });

  it("the same confirm with a different answer opens the gated questions", () => {
    const before = state({
      turn: {
        phase: "confirming",
        step: 0,
        candidate: { values: ["pain"], quote: "göğsümde baskı var" },
      },
      answers: {
        onset: { values: ["sudden"], quote: "" },
        duration: { values: ["days"], quote: "" },
      },
    });
    const after = runCardio(before, { type: "confirm", values: ["pain"] });
    expect(after.turn).toEqual({ phase: "speaking", step: 5, intent: "question" });
    expect(after.stream[after.stream.length - 1]).toEqual({
      kind: "agent_question",
      questionId: "pain_character",
    });
  });

  it("a gate that opens two levels deep is asked once its parent answer lands", () => {
    const before = state({
      turn: {
        phase: "confirming",
        step: 6,
        candidate: { values: ["arm"], quote: "koluma vuruyor" },
      },
      answers: {
        complaint: { values: ["pain"], quote: "" },
        duration: { values: ["days"], quote: "" },
        onset: { values: ["sudden"], quote: "" },
        pain_character: { values: ["pressure"], quote: "" },
      },
    });
    const after = runCardio(before, { type: "confirm", values: ["arm"] });
    expect(after.stream[after.stream.length - 1]).toEqual({
      kind: "agent_question",
      questionId: "radiation_side",
    });
  });

  it("completion ignores questions whose gate is unmet — a fever intake finishes", () => {
    const answered = (ids: string[]) =>
      Object.fromEntries(ids.map((id) => [id, { values: ["x"], quote: "" }]));
    const before = state({
      turn: { phase: "settling" },
      answers: answered(["duration", "onset", "trigger", "associated", "severity", "extra"]),
      asked: ["complaint", "duration", "onset", "trigger", "associated", "severity", "extra"],
      inflight: [1],
      pending: { complaint: { values: ["fever"], quote: "ateşim var" } },
    });
    // The complaint's suggestion confirms → nothing gated is open → done.
    const withConfirm = runCardio(before, { type: "extract_settled", workId: 1, candidates: {} });
    expect(withConfirm.turn).toEqual({
      phase: "speaking",
      step: 0,
      intent: "confirm",
      candidate: { values: ["fever"], quote: "ateşim var" },
    });
    const done = runCardio(
      {
        ...withConfirm,
        turn: {
          phase: "confirming",
          step: 0,
          candidate: { values: ["fever"], quote: "ateşim var" },
        },
      },
      { type: "confirm", values: ["fever"] },
    );
    expect(done.turn).toEqual({ phase: "done" });
  });

  it("a suggestion for a still-closed gate waits, then gets its confirm turn when the gate opens", () => {
    // The patient volunteers the radiation while answering the complaint.
    const before = state({
      turn: { phase: "confirming", step: 0, candidate: { values: ["pain"], quote: "göğsüm" } },
      pending: { radiation: { values: ["arm"], quote: "koluma vuruyor" } },
      seq: { radiation: 1 },
      answers: {
        duration: { values: ["days"], quote: "" },
        onset: { values: ["sudden"], quote: "" },
        pain_character: { values: ["pressure"], quote: "" },
      },
    });
    const after = runCardio(before, { type: "confirm", values: ["pain"] });
    expect(after.turn).toEqual({
      phase: "speaking",
      step: 6,
      intent: "confirm",
      candidate: { values: ["arm"], quote: "koluma vuruyor" },
    });
  });

  it("a panel confirm cannot commit an answer to a question the flow does not ask", () => {
    const before = state({
      turn: { phase: "speaking", step: 1, intent: "question" },
      answers: { complaint: { values: ["fever"], quote: "" } },
      pending: { radiation: { values: ["arm"], quote: "koluma vuruyor" } },
      seq: { radiation: 1 },
    });
    expect(runCardio(before, { type: "confirm_pending", questionId: "radiation" })).toEqual(before);
  });
});

describe("dialogueStreamReducer — turn micro-transitions and terminals", () => {
  it("speech_done: a question opens the mic, a confirm opens the confirming card", () => {
    const question = state({ turn: { phase: "speaking", step: 1, intent: "question" } });
    expect(runCardio(question, { type: "speech_done" }).turn).toEqual({
      phase: "listening",
      step: 1,
    });
    const confirm = state({
      turn: { phase: "speaking", step: 1, intent: "confirm", candidate: daysCandidate },
    });
    expect(runCardio(confirm, { type: "speech_done" }).turn).toEqual({
      phase: "confirming",
      step: 1,
      candidate: daysCandidate,
    });
  });

  it("barge-in during either speaking intent opens the mic; speak-correction too", () => {
    const confirmSpeech = state({
      turn: { phase: "speaking", step: 3, intent: "confirm", candidate: painCandidate },
      pending: { onset: suddenCandidate },
    });
    const bargedIn = runCardio(confirmSpeech, { type: "barge_in" });
    expect(bargedIn.turn).toEqual({ phase: "listening", step: 3 });
    expect(bargedIn.pending).toEqual(confirmSpeech.pending);
    const confirming = state({ turn: { phase: "confirming", step: 3, candidate: painCandidate } });
    expect(runCardio(confirming, { type: "speak" }).turn).toEqual({ phase: "listening", step: 3 });
  });

  it("stale actions are no-ops", () => {
    const speaking = state({
      turn: { phase: "speaking", step: 1, intent: "question" },
      stream: [{ kind: "agent_question", questionId: "duration" }],
    });
    expect(runCardio(speaking, { type: "utterance", workId: 9 })).toEqual(speaking);
    expect(runCardio(speaking, { type: "confirm", values: ["days"] })).toEqual(speaking);
    expect(runCardio(speaking, { type: "transcript_ready", workId: 9, text: "x" })).toEqual(
      speaking,
    );
  });

  it("failure is terminal and preserves the log and answers for the hand-over", () => {
    const before = state({
      turn: { phase: "listening", step: 1 },
      answers: { complaint: { values: ["pain"], quote: "göğsümde baskı var" } },
      stream: [{ kind: "agent_question", questionId: "duration" }],
    });
    const after = runCardio(before, { type: "failure" });
    expect(after.turn).toEqual({ phase: "failed" });
    expect(after.answers).toEqual(before.answers);
    expect(after.stream).toEqual(before.stream);
  });

  it("done, failed and handoff are absorbing", () => {
    for (const phase of ["done", "failed", "handoff"] as const) {
      const terminal = state({ turn: { phase } });
      expect(runCardio(terminal, { type: "utterance", workId: 1 })).toEqual(terminal);
      expect(runCardio(terminal, { type: "typed", workId: 1, text: "x" })).toEqual(terminal);
      expect(runCardio(terminal, { type: "extract_settled", workId: 1, candidates: {} })).toEqual(
        terminal,
      );
      expect(runCardio(terminal, { type: "confirm_pending", questionId: "duration" })).toEqual(
        terminal,
      );
    }
  });
});

// INT-249. The speaking driver in useDialogueSession keys its effect on the
// turn OBJECT (`useEffect(..., [speaking])` where `speaking = state.turn`),
// so a reconcile that rebuilt an equal-but-new turn would re-enter the
// effect, re-run `store.ensure` and restart the clip from the top. With a
// lane that takes seconds to answer, that is a question the patient hears
// twice — or a turn that never lands at all, because every late ASR or
// extract result restarts the wait. `toEqual` cannot see this; only `toBe`
// can, which is why these assertions are identity and not equality.
describe("dialogueStreamReducer — late work cannot re-block a live turn (INT-249)", () => {
  const live = () =>
    state({
      turn: { phase: "speaking", step: 1, intent: "question" },
      asked: ["complaint"],
      inflight: [1],
    });

  it("keeps the very same turn object when a transcript lands behind", () => {
    const before = live();
    const after = runCardio(before, {
      type: "transcript_ready",
      workId: 1,
      text: "göğsüm ağrıyor",
    });
    expect(after.turn).toBe(before.turn);
  });

  it("keeps the very same turn object when an extract settles behind", () => {
    const before = live();
    const after = runCardio(before, {
      type: "extract_settled",
      workId: 1,
      candidates: { complaint: painCandidate },
    });
    expect(after.turn).toBe(before.turn);
  });

  it("keeps it across a whole reconcile sequence, not just one action", () => {
    const before = live();
    const after = runCardio(
      before,
      { type: "transcript_ready", workId: 1, text: "göğsüm ağrıyor" },
      { type: "extract_settled", workId: 1, candidates: { complaint: painCandidate } },
    );
    expect(after.turn).toBe(before.turn);
  });
});

// INT-261 — the agent losing its VOICE is not the conversation ending.
//
// The field report was "voice and text based dynamic questions gets mixed
// up", and the reproduction is one screen: answer the first spoken question,
// and the app drops into the typed form — which asks that same question
// again, from zero, under a notice saying the voice feature was unavailable.
// What actually happened is that the NEXT question's clip could not be
// synthesized: the ladder is admitted on a real short synthesis against
// TURN_ROUND_TRIP_BUDGET_MS (1684 ms), and measured on the dev host VoxCPM2
// takes 2.78 s — over budget by construction — while Freya's 1.01 s is close
// enough to the line that a cold first call trips it too. `store.ensure`
// then throws `tts_unreachable`, and the speaking driver escalated that to
// `failure`, which is terminal for the whole intake.
//
// It is the wrong escalation. Nothing in this conversation needs the agent's
// audio: the question TEXT is in the bubble the moment the turn opens, the
// mic still records, the composer still sends, extraction still reconciles
// and the confirm turn still commits. Losing the voice must cost the VOICE.
// So a clip failure silences the agent for the rest of the session — one
// latch, one honest line on screen — and the turn proceeds exactly as if the
// clip had finished playing.
describe("dialogueStreamReducer — a clip that cannot be spoken silences the agent (INT-261)", () => {
  it("a question whose clip fails still opens the mic, and latches the mute", () => {
    const before = initialDialogueStreamState(general);
    expect(before.voiceMuted).toBe(false);
    const after = runGeneral(before, { type: "speech_unavailable" });
    // Exactly where `speech_done` would have gone: the turn is not lost.
    expect(after.turn).toEqual({ phase: "listening", step: 0 });
    expect(after.voiceMuted).toBe(true);
  });

  it("a confirm clip that cannot be spoken still shows the confirm turn", () => {
    const before = state({
      turn: { phase: "speaking", step: 0, intent: "confirm", candidate: painCandidate },
      asked: ["complaint"],
    });
    const after = runCardio(before, { type: "speech_unavailable" });
    expect(after.turn).toEqual({ phase: "confirming", step: 0, candidate: painCandidate });
    expect(after.voiceMuted).toBe(true);
  });

  it("the silence carries ACROSS turns until a clip actually plays", () => {
    // INT-261 wrote this as "later turns never un-mute" and asserted that a
    // clip which PLAYED left the session muted. That is the INT-294 defect
    // stated as a requirement: the surviving half is that the silence is not
    // forgotten between turns, and the corrected half is that a clip the
    // patient actually heard ends it.
    let s = runGeneral(initialDialogueStreamState(general), { type: "speech_unavailable" });
    s = runGeneral(s, { type: "utterance", workId: 1 });
    expect(s.turn).toEqual({ phase: "speaking", step: 1, intent: "question" });
    expect(s.voiceMuted).toBe(true);
    s = runGeneral(s, { type: "speech_done" });
    expect(s.voiceMuted).toBe(false);
  });

  it("the whole conversation still completes with no agent audio at all", () => {
    // Every turn silent: ask → answer → suggestion → confirm, three questions.
    let s = initialDialogueStreamState(general); // complaint → duration → extra
    s = runGeneral(s, { type: "speech_unavailable" }); // complaint, silent
    s = runGeneral(s, { type: "typed", workId: 1, text: "göğsümde baskı var" });
    s = runGeneral(s, {
      type: "extract_settled",
      workId: 1,
      candidates: { complaint: painCandidate },
    });
    s = runGeneral(s, { type: "speech_unavailable" }); // duration, silent
    s = runGeneral(s, { type: "typed", workId: 2, text: "birkaç gündür" });
    // complaint's suggestion is owed a confirm turn, silent like the rest
    expect(s.turn).toEqual({
      phase: "speaking",
      step: 0,
      intent: "confirm",
      candidate: painCandidate,
    });
    s = runGeneral(s, { type: "speech_unavailable" });
    expect(s.turn).toEqual({ phase: "confirming", step: 0, candidate: painCandidate });
    s = runGeneral(s, { type: "confirm", values: ["pain"] });
    expect(s.answers.complaint).toEqual({ values: ["pain"], quote: "göğsümde baskı var" });
    // and it never became a failure along the way
    expect(s.turn.phase).not.toBe("failed");
    expect(s.voiceMuted).toBe(true);
  });

  it("a mute outside a speaking turn latches without disturbing the turn", () => {
    // The pre-warm and a late clip can both fail while the patient is talking.
    const listening = state({ turn: { phase: "listening", step: 0 } });
    const after = runGeneral(listening, { type: "speech_unavailable" });
    expect(after.turn).toBe(listening.turn);
    expect(after.voiceMuted).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// INT-294 — the mute is a condition, not a life sentence
// ---------------------------------------------------------------------------

// INT-261 made a clip failure silence the agent for the REST OF THE SESSION,
// and the reason it gave was a cost argument: "re-probing the TTS ladder on
// every subsequent turn would spend the turn budget twice per question to
// arrive at the same answer". That argument was true of an admission walk
// that cost the whole clip deadline (docs/evidence/INT-293.md measured 4024 ms
// of a 4048 ms budget) and it is not true of a bounded one. What is left is
// the cost the owner actually paid: one slow FIRST turn, and a whole visit in
// silence with a healthy Freya answering in 0.8 s the entire time.
//
// So the mute becomes what it always was — a report about the last clip, not
// a property of the session. Three actions, and the difference between them
// is the whole design:
//   speech_done        the clip PLAYED      → the voice is back, on the record
//   speech_unavailable the clip FAILED      → silent, and one turn further
//                                             from the next attempt
//   speech_skipped     it was NOT ATTEMPTED → silent, and one turn closer
// A turn that was never attempted is not evidence of anything, which is why
// it cannot clear the caption; a turn that was heard is evidence, and it can.
describe("dialogueStreamReducer — a muted session recovers (INT-294)", () => {
  it("one bad turn does not mute the visit: a later clip that plays clears it", () => {
    let s = runGeneral(initialDialogueStreamState(general), { type: "speech_unavailable" });
    expect(s.voiceMuted).toBe(true);
    s = runGeneral(s, { type: "utterance", workId: 1 });
    expect(s.turn).toEqual({ phase: "speaking", step: 1, intent: "question" });
    // One failure buys no cooldown: the very next turn tries again.
    expect(s.voiceRetryIn).toBe(0);
    s = runGeneral(s, { type: "speech_done" });
    expect(s.voiceMuted).toBe(false);
    expect(s.voiceFailures).toBe(0);
  });

  it("backs off one further turn for each consecutive failure", () => {
    let s = runGeneral(initialDialogueStreamState(general), { type: "speech_unavailable" });
    expect([s.voiceFailures, s.voiceRetryIn]).toEqual([1, 0]);
    s = runGeneral(s, { type: "utterance", workId: 1 });
    s = runGeneral(s, { type: "speech_unavailable" });
    expect([s.voiceFailures, s.voiceRetryIn]).toEqual([2, 1]);
    s = runGeneral(s, { type: "utterance", workId: 2 });
    s = runGeneral(s, { type: "speech_skipped" });
    expect([s.voiceMuted, s.voiceFailures, s.voiceRetryIn]).toEqual([true, 2, 0]);
  });

  it("a turn nobody attempted is not evidence the voice is back", () => {
    let s = runGeneral(initialDialogueStreamState(general), { type: "speech_unavailable" });
    s = runGeneral(s, { type: "utterance", workId: 1 });
    s = runGeneral(s, { type: "speech_skipped" });
    expect(s.voiceMuted).toBe(true);
  });

  it("does not flap inside a turn: nothing between two clips touches the caption", () => {
    let s = runGeneral(initialDialogueStreamState(general), { type: "speech_unavailable" });
    s = runGeneral(s, { type: "utterance", workId: 1 });
    expect(s.voiceMuted).toBe(true);
    s = runGeneral(s, { type: "transcript_ready", workId: 1, text: "göğsümde baskı var" });
    expect(s.voiceMuted).toBe(true);
    s = runGeneral(s, { type: "extract_settled", workId: 1, candidates: {} });
    expect(s.voiceMuted).toBe(true);
    s = runGeneral(s, { type: "barge_in" });
    expect(s.voiceMuted).toBe(true);
  });

  it("a skipped clip moves the turn exactly where a played one would", () => {
    const played = runGeneral(initialDialogueStreamState(general), { type: "speech_done" });
    const skipped = runGeneral(initialDialogueStreamState(general), { type: "speech_skipped" });
    expect(skipped.turn).toEqual(played.turn);
  });

  it("the confirm turn recovers too — it is the same clip path", () => {
    let s = state({
      turn: { phase: "speaking", step: 0, intent: "confirm", candidate: painCandidate },
      asked: ["complaint"],
      voiceMuted: true,
      voiceFailures: 1,
      voiceRetryIn: 0,
    });
    s = runCardio(s, { type: "speech_done" });
    expect(s.turn).toEqual({ phase: "confirming", step: 0, candidate: painCandidate });
    expect(s.voiceMuted).toBe(false);
  });

  it("the caption on screen is exactly this flag, so clearing it clears the caption", () => {
    // The reducer tests above are about a boolean; this is the line that
    // makes them about what the patient sees. DialogueIntake renders the
    // "sesli okuma su an calismiyor" caption under `state.voiceMuted` and
    // nothing else, so a recovered voice takes the caption with it.
    const screen = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), "..", "..", "components", "DialogueIntake.tsx"),
      "utf8",
    );
    expect(screen).toContain("{state.voiceMuted ? (");
    expect(screen).toContain('t("dialogue.voiceMuted")');
  });

  it("shouldAttemptSpeech: silent turns are skipped only while a cooldown is owed", () => {
    expect(shouldAttemptSpeech({ voiceMuted: false, voiceRetryIn: 0 })).toBe(true);
    expect(shouldAttemptSpeech({ voiceMuted: true, voiceRetryIn: 0 })).toBe(true);
    expect(shouldAttemptSpeech({ voiceMuted: true, voiceRetryIn: 1 })).toBe(false);
  });
});

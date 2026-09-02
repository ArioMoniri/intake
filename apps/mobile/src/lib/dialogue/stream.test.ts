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
import { describe, expect, it } from "vitest";

import {
  applicableQuestions,
  intakeQuestions,
  packForDepartment,
  type IntakeQuestion,
} from "../intake/questions";
import { sectionPanelModel } from "./sectionPanel";
import {
  answerWords,
  committedAnswers,
  dialogueStreamReducer,
  initialDialogueStreamState,
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
    utteranceOf: {},
    unclear: {},
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

  it("the mute is a session latch — later turns never un-mute", () => {
    let s = runGeneral(initialDialogueStreamState(general), { type: "speech_unavailable" });
    s = runGeneral(s, { type: "utterance", workId: 1 });
    expect(s.turn).toEqual({ phase: "speaking", step: 1, intent: "question" });
    expect(s.voiceMuted).toBe(true);
    s = runGeneral(s, { type: "speech_done" });
    expect(s.voiceMuted).toBe(true);
  });

  it("the whole conversation still completes with no agent audio at all", () => {
    // Every turn silent: ask → answer → suggestion → confirm, three questions.
    let s = initialDialogueStreamState(general); // complaint → duration → extra
    s = runGeneral(s, { type: "speech_unavailable" }); // complaint, silent
    s = runGeneral(s, { type: "typed", workId: 1, text: "göğsümde baskı var" });
    s = runGeneral(s, { type: "extract_settled", workId: 1, candidates: { complaint: painCandidate } });
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

// INT-293 — the answers given on the dialogue surface reach the note.
//
// The walkthrough (docs/evidence/INT-293.md) answered three consecutive
// questions through the composer. The conversation advanced correctly every
// time and the note never moved: "Not oluşuyor 0 / 10 bölüm" after three
// answers, every section still "Henüz yanıtlanmadı", and the hand-over to the
// typed steps started at "0 soru yanıtlandı".
//
// The issue names the first thing to establish, and these tests establish it
// by asserting on the INTERMEDIATE value — the candidate the utterance
// produces — rather than on the note at the end:
//
//   (a) the answer is extracted into a slot and the slot never reaches the
//       note composer — a wiring defect; or
//   (b) the answer is never extracted at all — the note is correctly
//       reporting that it has nothing.
//
// `the write path` below is the separator: it drives the same commit with a
// candidate that already exists, so whichever way it goes decides which world
// this is before a line of it is fixed.
describe("dialogueStreamReducer — an answer given here reaches the note (INT-293)", () => {
  /** The suggestion standing for one question: pending, or the live confirm
   * turn that has already consumed it. */
  function suggestionFor(
    pack: readonly IntakeQuestion[],
    s: DialogueStreamState,
    questionId: string,
  ): DialogueCandidate | null {
    const { turn } = s;
    if (
      (turn.phase === "confirming" || (turn.phase === "speaking" && turn.intent === "confirm")) &&
      pack[turn.step]?.id === questionId
    ) {
      return turn.candidate;
    }
    return s.pending[questionId] ?? null;
  }

  /** One whole answered turn, exactly as the surface drives it: the patient
   * types, the agent reads the suggestion back, the patient confirms. */
  function answerByTyping(
    pack: readonly IntakeQuestion[],
    s: DialogueStreamState,
    workId: number,
    text: string,
  ): DialogueStreamState {
    let next = dialogueStreamReducer(pack, s, { type: "typed", workId, text });
    const candidate = suggestionFor(pack, next, currentId(pack, next) ?? "");
    if (candidate === null) {
      return next; // nothing to confirm — the caller asserts on that
    }
    next = dialogueStreamReducer(pack, next, { type: "speech_done" });
    return dialogueStreamReducer(pack, next, { type: "confirm", values: candidate.values });
  }

  function currentId(
    pack: readonly IntakeQuestion[],
    s: DialogueStreamState,
  ): string | undefined {
    return "step" in s.turn ? pack[s.turn.step]?.id : undefined;
  }

  const askingDuration = () =>
    state({
      turn: { phase: "listening", step: 1 },
      asked: ["complaint"],
      answers: { complaint: { values: ["pain"], quote: "agrim var" } },
      stream: [
        { kind: "agent_question", questionId: "complaint" },
        { kind: "agent_question", questionId: "duration" },
      ],
    });

  it("the reproduction: 'Bugun basladi' typed on the duration turn fills the slot", () => {
    // Diacritic-free Turkish is what the walkthrough could type, and what
    // people actually type. The assertion is on the SLOT, not on the note.
    const after = runGeneral(askingDuration(), {
      type: "typed",
      workId: 2,
      text: "Bugun basladi",
    });
    expect(suggestionFor(general, after, "duration")).toEqual({
      values: ["today"],
      quote: "Bugun basladi",
    });
  });

  it("the same answer fully diacritised fills the same slot", () => {
    const after = runGeneral(askingDuration(), {
      type: "typed",
      workId: 2,
      text: "Bugün başladı",
    });
    expect(suggestionFor(general, after, "duration")).toEqual({
      values: ["today"],
      quote: "Bugün başladı",
    });
  });

  it("the write path: a candidate that exists does reach the answers", () => {
    // The hypothesis separator. This one drives the commit from a candidate
    // handed in from outside, so it says whether the note-ward half of the
    // path works at all, independently of anything that produces candidates.
    let s = state({
      turn: { phase: "listening", step: 1 },
      asked: ["complaint"],
      answers: { complaint: { values: ["pain"], quote: "" } },
    });
    s = runGeneral(s, { type: "utterance", workId: 2 });
    s = runGeneral(s, {
      type: "extract_settled",
      workId: 2,
      candidates: { duration: { values: ["today"], quote: "bugün başladı" } },
    });
    expect(s.pending.duration).toEqual({ values: ["today"], quote: "bugün başladı" });
    // the landed suggestion gets its confirm turn on the next advance
    s = runGeneral(s, { type: "speech_done" });
    s = runGeneral(s, { type: "utterance", workId: 3 });
    expect(s.turn).toEqual({
      phase: "speaking",
      step: 1,
      intent: "confirm",
      candidate: { values: ["today"], quote: "bugün başladı" },
    });
    s = runGeneral(s, { type: "speech_done" });
    s = runGeneral(s, { type: "confirm", values: ["today"] });
    expect(s.answers.duration).toEqual({ values: ["today"], quote: "bugün başladı" });
  });

  it("words nothing can map are never swallowed: the question comes back", () => {
    // Ask-ahead speaks the next question while the pipeline runs (INT-235),
    // so the honest place to assert is once that utterance's fate is known:
    // the conversation has not moved PAST the question, and the patient is
    // told why it is being asked again.
    let s = state({
      turn: { phase: "listening", step: 0 },
      stream: [{ kind: "agent_question", questionId: "complaint" }],
    });
    s = runGeneral(s, { type: "typed", workId: 1, text: "pek bilmiyorum ki" });
    s = runGeneral(s, { type: "extract_settled", workId: 1, candidates: {} });
    expect(s.answers.complaint).toBeUndefined();
    expect(s.asked).not.toContain("complaint"); // not left behind as asked-and-done
    // and the very next advance asks it again, with the honest line first
    s = runGeneral(s, { type: "speech_done" });
    s = runGeneral(s, { type: "typed", workId: 2, text: "bugün başladı" });
    expect(currentId(general, s)).toBe("complaint");
    expect(s.stream.at(-2)).toEqual({ kind: "agent_unclear", questionId: "complaint" });
    expect(s.stream.at(-1)).toEqual({ kind: "agent_question", questionId: "complaint" });
  });

  it("a question the agent could not understand twice is not asked a third time", () => {
    let s = state({
      turn: { phase: "listening", step: 0 },
      stream: [{ kind: "agent_question", questionId: "complaint" }],
    });
    s = runGeneral(s, { type: "typed", workId: 1, text: "pek bilmiyorum ki" });
    s = runGeneral(s, { type: "extract_settled", workId: 1, candidates: {} });
    s = runGeneral(s, { type: "speech_done" });
    s = runGeneral(s, { type: "typed", workId: 2, text: "Bugun basladi" }); // duration lands
    expect(currentId(general, s)).toBe("complaint"); // and complaint is re-asked
    s = runGeneral(s, { type: "speech_done" });
    s = runGeneral(s, { type: "typed", workId: 3, text: "yine anlatamıyorum" });
    s = runGeneral(s, { type: "extract_settled", workId: 3, candidates: {} });
    expect(s.unclear.complaint).toBe(2);
    expect(s.asked).toContain("complaint"); // the second miss ends the loop
  });

  it("the dialogue never ENDS past a question it could not understand", () => {
    // The literal form of "does not advance the question index": with every
    // question asked and the last pipeline settling, an unmapped answer does
    // not resolve to handoff — the conversation comes back and asks it.
    let s = state({
      turn: { phase: "settling" },
      asked: ["complaint", "duration", "extra"],
      answers: {
        duration: { values: ["today"], quote: "bugün başladı" },
        extra: { values: [], quote: "" },
      },
      utteranceOf: { 7: "complaint" },
      inflight: [7],
    });
    s = runGeneral(s, { type: "extract_settled", workId: 7, candidates: {} });
    expect(s.turn).toEqual({ phase: "speaking", step: 0, intent: "question" });
    expect(s.stream.at(-2)).toEqual({ kind: "agent_unclear", questionId: "complaint" });
  });

  // ---- the negation guard, at the surface ---------------------------------
  //
  // The matcher's own refusals are pinned in `intake/answerMatch.test.ts`;
  // these two say what the refusal COSTS and what it buys, at the only place
  // the cost is visible. `DialogueIntake` pre-ticks a pending candidate and
  // commits it in one tap, so a candidate that reaches `pending` is one tap
  // from the clinician's note.

  it("a denied symptom never becomes a pending suggestion", () => {
    // "I have no fever" — one tap from writing FEVER into the note.
    let s = state({
      turn: { phase: "listening", step: 0 },
      stream: [{ kind: "agent_question", questionId: "complaint" }],
    });
    s = runGeneral(s, { type: "typed", workId: 1, text: "Ateş yok" });
    expect(suggestionFor(general, s, "complaint")).toBeNull();
    expect(s.answers.complaint).toBeUndefined();
    // and the question is not left behind: the extractor still has the words,
    // and an utterance neither could place comes back to be asked again.
    s = runGeneral(s, { type: "extract_settled", workId: 1, candidates: {} });
    expect(s.asked).not.toContain("complaint");
  });

  it("the extractor is not locked out of the utterance the local read already saw", () => {
    // The spoken path: the transcript lands its local read on the question it
    // answered without moving the live turn, so `extract_settled` for the
    // SAME work id is the extractor's verdict on the SAME sentence. It has to
    // be able to correct the local reading — that is what makes refusing
    // cheap and a wrong match expensive.
    let s = state({
      turn: { phase: "listening", step: 0 },
      stream: [{ kind: "agent_question", questionId: "complaint" }],
    });
    s = runGeneral(s, { type: "utterance", workId: 1 });
    s = runGeneral(s, { type: "transcript_ready", workId: 1, text: "Ateş var" });
    expect(s.pending.complaint).toEqual({ values: ["fever"], quote: "Ateş var" });
    s = runGeneral(s, {
      type: "extract_settled",
      workId: 1,
      candidates: { complaint: { values: ["fever", "cough"], quote: "Ateş var, öksürük de" } },
    });
    expect(s.pending.complaint).toEqual({
      values: ["fever", "cough"],
      quote: "Ateş var, öksürük de",
    });
  });

  it("the note counter is truthful: three answered turns are three filled sections", () => {
    let s = initialDialogueStreamState(cardio);
    s = runCardio(s, { type: "speech_done" });
    s = answerByTyping(cardio, s, 1, "Ağrı var");
    s = answerByTyping(cardio, s, 2, "Bugun basladi");
    s = answerByTyping(cardio, s, 3, "Sabah");
    expect(Object.keys(s.answers).sort()).toEqual(["complaint", "duration", "onset_today_when"]);
    const model = sectionPanelModel(cardio, s, []);
    expect(model.filled).toBe(3);
    expect(model.rows.filter((row) => row.status === "answered").map((row) => row.questionId)).
      toEqual(["complaint", "duration", "onset_today_when"]);
  });

  it("the gates fire here exactly as they do in the typed steps", () => {
    // duration = today opens `onset_today_when` and closes `duration_course`;
    // duration = month does the opposite. Same pack, same predicate, both
    // surfaces — the dialogue's asked-set against applicableQuestions.
    const walk = (durationWords: string) => {
      let s = initialDialogueStreamState(cardio);
      s = runCardio(s, { type: "speech_done" });
      s = answerByTyping(cardio, s, 1, "Ağrı var");
      s = answerByTyping(cardio, s, 2, durationWords);
      return s;
    };
    const today = walk("Bugun basladi");
    const month = walk("Bir aydan uzun süredir");
    expect(currentId(cardio, today)).toBe("onset_today_when");
    expect(currentId(cardio, month)).toBe("duration_course");
    for (const s of [today, month]) {
      const typedLane = applicableQuestions(cardio, committedAnswers(s)).map((q) => q.id);
      expect(typedLane).toContain(currentId(cardio, s));
      // the closed branch is absent from BOTH surfaces
      const closed = s === today ? "duration_course" : "onset_today_when";
      expect(typedLane).not.toContain(closed);
    }
  });

  it("the hand-over lands on the next question, not back at zero", () => {
    let s = initialDialogueStreamState(cardio);
    s = runCardio(s, { type: "speech_done" });
    s = answerByTyping(cardio, s, 1, "Ağrı var");
    s = answerByTyping(cardio, s, 2, "Bugun basladi");
    // What the screen commits per confirm, in the note's own shape.
    const noteAnswers = Object.entries(s.answers).map(([questionId, answer]) => ({
      questionId,
      values: answer.values,
      words: answerWords(
        cardio.find((q) => q.id === questionId)!,
        answer.quote,
      ),
    }));
    const applicable = applicableQuestions(cardio, noteAnswers);
    const answeredIds = new Set(noteAnswers.map((a) => a.questionId));
    expect(applicable.filter((q) => answeredIds.has(q.id)).length).toBe(2);
    expect(applicable.find((q) => !answeredIds.has(q.id))?.id).toBe("onset_today_when");
  });
});

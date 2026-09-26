/**
 * Typed intake flow, end to end, as DATA (INT — intake flow fix).
 *
 * The typed controller (app/(tabs)/visits/[visitId]/intake.tsx `StepFlow`)
 * does exactly three things per answer, and every one of them is a pure
 * function this file drives directly, with no renderer:
 *
 *   commit   → `noteReducer(state, { type: "answer", … })` appends the answer
 *   count    → `intakeProgress(pack, note.answers).answered` is what the
 *              "n soru yanıtlandı" row prints
 *   advance  → `nextApplicableQuestion(pack, nextAnswers, id)` is the next
 *              step, and `resumeQuestion(pack, answers)` is where a remount
 *              (or the voice→typed hand-off) lands
 *
 * The owner reported the counter stuck at 0 and questions repeating. Both are
 * claims about these three functions composed the way the screen composes
 * them, so they are pinned here: the count tracks the commits, the flow never
 * offers a question it already has an answer for, and a hand-off that carries
 * committed answers resumes at the first UNanswered step — not from zero.
 */
import { describe, expect, it } from "vitest";

import { emptyNoteState, noteReducer, type NoteState } from "./note";
import {
  intakeProgress,
  nextApplicableQuestion,
  packForVisit,
  resumeQuestion,
  type IntakeQuestion,
} from "./questions";

/** A value the given step would accept, exactly as the screen commits one:
 * the first option for a chip/card, a sentence for a free-text step, a
 * number string for a measure. The screen never resolves free text to a
 * value (chips are the answer), so text/measure carry a literal here. */
function sampleValues(question: IntakeQuestion): string[] {
  switch (question.kind) {
    case "chips":
    case "single":
      return [question.options[0].id];
    case "measure":
      return ["1"];
    case "text":
      return ["deneme"];
  }
}

/** One tap on "Devam edin" / a card: append the answer through the SAME
 * reducer the session provider runs, and return the new note state. */
function commit(state: NoteState, question: IntakeQuestion, values: string[]): NoteState {
  return noteReducer(state, { type: "answer", questionId: question.id, values });
}

const PACKS: { name: string; department: string | undefined }[] = [
  { name: "general", department: undefined },
  { name: "kardiyoloji", department: "kardiyoloji" },
  { name: "dahiliye", department: "dahiliye" },
];

describe("typed intake flow — commit, count, advance", () => {
  for (const { name, department } of PACKS) {
    const pack = packForVisit(department, { mode: "hizli" });

    it(`${name}: the counter tracks the commits and never repeats an answered step`, () => {
      let state = emptyNoteState();

      // Where the screen opens (fresh run, no request): the first applicable
      // question. resumeQuestion returning null would mean nothing to ask.
      const start = resumeQuestion(pack, state.answers);
      expect(start).not.toBeNull();

      const asked: string[] = [];
      let current: IntakeQuestion | null = start;
      // Bounded by the pack: a loop that revisits a step would blow past it.
      const guard = pack.length + 5;
      for (let step = 0; current !== null && step < guard; step += 1) {
        // The flow must never hand back a question already answered.
        expect(asked).not.toContain(current.id);
        asked.push(current.id);

        state = commit(state, current, sampleValues(current));

        // The row the patient reads: it is exactly the number of commits.
        expect(intakeProgress(pack, state.answers).answered).toBe(asked.length);

        // Advance against the answers INCLUDING this commit (the screen's rule).
        current = nextApplicableQuestion(pack, state.answers, current.id);
      }

      // The walk terminated at the end of the flow, not by hitting the guard.
      expect(current).toBeNull();
      // Every answered applicable question is counted — the honest denominator.
      const progress = intakeProgress(pack, state.answers);
      expect(progress.answered).toBe(asked.length);
      expect(progress.answered).toBe(
        progress.applicable.filter((q) => asked.includes(q.id)).length,
      );
      // No id was asked twice.
      expect(new Set(asked).size).toBe(asked.length);
    });
  }
});

describe("typed intake flow — adaptive gates", () => {
  // The kardiyoloji pack carries the duration→onset_today_when gate.
  const pack = packForVisit("kardiyoloji", { mode: "hizli" });

  it("an answer that opens a gate lengthens the flow and the new step is asked next", () => {
    let state = emptyNoteState();
    state = commit(
      state,
      pack.find((q) => q.id === "complaint")!,
      ["pain"],
    );
    // duration=today opens onset_today_when (questions.ts askIf).
    const beforeGate = intakeProgress(pack, state.answers).applicable.map((q) => q.id);
    expect(beforeGate).not.toContain("onset_today_when");

    state = commit(
      state,
      pack.find((q) => q.id === "duration")!,
      ["today"],
    );
    const afterGate = intakeProgress(pack, state.answers).applicable.map((q) => q.id);
    expect(afterGate).toContain("onset_today_when");
    // The gated step is what the flow offers right after its gating answer.
    expect(nextApplicableQuestion(pack, state.answers, "duration")?.id).toBe("onset_today_when");
  });

  it("re-answering to CLOSE a gate drops the step from the flow but keeps the committed answer", () => {
    let state = emptyNoteState();
    state = commit(
      state,
      pack.find((q) => q.id === "complaint")!,
      ["pain"],
    );
    state = commit(
      state,
      pack.find((q) => q.id === "duration")!,
      ["today"],
    );
    state = commit(
      state,
      pack.find((q) => q.id === "onset_today_when")!,
      ["morning"],
    );
    expect(intakeProgress(pack, state.answers).applicable.map((q) => q.id)).toContain(
      "onset_today_when",
    );

    // Change the gating answer: the gate closes.
    state = commit(
      state,
      pack.find((q) => q.id === "duration")!,
      ["month"],
    );
    expect(intakeProgress(pack, state.answers).applicable.map((q) => q.id)).not.toContain(
      "onset_today_when",
    );
    // …but the patient's committed onset answer is NOT silently discarded —
    // the note keeps it (buildNote marks it "koşul değişti").
    expect(state.answers.find((a) => a.questionId === "onset_today_when")?.values).toEqual([
      "morning",
    ]);
  });
});

describe("voice→typed hand-off preserves answers", () => {
  const pack = packForVisit(undefined, { mode: "hizli" });

  it("resumes at the first UNanswered step with the count reflecting what voice committed", () => {
    // The dialogue commits confirmed answers through the very same reducer
    // (DialogueIntake.confirmTurn → updateNote(type:"answer")), so a hand-off
    // is just a note that already carries some answers.
    let state = emptyNoteState();
    state = commit(
      state,
      pack.find((q) => q.id === "complaint")!,
      ["pain"],
    );
    state = commit(
      state,
      pack.find((q) => q.id === "duration")!,
      ["week"],
    );

    const progress = intakeProgress(pack, state.answers);
    // Not from zero.
    expect(progress.answered).toBe(2);

    const resume = resumeQuestion(pack, state.answers);
    expect(resume).not.toBeNull();
    // Not a question already answered (no repeat), and not the first step.
    const answeredIds = new Set(state.answers.map((a) => a.questionId));
    expect(answeredIds.has(resume!.id)).toBe(false);
    expect(resume!.id).not.toBe("complaint");
    // Exactly the first applicable step with no answer.
    const firstUnanswered = progress.applicable.find((q) => !answeredIds.has(q.id));
    expect(resume!.id).toBe(firstUnanswered!.id);
  });

  it("an empty hand-off (dead mic, nothing captured) degrades to the first step at zero, not a repeat", () => {
    // No answers were captured (the sim mic recorded silence): the typed lane
    // must open at the very first applicable question with the counter at 0.
    const state = emptyNoteState();
    const progress = intakeProgress(pack, state.answers);
    expect(progress.answered).toBe(0);
    const resume = resumeQuestion(pack, state.answers);
    expect(resume?.id).toBe(progress.applicable[0].id);
  });
});

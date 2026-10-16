/**
 * INT-497 runtime review — when the turn may end ITSELF, and how long it waits.
 *
 * An automatic end stops the recorder, and the microphone reopens only when
 * the next turn starts speaking (useDialogueSession). A turn whose taking
 * leads to no spoken turn — the last question, or a dialogue about to settle
 * — has no next turn to reopen it, so a word said after an automatic end
 * there would be said into a closed microphone. Those listens end on the tap
 * only. The reducer is pure, so the decision asks it rather than guessing.
 */
import { describe, expect, it } from "vitest";

import { intakeQuestions, type IntakeQuestion } from "../intake/questions";
import { answerShapeOf, autoEndAllowed } from "./autoEnd";
import {
  dialogueStreamReducer,
  initialDialogueStreamState,
  type DialogueStreamAction,
} from "./stream";

const general = intakeQuestions; // complaint → duration → extra

function run(pack: readonly IntakeQuestion[], ...actions: DialogueStreamAction[]) {
  return actions.reduce(
    (state, action) => dialogueStreamReducer(pack, state, action),
    initialDialogueStreamState(pack),
  );
}

describe("autoEndAllowed — only a listen whose taking leads to a spoken turn", () => {
  it("allows the first question of a pack with more to ask", () => {
    const listening = run(general, { type: "speech_done" });
    expect(listening.turn.phase).toBe("listening");
    expect(autoEndAllowed(general, listening)).toBe(true);
  });

  it("refuses the last question: nothing would reopen the microphone after it", () => {
    const last = run(
      general,
      { type: "speech_done" },
      { type: "utterance", workId: 1 },
      { type: "speech_done" },
      { type: "utterance", workId: 2 },
      { type: "speech_done" },
    );
    expect(last.turn).toEqual({ phase: "listening", step: general.length - 1 });
    expect(autoEndAllowed(general, last)).toBe(false);
  });

  it("refuses the last question even when a suggestion's confirm turn comes first", () => {
    // Re-check of the runtime review: complaint → duration → extra, with the
    // duration suggestion landing while the patient answers `extra`. The
    // taking opens a CONFIRM turn, and after its confirm the dialogue settles
    // — no question turn follows to keep the microphone's recording in use.
    const last = run(
      general,
      { type: "speech_done" },
      { type: "utterance", workId: 1 },
      { type: "speech_done" },
      { type: "utterance", workId: 2 },
      { type: "speech_done" },
      {
        type: "extract_settled",
        workId: 2,
        candidates: { duration: { values: ["days"], quote: "birkaç gündür" } },
      },
    );
    expect(last.turn).toEqual({ phase: "listening", step: general.length - 1 });
    expect(last.pending.duration).toBeDefined();
    expect(autoEndAllowed(general, last)).toBe(false);
  });

  it("allows a mid-flow listen whose confirm turn is followed by an unasked question", () => {
    const listening = run(general, { type: "speech_done" });
    const withSuggestion = {
      ...listening,
      pending: { complaint: { values: ["pain"], quote: "başım ağrıyor" } },
    };
    expect(autoEndAllowed(general, withSuggestion)).toBe(true);
  });

  it("refuses the only question of a one-question pack", () => {
    const one = [general[0]];
    expect(autoEndAllowed(one, run(one, { type: "speech_done" }))).toBe(false);
  });

  it("refuses anything that is not an open listen", () => {
    expect(autoEndAllowed(general, initialDialogueStreamState(general))).toBe(false);
  });

  it("asks the reducer and never changes the state it was handed", () => {
    const listening = run(general, { type: "speech_done" });
    const before = JSON.stringify(listening);
    autoEndAllowed(general, listening);
    expect(JSON.stringify(listening)).toBe(before);
  });
});

describe("answerShapeOf — what the question invites", () => {
  it("a question with an answer space invites a short answer", () => {
    const options = general.find((question) => question.kind !== "text")!;
    expect(answerShapeOf(options)).toBe("short");
  });

  it("a free-text question invites a narrative", () => {
    const text = general.find((question) => question.kind === "text")!;
    expect(answerShapeOf(text)).toBe("narrative");
  });

  it("a RED-adjacent step gets the long wait too — its answer is the one not to clip", () => {
    const options = general.find((question) => question.kind !== "text")!;
    expect(answerShapeOf({ ...options, redAdjacent: true } as IntakeQuestion)).toBe("narrative");
  });

  it("an unknown step gets the long wait, never the short one", () => {
    expect(answerShapeOf(undefined)).toBe("narrative");
  });
});

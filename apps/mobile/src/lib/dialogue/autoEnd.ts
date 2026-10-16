/**
 * When the turn may end itself, and how long it waits (INT-497, runtime
 * review).
 *
 * An automatic end stops the recorder, and the microphone reopens when the
 * NEXT turn starts speaking (useDialogueSession's speaking driver opens it
 * before anything else). So an automatic end is only safe where a QUESTION
 * turn follows — through any confirm turns in between — because only a
 * question turn leads to a listen that records what the patient adds. A
 * confirm turn alone is not enough: after its confirm the dialogue can settle,
 * finish or hand over, and words said meanwhile are never transcribed. After
 * the last question, or wherever the dialogue would settle, the tap ends the
 * turn. What remains is the native stop → record gap at the reopen, measured
 * on a device after deploy (docs/evidence/INT-497.md).
 *
 * The reducer is pure, so `autoEndAllowed` asks it what the taking would do —
 * walking each confirm turn on its suggested values — rather than re-deriving
 * the walk; the state it is handed is never changed.
 */
import type { IntakeQuestion } from "../intake/questions";
import type { AnswerShape } from "./endpointer";
import { dialogueStreamReducer, type DialogueStreamState } from "./stream";

/** A work id no live utterance carries — the prediction's own, never dispatched. */
const PREDICTION_WORK_ID = Number.MAX_SAFE_INTEGER;

/** Whether taking the open listen now leads, through any confirm turns, to a
 * question turn. */
export function autoEndAllowed(
  pack: readonly IntakeQuestion[],
  state: DialogueStreamState,
): boolean {
  if (state.turn.phase !== "listening") {
    return false;
  }
  let next = dialogueStreamReducer(pack, state, {
    type: "utterance",
    workId: PREDICTION_WORK_ID,
  });
  // Each confirm commits one answer, so the walk ends within the pack's
  // length; the bound is a guard against a reducer change, never the exit.
  for (let step = 0; step <= pack.length; step += 1) {
    if (next.turn.phase !== "speaking" || next.turn.intent !== "confirm") {
      break;
    }
    const values = [...next.turn.candidate.values];
    next = dialogueStreamReducer(pack, dialogueStreamReducer(pack, next, { type: "speech_done" }), {
      type: "confirm",
      values,
    });
  }
  return next.turn.phase === "speaking" && next.turn.intent === "question";
}

/**
 * What the question invites (endpointer.ts AnswerShape). A free-text question
 * invites a narrative. A RED-adjacent step gets the long wait too: its answer
 * is the one most worth not clipping. A step the hook cannot name gets the
 * long wait, never the short one.
 */
export function answerShapeOf(question: IntakeQuestion | undefined): AnswerShape {
  if (question === undefined || question.kind === "text" || question.redAdjacent === true) {
    return "narrative";
  }
  return "short";
}

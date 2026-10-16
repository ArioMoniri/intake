/**
 * When the turn may end itself, and how long it waits (INT-497, runtime
 * review).
 *
 * An automatic end stops the recorder, and the microphone reopens when the
 * NEXT turn starts speaking (useDialogueSession's speaking driver opens it
 * before anything else). So an automatic end is only safe where taking the
 * turn leads to a spoken turn. After the last question, or when the dialogue
 * would settle, nothing reopens the microphone, and a word the patient adds
 * after a pause would land in a closed one. Those listens end on the tap only.
 *
 * The reducer is pure, so `autoEndAllowed` asks it what the taking would do
 * rather than re-deriving the walk; the state it is handed is never changed.
 */
import type { IntakeQuestion } from "../intake/questions";
import type { AnswerShape } from "./endpointer";
import { dialogueStreamReducer, type DialogueStreamState } from "./stream";

/** A work id no live utterance carries — the prediction's own, never dispatched. */
const PREDICTION_WORK_ID = Number.MAX_SAFE_INTEGER;

/** Whether taking the open listen now leads straight to a spoken turn. */
export function autoEndAllowed(
  pack: readonly IntakeQuestion[],
  state: DialogueStreamState,
): boolean {
  if (state.turn.phase !== "listening") {
    return false;
  }
  const next = dialogueStreamReducer(pack, state, {
    type: "utterance",
    workId: PREDICTION_WORK_ID,
  });
  return next.turn.phase === "speaking";
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

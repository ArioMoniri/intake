/**
 * Spoken dialogue mode (INT-233): the pure turn engine over a department
 * pack. One step at a time the agent SPEAKS the question (catalog tr text
 * only — see speech.ts), LISTENS, transcribes, extracts against that single
 * question, then speaks a short confirmation with the candidate
 * pre-selected; the patient taps to confirm or speaks the correction.
 *
 * DEV-TIER honesty: this is the honest in-app dev dialogue over the HTTP
 * bridges (whisper/FreyaTTS/extract). The production voice path is the
 * LiveKit Talker with its six-tool boundary (invariant 9, files/03 §4.9,
 * files/13 Part II) — this module never grows tools, triage or LLM speech.
 *
 * Posture carried from INT-199 (invariants 1/2/10/22):
 * - Candidates are ANSWER SUGGESTIONS the patient confirms — never triage,
 *   never a diagnosis.
 * - Agent speech is composed from catalog tr strings only; patient words
 *   are displayed, never synthesized.
 * - DISTURBABLE: a barge-in during agent speech opens the mic immediately.
 * - Typed fallback exists on every turn for that step only; a hard service
 *   failure is terminal here and the component lands the patient in the
 *   existing manual steps with every committed answer intact.
 */
import type { IntakeQuestion } from "../intake/questions";

export interface DialogueCandidate {
  values: string[];
  /** The patient's verbatim words behind the suggestion (display only). */
  quote: string;
}

export type DialogueState =
  | { phase: "speaking"; step: number; intent: "question" }
  | { phase: "speaking"; step: number; intent: "confirm"; candidate: DialogueCandidate }
  | { phase: "listening"; step: number }
  | { phase: "transcribing"; step: number }
  | { phase: "extracting"; step: number }
  | { phase: "confirming"; step: number; candidate: DialogueCandidate }
  | { phase: "typing"; step: number; prefill: DialogueCandidate | null }
  | { phase: "done" }
  | { phase: "failed" };

export type DialogueAction =
  | { type: "speech_done" }
  /** Tap on the speech surface while the agent speaks — barge-in (02 §5). */
  | { type: "barge_in" }
  /** "Bitirdim" or tap-to-stop while listening. */
  | { type: "stop" }
  | { type: "transcript"; text: string }
  | { type: "candidate"; candidate: DialogueCandidate }
  | { type: "no_candidate" }
  /** Patient taps confirm on the pre-selected candidate. */
  | { type: "confirm" }
  /** Patient chooses to speak the correction from the confirm card. */
  | { type: "speak" }
  /** "Yazarak yanıtlayın" — typed fallback for THIS step only. */
  | { type: "type" }
  /** Typed answer committed — advance the dialogue. */
  | { type: "commit" }
  /** Hard service failure (TTS/ASR/extract) — terminal, falls to manual. */
  | { type: "failure" };

export function initialDialogueState(): DialogueState {
  return { phase: "speaking", step: 0, intent: "question" };
}

function advance(pack: readonly IntakeQuestion[], step: number): DialogueState {
  return step + 1 < pack.length
    ? { phase: "speaking", step: step + 1, intent: "question" }
    : { phase: "done" };
}

export function dialogueReducer(
  pack: readonly IntakeQuestion[],
  state: DialogueState,
  action: DialogueAction,
): DialogueState {
  // Terminal states absorb everything: late async results never resurrect
  // a finished or failed dialogue (same posture as voiceFirst's steps).
  if (state.phase === "done" || state.phase === "failed") {
    return state;
  }
  // A patient who is already typing this step is never ejected by a late
  // async failure or a stale voice result — typing only commits or stays.
  if (state.phase === "typing") {
    return action.type === "commit" ? advance(pack, state.step) : state;
  }
  switch (action.type) {
    case "speech_done":
      if (state.phase !== "speaking") {
        return state;
      }
      return state.intent === "question"
        ? { phase: "listening", step: state.step }
        : { phase: "confirming", step: state.step, candidate: state.candidate };
    case "barge_in":
      // DISTURBABLE: only agent speech can be interrupted; interrupting the
      // confirm clip means "let me say the correction" — candidate dropped.
      return state.phase === "speaking" ? { phase: "listening", step: state.step } : state;
    case "stop":
      return state.phase === "listening" ? { phase: "transcribing", step: state.step } : state;
    case "transcript": {
      if (state.phase !== "transcribing") {
        return state;
      }
      const text = action.text.trim();
      if (text.length === 0) {
        // Nothing usable was heard: this one step falls to typing; the
        // dialogue continues at the next step after the patient commits.
        return { phase: "typing", step: state.step, prefill: null };
      }
      const question = pack[state.step];
      if (question.kind === "text") {
        // Free-text step: the transcribed words ARE the answer — no extract
        // hop. The confirm speech for a text step is the generic catalog
        // line; the value is displayed on screen, never synthesized.
        return {
          phase: "speaking",
          step: state.step,
          intent: "confirm",
          candidate: { values: [text], quote: text },
        };
      }
      return { phase: "extracting", step: state.step };
    }
    case "candidate":
      return state.phase === "extracting"
        ? { phase: "speaking", step: state.step, intent: "confirm", candidate: action.candidate }
        : state;
    case "no_candidate":
      return state.phase === "extracting"
        ? { phase: "typing", step: state.step, prefill: null }
        : state;
    case "confirm":
      return state.phase === "confirming" ? advance(pack, state.step) : state;
    case "speak":
      return state.phase === "confirming" ? { phase: "listening", step: state.step } : state;
    case "type":
      // Typed fallback for this step only; a confirm context keeps the
      // candidate pre-selected so the tap work is not thrown away.
      if (state.phase === "confirming") {
        return { phase: "typing", step: state.step, prefill: state.candidate };
      }
      return {
        phase: "typing",
        step: state.step,
        prefill: state.phase === "speaking" && state.intent === "confirm" ? state.candidate : null,
      };
    case "commit":
      return state; // commit is only meaningful from typing (handled above)
    case "failure":
      return { phase: "failed" };
  }
}

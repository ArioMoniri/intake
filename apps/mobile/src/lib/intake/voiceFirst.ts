/**
 * Voice-first intake entry (INT-199): a pure state machine for the flow
 * (ASR gate → offer → record → transcribe → extract → prefilled confirm
 * steps), the transcript→prefill mapping for a pack, and the per-question
 * confirm/change/skip resolution.
 *
 * Invariant posture: candidates are ANSWER SUGGESTIONS the patient confirms
 * one question at a time — never triage, never a diagnosis (invariant 1);
 * every failure or skip lands in the exact manual flow, never a dead end;
 * the quote is the patient's verbatim words, rendered as provenance only.
 */
import type { ExtractCandidate } from "../extract";
import { askIfMet, type AnsweredValues, type IntakeQuestion } from "./questions";

export interface Prefill {
  values: string[];
  /** The patient's verbatim words behind the suggestion. */
  quote: string;
}

export type PrefillMap = Record<string, Prefill>;

export type VoiceIntakeState =
  | { phase: "gate" }
  | { phase: "offer" }
  | { phase: "recording" }
  | { phase: "transcribing" }
  | { phase: "extracting" }
  /** Spoken dialogue mode (INT-233): the turn engine in lib/dialogue owns
   * the per-step flow; this machine only holds the door. `failure` from
   * here lands in the manual steps WITH the notice, `skip` quietly —
   * answers are committed per step, so nothing is lost either way. */
  | { phase: "dialogue" }
  | { phase: "steps"; prefill: PrefillMap; failed: boolean };

export type VoiceIntakeAction =
  | { type: "voice_ready" }
  | { type: "voice_unavailable" }
  | { type: "record" }
  | { type: "stop" }
  | { type: "transcript" }
  | { type: "candidates"; prefill: PrefillMap }
  /** The offer's second primary path: turn-by-turn spoken dialogue. */
  | { type: "dialogue" }
  | { type: "failure" }
  | { type: "skip" };

export function initialVoiceIntakeState(voiceEligible: boolean): VoiceIntakeState {
  return voiceEligible ? { phase: "gate" } : { phase: "steps", prefill: {}, failed: false };
}

const MANUAL: VoiceIntakeState = { phase: "steps", prefill: {}, failed: false };

export function voiceIntakeReducer(
  state: VoiceIntakeState,
  action: VoiceIntakeAction,
): VoiceIntakeState {
  // steps is absorbing: late async results never yank the patient out
  if (state.phase === "steps") {
    return state;
  }
  switch (action.type) {
    case "voice_ready":
      return state.phase === "gate" ? { phase: "offer" } : state;
    case "voice_unavailable":
      return state.phase === "gate" ? MANUAL : state;
    case "record":
      return state.phase === "offer" ? { phase: "recording" } : state;
    case "dialogue":
      return state.phase === "offer" ? { phase: "dialogue" } : state;
    case "stop":
      return state.phase === "recording" ? { phase: "transcribing" } : state;
    case "transcript":
      return state.phase === "transcribing" ? { phase: "extracting" } : state;
    case "candidates":
      if (state.phase !== "extracting") {
        return state;
      }
      // An extract that yielded NO usable suggestion is a FAILED voice
      // attempt: the daemon's restart window answers a valid envelope with
      // zero candidates while its /health stays 200, and landing that
      // silently in manual hid the failure from the patient (live bug —
      // no prefill, no provenance, no notice). Empty prefill → failed.
      return Object.keys(action.prefill).length > 0
        ? { phase: "steps", prefill: action.prefill, failed: false }
        : { phase: "steps", prefill: {}, failed: true };
    case "failure":
      return { phase: "steps", prefill: {}, failed: true };
    case "skip":
      return MANUAL;
  }
}

/**
 * Validated candidates → per-question prefill, pack order, values copied.
 *
 * askIf filtering (INT-236, mirroring the DSL gates): the candidates are
 * treated as provisional answers, and a gated question keeps its
 * suggestion only when its gate is met BY THE SUGGESTIONS themselves. A
 * gate that cannot be established from the transcript drops the prefill —
 * the question still surfaces normally once the patient's committed
 * answers meet it, just without a suggestion (honest, never a dead end).
 */
export function prefillForPack(
  pack: readonly IntakeQuestion[],
  candidates: Record<string, ExtractCandidate>,
): PrefillMap {
  const provisional: AnsweredValues[] = pack
    .filter((question) => candidates[question.id] !== undefined)
    .map((question) => ({ questionId: question.id, values: candidates[question.id].values }));
  const prefill: PrefillMap = {};
  for (const question of pack) {
    const candidate = candidates[question.id];
    if (candidate && askIfMet(question.askIf, provisional)) {
      prefill[question.id] = { values: [...candidate.values], quote: candidate.quote };
    }
  }
  return prefill;
}

export type ConfirmAction =
  { type: "confirm" } | { type: "change"; values: string[] } | { type: "skip" };

/** What the patient's action on one question commits as the answer. */
export function resolveAnswer(prefill: Prefill | undefined, action: ConfirmAction): string[] {
  switch (action.type) {
    case "confirm":
      return prefill ? [...prefill.values] : [];
    case "change":
      return [...action.values];
    case "skip":
      return [];
  }
}

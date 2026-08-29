/**
 * Intake entry machine (INT-199, rewritten by INT-239). Three phases and
 * no chooser: probe the voice lane, run the SPOKEN DIALOGUE, or run the
 * typed steps.
 *
 * The dialogue (karşılıklı konuşma) is the only voice entry — the earlier
 * one-shot "tell it all at once, then confirm" path is gone from the
 * product, along with its offer screen. Typed intake stays reachable from
 * every phase (`skip`): it serves accessibility and anyone who cannot
 * speak, and it is what the blueprint's `typed` voice profile means
 * (files/03 §4.9.1) — a quiet second door, never a co-equal first button.
 *
 * Invariant posture: candidates are ANSWER SUGGESTIONS the patient confirms
 * one question at a time — never triage, never a diagnosis (invariant 1);
 * every failure or skip lands in the exact manual flow, never a dead end;
 * the quote is the patient's verbatim words, rendered as provenance only.
 */
export interface Prefill {
  values: string[];
  /** The patient's verbatim words behind the suggestion. */
  quote: string;
}

export type PrefillMap = Record<string, Prefill>;

export type VoiceIntakeState =
  /** Probing the voice lane — a beat, not a screen to decide on. */
  | { phase: "gate" }
  /** The spoken dialogue: lib/dialogue owns the turns, this machine only
   * holds the door. `failure` from here lands in the manual steps WITH the
   * notice, `skip` quietly — answers are committed per confirm and both
   * carry the unconfirmed suggestions as prefill, so nothing the patient
   * said is lost by either exit. A TTS outage is NOT one of these exits:
   * the conversation goes silent and continues (INT-261, stream.ts). */
  | { phase: "dialogue" }
  | { phase: "steps"; prefill: PrefillMap; failed: boolean };

export type VoiceIntakeAction =
  /** The voice lane answered: go straight into the conversation. */
  | { type: "voice_ready" }
  | { type: "voice_unavailable" }
  /** Dialogue hand-over: whatever it could not confirm, as prefill. */
  | { type: "candidates"; prefill: PrefillMap }
  /**
   * The dialogue cannot continue (no microphone, no ASR). It carries the
   * same leftovers a tidy hand-over would (INT-261): both actions land the
   * patient in the SAME typed steps, so both must arrive with everything
   * the conversation extracted from the patient's own words. `prefill` is
   * required rather than optional — a caller that has leftovers and forgets
   * to pass them is exactly the defect this replaced.
   */
  | { type: "failure"; prefill: PrefillMap }
  /** "Yazarak devam edin" — the typed lane, reachable from anywhere. */
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
      // No offer in between: a ready lane IS the conversation (INT-239).
      return state.phase === "gate" ? { phase: "dialogue" } : state;
    case "voice_unavailable":
      return state.phase === "gate" ? MANUAL : state;
    case "candidates":
      // Ask-ahead hand-over: the dialogue already committed every
      // confirmed answer; whatever could not be confirmed in-conversation
      // arrives here as prefill for the manual steps. Empty is NOT a
      // failure — the patient answers the remaining questions fresh.
      return state.phase === "dialogue"
        ? { phase: "steps", prefill: action.prefill, failed: false }
        : state;
    case "failure":
      return { phase: "steps", prefill: action.prefill, failed: true };
    case "skip":
      return MANUAL;
  }
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

/**
 * The typed event surface of the streaming voice session, and the seam onto
 * the existing dialogue state machine (INT-103).
 *
 * This module is the ONLY coupling point between lib/livekit and
 * lib/dialogue. It imports a TYPE from stream.ts and nothing else — no
 * runtime import, no edit to stream.ts, DialogueIntake.tsx or tts.ts, which
 * other issues own. The coordinator wires the two with the one line quoted in
 * `DIALOGUE_WIRING`.
 *
 * WHAT IS DELIBERATELY NOT MAPPED, and why: turn-taking. Invariant 9 puts the
 * Talker's tool boundary and its speech-insertion windows SERVER-side, and
 * this client must not re-implement or anticipate them. The agent messages
 * that will drive `utterance` / `transcript_ready` / `extract_settled` are
 * INT-091's and INT-092's to define on the wire; inventing a mapping for a
 * protocol that does not exist yet would be exactly the kind of plausible
 * fiction invariant 17 forbids. So the mapper below covers the one transition
 * whose meaning is already settled — a dead transport is a dead dialogue —
 * and returns null for everything else rather than guessing.
 *
 * RED is not mapped either, and that is structural rather than pending: a RED
 * preempts the dialogue instead of advancing it (invariant 21), so it is
 * rendered ABOVE the reducer by the screen, never fed through it as a turn.
 */
import type { DialogueStreamAction } from "../dialogue/stream";
import type { RedTrigger, SessionFailure, SessionPhase, TurnQuality } from "./types";

/**
 * Everything the session tells its caller. Every payload is ids, enums and
 * transport numbers — never patient words (invariant 6).
 */
export type VoiceSessionEvent =
  /** Lifecycle moved. The UI shows connection state honestly from this. */
  | { readonly type: "phase"; readonly phase: SessionPhase }
  /** One turn's RTT/jitter/loss window closed (the INT-103 acceptance). */
  | { readonly type: "turn_quality"; readonly quality: TurnQuality }
  /**
   * A rules-engine RED arrived over the DATA channel and was handed to the RED
   * store, which renders it from the pre-positioned catalog with media already
   * gone (invariant 21; INT-465).
   */
  | { readonly type: "red"; readonly trigger: RedTrigger }
  /** Terminal. The caller falls back to the typed intake. */
  | { readonly type: "failed"; readonly reason: SessionFailure };

export type VoiceSessionListener = (event: VoiceSessionEvent) => void;

/**
 * Map a session event onto the existing dialogue reducer's action type.
 *
 * Returns null when the event has no dialogue meaning — telemetry, lifecycle
 * noise, and RED (see the header). A null is a deliberate "nothing to
 * dispatch", not an unhandled case.
 */
export function toDialogueStreamAction(event: VoiceSessionEvent): DialogueStreamAction | null {
  if (event.type === "failed") {
    // stream.ts treats `failure` as terminal and lands the patient in the
    // manual steps with every committed answer intact — exactly the right
    // behaviour when the transport is gone for good.
    return { type: "failure" };
  }
  return null;
}

/**
 * The single line the coordinator adds inside useDialogueSession (or the
 * screen that owns the reducer) to join the two halves. Quoted as a string so
 * this file documents the seam without reaching into a module it must not
 * edit; the wiring test asserts the two sides still fit.
 */
export const DIALOGUE_WIRING =
  "session.subscribe((e) => { const a = toDialogueStreamAction(e); if (a !== null) dispatch(a); });";

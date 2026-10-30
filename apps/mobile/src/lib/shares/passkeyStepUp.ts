/**
 * INT-582 (D36) — the passkey `StepUp` that plugs into INT-587's seam.
 *
 * INT-587 typed the step-up in front of Doctor Link issuance (./stepUp) and
 * shipped the OTP-session tier behind it, saying "INT-582 supplies a passkey
 * StepUp and nothing above or below it changes". This is that StepUp:
 *
 * - the server says which tier this patient is on (`step-up/options`): a
 *   patient WITH a passkey asserts on the phone and the proof carries the
 *   single-use grant for this act; a patient WITHOUT one is answered by the
 *   tier that stood before (`fallback`, the OTP session) — never a lockout;
 * - a passkey that could not confirm the act is a refusal with its own
 *   sentence (the manual path), and a sheet the patient closed is theirs;
 * - an options call that did not get an answer proves the fallback tier and
 *   leaves the decision to the server's gate on the issuing POST itself,
 *   which asks again if this patient must step up (`withStepUp`).
 *
 * Pure over injected ports; ./sessionStepUp wires the production ones.
 */
import type { PasskeyPorts } from "@/lib/auth/passkey/ceremony";
import { stepUpFor } from "@/lib/auth/passkey/ceremony";
import { STEP_UP_GRANT_HEADER, type StepUpAction } from "@/lib/auth/passkey/rp";

import { type StepUp, type StepUpProof, passkeyProof } from "./stepUp";

export function passkeyStepUp(action: StepUpAction, fallback: StepUp, ports: PasskeyPorts): StepUp {
  return {
    tier: "passkey",
    async prove() {
      let result;
      try {
        result = await stepUpFor(action, ports);
      } catch {
        return fallback.prove();
      }
      switch (result.kind) {
        case "passkey":
          return passkeyProof(result.grant);
        case "otp_session":
          return fallback.prove();
        case "cancelled":
          return { refused: "step_up_cancelled" };
        case "refused":
          return result.manualPath ? { refused: "step_up" } : fallback.prove();
      }
    },
  };
}

/** The header a passkey proof adds to its one request; none for the OTP tier. */
export function stepUpHeaders(proof: StepUpProof): Record<string, string> {
  return proof.tier === "passkey" && typeof proof.grant === "string" && proof.grant.length > 0
    ? { [STEP_UP_GRANT_HEADER]: proof.grant }
    : {};
}

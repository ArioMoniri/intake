/**
 * INT-582 (D36) — the passkey step-up in front of a sensitive request.
 *
 * `withStepUp(action, send)` sends the request as the patient's tier stands
 * today. The server's gate answers it directly for a patient without a
 * passkey (the OTP-session tier — never a lockout) and refuses it with
 * `step_up_required` for a patient with one; only then does this run the
 * passkey ceremony for THAT action and send the request once more with the
 * single-use grant. So a patient without a passkey costs no extra round trip,
 * and the decision of who must step up stays the server's.
 *
 * `passkeyStepUp(action)` is the same ceremony in the shape of INT-587's
 * `StepUp` seam (`tier` + `prove()`), carrying the grant in its proof so the
 * Doctor Link issue can attach it with `stepUpHeaders(proof)` once that seam
 * is on main (#995).
 */
import { passkeyApi } from "./api";
import { type PasskeyPorts, type StepUpResult, stepUpFor } from "./ceremony";
import { loadPasskeyNative } from "./native";
import { STEP_UP_GRANT_HEADER, type StepUpAction } from "./rp";

export const defaultPasskeyPorts: PasskeyPorts = {
  native: loadPasskeyNative,
  registrationOptions: passkeyApi.registrationOptions,
  register: passkeyApi.register,
  stepUpOptions: passkeyApi.stepUpOptions,
  stepUp: passkeyApi.stepUp,
};

/** What a stepped-up send ended as. */
export type SteppedUp =
  | { kind: "response"; response: Response; error: string | null }
  | { kind: "refused"; manualPath: boolean }
  | { kind: "cancelled" };

async function errorCodeOf(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { error?: unknown };
    return typeof body.error === "string" ? body.error : "";
  } catch {
    return "";
  }
}

/**
 * Send, and step up only when the server asks for it. A 403 is read for its
 * error code (and so consumed); the code is handed back so the caller can
 * still name the refusal it was — a consent refusal stays a consent refusal.
 */
export async function withStepUp(
  action: StepUpAction,
  send: (headers: Record<string, string>) => Promise<Response>,
  ports: PasskeyPorts = defaultPasskeyPorts,
): Promise<SteppedUp> {
  const first = await send({});
  if (first.status !== 403) {
    return { kind: "response", response: first, error: null };
  }
  const error = await errorCodeOf(first);
  if (error !== "step_up_required") {
    return { kind: "response", response: first, error };
  }
  const result = await stepUpFor(action, ports);
  if (result.kind === "cancelled") {
    return { kind: "cancelled" };
  }
  if (result.kind !== "passkey") {
    // a passkey was required and could not be given: a person decides
    return { kind: "refused", manualPath: result.kind === "refused" ? result.manualPath : true };
  }
  const second = await send({ [STEP_UP_GRANT_HEADER]: result.grant });
  if (second.status === 403) {
    const again = await errorCodeOf(second);
    if (again === "step_up_required" || again === "step_up_refused") {
      return { kind: "refused", manualPath: true };
    }
    return { kind: "response", response: second, error: again };
  }
  return { kind: "response", response: second, error: null };
}

// --- INT-587's seam shape -----------------------------------------------------------------

/** Proof that the step-up for one act was passed; the grant rides with it. */
export interface PasskeyStepUpProof {
  readonly tier: "passkey" | "otp_session";
  readonly grant: string | null;
}

export function proofOf(result: StepUpResult): PasskeyStepUpProof | null {
  if (result.kind === "passkey") {
    return { tier: "passkey", grant: result.grant };
  }
  if (result.kind === "otp_session") {
    return { tier: "otp_session", grant: null };
  }
  return null;
}

/** The header a proven passkey step-up adds to its request; none otherwise. */
export function stepUpHeaders(proof: PasskeyStepUpProof): Record<string, string> {
  return proof.tier === "passkey" && proof.grant !== null
    ? { [STEP_UP_GRANT_HEADER]: proof.grant }
    : {};
}

export interface PasskeyStepUp {
  readonly tier: "passkey";
  prove(): Promise<PasskeyStepUpProof | null>;
}

/** INT-587's `StepUp`, made by a passkey for one action. */
export function passkeyStepUp(
  action: StepUpAction,
  ports: PasskeyPorts = defaultPasskeyPorts,
): PasskeyStepUp {
  return {
    tier: "passkey",
    async prove() {
      try {
        return proofOf(await stepUpFor(action, ports));
      } catch {
        return null;
      }
    },
  };
}

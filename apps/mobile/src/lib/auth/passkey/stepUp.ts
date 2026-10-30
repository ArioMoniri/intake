/**
 * INT-582 (D36) — the passkey step-up in front of a sensitive request.
 *
 * `withStepUp(action, send)` sends the request as the patient's tier stands.
 * The server's gate answers it directly for a patient without a passkey (the
 * OTP-session tier — never a lockout) and refuses it with `step_up_required`
 * for a patient with one; only then does this run the passkey ceremony for
 * THAT action and send the request once more with the single-use grant. So a
 * patient without a passkey costs no extra round trip, and the decision of
 * who must step up stays the server's.
 *
 * A caller that already holds a grant (INT-587's seam: a `passkey` proof made
 * by ../../shares/passkeyStepUp) passes it as `initial`; a grant the server
 * still refuses is a refusal, never a second ceremony.
 */
import { passkeyApi } from "./api";
import { type PasskeyPorts, stepUpFor } from "./ceremony";
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

/** The step-up refusals of the server's gate (intake_api.passkey.gate). */
function isStepUpRefusal(error: string): boolean {
  return error === "step_up_required" || error === "step_up_refused";
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
  initial: Record<string, string> = {},
): Promise<SteppedUp> {
  const first = await send(initial);
  if (first.status !== 403) {
    return { kind: "response", response: first, error: null };
  }
  const error = await errorCodeOf(first);
  if (!isStepUpRefusal(error)) {
    return { kind: "response", response: first, error };
  }
  if (error === "step_up_refused" || STEP_UP_GRANT_HEADER in initial) {
    // a grant was sent and refused (spent, expired, another session): a
    // person decides — never a loop of ceremonies
    return { kind: "refused", manualPath: true };
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
    if (isStepUpRefusal(again)) {
      return { kind: "refused", manualPath: true };
    }
    return { kind: "response", response: second, error: again };
  }
  return { kind: "response", response: second, error: null };
}

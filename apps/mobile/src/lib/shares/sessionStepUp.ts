/**
 * INT-587 — the production step-up; INT-582 (D36) puts the passkey in front of
 * the OTP tier.
 *
 * "An OTP-verified session is present" means the token custody holds one —
 * the in-memory access token, or the keychain refresh token it rotates from
 * (auth/tokens.ts, INT-131). Reading whether one exists is all this does; no
 * credential is copied, logged or returned. The server's own check is the
 * DPoP-bound token on the issuing POST itself.
 */
import { defaultPasskeyPorts } from "@/lib/auth/passkey/stepUp";
import { getAccessToken, getRefreshToken } from "@/lib/auth/tokens";

import { passkeyStepUp } from "./passkeyStepUp";
import { otpSessionStepUp, type StepUp } from "./stepUp";

async function hasOtpSession(): Promise<boolean> {
  if (getAccessToken() !== null) {
    return true;
  }
  return (await getRefreshToken()) !== null;
}

/**
 * The step-up the issuing screen uses. INT-582 (D36): a patient with a passkey
 * asserts for this act; a patient without one stays on the OTP session tier
 * above, unchanged — never a lockout.
 */
export const issueStepUp: StepUp = passkeyStepUp(
  "doctor_link_issue",
  otpSessionStepUp(hasOtpSession),
  defaultPasskeyPorts,
);

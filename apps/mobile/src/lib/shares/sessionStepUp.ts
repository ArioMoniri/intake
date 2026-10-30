/**
 * INT-587 — the production step-up until INT-582 (D36): the OTP tier.
 *
 * "An OTP-verified session is present" means the token custody holds one —
 * the in-memory access token, or the keychain refresh token it rotates from
 * (auth/tokens.ts, INT-131). Reading whether one exists is all this does; no
 * credential is copied, logged or returned. The server's own check is the
 * DPoP-bound token on the issuing POST itself.
 */
import { getAccessToken, getRefreshToken } from "@/lib/auth/tokens";

import { otpSessionStepUp, type StepUp } from "./stepUp";

async function hasOtpSession(): Promise<boolean> {
  if (getAccessToken() !== null) {
    return true;
  }
  return (await getRefreshToken()) !== null;
}

/** The step-up the issuing screen uses today. INT-582 replaces this export. */
export const issueStepUp: StepUp = otpSessionStepUp(hasOtpSession);

/**
 * INT-587 — the step-up seam in front of Doctor Link issuance.
 *
 * D36 (INT-582, GitHub #981) will step a sensitive action up to a patient
 * passkey. Until it lands the tier is the one that exists: the OTP-verified,
 * DPoP-bound session. The seam is typed so that issuing cannot be called
 * without a proof, and so INT-582 swaps one `StepUp` for another without
 * touching the transport or the screen.
 *
 * Two refusals happen here, before any network: a share consent this phone
 * has seen withdrawn (a revoked grant stops the link), and a missing session.
 */
import { describe, expect, it, vi } from "vitest";

import {
  STEP_UP_TIERS,
  authorizeIssue,
  isStepUpProof,
  isStepUpRefusal,
  otpSessionStepUp,
  passkeyProof,
} from "./stepUp";

describe("the OTP session tier", () => {
  it("proves the tier when an OTP session is present", async () => {
    const proof = await otpSessionStepUp(async () => true).prove();
    expect(proof).toMatchObject({ tier: "otp_session" });
  });

  it("proves nothing without one", async () => {
    expect(await otpSessionStepUp(async () => false).prove()).toBeNull();
  });

  it("a session check that throws is no proof", async () => {
    const stepUp = otpSessionStepUp(async () => {
      throw new Error("keychain locked");
    });
    expect(await stepUp.prove()).toBeNull();
  });

  it("names the passkey tier the seam is waiting for, and no other", () => {
    expect([...STEP_UP_TIERS]).toEqual(["otp_session", "passkey"]);
  });
});

describe("authorising an issue", () => {
  it("a share consent withdrawn on this phone refuses before the step-up runs", async () => {
    const prove = vi.fn(async () => true);
    const result = await authorizeIssue("withdrawn", otpSessionStepUp(prove));
    expect(result).toEqual({ ok: false, reason: "consent" });
    expect(prove).not.toHaveBeenCalled();
  });

  it("no session is a session refusal", async () => {
    expect(
      await authorizeIssue(
        "granted",
        otpSessionStepUp(async () => false),
      ),
    ).toEqual({
      ok: false,
      reason: "session",
    });
  });

  it("an unknown standing goes on to the server, which holds the record", async () => {
    // The near miss of the first case: this phone not having SEEN a grant is
    // not a withdrawal — the server may hold one from an earlier send, and its
    // own share-scope check is the authority (invariant 4).
    const result = await authorizeIssue(
      "unknown",
      otpSessionStepUp(async () => true),
    );
    expect(result.ok).toBe(true);
  });
});

describe("INT-582: the passkey tier in the seam", () => {
  it("a passkey proof is a proof of the passkey tier and carries its grant", () => {
    const proof = passkeyProof("grant-value");
    expect(isStepUpProof(proof)).toBe(true);
    expect(proof).toMatchObject({ tier: "passkey", grant: "grant-value" });
  });

  it("a refusal keeps its reason through authorizeIssue; null is still 'session'", async () => {
    const refusing = (refused: "step_up" | "step_up_cancelled") => ({
      tier: "passkey" as const,
      prove: async () => ({ refused }),
    });
    expect(await authorizeIssue("granted", refusing("step_up"))).toEqual({
      ok: false,
      reason: "step_up",
    });
    expect(await authorizeIssue("granted", refusing("step_up_cancelled"))).toEqual({
      ok: false,
      reason: "step_up_cancelled",
    });
    expect(isStepUpRefusal({ refused: "step_up" })).toBe(true);
    expect(isStepUpRefusal({ refused: "other" })).toBe(false);
    expect(isStepUpProof({ refused: "step_up" })).toBe(false);
  });
});

/**
 * INT-582 (D36) — the passkey StepUp in INT-587's seam.
 *
 * A patient with a passkey proves the Doctor Link issue with a passkey proof
 * carrying its single-use grant; a patient without one is answered by the
 * OTP session tier that stood before — never a lockout. A passkey refusal
 * keeps its own sentence (the manual path); a closed sheet is the patient's
 * choice; an unanswered options call leaves the decision to the server.
 */
import { describe, expect, it, vi } from "vitest";

import type { PasskeyPorts, ServerAnswer } from "@/lib/auth/passkey/ceremony";
import { STEP_UP_GRANT_HEADER } from "@/lib/auth/passkey/rp";

import { passkeyStepUp, stepUpHeaders } from "./passkeyStepUp";
import { authorizeIssue, isStepUpProof, otpSessionStepUp, type StepUpProof } from "./stepUp";

vi.mock("@/lib/auth/api", () => ({ authedFetch: vi.fn() }));
vi.mock("@/lib/auth/passkey/native", () => ({ loadPasskeyNative: async () => null }));

const OFFER = {
  enrolled: true,
  publicKey: {
    challenge: "Y2hhbGxlbmdl",
    rpId: "3-211-2-143.sslip.io",
    allowCredentials: [{ type: "public-key", id: "Y3JlZA" }],
    userVerification: "required",
  },
};

const ok = (body: unknown): ServerAnswer => ({ ok: true, status: 200, body });

function ports(overrides: Partial<PasskeyPorts> = {}): PasskeyPorts {
  return {
    native: async () => ({
      create: async () => null,
      get: async () => ({
        id: "Y3JlZA",
        rawId: "Y3JlZA",
        type: "public-key",
        response: { clientDataJSON: "e30", authenticatorData: "AA", signature: "AA" },
      }),
    }),
    registrationOptions: async () => ok({}),
    register: async () => ok({}),
    stepUpOptions: vi.fn(async () => ok(OFFER)),
    stepUp: vi.fn(async () => ok({ grant: "grant-value" })),
    ...overrides,
  };
}

const session = otpSessionStepUp(async () => true);

describe("the passkey StepUp", () => {
  it("is the passkey tier the seam named, and proves with the grant for this act", async () => {
    const wired = ports();
    const stepUp = passkeyStepUp("doctor_link_issue", session, wired);
    expect(stepUp.tier).toBe("passkey");
    const proof = await stepUp.prove();
    expect(isStepUpProof(proof)).toBe(true);
    expect(proof).toMatchObject({ tier: "passkey", grant: "grant-value" });
    expect(wired.stepUpOptions).toHaveBeenCalledWith("doctor_link_issue");
    expect(stepUpHeaders(proof as StepUpProof)).toEqual({
      [STEP_UP_GRANT_HEADER]: "grant-value",
    });
  });

  it("a patient without a passkey is proven by the OTP session tier, with no header", async () => {
    const wired = ports({
      stepUpOptions: async () => ok({ enrolled: false, tier: "otp_session", enrolment: "offered" }),
    });
    const proof = await passkeyStepUp("doctor_link_issue", session, wired).prove();
    expect(proof).toMatchObject({ tier: "otp_session" });
    expect(stepUpHeaders(proof as StepUpProof)).toEqual({});
  });

  it("near miss: no session is still no proof", async () => {
    const wired = ports({
      stepUpOptions: async () => ok({ enrolled: false, tier: "otp_session", enrolment: "offered" }),
    });
    const none = otpSessionStepUp(async () => false);
    expect(await passkeyStepUp("doctor_link_issue", none, wired).prove()).toBeNull();
  });

  it("a passkey that cannot confirm the act is a refusal with the manual-path sentence", async () => {
    const wired = ports({
      stepUp: async () => ({ ok: false, status: 403, error: "step_up_refused", manualPath: true }),
    });
    const stepUp = passkeyStepUp("doctor_link_issue", session, wired);
    expect(await authorizeIssue("granted", stepUp)).toEqual({ ok: false, reason: "step_up" });
  });

  it("a closed sheet is the patient's own choice", async () => {
    const wired = ports({
      native: async () => ({ create: async () => null, get: async () => null }),
    });
    const stepUp = passkeyStepUp("doctor_link_issue", session, wired);
    expect(await authorizeIssue("granted", stepUp)).toEqual({
      ok: false,
      reason: "step_up_cancelled",
    });
  });

  it("an unanswered options call proves the tier that stood and leaves it to the server", async () => {
    const unanswered = ports({
      stepUpOptions: async () => ({ ok: false, status: 0, error: "", manualPath: false }),
    });
    expect(await passkeyStepUp("doctor_link_issue", session, unanswered).prove()).toMatchObject({
      tier: "otp_session",
    });
    const thrown = ports({
      stepUpOptions: async () => {
        throw new Error("network");
      },
    });
    expect(await passkeyStepUp("doctor_link_issue", session, thrown).prove()).toMatchObject({
      tier: "otp_session",
    });
  });

  it("a withdrawn share consent still refuses before the passkey is asked", async () => {
    const wired = ports();
    const result = await authorizeIssue(
      "withdrawn",
      passkeyStepUp("doctor_link_issue", session, wired),
    );
    expect(result).toEqual({ ok: false, reason: "consent" });
    expect(wired.stepUpOptions).not.toHaveBeenCalled();
  });
});

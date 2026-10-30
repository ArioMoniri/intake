/**
 * INT-582 (D36) — stepping up in front of a sensitive request.
 *
 * The server decides who must step up: the request goes out as the tier
 * stands, and only a `step_up_required` answer runs the passkey ceremony and
 * resends with the single-use grant. Near misses: a patient without a
 * passkey (no 403) costs no ceremony; a consent refusal (a different 403) is
 * handed back as itself, not mistaken for a step-up; a grant already sent and
 * refused is a refusal, never a second ceremony.
 */
import { describe, expect, it, vi } from "vitest";

import type { PasskeyPorts, ServerAnswer } from "./ceremony";
import { STEP_UP_GRANT_HEADER } from "./rp";
import { withStepUp } from "./stepUp";

vi.mock("@/lib/auth/api", () => ({ authedFetch: vi.fn() }));
vi.mock("./native", () => ({ loadPasskeyNative: async () => null }));

function response(status: number, body: unknown = {}): Response {
  return { ok: status < 300, status, json: async () => body } as unknown as Response;
}

const OFFER = {
  enrolled: true,
  publicKey: {
    challenge: "Y2hhbGxlbmdl",
    rpId: "3-211-2-143.sslip.io",
    allowCredentials: [{ type: "public-key", id: "Y3JlZA" }],
    userVerification: "required",
  },
};

function ports(overrides: Partial<PasskeyPorts> = {}): PasskeyPorts {
  const ok = (body: unknown): ServerAnswer => ({ ok: true, status: 200, body });
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

describe("withStepUp", () => {
  it("a patient without a passkey is answered directly, with no ceremony", async () => {
    const wired = ports();
    const send = vi.fn(async () => response(201));
    const sent = await withStepUp("data_delete", send, wired);
    expect(sent.kind).toBe("response");
    expect(send).toHaveBeenCalledTimes(1);
    expect(send).toHaveBeenCalledWith({});
    expect(wired.stepUpOptions).not.toHaveBeenCalled();
  });

  it("a step-up answer runs the ceremony for this action and resends with the grant", async () => {
    const wired = ports();
    const send = vi
      .fn()
      .mockResolvedValueOnce(response(403, { error: "step_up_required", action: "data_delete" }))
      .mockResolvedValueOnce(response(201));
    const sent = await withStepUp("data_delete", send, wired);
    expect(sent.kind).toBe("response");
    expect(wired.stepUpOptions).toHaveBeenCalledWith("data_delete");
    expect(send).toHaveBeenLastCalledWith({ [STEP_UP_GRANT_HEADER]: "grant-value" });
  });

  it("a grant the caller already holds goes on the first send", async () => {
    const wired = ports();
    const send = vi.fn(async () => response(201));
    await withStepUp("doctor_link_issue", send, wired, { [STEP_UP_GRANT_HEADER]: "held" });
    expect(send).toHaveBeenCalledWith({ [STEP_UP_GRANT_HEADER]: "held" });
    expect(wired.stepUpOptions).not.toHaveBeenCalled();
  });

  it("a held grant the server refuses is a refusal, not a second ceremony", async () => {
    const wired = ports();
    const send = vi.fn(async () => response(403, { error: "step_up_refused" }));
    const sent = await withStepUp("doctor_link_issue", send, wired, {
      [STEP_UP_GRANT_HEADER]: "spent",
    });
    expect(sent).toEqual({ kind: "refused", manualPath: true });
    expect(send).toHaveBeenCalledTimes(1);
    expect(wired.stepUpOptions).not.toHaveBeenCalled();
  });

  it("near miss: a consent refusal is handed back as itself", async () => {
    const wired = ports();
    const send = vi.fn(async () => response(403, { error: "consent_required" }));
    const sent = await withStepUp("doctor_link_issue", send, wired);
    expect(sent).toMatchObject({ kind: "response", error: "consent_required" });
    expect(wired.stepUpOptions).not.toHaveBeenCalled();
  });

  it("a cancelled sheet sends nothing more", async () => {
    const wired = ports({
      native: async () => ({ create: async () => null, get: async () => null }),
    });
    const send = vi.fn(async () => response(403, { error: "step_up_required" }));
    expect(await withStepUp("data_delete", send, wired)).toEqual({ kind: "cancelled" });
    expect(send).toHaveBeenCalledTimes(1);
  });

  it("a refused step-up names the manual path", async () => {
    const wired = ports({
      stepUp: vi.fn(async () => ({
        ok: false as const,
        status: 403,
        error: "step_up_refused",
        manualPath: true,
      })),
    });
    const send = vi.fn(async () => response(403, { error: "step_up_required" }));
    expect(await withStepUp("data_delete", send, wired)).toEqual({
      kind: "refused",
      manualPath: true,
    });
  });

  it("a grant the server still refuses on the resend is a refusal, not a retry loop", async () => {
    const send = vi.fn(async () => response(403, { error: "step_up_required" }));
    expect(await withStepUp("data_delete", send, ports())).toEqual({
      kind: "refused",
      manualPath: true,
    });
    expect(send).toHaveBeenCalledTimes(2);
  });

  it("another refusal on the resend is handed back with its code", async () => {
    const send = vi
      .fn()
      .mockResolvedValueOnce(response(403, { error: "step_up_required" }))
      .mockResolvedValueOnce(response(403, { error: "consent_required" }));
    expect(await withStepUp("doctor_link_issue", send, ports())).toMatchObject({
      kind: "response",
      error: "consent_required",
    });
  });

  it("an OTP-tier answer to the options after a step-up demand is still sent to a person", async () => {
    const wired = ports({
      stepUpOptions: vi.fn(async () => ({
        ok: true as const,
        status: 200,
        body: { enrolled: false, tier: "otp_session", enrolment: "offered" },
      })),
    });
    const send = vi.fn(async () => response(403, { error: "step_up_required" }));
    expect(await withStepUp("data_delete", send, wired)).toEqual({
      kind: "refused",
      manualPath: true,
    });
  });
});

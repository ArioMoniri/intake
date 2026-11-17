/**
 * INT-311 — the issuing transport, proved without a network.
 *
 * Two steps, one act: issue the grant (which returns the 128-bit token once),
 * then mint the opening code over the SAME authenticated session — the one
 * delivery channel that exists (HB-O7: no phone/e-mail destination is recorded
 * and no vendor is contracted, so the public delivery route refuses). The
 * credential is returned to the caller and held nowhere else; this module reads
 * no store and writes none.
 *
 * The properties below are the ones a screen cannot be trusted to preserve:
 * a bad recipient never reaches the network; each server refusal maps to its
 * own reason so the screen can say the true sentence; and a malformed body is
 * a failure, never a half-built credential.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { issueDoctorLink, parseCode, parseIssued, validateRecipient } from "./issue";
import { otpSessionStepUp, type StepUpProof } from "./stepUp";

const mocks = vi.hoisted(() => {
  class AuthApiError extends Error {
    readonly kind: string;
    constructor(kind: string) {
      super(kind);
      this.kind = kind;
    }
  }
  return { authedFetch: vi.fn(), AuthApiError };
});

vi.mock("@/lib/auth/api", () => ({
  authedFetch: mocks.authedFetch,
  AuthApiError: mocks.AuthApiError,
}));

const VISIT = "8c1a0b22-0000-4000-8000-0000000000aa";
const LINK = "3f1d6f3e-0000-4000-8000-000000000001";

const ISSUED = {
  link_id: LINK,
  recipient: "Dr Efe Onganer",
  expires_at: "2026-09-09T21:00:00Z",
  view_limit: 10,
  views_used: 0,
  revoked: false,
  spent: false,
  // A real token is ~128 bits of entropy; this stand-in is deliberately
  // low-entropy so it does not read as a secret to the gitleaks
  // generic-api-key rule (.gitleaks.toml uses no path allowlist). The test
  // asserts nothing about its shape, only that it is carried through and never
  // put in a URL.
  token: "link-token-aaaa-bbbb-cccc",
};
const CODE = { code: "482913", expires_in_s: 300, resend_after_s: 60 };

function ok(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body } as unknown as Response;
}

function refused(status: number, error: string): Response {
  return { ok: false, status, json: async () => ({ error }) } as unknown as Response;
}

/** The happy path: issue returns the token, then the OTP mint returns a code. */
function serving(): void {
  mocks.authedFetch.mockImplementation(async (path: string) =>
    path.endsWith("/otp") ? ok(CODE) : ok(ISSUED),
  );
}

afterEach(() => {
  mocks.authedFetch.mockReset();
});

/** The tier that exists until INT-582: an OTP session is present. */
async function proof(): Promise<StepUpProof> {
  const proved = await otpSessionStepUp(async () => true).prove();
  if (proved === null) throw new Error("fixture");
  return proved;
}

describe("validateRecipient — a label the watermark can carry", () => {
  it("accepts a trimmed, single-line label", () => {
    expect(validateRecipient("  Dr Efe Onganer  ")).toBe("Dr Efe Onganer");
  });

  it("refuses empty, over-long and control-character labels", () => {
    expect(validateRecipient("")).toBeNull();
    expect(validateRecipient("   ")).toBeNull();
    expect(validateRecipient("a".repeat(121))).toBeNull();
    expect(validateRecipient("Dr\nEfe")).toBeNull();
  });
});

describe("parsers — a malformed body is null, never a half-built value", () => {
  it("reads the token and the grant fields, or nothing", () => {
    expect(parseIssued(ISSUED)).toEqual({
      token: ISSUED.token,
      linkId: LINK,
      recipient: ISSUED.recipient,
      expiresAt: ISSUED.expires_at,
    });
    expect(parseIssued({ ...ISSUED, token: "" })).toBeNull();
    expect(parseIssued({ ...ISSUED, link_id: 42 })).toBeNull();
    expect(parseIssued(null)).toBeNull();
  });

  it("reads the opening code, or nothing", () => {
    expect(parseCode(CODE)).toBe("482913");
    expect(parseCode({ code: "" })).toBeNull();
    expect(parseCode({})).toBeNull();
  });
});

describe("issueDoctorLink — issue then mint, in one act", () => {
  it("returns the token and the freshly minted code together", async () => {
    serving();
    const result = await issueDoctorLink(VISIT, "Dr Efe Onganer", await proof());
    expect(result).toEqual({
      ok: true,
      credential: {
        recipient: "Dr Efe Onganer",
        token: ISSUED.token,
        code: "482913",
        expiresAt: ISSUED.expires_at,
      },
    });
  });

  it("calls issue first, then the OTP mint over the same session — two POSTs", async () => {
    serving();
    await issueDoctorLink(VISIT, "Dr Efe Onganer", await proof());
    const calls = mocks.authedFetch.mock.calls;
    expect(calls).toHaveLength(2);
    expect(calls[0][0]).toContain("/note/doctor-links");
    expect(calls[0][0]).not.toContain("/otp");
    expect((calls[0][1] as RequestInit).method).toBe("POST");
    expect(calls[1][0]).toContain(`/${LINK}/otp`);
    expect((calls[1][1] as RequestInit).method).toBe("POST");
  });

  it("never puts the token or the recipient in a URL (invariant 6)", async () => {
    serving();
    await issueDoctorLink(VISIT, "Dr Efe Onganer", await proof());
    for (const [path] of mocks.authedFetch.mock.calls) {
      expect(String(path)).not.toContain(ISSUED.token);
      expect(String(path)).not.toContain("Efe");
    }
  });

  it("refuses a bad recipient before it reaches the network", async () => {
    const result = await issueDoctorLink(VISIT, "   ", await proof());
    expect(result).toEqual({ ok: false, reason: "recipient_invalid" });
    expect(mocks.authedFetch).not.toHaveBeenCalled();
  });

  it("maps a note that was never sent to its own reason", async () => {
    mocks.authedFetch.mockResolvedValue(refused(409, "note_not_shared"));
    expect(await issueDoctorLink(VISIT, "Dr Efe", await proof())).toEqual({
      ok: false,
      reason: "not_shared",
    });
  });

  it("maps a visit with no date, and a rejected recipient, to their reasons", async () => {
    mocks.authedFetch.mockResolvedValue(refused(422, "visit_date_unknown"));
    expect(await issueDoctorLink(VISIT, "Dr Efe", await proof())).toEqual({
      ok: false,
      reason: "date_unknown",
    });
    mocks.authedFetch.mockResolvedValue(refused(422, "recipient_invalid"));
    expect(await issueDoctorLink(VISIT, "Dr Efe", await proof())).toEqual({
      ok: false,
      reason: "recipient_invalid",
    });
  });

  it("maps the abuse-gate 429 and the 503 unconfigured tier to their reasons", async () => {
    mocks.authedFetch.mockResolvedValue(refused(429, "otp_limited"));
    expect(await issueDoctorLink(VISIT, "Dr Efe", await proof())).toEqual({
      ok: false,
      reason: "limited",
    });
    mocks.authedFetch.mockResolvedValue(refused(503, "doctor_link_unconfigured"));
    expect(await issueDoctorLink(VISIT, "Dr Efe", await proof())).toEqual({
      ok: false,
      reason: "unavailable",
    });
  });

  it("does not mint a code when issuing failed", async () => {
    mocks.authedFetch.mockResolvedValue(refused(409, "note_not_shared"));
    await issueDoctorLink(VISIT, "Dr Efe", await proof());
    for (const [path] of mocks.authedFetch.mock.calls) {
      expect(String(path)).not.toContain("/otp");
    }
  });

  it("treats an unreachable server, and a malformed body, as unreachable", async () => {
    mocks.authedFetch.mockRejectedValue(new mocks.AuthApiError("network"));
    expect(await issueDoctorLink(VISIT, "Dr Efe", await proof())).toEqual({
      ok: false,
      reason: "unreachable",
    });
    mocks.authedFetch.mockReset();
    mocks.authedFetch.mockImplementation(async (path: string) =>
      path.endsWith("/otp") ? ok({ code: "" }) : ok(ISSUED),
    );
    expect(await issueDoctorLink(VISIT, "Dr Efe", await proof())).toEqual({
      ok: false,
      reason: "unreachable",
    });
  });
});

describe("INT-587 — the share consent and the step-up seam", () => {
  it("a revoked share grant stops the link: 403 on the share scope is its own reason", async () => {
    mocks.authedFetch.mockResolvedValue({
      ok: false,
      status: 403,
      json: async () => ({ error: "consent_required", scope: "share:previsit_note" }),
    } as unknown as Response);
    expect(await issueDoctorLink(VISIT, "Dr Efe", await proof())).toEqual({
      ok: false,
      reason: "consent",
    });
    for (const [path] of mocks.authedFetch.mock.calls) {
      expect(String(path)).not.toContain("/otp");
    }
  });

  it("refuses a proof from no known tier before any network", async () => {
    const forged = { tier: "sms_link" } as unknown as StepUpProof;
    expect(await issueDoctorLink(VISIT, "Dr Efe", forged)).toEqual({
      ok: false,
      reason: "session",
    });
    expect(mocks.authedFetch).not.toHaveBeenCalled();
  });

  it("a lost session is a session refusal, not an unreachable server", async () => {
    mocks.authedFetch.mockRejectedValue(new mocks.AuthApiError("session"));
    expect(await issueDoctorLink(VISIT, "Dr Efe", await proof())).toEqual({
      ok: false,
      reason: "session",
    });
  });
});

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

// INT-582: a phone without the native passkey module
vi.mock("@/lib/auth/passkey/native", () => ({ loadPasskeyNative: async () => null }));

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
    const result = await issueDoctorLink(VISIT, "Dr Efe Onganer");
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
    await issueDoctorLink(VISIT, "Dr Efe Onganer");
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
    await issueDoctorLink(VISIT, "Dr Efe Onganer");
    for (const [path] of mocks.authedFetch.mock.calls) {
      expect(String(path)).not.toContain(ISSUED.token);
      expect(String(path)).not.toContain("Efe");
    }
  });

  it("refuses a bad recipient before it reaches the network", async () => {
    const result = await issueDoctorLink(VISIT, "   ");
    expect(result).toEqual({ ok: false, reason: "recipient_invalid" });
    expect(mocks.authedFetch).not.toHaveBeenCalled();
  });

  it("maps a note that was never sent to its own reason", async () => {
    mocks.authedFetch.mockResolvedValue(refused(409, "note_not_shared"));
    expect(await issueDoctorLink(VISIT, "Dr Efe")).toEqual({ ok: false, reason: "not_shared" });
  });

  it("maps a visit with no date, and a rejected recipient, to their reasons", async () => {
    mocks.authedFetch.mockResolvedValue(refused(422, "visit_date_unknown"));
    expect(await issueDoctorLink(VISIT, "Dr Efe")).toEqual({ ok: false, reason: "date_unknown" });
    mocks.authedFetch.mockResolvedValue(refused(422, "recipient_invalid"));
    expect(await issueDoctorLink(VISIT, "Dr Efe")).toEqual({
      ok: false,
      reason: "recipient_invalid",
    });
  });

  it("maps the abuse-gate 429 and the 503 unconfigured tier to their reasons", async () => {
    mocks.authedFetch.mockResolvedValue(refused(429, "otp_limited"));
    expect(await issueDoctorLink(VISIT, "Dr Efe")).toEqual({ ok: false, reason: "limited" });
    mocks.authedFetch.mockResolvedValue(refused(503, "doctor_link_unconfigured"));
    expect(await issueDoctorLink(VISIT, "Dr Efe")).toEqual({ ok: false, reason: "unavailable" });
  });

  it("does not mint a code when issuing failed", async () => {
    mocks.authedFetch.mockResolvedValue(refused(409, "note_not_shared"));
    await issueDoctorLink(VISIT, "Dr Efe");
    for (const [path] of mocks.authedFetch.mock.calls) {
      expect(String(path)).not.toContain("/otp");
    }
  });

  it("treats an unreachable server, and a malformed body, as unreachable", async () => {
    mocks.authedFetch.mockRejectedValue(new mocks.AuthApiError("network"));
    expect(await issueDoctorLink(VISIT, "Dr Efe")).toEqual({ ok: false, reason: "unreachable" });
    mocks.authedFetch.mockReset();
    mocks.authedFetch.mockImplementation(async (path: string) =>
      path.endsWith("/otp") ? ok({ code: "" }) : ok(ISSUED),
    );
    expect(await issueDoctorLink(VISIT, "Dr Efe")).toEqual({ ok: false, reason: "unreachable" });
  });
});

describe("issuing steps up to the passkey when the server asks (INT-582, D36)", () => {
  it("a refused step-up mints nothing and names the manual-path sentence", async () => {
    mocks.authedFetch.mockImplementation(async (path: string) => {
      if (path.endsWith("/step-up/options")) {
        return ok({
          enrolled: true,
          publicKey: {
            challenge: "Y2hhbGxlbmdl",
            rpId: "3-211-2-143.sslip.io",
            allowCredentials: [{ type: "public-key", id: "Y3JlZA" }],
            userVerification: "required",
          },
        });
      }
      return refused(403, "step_up_required");
    });
    expect(await issueDoctorLink(VISIT, "Dr Efe")).toEqual({ ok: false, reason: "step_up" });
    const paths = mocks.authedFetch.mock.calls.map(([path]) => String(path));
    expect(paths.some((path) => path.endsWith("/otp"))).toBe(false);
  });

  it("a consent refusal is still a consent-shaped failure, not a step-up", async () => {
    mocks.authedFetch.mockResolvedValue(refused(403, "consent_required"));
    const result = await issueDoctorLink(VISIT, "Dr Efe");
    expect(result).toEqual({ ok: false, reason: "unreachable" });
    expect(mocks.authedFetch).toHaveBeenCalledTimes(1);
  });

  it("near miss: a patient without a passkey issues exactly as before", async () => {
    serving();
    const result = await issueDoctorLink(VISIT, "Dr Efe");
    expect(result.ok).toBe(true);
    expect(mocks.authedFetch).toHaveBeenCalledTimes(2);
  });
});

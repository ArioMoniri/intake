/**
 * INT-582 (D36) — the passkey state behind *Verileriniz*.
 *
 * Nothing is shown as enrolled or as recovering that the server did not
 * confirm; an unconfigured tier hides the offer rather than promising one;
 * a failed enrolment says which true sentence applies.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import type { PasskeyPorts, ServerAnswer } from "./ceremony";
import {
  addPasskey,
  loadPasskeys,
  parsePasskeyList,
  passkeySnapshot,
  resetPasskeys,
  startPasskeyRecovery,
} from "./store";

const mocks = vi.hoisted(() => ({ authedFetch: vi.fn() }));
vi.mock("@/lib/auth/api", () => ({ authedFetch: mocks.authedFetch }));
vi.mock("./native", () => ({ loadPasskeyNative: async () => null }));

function response(status: number, body: unknown): Response {
  return { ok: status < 300, status, json: async () => body } as unknown as Response;
}

afterEach(() => {
  resetPasskeys();
  mocks.authedFetch.mockReset();
});

describe("the list", () => {
  it("reads the server's enrolment word and the earliest running recovery", () => {
    expect(
      parsePasskeyList({
        enrolment: "enrolled",
        passkeys: [
          { recovery_ends_at: "2026-11-03T10:00:00+00:00" },
          { recovery_ends_at: "2026-11-02T10:00:00+00:00" },
          { recovery_ends_at: null },
        ],
      }),
    ).toEqual({ enrolment: "enrolled", recoveryEndsAt: "2026-11-02T10:00:00+00:00" });
    expect(parsePasskeyList({ enrolment: "offered", passkeys: [] })).toEqual({
      enrolment: "offered",
      recoveryEndsAt: null,
    });
  });

  it("refuses anything else", () => {
    expect(parsePasskeyList({ enrolment: "maybe", passkeys: [] })).toBeNull();
    expect(parsePasskeyList({ enrolment: "offered" })).toBeNull();
    expect(parsePasskeyList(null)).toBeNull();
  });

  it("an unconfigured tier hides the offer; an unreachable server claims nothing", async () => {
    mocks.authedFetch.mockResolvedValue(response(503, { error: "passkey_not_configured" }));
    await loadPasskeys();
    expect(passkeySnapshot().enrolment).toBe("unavailable");
    resetPasskeys();
    mocks.authedFetch.mockRejectedValue(new Error("network"));
    await loadPasskeys();
    expect(passkeySnapshot().enrolment).toBeNull();
  });

  it("loads an enrolled patient", async () => {
    mocks.authedFetch.mockResolvedValue(response(200, { enrolment: "enrolled", passkeys: [{}] }));
    await loadPasskeys();
    expect(passkeySnapshot()).toEqual({
      enrolment: "enrolled",
      recoveryEndsAt: null,
      notice: null,
    });
  });
});

describe("enrolling", () => {
  it("a phone without passkeys says so and claims nothing", async () => {
    await addPasskey();
    expect(passkeySnapshot()).toMatchObject({ enrolment: null, notice: "unsupported" });
  });

  it("a confirmed enrolment shows as enrolled", async () => {
    const ok = (body: unknown, status = 200): ServerAnswer => ({ ok: true, status, body });
    const ports: PasskeyPorts = {
      native: async () => ({
        create: async () => ({
          id: "Y3JlZA",
          rawId: "Y3JlZA",
          type: "public-key",
          response: { clientDataJSON: "e30", attestationObject: "oA" },
        }),
        get: async () => null,
      }),
      registrationOptions: async () =>
        ok({
          publicKey: {
            rp: { id: "3-211-2-143.sslip.io", name: "Önvizit" },
            user: { id: "aGFuZGxl", name: "Önvizit", displayName: "Önvizit" },
            challenge: "Y2hhbGxlbmdl",
            pubKeyCredParams: [{ type: "public-key", alg: -7 }],
            excludeCredentials: [],
            authenticatorSelection: {
              authenticatorAttachment: "platform",
              residentKey: "required",
              userVerification: "required",
            },
            attestation: "none",
          },
        }),
      register: async () => ok({ passkey_id: "p" }, 201),
      stepUpOptions: async () => ok({}),
      stepUp: async () => ok({}),
    };
    mocks.authedFetch.mockResolvedValue(response(200, { enrolment: "enrolled", passkeys: [{}] }));
    await addPasskey(ports);
    expect(passkeySnapshot()).toMatchObject({ enrolment: "enrolled", notice: "added" });
  });
});

describe("the lost phone", () => {
  it("shows the cool-off end the server returned", async () => {
    mocks.authedFetch.mockResolvedValue(
      response(202, { recovery_ends_at: "2026-11-02T10:00:00+00:00" }),
    );
    await startPasskeyRecovery();
    expect(passkeySnapshot()).toMatchObject({
      recoveryEndsAt: "2026-11-02T10:00:00+00:00",
      notice: "recovery_started",
    });
  });

  it("a recovery the server did not start is not shown as started", async () => {
    mocks.authedFetch.mockResolvedValue(response(404, { error: "not_found" }));
    await startPasskeyRecovery();
    expect(passkeySnapshot()).toMatchObject({ recoveryEndsAt: null, notice: "recovery_failed" });
  });
});

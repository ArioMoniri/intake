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
  cancelPasskeyRecovery,
  loadPasskeys,
  parsePasskeyList,
  passkeyRows,
  passkeySnapshot,
  removePasskey,
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
    ).toEqual({
      enrolment: "enrolled",
      recoveryEndsAt: "2026-11-02T10:00:00+00:00",
      passkeyIds: [],
    });
    expect(parsePasskeyList({ enrolment: "offered", passkeys: [] })).toEqual({
      enrolment: "offered",
      recoveryEndsAt: null,
      passkeyIds: [],
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
      passkeyIds: [],
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

describe("INT-582 review: cancelling a recovery, removing a passkey, the rows shown", () => {
  const OFFER = {
    enrolled: true,
    publicKey: {
      challenge: "Y2hhbGxlbmdl",
      rpId: "3-211-2-143.sslip.io",
      allowCredentials: [],
      userVerification: "required",
    },
  };
  const ok = (body: unknown, status = 200): ServerAnswer => ({ ok: true, status, body });
  const holder: PasskeyPorts = {
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
  };

  it("cancelling a running recovery steps up with recovery_cancel, then withdraws it", async () => {
    mocks.authedFetch.mockImplementation(async (path: string, init?: RequestInit) => {
      if (path === "/v1/me/passkeys/recovery" && init?.method === "DELETE") {
        return response(200, { cancelled: 1 });
      }
      return response(200, { enrolment: "enrolled", passkeys: [{ passkey_id: "p1" }] });
    });
    await cancelPasskeyRecovery(holder);
    expect(holder.stepUpOptions).toHaveBeenCalledWith("recovery_cancel");
    const cancel = mocks.authedFetch.mock.calls.find(
      ([path, init]) => path === "/v1/me/passkeys/recovery" && init?.method === "DELETE",
    );
    expect((cancel?.[1] as RequestInit).headers).toEqual({
      "X-Intake-Step-Up-Grant": "grant-value",
    });
    expect(passkeySnapshot()).toMatchObject({ recoveryEndsAt: null, notice: "recovery_cancelled" });
  });

  it("removing the passkey steps up with passkey_remove and names the passkey it removes", async () => {
    mocks.authedFetch.mockImplementation(async (path: string, init?: RequestInit) => {
      if (init?.method === "DELETE") {
        return response(204, null);
      }
      return response(200, { enrolment: "enrolled", passkeys: [{ passkey_id: "p1" }] });
    });
    await loadPasskeys();
    await removePasskey(holder);
    expect(holder.stepUpOptions).toHaveBeenCalledWith("passkey_remove");
    const removal = mocks.authedFetch.mock.calls.find(([, init]) => init?.method === "DELETE");
    expect(removal?.[0]).toBe("/v1/me/passkeys/p1");
    expect(passkeySnapshot().notice).toBe("removed");
  });

  it("shows the cancel row only while a recovery is running (near miss: none without one)", () => {
    expect(
      passkeyRows(
        { enrolment: "enrolled", recoveryEndsAt: null, notice: null, passkeyIds: ["p"] },
        false,
      ),
    ).toEqual(["enrolled", "remove", "lost"]);
    expect(
      passkeyRows(
        {
          enrolment: "enrolled",
          recoveryEndsAt: "2026-11-02T10:00:00+00:00",
          notice: null,
          passkeyIds: ["p"],
        },
        false,
      ),
    ).toEqual(["enrolled", "recoveryEnds", "cancelRecovery"]);
    expect(
      passkeyRows(
        { enrolment: "offered", recoveryEndsAt: null, notice: null, passkeyIds: [] },
        false,
      ),
    ).toEqual(["add"]);
  });

  it("'I lost my phone' asks to be confirmed before it starts anything", () => {
    expect(
      passkeyRows(
        { enrolment: "enrolled", recoveryEndsAt: null, notice: null, passkeyIds: ["p"] },
        true,
      ),
    ).toEqual(["enrolled", "remove", "lostConfirm"]);
  });

  it("removes every passkey this patient holds, one step-up each, and stops at a refusal", async () => {
    mocks.authedFetch.mockImplementation(async (_path: string, init?: RequestInit) => {
      if (init?.method === "DELETE") {
        return response(204, null);
      }
      return response(200, {
        enrolment: "enrolled",
        passkeys: [{ passkey_id: "p1" }, { passkey_id: "p2" }],
      });
    });
    await loadPasskeys();
    const stepUp = vi.fn(async () => ok({ grant: "grant-value" }));
    await removePasskey({ ...holder, stepUp });
    const removed = mocks.authedFetch.mock.calls
      .filter(([, init]) => init?.method === "DELETE")
      .map(([path]) => path);
    expect(removed).toEqual(["/v1/me/passkeys/p1", "/v1/me/passkeys/p2"]);
    expect(stepUp).toHaveBeenCalledTimes(2);
    expect(passkeySnapshot().notice).toBe("removed");

    mocks.authedFetch.mockClear();
    const refusing = vi.fn(async () => ({
      ok: false as const,
      status: 403,
      error: "step_up_refused",
      manualPath: true,
    }));
    await removePasskey({ ...holder, stepUp: refusing });
    expect(mocks.authedFetch.mock.calls.filter(([, init]) => init?.method === "DELETE")).toEqual(
      [],
    );
    expect(passkeySnapshot().notice).toBe("remove_failed");
  });
});

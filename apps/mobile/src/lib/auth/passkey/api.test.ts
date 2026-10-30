/**
 * INT-582 (D36) — the passkey transport, without a network.
 *
 * Routes and methods are the server's; a grant travels in its header and
 * never in a URL; a refusal is reduced to its machine code and whether the
 * server named the manual path; an unreachable server is a refusal, never a
 * pass.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { passkeyApi, toAnswer } from "./api";
import { STEP_UP_GRANT_HEADER } from "./rp";

const mocks = vi.hoisted(() => ({ authedFetch: vi.fn() }));
vi.mock("@/lib/auth/api", () => ({ authedFetch: mocks.authedFetch }));

function response(status: number, body: unknown): Response {
  return { ok: status < 300, status, json: async () => body } as unknown as Response;
}

afterEach(() => {
  mocks.authedFetch.mockReset();
});

describe("answers", () => {
  it("keeps the body of a success", async () => {
    expect(await toAnswer(response(201, { passkey_id: "p" }))).toEqual({
      ok: true,
      status: 201,
      body: { passkey_id: "p" },
    });
  });

  it("keeps only the code and the manual path of a refusal", async () => {
    const refused = response(403, {
      error: "step_up_refused",
      reason: "passkey_origin",
      manual_path: "kvkk_m13_application",
    });
    expect(await toAnswer(refused)).toEqual({
      ok: false,
      status: 403,
      error: "step_up_refused",
      manualPath: true,
    });
    expect(
      await toAnswer({ ok: false, status: 500, json: async () => "x" } as unknown as Response),
    ).toEqual({ ok: false, status: 500, error: "", manualPath: false });
  });

  it("an unreachable server is a refusal", async () => {
    mocks.authedFetch.mockRejectedValue(new Error("network"));
    expect(await passkeyApi.list()).toEqual({ ok: false, status: 0, error: "", manualPath: false });
  });
});

describe("routes", () => {
  it("each ceremony reaches its own route with its own method", async () => {
    mocks.authedFetch.mockResolvedValue(response(200, {}));
    const credential = {
      id: "Y3JlZA",
      rawId: "Y3JlZA",
      type: "public-key" as const,
      response: { clientDataJSON: "e30", attestationObject: "oA" },
    };
    await passkeyApi.registrationOptions();
    await passkeyApi.register(credential);
    await passkeyApi.stepUpOptions("data_export");
    await passkeyApi.list();
    await passkeyApi.startRecovery();
    const calls = mocks.authedFetch.mock.calls.map(([path, init]) => [path, init?.method]);
    expect(calls).toEqual([
      ["/v1/me/passkeys/registration/options", "POST"],
      ["/v1/me/passkeys/registration", "POST"],
      ["/v1/me/passkeys/step-up/options", "POST"],
      ["/v1/me/passkeys", "GET"],
      ["/v1/me/passkeys/recovery", "POST"],
    ]);
    expect(JSON.parse(String(mocks.authedFetch.mock.calls[2]?.[1]?.body))).toEqual({
      action: "data_export",
    });
  });

  it("a grant travels in its header, never in the URL", async () => {
    mocks.authedFetch.mockResolvedValue(response(204, null));
    await passkeyApi.remove("passkey-id", "grant-value");
    await passkeyApi.cancelRecovery("grant-value");
    for (const [path, init] of mocks.authedFetch.mock.calls) {
      expect(String(path)).not.toContain("grant-value");
      expect((init as RequestInit).headers).toEqual({ [STEP_UP_GRANT_HEADER]: "grant-value" });
      expect((init as RequestInit).method).toBe("DELETE");
    }
  });
});

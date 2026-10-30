/**
 * INT-583 — the push-token seam: PUT and DELETE /v1/auth/push-token over an
 * injected authed fetch, every server answer mapped to a typed result.
 *
 * The server keys a token to the device the session signed in from, so the
 * body names a platform and a token and nothing else: the client cannot say
 * which device it is.
 */
import { describe, expect, it, vi } from "vitest";

import { deletePushToken, putPushToken } from "./api";

/** An APNs-shaped device token: 32 bytes of lower-case hex, low entropy on purpose. */
const TOKEN = "a1".repeat(32);

function answer(status: number, body?: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => {
      if (body === undefined) {
        throw new SyntaxError("no body");
      }
      return body;
    },
  } as unknown as Response;
}

function fetcherAnswering(response: Response) {
  return vi.fn(async (_path: string, _init?: RequestInit) => response);
}

describe("PUT /v1/auth/push-token", () => {
  it("sends the platform and the token, as JSON, to the one route", async () => {
    const fetcher = fetcherAnswering(answer(204));
    await putPushToken(fetcher, TOKEN);
    expect(fetcher).toHaveBeenCalledTimes(1);
    const [path, init] = fetcher.mock.calls[0];
    expect(path).toBe("/v1/auth/push-token");
    expect(init?.method).toBe("PUT");
    expect(init?.headers).toEqual({ "Content-Type": "application/json" });
    expect(JSON.parse(String(init?.body))).toEqual({ platform: "ios", token: TOKEN });
  });

  it("204 is registered", async () => {
    expect(await putPushToken(fetcherAnswering(answer(204)), TOKEN)).toEqual({ ok: true });
  });

  it("409 session_unbound is its own result, so the caller stops trying", async () => {
    const fetcher = fetcherAnswering(answer(409, { error: "session_unbound" }));
    expect(await putPushToken(fetcher, TOKEN)).toEqual({ ok: false, error: "session_unbound" });
  });

  it("409 with another code is not read as unbound (near miss)", async () => {
    const fetcher = fetcherAnswering(answer(409, { error: "conflict" }));
    expect(await putPushToken(fetcher, TOKEN)).toEqual({ ok: false, error: "unreachable" });
  });

  it("422 is a malformed token", async () => {
    const fetcher = fetcherAnswering(
      answer(422, {
        error: "validation_error",
        detail: [{ type: "string_pattern_mismatch", loc: ["body", "token"] }],
      }),
    );
    expect(await putPushToken(fetcher, TOKEN)).toEqual({ ok: false, error: "invalid_token" });
  });

  it("503 push_unavailable is its own result: the server has no channel and stored nothing", async () => {
    const fetcher = fetcherAnswering(answer(503, { error: "push_unavailable" }));
    expect(await putPushToken(fetcher, TOKEN)).toEqual({ ok: false, error: "push_unavailable" });
  });

  it("503 without that code is not read as no channel (near miss)", async () => {
    expect(await putPushToken(fetcherAnswering(answer(503)), TOKEN)).toEqual({
      ok: false,
      error: "unreachable",
    });
    const other = fetcherAnswering(answer(503, { error: "upstream_down" }));
    expect(await putPushToken(other, TOKEN)).toEqual({ ok: false, error: "unreachable" });
  });

  it("push_unavailable on another status is not read as no channel (near miss)", async () => {
    const fetcher = fetcherAnswering(answer(500, { error: "push_unavailable" }));
    expect(await putPushToken(fetcher, TOKEN)).toEqual({ ok: false, error: "unreachable" });
  });

  it("a server error is unreachable, never registered", async () => {
    expect(await putPushToken(fetcherAnswering(answer(500)), TOKEN)).toEqual({
      ok: false,
      error: "unreachable",
    });
  });

  it("a thrown fetch (no network, no session) is unreachable and does not throw", async () => {
    const fetcher = vi.fn(async () => {
      throw new Error("session");
    });
    expect(await putPushToken(fetcher, TOKEN)).toEqual({ ok: false, error: "unreachable" });
  });

  it.each([
    ["63 characters", TOKEN.slice(1)],
    ["201 characters", "a".repeat(201)],
    ["uppercase", TOKEN.toUpperCase()],
    ["a non-hex letter", TOKEN.slice(0, 63) + "z"],
  ])("a token with %s is refused on the phone and never sent", async (_why, token) => {
    const fetcher = fetcherAnswering(answer(204));
    expect(await putPushToken(fetcher, token)).toEqual({ ok: false, error: "invalid_token" });
    expect(fetcher).not.toHaveBeenCalled();
  });
});

describe("DELETE /v1/auth/push-token", () => {
  it("calls the one route with DELETE and no body", async () => {
    const fetcher = fetcherAnswering(answer(204));
    await deletePushToken(fetcher);
    const [path, init] = fetcher.mock.calls[0];
    expect(path).toBe("/v1/auth/push-token");
    expect(init?.method).toBe("DELETE");
    expect(init?.body).toBeUndefined();
  });

  it("204 is done", async () => {
    expect(await deletePushToken(fetcherAnswering(answer(204)))).toEqual({ ok: true });
  });

  it("anything else is unreachable, and a thrown fetch does not throw", async () => {
    expect(await deletePushToken(fetcherAnswering(answer(503)))).toEqual({
      ok: false,
      error: "unreachable",
    });
    const fetcher = vi.fn(async () => {
      throw new TypeError("Network request failed");
    });
    expect(await deletePushToken(fetcher)).toEqual({ ok: false, error: "unreachable" });
  });
});

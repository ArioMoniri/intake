/** Room-token client (INT-103) against the INT-090 mint contract. */
import { describe, expect, it, vi } from "vitest";

import { RoomTokenError, createTokenSource, parseTokenResponse, voiceTokenPath } from "./token";

const SESSION_ID = "3f2504e0-4f89-11d3-9a0c-0305e82c3301";

const BODY = {
  url: "wss://sfu.example.invalid",
  token: "header.payload.signature",
  room: `intake-${SESSION_ID}`,
  expires_at_ms: 1_700_000_000_000,
};

function response(body: unknown, ok = true, status = 200): Response {
  return { ok, status, json: async () => body } as unknown as Response;
}

describe("voiceTokenPath", () => {
  it("addresses the session by id only", () => {
    expect(voiceTokenPath(SESSION_ID)).toBe(`/v1/visits/${SESSION_ID}/voice-token`);
  });
});

describe("parseTokenResponse", () => {
  it("accepts a well-formed response", () => {
    expect(parseTokenResponse(SESSION_ID, BODY)).toEqual({
      url: BODY.url,
      token: BODY.token,
      room: BODY.room,
      expiresAtMs: BODY.expires_at_ms,
    });
  });

  it("refuses a room that is not this session's", () => {
    const other = { ...BODY, room: "intake-00000000-0000-0000-0000-000000000000" };
    expect(() => parseTokenResponse(SESSION_ID, other)).toThrow(RoomTokenError);
  });

  it("refuses a non-wss signalling url", () => {
    expect(() => parseTokenResponse(SESSION_ID, { ...BODY, url: "ws://sfu" })).toThrow(
      RoomTokenError,
    );
  });

  it("refuses a response with no expiry rather than assuming one", () => {
    const { expires_at_ms: _dropped, ...withoutExpiry } = BODY;
    expect(() => parseTokenResponse(SESSION_ID, withoutExpiry)).toThrow(RoomTokenError);
  });

  it("refuses an empty token and a non-object body", () => {
    expect(() => parseTokenResponse(SESSION_ID, { ...BODY, token: "" })).toThrow(RoomTokenError);
    expect(() => parseTokenResponse(SESSION_ID, null)).toThrow(RoomTokenError);
    expect(() => parseTokenResponse(SESSION_ID, "token")).toThrow(RoomTokenError);
  });
});

describe("createTokenSource", () => {
  it("POSTs to the session's token route", async () => {
    const authedFetch = vi.fn(async () => response(BODY));
    const source = createTokenSource(authedFetch);

    const credentials = await source.fetch(SESSION_ID);

    expect(authedFetch).toHaveBeenCalledWith(`/v1/visits/${SESSION_ID}/voice-token`, {
      method: "POST",
    });
    expect(credentials.token).toBe(BODY.token);
  });

  it("refuses a session id that is not a canonical uuid", async () => {
    const authedFetch = vi.fn(async () => response(BODY));
    const source = createTokenSource(authedFetch);

    await expect(source.fetch("not-a-uuid")).rejects.toThrow(RoomTokenError);
    expect(authedFetch).not.toHaveBeenCalled();
  });

  it("fails with the status and never echoes the error body", async () => {
    const source = createTokenSource(async () =>
      response({ detail: "visit 0532 111 44 55 not found" }, false, 404),
    );

    await expect(source.fetch(SESSION_ID)).rejects.toThrow(/404/);
    await expect(source.fetch(SESSION_ID)).rejects.not.toThrow(/0532/);
  });

  it("mints nothing locally when the endpoint is unavailable", async () => {
    const source = createTokenSource(async () => {
      throw new Error("network down");
    });
    await expect(source.fetch(SESSION_ID)).rejects.toThrow();
  });
});

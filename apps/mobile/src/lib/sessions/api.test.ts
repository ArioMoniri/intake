/**
 * INT-583 — the device-sessions seam over an injected authed fetch.
 *
 * Every route, every error code the contract names, mapped to a typed result
 * the screen can render without reading a server sentence (02 §8.2: generic
 * errors). One rule is stricter than it looks: a list the app cannot fully
 * read is not shown at all. Dropping the one row that did not parse could
 * hide exactly the device the patient needs to see.
 */
import { describe, expect, it, vi } from "vitest";

import { createSessionsApi, type AuthedFetch } from "./api";

const HERE = "0123456789abcdef0123456789abcdef";
const THERE = "fedcba9876543210fedcba9876543210";

const LIST_BODY = {
  sessions: [
    { session_id: HERE, current: true, signed_in_at: "2026-10-30T09:12:00Z", push: true },
    { session_id: THERE, current: false, signed_in_at: "2026-10-29T18:40:00Z", push: false },
  ],
  sign_out_others_after: null,
  notices_on: true,
};

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

function api(response: Response) {
  const fetcher = vi.fn<AuthedFetch>(async () => response);
  return { fetcher, sessions: createSessionsApi(fetcher) };
}

function throwing() {
  const fetcher = vi.fn<AuthedFetch>(async () => {
    throw new TypeError("Network request failed");
  });
  return { fetcher, sessions: createSessionsApi(fetcher) };
}

describe("GET /v1/auth/sessions", () => {
  it("reads every device, in the app's own field names", async () => {
    const { fetcher, sessions } = api(answer(200, LIST_BODY));
    expect(await sessions.list()).toEqual({
      ok: true,
      list: {
        sessions: [
          { sessionId: HERE, current: true, signedInAt: "2026-10-30T09:12:00Z", push: true },
          { sessionId: THERE, current: false, signedInAt: "2026-10-29T18:40:00Z", push: false },
        ],
        signOutOthersAfter: null,
        noticesOn: true,
      },
    });
    expect(fetcher).toHaveBeenCalledWith("/v1/auth/sessions");
  });

  it("carries whether the server has a push channel wired", async () => {
    const { sessions } = api(answer(200, { ...LIST_BODY, notices_on: false }));
    const result = await sessions.list();
    expect(result.ok && result.list.noticesOn).toBe(false);
  });

  it("a list without notices_on is refused like any malformed list", async () => {
    const { notices_on: _dropped, ...withoutNotices } = LIST_BODY;
    expect(await api(answer(200, withoutNotices)).sessions.list()).toEqual({
      ok: false,
      error: "unreachable",
    });
  });

  it.each([["true"], [1], [null]])(
    "notices_on that is not a boolean (%j) is refused (near miss)",
    async (value) => {
      expect(
        await api(answer(200, { ...LIST_BODY, notices_on: value })).sessions.list(),
      ).toEqual({ ok: false, error: "unreachable" });
    },
  );

  it("carries the hold instant when the server sets one", async () => {
    const { sessions } = api(
      answer(200, { ...LIST_BODY, sign_out_others_after: "2026-10-31T09:12:00Z" }),
    );
    const result = await sessions.list();
    expect(result.ok && result.list.signOutOthersAfter).toBe("2026-10-31T09:12:00Z");
  });

  it.each([
    ["a session id that is not 32 lowercase hex", { session_id: HERE.toUpperCase() }],
    ["a 31-character session id", { session_id: HERE.slice(1) }],
    ["a missing current flag", { current: undefined }],
    ["a sign-in time that is not a date", { signed_in_at: "dün akşam" }],
    ["a push flag that is a string", { push: "true" }],
  ])("one unreadable row (%s) fails the whole list rather than hiding it", async (_why, patch) => {
    const rows = [LIST_BODY.sessions[0], { ...LIST_BODY.sessions[1], ...patch }];
    const { sessions } = api(answer(200, { ...LIST_BODY, sessions: rows }));
    expect(await sessions.list()).toEqual({ ok: false, error: "unreachable" });
  });

  it("a hold that is neither null nor an instant fails the list (near miss: missing key)", async () => {
    const { sign_out_others_after: _dropped, ...withoutHold } = LIST_BODY;
    expect(await api(answer(200, withoutHold)).sessions.list()).toEqual({
      ok: false,
      error: "unreachable",
    });
    expect(
      await api(answer(200, { ...LIST_BODY, sign_out_others_after: "soon" })).sessions.list(),
    ).toEqual({ ok: false, error: "unreachable" });
  });

  it("a body that is not a list is unreachable", async () => {
    expect(await api(answer(200, { sessions: "none" })).sessions.list()).toEqual({
      ok: false,
      error: "unreachable",
    });
    expect(await api(answer(200)).sessions.list()).toEqual({ ok: false, error: "unreachable" });
  });

  it("a refusal or a thrown fetch is unreachable, never an empty list", async () => {
    expect(await api(answer(500)).sessions.list()).toEqual({ ok: false, error: "unreachable" });
    expect(await throwing().sessions.list()).toEqual({ ok: false, error: "unreachable" });
  });
});

describe("DELETE /v1/auth/sessions/{session_id}", () => {
  it("204 signs that device out", async () => {
    const { fetcher, sessions } = api(answer(204));
    expect(await sessions.revoke(THERE)).toEqual({ ok: true });
    const [path, init] = fetcher.mock.calls[0];
    expect(path).toBe(`/v1/auth/sessions/${THERE}`);
    expect(init?.method).toBe("DELETE");
  });

  it("404 not_found is its own result", async () => {
    const { sessions } = api(answer(404, { error: "not_found" }));
    expect(await sessions.revoke(THERE)).toEqual({ ok: false, error: "not_found" });
  });

  it("a bare 404 without the code is not read as already signed out (near miss)", async () => {
    const { sessions } = api(answer(404, { detail: "Not Found" }));
    expect(await sessions.revoke(THERE)).toEqual({ ok: false, error: "unreachable" });
  });

  it("the code is read where the API puts it, at the top level (near miss: nested)", async () => {
    const { sessions } = api(answer(404, { detail: { error: "not_found" } }));
    expect(await sessions.revoke(THERE)).toEqual({ ok: false, error: "unreachable" });
  });

  it("403 session_too_new carries retry_after_s", async () => {
    const { sessions } = api(answer(403, { error: "session_too_new", retry_after_s: 3600 }));
    expect(await sessions.revoke(THERE)).toEqual({
      ok: false,
      error: "session_too_new",
      retryAfterS: 3600,
    });
  });

  it("403 session_too_new without a usable retry_after_s keeps the code, with no number", async () => {
    for (const retry of [undefined, -5, "3600", Number.NaN]) {
      const { sessions } = api(answer(403, { error: "session_too_new", retry_after_s: retry }));
      expect(await sessions.revoke(THERE)).toEqual({
        ok: false,
        error: "session_too_new",
        retryAfterS: null,
      });
    }
  });

  it("403 with another code is not the hold (near miss)", async () => {
    const { sessions } = api(answer(403, { error: "forbidden" }));
    expect(await sessions.revoke(THERE)).toEqual({ ok: false, error: "unreachable" });
  });

  it("an id that is not a session id never reaches the network", async () => {
    for (const id of ["../push-token", HERE.toUpperCase(), HERE.slice(1), `${HERE}0`, ""]) {
      const { fetcher, sessions } = api(answer(204));
      expect(await sessions.revoke(id)).toEqual({ ok: false, error: "not_found" });
      expect(fetcher).not.toHaveBeenCalled();
    }
  });

  it("a thrown fetch is unreachable", async () => {
    expect(await throwing().sessions.revoke(THERE)).toEqual({ ok: false, error: "unreachable" });
  });
});

describe("POST /v1/auth/sessions/sign-out-others", () => {
  it.each([false, true])("sends not_me=%s as JSON", async (notMe) => {
    const { fetcher, sessions } = api(answer(200, { signed_out: 2 }));
    await sessions.signOutOthers(notMe);
    const [path, init] = fetcher.mock.calls[0];
    expect(path).toBe("/v1/auth/sessions/sign-out-others");
    expect(init?.method).toBe("POST");
    expect(init?.headers).toEqual({ "Content-Type": "application/json" });
    expect(JSON.parse(String(init?.body))).toEqual({ not_me: notMe });
  });

  it("200 reports how many devices were signed out", async () => {
    expect(await api(answer(200, { signed_out: 2 })).sessions.signOutOthers(false)).toEqual({
      ok: true,
      signedOut: 2,
    });
    expect(await api(answer(200, { signed_out: 0 })).sessions.signOutOthers(true)).toEqual({
      ok: true,
      signedOut: 0,
    });
  });

  it("200 with an unreadable count still happened: the count is null, never invented", async () => {
    for (const count of [undefined, -1, 1.5, "2"]) {
      expect(await api(answer(200, { signed_out: count })).sessions.signOutOthers(false)).toEqual({
        ok: true,
        signedOut: null,
      });
    }
  });

  it("403 session_too_new carries retry_after_s", async () => {
    const { sessions } = api(answer(403, { error: "session_too_new", retry_after_s: 120 }));
    expect(await sessions.signOutOthers(true)).toEqual({
      ok: false,
      error: "session_too_new",
      retryAfterS: 120,
    });
  });

  it("anything else, or a thrown fetch, is unreachable", async () => {
    expect(await api(answer(500)).sessions.signOutOthers(true)).toEqual({
      ok: false,
      error: "unreachable",
    });
    expect(await throwing().sessions.signOutOthers(true)).toEqual({
      ok: false,
      error: "unreachable",
    });
  });
});

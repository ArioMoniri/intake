/**
 * INT-139 — the working copy behind the share centre, and the two properties
 * the acceptance line turns on.
 *
 * **"revocation cascades to tokens within 1 min"** is a claim about the
 * server; what the client owes it is *no deferral of its own*. Every way a
 * client can add latency to a revocation is a way to break that clause
 * without touching the server, and each one is asserted here: no cached copy
 * that outlives the call, no optimistic write that makes the screen agree
 * before the row does, no poll interval the patient has to wait out, and no
 * second round trip between the tap and the authoritative answer. The
 * interval itself is measured in docs/evidence/INT-139.md against a named
 * corpus, because a latency figure is a measurement and never a property of
 * the product (invariant 20).
 *
 * **A withdrawal of the share purpose cannot lock the revoke button.**
 * INT-150 §6 moved `share:previsit_note` to `conditional` and declared
 * revoke and the access log under `core` alone for exactly this reason. The
 * client half of that is stronger than "revoke survives": with the issuing
 * surface deliberately absent, *every* route this app calls is core-declared,
 * so there is nothing here for a withdrawal to take away. The transport in
 * `refusesTheSharePurpose` refuses anything the server enforces the share
 * scope on, and the store still lists, revokes and reads the log.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { loadShareCentre, resetShares, revokeShare, sharesSnapshot } from "./store";

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

const LIVE = {
  link_id: LINK,
  recipient: "Kardiyoloji",
  expires_at: "2026-09-06T21:00:00Z",
  view_limit: 5,
  views_used: 1,
  revoked: false,
  spent: false,
};
const STOPPED = { ...LIVE, revoked: true, spent: true };

const ENTRY = {
  seq: 4,
  occurred_at_utc: "2026-09-03T11:24:05Z",
  category: "record_viewed",
  accessor_role: "clinician",
  resource_ref: `doctor_link:${LINK}`,
  entry_hash: "a".repeat(64),
};

function ok(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body } as unknown as Response;
}

function refused(status: number, error: string): Response {
  return {
    ok: false,
    status,
    json: async () => ({ error, scope: "share:previsit_note" }),
  } as unknown as Response;
}

/** The happy path: every route this client calls is declared under `core`. */
function serving(links: unknown[], log: unknown[] = [ENTRY]): void {
  mocks.authedFetch.mockImplementation(async (path: string, init?: RequestInit) => {
    if (path.endsWith("/access-log")) {
      return ok(log);
    }
    if (path.endsWith("/revoke") && init?.method === "POST") {
      return ok(STOPPED);
    }
    return ok(links);
  });
}

/**
 * A server on which the patient has withdrawn `share:previsit_note`. Anything
 * the share purpose gates answers 403 `consent_required`; the three
 * core-declared routes answer normally. If this app ever grew a call that
 * needs the share purpose, this transport is what would catch it.
 */
function refusesTheSharePurpose(): void {
  mocks.authedFetch.mockImplementation(async (path: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const gated = path.endsWith("/otp") || (method === "POST" && path.endsWith("/doctor-links"));
    if (gated) {
      return refused(403, "consent_required");
    }
    if (path.endsWith("/access-log")) {
      return ok([ENTRY]);
    }
    if (path.endsWith("/revoke")) {
      return ok(STOPPED);
    }
    return ok([LIVE]);
  });
}

afterEach(() => {
  resetShares();
  mocks.authedFetch.mockReset();
});

describe("loading the share centre", () => {
  it("shows the grants and the log the server returned", async () => {
    serving([LIVE]);
    await loadShareCentre(VISIT);
    const state = sharesSnapshot();
    expect(state.loaded).toBe(true);
    expect(state.links.map((l) => l.id)).toEqual([LINK]);
    expect(state.log.map((e) => e.role)).toEqual(["clinician"]);
    expect(state.unreachable).toBe(false);
  });

  it("claims nothing when the server cannot be reached", async () => {
    mocks.authedFetch.mockRejectedValue(new mocks.AuthApiError("network"));
    await loadShareCentre(VISIT);
    const state = sharesSnapshot();
    // Not "no shares" — "we do not know". An empty list drawn from a failed
    // read would tell a patient nobody has access to their record.
    expect(state.loaded).toBe(false);
    expect(state.unreachable).toBe(true);
    expect(state.links).toEqual([]);
  });

  it("reads a different visit's centre from scratch rather than merging", async () => {
    serving([LIVE]);
    await loadShareCentre(VISIT);
    serving([]);
    await loadShareCentre("0000ffff-0000-4000-8000-0000000000bb");
    expect(sharesSnapshot().links).toEqual([]);
  });
});

describe("revoking", () => {
  it("takes the row the server returned, and shows nothing before it", async () => {
    serving([LIVE]);
    await loadShareCentre(VISIT);
    let resolveRevoke: ((value: Response) => void) | null = null;
    mocks.authedFetch.mockImplementation(
      (path: string) =>
        new Promise<Response>((resolve) => {
          if (path.endsWith("/revoke")) {
            resolveRevoke = resolve;
            return;
          }
          resolve(ok([STOPPED]));
        }),
    );
    const pending = revokeShare(VISIT, LINK);
    // The optimistic write this test exists to forbid: while the call is in
    // flight the grant is still shown exactly as the server last described
    // it. A screen that says "stopped" before the row does is a screen that
    // can say it when the row never changed.
    expect(sharesSnapshot().links[0].revoked).toBe(false);
    resolveRevoke!(ok(STOPPED));
    await pending;
    expect(sharesSnapshot().links[0].revoked).toBe(true);
  });

  it("adds no round trip of its own between the tap and the new row", async () => {
    serving([LIVE]);
    await loadShareCentre(VISIT);
    mocks.authedFetch.mockClear();
    await revokeShare(VISIT, LINK);
    // One call. A re-list afterwards would be a second network wait between
    // the patient's tap and the screen telling them it worked, and the
    // revoke response already IS the authoritative row.
    expect(mocks.authedFetch).toHaveBeenCalledTimes(1);
    expect(mocks.authedFetch.mock.calls[0][0]).toContain("/revoke");
  });

  it("says the request did not land rather than showing a share as stopped", async () => {
    serving([LIVE]);
    await loadShareCentre(VISIT);
    mocks.authedFetch.mockRejectedValue(new mocks.AuthApiError("network"));
    await revokeShare(VISIT, LINK);
    expect(sharesSnapshot().links[0].revoked).toBe(false);
    expect(sharesSnapshot().unsent).toBe(true);
  });

  it("clears the unsent flag once a revocation does land", async () => {
    serving([LIVE]);
    await loadShareCentre(VISIT);
    mocks.authedFetch.mockRejectedValue(new mocks.AuthApiError("network"));
    await revokeShare(VISIT, LINK);
    expect(sharesSnapshot().unsent).toBe(true);
    serving([STOPPED]);
    await revokeShare(VISIT, LINK);
    expect(sharesSnapshot().unsent).toBe(false);
    expect(sharesSnapshot().links[0].revoked).toBe(true);
  });

  it("answers true only when the server's own row came back (INT-340)", async () => {
    // The screen's success haptic waits for this answer, never for the tap.
    serving([LIVE]);
    await loadShareCentre(VISIT);
    mocks.authedFetch.mockRejectedValue(new mocks.AuthApiError("network"));
    expect(await revokeShare(VISIT, LINK)).toBe(false);
    serving([STOPPED]);
    expect(await revokeShare(VISIT, LINK)).toBe(true);
  });

  it("is idempotent on the client too: revoking twice leaves one row", async () => {
    serving([LIVE]);
    await loadShareCentre(VISIT);
    await revokeShare(VISIT, LINK);
    await revokeShare(VISIT, LINK);
    expect(sharesSnapshot().links).toHaveLength(1);
    expect(sharesSnapshot().links[0].revoked).toBe(true);
  });
});

describe("a withdrawal of the share purpose cannot lock the revoke path", () => {
  it("still lists, still revokes and still reads the log", async () => {
    refusesTheSharePurpose();
    await loadShareCentre(VISIT);
    expect(sharesSnapshot().links).toHaveLength(1);
    expect(sharesSnapshot().log).toHaveLength(1);
    await revokeShare(VISIT, LINK);
    expect(sharesSnapshot().links[0].revoked).toBe(true);
    expect(sharesSnapshot().unsent).toBe(false);
  });

  it("never asks the server for anything the share purpose gates", async () => {
    refusesTheSharePurpose();
    await loadShareCentre(VISIT);
    await revokeShare(VISIT, LINK);
    for (const [path, init] of mocks.authedFetch.mock.calls) {
      const method = (init as RequestInit | undefined)?.method ?? "GET";
      expect(path, "the OTP mint enforces share:previsit_note").not.toContain("/otp");
      expect(
        method === "POST" && String(path).endsWith("/doctor-links"),
        "issuing a link enforces share:previsit_note",
      ).toBe(false);
    }
  });
});

describe("nothing survives the session", () => {
  it("drops the whole working copy on reset — another patient's grants are not ours", async () => {
    serving([LIVE]);
    await loadShareCentre(VISIT);
    resetShares();
    const state = sharesSnapshot();
    expect(state.links).toEqual([]);
    expect(state.log).toEqual([]);
    expect(state.loaded).toBe(false);
  });
});

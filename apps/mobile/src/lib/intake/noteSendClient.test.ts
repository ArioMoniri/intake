/**
 * INT-510 — the send's transport, over the real records resolver and a mocked
 * authedFetch: the composition the session runs when the patient taps Gönder.
 *
 * The order on the wire is the point: list the patient's server visits, create
 * the one this local visit stands for when it is missing, then PUT the note to
 * THAT id. The local id (`v-local-…`) is an address only this phone knows, and
 * the defect this issue closes is exactly that id reaching `/v1/visits/*`.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { emptyNoteState, noteReducer, type NoteState } from "./note";
import { deliverVisitNote, PUT_TIMEOUT_MS } from "./noteSendClient";

const mocks = vi.hoisted(() => {
  class AuthApiError extends Error {
    readonly kind: string;
    readonly retryAfterS: number | null = null;
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

// records/api reads picked files through expo-file-system; the send never does.
vi.mock("expo-file-system", () => ({ File: class {} }));

const LOCAL_ID = "v-local-1";
const SERVER_ID = "6b0f2c1e-4d7a-4a51-9c3e-0d1f2a3b4c5d";
const VISIT = {
  hospital: "Ankara Şehir Hastanesi",
  department: "İç Hastalıkları",
  date: "2026-09-03",
  branchId: null,
  visitType: null,
};
const PATIENT = { kind: "otp" as const, carriedFacts: [] };

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status });
}

function note(): NoteState {
  const answered = noteReducer(emptyNoteState(), {
    type: "answer",
    questionId: "complaint",
    values: ["pain"],
  });
  return noteReducer(answered, { type: "send" });
}

/** A server with no visit yet, that creates one and accepts the note. */
function freshServer(put: () => Response): void {
  mocks.authedFetch.mockImplementation(async (path: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    if (path === "/v1/visits" && method === "GET") {
      return json(200, []);
    }
    if (path === "/v1/visits" && method === "POST") {
      return json(201, { id: SERVER_ID, ...VISIT });
    }
    if (path === `/v1/visits/${SERVER_ID}/note` && method === "PUT") {
      return put();
    }
    return json(404, { error: "not_found" });
  });
}

function calls(): { path: string; method: string; body: unknown }[] {
  return mocks.authedFetch.mock.calls.map(([path, init]) => ({
    path: String(path),
    method: (init as RequestInit | undefined)?.method ?? "GET",
    body:
      typeof (init as RequestInit | undefined)?.body === "string"
        ? JSON.parse((init as RequestInit).body as string)
        : null,
  }));
}

afterEach(() => {
  mocks.authedFetch.mockReset();
});

describe("a send resolves the server visit, then PUTs the note to it", () => {
  it("creates the missing server visit and sends to its id", async () => {
    freshServer(() => json(200, { visit_id: SERVER_ID, status: "sent" }));
    const outcome = await deliverVisitNote({
      note: note(),
      account: PATIENT,
      visit: VISIT,
      knownServerVisitId: null,
    });
    expect(outcome).toEqual({ kind: "delivered", serverVisitId: SERVER_ID });
    expect(calls().map((c) => `${c.method} ${c.path}`)).toEqual([
      "GET /v1/visits",
      "POST /v1/visits",
      `PUT /v1/visits/${SERVER_ID}/note`,
    ]);
    const put = calls()[2].body as { status: string; sections: { id: string }[] };
    expect(put.status).toBe("sent");
    expect(put.sections.map((s) => s.id)).toEqual(["chief_complaint"]);
  });

  it("never puts the local id on the wire", async () => {
    freshServer(() => json(200, { visit_id: SERVER_ID, status: "sent" }));
    await deliverVisitNote({
      note: note(),
      account: PATIENT,
      visit: VISIT,
      knownServerVisitId: null,
    });
    for (const call of calls()) {
      expect(call.path).not.toContain(LOCAL_ID);
    }
  });

  it("with the id already held, goes straight to the PUT", async () => {
    freshServer(() => json(200, { visit_id: SERVER_ID, status: "sent" }));
    await deliverVisitNote({
      note: note(),
      account: PATIENT,
      visit: VISIT,
      knownServerVisitId: SERVER_ID,
    });
    expect(calls().map((c) => c.method)).toEqual(["PUT"]);
  });

  it("bounds the PUT, so a stalled request becomes a queued send", () => {
    expect(PUT_TIMEOUT_MS).toBeGreaterThan(0);
    freshServer(() => json(200, { visit_id: SERVER_ID, status: "sent" }));
    return deliverVisitNote({
      note: note(),
      account: PATIENT,
      visit: VISIT,
      knownServerVisitId: SERVER_ID,
    }).then(() => {
      const init = mocks.authedFetch.mock.calls[0][1] as RequestInit;
      expect(init.signal).toBeInstanceOf(AbortSignal);
    });
  });
});

describe("what the server says is what the phone says", () => {
  it("a refused share consent comes back as a consent refusal", async () => {
    freshServer(() => json(403, { error: "consent_required", scope: "share:previsit_note" }));
    expect(
      await deliverVisitNote({
        note: note(),
        account: PATIENT,
        visit: VISIT,
        knownServerVisitId: null,
      }),
    ).toEqual({ kind: "refused", reason: "consent", serverVisitId: SERVER_ID });
  });

  it("a consent refused on the visit itself is worded as consent, and nothing is PUT", async () => {
    mocks.authedFetch.mockImplementation(async (path: string, init?: RequestInit) => {
      if ((init?.method ?? "GET") === "POST") {
        return json(403, { error: "consent_required", scope: "core" });
      }
      return json(200, []);
    });
    expect(
      await deliverVisitNote({
        note: note(),
        account: PATIENT,
        visit: VISIT,
        knownServerVisitId: null,
      }),
    ).toEqual({ kind: "refused", reason: "consent", serverVisitId: null });
    expect(calls().map((c) => c.method)).toEqual(["GET", "POST"]);
  });

  it("a dropped connection on the PUT is a queued send", async () => {
    freshServer(() => {
      throw new TypeError("Network request failed");
    });
    expect(
      await deliverVisitNote({
        note: note(),
        account: PATIENT,
        visit: VISIT,
        knownServerVisitId: null,
      }),
    ).toEqual({ kind: "queued", serverVisitId: SERVER_ID });
  });

  it("no network at all while resolving is a queued send with no id", async () => {
    mocks.authedFetch.mockRejectedValue(new mocks.AuthApiError("network"));
    expect(
      await deliverVisitNote({
        note: note(),
        account: PATIENT,
        visit: VISIT,
        knownServerVisitId: null,
      }),
    ).toEqual({ kind: "queued", serverVisitId: null });
  });

  it("no session is a refusal the patient can act on", async () => {
    mocks.authedFetch.mockRejectedValue(new mocks.AuthApiError("session"));
    expect(
      await deliverVisitNote({
        note: note(),
        account: PATIENT,
        visit: VISIT,
        knownServerVisitId: null,
      }),
    ).toEqual({ kind: "refused", reason: "session", serverVisitId: null });
  });

  it("a note for a visit the session no longer lists is not sent anywhere", async () => {
    expect(
      await deliverVisitNote({
        note: note(),
        account: PATIENT,
        visit: null,
        knownServerVisitId: null,
      }),
    ).toEqual({ kind: "refused", reason: "failed", serverVisitId: null });
    expect(mocks.authedFetch).not.toHaveBeenCalled();
  });
});

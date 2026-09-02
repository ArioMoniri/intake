/**
 * INT-140 — the DSAR seam and the working copy behind "Verileriniz".
 *
 * Three properties carry the whole feature, and each is a way the screen
 * could lie to a patient exercising KVKK m.11:
 *
 * 1. **An unreachable server never becomes a filed request.** The obligation
 *    exists the moment the patient asks, so a request that did not reach the
 *    controller is reported as unsent, never shown as filed.
 * 2. **Withdrawing an erasure replaces the row it withdrew**, so the screen
 *    cannot show a cancelled deletion and a live one at the same time.
 * 3. **The export DOCUMENT is not fetched.** `GET /v1/me/dsar/export/{id}`
 *    marks the m.13 obligation answered at the moment of delivery, and this
 *    app has nothing to deliver: `docs/legal/strings.yaml` does not exist yet
 *    (INT-210), so the server cannot render the document at all. Calling it
 *    would record an answer the patient never received. The absence is the
 *    control, so it is asserted rather than assumed.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchDsarRequests, fileErasureRequest, fileExportRequest } from "./api";
import {
  dsarSnapshot,
  fileErasure,
  fileExport,
  loadDsarRequests,
  resetDsar,
  withdrawErasure,
} from "./store";

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

const EXPORT_ROW = {
  request_id: "11111111-1111-4111-8111-111111111111",
  kind: "export",
  status: "received",
  received_at: "2026-09-01T08:00:00Z",
  due_at: "2026-10-01T08:00:00Z",
  grace_ends_at: null,
  completed_at: null,
  overdue: false,
};

const ERASURE_ROW = {
  ...EXPORT_ROW,
  request_id: "22222222-2222-4222-8222-222222222222",
  kind: "delete",
  status: "scheduled",
  grace_ends_at: "2026-10-01T08:00:00Z",
};

function ok(body: unknown, status = 200): Response {
  return { ok: true, status, json: async () => body } as unknown as Response;
}

function refused(status: number): Response {
  return { ok: false, status, json: async () => ({ error: "nope" }) } as unknown as Response;
}

afterEach(() => {
  resetDsar();
  mocks.authedFetch.mockReset();
});

describe("the seam", () => {
  it("files an access request against the DSAR export route", async () => {
    mocks.authedFetch.mockResolvedValue(ok(EXPORT_ROW, 201));
    const filed = await fileExportRequest();
    expect(mocks.authedFetch).toHaveBeenCalledWith(
      "/v1/me/dsar/export",
      expect.objectContaining({ method: "POST" }),
    );
    expect(filed?.kind).toBe("export");
  });

  it("files an erasure and reports whether live shares were cancelled by it", async () => {
    mocks.authedFetch.mockResolvedValue(ok({ ...ERASURE_ROW, shares_cancelled: 2 }, 201));
    const filed = await fileErasureRequest();
    expect(mocks.authedFetch).toHaveBeenCalledWith(
      "/v1/me/dsar/delete",
      expect.objectContaining({ method: "POST" }),
    );
    expect(filed?.sharesCancelled).toBe(true);
  });

  it("reports no cancelled share rather than a count — no numeral reaches the copy", async () => {
    mocks.authedFetch.mockResolvedValue(ok({ ...ERASURE_ROW, shares_cancelled: 0 }, 201));
    expect((await fileErasureRequest())?.sharesCancelled).toBe(false);
  });

  it("resolves to null on a refusal and on an unreachable server", async () => {
    mocks.authedFetch.mockResolvedValue(refused(503));
    expect(await fileExportRequest()).toBeNull();
    mocks.authedFetch.mockRejectedValue(new mocks.AuthApiError("network"));
    expect(await fetchDsarRequests()).toBeNull();
  });

  it("never asks for the export document", async () => {
    mocks.authedFetch.mockResolvedValue(ok([EXPORT_ROW]));
    await fetchDsarRequests();
    await fileExportRequest();
    for (const [path] of mocks.authedFetch.mock.calls) {
      expect(path).not.toMatch(/\/v1\/me\/dsar\/export\/[^/]+$/);
    }
  });
});

describe("the working copy", () => {
  it("starts empty and unloaded — nothing is claimed before the server answers", () => {
    expect(dsarSnapshot()).toEqual({
      requests: [],
      loaded: false,
      unsent: false,
      sharesCancelled: false,
    });
  });

  it("loads the patient's own tracker", async () => {
    mocks.authedFetch.mockResolvedValue(ok([EXPORT_ROW, ERASURE_ROW]));
    await loadDsarRequests("patient-a");
    expect(mocks.authedFetch).toHaveBeenCalledWith("/v1/me/dsar/requests");
    expect(dsarSnapshot().loaded).toBe(true);
    expect(dsarSnapshot().requests).toHaveLength(2);
  });

  it("clears another patient's tracker before the server answers for this one", async () => {
    mocks.authedFetch.mockResolvedValue(ok([EXPORT_ROW]));
    await loadDsarRequests("patient-a");
    mocks.authedFetch.mockResolvedValue(refused(503));
    await loadDsarRequests("patient-b");
    expect(dsarSnapshot().requests).toEqual([]);
    expect(dsarSnapshot().loaded).toBe(false);
  });

  it("stays unloaded when the tracker is unreachable, and claims nothing", async () => {
    mocks.authedFetch.mockRejectedValue(new mocks.AuthApiError("network"));
    await loadDsarRequests("patient-a");
    expect(dsarSnapshot()).toEqual({
      requests: [],
      loaded: false,
      unsent: false,
      sharesCancelled: false,
    });
  });

  it("adds a filed request to the tracker", async () => {
    mocks.authedFetch.mockResolvedValue(ok(EXPORT_ROW, 201));
    await fileExport();
    expect(dsarSnapshot().requests.map((r) => r.id)).toEqual([EXPORT_ROW.request_id]);
    expect(dsarSnapshot().unsent).toBe(false);
  });

  it("does NOT show a request the controller never received", async () => {
    mocks.authedFetch.mockResolvedValue(refused(503));
    await fileExport();
    expect(dsarSnapshot().requests).toEqual([]);
    expect(dsarSnapshot().unsent).toBe(true);
  });

  it("carries the cancelled-share fact off an erasure filing", async () => {
    mocks.authedFetch.mockResolvedValue(ok({ ...ERASURE_ROW, shares_cancelled: 1 }, 201));
    await fileErasure();
    expect(dsarSnapshot().sharesCancelled).toBe(true);
  });

  it("replaces the erasure row when the withdrawal lands, never duplicating it", async () => {
    mocks.authedFetch.mockResolvedValue(ok({ ...ERASURE_ROW, shares_cancelled: 0 }, 201));
    await fileErasure();
    mocks.authedFetch.mockResolvedValue(
      ok({ ...ERASURE_ROW, status: "cancelled", completed_at: "2026-09-03T09:00:00Z" }),
    );
    await withdrawErasure(ERASURE_ROW.request_id);
    expect(mocks.authedFetch).toHaveBeenLastCalledWith(
      `/v1/me/dsar/delete/${ERASURE_ROW.request_id}`,
      expect.objectContaining({ method: "DELETE" }),
    );
    expect(dsarSnapshot().requests).toHaveLength(1);
    expect(dsarSnapshot().requests[0].status).toBe("cancelled");
  });

  it("leaves the erasure standing when the withdrawal does not reach the server", async () => {
    mocks.authedFetch.mockResolvedValue(ok({ ...ERASURE_ROW, shares_cancelled: 0 }, 201));
    await fileErasure();
    mocks.authedFetch.mockResolvedValue(refused(409));
    await withdrawErasure(ERASURE_ROW.request_id);
    expect(dsarSnapshot().requests[0].status).toBe("scheduled");
    expect(dsarSnapshot().unsent).toBe(true);
  });
});

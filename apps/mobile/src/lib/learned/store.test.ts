/**
 * INT-140 — the ledger seam and the working copy behind the learned screen.
 *
 * The rule the whole file exists to pin: **a record fact is never removed
 * from the screen until the record has removed it.** An optimistic deletion
 * that fails leaves the patient believing something is gone while it is not,
 * which is worse than a visible failure — so a write that does not land
 * changes nothing and says so.
 *
 * The mirror image is the device-held fact, seeded from the synthetic
 * account: it exists in exactly one place, so removing it here removes it,
 * and no server call is made for a fact no server holds.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CarriedFact } from "../intake/carriedFacts";
import { fetchLearnedFacts, forgetRecordFact, pushFactShared } from "./api";
import {
  forgetFact,
  learnedSnapshot,
  loadLearnedLedger,
  resetLearnedLedger,
  seedLearnedLedger,
  setFactShared,
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

const ROW = {
  key: "ilaclar.metoprolol",
  value: "Metoprolol (düzenli kullanım)",
  source: "confirmed_intake_extraction",
  source_ref: "sentetik-onay-karti",
  confirmed_by: "patient",
  confirmed_at: "2026-05-12T08:00:00Z",
  confidence: 0.9,
  shared: true,
  needs_reconfirmation: false,
};

const CARRIED: CarriedFact = {
  id: "cf-1",
  kind: "medication",
  text: "Metoprolol (düzenli kullanım)",
  source: "clinician_accepted_note",
  assertedBy: { role: "clinician" },
  assertedAt: "2026-05-12",
  sourceVisitId: "v-0",
};

function ok(body: unknown, status = 200): Response {
  return { ok: true, status, json: async () => body } as unknown as Response;
}

function refused(status: number): Response {
  return { ok: false, status, json: async () => ({}) } as unknown as Response;
}

afterEach(() => {
  resetLearnedLedger();
  mocks.authedFetch.mockReset();
});

describe("the seam", () => {
  it("reads the patient's own overlay", async () => {
    mocks.authedFetch.mockResolvedValue(ok({ version: 1, facts: [ROW] }));
    const facts = await fetchLearnedFacts();
    expect(mocks.authedFetch).toHaveBeenCalledWith("/v1/me/learned");
    expect(facts?.[0].id).toBe("ilaclar.metoprolol");
  });

  it("re-scopes one field by key, per files/09 §3", async () => {
    mocks.authedFetch.mockResolvedValue(ok({ ...ROW, shared: false }));
    expect(await pushFactShared("ilaclar.metoprolol", false)).toBe(true);
    expect(mocks.authedFetch).toHaveBeenCalledWith(
      "/v1/me/learned/ilaclar.metoprolol",
      expect.objectContaining({ method: "PATCH", body: JSON.stringify({ shared: false }) }),
    );
  });

  it("escapes a key rather than pasting it into the path", async () => {
    mocks.authedFetch.mockResolvedValue(ok({}));
    await pushFactShared("oyku/belirti var", true);
    expect(mocks.authedFetch).toHaveBeenCalledWith(
      "/v1/me/learned/oyku%2Fbelirti%20var",
      expect.anything(),
    );
  });

  it("treats a 204 and a 404 alike: the record does not hold the fact", async () => {
    mocks.authedFetch.mockResolvedValue({ ok: true, status: 204 } as Response);
    expect(await forgetRecordFact("k")).toBe(true);
    mocks.authedFetch.mockResolvedValue(refused(404));
    expect(await forgetRecordFact("k")).toBe(true);
  });

  it("reports a refusal and an unreachable server as not-done", async () => {
    mocks.authedFetch.mockResolvedValue(refused(403));
    expect(await forgetRecordFact("k")).toBe(false);
    mocks.authedFetch.mockRejectedValue(new mocks.AuthApiError("network"));
    expect(await fetchLearnedFacts()).toBeNull();
    expect(await pushFactShared("k", true)).toBe(false);
  });
});

describe("the working copy", () => {
  it("starts empty and unloaded", () => {
    expect(learnedSnapshot()).toEqual({ facts: [], loaded: false, unsaved: false });
  });

  it("seeds the device-held facts of one account, and clears them for another", () => {
    seedLearnedLedger("ayse", [CARRIED]);
    expect(learnedSnapshot().facts.map((f) => f.origin)).toEqual(["device"]);
    seedLearnedLedger("mehmet", []);
    expect(learnedSnapshot().facts).toEqual([]);
  });

  it("keeps device-held facts beside the record's own", async () => {
    seedLearnedLedger("ayse", [CARRIED]);
    mocks.authedFetch.mockResolvedValue(ok({ version: 1, facts: [ROW] }));
    await loadLearnedLedger();
    expect(
      learnedSnapshot()
        .facts.map((f) => f.origin)
        .sort(),
    ).toEqual(["device", "record"]);
    expect(learnedSnapshot().loaded).toBe(true);
  });

  it("replaces the record's facts on a reload rather than appending them", async () => {
    mocks.authedFetch.mockResolvedValue(ok({ version: 1, facts: [ROW] }));
    await loadLearnedLedger();
    await loadLearnedLedger();
    expect(learnedSnapshot().facts).toHaveLength(1);
  });

  it("claims nothing when the overlay is unreachable", async () => {
    mocks.authedFetch.mockRejectedValue(new mocks.AuthApiError("network"));
    await loadLearnedLedger();
    expect(learnedSnapshot()).toEqual({ facts: [], loaded: false, unsaved: false });
  });
});

describe("deleting a fact", () => {
  it("removes a record fact only once the record has removed it", async () => {
    mocks.authedFetch.mockResolvedValue(ok({ version: 1, facts: [ROW] }));
    await loadLearnedLedger();
    mocks.authedFetch.mockResolvedValue({ ok: true, status: 204 } as Response);
    await forgetFact("ilaclar.metoprolol");
    expect(mocks.authedFetch).toHaveBeenLastCalledWith(
      "/v1/me/learned/ilaclar.metoprolol",
      expect.objectContaining({ method: "DELETE" }),
    );
    expect(learnedSnapshot().facts).toEqual([]);
    expect(learnedSnapshot().unsaved).toBe(false);
  });

  it("keeps a record fact on screen when the deletion did not land, and says so", async () => {
    mocks.authedFetch.mockResolvedValue(ok({ version: 1, facts: [ROW] }));
    await loadLearnedLedger();
    mocks.authedFetch.mockResolvedValue(refused(503));
    await forgetFact("ilaclar.metoprolol");
    expect(learnedSnapshot().facts).toHaveLength(1);
    expect(learnedSnapshot().unsaved).toBe(true);
  });

  it("removes a device-held fact without asking any server", async () => {
    seedLearnedLedger("ayse", [CARRIED]);
    await forgetFact("cf-1");
    expect(mocks.authedFetch).not.toHaveBeenCalled();
    expect(learnedSnapshot().facts).toEqual([]);
  });
});

describe("re-scoping a fact", () => {
  it("turns the scope only once the record has turned it", async () => {
    mocks.authedFetch.mockResolvedValue(ok({ version: 1, facts: [ROW] }));
    await loadLearnedLedger();
    mocks.authedFetch.mockResolvedValue(ok({ ...ROW, shared: false }));
    await setFactShared("ilaclar.metoprolol", false);
    expect(learnedSnapshot().facts[0].shared).toBe(false);
  });

  it("leaves the scope as the record has it when the change did not land", async () => {
    mocks.authedFetch.mockResolvedValue(ok({ version: 1, facts: [ROW] }));
    await loadLearnedLedger();
    mocks.authedFetch.mockResolvedValue(refused(503));
    await setFactShared("ilaclar.metoprolol", false);
    expect(learnedSnapshot().facts[0].shared).toBe(true);
    expect(learnedSnapshot().unsaved).toBe(true);
  });

  it("has no scope to turn on a device-held fact, and asks no server for one", async () => {
    seedLearnedLedger("ayse", [CARRIED]);
    await setFactShared("cf-1", false);
    expect(mocks.authedFetch).not.toHaveBeenCalled();
    expect(learnedSnapshot().facts[0].shared).toBeNull();
  });
});

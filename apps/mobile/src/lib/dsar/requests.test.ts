/**
 * INT-140 — the KVKK m.11/m.13 request model the "Verileriniz" screen reads.
 *
 * The server (INT-037) is the enforcer; this module is a reader. So the
 * properties worth pinning are the ones a reader can get wrong: admitting a
 * status or a kind the server never sends, claiming a withdrawal is still
 * possible after the grace has run out, and losing the overdue fact that is
 * the whole point of the m.13 clock.
 */
import { describe, expect, it } from "vitest";

import {
  canWithdrawErasure,
  formatDsarDay,
  kindLabelKey,
  latestRequest,
  parseRequest,
  parseRequests,
  scheduledErasure,
  statusLabelKey,
} from "./requests";

const NOW = "2026-09-03T09:00:00Z";

function row(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    request_id: "11111111-1111-4111-8111-111111111111",
    kind: "export",
    status: "received",
    received_at: "2026-09-01T08:00:00Z",
    due_at: "2026-10-01T08:00:00Z",
    grace_ends_at: null,
    completed_at: null,
    overdue: false,
    ...overrides,
  };
}

describe("parseRequest", () => {
  it("reads the row the DSAR router sends", () => {
    expect(parseRequest(row())).toEqual({
      id: "11111111-1111-4111-8111-111111111111",
      kind: "export",
      status: "received",
      receivedAt: "2026-09-01T08:00:00Z",
      dueAt: "2026-10-01T08:00:00Z",
      graceEndsAt: null,
      completedAt: null,
      overdue: false,
    });
  });

  it("keeps the grace and completion instants when the server sends them", () => {
    const parsed = parseRequest(
      row({
        kind: "delete",
        status: "scheduled",
        grace_ends_at: "2026-10-01T08:00:00Z",
        completed_at: "2026-09-02T08:00:00Z",
      }),
    );
    expect(parsed?.graceEndsAt).toBe("2026-10-01T08:00:00Z");
    expect(parsed?.completedAt).toBe("2026-09-02T08:00:00Z");
  });

  it.each(["kind", "status"])("refuses a row whose %s is outside the closed set", (field) => {
    expect(parseRequest(row({ [field]: "anonymise" }))).toBeNull();
  });

  it.each(["request_id", "received_at", "due_at"])("refuses a row missing %s", (field) => {
    expect(parseRequest(row({ [field]: null }))).toBeNull();
  });

  it("refuses anything that is not an object", () => {
    expect(parseRequest("received")).toBeNull();
    expect(parseRequest(null)).toBeNull();
  });

  it("never invents the overdue fact: an unreadable flag is a refusal, not a false", () => {
    expect(parseRequest(row({ overdue: "yes" }))).toBeNull();
  });
});

describe("parseRequests", () => {
  it("drops rows it cannot read rather than guessing them", () => {
    const parsed = parseRequests([row(), row({ status: "burned" }), "x"]);
    expect(parsed).toHaveLength(1);
  });

  it("orders newest first — the tracker reads down from the latest request", () => {
    const parsed = parseRequests([
      row({ request_id: "a", received_at: "2026-08-01T08:00:00Z" }),
      row({ request_id: "b", received_at: "2026-09-01T08:00:00Z" }),
    ]);
    expect(parsed.map((r) => r.id)).toEqual(["b", "a"]);
  });

  it("reads a non-array as no requests at all", () => {
    expect(parseRequests({ requests: [] })).toEqual([]);
  });
});

describe("the erasure grace", () => {
  const scheduled = parseRequest(
    row({ kind: "delete", status: "scheduled", grace_ends_at: "2026-10-01T08:00:00Z" }),
  )!;

  it("is withdrawable while the grace is running", () => {
    expect(canWithdrawErasure(scheduled, NOW)).toBe(true);
  });

  it("is not withdrawable once the grace has elapsed", () => {
    expect(canWithdrawErasure(scheduled, "2026-10-02T08:00:00Z")).toBe(false);
  });

  it("is not withdrawable once the request left the scheduled state", () => {
    expect(canWithdrawErasure({ ...scheduled, status: "completed" }, NOW)).toBe(false);
  });

  it("is not withdrawable without a grace instant — absence is never permission", () => {
    expect(canWithdrawErasure({ ...scheduled, graceEndsAt: null }, NOW)).toBe(false);
  });

  it("finds the live erasure, and only an erasure", () => {
    const requests = [parseRequest(row())!, scheduled];
    expect(scheduledErasure(requests, NOW)?.kind).toBe("delete");
    expect(scheduledErasure([parseRequest(row())!], NOW)).toBeNull();
  });

  it("reports no live erasure once its grace has run out", () => {
    expect(scheduledErasure([scheduled], "2026-10-02T08:00:00Z")).toBeNull();
  });
});

describe("labels", () => {
  it("names every kind and every status from the catalogue", () => {
    expect(kindLabelKey("export")).toBe("data.kind.export");
    expect(kindLabelKey("delete")).toBe("data.kind.delete");
    expect(kindLabelKey("rectify")).toBe("data.kind.rectify");
    expect(statusLabelKey(parseRequest(row())!)).toBe("data.status.received");
    expect(statusLabelKey(parseRequest(row({ status: "cancelled" }))!)).toBe(
      "data.status.cancelled",
    );
  });

  it("says overdue over the status — a missed m.13 window is the patient's news", () => {
    expect(statusLabelKey(parseRequest(row({ overdue: true }))!)).toBe("data.status.overdue");
  });
});

describe("latestRequest", () => {
  it("returns the newest of one kind, or null when none exists", () => {
    const requests = parseRequests([
      row({ request_id: "old", received_at: "2026-08-01T08:00:00Z" }),
      row({ request_id: "new", received_at: "2026-09-01T08:00:00Z" }),
      row({ request_id: "del", kind: "delete", status: "scheduled" }),
    ]);
    expect(latestRequest(requests, "export")?.id).toBe("new");
    expect(latestRequest(requests, "rectify")).toBeNull();
  });
});

describe("formatDsarDay", () => {
  it("writes the month as a word, so the day is unambiguous in both catalogues", () => {
    expect(formatDsarDay("2026-10-01T08:00:00Z")).toContain("2026");
    expect(formatDsarDay("2026-10-01T08:00:00Z")).not.toMatch(/^\d+\/\d+/);
  });
});

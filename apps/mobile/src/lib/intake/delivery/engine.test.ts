/**
 * INT-587 — one delivery attempt, with every dependency faked.
 *
 * The order is the policy: the patient's share consent must have reached the
 * server before the note does, because `write_note` checks the share scope in
 * the same transaction that creates the share. So an attempt flushes the
 * consent queue first and sends nothing while a grant is still on the phone.
 */
import { describe, expect, it, vi } from "vitest";

import { attemptDelivery, classifyVisitError, type DeliveryDeps } from "./engine";
import { newItem, settle, type DeliveryItem } from "./outbox";
import type { NotePutBody } from "./payload";

const BODY: NotePutBody = {
  sections: [{ id: "chief_complaint", title: "Başvuru nedeni", lines: ["Ağrı"] }],
  scopes: { chief_complaint: true },
  status: "sent",
};
const VISIT = {
  hospital: "Deneme Hastanesi",
  department: "Kardiyoloji",
  date: "2026-11-02",
  branchId: null,
  visitType: null,
};
const SERVER = "0b6f6a52-0000-4000-8000-0000000000a1";
const T0 = 1_800_000_000_000;

function item(): DeliveryItem {
  return newItem({ visitId: "v-local-1", accountId: "acct-1", visit: VISIT, body: BODY }, T0);
}

function deps(overrides: Partial<DeliveryDeps> = {}): DeliveryDeps & { calls: string[] } {
  const calls: string[] = [];
  const base: DeliveryDeps = {
    shareStanding: () => "granted",
    flushConsent: async () => {
      calls.push("flush");
      return true;
    },
    resolveServerVisit: async () => {
      calls.push("resolve");
      return { kind: "resolved", serverVisitId: SERVER };
    },
    putNote: async () => {
      calls.push("put");
      return { kind: "delivered" };
    },
  };
  return Object.assign({ ...base, ...overrides }, { calls });
}

describe("the order is the disclosure policy", () => {
  it("flushes consent, resolves the visit, then PUTs — and records the delivery", async () => {
    const d = deps();
    const next = await attemptDelivery(item(), d, T0);
    expect(d.calls).toEqual(["flush", "resolve", "put"]);
    expect(next.stage).toBe("delivered");
    expect(next.serverVisitId).toBe(SERVER);
  });

  it("sends no note while a consent change is still on the phone", async () => {
    const put = vi.fn();
    const d = deps({ flushConsent: async () => false, putNote: put });
    const next = await attemptDelivery(item(), d, T0);
    expect(put).not.toHaveBeenCalled();
    expect(next.stage).toBe("queued");
    expect(next.attempts).toBe(1);
  });
});

describe("no share without the grant", () => {
  it("a share consent withdrawn on this phone parks the note with no network at all", async () => {
    const d = deps({ shareStanding: () => "withdrawn" });
    const next = await attemptDelivery(item(), d, T0);
    expect(d.calls).toEqual([]);
    expect(next.stage).toBe("awaiting_consent");
  });

  it("a server that refuses the share scope parks it for the patient", async () => {
    const d = deps({ putNote: async () => ({ kind: "consent" }) });
    const next = await attemptDelivery(item(), d, T0);
    expect(next.stage).toBe("awaiting_consent");
    // the server visit it found is kept, so a re-confirmed send does not
    // look it up a second time
    expect(next.serverVisitId).toBe(SERVER);
  });

  it("never attempts an item that is waiting for consent, refused or delivered", async () => {
    for (const settled of [
      settle(item(), { kind: "consent", serverVisitId: null }, T0),
      settle(item(), { kind: "refused", reason: "invalid", serverVisitId: null }, T0),
      settle(item(), { kind: "delivered", serverVisitId: SERVER }, T0),
    ]) {
      const d = deps();
      expect(await attemptDelivery(settled, d, T0)).toBe(settled);
      expect(d.calls).toEqual([]);
    }
  });
});

describe("the server visit", () => {
  it("is resolved once and then reused", async () => {
    const first = await attemptDelivery(
      item(),
      deps({ putNote: async () => ({ kind: "transient", retryAfterMs: null }) }),
      T0,
    );
    expect(first.serverVisitId).toBe(SERVER);
    const d = deps();
    await attemptDelivery(first, d, first.nextAttemptAt);
    expect(d.calls).toEqual(["flush", "put"]);
  });

  it("an unreachable lookup is retried; a refused one is surfaced", async () => {
    const transient = await attemptDelivery(
      item(),
      deps({ resolveServerVisit: async () => ({ kind: "transient" }) }),
      T0,
    );
    expect(transient.stage).toBe("queued");
    expect(transient.serverVisitId).toBeNull();
    const refused = await attemptDelivery(
      item(),
      deps({ resolveServerVisit: async () => ({ kind: "refused", reason: "core_consent" }) }),
      T0,
    );
    expect(refused.stage).toBe("refused");
    expect(refused.refusal).toBe("core_consent");
  });
});

describe("a failed server-visit lookup", () => {
  it("retries what a retry can change and surfaces what it cannot", () => {
    expect(classifyVisitError({ kind: "network", status: null })).toEqual({ kind: "transient" });
    expect(classifyVisitError({ kind: "generic", status: 503 })).toEqual({ kind: "transient" });
    expect(classifyVisitError({ kind: "generic", status: 429 })).toEqual({ kind: "transient" });
    expect(classifyVisitError({ kind: "generic", status: null })).toEqual({ kind: "transient" });
    expect(classifyVisitError(new TypeError("Network request failed"))).toEqual({
      kind: "transient",
    });
    // the near miss: a 4xx on visit creation is an answer, not a blip
    expect(classifyVisitError({ kind: "generic", status: 422 })).toEqual({
      kind: "refused",
      reason: "invalid",
    });
    expect(classifyVisitError({ kind: "session", status: null })).toEqual({
      kind: "refused",
      reason: "session",
    });
    expect(classifyVisitError({ kind: "core_consent", status: null })).toEqual({
      kind: "refused",
      reason: "core_consent",
    });
    expect(classifyVisitError({ kind: "consent", status: null })).toEqual({
      kind: "refused",
      reason: "rejected",
    });
  });
});

describe("an attempt never throws", () => {
  it("a dependency that throws is a transient failure, and the note is kept", async () => {
    const boom = async () => {
      throw new Error("boom");
    };
    for (const broken of [
      deps({ flushConsent: boom }),
      deps({ resolveServerVisit: boom }),
      deps({ putNote: boom }),
    ]) {
      const next = await attemptDelivery(item(), broken, T0);
      expect(next.stage).toBe("queued");
      expect(next.body).toEqual(BODY);
    }
  });
});

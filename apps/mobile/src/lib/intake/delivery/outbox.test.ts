/**
 * INT-587 — the delivery state machine for one queued note.
 *
 * Four stages and one rule per stage: `queued` retries with backoff and is
 * never dropped; `awaiting_consent` waits for the patient and never retries on
 * its own; `refused` is a 4xx the patient is told about and that is never
 * retried on its own; `delivered` is the only stage that may say "sent".
 */
import { describe, expect, it } from "vitest";

import {
  BACKOFF,
  backoffMs,
  holdForConsent,
  isDue,
  newItem,
  parseItem,
  reconfirm,
  reopenable,
  retryNow,
  settle,
  type DeliveryItem,
} from "./outbox";
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

const T0 = 1_800_000_000_000;

function queued(): DeliveryItem {
  return newItem({ visitId: "v-local-1", accountId: "acct-1", visit: VISIT, body: BODY }, T0);
}

describe("a new item is queued and due at once", () => {
  it("starts queued, unattempted, due now", () => {
    const item = queued();
    expect(item.stage).toBe("queued");
    expect(item.attempts).toBe(0);
    expect(isDue(item, T0)).toBe(true);
  });
});

describe("backoff", () => {
  it("doubles from the base and stops at the cap", () => {
    expect(backoffMs(1)).toBe(BACKOFF.baseMs);
    expect(backoffMs(2)).toBe(BACKOFF.baseMs * 2);
    expect(backoffMs(3)).toBe(BACKOFF.baseMs * 4);
    expect(backoffMs(60)).toBe(BACKOFF.capMs);
  });

  it("a transient failure re-queues the item later and keeps its body", () => {
    const next = settle(
      queued(),
      { kind: "transient", retryAfterMs: null, serverVisitId: null },
      T0,
    );
    expect(next.stage).toBe("queued");
    expect(next.attempts).toBe(1);
    expect(next.nextAttemptAt).toBe(T0 + BACKOFF.baseMs);
    expect(next.body).toEqual(BODY);
    expect(isDue(next, T0)).toBe(false);
    expect(isDue(next, T0 + BACKOFF.baseMs)).toBe(true);
  });

  it("honours a server Retry-After, bounded by the cap", () => {
    const next = settle(
      queued(),
      { kind: "transient", retryAfterMs: 90_000, serverVisitId: null },
      T0,
    );
    expect(next.nextAttemptAt).toBe(T0 + 90_000);
    const capped = settle(
      queued(),
      { kind: "transient", retryAfterMs: BACKOFF.capMs * 10, serverVisitId: null },
      T0,
    );
    expect(capped.nextAttemptAt).toBe(T0 + BACKOFF.capMs);
  });

  it("never drops an item, however many transient failures it meets", () => {
    let item = queued();
    for (let i = 0; i < 200; i += 1) {
      item = settle(item, { kind: "transient", retryAfterMs: null, serverVisitId: null }, T0);
    }
    expect(item.stage).toBe("queued");
    expect(item.body).toEqual(BODY);
    expect(item.attempts).toBe(200);
    expect(item.nextAttemptAt - T0).toBe(BACKOFF.capMs);
  });
});

describe("a 4xx is surfaced and not retried on its own", () => {
  it("moves to refused with its reason and is never due again", () => {
    const refused = settle(
      queued(),
      { kind: "refused", reason: "invalid", serverVisitId: "srv-1" },
      T0,
    );
    expect(refused.stage).toBe("refused");
    expect(refused.refusal).toBe("invalid");
    expect(isDue(refused, T0 + BACKOFF.capMs * 100)).toBe(false);
    expect(refused.body).toEqual(BODY);
  });

  it("a patient's retry re-queues it — the only way back", () => {
    const refused = settle(
      queued(),
      { kind: "refused", reason: "session", serverVisitId: null },
      T0,
    );
    const again = retryNow(refused, T0 + 5);
    expect(again.stage).toBe("queued");
    expect(again.refusal).toBeNull();
    expect(isDue(again, T0 + 5)).toBe(true);
  });

  it("retry does nothing to a stage it does not own", () => {
    const item = queued();
    expect(retryNow(item, T0)).toBe(item);
  });
});

describe("consent", () => {
  it("a server consent refusal waits for the patient and never retries itself", () => {
    const waiting = settle(queued(), { kind: "consent", serverVisitId: "srv-1" }, T0);
    expect(waiting.stage).toBe("awaiting_consent");
    expect(isDue(waiting, T0 + BACKOFF.capMs * 100)).toBe(false);
    expect(waiting.serverVisitId).toBe("srv-1");
  });

  it("a fresh confirmation re-queues it", () => {
    const waiting = settle(queued(), { kind: "consent", serverVisitId: null }, T0);
    expect(reconfirm(waiting, T0 + 1).stage).toBe("queued");
    expect(isDue(reconfirm(waiting, T0 + 1), T0 + 1)).toBe(true);
  });

  it("a local withdrawal parks a queued item before it can be sent", () => {
    expect(holdForConsent(queued()).stage).toBe("awaiting_consent");
  });

  it("a local withdrawal does not reach back into a delivered item", () => {
    const delivered = settle(queued(), { kind: "delivered", serverVisitId: "srv-1" }, T0);
    expect(holdForConsent(delivered)).toBe(delivered);
  });
});

describe("delivered", () => {
  it("records the server visit and the instant, and keeps no copy of the note", () => {
    const delivered = settle(queued(), { kind: "delivered", serverVisitId: "srv-1" }, T0 + 7);
    expect(delivered.stage).toBe("delivered");
    expect(delivered.serverVisitId).toBe("srv-1");
    expect(delivered.deliveredAt).toBe(T0 + 7);
    expect(delivered.body).toBeNull();
    expect(isDue(delivered, T0 + BACKOFF.capMs * 100)).toBe(false);
  });

  it("is terminal — no outcome moves it again", () => {
    const delivered = settle(queued(), { kind: "delivered", serverVisitId: "srv-1" }, T0);
    expect(
      settle(delivered, { kind: "transient", retryAfterMs: null, serverVisitId: null }, T0),
    ).toBe(delivered);
    expect(retryNow(delivered, T0)).toBe(delivered);
    expect(reconfirm(delivered, T0)).toBe(delivered);
  });
});

describe("which notes the patient may take back to a draft", () => {
  it("one nothing has reached: unconfirmed, waiting for consent, or refused", () => {
    expect(reopenable(null)).toBe(true);
    expect(reopenable(settle(queued(), { kind: "consent", serverVisitId: null }, T0))).toBe(true);
    expect(
      reopenable(settle(queued(), { kind: "refused", reason: "invalid", serverVisitId: null }, T0)),
    ).toBe(true);
  });

  it("never a queued one — a PUT may be in flight or its answer lost", () => {
    expect(reopenable(queued())).toBe(false);
  });

  it("never a delivered one", () => {
    expect(reopenable(settle(queued(), { kind: "delivered", serverVisitId: "s" }, T0))).toBe(false);
  });
});

describe("a stored item is validated before it is trusted", () => {
  it("round-trips through JSON", () => {
    const item = settle(
      queued(),
      { kind: "transient", retryAfterMs: null, serverVisitId: "s" },
      T0,
    );
    expect(parseItem(JSON.parse(JSON.stringify(item)))).toEqual(item);
  });

  it("refuses an unknown stage, a missing body on a queued item, or garbage", () => {
    expect(parseItem({ ...queued(), stage: "lost" })).toBeNull();
    expect(parseItem({ ...queued(), body: null })).toBeNull();
    expect(parseItem("x")).toBeNull();
  });
});

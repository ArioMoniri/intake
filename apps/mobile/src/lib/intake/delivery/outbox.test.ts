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
  linkWindow,
  markShareWithdrawn,
  needsReshare,
  newItem,
  parseItem,
  reconfirm,
  reopenable,
  reshare,
  retryNow,
  settle,
  unsentItems,
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

/** The share grant this note was queued under (INT-587 legal review B1). */
const GRANT = {
  version: "2026-10-28.syn1",
  textHash: "a".repeat(64),
  atIso: "2026-10-29T10:00:00.000Z",
};
const LATER_GRANT = { ...GRANT, atIso: "2026-10-29T11:00:00.000Z" };

function queued(): DeliveryItem {
  return newItem(
    { visitId: "v-local-1", accountId: "acct-1", visit: VISIT, body: BODY, grant: GRANT },
    T0,
  );
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

  it("a fresh confirmation re-queues it, bound to the new grant", () => {
    const waiting = settle(queued(), { kind: "consent", serverVisitId: null }, T0);
    const released = reconfirm(waiting, LATER_GRANT, T0 + 1);
    expect(released.stage).toBe("queued");
    expect(released.grant).toEqual(LATER_GRANT);
    expect(isDue(released, T0 + 1)).toBe(true);
  });

  it("a local withdrawal parks a queued item before it can be sent, and unbinds its grant", () => {
    const parked = holdForConsent(queued());
    expect(parked.stage).toBe("awaiting_consent");
    expect(parked.grant).toBeNull();
  });

  it("a local withdrawal parks a REFUSED item too — a retry must not resend it (B1)", () => {
    const refused = settle(
      queued(),
      { kind: "refused", reason: "session", serverVisitId: null },
      T0,
    );
    const parked = holdForConsent(refused);
    expect(parked.stage).toBe("awaiting_consent");
    expect(parked.refusal).toBeNull();
    expect(parked.grant).toBeNull();
    expect(retryNow(parked, T0)).toBe(parked);
  });

  it("a local withdrawal does not reach back into a delivered item", () => {
    const delivered = settle(queued(), { kind: "delivered", serverVisitId: "srv-1" }, T0);
    expect(holdForConsent(delivered)).toBe(delivered);
  });

  it("a parked item is released only by reconfirm, never by a retry", () => {
    const parked = holdForConsent(queued());
    expect(retryNow(parked, T0)).toBe(parked);
    expect(isDue(parked, T0 + BACKOFF.capMs * 100)).toBe(false);
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
    expect(reconfirm(delivered, LATER_GRANT, T0)).toBe(delivered);
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

  it("restores a parked item parked — the restart cannot resurrect a send", () => {
    const parked = holdForConsent(queued());
    const restored = parseItem(JSON.parse(JSON.stringify(parked)));
    expect(restored?.stage).toBe("awaiting_consent");
    expect(restored?.grant).toBeNull();
  });

  it("a stored queued item with no valid grant comes back parked, never sendable", () => {
    for (const grant of [null, undefined, { version: 1 }, { ...GRANT, atIso: 5 }]) {
      const restored = parseItem({ ...queued(), grant });
      expect(restored?.stage, JSON.stringify(grant)).toBe("awaiting_consent");
      expect(restored?.grant).toBeNull();
      expect(restored?.body).toEqual(BODY); // kept, not dropped
    }
  });
});

/*
 * INT-589 (1): after the patient withdraws the share consent, the server
 * revokes the delivered note's share and links (consents.py), so the note can
 * no longer be linked. A re-share is a fresh grant FOR THIS NOTE and the same
 * frozen body sent again; the server recreates the share in that PUT.
 */
describe("re-share after a withdrawal", () => {
  const delivered = (at: number): DeliveryItem =>
    settle(queued(), { kind: "delivered", serverVisitId: "srv-1" }, at);

  // The mark is on the item itself, which the sealed outbox persists, so the
  // re-share survives a restart (the consent ledger is in-memory; legal note).
  it("a note delivered BEFORE a landed withdrawal is marked, and needs a re-share", () => {
    const item = markShareWithdrawn(
      delivered(Date.parse("2026-10-29T10:00:00.000Z")),
      "2026-10-29T11:00:00.000Z",
    );
    expect(item.shareWithdrawnAt).toBe("2026-10-29T11:00:00.000Z");
    expect(needsReshare(item)).toBe(true);
  });

  it("near miss: a note delivered AFTER the withdrawal is not marked", () => {
    const item = delivered(Date.parse("2026-10-29T12:00:00.000Z"));
    expect(markShareWithdrawn(item, "2026-10-29T11:00:00.000Z")).toBe(item);
    expect(needsReshare(item)).toBe(false);
  });

  it("near miss: an undelivered note or an unreadable instant is never marked", () => {
    const q = queued();
    expect(markShareWithdrawn(q, "2026-10-29T11:00:00.000Z")).toBe(q);
    const d = delivered(T0 - 1);
    expect(markShareWithdrawn(d, "not-a-date")).toBe(d);
    expect(needsReshare(null)).toBe(false);
    expect(needsReshare(q)).toBe(false);
  });

  it("the mark survives the sealed round trip, and an unreadable one is dropped", () => {
    const marked = markShareWithdrawn(delivered(T0), new Date(T0 + 1).toISOString());
    const restored = parseItem(JSON.parse(JSON.stringify(marked)));
    expect(restored?.shareWithdrawnAt).toBe(marked.shareWithdrawnAt);
    expect(needsReshare(restored)).toBe(true);
    const garbled = parseItem({ ...JSON.parse(JSON.stringify(marked)), shareWithdrawnAt: 5 });
    expect(garbled?.shareWithdrawnAt).toBeUndefined();
    // an item written before INT-589 carries no mark and reads back unmarked
    const legacy = parseItem(JSON.parse(JSON.stringify(delivered(T0))));
    expect(needsReshare(legacy)).toBe(false);
  });

  it("re-queues the delivered note with the fresh grant and the body again", () => {
    const item = markShareWithdrawn(delivered(T0), new Date(T0 + 1).toISOString());
    expect(item.body).toBeNull();
    const next = reshare(item, BODY, LATER_GRANT, T0 + 5);
    expect(next.shareWithdrawnAt).toBeUndefined();
    expect(next.stage).toBe("queued");
    expect(next.body).toEqual(BODY);
    expect(next.grant).toEqual(LATER_GRANT);
    expect(next.deliveredAt).toBeNull();
    expect(next.attempts).toBe(0);
    expect(isDue(next, T0 + 5)).toBe(true);
    // the server visit it reached is kept: the PUT goes to the same visit
    expect(next.serverVisitId).toBe("srv-1");
  });

  it("near miss: only a delivered note can be re-shared", () => {
    const item = queued();
    expect(reshare(item, BODY, LATER_GRANT, T0)).toBe(item);
  });
});

/*
 * INT-589 legal note: a re-share is only worth offering while a Doctor Link
 * can still be issued. A link closes at the latest 72 h after the visit
 * (files/02 §2b), and an undated visit cannot have one. The device holds the
 * visit's DATE, not its hour, and the server's note answer carries no close
 * instant, so the window is anchored where the server's own fallback is: the
 * START of the visit day in Türkiye + 72 h. That is never later than the
 * server's link close (the appointment hour can only move it later), so the
 * card never asks for consent to a share whose links are already dead.
 */
describe("the link window a re-share needs", () => {
  const at = (iso: string): number => Date.parse(iso);

  it("is open from before the visit until 72 h after the start of its day", () => {
    expect(linkWindow("2026-11-02", at("2026-10-20T08:00:00+03:00"))).toBe("open");
    expect(linkWindow("2026-11-02", at("2026-11-02T08:00:00+03:00"))).toBe("open");
    expect(linkWindow("2026-11-02", at("2026-11-04T23:59:59+03:00"))).toBe("open");
  });

  it("is closed from 72 h after the start of the visit day", () => {
    expect(linkWindow("2026-11-02", at("2026-11-05T00:00:00+03:00"))).toBe("closed");
    expect(linkWindow("2026-11-02", at("2026-12-01T12:00:00+03:00"))).toBe("closed");
  });

  it("near miss: never later than the server's close, even for a midnight appointment", () => {
    // the earliest the server can close a link for this visit: 00:00 + 72 h
    const serverEarliestClose = at("2026-11-02T00:00:00+03:00") + 72 * 60 * 60 * 1_000;
    expect(linkWindow("2026-11-02", serverEarliestClose - 1)).toBe("open");
    expect(linkWindow("2026-11-02", serverEarliestClose)).toBe("closed");
    // the end-of-day anchor the review replaced would still say open here
    expect(linkWindow("2026-11-02", at("2026-11-05T12:00:00+03:00"))).toBe("closed");
  });

  it("near miss: the day boundary is Türkiye's, not UTC's", () => {
    // 2026-11-04T21:30Z is already 5 Nov 00:30 in Türkiye: closed there
    expect(linkWindow("2026-11-02", at("2026-11-04T21:30:00Z"))).toBe("closed");
    // and 2026-11-04T20:30Z is still 4 Nov 23:30 in Türkiye: open
    expect(linkWindow("2026-11-02", at("2026-11-04T20:30:00Z"))).toBe("open");
  });

  it("an undated visit has no link window at all", () => {
    expect(linkWindow(null, at("2026-11-02T08:00:00+03:00"))).toBe("no_date");
  });
});

/*
 * INT-589 (2): sign-out shreds the outbox with the drafts. A note still on
 * the phone — queued, refused or waiting for consent — is lost then, so the
 * sign-out warns while there is one.
 */
describe("which notes a sign-out would lose", () => {
  it("lists every note not yet delivered, and no delivered one", () => {
    const items: Record<string, DeliveryItem> = {
      a: queued(),
      b: { ...queued(), visitId: "b", stage: "refused", refusal: "rejected" },
      c: holdForConsent({ ...queued(), visitId: "c" }),
      d: settle({ ...queued(), visitId: "d" }, { kind: "delivered", serverVisitId: "s" }, T0),
    };
    expect(
      unsentItems(items)
        .map((item) => item.visitId)
        .sort(),
    ).toEqual(["b", "c", "v-local-1"]);
  });

  it("near miss: an outbox of delivered notes loses nothing", () => {
    const d = settle(queued(), { kind: "delivered", serverVisitId: "s" }, T0);
    expect(unsentItems({ [d.visitId]: d })).toEqual([]);
    expect(unsentItems({})).toEqual([]);
  });
});

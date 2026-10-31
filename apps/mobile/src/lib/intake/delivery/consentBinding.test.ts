/**
 * INT-587 legal review B1 — a share consent given for one note can never
 * release a different note after a withdrawal (KVKK m.4/5/6).
 *
 * The scenario the review found: note C is queued; the patient withdraws core
 * (which takes the share purpose down with it), grants core again, then sends
 * note B. B's grant sets the share standing back to `granted`, and before this
 * fix C went out on it — with no consent of its own. After a restart the
 * in-memory withdrawal op was gone and C still went.
 *
 * These tests run the REAL consent store (lib/consent/store) against the real
 * outbox, with only the network faked, so the withdrawal travels the same path
 * the İzinleriniz screens use (`withdrawLocal`) and the outbox hears of it the
 * way the app wires it (`watchConsent` = the ledger subscription).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  consentQueueClear,
  grantLocal,
  grantShareLocal,
  landedShareWithdrawal,
  lastShareWithdrawal,
  refreshLedgerFromServer,
  resetLedger,
  seedLedgerForAccount,
  shareStanding,
  subscribeToLedger,
  withdrawLocal,
  withdrawShareLocal,
} from "../../consent/store";
import type { DraftBackend } from "../offline/draftStore";
import type { DeliveryDeps } from "./engine";
import { BACKOFF, needsReshare } from "./outbox";
import type { NotePutBody } from "./payload";
import { sealedOutbox } from "./persistence";
import {
  deliveryOf,
  enqueueDelivery,
  reconfirmDelivery,
  reshareDelivery,
  retryDelivery,
  runDueDeliveries,
  startDelivery,
  stopDelivery,
  type DeliveryRuntime,
} from "./store";
import type { PutResult } from "./transport";

const mocks = vi.hoisted(() => ({ authedFetch: vi.fn() }));
vi.mock("@/lib/auth/api", () => ({ authedFetch: mocks.authedFetch }));

const HASH = "c".repeat(64);
const SNAPSHOT = {
  scopes: [{ scope: "core", reason: "granted", version: "syn3", text_hash: HASH }],
  texts: [
    { purpose: "core", version: "syn3", text_hash: HASH, body: "Deneme temel metni." },
    { purpose: "documents", version: "syn1", text_hash: HASH, body: "Deneme belge metni." },
    { purpose: "share", version: "syn1", text_hash: HASH, body: "Deneme paylaşım metni." },
  ],
};

function reply(ok: boolean, body: unknown = {}): Response {
  return { ok, status: ok ? 200 : 503, json: async () => body } as unknown as Response;
}

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

function fakeBackend(): DraftBackend {
  const blobs = new Map<string, string>();
  let iv = 0;
  return {
    vault: { key: async () => new Uint8Array(32).fill(7), destroy: async () => undefined },
    blobs: {
      write: async (id, data) => void blobs.set(id, data),
      read: async (id) => blobs.get(id) ?? null,
      remove: async (id) => void blobs.delete(id),
      list: async () => [...blobs.keys()],
    },
    randomIv: async () => {
      iv += 1;
      const bytes = new Uint8Array(12);
      bytes[11] = iv;
      return bytes;
    },
    now: () => T0,
    origin: async () => "origin",
  };
}

interface World {
  backend: DraftBackend;
  /** PUTs per visit id — the only evidence a note left the phone. */
  puts: Map<string, number>;
  online: { value: boolean };
  answers: Map<string, PutResult>;
  clock: { now: number };
}

function world(): World {
  return {
    backend: fakeBackend(),
    puts: new Map(),
    online: { value: false },
    answers: new Map(),
    clock: { now: T0 },
  };
}

/** The runtime ./native builds, with the network faked and the consent store real. */
function runtime(w: World): DeliveryRuntime {
  const servers = new Map<string, string>();
  const deps: DeliveryDeps = {
    shareStanding,
    lastShareWithdrawal,
    landedShareWithdrawal,
    flushConsent: async () => w.online.value && (await consentQueueClear()),
    resolveServerVisit: async (_visit, visitId) =>
      w.online.value
        ? { kind: "resolved", serverVisitId: `srv-${visitId}` }
        : { kind: "transient" },
    putNote: async (serverVisitId) => {
      if (!w.online.value) {
        return { kind: "transient", retryAfterMs: null };
      }
      const visitId = serverVisitId.slice("srv-".length);
      servers.set(visitId, serverVisitId);
      w.puts.set(visitId, (w.puts.get(visitId) ?? 0) + 1);
      return w.answers.get(visitId) ?? { kind: "delivered" };
    },
  };
  return {
    deps,
    persistence: sealedOutbox(w.backend),
    now: () => w.clock.now,
    schedule: () => () => undefined,
    watchConsent: subscribeToLedger,
  };
}

function puts(w: World, visitId: string): number {
  return w.puts.get(visitId) ?? 0;
}

async function signedIn(w: World): Promise<void> {
  mocks.authedFetch.mockImplementation(async (path: string) =>
    path === "/v1/consents" ? reply(true, SNAPSHOT) : reply(w.online.value),
  );
  seedLedgerForAccount("acct-1", null);
  await refreshLedgerFromServer();
  await startDelivery("acct-1", runtime(w));
}

/** Grant the share for one note and queue it — what NoteDelivery does. */
async function send(visitId: string, atIso: string): Promise<void> {
  const receipt = grantShareLocal(visitId, atIso);
  if (receipt === null) throw new Error("fixture: no share text");
  await enqueueDelivery({ visitId, visit: VISIT, body: BODY }, receipt);
}

beforeEach(() => {
  stopDelivery();
  resetLedger();
});

afterEach(() => {
  stopDelivery();
  resetLedger();
  mocks.authedFetch.mockReset();
});

describe("(a) a core withdrawal parks every unsent note, and a restart keeps them parked", () => {
  it("parks queued AND refused notes, with zero PUTs before or after a restore from disk", async () => {
    const w = world();
    await signedIn(w);
    await send("v-c", "2026-10-29T10:00:00.000Z"); // offline: stays queued
    w.online.value = true;
    w.answers.set("v-d", { kind: "refused", reason: "session" });
    await send("v-d", "2026-10-29T10:00:01.000Z"); // refused: waits for a retry
    expect(deliveryOf("v-c")?.stage).toBe("queued");
    expect(deliveryOf("v-d")?.stage).toBe("refused");
    const dPuts = puts(w, "v-d");
    w.online.value = false;

    withdrawLocal("core", "2026-10-29T10:05:00.000Z");
    // parked in memory synchronously, before any await
    expect(deliveryOf("v-c")?.stage).toBe("awaiting_consent");
    expect(deliveryOf("v-d")?.stage).toBe("awaiting_consent");
    // let the sealed writes land (milliseconds on a device)
    await new Promise((resolve) => setTimeout(resolve, 0));

    // the process dies; only the sealed bytes remain — the in-memory consent
    // state (the withdrawal op, the withdrawal instant) is gone with it
    stopDelivery();
    resetLedger();
    seedLedgerForAccount("acct-1", null);
    await refreshLedgerFromServer();
    expect(lastShareWithdrawal()).toBeNull();
    w.online.value = true;
    w.clock.now += BACKOFF.capMs;
    await startDelivery("acct-1", runtime(w));
    await runDueDeliveries();
    expect(deliveryOf("v-c")?.stage).toBe("awaiting_consent");
    expect(deliveryOf("v-d")?.stage).toBe("awaiting_consent");
    expect(puts(w, "v-c")).toBe(0);
    expect(puts(w, "v-d")).toBe(dPuts);
  });
});

describe("(b) a later grant for note B never releases note C", () => {
  it("C stays parked with zero PUTs while B is granted and delivered", async () => {
    const w = world();
    await signedIn(w);
    await send("v-c", "2026-10-29T10:00:00.000Z");
    withdrawLocal("core", "2026-10-29T10:05:00.000Z");
    grantLocal("core", "2026-10-29T10:06:00.000Z");
    w.online.value = true;
    await send("v-b", "2026-10-29T10:07:00.000Z");
    w.clock.now += BACKOFF.capMs;
    await runDueDeliveries();

    expect(shareStanding()).toBe("granted"); // the standing really is back …
    expect(deliveryOf("v-b")?.stage).toBe("delivered");
    expect(deliveryOf("v-c")?.stage).toBe("awaiting_consent"); // … and C is still parked
    expect(puts(w, "v-c")).toBe(0);
  });

  it("C goes only on a grant of its own", async () => {
    const w = world();
    await signedIn(w);
    await send("v-c", "2026-10-29T10:00:00.000Z");
    withdrawLocal("core", "2026-10-29T10:05:00.000Z");
    grantLocal("core", "2026-10-29T10:06:00.000Z");
    w.online.value = true;
    const own = grantShareLocal("v-c", "2026-10-29T10:08:00.000Z");
    if (own === null) throw new Error("fixture");
    await reconfirmDelivery("v-c", own);
    expect(deliveryOf("v-c")?.stage).toBe("delivered");
    expect(puts(w, "v-c")).toBe(1);
  });
});

describe("(c) 'Tekrar deneyin' after a withdrawal sends nothing", () => {
  it("retryDelivery(C) after a share withdrawal and a grant for B leaves C unsent", async () => {
    const w = world();
    await signedIn(w);
    w.online.value = true;
    w.answers.set("v-c", { kind: "refused", reason: "rejected" });
    await send("v-c", "2026-10-29T10:00:00.000Z");
    expect(deliveryOf("v-c")?.stage).toBe("refused");
    const cPuts = puts(w, "v-c");
    w.answers.delete("v-c");

    expect(await withdrawShareLocal("2026-10-29T10:05:00.000Z")).toBe("landed");
    await send("v-b", "2026-10-29T10:06:00.000Z");
    await retryDelivery("v-c");

    expect(deliveryOf("v-b")?.stage).toBe("delivered");
    expect(deliveryOf("v-c")?.stage).toBe("awaiting_consent");
    expect(puts(w, "v-c")).toBe(cPuts);
  });
});

describe("near miss: a withdrawal of another purpose parks nothing", () => {
  it("withdrawing documents leaves a queued note queued, and it is delivered", async () => {
    const w = world();
    await signedIn(w);
    await send("v-c", "2026-10-29T10:00:00.000Z");
    withdrawLocal("documents", "2026-10-29T10:05:00.000Z");
    expect(deliveryOf("v-c")?.stage).toBe("queued");
    w.online.value = true;
    w.clock.now += BACKOFF.capMs;
    await runDueDeliveries();
    expect(deliveryOf("v-c")?.stage).toBe("delivered");
    expect(puts(w, "v-c")).toBe(1);
  });
});

describe("(e) INT-589: a delivered note is shared again only on a fresh grant for it", () => {
  /** An instant `ms` after the outbox clock started, as the ledger records one. */
  const at = (ms: number): string => new Date(T0 + ms).toISOString();

  async function deliveredThenWithdrawn(w: World): Promise<void> {
    await signedIn(w);
    w.online.value = true;
    await send("v-r", at(0));
    expect(deliveryOf("v-r")?.stage).toBe("delivered");
    expect(await withdrawShareLocal(at(60_000))).toBe("landed");
  }

  it("after a withdrawal the delivered note needs a re-share; a fresh grant for it re-sends it", async () => {
    const w = world();
    await deliveredThenWithdrawn(w);
    expect(needsReshare(deliveryOf("v-r"))).toBe(true);

    // two minutes later, on the same clock the outbox stamps deliveries with
    w.clock.now = T0 + 120_000;
    const receipt = grantShareLocal("v-r", at(120_000));
    if (receipt === null) throw new Error("fixture: no share text");
    expect(await reshareDelivery("v-r", BODY, receipt)).toBe(true);
    expect(deliveryOf("v-r")?.stage).toBe("delivered");
    expect(puts(w, "v-r")).toBe(2);
    expect(needsReshare(deliveryOf("v-r"))).toBe(false);
  });

  it("the re-share survives a restart: the mark is on the sealed item, not in the ledger", async () => {
    const w = world();
    await deliveredThenWithdrawn(w);
    // let the sealed write land, then lose everything in memory
    await new Promise((resolve) => setTimeout(resolve, 0));
    stopDelivery();
    resetLedger();
    seedLedgerForAccount("acct-1", null);
    expect(lastShareWithdrawal()).toBeNull();
    await startDelivery("acct-1", runtime(w));
    expect(needsReshare(deliveryOf("v-r"))).toBe(true);
  });

  it("near miss: a withdrawal the server refused marks nothing — the share stands", async () => {
    const w = world();
    await signedIn(w);
    w.online.value = true;
    await send("v-r", at(0));
    mocks.authedFetch.mockImplementation(async (path: string) => {
      if (path === "/v1/consents") {
        return reply(true, SNAPSHOT);
      }
      const status = path.endsWith("/withdraw") ? 409 : 200;
      return { ok: status < 300, status, json: async () => ({}) } as unknown as Response;
    });
    expect(await withdrawShareLocal(at(60_000))).toBe("refused");
    expect(needsReshare(deliveryOf("v-r"))).toBe(false);
  });

  it("near miss: a grant given for another note re-shares nothing", async () => {
    const w = world();
    await deliveredThenWithdrawn(w);
    const other = grantShareLocal("v-other", at(120_000));
    if (other === null) throw new Error("fixture: no share text");
    expect(await reshareDelivery("v-r", BODY, other)).toBe(false);
    expect(puts(w, "v-r")).toBe(1);
    expect(needsReshare(deliveryOf("v-r"))).toBe(true);
  });

  it("near miss: a note still on its way is not re-shared — it is reconfirmed instead", async () => {
    const w = world();
    await signedIn(w);
    await send("v-q", at(0)); // offline: queued
    const receipt = grantShareLocal("v-q", at(30_000));
    if (receipt === null) throw new Error("fixture: no share text");
    expect(await reshareDelivery("v-q", BODY, receipt)).toBe(false);
    expect(deliveryOf("v-q")?.stage).toBe("queued");
  });
});

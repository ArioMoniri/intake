/**
 * INT-587 — the outbox as the app runs it: sealed on disk, restored after a
 * restart, retried with backoff, and never dropped.
 *
 * The backend is the INT-142 in-memory fake (the production one is keychain +
 * expo-file-system behind a lazy import), so "survives an app restart" is
 * proved the honest way: the store's memory is thrown away and a new run
 * starts from nothing but the bytes on "disk".
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  applyShareText,
  freshLedger,
  grantShare,
  type ShareGrantReceipt,
} from "../../consent/ledger";
import { isEncryptedEnvelope } from "../offline/envelope";
import type { DraftBackend } from "../offline/draftStore";
import type { DeliveryDeps } from "./engine";
import { BACKOFF } from "./outbox";
import type { NotePutBody } from "./payload";
import { sealedOutbox } from "./persistence";
import {
  deliveryOf,
  discardUndelivered,
  enqueueDelivery,
  holdDeliveriesForConsent,
  reconfirmDelivery,
  retryDelivery,
  runDueDeliveries,
  serverVisitIdOf,
  startDelivery,
  stopDelivery,
  type DeliveryRuntime,
} from "./store";
import type { PutResult } from "./transport";

const BODY: NotePutBody = {
  sections: [{ id: "chief_complaint", title: "Başvuru nedeni", lines: ["Göğüsümde baskı var"] }],
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

function fakeBackend(): DraftBackend & { blobBytes: Map<string, string> } {
  const blobBytes = new Map<string, string>();
  let key: Uint8Array | null = null;
  let iv = 0;
  return {
    blobBytes,
    vault: {
      async key() {
        key ??= new Uint8Array(32).fill(0x5a);
        return key;
      },
      async destroy() {
        key = null;
      },
    },
    blobs: {
      async write(id, data) {
        blobBytes.set(id, data);
      },
      async read(id) {
        return blobBytes.get(id) ?? null;
      },
      async remove(id) {
        blobBytes.delete(id);
      },
      async list() {
        return [...blobBytes.keys()];
      },
    },
    async randomIv() {
      iv += 1;
      const bytes = new Uint8Array(12);
      bytes[11] = iv;
      return bytes;
    },
    now: () => T0,
    origin: async () => "origin-test",
  };
}

/** A receipt the way the app gets one: a grant against a loaded share text. */
function receipt(): ShareGrantReceipt {
  const ledger = applyShareText(freshLedger(), {
    status: "loaded",
    text: { version: "2026-10-28.syn1", textHash: "a".repeat(64), body: "Deneme metni." },
  });
  const granted = grantShare(ledger, "2026-10-29T10:00:00Z");
  if (granted.receipt === null) throw new Error("fixture");
  return granted.receipt;
}

interface Harness {
  runtime: DeliveryRuntime;
  network: { online: boolean; answer: PutResult };
  puts: number;
  timers: number[];
  clock: { now: number };
}

function harness(backend: DraftBackend): Harness {
  const h: Harness = {
    network: { online: false, answer: { kind: "delivered" } },
    puts: 0,
    timers: [],
    clock: { now: T0 },
    runtime: undefined as unknown as DeliveryRuntime,
  };
  const deps: DeliveryDeps = {
    shareStanding: () => "granted",
    flushConsent: async () => h.network.online,
    resolveServerVisit: async () =>
      h.network.online ? { kind: "resolved", serverVisitId: SERVER } : { kind: "transient" },
    putNote: async () => {
      h.puts += 1;
      return h.network.online ? h.network.answer : { kind: "transient", retryAfterMs: null };
    },
  };
  h.runtime = {
    deps,
    persistence: sealedOutbox(backend),
    now: () => h.clock.now,
    schedule: (_run, delayMs) => {
      h.timers.push(delayMs);
      return () => undefined;
    },
  };
  return h;
}

beforeEach(() => {
  stopDelivery();
});

afterEach(() => {
  stopDelivery();
  vi.restoreAllMocks();
});

describe("offline send queues, sealed, and survives an app restart", () => {
  it("lands encrypted at rest with no plaintext of the note", async () => {
    const backend = fakeBackend();
    const h = harness(backend);
    await startDelivery("acct-1", h.runtime);
    expect(
      await enqueueDelivery({ visitId: "v-local-1", visit: VISIT, body: BODY }, receipt()),
    ).toBe(true);
    expect(deliveryOf("v-local-1")?.stage).toBe("queued");
    const [raw] = [...backend.blobBytes.values()];
    expect(isEncryptedEnvelope(JSON.parse(raw))).toBe(true);
    expect(raw).not.toContain("Göğüsümde");
    expect(raw).not.toContain("Kardiyoloji");
  });

  it("is restored from disk alone after a restart, then delivered on reconnect", async () => {
    const backend = fakeBackend();
    const first = harness(backend);
    await startDelivery("acct-1", first.runtime);
    await enqueueDelivery({ visitId: "v-local-1", visit: VISIT, body: BODY }, receipt());
    expect(deliveryOf("v-local-1")?.stage).toBe("queued");

    // the process dies: every byte of memory is gone, only "disk" remains
    stopDelivery();
    expect(deliveryOf("v-local-1")).toBeNull();

    const second = harness(backend);
    second.network.online = true;
    second.clock.now = T0 + BACKOFF.capMs;
    await startDelivery("acct-1", second.runtime);
    expect(deliveryOf("v-local-1")?.stage).toBe("delivered");
    expect(serverVisitIdOf("v-local-1")).toBe(SERVER);
  });

  it("never surfaces another account's queued note after a restart", async () => {
    const backend = fakeBackend();
    const first = harness(backend);
    await startDelivery("acct-1", first.runtime);
    await enqueueDelivery({ visitId: "v-local-1", visit: VISIT, body: BODY }, receipt());
    stopDelivery();
    const other = harness(backend);
    await startDelivery("acct-2", other.runtime);
    expect(deliveryOf("v-local-1")).toBeNull();
    expect(other.puts).toBe(0);
  });
});

describe("never drops a queued note", () => {
  it("keeps it through any number of failed passes, scheduling each retry", async () => {
    const backend = fakeBackend();
    const h = harness(backend);
    await startDelivery("acct-1", h.runtime);
    await enqueueDelivery({ visitId: "v-local-1", visit: VISIT, body: BODY }, receipt());
    for (let i = 0; i < 25; i += 1) {
      h.clock.now += BACKOFF.capMs;
      await runDueDeliveries();
    }
    expect(deliveryOf("v-local-1")?.stage).toBe("queued");
    expect(deliveryOf("v-local-1")?.body).toEqual(BODY);
    expect(h.timers.length).toBeGreaterThan(0);
    expect(Math.max(...h.timers)).toBeLessThanOrEqual(BACKOFF.capMs);
  });
});

describe("a server 4xx is surfaced and not retried forever", () => {
  it("stops calling the server after a refusal until the patient retries", async () => {
    const backend = fakeBackend();
    const h = harness(backend);
    h.network.online = true;
    h.network.answer = { kind: "refused", reason: "invalid" };
    await startDelivery("acct-1", h.runtime);
    await enqueueDelivery({ visitId: "v-local-1", visit: VISIT, body: BODY }, receipt());
    expect(deliveryOf("v-local-1")?.stage).toBe("refused");
    expect(deliveryOf("v-local-1")?.refusal).toBe("invalid");
    const after = h.puts;
    for (let i = 0; i < 10; i += 1) {
      h.clock.now += BACKOFF.capMs;
      await runDueDeliveries();
    }
    expect(h.puts).toBe(after);

    h.network.answer = { kind: "delivered" };
    await retryDelivery("v-local-1");
    expect(deliveryOf("v-local-1")?.stage).toBe("delivered");
  });
});

describe("no share without the grant", () => {
  it("refuses to queue without a share-scope receipt", async () => {
    const backend = fakeBackend();
    const h = harness(backend);
    await startDelivery("acct-1", h.runtime);
    const forged = { scope: "core", version: "v", textHash: "b".repeat(64) } as unknown;
    expect(
      await enqueueDelivery(
        { visitId: "v-local-1", visit: VISIT, body: BODY },
        forged as ShareGrantReceipt,
      ),
    ).toBe(false);
    expect(deliveryOf("v-local-1")).toBeNull();
    expect(backend.blobBytes.size).toBe(0);
  });

  it("a local withdrawal parks every queued note; a new receipt releases it", async () => {
    const backend = fakeBackend();
    const h = harness(backend);
    await startDelivery("acct-1", h.runtime);
    await enqueueDelivery({ visitId: "v-local-1", visit: VISIT, body: BODY }, receipt());
    await holdDeliveriesForConsent();
    expect(deliveryOf("v-local-1")?.stage).toBe("awaiting_consent");
    const before = h.puts;
    h.network.online = true;
    h.clock.now += BACKOFF.capMs;
    await runDueDeliveries();
    expect(h.puts).toBe(before);
    await reconfirmDelivery("v-local-1", receipt());
    expect(deliveryOf("v-local-1")?.stage).toBe("delivered");
  });
});

describe("taking a note back to a draft", () => {
  it("is allowed only where nothing can have reached the server", async () => {
    const backend = fakeBackend();
    const h = harness(backend);
    await startDelivery("acct-1", h.runtime);
    await enqueueDelivery({ visitId: "v-local-1", visit: VISIT, body: BODY }, receipt());
    expect(await discardUndelivered("v-local-1")).toBe(false);
    expect(deliveryOf("v-local-1")?.stage).toBe("queued");
    await holdDeliveriesForConsent();
    expect(await discardUndelivered("v-local-1")).toBe(true);
    expect(deliveryOf("v-local-1")).toBeNull();
    expect(backend.blobBytes.size).toBe(0);
  });
});

describe("no PHI in logs (invariant 6)", () => {
  it("a full run through every failure mode writes nothing to the console", async () => {
    const spies = (["log", "info", "warn", "error", "debug"] as const).map((level) =>
      vi.spyOn(console, level).mockImplementation(() => undefined),
    );
    const backend = fakeBackend();
    const h = harness(backend);
    await startDelivery("acct-1", h.runtime);
    await enqueueDelivery({ visitId: "v-local-1", visit: VISIT, body: BODY }, receipt());
    h.network.online = true;
    for (const answer of [
      { kind: "transient", retryAfterMs: 5 },
      { kind: "consent" },
      { kind: "refused", reason: "rejected" },
    ] as PutResult[]) {
      h.network.answer = answer;
      await retryDelivery("v-local-1");
      await reconfirmDelivery("v-local-1", receipt());
      h.clock.now += BACKOFF.capMs;
      await runDueDeliveries();
    }
    for (const spy of spies) {
      expect(spy).not.toHaveBeenCalled();
    }
  });
});

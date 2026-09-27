/**
 * INT-397 — the consent store says where the patient's own changes stand with
 * the server (WCAG 2.2 SC 4.1.3).
 *
 * The İzinleriniz screens show `consent.queue.note` ("applied on this device;
 * they will reach the server once a connection is available") while the
 * queue holds anything. That is also true for the moment every change is in
 * flight, and on every visit while a change waits. The outbox state tells
 * those apart: `sending` while a change made here is on its way, `held` once a
 * push did not land, `clear` when nothing waits. Only a move into `held` is
 * news; a retry that fails again is not a new one.
 *
 * The flush itself is unchanged: strictly in order, the first failure stops
 * the pass, and everything after it stays queued (INT-132).
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  consentOutbox,
  flushConsentQueue,
  ledgerSnapshot,
  resetLedger,
  seedLedgerForAccount,
  subscribeToLedger,
  withdrawLocal,
  type ConsentOutbox,
} from "./store";

const mocks = vi.hoisted(() => ({ authedFetch: vi.fn(), pushLands: { value: true } }));

vi.mock("@/lib/auth/api", () => ({ authedFetch: mocks.authedFetch }));

function answer(ok: boolean): Response {
  return { ok, status: ok ? 200 : 503, json: async () => ({}) } as unknown as Response;
}

/** The loader read is unreachable (the local state stands); a push lands or not. */
function server(): void {
  mocks.authedFetch.mockImplementation(async (path: string) =>
    path === "/v1/consents" ? answer(false) : answer(mocks.pushLands.value),
  );
}

/** Let every pending push and flush settle. */
async function settle(): Promise<void> {
  for (let i = 0; i < 10; i += 1) {
    await Promise.resolve();
  }
}

/** Every outbox state the screens are shown, in order, without repeats. */
function watchOutbox(): { seen: ConsentOutbox[]; stop: () => void } {
  const seen: ConsentOutbox[] = [consentOutbox()];
  const stop = subscribeToLedger(() => {
    const now = consentOutbox();
    if (seen[seen.length - 1] !== now) {
      seen.push(now);
    }
  });
  return { seen, stop };
}

const SEED = { core: true, voice: true, wellbeing: false, documents: true, health: false };

async function seeded(): Promise<void> {
  server();
  seedLedgerForAccount("hesap-1", SEED);
  await settle();
}

afterEach(() => {
  resetLedger();
  mocks.authedFetch.mockReset();
  mocks.pushLands.value = true;
});

describe("the outbox tells a change on its way from a change that waits (INT-397)", () => {
  it("a seeded account has nothing waiting", async () => {
    await seeded();
    expect(consentOutbox()).toBe("clear");
    expect(ledgerSnapshot().queue).toEqual([]);
  });

  it("a change the server takes at once is sending, then clear — never held", async () => {
    await seeded();
    const { seen, stop } = watchOutbox();
    withdrawLocal("documents");
    expect(consentOutbox()).toBe("sending");
    await settle();
    stop();
    expect(ledgerSnapshot().queue).toEqual([]);
    expect(seen).toEqual(["clear", "sending", "clear"]);
  });

  it("a change the server cannot take is held, and stays applied on this device", async () => {
    await seeded();
    mocks.pushLands.value = false;
    const { seen, stop } = watchOutbox();
    withdrawLocal("documents");
    await settle();
    stop();
    expect(seen).toEqual(["clear", "sending", "held"]);
    expect(ledgerSnapshot().queue).toHaveLength(1);
    expect(ledgerSnapshot().records.documents.granted).toBe(false);
  });

  it("a retry that fails again is not a new transition", async () => {
    await seeded();
    mocks.pushLands.value = false;
    withdrawLocal("documents");
    await settle();
    const { seen, stop } = watchOutbox();
    await flushConsentQueue();
    stop();
    expect(seen).toEqual(["held"]);
    expect(ledgerSnapshot().queue).toHaveLength(1);
  });

  it("a new change while one waits goes through sending again, so it is its own transition", async () => {
    await seeded();
    mocks.pushLands.value = false;
    withdrawLocal("documents");
    await settle();
    const { seen, stop } = watchOutbox();
    withdrawLocal("voice");
    await settle();
    stop();
    expect(seen).toEqual(["held", "sending", "held"]);
    expect(ledgerSnapshot().queue).toHaveLength(2);
  });

  it("the queue reaching the server clears it", async () => {
    await seeded();
    mocks.pushLands.value = false;
    withdrawLocal("documents");
    await settle();
    mocks.pushLands.value = true;
    await flushConsentQueue();
    expect(consentOutbox()).toBe("clear");
    expect(ledgerSnapshot().queue).toEqual([]);
  });

  it("signing out clears it with the working copy", async () => {
    await seeded();
    mocks.pushLands.value = false;
    withdrawLocal("documents");
    await settle();
    resetLedger();
    expect(consentOutbox()).toBe("clear");
  });
});

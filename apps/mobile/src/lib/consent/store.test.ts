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

import { shareView, viewOf } from "./ledger";
import {
  consentOutbox,
  flushConsentQueue,
  grantLocal,
  grantShareLocal,
  ledgerSeededFor,
  ledgerSnapshot,
  refreshLedgerFromServer,
  resetLedger,
  seedLedgerForAccount,
  subscribeToLedger,
  withdrawLocal,
  withdrawShareLocal,
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

describe("which account the working copy belongs to (INT-537)", () => {
  // The visit-start gate reads the ledger, and a ledger nobody seeded is a
  // fresh one: it would refuse a dev account that holds core. The screen
  // asks whether the copy is this account's before it refuses anything.
  it("is nobody's until an account seeds it", () => {
    expect(ledgerSeededFor("hesap-1")).toBe(false);
  });

  it("is the seeding account's, and only that account's", async () => {
    await seeded();
    expect(ledgerSeededFor("hesap-1")).toBe(true);
    expect(ledgerSeededFor("hesap-2")).toBe(false);
  });

  it("is nobody's again after sign-out", async () => {
    await seeded();
    resetLedger();
    expect(ledgerSeededFor("hesap-1")).toBe(false);
  });
});

/* ------------------------------------------------------------------ */
/* INT-587 legal review N5 — a refused grant cannot stall a withdrawal */
/* ------------------------------------------------------------------ */

describe("a grant the server refuses is an answer, not a wait (INT-587 N5)", () => {
  const HASH = "e".repeat(64);
  const TEXTS = [
    { purpose: "documents", version: "syn1", text_hash: HASH, body: "Deneme belge metni." },
    { purpose: "share", version: "syn1", text_hash: HASH, body: "Deneme paylaşım metni." },
  ];

  /** The snapshot serves texts; a grant answers `grantStatus`; everything else lands. */
  function serving(grantStatus: number): string[] {
    const posted: string[] = [];
    mocks.authedFetch.mockImplementation(async (path: string) => {
      if (path === "/v1/consents") {
        return {
          ok: true,
          status: 200,
          json: async () => ({ scopes: [], texts: TEXTS }),
        } as unknown as Response;
      }
      posted.push(path);
      const status = path.endsWith("/grant") ? grantStatus : 200;
      return { ok: status < 300, status, json: async () => ({}) } as unknown as Response;
    });
    return posted;
  }

  async function signedIn(grantStatus: number): Promise<string[]> {
    const posted = serving(grantStatus);
    seedLedgerForAccount("hesap-1", null);
    await refreshLedgerFromServer();
    return posted;
  }

  it("a 409 on the share grant is dropped, and the withdrawal behind it reaches the server", async () => {
    const posted = await signedIn(409);
    grantShareLocal("v-1");
    await settle();
    expect(await withdrawShareLocal()).toBe("landed");
    expect(posted).toEqual(["/v1/consents/grant", "/v1/consents/withdraw"]);
    expect(ledgerSnapshot().queue).toEqual([]);
  });

  it("a refused share grant is asked again: the phone no longer counts it as given", async () => {
    await signedIn(409);
    grantShareLocal("v-1");
    await settle();
    await flushConsentQueue();
    expect(shareView(ledgerSnapshot()).standing).toBe("unknown");
  });

  it("a 422 on a purpose grant is dropped and the purpose is offered again", async () => {
    await signedIn(422);
    grantLocal("documents");
    await settle();
    await flushConsentQueue();
    const documents = viewOf(ledgerSnapshot()).find((view) => view.id === "documents");
    expect(documents?.allowed).toBe(false);
    expect(documents?.grantable).toBe(true);
    expect(ledgerSnapshot().queue).toEqual([]);
  });

  it("near miss: a 503 is a wait — the grant stays queued and the outbox holds", async () => {
    await signedIn(503);
    grantShareLocal("v-1");
    await settle();
    await flushConsentQueue();
    expect(ledgerSnapshot().queue).toHaveLength(1);
    expect(consentOutbox()).toBe("held");
  });
});

/* ------------------------------------------------------------------ */
/* INT-589 — a withdrawal is reported as done only when it landed       */
/* ------------------------------------------------------------------ */

describe("a withdrawal the server refuses is reported as not done (INT-589)", () => {
  const HASH = "f".repeat(64);
  const TEXTS = [
    { purpose: "share", version: "syn1", text_hash: HASH, body: "Deneme paylaşım metni." },
  ];

  /** Grants land; a withdrawal answers `withdrawStatus`. */
  async function signedIn(withdrawStatus: number): Promise<void> {
    mocks.authedFetch.mockImplementation(async (path: string) => {
      if (path === "/v1/consents") {
        return {
          ok: true,
          status: 200,
          json: async () => ({ scopes: [], texts: TEXTS }),
        } as unknown as Response;
      }
      const status = path.endsWith("/withdraw") ? withdrawStatus : 200;
      return { ok: status < 300, status, json: async () => ({}) } as unknown as Response;
    });
    seedLedgerForAccount("hesap-2", null);
    await refreshLedgerFromServer();
    grantShareLocal("v-1", "2026-10-30T10:00:00.000Z");
    await settle();
    await flushConsentQueue();
  }

  it("a landed withdrawal says landed", async () => {
    await signedIn(200);
    expect(await withdrawShareLocal("2026-10-30T11:00:00.000Z")).toBe("landed");
    expect(shareView(ledgerSnapshot()).standing).toBe("withdrawn");
  });

  it("a refused withdrawal says refused, never landed", async () => {
    await signedIn(409);
    expect(await withdrawShareLocal("2026-10-30T11:00:00.000Z")).toBe("refused");
    expect(ledgerSnapshot().queue).toEqual([]);
  });

  it("after a refusal the withdrawal is offered again, and unsent notes stay held", async () => {
    await signedIn(422);
    await withdrawShareLocal("2026-10-30T11:00:00.000Z");
    const share = ledgerSnapshot().share;
    // the server's record is not known to be withdrawn: the control comes back
    expect(share.standing).toBe("unknown");
    // but the phone keeps the instant, so a note granted before it stays parked
    expect(share.withdrawnAt).toBe("2026-10-30T11:00:00.000Z");
  });

  it("near miss: a withdrawal still waiting for the server says unsent", async () => {
    await signedIn(503);
    expect(await withdrawShareLocal("2026-10-30T11:00:00.000Z")).toBe("unsent");
    expect(ledgerSnapshot().queue).toHaveLength(1);
  });
});

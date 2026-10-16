/**
 * INT-475 — the patient's answer to the one location question reaches the server
 * (files/02 §5.3 Axis 3; files/04 §8.1 rule 7; LD-05; CLAUDE.md invariants 6, 21).
 *
 * "Şu anda hastanede misiniz?" — "evet" sends the RED to ON_SITE, where staff are
 * notified automatically; "hayır" to REMOTE. The answer is posted to
 * `/v1/triage/red-location`, ids and the branch only, fire-and-forget with retry:
 * the RED is already on the screen and nothing on it waits for this request. A
 * late "evet" after the no-answer wait (LD-05) is posted then. The wait's own
 * expiry is not the patient's answer, and is not posted. Never twice.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import type { RedTrigger } from "../livekit/types";
import { decodeRedCatalog, type HopTransport, type PrePositionedRed, type RedOrigin } from "./hop";
import {
  createLocationReporter,
  LOCATION_PATH,
  LOCATION_REPORT_MAX_ATTEMPTS,
  LOCATION_REPORT_TIMEOUT_MS,
  locationReportFor,
  subscribeLocationReports,
} from "./locationReport";
import { createRedStore, redScreen } from "./store";

const FIXTURES = join(__dirname, "..", "..", "..", "..", "..", "tests", "fixtures", "triage_hop");
const CATALOG = decodeRedCatalog(
  new Uint8Array(readFileSync(join(FIXTURES, "red_catalog.json"))),
) as PrePositionedRed;
const ORIGIN: RedOrigin = { sessionId: "visit-1", visitId: "visit-1" };

function trigger(
  location: RedTrigger["location"],
  register: RedTrigger["register"] = "ALERT",
): RedTrigger {
  return {
    kind: "red_trigger",
    ruleId: "rf.sentetik_yasamsal",
    register,
    location,
    scriptId: `rf.sentetik_yasamsal.${location.toLowerCase()}`,
  };
}

interface Sent {
  readonly path: string;
  readonly body: unknown;
}

/** A server that answers each call with the next status (the last repeats). */
function server(statuses: readonly (number | "throw")[]) {
  const sent: Sent[] = [];
  const transport: HopTransport = async (path, body) => {
    sent.push({ path, body: JSON.parse(body ?? "null") as unknown });
    const status = statuses[Math.min(sent.length, statuses.length) - 1];
    if (status === "throw") {
      throw new Error("network down");
    }
    return { status, bytes: new Uint8Array() };
  };
  return { sent, transport };
}

/** Sleeps that record the wait and return at once. */
function sleeps() {
  const waited: number[] = [];
  return { waited, sleep: async (ms: number) => void waited.push(ms) };
}

/** Let every queued retry run. */
async function settle(): Promise<void> {
  for (let i = 0; i < 200; i += 1) {
    await Promise.resolve();
  }
}

/** A request deadline that never expires on its own: the test decides. */
const NEVER = () => ({ expired: new Promise<void>(() => undefined), cancel: () => undefined });

function rig(statuses: readonly (number | "throw")[] = [202]) {
  const store = createRedStore();
  const { sent, transport } = server(statuses);
  const { waited, sleep } = sleeps();
  const reporter = createLocationReporter({
    transport,
    sleep,
    jitter: () => 0.5,
    timeout: NEVER,
  });
  const unsubscribe = subscribeLocationReports(store, reporter);
  return { store, sent, waited, reporter, unsubscribe };
}

const ON_SITE_BODY = {
  session_id: "visit-1",
  visit_id: "visit-1",
  rule_id: "rf.sentetik_yasamsal",
  location: "ON_SITE",
};

describe("INT-475 — what the answer says, and only that", () => {
  it("evet is ON_SITE and hayır is REMOTE, with the RED's ids and nothing else", () => {
    const store = createRedStore();
    store.present(trigger("UNKNOWN"), CATALOG, ORIGIN);
    expect(locationReportFor(store.getSnapshot())).toBeNull(); // asked, not answered
    store.answerLocation("inHospital");
    const report = locationReportFor(store.getSnapshot());
    expect(report).toEqual(ON_SITE_BODY);
    expect(Object.keys(report ?? {}).sort()).toEqual([
      "location",
      "rule_id",
      "session_id",
      "visit_id",
    ]);
    const no = createRedStore();
    no.present(trigger("UNKNOWN"), CATALOG, ORIGIN);
    no.answerLocation("notInHospital");
    expect(locationReportFor(no.getSnapshot())).toEqual({ ...ON_SITE_BODY, location: "REMOTE" });
  });

  it("near miss: the wait's expiry is not the patient's answer, and nothing is reported", () => {
    const store = createRedStore();
    store.present(trigger("UNKNOWN"), CATALOG, ORIGIN);
    store.answerLocation("noAnswer");
    expect(redScreen(store.getSnapshot())).toMatchObject({ kind: "act", location: "REMOTE" });
    expect(locationReportFor(store.getSnapshot())).toBeNull();
  });

  it.each(["REMOTE", "ON_SITE"] as const)(
    "near miss: a RED that arrived at %s asked nothing, so there is no answer",
    (location) => {
      const store = createRedStore();
      store.present(trigger(location), CATALOG, ORIGIN);
      store.answerLocation("inHospital"); // refused by the store: no question stands
      expect(locationReportFor(store.getSnapshot())).toBeNull();
      expect(locationReportFor(null)).toBeNull();
    },
  );
});

describe("INT-475 — the answer reaches the server, fire-and-forget", () => {
  it("evet is posted once to the location route", async () => {
    const h = rig();
    h.store.present(trigger("UNKNOWN"), CATALOG, ORIGIN);
    expect(h.sent).toEqual([]);
    h.store.answerLocation("inHospital");
    await settle();
    expect(h.sent).toEqual([{ path: LOCATION_PATH, body: ON_SITE_BODY }]);
  });

  it("a late evet after the no-answer branch is posted then (LD-05), once", async () => {
    const h = rig();
    h.store.present(trigger("UNKNOWN", "CALM"), CATALOG, ORIGIN);
    h.store.answerLocation("noAnswer");
    await settle();
    expect(h.sent).toEqual([]); // REMOTE by the wait: nothing the patient said
    h.store.answerLocation("inHospital");
    h.store.answerLocation("inHospital"); // a second tap
    await settle();
    expect(h.sent).toEqual([{ path: LOCATION_PATH, body: ON_SITE_BODY }]);
  });

  it("hayır is posted as REMOTE, and the store keeps the patient's answer final", async () => {
    const h = rig();
    h.store.present(trigger("UNKNOWN", "SILENT"), CATALOG, ORIGIN);
    h.store.answerLocation("notInHospital");
    h.store.answerLocation("inHospital"); // refused: the patient's answer is final
    await settle();
    expect(h.sent).toEqual([
      { path: LOCATION_PATH, body: { ...ON_SITE_BODY, location: "REMOTE" } },
    ]);
  });

  it("the RED paints first: nothing waits on the request, which is still in flight", () => {
    const store = createRedStore();
    const pending: Sent[] = [];
    const reporter = createLocationReporter({
      transport: (path, body) => {
        pending.push({ path, body });
        return new Promise(() => undefined); // the server never answers
      },
      timeout: NEVER,
    });
    subscribeLocationReports(store, reporter);
    store.present(trigger("UNKNOWN"), CATALOG, ORIGIN);
    store.answerLocation("inHospital");
    // The screen moved to ON_SITE synchronously, with the request unanswered.
    expect(redScreen(store.getSnapshot())).toMatchObject({
      kind: "act",
      location: "ON_SITE",
      call112: false,
    });
    expect(pending).toHaveLength(1);
  });

  it("retries a refused or failed delivery with backoff, and stops at the first acceptance", async () => {
    const h = rig(["throw", 503, 429, 202]);
    h.store.present(trigger("UNKNOWN"), CATALOG, ORIGIN);
    h.store.answerLocation("inHospital");
    await settle();
    expect(h.sent).toHaveLength(4);
    expect(h.waited).toHaveLength(3);
    expect(h.sent.every((call) => call.path === LOCATION_PATH)).toBe(true);
  });

  it("a request that hangs is abandoned at its deadline and offered again", async () => {
    const store = createRedStore();
    const sent: string[] = [];
    const expire: (() => void)[] = [];
    const deadlines: number[] = [];
    const reporter = createLocationReporter({
      transport: async (path) => {
        sent.push(path);
        if (sent.length === 1) {
          return new Promise(() => undefined); // the first request hangs
        }
        return { status: 202, bytes: new Uint8Array() };
      },
      sleep: async () => undefined,
      timeout: (ms) => {
        deadlines.push(ms);
        let fire: () => void = () => undefined;
        const expired = new Promise<void>((resolve) => {
          fire = resolve;
        });
        expire.push(fire);
        return { expired, cancel: () => undefined };
      },
    });
    subscribeLocationReports(store, reporter);
    store.present(trigger("UNKNOWN"), CATALOG, ORIGIN);
    store.answerLocation("inHospital");
    await settle();
    expect(sent).toEqual([LOCATION_PATH]); // waiting on the hung request
    expect(deadlines).toEqual([LOCATION_REPORT_TIMEOUT_MS]);
    expire[0]();
    await settle();
    expect(sent).toEqual([LOCATION_PATH, LOCATION_PATH]);
    // Near miss: the second was accepted, so nothing more is sent.
    expire[1]?.();
    await settle();
    expect(sent).toHaveLength(2);
  });

  it("gives up after the bounded attempts, never forever", async () => {
    const h = rig([503]);
    h.store.present(trigger("UNKNOWN"), CATALOG, ORIGIN);
    h.store.answerLocation("inHospital");
    await settle();
    expect(h.sent).toHaveLength(LOCATION_REPORT_MAX_ATTEMPTS);
    expect(h.waited).toHaveLength(LOCATION_REPORT_MAX_ATTEMPTS - 1);
  });

  it("near miss: a request the server refuses as malformed is not retried", async () => {
    const h = rig([422]);
    h.store.present(trigger("UNKNOWN"), CATALOG, ORIGIN);
    h.store.answerLocation("inHospital");
    await settle();
    expect(h.sent).toHaveLength(1);
    expect(h.waited).toEqual([]);
  });

  it("stops listening when unsubscribed", async () => {
    const h = rig();
    h.unsubscribe();
    h.store.present(trigger("UNKNOWN"), CATALOG, ORIGIN);
    h.store.answerLocation("inHospital");
    await settle();
    expect(h.sent).toEqual([]);
  });
});

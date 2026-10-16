/**
 * INT-465: CD-24 `generic_red_unknown_no_answer_goes_remote`, driven on a fake
 * clock through the real store.
 *
 * Under UNKNOWN the location question is asked with no 112 control. When it is
 * still unanswered at the end of the unsigned wait, the store takes the rule's
 * no-answer branch: REMOTE, with the 112 control. The near misses:
 * - one millisecond short of the wait, nothing has changed;
 * - an answered question is never overridden by the clock;
 * - a cancelled clock does nothing.
 * And the patient's own answer, given after the wait, still lands (LD-05).
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { GENERIC_RED_SCRIPT_IDS } from "../livekit/red";
import { decodeRedCatalog, type PrePositionedRed, type RedOrigin } from "./hop";
import { startNoAnswerClock, type NoAnswerTimers } from "./noAnswerClock";
import { createRedStore, redScreen, UNSIGNED_LOCATION_NO_ANSWER_WAIT_MS } from "./store";

const FIXTURES = join(__dirname, "..", "..", "..", "..", "..", "tests", "fixtures", "triage_hop");
const CATALOG = decodeRedCatalog(
  new Uint8Array(readFileSync(join(FIXTURES, "red_catalog.json"))),
) as PrePositionedRed;
const ORIGIN: RedOrigin = { sessionId: "visit-1", visitId: "visit-1" };

/** A fake clock: timers run only when the test advances time. */
function fakeTimers(): NoAnswerTimers & { advance: (ms: number) => void } {
  let now = 0;
  let next = 0;
  const due = new Map<number, { at: number; run: () => void }>();
  return {
    set: (run, ms) => {
      next += 1;
      due.set(next, { at: now + ms, run });
      return next;
    },
    clear: (handle) => {
      due.delete(handle as number);
    },
    advance: (ms) => {
      now += ms;
      for (const [id, timer] of [...due]) {
        if (timer.at <= now) {
          due.delete(id);
          timer.run();
        }
      }
    },
  };
}

function asked(register: "ALERT" | "CALM" | "SILENT") {
  const store = createRedStore();
  store.present(
    {
      kind: "red_trigger",
      ruleId: "rf.not.on.device",
      register,
      location: "UNKNOWN",
      scriptId: "rf.not.on.device.unknown",
    },
    CATALOG,
    ORIGIN,
  );
  return store;
}

describe("CD-24 generic_red_unknown_no_answer_goes_remote — the clock", () => {
  for (const register of ["ALERT", "CALM", "SILENT"] as const) {
    it(`${register}: no answer at the end of the wait shows REMOTE with 112`, () => {
      const store = asked(register);
      const timers = fakeTimers();
      startNoAnswerClock(store, timers);
      timers.advance(UNSIGNED_LOCATION_NO_ANSWER_WAIT_MS - 1);
      expect(redScreen(store.getSnapshot()).kind).toBe("ask"); // near miss: not yet
      timers.advance(1);
      expect(redScreen(store.getSnapshot())).toMatchObject({
        kind: "act",
        location: "REMOTE",
        call112: true,
        actionTr: CATALOG.scripts[GENERIC_RED_SCRIPT_IDS.REMOTE].actionTr,
      });
    });
  }

  it("an answer given before the wait ends is never overridden", () => {
    const store = asked("ALERT");
    const timers = fakeTimers();
    startNoAnswerClock(store, timers);
    store.answerLocation("inHospital");
    timers.advance(UNSIGNED_LOCATION_NO_ANSWER_WAIT_MS);
    expect(redScreen(store.getSnapshot())).toMatchObject({ location: "ON_SITE", call112: false });
  });

  // LD-05 (INT-471, #800): the Essential Exception holds only if a late answer lands.
  it("an answer given after the wait still lands — ON_SITE, without 112", () => {
    const store = asked("ALERT");
    const timers = fakeTimers();
    startNoAnswerClock(store, timers);
    timers.advance(UNSIGNED_LOCATION_NO_ANSWER_WAIT_MS);
    expect(redScreen(store.getSnapshot())).toMatchObject({ location: "REMOTE", call112: true });
    store.answerLocation("inHospital");
    expect(redScreen(store.getSnapshot())).toMatchObject({ location: "ON_SITE", call112: false });
  });

  it("a cancelled clock does nothing", () => {
    const store = asked("CALM");
    const timers = fakeTimers();
    startNoAnswerClock(store, timers)();
    timers.advance(UNSIGNED_LOCATION_NO_ANSWER_WAIT_MS * 2);
    expect(redScreen(store.getSnapshot()).kind).toBe("ask");
  });
});

/**
 * INT-409: "today" comes from an injected clock, and the calendar day is the
 * day in Europe/Istanbul.
 *
 * Acceptance (verbatim): "'today' comes from an injectable clock (the device
 * date in the app's time zone, Europe/Istanbul for date boundaries); tests
 * inject a fixed clock; no build contains a pinned date".
 *
 * Every clock here is fixed, so no assertion depends on the day the suite runs.
 * The source guard that no build pins a date is e2e/pinnedToday.spec.ts.
 */
import { describe, expect, it } from "vitest";

import { initialMonth, initialSelectedDay, pastVisitsRecentFirst } from "./calendar";
import { APP_TIME_ZONE, deviceClock, isoDateIn, todayIso, type Clock } from "./clock";
import { splitVisits } from "./visits";

/** A clock that always answers `iso`, the only kind a test may use. */
const fixedClock =
  (iso: string): Clock =>
  () =>
    new Date(iso);

describe("the app's calendar day is the day in Europe/Istanbul", () => {
  it("names the zone once, for every date boundary", () => {
    expect(APP_TIME_ZONE).toBe("Europe/Istanbul");
  });

  it("the last second before midnight in Istanbul is still that day", () => {
    // 20:59:59 UTC is 23:59:59 in Istanbul (UTC+3, no daylight saving)
    expect(isoDateIn(new Date("2026-10-01T20:59:59Z"))).toBe("2026-10-01");
  });

  it("midnight in Istanbul is the next day, while UTC still says the old one", () => {
    const instant = new Date("2026-10-01T21:00:00Z");
    expect(isoDateIn(instant)).toBe("2026-10-02");
    // near miss: the UTC reading the records screen used to take is a day behind
    expect(instant.toISOString().slice(0, 10)).toBe("2026-10-01");
  });

  it("crosses a year boundary in the zone, not in UTC", () => {
    expect(isoDateIn(new Date("2026-12-31T21:30:00Z"))).toBe("2027-01-01");
  });

  it("reads another zone only when one is named", () => {
    expect(isoDateIn(new Date("2026-10-01T21:00:00Z"), "UTC")).toBe("2026-10-01");
  });

  it("pads month and day to the ISO shape the visits store uses", () => {
    expect(isoDateIn(new Date("2027-01-04T09:00:00Z"))).toMatch(/^2027-01-04$/);
  });
});

describe("today is read from the clock it is given", () => {
  it("a fixed clock gives a fixed day", () => {
    expect(todayIso(fixedClock("2026-10-01T09:00:00Z"))).toBe("2026-10-01");
  });

  it("two clocks give two days: the answer is not pinned", () => {
    const early = todayIso(fixedClock("2026-08-27T09:00:00Z"));
    const later = todayIso(fixedClock("2026-10-15T09:00:00Z"));
    expect(early).toBe("2026-08-27");
    expect(later).toBe("2026-10-15");
  });

  it("the device clock is the real current instant", () => {
    const before = Date.now();
    const read = deviceClock().getTime();
    expect(read).toBeGreaterThanOrEqual(before);
    expect(read).toBeLessThanOrEqual(Date.now());
  });
});

// Vizitlerim's four readings of "today", driven by an injected clock.
const VISITS = [
  { id: "yesterday", date: "2026-10-01" },
  { id: "today", date: "2026-10-02" },
  { id: "next-week", date: "2026-10-09" },
  { id: "unbooked", date: null },
] as const;

const ids = (visits: readonly { id: string }[]) => visits.map((visit) => visit.id);

describe("Vizitlerim splits visits on the clock's day", () => {
  // 00:30 in Istanbul on 2 October: a patient opening the app just after
  // midnight sees yesterday's visit as past, today's as upcoming.
  const justAfterMidnight = fixedClock("2026-10-01T21:30:00Z");

  it("upcoming holds today, next week and the unbooked visit; past holds yesterday", () => {
    const { upcoming, past } = splitVisits(VISITS, todayIso(justAfterMidnight));
    expect(ids(upcoming)).toEqual(["today", "next-week", "unbooked"]);
    expect(ids(past)).toEqual(["yesterday"]);
    expect(ids(pastVisitsRecentFirst(VISITS, todayIso(justAfterMidnight)))).toEqual(["yesterday"]);
  });

  it("the calendar opens on the soonest visit from the clock's day", () => {
    const today = todayIso(justAfterMidnight);
    expect(initialSelectedDay(VISITS, today)).toBe("2026-10-02");
    expect(initialMonth(VISITS, today)).toEqual({ year: 2026, month: 9 });
  });

  it("a later clock moves next week's visit into the past", () => {
    // the defect: a pinned date gave the same split whatever the real day was
    const { upcoming, past } = splitVisits(VISITS, todayIso(fixedClock("2026-10-20T09:00:00Z")));
    expect(ids(upcoming)).toEqual(["unbooked"]);
    expect(ids(past)).toEqual(["yesterday", "today", "next-week"]);
  });

  it("with no visit ahead, the calendar opens on the clock's own day and month", () => {
    const today = todayIso(fixedClock("2026-11-03T09:00:00Z"));
    expect(initialSelectedDay(VISITS, today)).toBe("2026-11-03");
    expect(initialMonth(VISITS, today)).toEqual({ year: 2026, month: 10 });
  });
});

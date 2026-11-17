/**
 * Calendar model (02 §4 takvim view): month-grid arithmetic, the visit-per-day
 * counts, the past-visit ordering and the Intl-backed date names. Pure node —
 * the RN component that renders this is exercised by the screen tests.
 */
import { describe, expect, it } from "vitest";

import {
  addMonths,
  buildCalendarGrid,
  countVisitsByDay,
  daysInMonth,
  initialMonth,
  initialSelectedDay,
  longDate,
  monthOf,
  monthTitle,
  parseIso,
  pastVisitsRecentFirst,
  sameMonth,
  toIso,
  visitsOnDay,
  weekdayHeaders,
} from "./calendar";

const TODAY = "2026-08-27";

// two dated visits, one dateless (not on the calendar), one duplicate day
const VISITS = [
  { id: "a", date: "2026-09-05" },
  { id: "b", date: "2026-09-05" },
  { id: "c", date: "2026-05-12" },
  { id: "d", date: null },
] as const;

describe("iso helpers", () => {
  it("pads and round-trips", () => {
    expect(toIso(2026, 8, 5)).toBe("2026-09-05");
    expect(toIso(2026, 0, 1)).toBe("2026-01-01");
    expect(parseIso("2026-09-05")).toEqual({ year: 2026, month: 8, day: 5 });
    expect(monthOf("2026-09-05")).toEqual({ year: 2026, month: 8 });
  });
});

describe("addMonths / sameMonth", () => {
  it("carries across year boundaries in both directions", () => {
    expect(addMonths({ year: 2026, month: 11 }, 1)).toEqual({ year: 2027, month: 0 });
    expect(addMonths({ year: 2026, month: 0 }, -1)).toEqual({ year: 2025, month: 11 });
    expect(addMonths({ year: 2026, month: 8 }, -13)).toEqual({ year: 2025, month: 7 });
  });

  it("compares year+month", () => {
    expect(sameMonth({ year: 2026, month: 8 }, { year: 2026, month: 8 })).toBe(true);
    expect(sameMonth({ year: 2026, month: 8 }, { year: 2027, month: 8 })).toBe(false);
  });
});

describe("daysInMonth", () => {
  it("handles leap February and 30/31-day months", () => {
    expect(daysInMonth(2024, 1)).toBe(29); // leap
    expect(daysInMonth(2026, 1)).toBe(28);
    expect(daysInMonth(2026, 8)).toBe(30); // September
    expect(daysInMonth(2026, 0)).toBe(31);
  });
});

describe("countVisitsByDay", () => {
  it("sums per day and skips dateless visits", () => {
    const counts = countVisitsByDay(VISITS);
    expect(counts.get("2026-09-05")).toBe(2);
    expect(counts.get("2026-05-12")).toBe(1);
    expect(counts.size).toBe(2); // the null date created no key
  });
});

describe("buildCalendarGrid", () => {
  const grid = buildCalendarGrid({ year: 2026, month: 8 }, TODAY, countVisitsByDay(VISITS));

  it("is a Monday-first six-by-seven grid", () => {
    expect(grid.weeks).toHaveLength(6);
    for (const week of grid.weeks) {
      expect(week).toHaveLength(7);
    }
  });

  it("spills the leading days of September 2026 from August", () => {
    // 2026-09-01 is a Tuesday, so Monday col 0 is 2026-08-31
    expect(grid.weeks[0][0]).toMatchObject({ iso: "2026-08-31", inMonth: false });
    expect(grid.weeks[0][1]).toMatchObject({ iso: "2026-09-01", inMonth: true, day: 1 });
  });

  it("marks the visit day with its count and leaves empty days at zero", () => {
    const sep5 = grid.weeks[0][5];
    expect(sep5).toMatchObject({ iso: "2026-09-05", inMonth: true, visitCount: 2 });
    expect(grid.weeks[0][2].visitCount).toBe(0); // 2026-09-02
  });

  it("marks today only in the month that holds it", () => {
    const augGrid = buildCalendarGrid({ year: 2026, month: 7 }, TODAY, new Map());
    const flatAug = augGrid.weeks.flat().filter((cell) => cell.isToday);
    expect(flatAug).toHaveLength(1);
    expect(flatAug[0].iso).toBe(TODAY);
    // September has no "today" cell
    expect(grid.weeks.flat().some((cell) => cell.isToday)).toBe(false);
  });
});

describe("visitsOnDay", () => {
  it("returns just that day's visits", () => {
    expect(visitsOnDay(VISITS, "2026-09-05").map((v) => v.id)).toEqual(["a", "b"]);
    expect(visitsOnDay(VISITS, "2026-09-06")).toEqual([]);
  });
});

describe("pastVisitsRecentFirst", () => {
  it("keeps dated past visits, most recent first, dropping today/future/dateless", () => {
    const past = pastVisitsRecentFirst(
      [
        { id: "old", date: "2026-01-10" },
        { id: "mid", date: "2026-05-12" },
        { id: "today", date: TODAY },
        { id: "future", date: "2026-09-05" },
        { id: "nodate", date: null },
      ],
      TODAY,
    );
    expect(past.map((v) => v.id)).toEqual(["mid", "old"]);
  });
});

describe("initial month / selected day", () => {
  it("opens on the soonest upcoming booked visit", () => {
    expect(initialMonth(VISITS, TODAY)).toEqual({ year: 2026, month: 8 });
    expect(initialSelectedDay(VISITS, TODAY)).toBe("2026-09-05");
  });

  it("falls back to today when there is no upcoming booked visit", () => {
    const onlyPast = [
      { id: "c", date: "2026-05-12" },
      { id: "d", date: null },
    ];
    expect(initialMonth(onlyPast, TODAY)).toEqual({ year: 2026, month: 7 });
    expect(initialSelectedDay(onlyPast, TODAY)).toBe(TODAY);
  });
});

describe("localized date names (Intl)", () => {
  it("names the month and year", () => {
    expect(monthTitle({ year: 2026, month: 8 }, "tr")).toContain("Eylül");
    expect(monthTitle({ year: 2026, month: 8 }, "tr")).toContain("2026");
    expect(monthTitle({ year: 2026, month: 8 }, "en")).toBe("September 2026");
  });

  it("gives seven Monday-first weekday headers", () => {
    const en = weekdayHeaders("en");
    expect(en).toHaveLength(7);
    expect(en[0]).toBe("Mon");
    expect(en[6]).toBe("Sun");
    expect(weekdayHeaders("tr")).toHaveLength(7);
  });

  it("spells a full spoken date", () => {
    expect(longDate("2026-09-05", "tr")).toContain("Eylül");
    expect(longDate("2026-09-05", "en")).toContain("September");
  });
});

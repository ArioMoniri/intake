/**
 * INT-400 — the device reads one printed date by the server's rule.
 *
 * Every `printed` row of tests/fixtures/records/mhrs_dates.json goes through
 * `parsePrintedDate` here and through the server's `parse_printed_date` in
 * tests/records/test_mhrs.py. The rule is not restated in this file: the rows
 * are the rule, and the server is the side they were written from.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { parsePrintedDate, type DateOrder, type PrintedDate } from "./turkishDates";

type Expect = { date: string } | { refusal: "ambiguous" | "not_found" | "unreadable" };

interface PrintedRow {
  id: string;
  printed: string;
  order: DateOrder | null;
  expect: Expect;
}

const TABLE = JSON.parse(
  readFileSync(
    join(
      __dirname,
      "..",
      "..",
      "..",
      "..",
      "..",
      "tests",
      "fixtures",
      "records",
      "mhrs_dates.json",
    ),
    "utf8",
  ),
) as { printed: PrintedRow[] };

/** The fixture's spelling of one device read. */
function outcome(read: PrintedDate): Expect {
  return read.ok ? { date: read.iso } : { refusal: read.refusal };
}

describe("parsePrintedDate reads every shared row as the server does", () => {
  it.each(TABLE.printed.map((row) => [row.id, row] as const))("%s", (_id, row) => {
    expect(outcome(parsePrintedDate(row.printed, row.order))).toEqual(row.expect);
  });
});

describe("the device never guesses a date that reads two ways", () => {
  it("refuses 03.09.2026 with no order, and reads it either way only when an order is stated", () => {
    expect(parsePrintedDate("03.09.2026")).toEqual({ ok: false, refusal: "ambiguous" });
    expect(parsePrintedDate("03.09.2026", "day_first")).toEqual({ ok: true, iso: "2026-09-03" });
    expect(parsePrintedDate("03.09.2026", "month_first")).toEqual({ ok: true, iso: "2026-03-09" });
  });

  it("never throws, whatever it is handed", () => {
    for (const printed of [
      "",
      " ",
      "saat 14:30",
      "03.09",
      "9999.99.99",
      "\u{1D7D9}\u{1D7DB}.09.2026",
    ]) {
      expect(() => parsePrintedDate(printed)).not.toThrow();
    }
  });
});

import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import {
  NBSP,
  buildSummary,
  formatQuantity,
  formatRange,
  lastSevenDayRange,
  summaryNoteLines,
} from "./format";

describe("formatQuantity — invariant 22 display discipline", () => {
  it("never groups digits (useGrouping:false)", () => {
    expect(formatQuantity(12345, "adım", "tr")).toBe(`12345${NBSP}adım`);
    expect(formatQuantity(12345, "steps", "en")).toBe(`12345${NBSP}steps`);
  });

  it("number + unit is ONE non-breaking atom (no plain space after a digit)", () => {
    const value = formatQuantity(7842, "adım", "tr");
    expect(value).toContain(NBSP);
    expect(value).not.toMatch(/\d /u);
  });

  it("decimals follow the locale — comma in Turkish, dot in English", () => {
    expect(formatQuantity(6.4, "saat", "tr")).toBe(`6,4${NBSP}saat`);
    expect(formatQuantity(6.4, "h", "en")).toBe(`6.4${NBSP}h`);
  });

  it("writes every digit the value has, and adds none (INT-385)", () => {
    // A cap of one fraction digit printed 0.05 as 0,1: a clinical quantity
    // rounded on its way to the screen.
    expect(formatQuantity(0.05, "mg/L", "tr")).toBe(`0,05${NBSP}mg/L`);
    expect(formatQuantity(1.25, "mg", "en")).toBe(`1.25${NBSP}mg`);
    // No exponent at either end of the range.
    expect(formatQuantity(5e-7, "g", "tr")).toBe(`0,0000005${NBSP}g`);
    expect(formatQuantity(1e21, "g", "en")).toBe(`1000000000000000000000${NBSP}g`);
  });
});

describe("formatRange", () => {
  it("joins with an en dash and carries the unit once, non-breaking", () => {
    expect(formatRange(58, 64, "atım/dk", "tr")).toBe(`58–64${NBSP}atım/dk`);
  });

  it("collapses a degenerate range to a single quantity", () => {
    expect(formatRange(62, 62, "atım/dk", "tr")).toBe(`62${NBSP}atım/dk`);
  });
});

describe("lastSevenDayRange", () => {
  it("spans seven calendar days ending now", () => {
    const now = new Date("2026-08-28T10:00:00.000Z");
    const range = lastSevenDayRange(now);
    expect(new Date(range.endISO).getTime()).toBe(now.getTime());
    const days = (now.getTime() - new Date(range.startISO).getTime()) / 86_400_000;
    expect(days).toBeGreaterThanOrEqual(6);
    expect(days).toBeLessThanOrEqual(7);
  });
});

describe("buildSummary — raw device samples to display strings", () => {
  const raw = {
    stepsByDay: [
      { dateISO: "2026-08-21", count: 4180 },
      { dateISO: "2026-08-22", count: 12345 },
    ],
    restingHeartRateBpm: [64, 58, 61],
    sleepSessions: [
      { endDateISO: "2026-08-22", minutes: 402 },
      { endDateISO: "2026-08-23", minutes: 366 },
    ],
  };

  it("formats daily step totals without grouping, unit attached", () => {
    const summary = buildSummary(raw, "tr");
    expect(summary.steps).toEqual([
      { dateISO: "2026-08-21", value: `4180${NBSP}adım` },
      { dateISO: "2026-08-22", value: `12345${NBSP}adım` },
    ]);
  });

  it("resting heart rate is the observed min–max range", () => {
    expect(buildSummary(raw, "tr").restingHeartRate).toBe(`58–64${NBSP}atım/dk`);
  });

  it("sleep is the nightly average in hours, one decimal, locale decimals", () => {
    // (402 + 366) / 2 nights = 384 min = 6.4 h
    expect(buildSummary(raw, "tr").sleepHours).toBe(`6,4${NBSP}saat`);
  });

  it("absent data stays absent — no invented values (CLAUDE.md: never invent)", () => {
    const empty = buildSummary(
      { stepsByDay: [], restingHeartRateBpm: [], sleepSessions: [] },
      "tr",
    );
    expect(empty.steps).toEqual([]);
    expect(empty.restingHeartRate).toBeNull();
    expect(empty.sleepHours).toBeNull();
  });
});

describe("summaryNoteLines — the block the patient attaches to the note", () => {
  it("labels each metric and skips absent ones", () => {
    const summary = buildSummary(
      {
        stepsByDay: [{ dateISO: "2026-08-21", count: 4180 }],
        restingHeartRateBpm: [60],
        sleepSessions: [],
      },
      "tr",
    );
    const lines = summaryNoteLines(summary, "tr");
    expect(lines).toEqual([
      `Adımlar (son 7 gün): 2026-08-21 4180${NBSP}adım`,
      `Dinlenme nabzı: 60${NBSP}atım/dk`,
    ]);
  });

  it("is empty when there is nothing to attach", () => {
    const summary = buildSummary(
      { stepsByDay: [], restingHeartRateBpm: [], sleepSessions: [] },
      "tr",
    );
    expect(summaryNoteLines(summary, "tr")).toEqual([]);
  });
});

describe("health module stays off the speech path (invariant 22: no numeral may reach TTS)", () => {
  it("no file under lib/health imports voice, speech or TTS modules", () => {
    const dir = __dirname;
    for (const name of readdirSync(dir)) {
      // Production modules only — this test file carries the pattern itself.
      if (!/\.tsx?$/.test(name) || name.includes(".test.")) continue;
      const source = readFileSync(join(dir, name), "utf8");
      // Import specifiers only — prose may mention the invariant by name.
      expect(source, name).not.toMatch(/from\s+["'][^"']*(voice|speech|tts)[^"']*["']/i);
      expect(source, name).not.toMatch(/import\(\s*["'][^"']*(voice|speech|tts)[^"']*["']\s*\)/i);
    }
  });
});

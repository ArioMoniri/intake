/**
 * INT-594 — Bugün is true (GitHub #1007).
 *
 * The INT-502 captures of build 7 showed an OTP account's Today screen stuck
 * on "Muayeneye hazırlanın (≈3 dk)" over a "%36 Vizit hazırlığı" gauge.
 *
 * - The hospital feed carries no note state, so api.ts's `syncVisits` sets
 *   `noteStatus: null`. The screen read that raw value, so it never reached
 *   "Devam edin" and never saw a note the server had confirmed (INT-587).
 * - "≈3 dk" is a duration nobody measured. Invariant 20 and INT-139 keep a
 *   duration as a dated measurement in docs/evidence, never in patient copy.
 * - The gauge printed answered ÷ the pack's questions as a bare score. The
 *   flow asks conditionally (`askIfMet`), so the denominator counts questions
 *   that may never be asked.
 */
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";

import { en } from "./i18n/en";
import { tr } from "./i18n/tr";
import { emptyNoteState, type NoteState } from "./intake/note";
import { todayFocus } from "./today";
import type { VisitFixture } from "./types/account";

const MOBILE = join(__dirname, "..", "..");
const read = (...segments: string[]) => readFileSync(join(MOBILE, ...segments), "utf8");

/** A visit as the hospital feed returns it: no note state (api.ts `syncVisits`). */
function feedVisit(id: string): VisitFixture {
  return {
    id,
    hospital: "Sentetik Eğitim Hastanesi",
    department: "Kardiyoloji · 10:30",
    branchId: null,
    visitType: null,
    date: "2026-11-03",
    noteStatus: null,
  };
}

function answered(): NoteState {
  return { ...emptyNoteState(), answers: [{ questionId: "chief_complaint", values: ["öksürük"] }] };
}

function sentByPatient(): NoteState {
  return { ...answered(), status: "sent" };
}

const NONE_DELIVERED = (): boolean => false;
const deliveredOnly =
  (...ids: string[]) =>
  (visitId: string): boolean =>
    ids.includes(visitId);

describe("Bugün's focus comes from the note's real state, not the feed's null", () => {
  it("a feed visit with nothing on the phone asks the patient to prepare", () => {
    const focus = todayFocus([feedVisit("v1")], {}, NONE_DELIVERED);
    expect(focus).toMatchObject({ kind: "prepare", status: null, cta: "visit.prepare" });
  });

  it("a feed visit with answers on the phone continues — the state build 7 never reached", () => {
    const focus = todayFocus([feedVisit("v1")], { v1: answered() }, NONE_DELIVERED);
    expect(focus).toMatchObject({ kind: "continue", status: "draft", cta: "today.continueCta" });
  });

  it("near miss: a note the patient sent that the server has not confirmed is still a draft", () => {
    const focus = todayFocus([feedVisit("v1")], { v1: sentByPatient() }, NONE_DELIVERED);
    expect(focus).toMatchObject({ kind: "continue", status: "draft" });
  });

  it("near miss: a confirmed delivery without the patient's send is not a sent note", () => {
    const focus = todayFocus([feedVisit("v1")], { v1: answered() }, deliveredOnly("v1"));
    expect(focus).toMatchObject({ kind: "continue", status: "draft" });
  });

  it("a note the server confirmed shows as sent, and the action opens the visit", () => {
    const focus = todayFocus([feedVisit("v1")], { v1: sentByPatient() }, deliveredOnly("v1"));
    expect(focus).toMatchObject({ kind: "sent", status: "sent", cta: "today.openCta" });
  });

  it("a visit still to prepare comes before one already delivered", () => {
    const focus = todayFocus(
      [feedVisit("v1"), feedVisit("v2")],
      { v1: sentByPatient() },
      deliveredOnly("v1"),
    );
    expect(focus.kind).toBe("prepare");
    expect(focus.kind !== "none" && focus.visit.id).toBe("v2");
  });

  it("a delivered visit is still the next visit: Bugün never says there is none", () => {
    const focus = todayFocus([feedVisit("v1")], { v1: sentByPatient() }, deliveredOnly("v1"));
    expect(focus.kind).not.toBe("none");
  });

  it("keeps the dev fixtures' ladder: a draft continues, a filed visit is not today's", () => {
    const draft = { ...feedVisit("d1"), noteStatus: "draft" as const };
    const filed = { ...feedVisit("f1"), noteStatus: "filed" as const };
    expect(todayFocus([filed, draft], {}, NONE_DELIVERED)).toMatchObject({
      kind: "continue",
      status: "draft",
    });
    expect(todayFocus([filed], {}, NONE_DELIVERED)).toEqual({ kind: "none" });
    expect(todayFocus([], {}, NONE_DELIVERED)).toEqual({ kind: "none" });
  });
});

/** A duration or an approximate figure: what invariant 20 keeps out of copy. */
const DURATION =
  /(?:≈|~)\s*\d|\b\d+\s*(?:sn|sec|secs|seconds?|saniye|dk|dakika|minutes?|mins?)\b/iu;

describe("the copy carries no figure nobody measured (invariant 20)", () => {
  it("no catalogue line, in either language, puts a duration in patient copy", () => {
    for (const [key, value] of [...Object.entries(tr), ...Object.entries(en)]) {
      expect(value, key).not.toMatch(DURATION);
    }
  });

  it("near miss: the pattern bites on the lines build 7 showed, and not on their fix", () => {
    expect("Muayeneye hazırlanın (≈3 dk)").toMatch(DURATION);
    expect("Prepare for the visit (≈3 min)").toMatch(DURATION);
    expect("Yaklaşık 3 dakika sürer").toMatch(DURATION);
    expect(tr["visit.prepare"]).toBe("Muayeneye hazırlanın");
    expect(tr["visit.prepare"]).not.toMatch(DURATION);
  });

  it("the open action reads as a short siz button, tr first with an en mirror", () => {
    expect(tr["today.openCta"]).toBe("Viziti açın");
    expect(en["today.openCta"]).toBe("Open the visit");
  });

  it("the gauge's caption and the timed CTA are gone from both catalogues", () => {
    for (const key of ["today.prep", "today.prepareCta"]) {
      expect(Object.keys(tr)).not.toContain(key);
      expect(Object.keys(en)).not.toContain(key);
    }
  });
});

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

const SHIPPED = walk(join(MOBILE, "src"))
  .filter((path) => /\.tsx?$/.test(path) && !/\.test\.tsx?$/.test(path))
  .map((path) => ({
    name: relative(MOBILE, path).split(sep).join("/"),
    source: readFileSync(path, "utf8"),
  }));

describe("no bare percentage score on Bugün", () => {
  const screen = read("src", "app", "(tabs)", "today.tsx");

  it("the screen takes its focus from todayFocus and the delivery store", () => {
    expect(screen).toContain("todayFocus(");
    expect(screen).toContain("useDeliveries()");
    expect(screen).toContain("t(focus.cta)");
    // near miss: the raw feed value is exactly what kept it on "prepare"
    expect(screen).not.toMatch(/\.noteStatus\s*===/);
  });

  it("the screen renders no gauge and formats no percentage", () => {
    expect(screen).not.toContain("PrepGauge");
    expect(screen).not.toContain("fraction");
    expect(existsSync(join(MOBILE, "src", "components", "PrepGauge.tsx"))).toBe(false);
  });

  it("no shipped module formats a number as a percentage for display", () => {
    const formatters = SHIPPED.filter((f) => /style:\s*["']percent["']/.test(f.source)).map(
      (f) => f.name,
    );
    expect(formatters).toEqual([]);
    // near miss: the pattern does see the formatter the gauge used
    expect('new Intl.NumberFormat("tr-TR", { style: "percent" })').toMatch(
      /style:\s*["']percent["']/,
    );
  });
});

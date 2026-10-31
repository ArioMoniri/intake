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

/** A fixed "today" (Europe/Istanbul ISO date), so the upcoming/past split is deterministic. */
const TODAY = "2026-10-31";

const NONE_DELIVERED = (): boolean => false;
const deliveredOnly =
  (...ids: string[]) =>
  (visitId: string): boolean =>
    ids.includes(visitId);

describe("Bugün's focus comes from the note's real state, not the feed's null", () => {
  it("a feed visit with nothing on the phone asks the patient to prepare", () => {
    const focus = todayFocus([feedVisit("v1")], {}, NONE_DELIVERED, TODAY);
    expect(focus).toMatchObject({ kind: "prepare", status: null, cta: "visit.prepare" });
  });

  it("a feed visit with answers on the phone continues — the state build 7 never reached", () => {
    const focus = todayFocus([feedVisit("v1")], { v1: answered() }, NONE_DELIVERED, TODAY);
    expect(focus).toMatchObject({ kind: "continue", status: "draft", cta: "today.continueCta" });
  });

  it("near miss: a note the patient sent that the server has not confirmed is still a draft", () => {
    const focus = todayFocus([feedVisit("v1")], { v1: sentByPatient() }, NONE_DELIVERED, TODAY);
    expect(focus).toMatchObject({ kind: "continue", status: "draft" });
  });

  it("near miss: a confirmed delivery without the patient's send is not a sent note", () => {
    const focus = todayFocus([feedVisit("v1")], { v1: answered() }, deliveredOnly("v1"), TODAY);
    expect(focus).toMatchObject({ kind: "continue", status: "draft" });
  });

  it("a note the server confirmed shows as sent, and the action opens the visit", () => {
    const focus = todayFocus(
      [feedVisit("v1")],
      { v1: sentByPatient() },
      deliveredOnly("v1"),
      TODAY,
    );
    expect(focus).toMatchObject({ kind: "sent", status: "sent", cta: "today.openCta" });
  });

  it("a visit still to prepare comes before one already delivered", () => {
    const focus = todayFocus(
      [feedVisit("v1"), feedVisit("v2")],
      { v1: sentByPatient() },
      deliveredOnly("v1"),
      TODAY,
    );
    expect(focus.kind).toBe("prepare");
    expect(focus.kind !== "none" && focus.visit.id).toBe("v2");
  });

  it("a delivered visit is still the next visit: Bugün never says there is none", () => {
    const focus = todayFocus(
      [feedVisit("v1")],
      { v1: sentByPatient() },
      deliveredOnly("v1"),
      TODAY,
    );
    expect(focus.kind).not.toBe("none");
  });

  it("keeps the dev fixtures' ladder: a draft continues, a filed visit is not today's", () => {
    const draft = { ...feedVisit("d1"), noteStatus: "draft" as const };
    const filed = { ...feedVisit("f1"), noteStatus: "filed" as const };
    expect(todayFocus([filed, draft], {}, NONE_DELIVERED, TODAY)).toMatchObject({
      kind: "continue",
      status: "draft",
    });
    expect(todayFocus([filed], {}, NONE_DELIVERED, TODAY)).toEqual({ kind: "none" });
    expect(todayFocus([], {}, NONE_DELIVERED, TODAY)).toEqual({ kind: "none" });
  });
});

/*
 * Legal review of #1013: "Sıradaki vizit" may not label a past visit. Only an
 * upcoming visit can be the focus, by the rule Vizitlerim uses (splitVisits:
 * dated today or later, or dateless). The soonest dated one comes first.
 */
describe("only an upcoming visit can be Bugün's 'Sıradaki vizit'", () => {
  const dated = (id: string, date: string | null): VisitFixture => ({ ...feedVisit(id), date });

  it("a past visit with nothing on the phone is never the next visit", () => {
    expect(todayFocus([dated("old", "2026-10-30")], {}, NONE_DELIVERED, TODAY)).toEqual({
      kind: "none",
    });
  });

  it("a past visit with a draft is not the next visit either", () => {
    const focus = todayFocus(
      [dated("old", "2026-10-01"), dated("new", "2026-11-05")],
      { old: answered() },
      NONE_DELIVERED,
      TODAY,
    );
    expect(focus).toMatchObject({ kind: "prepare" });
    expect(focus.kind !== "none" && focus.visit.id).toBe("new");
  });

  it("a past visit whose note was delivered is not shown as the next visit", () => {
    expect(
      todayFocus(
        [dated("old", "2026-10-30")],
        { old: sentByPatient() },
        deliveredOnly("old"),
        TODAY,
      ),
    ).toEqual({ kind: "none" });
  });

  it("near miss: a visit dated today is still the next visit", () => {
    expect(todayFocus([dated("now", TODAY)], {}, NONE_DELIVERED, TODAY).kind).toBe("prepare");
  });

  it("near miss: a dateless visit is upcoming, after every dated one", () => {
    expect(todayFocus([dated("tbd", null)], {}, NONE_DELIVERED, TODAY).kind).toBe("prepare");
    const focus = todayFocus(
      [dated("tbd", null), dated("soon", "2026-11-02")],
      {},
      NONE_DELIVERED,
      TODAY,
    );
    expect(focus.kind !== "none" && focus.visit.id).toBe("soon");
  });

  it("the soonest upcoming visit comes first, whatever order the feed sent", () => {
    const focus = todayFocus(
      [dated("later", "2026-11-20"), dated("sooner", "2026-11-04")],
      {},
      NONE_DELIVERED,
      TODAY,
    );
    expect(focus.kind !== "none" && focus.visit.id).toBe("sooner");
  });

  it("the screen reads today from the injected clock, the way Vizitlerim does", () => {
    const screen = read("src", "app", "(tabs)", "today.tsx");
    expect(screen).toMatch(/export default function Today\(\{ clock = deviceClock \}/);
    expect(screen).toContain("todayIso(clock)");
    expect(screen).toMatch(/todayFocus\(visits, notes, [\s\S]*?, today\);/);
  });
});

/**
 * A duration or an approximate figure: what invariant 20 keeps out of copy.
 * Legal review of #1013: spelled-out numbers count too ("üç dakika", "yarım
 * saat", "a few minutes"), and so do hours.
 */
const NUMBER_WORD =
  "bir|iki|üç|dört|beş|altı|yedi|sekiz|dokuz|on|yirmi|otuz|kırk|elli|yarım|birkaç|" +
  "one|two|three|four|five|six|seven|eight|nine|ten|fifteen|twenty|thirty|a few|a couple of|half an?";
/** Turkish units take case suffixes ("dakikada", "saatte"); English ones end the word. */
const TIME_UNIT =
  "(?:saniye|dakika|saat)\\p{L}*|(?:sn|dk)(?!\\p{L})|(?:seconds?|secs?|minutes?|mins?|hours?)(?!\\p{L})";
const DURATION = new RegExp(
  `(?:≈|~)\\s*\\d|\\b\\d+\\s*(?:${TIME_UNIT})|(?<!\\p{L})(?:${NUMBER_WORD})\\s+(?:${TIME_UNIT})`,
  "iu",
);

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

  it("near miss: a spelled-out duration is a duration too (legal review of #1013)", () => {
    for (const line of [
      "Muayeneye hazırlanın (üç dakika)",
      "Yaklaşık beş dakikada biter",
      "Yarım saat sürer",
      "Birkaç dakikanızı alır",
      "Takes about three minutes",
      "a few minutes",
      "Prepare in half an hour",
      "2 saat",
    ]) {
      expect(line, line).toMatch(DURATION);
    }
  });

  it("near miss: a number word that is not a duration is not caught", () => {
    for (const line of [
      "Bir veri notunuza ancak siz eklerseniz girer",
      "Saat kaçta gideceğinizi ekleyin",
      "One question at a time",
      "Add a second visit",
      "Bu vizitin hangi bölüm olduğunu seçin",
    ]) {
      expect(line, line).not.toMatch(DURATION);
    }
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

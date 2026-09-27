/**
 * Visits acceptance (INT-134), pinned as source facts — the nav.spec.ts
 * technique: the file tree and the call sites ARE the contract, so a picker
 * quietly rewired to free text, an SMS body leaking into a network call or
 * an OCR affordance escaping its consent gate fails here before any device
 * run would notice.
 *
 * Pins (issue acceptance, verbatim): "branch list from taxonomy; unknown
 * branch -> cluster with notice; OCR path behind documents consent".
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(__dirname, "..", "src");
const APP = join(SRC, "app");

const read = (...segments: string[]) => readFileSync(join(...segments), "utf8");

describe("visit creation runs on the production taxonomy", () => {
  it("the new-visit screen exists and drives the taxonomy-backed form", () => {
    const screen = read(APP, "(tabs)/visits/new.tsx");
    expect(screen).toContain("newVisitFormReducer");
    expect(screen).toContain("visibleBranches(");
    // branch labels render the taxonomy's own tr names (invariant 5)
    expect(screen).toContain("nameTr");
    // the demo free-text department field is gone
    expect(screen).not.toContain('t("visits.new.department")');
  });

  it("the picker can never be empty: server feed falls back to cache, then seed", () => {
    const feed = read(SRC, "lib", "taxonomy", "feed.ts");
    expect(feed).toContain("SEED_BRANCHES");
    expect(feed).toContain('"cache"');
    expect(feed).toContain('"seed"');
  });

  it("pack selection stays behind the packForVisit glue", () => {
    // INT-256: the screen composes the department pack with the universal
    // history block for this session's profile, so the glue it reaches for
    // is packForVisit — which resolves packForDepartment underneath.
    const intake = read(APP, "(tabs)/visits/[visitId]/intake.tsx");
    expect(intake).toContain("packForVisit");
  });

  it("the visit record carries its type into the session state", () => {
    expect(read(SRC, "lib", "dev", "accounts.ts")).toContain("visitType");
    expect(read(APP, "(tabs)/visits/[visitId]/index.tsx")).toContain("visitTypeLabelKey");
  });
});

describe("MHRS SMS paste-parse stays on the device", () => {
  it("the parser is pure text-in/structure-out — no network, no storage", () => {
    const parser = read(SRC, "lib", "taxonomy", "mhrsSms.ts");
    expect(parser).not.toMatch(/fetch|AsyncStorage|SecureStore|expo-file-system|XMLHttpRequest/);
  });

  it("the screen parses the paste and never hands the raw text onward", () => {
    const screen = read(APP, "(tabs)/visits/new.tsx");
    expect(screen).toContain("parseMhrsSms(");
    expect(screen).not.toContain("fetch(");
    // what is saved is the structured NewVisitInput, which has no sms field
    const visits = read(SRC, "lib", "visits.ts");
    const inputBlock = visits.slice(
      visits.indexOf("export interface NewVisitInput"),
      visits.indexOf("}", visits.indexOf("export interface NewVisitInput")),
    );
    expect(inputBlock).not.toMatch(/sms/i);
  });

  it("the unknown-branch fallback speaks tr copy, not an exception", () => {
    const tr = read(SRC, "lib", "i18n", "tr.ts");
    expect(tr).toContain('"visits.new.smsUnknownBranch"');
    expect(tr).toContain('"visits.new.smsNoDate"');
    expect(tr).toContain('"visits.new.smsTitle"');
  });
});

describe("the OCR path sits behind the documents consent, fail closed", () => {
  it("the screen renders the OCR affordance only through the gate", () => {
    const screen = read(APP, "(tabs)/visits/new.tsx");
    expect(screen).toContain("ocrImportAvailable(");
  });

  it("the gate requires the documents consent AND a licence-verified engine", () => {
    const visits = read(SRC, "lib", "visits.ts");
    const gate = visits.slice(visits.indexOf("export function ocrImportAvailable"));
    expect(gate).toContain("documents");
    // files/03 §4.9.2(f): no OCR component on the PHI path without a
    // licence_verified_at entry — the engine half of the gate is anchored
    // to that clause in source, so nobody flips it without meeting it
    expect(visits).toContain("4.9.2(f)");
  });
});

/**
 * INT-370 (INT-354 slice S3, int-demo 148a7dbd). Acceptance, verbatim:
 * "Vizitlerim offers a calendar view and a Geçmiş list of past visits, built
 * on the existing visits store with no new data field".
 */
describe("Vizitlerim offers a calendar and a Geçmiş list over the existing visits", () => {
  const screen = () => read(APP, "(tabs)/visits/index.tsx");

  it("a Liste/Takvim toggle chooses between the list and the month calendar", () => {
    const source = screen();
    expect(source).toContain("<Segmented");
    expect(source).toContain('t("visits.view.list")');
    expect(source).toContain('t("visits.view.calendar")');
    expect(source).toContain("<VisitCalendar");
  });

  it("both views read the one visits list the session already holds", () => {
    const source = screen();
    expect(source).toContain("const { visits } = useSession();");
    expect(source).toContain("pastVisitsRecentFirst(visits,");
    expect(source).toContain("visitsOnDay(visits,");
    expect(source).toMatch(/<VisitCalendar[\s\S]*?visits=\{visits\}/);
  });

  it("the Geçmiş group is always shown, with an honest empty state instead of invented history", () => {
    const source = screen();
    // Before: the whole group, kicker included, sat behind `past.length > 0 ?`
    // and vanished for a patient with no past visit.
    expect(source).not.toMatch(/past\.length > 0 \? \(\s*<View style=\{styles\.section\}>/);
    // Now the kicker renders first, and only its contents depend on the list.
    expect(source).toMatch(
      /<Kicker label=\{t\("visits\.past"\)\} \/>\s*\{past\.length > 0 \? \([\s\S]*?t\("visits\.pastEmpty"\)/,
    );
  });

  it("the calendar model is pure and reads a visit's date and nothing else", () => {
    const model = read(SRC, "lib", "calendar.ts");
    // No import at all: no store, no persistence, no native module.
    expect(model).not.toMatch(/^import /m);
    expect(model).not.toMatch(/SecureStore|AsyncStorage|fetch\(/);
    // Every visit-shaped parameter is structurally `{ date }` only.
    expect(model).toContain("readonly { readonly date: string | null }[]");
    const calendar = read(SRC, "components", "VisitCalendar.tsx");
    expect(calendar).toContain("visits: readonly { readonly date: string | null }[];");
  });

  it("every day is a named target of at least MIN_TAP, with a catalogue hint", () => {
    const calendar = read(SRC, "components", "VisitCalendar.tsx");
    expect(calendar).toContain("minHeight: MIN_TAP");
    expect(calendar).toContain('accessibilityHint={t("a11y.visits.dayHint")}');
    expect(calendar).toContain("accessibilityState={{ selected }}");
  });

  it("the new chrome is catalogued in tr, the source of truth", () => {
    const tr = read(SRC, "lib", "i18n", "tr.ts");
    for (const key of [
      "visits.view.label",
      "visits.view.list",
      "visits.view.calendar",
      "visits.pastEmpty",
      "visits.calendar.prevMonth",
      "visits.calendar.nextMonth",
      "visits.calendar.hasVisits",
      "visits.calendar.noVisitsOnDay",
      "visits.calendar.monthEmpty",
      "a11y.visits.dayHint",
    ]) {
      expect(tr).toContain(`"${key}"`);
    }
  });
});

describe("visit types speak tr copy from the i18n source of truth", () => {
  it("every files/09 §1 visit type has a tr label", () => {
    const tr = read(SRC, "lib", "i18n", "tr.ts");
    for (const type of [
      "first",
      "followup",
      "preop",
      "report",
      "pregnancy_followup",
      "chronic_review",
      "post_discharge",
      "screening",
      "second_opinion",
      "teleconsult",
    ]) {
      expect(tr).toContain(`"visits.type.${type}"`);
    }
    expect(tr).toContain('"visits.noDate"');
  });
});

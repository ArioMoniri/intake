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

import { tr } from "../src/lib/i18n/tr";

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
    for (const file of ["mhrsSms.ts", "turkishDates.ts"]) {
      const parser = read(SRC, "lib", "taxonomy", file);
      expect(parser).not.toMatch(/fetch|AsyncStorage|SecureStore|expo-file-system|XMLHttpRequest/);
    }
  });

  it("a date that reads two ways is asked for, never guessed (INT-400)", () => {
    // the device reads dates by the server's rule, ported, not by its own
    const parser = read(SRC, "lib", "taxonomy", "mhrsSms.ts");
    expect(parser).toContain('from "./turkishDates"');
    // the screen turns the refusal into a notice the patient acts on
    const screen = read(APP, "(tabs)/visits/new.tsx");
    expect(screen).toContain('ambiguous_date: "visits.new.smsAmbiguousDate"');
    expect(read(SRC, "lib", "i18n", "tr.ts")).toContain('"visits.new.smsAmbiguousDate"');
    expect(read(SRC, "lib", "i18n", "en.ts")).toContain('"visits.new.smsAmbiguousDate"');
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
 * INT-537 (GitHub #904). Visits and notes require the `core` açık rıza scope
 * (services/api visits.py and notes.py declare it), and nothing in the app
 * granted it. Acceptance: without core, visit start refuses with a clear B1
 * message that leads to the consent control; with it, a visit starts.
 */
describe("visit start needs the core consent, and leads to it (INT-537)", () => {
  const screen = () => read(APP, "(tabs)/visits/new.tsx");

  it("the screen reads the consent ledger, seeded for this account", () => {
    const source = screen();
    expect(source).toContain("useConsentLedger()");
    expect(source).toContain("seedLedgerForAccount(account.id, consents)");
    // a ledger nobody seeded yet is not this account's answer
    expect(source).toContain("ledgerSeededFor(account.id)");
    expect(source).toContain("coreGate(ledger)");
  });

  it("save refuses before a visit is added while the gate is shut", () => {
    const source = screen();
    const start = source.indexOf("const save = ");
    const save = source.slice(start, source.indexOf("\n  };", start));
    expect(save).toContain("!gate.open");
    expect(save.indexOf("!gate.open")).toBeLessThan(save.indexOf("addVisit("));
  });

  it("the refusal is B1 copy from the catalogue and its one action opens the core text", () => {
    const source = screen();
    for (const key of [
      "visits.new.core.kicker",
      "visits.new.core.title",
      "visits.new.core.body",
      "visits.new.core.staleBody",
      "visits.new.core.pendingBody",
      "visits.new.core.cta",
      "visits.new.core.pendingCta",
    ]) {
      expect(source).toContain(`"${key}"`);
      expect(read(SRC, "lib", "i18n", "tr.ts")).toContain(`"${key}"`);
      expect(read(SRC, "lib", "i18n", "en.ts")).toContain(`"${key}"`);
    }
    expect(source).toContain('router.push(`/(tabs)/me/consents/${purposeParam("core")}`)');
  });

  it("with no core text served, the screen never invites the patient to read one", () => {
    // a real tenant serves no text until counsel signs (HB-L27): the body
    // and the button say the text is on its way instead (legal review round 2)
    const source = screen();
    expect(source).toContain('gate.reason === "no_text"');
    // the pending pair says the text is being prepared; the button does not
    // promise a text to read
    expect(tr["visits.new.core.pendingBody"]).toContain("hazırlanıyor");
    expect(tr["visits.new.core.pendingCta"]).not.toMatch(/metn|okuyun/i);
    expect(tr["visits.new.core.cta"]).toContain("okuyun");
  });

  it("the gate asks for core and for nothing optional (files/02 §7)", () => {
    const gate = read(SRC, "lib", "consent", "gate.ts");
    const body = gate.slice(gate.indexOf("export function coreGate"));
    expect(body).toContain('"core"');
    for (const optional of ["voice", "wellbeing", "documents", "satisfaction", "research"]) {
      expect(body).not.toContain(`"${optional}"`);
    }
    // the screen has one consent question, and it is this one
    expect(screen()).not.toContain("viewOf(");
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

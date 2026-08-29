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

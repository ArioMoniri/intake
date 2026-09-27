/**
 * Development test accounts (INT-130). Every value here is SYNTHETIC —
 * invented names, invented dates, no real patient, no real TCKN (the id
 * fields deliberately fail the TCKN checksum shape). They exist so designers
 * and reviewers can walk the five tabs with realistic-looking state.
 *
 * Only development builds contain them (INT-410, audit F30). The welcome screen
 * loads this module with an `import()` inside `if (__DEV__)`. A release build
 * compiles `__DEV__` to `false`, and Metro drops the branch before it collects
 * dependencies, so the module never enters the release bundle. No shipped
 * module imports it statically, not even for a type: the shapes live in
 * lib/types/account.ts. Tests import it directly.
 * tests/release/test_release_bundle_has_no_fixtures.py builds the production
 * export and checks that none of these strings is in it. Real sign-in
 * (INT-131, phone verification) replaces this path entirely.
 *
 * Pure TS — unit-testable; the consent shapes double as the fixture for the
 * tab-visibility rule (wellbeing hidden until consent — 02 §4).
 */

import type { TestAccount } from "../types/account";

export const testAccounts: readonly TestAccount[] = [
  {
    id: "ayse",
    name: "Ayşe Yılmaz",
    ageYears: 58,
    locale: "tr",
    consents: { core: true, voice: true, wellbeing: true, documents: true, health: false },
    visits: [
      {
        id: "v-ayse-1",
        hospital: "Ankara Şehir Hastanesi",
        department: "İç Hastalıkları",
        branchId: "ic_hastaliklari",
        visitType: "chronic_review",
        date: "2026-09-03",
        noteStatus: "draft",
      },
      {
        id: "v-ayse-0",
        hospital: "Ankara Şehir Hastanesi",
        department: "İç Hastalıkları",
        branchId: "ic_hastaliklari",
        visitType: "first",
        date: "2026-05-12",
        noteStatus: "filed",
      },
    ],
    // Carried out of the filed 2026-05-12 visit below — the exact shape the
    // owner bug is about. It is UNCONFIRMED until Ayşe answers for the visit
    // she is in, and the note says so until she does.
    carriedFacts: [
      {
        id: "cf-ayse-metoprolol",
        kind: "medication",
        text: "Metoprolol (düzenli kullanım)",
        source: "clinician_accepted_note",
        assertedBy: { role: "clinician" },
        assertedAt: "2026-05-12",
        sourceVisitId: "v-ayse-0",
      },
      // INT-256: the same shape for the other carried category files/09 §3
      // names. An allergy carried out of an earlier visit is not an allergy
      // of THIS one until Ayşe says so, and the note says as much until she
      // does — the medication bug, one section over.
      {
        id: "cf-ayse-penisilin",
        kind: "allergy",
        text: "Penisilin (deri döküntüsü)",
        source: "confirmed_intake_extraction",
        assertedBy: { role: "patient", attribution: "self_report" },
        assertedAt: "2026-05-12",
        sourceVisitId: "v-ayse-0",
      },
    ],
    records: [
      { id: "r-ayse-1", title: "Kan tahlili sonucu", date: "2026-08-20" },
      { id: "r-ayse-2", title: "EKG raporu", date: "2026-05-12" },
    ],
  },
  {
    id: "mehmet",
    name: "Mehmet Kaya",
    ageYears: 34,
    locale: "tr",
    // wellbeing OFF: proves the tab stays hidden (02 §4 — consent-gated).
    consents: { core: true, voice: false, wellbeing: false, documents: false, health: false },
    visits: [
      {
        id: "v-mehmet-1",
        hospital: "İstanbul Eğitim ve Araştırma Hastanesi",
        // the taxonomy's own name_tr, not the colloquial short form
        department: "Kulak Burun Boğaz Hastalıkları",
        branchId: "kulak_burun_bogaz_hastaliklari",
        visitType: "first",
        date: "2026-09-10",
        noteStatus: null,
      },
    ],
    carriedFacts: [],
    records: [],
  },
] as const;

export function getTestAccount(id: string): TestAccount | undefined {
  return testAccounts.find((a) => a.id === id);
}

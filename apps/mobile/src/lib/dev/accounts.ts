/**
 * Development test accounts (INT-130). Every value here is SYNTHETIC —
 * invented names, invented dates, no real patient, no real TCKN (the id
 * fields deliberately fail the TCKN checksum shape). They exist so designers
 * and reviewers can walk the five tabs with realistic-looking state.
 *
 * These are compiled into __DEV__ builds only: the welcome screen renders
 * them behind `__DEV__`, and nothing else imports this module. Real sign-in
 * (INT-131, phone verification) replaces this path entirely.
 *
 * Pure TS — unit-testable; the consent shapes double as the fixture for the
 * tab-visibility rule (wellbeing hidden until consent — 02 §4).
 */

import type { CarriedFact } from "../intake/carriedFacts";
import type { VisitTypeId } from "../taxonomy/branches";

export type NoteStatus = "draft" | "sent" | "viewed" | "filed";

export interface ConsentState {
  core: boolean;
  voice: boolean;
  wellbeing: boolean;
  documents: boolean;
  /**
   * Device-local health data reading (INT-208): gates the HealthKit/Health
   * Connect read on the phone itself. A NEW category of personal data, so it
   * defaults OFF for every fixture — always an explicit patient opt-in, and
   * nothing read under it is persisted or sent server-side.
   */
  health: boolean;
}

export interface VisitFixture {
  id: string;
  hospital: string;
  /** The branch's tr name as the taxonomy prints it (invariant 5). */
  department: string;
  /** Taxonomy branch id (INT-134) — the visit's source of truth. */
  branchId: string | null;
  /** files/09 §1 visit type, carried into pack selection. */
  visitType: VisitTypeId | null;
  /** ISO date — null when the appointment is not booked yet (02 §2b). */
  date: string | null;
  noteStatus: NoteStatus | null;
}

export interface RecordFixture {
  id: string;
  title: string;
  /** ISO date — synthetic. */
  date: string;
}

export interface TestAccount {
  id: string;
  /** Display name — obviously synthetic, badge shown in Profil. */
  name: string;
  ageYears: number;
  locale: "tr" | "en";
  consents: ConsentState;
  visits: VisitFixture[];
  /**
   * Facts carried out of the account's EARLIER visits (INT-247) — never
   * "current medications". Each one names where it came from and when, and
   * stays unconfirmed until the patient answers for the visit in hand
   * (invariant 12). No doses invented; no dose is carried at all.
   */
  carriedFacts: CarriedFact[];
  records: RecordFixture[];
}

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
      // INT-250: the same shape for the other carried category files/09 §3
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

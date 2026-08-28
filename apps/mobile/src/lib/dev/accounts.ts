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

export type NoteStatus = "draft" | "sent" | "viewed" | "filed";

export interface ConsentState {
  core: boolean;
  voice: boolean;
  wellbeing: boolean;
  documents: boolean;
  /**
   * Device-local health data reading (INT-200): gates the HealthKit/Health
   * Connect read on the phone itself. A NEW category of personal data, so it
   * defaults OFF for every fixture — always an explicit patient opt-in, and
   * nothing read under it is persisted or sent server-side.
   */
  health: boolean;
}

export interface VisitFixture {
  id: string;
  hospital: string;
  department: string;
  /** ISO date, always in the fixture's frame — synthetic. */
  date: string;
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
  /** Registered medications as the patient reported them — no doses invented. */
  medications: string[];
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
        date: "2026-09-03",
        noteStatus: "draft",
      },
      {
        id: "v-ayse-0",
        hospital: "Ankara Şehir Hastanesi",
        department: "İç Hastalıkları",
        date: "2026-05-12",
        noteStatus: "filed",
      },
    ],
    medications: ["Metoprolol (düzenli kullanım)"],
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
        department: "Kulak Burun Boğaz",
        date: "2026-09-10",
        noteStatus: null,
      },
    ],
    medications: [],
    records: [],
  },
] as const;

export function getTestAccount(id: string): TestAccount | undefined {
  return testAccounts.find((a) => a.id === id);
}

/**
 * The shapes a signed-in account carries: its consents, its visits and their
 * note status, its records.
 *
 * They used to be declared beside the synthetic seed in lib/dev/accounts.ts,
 * so eight shipped modules imported a dev module for their types (audit F30).
 * A type import is erased at build time, so the types never carried the seed
 * into a release build. They did tie every release screen to a dev-only file,
 * though, and they made "nothing shipped imports the seed" something you had to
 * read line by line rather than a rule a test could check. The shapes now live
 * here. The seed imports them like any other module, and a release build
 * reaches the seed only through the welcome screen's `__DEV__` branch (INT-410).
 *
 * Types only, no values.
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

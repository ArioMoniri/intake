/**
 * Visit creation (INT-134): the "Yeni vizit" form over the production
 * branch taxonomy — branch picker + visit type + optional date, plus the
 * MHRS appointment-SMS paste-parse.
 *
 * Three rules the shapes here enforce rather than document:
 * - the department label is DERIVED from the branch's `name_tr`; nobody
 *   types a department any more (invariant 5: tr names are the source of
 *   truth, and a typed "Kardioloji" resolves to no pack at all);
 * - the date is optional. A patient adding a visit they have not booked yet
 *   gets a visit without a date, not an invented one — the whole timing
 *   model keys off this field (02 §2b);
 * - the pasted SMS is parsed on the device and DISCARDED. Only the
 *   structured fields survive into `NewVisitInput`, so the raw message body
 *   is never persisted, never uploaded, and carries no inventory annotation
 *   because it is never stored anywhere.
 */
import { branchById, type Branch, type VisitTypeId } from "./taxonomy/branches";
import type { ParsedMhrsSms } from "./taxonomy/mhrsSms";
import type { ConsentState, VisitFixture } from "./types/account";

export interface NewVisitInput {
  hospital: string;
  /** Taxonomy branch id (files/09 §1) — the source of truth for the visit. */
  branchId: string | null;
  /** The branch's tr name, carried so the card renders without a lookup. */
  branchNameTr: string | null;
  visitType: VisitTypeId | null;
  /** ISO date YYYY-MM-DD, or null when the appointment is not booked yet. */
  date: string | null;
}

export type VisitValidation = { ok: true } | { ok: false; reason: "missing_fields" | "bad_date" };

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function isRealDate(iso: string): boolean {
  const [year, month, day] = iso.split("-").map(Number);
  const candidate = new Date(Date.UTC(year, month - 1, day));
  return (
    candidate.getUTCFullYear() === year &&
    candidate.getUTCMonth() === month - 1 &&
    candidate.getUTCDate() === day
  );
}

export function validateNewVisit(input: NewVisitInput): VisitValidation {
  if (input.hospital.trim().length === 0 || input.branchId === null || input.visitType === null) {
    return { ok: false, reason: "missing_fields" };
  }
  if (input.date === null) {
    return { ok: true }; // an unbooked visit is a real visit
  }
  const date = input.date.trim();
  if (!ISO_DATE.test(date) || !isRealDate(date)) {
    return { ok: false, reason: "bad_date" };
  }
  return { ok: true };
}

/** Deterministic local ids so screens and tests can address created visits. */
export function buildLocalVisit(input: NewVisitInput, seq: number): VisitFixture {
  const date = input.date === null ? null : input.date.trim();
  return {
    id: `v-local-${seq}`,
    hospital: input.hospital.trim(),
    // the visible department IS the taxonomy's tr name (invariant 5)
    department: (input.branchNameTr ?? "").trim(),
    branchId: input.branchId,
    visitType: input.visitType,
    date: date !== null && date.length > 0 ? date : null,
    noteStatus: null,
  };
}

/**
 * Upcoming / past split. A visit with no date is UPCOMING: it is something
 * the patient still intends to attend, and burying it under "Geçmiş"
 * because we lack a date would hide their own plan from them.
 */
export function splitVisits<V extends { date: string | null }>(
  visits: readonly V[],
  todayIso: string,
): { upcoming: V[]; past: V[] } {
  return {
    upcoming: visits.filter((visit) => visit.date === null || visit.date >= todayIso),
    past: visits.filter((visit) => visit.date !== null && visit.date < todayIso),
  };
}

// --- the new-visit form -----------------------------------------------------------------

/** What the paste-parse told the patient, in tr copy the screen renders. */
export type SmsNotice = "filled" | "unknown_branch" | "no_date" | "unreadable" | null;

export interface NewVisitForm {
  hospital: string;
  branchId: string | null;
  branchNameTr: string | null;
  visitType: VisitTypeId | null;
  date: string | null;
  /** The pasted message, held only until it is parsed, then cleared. */
  sms: string;
  smsNotice: SmsNotice;
  problem: "missing_fields" | "bad_date" | null;
}

export function emptyNewVisitForm(): NewVisitForm {
  return {
    hospital: "",
    branchId: null,
    branchNameTr: null,
    visitType: null,
    date: null,
    sms: "",
    smsNotice: null,
    problem: null,
  };
}

export type NewVisitAction =
  | { type: "set_hospital"; value: string }
  | { type: "pick_branch"; branch: Branch }
  | { type: "pick_visit_type"; visitType: VisitTypeId }
  | { type: "set_date"; value: string }
  | { type: "set_sms"; value: string }
  | { type: "apply_sms"; parsed: ParsedMhrsSms; branches: readonly Branch[] }
  | { type: "set_problem"; problem: "missing_fields" | "bad_date" | null };

export function newVisitFormReducer(state: NewVisitForm, action: NewVisitAction): NewVisitForm {
  switch (action.type) {
    case "set_hospital":
      return { ...state, hospital: action.value, problem: null };
    case "pick_branch": {
      // a visit type the new branch does not book is dropped, not carried:
      // Anesteziyoloji books preop only, and a stale "followup" would be a
      // lie the server refuses anyway (files/09 §1)
      const keepsType =
        state.visitType !== null && action.branch.visitTypes.includes(state.visitType);
      return {
        ...state,
        branchId: action.branch.id,
        branchNameTr: action.branch.nameTr,
        visitType: keepsType ? state.visitType : null,
        problem: null,
      };
    }
    case "pick_visit_type":
      return { ...state, visitType: action.visitType, problem: null };
    case "set_date": {
      const value = action.value.trim();
      return { ...state, date: value.length > 0 ? value : null, problem: null };
    }
    case "set_sms":
      return { ...state, sms: action.value };
    case "apply_sms": {
      const { parsed } = action;
      const branch =
        parsed.branchId === null ? undefined : branchById(action.branches, parsed.branchId);
      const readable = branch !== undefined || parsed.dateIso !== null || parsed.hospital !== null;
      // the raw message is cleared the moment it has been read: it is parsed
      // on the device and kept only as structure (no raw SMS is persisted)
      const base: NewVisitForm = { ...state, sms: "", problem: null };
      if (!readable) {
        return { ...base, smsNotice: "unreadable" };
      }
      const next: NewVisitForm = {
        ...base,
        hospital: parsed.hospital ?? state.hospital,
        branchId: branch?.id ?? state.branchId,
        branchNameTr: branch?.nameTr ?? state.branchNameTr,
        visitType: branch !== undefined ? null : state.visitType,
        date: parsed.dateIso ?? state.date,
        smsNotice: null,
      };
      if (branch === undefined) {
        // never a crash and never a guess: name what we could not place and
        // let the patient choose it from the picker
        return { ...next, smsNotice: "unknown_branch" };
      }
      if (parsed.dateIso === null) {
        return { ...next, smsNotice: "no_date" };
      }
      return { ...next, smsNotice: "filled" };
    }
    case "set_problem":
      return { ...state, problem: action.problem };
  }
}

export function formToInput(state: NewVisitForm): NewVisitInput {
  return {
    hospital: state.hospital,
    branchId: state.branchId,
    branchNameTr: state.branchNameTr,
    visitType: state.visitType,
    date: state.date,
  };
}

// --- the OCR leg ------------------------------------------------------------------------

/**
 * INT-134 acceptance: "OCR path behind documents consent". The gate is
 * consent AND a servable engine, and today the engine half is honestly
 * false: files/03 §4.9.2(f) makes OCR (§4.9.1 rows 20–21) the one layer in
 * the stack where NO licence has been verified, under a hard gate — "no OCR
 * component reaches the PHI path without a `licence_verified_at` entry read
 * from the raw LICENSE blob". Screenshot import therefore ships as a wired,
 * fail-closed affordance with no engine behind it, never as a fake that
 * pretends to read. The consent term is live and enforced; verifying the
 * licence is what flips the engine term.
 */
export const OCR_ENGINE_LICENCE_VERIFIED = false;

export function ocrImportAvailable(consents: Pick<ConsentState, "documents"> | null): boolean {
  return consents?.documents === true && OCR_ENGINE_LICENCE_VERIFIED;
}

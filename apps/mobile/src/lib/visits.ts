/**
 * Local visit creation (INT-193): the manual "Yeni vizit" form writes real
 * session state so the demo flows end-to-end (today → detail → intake →
 * review → send) on a visit the user just created. MHRS-message import and
 * server persistence arrive with INT-134 — the shapes here are theirs.
 */
import type { VisitFixture } from "./dev/accounts";

export interface NewVisitInput {
  hospital: string;
  department: string;
  /** ISO date YYYY-MM-DD. */
  date: string;
}

export type VisitValidation = { ok: true } | { ok: false; reason: "missing_fields" | "bad_date" };

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

export function validateNewVisit(input: NewVisitInput): VisitValidation {
  if (input.hospital.trim().length === 0 || input.department.trim().length === 0) {
    return { ok: false, reason: "missing_fields" };
  }
  if (!ISO_DATE.test(input.date.trim())) {
    return { ok: false, reason: "bad_date" };
  }
  return { ok: true };
}

/** Deterministic local ids so screens and tests can address created visits. */
export function buildLocalVisit(input: NewVisitInput, seq: number): VisitFixture {
  return {
    id: `v-local-${seq}`,
    hospital: input.hospital.trim(),
    department: input.department.trim(),
    date: input.date.trim(),
    noteStatus: null,
  };
}

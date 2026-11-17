/**
 * INT-587 — the body the app PUTs to `/v1/visits/{id}/note` (services/api
 * notes.write_note, schema `NotePut`).
 *
 * Built from the same `buildNote` the review screen renders, so what the
 * patient read is what leaves the phone. Two rules the server depends on:
 *
 * - **every section the note holds is sent, each with an explicit scope.** The
 *   server stores the whole note under `core` in one envelope-encrypted row
 *   and serves the clinic side only the scoped-on sections; it records the
 *   withheld ids affirmatively (INT-304). A client that dropped a withheld
 *   section instead would leave that withholding recorded nowhere;
 * - **a body the server would refuse never leaves the phone.** The bounds are
 *   the server's own (`Line`, `Title`, `NoteSection.lines`), counted the way
 *   pydantic counts — in code points — so the phone neither refuses what the
 *   server accepts nor sends what it refuses. `e2e/noteDelivery.spec.ts` pins
 *   them against schemas.py.
 *
 * Pure and node-testable. Nothing here logs; the body is note text, which is
 * exactly what invariant 6 keeps out of every log.
 */
import { t } from "../../i18n";
import {
  NOTE_SECTION_IDS,
  buildNote,
  type NoteAccount,
  type NoteSectionEmittedId,
  type NoteState,
} from "../note";

/** Mirrors services/api schemas.py — `Line`, `Title`, `NoteSection.lines`. */
export const NOTE_LIMITS = {
  sections: NOTE_SECTION_IDS.length,
  linesPerSection: 100,
  lineChars: 2000,
  titleChars: 200,
} as const;

export interface SectionBody {
  id: NoteSectionEmittedId;
  title: string;
  lines: string[];
}

export interface NotePutBody {
  sections: SectionBody[];
  /** Every section's scope, shared AND withheld, stated affirmatively. */
  scopes: Partial<Record<NoteSectionEmittedId, boolean>>;
  /** The one status that creates a share (notes.write_note). */
  status: "sent";
}

export type PayloadResult =
  { ok: true; body: NotePutBody } | { ok: false; reason: "empty" | "too_long" };

const SECTION_IDS: ReadonlySet<string> = new Set(NOTE_SECTION_IDS);

function isSectionId(id: string): id is NoteSectionEmittedId {
  return SECTION_IDS.has(id);
}

/** pydantic's `max_length` counts code points, not UTF-16 units. */
function chars(value: string): number {
  return [...value].length;
}

function withinBounds(section: SectionBody): boolean {
  const titleLength = chars(section.title);
  return (
    titleLength >= 1 &&
    titleLength <= NOTE_LIMITS.titleChars &&
    section.lines.length >= 1 &&
    section.lines.length <= NOTE_LIMITS.linesPerSection &&
    section.lines.every((line) => chars(line) >= 1 && chars(line) <= NOTE_LIMITS.lineChars)
  );
}

/** The PUT body for a note the patient has sent, or why there is none. */
export function notePutBody(note: NoteState, account: NoteAccount): PayloadResult {
  const sections: SectionBody[] = [];
  const scopes: NotePutBody["scopes"] = {};
  for (const section of buildNote(
    note.answers,
    account,
    note.healthLines,
    note.deferred,
    note.factReview,
  )) {
    if (!isSectionId(section.id)) {
      continue; // unreachable while buildNote and NOTE_SECTION_IDS agree (review_send.spec §9)
    }
    sections.push({ id: section.id, title: t(section.titleKey), lines: [...section.lines] });
    scopes[section.id] = note.scopes[section.id] !== false;
  }
  if (sections.length === 0) {
    return { ok: false, reason: "empty" };
  }
  if (sections.length > NOTE_LIMITS.sections || !sections.every(withinBounds)) {
    return { ok: false, reason: "too_long" };
  }
  return { ok: true, body: { sections, scopes, status: "sent" } };
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

/** A stored body, checked before it is trusted — the outbox's own bytes
 * included, because a body that no longer validates must not be sent. */
export function isNotePutBody(value: unknown): value is NotePutBody {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const body = value as Record<string, unknown>;
  if (body.status !== "sent" || !Array.isArray(body.sections) || body.sections.length === 0) {
    return false;
  }
  if (typeof body.scopes !== "object" || body.scopes === null) {
    return false;
  }
  for (const [id, shared] of Object.entries(body.scopes as Record<string, unknown>)) {
    if (!isSectionId(id) || typeof shared !== "boolean") {
      return false;
    }
  }
  return body.sections.every((raw: unknown) => {
    if (typeof raw !== "object" || raw === null) {
      return false;
    }
    const section = raw as Record<string, unknown>;
    return (
      typeof section.id === "string" &&
      isSectionId(section.id) &&
      typeof section.title === "string" &&
      isStringArray(section.lines) &&
      withinBounds({ id: section.id, title: section.title, lines: section.lines })
    );
  });
}

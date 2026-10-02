/**
 * INT-134 — MHRS appointment-SMS paste-parse.
 *
 * The patient pastes the appointment message; this module turns that text
 * into {date, time, hospital, branch} and NOTHING ELSE happens to it. It is
 * a pure function: no network, no storage, no logging — the raw message is
 * never persisted, never uploaded and never leaves the reducer that called
 * this (only the structured fields survive; visits.spec.ts pins that).
 *
 * Every field is honestly optional. A message we cannot read yields nulls,
 * and the screen falls back to the picker — an invented appointment date
 * would be a lie the whole timing model then trusts (02 §2b).
 *
 * INT-400: the date is read by the server's rule (`findPrintedDate`, a port
 * of `find_printed_date`), with no order, as the server's `parse_mhrs_sms`.
 * INT-134 read `03.09.2026` day-first, as 3 September. The server refuses it,
 * because no committed source states the order an MHRS SMS prints. A date
 * that reads two ways now comes back as `dateRefusal: "ambiguous"`, and the
 * screen asks the patient for the date. It is never guessed.
 */
import { branchById, foldTr, type Branch } from "./branches";
import { findPrintedDate, type PrintedDateRefusal } from "./turkishDates";

export interface ParsedMhrsSms {
  /** ISO date (YYYY-MM-DD), or null when the message's date is refused. */
  dateIso: string | null;
  /**
   * Why `dateIso` is null, in the server's words (`VisitFieldRefusal`):
   * `ambiguous` (reads as two days, or two dates are printed), `not_found`,
   * or `unreadable`. Null exactly when `dateIso` is set.
   */
  dateRefusal: PrintedDateRefusal | null;
  /** HH:MM, or null. */
  time: string | null;
  /** The hospital name as printed, or null. */
  hospital: string | null;
  /** The taxonomy branch id, or null when the clinic name is unknown. */
  branchId: string | null;
  /** The clinic text as printed — echoed back so the patient recognises it. */
  branchText: string | null;
}

const EMPTY: ParsedMhrsSms = {
  dateIso: null,
  dateRefusal: "not_found",
  time: null,
  hospital: null,
  branchId: null,
  branchText: null,
};

/** Turkish uppercase run of two letters or more — how MHRS prints names. */
const UPPER_WORD = "[A-ZÇĞİIÖŞÜ]{2,}";
const HOSPITAL = new RegExp(`((?:${UPPER_WORD}[- ]+)*HASTANES[İI])`);
const AFTER_HOSPITAL = new RegExp(`HASTANES[İI]\\s+((?:${UPPER_WORD}[- ]+)*${UPPER_WORD})`);
const TIME = /saat\s*(\d{1,2})[:.](\d{2})/i;

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * The longest taxonomy branch name occurring at word boundaries in the
 * message. Longest wins so a yan dal ("Çocuk Kardiyolojisi") beats the
 * parent token it contains, and boundaries stop a short name matching
 * inside a longer word.
 */
function matchBranch(
  text: string,
  branches: readonly Branch[],
): { id: string; start: number; end: number } | null {
  const folded = foldTr(text);
  let best: { id: string; start: number; end: number } | null = null;
  for (const branch of branches) {
    const name = foldTr(branch.nameTr);
    const pattern = new RegExp(`(^|[^a-z0-9])${escapeRegExp(name)}([^a-z0-9]|$)`);
    const found = pattern.exec(folded);
    if (found === null) {
      continue;
    }
    const start = found.index + found[1].length;
    const candidate = { id: branch.id, start, end: start + name.length };
    if (best === null || candidate.end - candidate.start > best.end - best.start) {
      best = candidate;
    }
  }
  return best;
}

/**
 * Parse a pasted MHRS appointment message against the branch taxonomy.
 * `branches` is whatever list the picker is running on (server feed, cached
 * last-good or the bundled seed), so the parser and the picker always agree.
 */
export function parseMhrsSms(text: string, branches: readonly Branch[]): ParsedMhrsSms {
  if (text.trim().length === 0) {
    return EMPTY;
  }

  // no order is passed: none is stated for an MHRS SMS (INT-399)
  const date = findPrintedDate(text);
  const dateIso = date.ok ? date.iso : null;
  const dateRefusal = date.ok ? null : date.refusal;

  const time = TIME.exec(text);
  const clock = time === null ? null : `${String(Number(time[1])).padStart(2, "0")}:${time[2]}`;

  const hospitalMatch = HOSPITAL.exec(text);
  const hospital = hospitalMatch === null ? null : hospitalMatch[1].trim();

  const branch = matchBranch(text, branches);
  if (branch !== null) {
    // folding is one character in, one character out, so the folded offsets
    // address the original string too — the patient sees their own spelling
    return {
      dateIso,
      dateRefusal,
      time: clock,
      hospital,
      branchId: branchById(branches, branch.id)?.id ?? null,
      branchText: text.slice(branch.start, branch.end),
    };
  }

  // unknown clinic: keep the printed name so the screen can say which one it
  // could not place, and let the patient pick (never a crash, never a guess)
  const trailing = AFTER_HOSPITAL.exec(text);
  return {
    dateIso,
    dateRefusal,
    time: clock,
    hospital,
    branchId: null,
    branchText: trailing === null ? null : trailing[1].trim(),
  };
}

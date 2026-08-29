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
 */
import { branchById, foldTr, type Branch } from "./branches";

export interface ParsedMhrsSms {
  /** ISO date (YYYY-MM-DD), or null when absent/impossible. */
  dateIso: string | null;
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
  time: null,
  hospital: null,
  branchId: null,
  branchText: null,
};

/** Turkish uppercase run of two letters or more — how MHRS prints names. */
const UPPER_WORD = "[A-ZÇĞİIÖŞÜ]{2,}";
const HOSPITAL = new RegExp(`((?:${UPPER_WORD}[- ]+)*HASTANES[İI])`);
const AFTER_HOSPITAL = new RegExp(`HASTANES[İI]\\s+((?:${UPPER_WORD}[- ]+)*${UPPER_WORD})`);
const DATE = /(\d{1,2})[./](\d{1,2})[./](\d{4})/;
const TIME = /saat\s*(\d{1,2})[:.](\d{2})/i;

function isoDate(day: string, month: string, year: string): string | null {
  const d = Number(day);
  const m = Number(month);
  const y = Number(year);
  const candidate = new Date(Date.UTC(y, m - 1, d));
  // roundtrip: 31.02 silently rolls over to 03.03 — refuse instead
  if (
    candidate.getUTCFullYear() !== y ||
    candidate.getUTCMonth() !== m - 1 ||
    candidate.getUTCDate() !== d
  ) {
    return null;
  }
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${y}-${pad(m)}-${pad(d)}`;
}

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

  const date = DATE.exec(text);
  const dateIso = date === null ? null : isoDate(date[1], date[2], date[3]);

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
    time: clock,
    hospital,
    branchId: null,
    branchText: trailing === null ? null : trailing[1].trim(),
  };
}

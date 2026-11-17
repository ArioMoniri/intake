/**
 * INT-400 — a printed date is a numeral, and it crosses a boundary.
 *
 * This is the server's rule, PORTED, not a device rule written again:
 * packages/intake_platform/src/intake_platform/records/turkish_dates.py
 * (`parse_printed_date`, `find_printed_date`; INT-122). One fixture holds
 * both sides, tests/fixtures/records/mhrs_dates.json. turkishDates.test.ts and
 * mhrsSms.test.ts read it here, and tests/records/test_mhrs.py reads it on the
 * server, so a change one side makes and the other does not fails a build.
 *
 * `03.04.2026` is 3 April day-first and 4 March month-first. The two readings
 * are a month apart, and nothing on the screen makes the wrong one look wrong
 * (CLAUDE.md invariant 22). So, as on the server:
 * - a value is resolved on its own, never by a locale picked for the message;
 * - a form whose two readings are two different real days is refused as
 *   `ambiguous`. `13.09.2026` has one reading (13 is not a month) and is read;
 * - a two-digit year is refused: the century would be a guess;
 * - a Turkish month NAME cannot be read as a day, so `3 Eylül 2026` needs no
 *   order at all.
 * Scanning a message adds two rules. More than one distinct date refuses the
 * read. A date-shaped token that cannot be read refuses the whole scan, and
 * the first refusal met is the one named. Month-name forms are scanned before
 * numeric ones, in the order the server raises.
 *
 * `order` is the seam for the day a human states the order a source prints.
 * It has no default. `parseMhrsSms` passes none, as `parse_mhrs_sms` passes
 * none, because no committed source states the order an MHRS SMS prints
 * (INT-399; docs/backlog/blockers.md INT-122 Ask 2).
 *
 * Python's regex classes are Unicode-aware, and JavaScript's shorthand classes
 * are not. So every class below is spelled out: `\p{Nd}` is Python's `\d`,
 * `[\p{L}\p{N}_]` its `\w`, `[\p{L}\p{Nl}\p{No}]` its `[^\W\d_]`, and the
 * whitespace class its `\s`. docs/evidence/INT-400.md records the check: each
 * class was compared with CPython, one code point at a time, over every code
 * point Unicode 15.0 assigns. Each pattern is a literal, so the Hermes compiler
 * checks it at build time.
 *
 * Pure: no network, no storage, no logging. Nothing here echoes the text.
 */

export type DateOrder = "day_first" | "month_first";

/** The server's `VisitFieldRefusal`, for the date field. */
export type PrintedDateRefusal = "ambiguous" | "not_found" | "unreadable";

export type PrintedDate =
  | { readonly ok: true; readonly iso: string }
  | { readonly ok: false; readonly refusal: PrintedDateRefusal };

/**
 * The twelve Turkish month names, folded — the server's `TURKISH_MONTHS`.
 * This is calendar vocabulary read FROM what a message printed. It is never
 * rendered, so it is not catalogue copy (invariant 5 is untouched).
 */
const TURKISH_MONTHS: ReadonlyMap<string, number> = new Map([
  ["ocak", 1],
  ["şubat", 2],
  ["mart", 3],
  ["nisan", 4],
  ["mayıs", 5],
  ["haziran", 6],
  ["temmuz", 7],
  ["ağustos", 8],
  ["eylül", 9],
  ["ekim", 10],
  ["kasım", 11],
  ["aralık", 12],
]);

// `_NUMERIC_DATE`, `_NAMED_DATE` and their scanning forms, class for class.
const NUMERIC_DATE = /^(\p{Nd}{1,4})([./-])(\p{Nd}{1,2})\2(\p{Nd}{1,4})$/u;
const NAMED_DATE =
  /^(\p{Nd}{1,2})[\t\n\v\f\r\x1c-\x1f \x85\xa0\u{1680}\u{2000}-\u{200a}\u{2028}\u{2029}\u{202f}\u{205f}\u{3000}]+([\p{L}\p{Nl}\p{No}]+)[\t\n\v\f\r\x1c-\x1f \x85\xa0\u{1680}\u{2000}-\u{200a}\u{2028}\u{2029}\u{202f}\u{205f}\u{3000}]+(\p{Nd}{4})$/u;
const NUMERIC_DATE_SCAN =
  /(?<![\p{Nd}./-])(\p{Nd}{1,4})([./-])(\p{Nd}{1,2})\2(\p{Nd}{1,4})(?![\p{Nd}./-])/gu;
const NAMED_DATE_SCAN =
  /(?<![\p{L}\p{N}_])(\p{Nd}{1,2})[\t\n\v\f\r\x1c-\x1f \x85\xa0\u{1680}\u{2000}-\u{200a}\u{2028}\u{2029}\u{202f}\u{205f}\u{3000}]+([\p{L}\p{Nl}\p{No}]+)[\t\n\v\f\r\x1c-\x1f \x85\xa0\u{1680}\u{2000}-\u{200a}\u{2028}\u{2029}\u{202f}\u{205f}\u{3000}]+(\p{Nd}{4})(?![\p{L}\p{N}_])/gu;
/** Python's `str.strip()`: leading and trailing `\s`. */
const EDGE_SPACE =
  /^[\t\n\v\f\r\x1c-\x1f \x85\xa0\u{1680}\u{2000}-\u{200a}\u{2028}\u{2029}\u{202f}\u{205f}\u{3000}]+|[\t\n\v\f\r\x1c-\x1f \x85\xa0\u{1680}\u{2000}-\u{200a}\u{2028}\u{2029}\u{202f}\u{205f}\u{3000}]+$/gu;
const DECIMAL_DIGIT = /^\p{Nd}$/u;

/**
 * The server's `fold_tr`: `I` to `ı`, `İ` to `i`, then Python's `casefold`.
 * Over every code point where `toLowerCase` and `casefold` differ, only five
 * fold to letters a month name is spelled with: ß, ẞ, ſ, ﬅ and ﬆ. They are
 * mapped here (ẞ lowercases to ß first). So a word folds to a month name on
 * the device exactly when it does on the server (evidence: the same
 * per-code-point comparison).
 */
const CASEFOLD_ONLY: Readonly<Record<string, string>> = {
  ß: "ss",
  ſ: "s",
  ﬅ: "st",
  ﬆ: "st",
};

function foldTr(text: string): string {
  const lowered = text.replaceAll("I", "ı").replaceAll("İ", "i").toLowerCase();
  let folded = "";
  for (const character of lowered) {
    folded += CASEFOLD_ONLY[character] ?? character;
  }
  return folded;
}

/**
 * The value of one Unicode decimal digit, as Python's `int()` reads it.
 * Unicode encodes every decimal digit set as ten consecutive code points, 0
 * to 9. So a digit's value is its distance from the start of its run, modulo
 * ten.
 */
function digitValue(digit: string): number {
  const codePoint = digit.codePointAt(0) ?? 0;
  let start = codePoint;
  while (start > 0 && DECIMAL_DIGIT.test(String.fromCodePoint(start - 1))) {
    start -= 1;
  }
  return (codePoint - start) % 10;
}

function toInt(digits: string): number {
  let value = 0;
  for (const digit of digits) {
    value = value * 10 + digitValue(digit);
  }
  return value;
}

/** Python's `len`: code points, not UTF-16 units. */
function length(text: string): number {
  return Array.from(text).length;
}

/** `datetime.date(year, month, day).isoformat()`, or null where Python raises. */
function realDay(year: number, month: number, day: number): string | null {
  if (year < 1 || year > 9999 || month < 1 || month > 12 || day < 1) {
    return null;
  }
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1];
  if (day > days) {
    return null;
  }
  const pad = (value: number, width: number) => String(value).padStart(width, "0");
  return `${pad(year, 4)}-${pad(month, 2)}-${pad(day, 2)}`;
}

/** The server's exceptions, kept inside this module: nothing public throws. */
class Refused extends Error {
  readonly refusal: PrintedDateRefusal;

  constructor(refusal: PrintedDateRefusal) {
    super(refusal);
    this.refusal = refusal;
  }
}

function named(text: string): string | null {
  const match = NAMED_DATE.exec(text);
  if (match === null) {
    return null;
  }
  const month = TURKISH_MONTHS.get(foldTr(match[2]));
  if (month === undefined) {
    return null;
  }
  return realDay(toInt(match[3]), month, toInt(match[1]));
}

/** `parse_printed_date`, line for line. Throws `Refused`. */
function resolve(printed: string, order: DateOrder | null): string {
  const text = printed.replace(EDGE_SPACE, "");
  const byName = named(text);
  if (byName !== null) {
    return byName;
  }
  const match = NUMERIC_DATE.exec(text);
  if (match === null) {
    throw new Refused("unreadable");
  }
  const [, first, , middle, last] = match;
  if (length(first) === 4 && length(last) === 4) {
    throw new Refused("unreadable");
  }
  if (length(first) === 4) {
    // a four-digit leading component is a year, and year-first is
    // year-month-day in every notation that writes one
    const yearFirst = realDay(toInt(first), toInt(middle), toInt(last));
    if (yearFirst === null) {
      throw new Refused("unreadable");
    }
    return yearFirst;
  }
  if (length(last) !== 4) {
    // no century is inferred: 26 is as much 1926 as 2026
    throw new Refused("unreadable");
  }
  const year = toInt(last);
  const a = toInt(first);
  const b = toInt(middle);
  const dayFirst = realDay(year, b, a);
  const monthFirst = realDay(year, a, b);
  const readings =
    order === "day_first"
      ? [dayFirst]
      : order === "month_first"
        ? [monthFirst]
        : [dayFirst, monthFirst];
  const valid = readings.filter((reading): reading is string => reading !== null);
  if (valid.length === 0) {
    throw new Refused("unreadable");
  }
  if (new Set(valid).size > 1) {
    throw new Refused("ambiguous");
  }
  return valid[0];
}

/** `find_printed_date`, line for line. Throws `Refused`. */
function scan(text: string, order: DateOrder | null): string {
  const found = new Set<string>();
  for (const match of text.matchAll(NAMED_DATE_SCAN)) {
    if (TURKISH_MONTHS.has(foldTr(match[2]))) {
      found.add(resolve(match[0], order));
    }
  }
  for (const match of text.matchAll(NUMERIC_DATE_SCAN)) {
    found.add(resolve(match[0], order));
  }
  if (found.size === 0) {
    throw new Refused("not_found");
  }
  if (found.size > 1) {
    throw new Refused("ambiguous");
  }
  return [...found][0];
}

function settle(read: () => string): PrintedDate {
  try {
    return { ok: true, iso: read() };
  } catch (error) {
    if (error instanceof Refused) {
      return { ok: false, refusal: error.refusal };
    }
    throw error;
  }
}

/**
 * One printed date, or the reason it is refused. `order` is passed only
 * where a human has stated the order the source prints.
 */
export function parsePrintedDate(printed: string, order: DateOrder | null = null): PrintedDate {
  return settle(() => resolve(printed, order));
}

/** The one date a message states, or the reason none is taken. */
export function findPrintedDate(text: string, order: DateOrder | null = null): PrintedDate {
  return settle(() => scan(text, order));
}

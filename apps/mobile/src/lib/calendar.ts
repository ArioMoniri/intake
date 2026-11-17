/**
 * Calendar model for the Vizitlerim takvim view (02 §4).
 *
 * Pure TS — no react-native import — so the month-grid arithmetic and the
 * date-name formatting are unit-testable in node, the same split lib/theme.ts
 * and lib/visits.ts use. The component (components/VisitCalendar.tsx) is the
 * thin View/Pressable adapter over this.
 *
 * Three rules baked into the shapes here rather than documented elsewhere:
 * - the grid is Monday-first (Turkey and e-Nabız/MHRS start the week on
 *   Monday) and always six rows, so the calendar never changes height as the
 *   patient pages between months;
 * - a dateless visit is NOT on the calendar at all — it has no day to sit on
 *   (02 §2b: inventing a day is a lie the reminders and note-staleness clock
 *   would trust). It stays reachable in the Liste view's "Yaklaşan" group;
 * - month and weekday NAMES come from Intl, never from a hardcoded table:
 *   the app already renders Turkish dates this way (components/VisitCard.tsx),
 *   so there is one source of localized date text and no parallel catalog of
 *   month names to drift from the platform (invariant 5 governs authored
 *   copy, not the calendar of the Gregorian year).
 */

export interface YearMonth {
  /** Full year, e.g. 2026. */
  readonly year: number;
  /** Month index 0–11 (January = 0), matching `Date` and `Intl`. */
  readonly month: number;
}

export interface CalendarCell {
  /** ISO `YYYY-MM-DD` — the key visits are matched on. */
  readonly iso: string;
  /** Day-of-month 1–31, the numeral the cell renders. */
  readonly day: number;
  /** Whether this cell belongs to the displayed month (vs. a spill day). */
  readonly inMonth: boolean;
  /** Whether this cell is the caller's "today". */
  readonly isToday: boolean;
  /** How many of the passed visits fall on this day (0 = no marker). */
  readonly visitCount: number;
}

export interface CalendarGrid extends YearMonth {
  /** Six rows of seven cells, Monday-first. */
  readonly weeks: readonly (readonly CalendarCell[])[];
}

type Locale = "tr" | "en";

const INTL_LOCALE: Record<Locale, string> = { tr: "tr-TR", en: "en-GB" };

function pad2(value: number): string {
  return value < 10 ? `0${value}` : `${value}`;
}

/** Compose an ISO date from a year, a 0–11 month and a day. */
export function toIso(year: number, month: number, day: number): string {
  return `${year}-${pad2(month + 1)}-${pad2(day)}`;
}

/** Split an ISO date into its parts, with the month back to a 0–11 index. */
export function parseIso(iso: string): YearMonth & { readonly day: number } {
  const [year, month, day] = iso.split("-").map(Number);
  return { year, month: month - 1, day };
}

/** The year+month of an ISO date. */
export function monthOf(iso: string): YearMonth {
  const { year, month } = parseIso(iso);
  return { year, month };
}

/** Step a YearMonth forwards or backwards, carrying across year boundaries. */
export function addMonths({ year, month }: YearMonth, delta: number): YearMonth {
  const total = year * 12 + month + delta;
  return { year: Math.floor(total / 12), month: ((total % 12) + 12) % 12 };
}

export function sameMonth(a: YearMonth, b: YearMonth): boolean {
  return a.year === b.year && a.month === b.month;
}

/** Days in a 0–11 month, leap years handled by `Date`. */
export function daysInMonth(year: number, month: number): number {
  return new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
}

/** Monday-first weekday index (Monday = 0 … Sunday = 6) of an ISO date. */
function mondayIndex(date: Date): number {
  return (date.getUTCDay() + 6) % 7;
}

/**
 * Count how many visits fall on each day. A dateless visit contributes to no
 * day and is silently skipped — it is not on the calendar (02 §2b).
 */
export function countVisitsByDay(
  visits: readonly { readonly date: string | null }[],
): ReadonlyMap<string, number> {
  const counts = new Map<string, number>();
  for (const visit of visits) {
    if (visit.date === null) {
      continue;
    }
    counts.set(visit.date, (counts.get(visit.date) ?? 0) + 1);
  }
  return counts;
}

/**
 * Build the six-week Monday-first grid for a month, marking today and each
 * day's visit count. Six rows always, so paging between months never jumps
 * the layout (a five-row month pads to six).
 */
export function buildCalendarGrid(
  { year, month }: YearMonth,
  todayIso: string,
  visitCounts: ReadonlyMap<string, number>,
): CalendarGrid {
  const firstOfMonth = new Date(Date.UTC(year, month, 1));
  const leading = mondayIndex(firstOfMonth);
  const start = new Date(Date.UTC(year, month, 1 - leading));
  const weeks: CalendarCell[][] = [];
  for (let week = 0; week < 6; week += 1) {
    const row: CalendarCell[] = [];
    for (let weekday = 0; weekday < 7; weekday += 1) {
      const cursor = new Date(start);
      cursor.setUTCDate(start.getUTCDate() + week * 7 + weekday);
      const cellYear = cursor.getUTCFullYear();
      const cellMonth = cursor.getUTCMonth();
      const cellDay = cursor.getUTCDate();
      const iso = toIso(cellYear, cellMonth, cellDay);
      row.push({
        iso,
        day: cellDay,
        inMonth: cellMonth === month && cellYear === year,
        isToday: iso === todayIso,
        visitCount: visitCounts.get(iso) ?? 0,
      });
    }
    weeks.push(row);
  }
  return { year, month, weeks };
}

/** The visits that fall on one ISO day, in their given order. */
export function visitsOnDay<V extends { readonly date: string | null }>(
  visits: readonly V[],
  iso: string,
): V[] {
  return visits.filter((visit) => visit.date === iso);
}

/**
 * Past (dated, strictly before today) visits, most recent first. A dateless
 * visit is upcoming, not past (INT-134, lib/visits.ts) and never appears here.
 */
export function pastVisitsRecentFirst<V extends { readonly date: string | null }>(
  visits: readonly V[],
  todayIso: string,
): V[] {
  return visits
    .filter((visit): visit is V & { date: string } => visit.date !== null && visit.date < todayIso)
    .sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0));
}

/** The soonest dated visit on or after today, or `null` if there is none. */
function soonestUpcoming(
  visits: readonly { readonly date: string | null }[],
  todayIso: string,
): string | null {
  let soonest: string | null = null;
  for (const visit of visits) {
    if (visit.date === null || visit.date < todayIso) {
      continue;
    }
    if (soonest === null || visit.date < soonest) {
      soonest = visit.date;
    }
  }
  return soonest;
}

/**
 * The month the calendar should open on: the one holding the soonest booked
 * upcoming visit, so a patient with an appointment lands on it, else today's.
 */
export function initialMonth(
  visits: readonly { readonly date: string | null }[],
  todayIso: string,
): YearMonth {
  return monthOf(soonestUpcoming(visits, todayIso) ?? todayIso);
}

/**
 * The day the calendar should pre-select: the soonest booked upcoming visit,
 * else today — so the day panel below the grid is never empty on first open
 * when the patient has an appointment.
 */
export function initialSelectedDay(
  visits: readonly { readonly date: string | null }[],
  todayIso: string,
): string {
  return soonestUpcoming(visits, todayIso) ?? todayIso;
}

/** "Eylül 2026" / "September 2026" — the month-picker heading. */
export function monthTitle({ year, month }: YearMonth, locale: Locale): string {
  return new Intl.DateTimeFormat(INTL_LOCALE[locale], {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(Date.UTC(year, month, 1)));
}

/**
 * The seven weekday column headers, Monday-first. Anchored on 2024-01-01,
 * which was a Monday, so the order matches `buildCalendarGrid` by
 * construction rather than by a hand-kept table.
 */
export function weekdayHeaders(locale: Locale): string[] {
  const format = new Intl.DateTimeFormat(INTL_LOCALE[locale], {
    weekday: "short",
    timeZone: "UTC",
  });
  const headers: string[] = [];
  for (let offset = 0; offset < 7; offset += 1) {
    headers.push(format.format(new Date(Date.UTC(2024, 0, 1 + offset))));
  }
  return headers;
}

/** "5 Eylül 2026 Cumartesi" — a full spoken date for a day's accessible name. */
export function longDate(iso: string, locale: Locale): string {
  const { year, month, day } = parseIso(iso);
  return new Intl.DateTimeFormat(INTL_LOCALE[locale], {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(Date.UTC(year, month, day)));
}

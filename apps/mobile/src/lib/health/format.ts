/**
 * Display formatting for device health values (INT-200), under the
 * invariant-22 display discipline even though these are wellness metrics,
 * not clinical quantities: `useGrouping:false` for every number, and
 * number + unit joined into ONE non-breaking atom. Numerals are allowed in
 * on-screen data values; what is banned is a numeral reaching any TTS
 * path — nothing in lib/health touches speech (test-enforced).
 */
import { t, type Locale } from "../i18n";
import type { HealthRange, HealthSummary, RawHealthSamples } from "./types";

export const NBSP = "\u00A0";
const EN_DASH = "–";

const INTL_LOCALE: Record<Locale, string> = { tr: "tr-TR", en: "en-US" };

function formatNumber(value: number, locale: Locale): string {
  return new Intl.NumberFormat(INTL_LOCALE[locale], {
    useGrouping: false,
    maximumFractionDigits: 1,
  }).format(value);
}

/** `7842␣adım` — the number and its unit are one non-breaking atom. */
export function formatQuantity(value: number, unit: string, locale: Locale): string {
  return `${formatNumber(value, locale)}${NBSP}${unit}`;
}

/** `58–64␣atım/dk`; a degenerate range collapses to a single quantity. */
export function formatRange(lo: number, hi: number, unit: string, locale: Locale): string {
  if (lo === hi) {
    return formatQuantity(lo, unit, locale);
  }
  return `${formatNumber(lo, locale)}${EN_DASH}${formatNumber(hi, locale)}${NBSP}${unit}`;
}

/** Local calendar day as YYYY-MM-DD (device timezone — where the patient is). */
export function localISODay(date: Date): string {
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

/** Seven calendar days ending now: local midnight six days back → now. */
export function lastSevenDayRange(now: Date): HealthRange {
  const start = new Date(now);
  start.setDate(start.getDate() - 6);
  start.setHours(0, 0, 0, 0);
  return { startISO: start.toISOString(), endISO: now.toISOString() };
}

/**
 * Raw device samples → display strings. Absent data stays absent (null /
 * empty) — no value is ever invented to fill a card.
 */
export function buildSummary(raw: RawHealthSamples, locale: Locale): HealthSummary {
  const stepsUnit = t("health.unit.steps", locale);
  const steps = raw.stepsByDay.map((day) => ({
    dateISO: day.dateISO,
    value: formatQuantity(Math.round(day.count), stepsUnit, locale),
  }));

  let restingHeartRate: string | null = null;
  if (raw.restingHeartRateBpm.length > 0) {
    const rounded = raw.restingHeartRateBpm.map((bpm) => Math.round(bpm));
    restingHeartRate = formatRange(
      Math.min(...rounded),
      Math.max(...rounded),
      t("health.unit.bpm", locale),
      locale,
    );
  }

  let sleepHours: string | null = null;
  if (raw.sleepSessions.length > 0) {
    const minutesByNight = new Map<string, number>();
    for (const session of raw.sleepSessions) {
      minutesByNight.set(
        session.endDateISO,
        (minutesByNight.get(session.endDateISO) ?? 0) + session.minutes,
      );
    }
    const totals = [...minutesByNight.values()];
    const averageHours = totals.reduce((sum, m) => sum + m, 0) / totals.length / 60;
    sleepHours = formatQuantity(
      Math.round(averageHours * 10) / 10,
      t("health.unit.hours", locale),
      locale,
    );
  }

  return { steps, restingHeartRate, sleepHours };
}

/**
 * The labelled block the patient attaches to the visit note draft — one
 * line per metric, absent metrics skipped. Pure text; the review screen
 * frames it with the fixed provenance line (`review.healthProvenance`).
 */
export function summaryNoteLines(summary: HealthSummary, locale: Locale): string[] {
  const lines: string[] = [];
  if (summary.steps.length > 0) {
    const days = summary.steps.map((day) => `${day.dateISO} ${day.value}`).join(" · ");
    lines.push(`${t("health.steps.label", locale)}: ${days}`);
  }
  if (summary.restingHeartRate !== null) {
    lines.push(`${t("health.rhr.label", locale)}: ${summary.restingHeartRate}`);
  }
  if (summary.sleepHours !== null) {
    lines.push(`${t("health.sleep.label", locale)}: ${summary.sleepHours}`);
  }
  return lines;
}

/**
 * The app's one reading of "now" and "today" (INT-409).
 *
 * Before INT-409 Vizitlerim read "today" from a constant, in every build
 * including release, so a visit next week could show as past and a past one
 * as upcoming. Two rules replace it:
 *
 * - The instant comes from an injected `Clock`. Screens pass `deviceClock`,
 *   the device's own time. A test passes a fixed clock, so no test depends on
 *   the day it runs and no build carries a pinned date
 *   (e2e/pinnedToday.spec.ts holds the tree to that).
 * - The calendar day is the day in Europe/Istanbul, where the visits are
 *   booked. The server anchors visit times in the same zone
 *   (intake_platform.doctor_link). A phone set to another zone, or the three
 *   hours after midnight in Istanbul when UTC still names yesterday, agree with
 *   the hospital about which day it is.
 *
 * Pure TS with no react-native import, so it is node-testable (the
 * lib/calendar.ts split).
 */

/** The zone every date boundary in the app is drawn in. */
export const APP_TIME_ZONE = "Europe/Istanbul";

/** Answers the current instant. Injected, so a test can fix it. */
export type Clock = () => Date;

/** The device's own clock: what every screen passes. */
export const deviceClock: Clock = () => new Date();

/** The ISO `YYYY-MM-DD` of the calendar day `instant` falls on in `timeZone`. */
export function isoDateIn(instant: Date, timeZone: string = APP_TIME_ZONE): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(instant);
  const part = (type: "year" | "month" | "day"): string =>
    parts.find((candidate) => candidate.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")}`;
}

/** Today's ISO date in the app's time zone, as `clock` reads it. */
export function todayIso(clock: Clock): string {
  return isoDateIn(clock());
}

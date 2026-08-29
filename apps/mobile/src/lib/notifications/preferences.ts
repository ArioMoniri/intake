/**
 * INT-141 — the patient's notification controls, as pure functions.
 *
 * The arithmetic mirrors the server's
 * (`intake_platform.notifications.preferences`) deliberately: half-open
 * window, wrap around midnight, both ends or neither, no invented default.
 * The client is not the authority — the server register is (it has to
 * survive more than this process) — but a client that computed "quiet"
 * differently would show the patient a state the server does not hold.
 *
 * Nothing here composes a notification BODY. Bodies are constants in the
 * server catalogue, for the reason set out there: a client that assembles
 * its own reminder assembles it from the visit, the branch and the slots it
 * happens to have to hand, which is exactly the lock-screen disclosure this
 * issue exists to prevent.
 */

/** Wire shape, identical to `GET/PUT /v1/me/notifications`. */
export interface NotificationPrefs {
  optedOut: boolean;
  /** "HH:MM" local, or null when the patient has said nothing about hours. */
  quietStart: string | null;
  quietEnd: string | null;
}

export interface QuietPreset {
  start: string;
  end: string;
}

export type PrefsProblem = "half_window" | "empty_window" | "malformed_time";

export type PrefsCheck = { ok: true } | { ok: false; reason: PrefsProblem };

/**
 * A fresh patient has said nothing: not opted out, and NO window. The
 * absence is the point — files/10 §9 names quiet hours as a control and no
 * file names an hour, so the app offers choices and pre-selects none.
 */
export const DEFAULT_PREFS: NotificationPrefs = {
  optedOut: false,
  quietStart: null,
  quietEnd: null,
};

/**
 * The windows the picker offers. These are affordances, not a default: one
 * of them only ever applies because the patient tapped it. Offering a short
 * list rather than a free time field also keeps numeric text entry out of
 * the app (invariant 22).
 */
export const QUIET_PRESETS: readonly QuietPreset[] = [
  { start: "21:00", end: "07:00" },
  { start: "22:00", end: "08:00" },
  { start: "23:00", end: "09:00" },
];

const TIME_OF_DAY = /^([01][0-9]|2[0-3]):([0-5][0-9])$/u;

/** Minutes since local midnight, or null when the text is not a time. */
export function parseTimeOfDay(value: string): number | null {
  const match = TIME_OF_DAY.exec(value);
  if (match === null) {
    return null;
  }
  return Number(match[1]) * 60 + Number(match[2]);
}

export function formatTimeOfDay(minuteOfDay: number): string {
  const hours = Math.floor(minuteOfDay / 60);
  const minutes = minuteOfDay % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

export function validatePrefs(prefs: NotificationPrefs): PrefsCheck {
  const { quietStart, quietEnd } = prefs;
  if ((quietStart === null) !== (quietEnd === null)) {
    return { ok: false, reason: "half_window" };
  }
  if (quietStart === null || quietEnd === null) {
    return { ok: true };
  }
  const start = parseTimeOfDay(quietStart);
  const end = parseTimeOfDay(quietEnd);
  if (start === null || end === null) {
    return { ok: false, reason: "malformed_time" };
  }
  if (start === end) {
    return { ok: false, reason: "empty_window" };
  }
  return { ok: true };
}

export function withOptOut(prefs: NotificationPrefs, optedOut: boolean): NotificationPrefs {
  return { ...prefs, optedOut };
}

export function withQuietWindow(prefs: NotificationPrefs, window: QuietPreset): NotificationPrefs {
  return { ...prefs, quietStart: window.start, quietEnd: window.end };
}

/** Both ends leave together — half a window is not a window. */
export function clearQuietWindow(prefs: NotificationPrefs): NotificationPrefs {
  return { ...prefs, quietStart: null, quietEnd: null };
}

/** Half-open, wrapping midnight: the start minute is quiet, the end is not. */
export function isQuiet(prefs: NotificationPrefs, minuteOfDay: number): boolean {
  if (prefs.quietStart === null || prefs.quietEnd === null) {
    return false;
  }
  const start = parseTimeOfDay(prefs.quietStart);
  const end = parseTimeOfDay(prefs.quietEnd);
  if (start === null || end === null) {
    return false;
  }
  if (start < end) {
    return minuteOfDay >= start && minuteOfDay < end;
  }
  return minuteOfDay >= start || minuteOfDay < end;
}

/** True when this preset is the one currently chosen. */
export function isPresetSelected(prefs: NotificationPrefs, window: QuietPreset): boolean {
  return prefs.quietStart === window.start && prefs.quietEnd === window.end;
}

/**
 * Device health connectors (INT-208): typed boundary between the UI and
 * HealthKit / Health Connect. Everything here is DEVICE-LOCAL by design —
 * health metrics are a new category of personal data and server persistence
 * has not been approved (CLAUDE.md: persisting new data categories needs the
 * human). No module in lib/health may perform a network call or write to
 * disk; values leave the phone only when the patient explicitly attaches
 * them to a visit note draft.
 */

/**
 * The honest capability ladder. `needs_dev_build` is the Expo Go truth: the
 * native modules cannot load there, and we say so instead of faking data.
 */
export type HealthAvailabilityStatus =
  "ok" | "needs_dev_build" | "platform_unsupported" | "permission_denied";

export interface HealthAvailability {
  readonly status: HealthAvailabilityStatus;
}

/** Half-open time window in ISO datetime strings. */
export interface HealthRange {
  readonly startISO: string;
  readonly endISO: string;
}

/** One day's step total, already formatted for display (invariant 22). */
export interface StepsDay {
  readonly dateISO: string;
  readonly value: string;
}

/**
 * Display-ready summary: values are STRINGS formatted with useGrouping:false
 * and the number+unit joined into one non-breaking atom. Raw numerics stay
 * inside lib/health so no caller can re-format them unguarded.
 */
export interface HealthSummary {
  readonly steps: readonly StepsDay[];
  readonly restingHeartRate: string | null;
  readonly sleepHours: string | null;
}

/** Raw device samples as the platform adapters deliver them. */
export interface RawHealthSamples {
  readonly stepsByDay: readonly { readonly dateISO: string; readonly count: number }[];
  readonly restingHeartRateBpm: readonly number[];
  readonly sleepSessions: readonly { readonly endDateISO: string; readonly minutes: number }[];
}

export interface HealthConnector {
  available(): Promise<HealthAvailability>;
  readSummary(range: HealthRange): Promise<HealthSummary>;
}

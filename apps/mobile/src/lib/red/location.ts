/**
 * The RED location axis on the device (INT-446; files/02 §5.3 Axis 3;
 * CLAUDE.md invariant 21): "derived from the visit lifecycle state plus the
 * mode. It is never asked when it can be known, and never assumed when it
 * cannot."
 *
 * - REMOTE — Hızlı (fast) mode on a visit that is planned or confirmed for a
 *   later day: the patient is at home, hours or days before the visit.
 * - ON_SITE — Detaylı mode on a visit with a check-in event. This client
 *   records no check-in event (the visit model carries a date, not a
 *   lifecycle state), so it never derives ON_SITE: claiming the patient is in
 *   the building without the event is the guess the table forbids. ON_SITE
 *   reaches the screen through the one location question, or from a server
 *   that holds the check-in.
 * - UNKNOWN — everything else: Detaylı without a check-in, the visit day
 *   itself ("a fast-mode session started in the car park"), a kiosk.
 *
 * Pure; dates are compared as calendar days in ISO form.
 */
import type { RedLocation } from "../livekit/red";

export interface RedLocationInput {
  readonly mode: "hizli" | "detayli";
  /** The visit's ISO date, or null when it is not booked yet (02 §2b: planned). */
  readonly visitDate: string | null;
  /** Today, as an ISO calendar date. */
  readonly today: string;
  /** A clinic-provisioned shared device (INT-143). */
  readonly kiosk: boolean;
}

export function deriveRedLocation({
  mode,
  visitDate,
  today,
  kiosk,
}: RedLocationInput): RedLocation {
  if (kiosk || mode !== "hizli") {
    return "UNKNOWN";
  }
  if (visitDate === null) {
    return "REMOTE";
  }
  return visitDate.slice(0, 10) > today ? "REMOTE" : "UNKNOWN";
}

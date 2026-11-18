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
 * INT-604 (owner decision M3, 17 Nov 2026, D18 scope): the up-front intake
 * question asks ONE thing — "Şu anda hastanede misiniz?" — and the mode follows
 * from the answer, as 02 §2 defines the modes by place (Hızlı pre-hospital,
 * Detaylı in-hospital). It used to offer "Hastanedeyim" beside "Kısa tutalım",
 * a place beside a preference, so a patient in the corridor who wanted it
 * short picked the REMOTE-eligible answer. Now:
 *
 * - "Hayır, hastanede değilim" (hızlı) on a later-day visit is REMOTE: an
 *   explicit answer, and the visit cannot be under way;
 * - "Evet, hastanedeyim" (detaylı) is UNKNOWN here. The answer may be hours old
 *   by the time a RED fires, and ON_SITE removes the 112 affordance, so the RED
 *   asks its own question at RED time; that fresh explicit "Evet" is the only
 *   way the device reaches ON_SITE (store.ts, `RedLocationQuestion.onYes`).
 * - no answer, the visit day, a kiosk: UNKNOWN. No answer is never read as one:
 *   the chooser shows before anything else until it is answered
 *   (note.ts `modeChoiceNeeded`).
 *
 * Pure; dates are compared as calendar days in ISO form.
 */
import type { MessageKey } from "../i18n";
import type { RedLocation } from "../livekit/red";

/** One answer to the up-front location question and the mode it selects. */
export interface ModeChoiceOption {
  readonly labelKey: MessageKey;
  readonly subKey: MessageKey;
  readonly mode: "hizli" | "detayli";
}

/**
 * The up-front question's answers, in display order. Both are location
 * answers; neither is a preference (INT-604). `location.test.ts` pins that no
 * answer here can make `deriveRedLocation` return ON_SITE.
 */
export const MODE_CHOICES: readonly ModeChoiceOption[] = [
  { labelKey: "intake.mode.hospital", subKey: "intake.mode.hospitalSub", mode: "detayli" },
  { labelKey: "intake.mode.away", subKey: "intake.mode.awaySub", mode: "hizli" },
];

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

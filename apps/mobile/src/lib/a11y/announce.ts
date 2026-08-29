/**
 * When a status change is worth speaking (INT-144).
 *
 * Split out of ./prefs as a pure function because the first version of this
 * rule had a bug that only a test would have caught: it returned early on
 * `null` WITHOUT clearing the remembered value, so the sequence A → null → A
 * announced A once. That sequence is the ordinary path in the voice dialogue
 * (speaking → confirming, which has no status → speaking again), so the
 * second turn's state went unannounced.
 *
 * The rule: announce a non-null message that differs from the last thing the
 * screen showed, and always remember what the screen is showing now —
 * including nothing.
 */
export interface Announcement {
  /** What to say, or null to stay quiet. */
  readonly speak: string | null;
  /** What the caller must remember as "currently shown". */
  readonly remember: string | null;
}

export function nextAnnouncement(previous: string | null, message: string | null): Announcement {
  if (message === null) {
    // Nothing is shown now. Remember that, so the same message returning
    // later is a real transition and gets announced again.
    return { speak: null, remember: null };
  }
  if (message === previous) {
    return { speak: null, remember: previous };
  }
  return { speak: message, remember: message };
}

/**
 * When a status change is worth speaking (INT-144), and how each platform
 * hears it (INT-362).
 *
 * Split out of ./prefs as pure functions because the first version of this
 * rule had a bug that only a test would have caught: it returned early on
 * `null` WITHOUT clearing the remembered value, so the sequence A → null → A
 * announced A once. That sequence is the ordinary path in the voice dialogue
 * (speaking → confirming, which has no status → speaking again), so the
 * second turn's state went unannounced.
 *
 * The rule: announce a non-empty message that differs from the last thing the
 * screen showed, and always remember what the screen is showing now —
 * including nothing.
 */
import { labelled } from "./labels";

export interface Announcement {
  /** What to say, or null to stay quiet. */
  readonly speak: string | null;
  /** What the caller must remember as "currently shown". */
  readonly remember: string | null;
}

export function nextAnnouncement(previous: string | null, message: string | null): Announcement {
  if (message === null || message.trim() === "") {
    // Nothing is shown now. Remember that, so the same message returning
    // later is a real transition and gets announced again. An empty string
    // is nothing too: posted to VoiceOver it would cut off whatever was
    // being read and say nothing in its place.
    return { speak: null, remember: null };
  }
  if (message === previous) {
    return { speak: null, remember: previous };
  }
  return { speak: message, remember: message };
}

/**
 * What a line on screen is (INT-362): an `error` the patient must know about
 * before going on, or a `status` — a wait, an outcome — that can wait its turn.
 */
export type LineTone = "error" | "status";

/** The two politeness levels both platforms share. */
export type Politeness = "polite" | "assertive";

/** An error interrupts what is being read; a status waits for a gap. */
export function politenessOf(tone: LineTone): Politeness {
  return tone === "error" ? "assertive" : "polite";
}

/**
 * The words a screen reader hears for a line (SC 3.3.1).
 *
 * A screen reader meets an error line with no colour and no position to tell
 * it apart from the hint beside it, so an error is spoken with the error word
 * first ("Hata: …"). The VISIBLE copy is never changed — this is only what is
 * spoken — and a line whose visible copy already opens with the word is not
 * given it twice. The error word is passed in (the catalogue's `a11y.error`),
 * so this stays free of the i18n runtime.
 */
export function spokenLine(tone: LineTone, message: string, errorWord: string): string {
  const shown = message.trim();
  if (shown === "" || tone === "status" || shown.startsWith(errorWord)) {
    return shown;
  }
  return labelled(errorWord, shown);
}

/** One call to `AccessibilityInfo.announceForAccessibilityWithOptions`. */
export interface IosAnnouncement {
  readonly text: string;
  readonly options: { readonly queue: boolean; readonly priority: "low" | "high" };
}

/**
 * The half VoiceOver hears, or null when this platform must not post one.
 *
 * iOS has no live regions, so a line is heard only when the app posts it: an
 * error interrupts and cannot itself be cut off by the focus move that often
 * follows it (high priority, not queued); a status is queued behind current
 * speech and yields (low priority).
 *
 * Android posts NOTHING here. There the line's own `accessibilityLiveRegion`
 * is what TalkBack reads, and an imperative announcement on top of it says
 * the line twice. The web build renders the live region as `aria-live`, so it
 * is in the same position.
 */
export function iosAnnouncement(
  os: string,
  speak: string | null,
  politeness: Politeness,
): IosAnnouncement | null {
  if (os !== "ios" || speak === null) {
    return null;
  }
  return politeness === "assertive"
    ? { text: speak, options: { queue: false, priority: "high" } }
    : { text: speak, options: { queue: true, priority: "low" } };
}

/**
 * One render of one announced line: what to post, and what to remember.
 * The hook in ./prefs is this plus the platform call, so everything that
 * decides what is said is provable without a device.
 */
export function lineStep(
  previous: string | null,
  message: string | null,
  os: string,
  politeness: Politeness,
): { readonly post: IosAnnouncement | null; readonly remember: string | null } {
  const { speak, remember } = nextAnnouncement(previous, message);
  return { post: iosAnnouncement(os, speak, politeness), remember };
}

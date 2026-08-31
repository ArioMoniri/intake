/**
 * The consent summary shown above **Gönder** (INT-137; 02 §5.4 *"consent
 * summary (what is shared, with whom, until when)"*).
 *
 * Three parts, each derived from something the patient can already see, so the
 * summary can never say more than the screen above it:
 *
 * - **what** — the title keys of the sections currently scoped ON, in the
 *   note's own order. It is `sentSections` that decides, not a second reading
 *   of the scopes, so the summary and the send can never disagree.
 * - **with whom** — the visit's hospital and department. `null` when the visit
 *   is unknown: a recipient nobody named is not filled in with a plausible
 *   one.
 * - **until when** — an ANCHOR, not a timestamp. 02 §2 pins the Doctor Link
 *   expiry to `visit_datetime + 72 h` and calls `issue_time + 72 h` *"the
 *   single most likely cause of 'the doctor couldn't see it' at P1"*, because
 *   a note prepared five days early expires before the clinician opens it.
 *   The device therefore states the rule and computes nothing: it holds no
 *   appointment time it could anchor to (a visit carries a date, not a
 *   datetime), and the clock belongs to whatever issues the link. This module
 *   reaches no `Date` at all, and the spec above pins that by absence.
 *
 * What this is NOT: it is not a share grant and it does not perform one. The
 * consent of record for a share is `share:{recipient,visit,sections,expiry}`
 * (files/06 §2), checked and audited server-side on
 * `services/api/src/intake_api/notes.py`. This is the patient-facing summary
 * of what sending means — invariant 4's UI half, never its enforcement.
 */
import type { MessageKey } from "../i18n";
import { sentSections, type NoteAccount, type NoteState } from "./note";

/**
 * 02 §2, verbatim: *"Doctor Link expiry is pinned to `visit_datetime + 72 h`,
 * never `issue_time + 72 h`."* Named so the anchor is a value the tests can
 * hold rather than a sentence in a comment.
 */
export const SHARE_EXPIRY_ANCHOR = "visit_datetime" as const;

/** Who the note goes to, as the visit already names them on screen. */
export interface ShareRecipient {
  hospital: string;
  department: string;
}

export interface ShareSummary {
  /** Title keys of the sections scoped ON, in note order. May be empty. */
  sections: MessageKey[];
  /** The visit's recipient, or null when there is no visit to name one. */
  recipient: ShareRecipient | null;
  /** The expiry's anchor. There is deliberately no computed timestamp. */
  expiryAnchor: typeof SHARE_EXPIRY_ANCHOR;
}

export function shareSummary(
  state: NoteState,
  account: NoteAccount,
  visit: ShareRecipient | null,
): ShareSummary {
  return {
    sections: sentSections(state, account).map((section) => section.titleKey),
    recipient: visit === null ? null : { hospital: visit.hospital, department: visit.department },
    expiryAnchor: SHARE_EXPIRY_ANCHOR,
  };
}

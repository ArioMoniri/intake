/**
 * The consent summary shown above **Gönder** (INT-137; 02 §5.4 *"consent
 * summary (what is shared, with whom, until when)"*).
 *
 * Three parts, each derived from something the patient can already see on the
 * screen above it, so the summary can never promise more than the send does:
 *
 * - **what** — the title keys of the sections currently scoped ON, in the
 *   note's own order. It is `sentSections` that decides, the same function the
 *   send path uses, so the summary and the send cannot disagree. A second
 *   reading of `scopes` here would be a second source of truth.
 * - **with whom** — the visit's hospital and department. `null` when there is
 *   no visit: a recipient nobody named is left unnamed rather than filled in
 *   with a plausible one.
 * - **until when** — an ANCHOR, not a timestamp. 02 §2 pins the Doctor Link
 *   expiry to `visit_datetime + 72 h` and calls `issue_time + 72 h` the single
 *   most likely cause of "the doctor couldn't see it", because a note prepared
 *   five days early expires before the clinician opens it. So the device
 *   states the rule and computes nothing: it holds no appointment *time* to
 *   anchor to (a visit fixture carries a date), and the clock belongs to
 *   whatever issues the link. This module reaches no `Date` at all and its
 *   spec pins that by absence.
 *
 * **What this is not.** It is not a share grant and it performs none. The
 * consent of record for a share is `share:{recipient,visit,sections,expiry}`
 * (files/06 §2), checked and audited server-side on the note routes
 * (`services/api/src/intake_api/notes.py`). This is invariant 4's patient-
 * facing half — what sending means, said before it happens — never its
 * enforcement.
 */
import type { MessageKey } from "../i18n";

import { sentSections, type NoteAccount, type NoteState } from "./note";

/**
 * 02 §2, verbatim: *"Doctor Link expiry is pinned to `visit_datetime + 72 h`,
 * never `issue_time + 72 h`."* Named so a test can hold the anchor as a value
 * rather than as a sentence in a comment.
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
  /** The visit's recipient, or null when no visit names one. */
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

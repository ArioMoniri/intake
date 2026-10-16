/**
 * INT-472: the review screen as iOS grouped inset lists. Each note section is
 * one group, and this module decides its rows and its footer, so the screen
 * only draws them (reviewRows.test.ts holds the order and the frozen state).
 *
 * The share summary above Gönder (02 §5.4) is a metadata group: what leaves,
 * who receives it and until when, each label over its values.
 */
import { joinParts } from "@/lib/a11y/labels";
import { t, type MessageKey } from "@/lib/i18n";

import type { CarriedFactKind } from "./carriedFacts";
import type { NoteSection } from "./note";
import type { ShareSummary } from "./share";

/** The intake question an edit row reopens (`intake?q=`). */
export type EditTarget = "complaint" | "duration" | "extra";

export type ReviewRow =
  | { readonly kind: "line"; readonly text: string }
  | { readonly kind: "facts"; readonly factKind: CarriedFactKind }
  | { readonly kind: "share"; readonly shared: boolean; readonly readOnly: boolean }
  | { readonly kind: "edit"; readonly target: EditTarget; readonly labelKey: MessageKey };

export interface ReviewGroup {
  readonly rows: readonly ReviewRow[];
  /** The section's own note, shown under the group; null when it has none. */
  readonly footerKey: MessageKey | null;
}

/**
 * Which carried-fact kind each note section reviews (INT-256). A section not
 * listed here shows no review block at all, so a fact can never be answered
 * under the wrong heading.
 */
const CARRIED_IN_SECTION: Readonly<Record<string, CarriedFactKind>> = {
  medications: "medication",
  allergies: "allergy",
};

/**
 * The questions a section's edit rows reopen. Medications come from the
 * profile and have no question to edit; the history section reopens the
 * duration and the patient's own note.
 */
const EDITS_IN_SECTION: Readonly<Record<string, readonly ReviewRow[]>> = {
  chief_complaint: [{ kind: "edit", target: "complaint", labelKey: "review.edit" }],
  hpi: [
    { kind: "edit", target: "duration", labelKey: "review.edit" },
    { kind: "edit", target: "extra", labelKey: "review.hpi.patientNote" },
  ],
};

const FOOTER_OF_SECTION: Readonly<Record<string, MessageKey>> = {
  medications: "review.medsNote",
  device_health: "review.healthProvenance",
};

export function reviewSectionRows(
  section: NoteSection,
  { shared, sent }: { readonly shared: boolean; readonly sent: boolean },
): ReviewGroup {
  const lines: ReviewRow[] = section.lines.map((text) => ({ kind: "line", text }));
  const factKind = CARRIED_IN_SECTION[section.id];
  const facts: ReviewRow[] = factKind === undefined ? [] : [{ kind: "facts", factKind }];
  const share: ReviewRow = { kind: "share", shared, readOnly: sent };
  // A sent note is frozen (02 §5.1): nothing reopens a question.
  const edits = sent ? [] : (EDITS_IN_SECTION[section.id] ?? []);
  return {
    rows: [...lines, ...facts, share, ...edits],
    footerKey: FOOTER_OF_SECTION[section.id] ?? null,
  };
}

export interface MetadataRowModel {
  readonly label: string;
  readonly values: readonly string[];
}

export function shareSummaryRows(summary: ShareSummary): MetadataRowModel[] {
  const sections: MetadataRowModel = {
    label: t("review.consent.sections"),
    values:
      summary.sections.length === 0
        ? [t("review.consent.nothing")]
        : summary.sections.map((titleKey) => t(titleKey)),
  };
  const recipient: MetadataRowModel[] =
    summary.recipient === null
      ? []
      : [
          {
            label: t("review.consent.recipient"),
            values: [joinParts(summary.recipient.hospital, summary.recipient.department)],
          },
        ];
  // The anchor, in words: the device holds no appointment time and 02 §2
  // forbids an issue-time clock, so there is no timestamp to render.
  const until: MetadataRowModel = {
    label: t("review.consent.until"),
    values: [t("review.consent.untilValue")],
  };
  return [sections, ...recipient, until];
}

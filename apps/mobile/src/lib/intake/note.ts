/**
 * Pre-visit note state (INT-179): pure builder + reducer so the review-and-
 * send rules are unit-testable in node. In-memory only — persistence and the
 * real note pipeline (INT-084) replace this. Two rules are load-bearing:
 * scope-off excludes a section from what is sent, and scope choices NEVER
 * block sending (02 §5.1 — sending is the patient's call).
 */
import type { TestAccount } from "../dev/accounts";
import { t, type MessageKey } from "../i18n";
import { allQuestions, optionLabelKey } from "./questions";

export interface Answer {
  questionId: string;
  values: string[];
}

export interface NoteSection {
  id: string;
  titleKey: MessageKey;
  lines: string[];
}

export interface NoteState {
  answers: Answer[];
  /** sectionId -> shared; absent means shared (default-on, visible label). */
  scopes: Record<string, boolean>;
  status: "draft" | "sent";
}

export type NoteAction =
  | { type: "answer"; questionId: string; values: string[] }
  | { type: "scope"; sectionId: string; shared: boolean }
  | { type: "send" };

export function emptyNoteState(): NoteState {
  return { answers: [], scopes: {}, status: "draft" };
}

export function noteReducer(state: NoteState, action: NoteAction): NoteState {
  switch (action.type) {
    case "answer": {
      const rest = state.answers.filter((a) => a.questionId !== action.questionId);
      return { ...state, answers: [...rest, { questionId: action.questionId, values: action.values }] };
    }
    case "scope":
      return { ...state, scopes: { ...state.scopes, [action.sectionId]: action.shared } };
    case "send":
      return { ...state, status: "sent" };
  }
}

function answerLines(answer: Answer): string[] {
  return answer.values.map((v) => {
    const key = optionLabelKey(answer.questionId, v);
    return key ? t(key) : v;
  });
}

function hasContent(answer: Answer | undefined): answer is Answer {
  return answer !== undefined && answer.values.some((v) => v.trim().length > 0);
}

/**
 * The clinician-bound brief in the standardized anamnesis order the
 * clinician expects: chief complaint (Başvuru nedeni) → history of the
 * present complaint (Şikâyet öyküsü: labelled duration + the patient's own
 * words, clearly attributed) → medications as reported. Section ids are
 * stable codes so the share-scope ledger and the future FHIR-composition
 * mapper (INT-084) address the same things. Provenance is the note's frame,
 * not a section — the review screen renders `review.provenance` under the
 * sections (06 §7: the note is patient-reported and diagnosis-free).
 */
export function buildNote(answers: Answer[], account: TestAccount): NoteSection[] {
  const byId = new Map(answers.map((a) => [a.questionId, a]));
  const sections: NoteSection[] = [];

  const complaint = byId.get("complaint");
  if (hasContent(complaint)) {
    sections.push({ id: "chief_complaint", titleKey: "review.section.cc", lines: answerLines(complaint) });
  }

  // Every answered dimension beyond the chief complaint becomes a labelled
  // HPI line, in the pack's question order (duration and the department
  // dimensions carry hpiLabelKey); the free note closes the section.
  const hpiLines: string[] = [];
  for (const question of allQuestions) {
    if (question.hpiLabelKey === undefined) {
      continue;
    }
    const answer = byId.get(question.id);
    if (hasContent(answer)) {
      hpiLines.push(`${t(question.hpiLabelKey)}: ${answerLines(answer).join(", ")}`);
    }
  }
  const extra = byId.get("extra");
  if (hasContent(extra)) {
    hpiLines.push(`${t("review.hpi.patientNote")}: ${answerLines(extra).join(" ")}`);
  }
  if (hpiLines.length > 0) {
    sections.push({ id: "hpi", titleKey: "review.section.hpi", lines: hpiLines });
  }

  if (account.medications.length > 0) {
    sections.push({
      id: "medications",
      titleKey: "review.section.medications",
      lines: [...account.medications],
    });
  }
  return sections;
}

/** What actually goes to the doctor: scope-off sections are excluded. */
export function sentSections(state: NoteState, account: TestAccount): NoteSection[] {
  return buildNote(state.answers, account).filter((s) => state.scopes[s.id] !== false);
}

/** Display status: a locally sent note wins over the fixture's ladder step. */
export function effectiveStatus(
  fixtureStatus: "draft" | "sent" | "viewed" | "filed" | null,
  state: NoteState | undefined,
): "draft" | "sent" | "viewed" | "filed" | null {
  if (state?.status === "sent" && (fixtureStatus === "draft" || fixtureStatus === null)) {
    return "sent";
  }
  if (state && state.answers.length > 0 && fixtureStatus === null) {
    return "draft";
  }
  return fixtureStatus;
}

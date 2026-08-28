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
  /**
   * Device health summary lines the patient explicitly attached (INT-208).
   * Device-local by design: they exist only in this in-memory draft, and
   * only because the patient confirmed the attach — never auto-filled.
   */
  healthLines: string[] | null;
}

export type NoteAction =
  | { type: "answer"; questionId: string; values: string[] }
  | { type: "scope"; sectionId: string; shared: boolean }
  | { type: "attachHealth"; lines: string[] }
  | { type: "send" };

export function emptyNoteState(): NoteState {
  return { answers: [], scopes: {}, status: "draft", healthLines: null };
}

export function noteReducer(state: NoteState, action: NoteAction): NoteState {
  switch (action.type) {
    case "answer": {
      const rest = state.answers.filter((a) => a.questionId !== action.questionId);
      return {
        ...state,
        answers: [...rest, { questionId: action.questionId, values: action.values }],
      };
    }
    case "scope":
      return { ...state, scopes: { ...state.scopes, [action.sectionId]: action.shared } };
    case "attachHealth":
      // A sent note is frozen; re-attaching on a draft replaces the block
      // (idempotent — never a duplicate section).
      return state.status === "sent" ? state : { ...state, healthLines: [...action.lines] };
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
export function buildNote(
  answers: Answer[],
  account: TestAccount,
  healthLines?: readonly string[] | null,
): NoteSection[] {
  const byId = new Map(answers.map((a) => [a.questionId, a]));
  const sections: NoteSection[] = [];

  const complaint = byId.get("complaint");
  if (hasContent(complaint)) {
    sections.push({
      id: "chief_complaint",
      titleKey: "review.section.cc",
      lines: answerLines(complaint),
    });
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

  // Device health block (INT-208): present only when the patient explicitly
  // attached it on Profilim; the review screen frames it with the fixed
  // provenance line (`review.healthProvenance`). Always the last section —
  // patient-reported history stays first.
  if (healthLines !== undefined && healthLines !== null && healthLines.length > 0) {
    sections.push({
      id: "device_health",
      titleKey: "review.section.health",
      lines: [...healthLines],
    });
  }
  return sections;
}

/** What actually goes to the doctor: scope-off sections are excluded. */
export function sentSections(state: NoteState, account: TestAccount): NoteSection[] {
  return buildNote(state.answers, account, state.healthLines).filter(
    (s) => state.scopes[s.id] !== false,
  );
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

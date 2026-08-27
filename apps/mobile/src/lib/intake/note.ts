/**
 * Pre-visit note state (INT-179): pure builder + reducer so the review-and-
 * send rules are unit-testable in node. In-memory only — persistence and the
 * real note pipeline (INT-084) replace this. Two rules are load-bearing:
 * scope-off excludes a section from what is sent, and scope choices NEVER
 * block sending (02 §5.1 — sending is the patient's call).
 */
import type { TestAccount } from "../dev/accounts";
import { t, type MessageKey } from "../i18n";
import { optionLabelKey } from "./questions";

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

const sectionTitle: Record<string, MessageKey> = {
  complaint: "review.section.complaint",
  duration: "review.section.duration",
  extra: "review.section.extra",
  medications: "review.section.medications",
};

/** Sections in fixed order; medications come from the profile fixture. */
export function buildNote(answers: Answer[], account: TestAccount): NoteSection[] {
  const byId = new Map(answers.map((a) => [a.questionId, a]));
  const sections: NoteSection[] = [];
  for (const id of ["complaint", "duration", "extra"] as const) {
    const answer = byId.get(id);
    if (answer && answer.values.some((v) => v.trim().length > 0)) {
      sections.push({ id, titleKey: sectionTitle[id], lines: answerLines(answer) });
    }
  }
  if (account.medications.length > 0) {
    sections.push({ id: "medications", titleKey: sectionTitle.medications, lines: [...account.medications] });
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

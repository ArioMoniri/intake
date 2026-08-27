/**
 * Typed-intake question fixtures (INT-179). One question per screen (Alan
 * pacing), chips grid for the complaint step (CVS Health pattern) — see
 * docs/design/mobile-ui.md §refs. These are UI fixtures, NOT clinical
 * protocol content: the real question set arrives compiled from
 * packages/protocols (INT-096) and replaces this module wholesale.
 */
import type { MessageKey } from "../i18n";

export interface IntakeOption {
  id: string;
  labelKey: MessageKey;
}

export interface IntakeQuestion {
  id: "complaint" | "duration" | "extra";
  kind: "chips" | "single" | "text";
  titleKey: MessageKey;
  hintKey?: MessageKey;
  options?: readonly IntakeOption[];
}

export const intakeQuestions: readonly IntakeQuestion[] = [
  {
    id: "complaint",
    kind: "chips",
    titleKey: "intake.q.complaint",
    hintKey: "intake.q.complaint.hint",
    options: [
      { id: "pain", labelKey: "intake.opt.pain" },
      { id: "fever", labelKey: "intake.opt.fever" },
      { id: "cough", labelKey: "intake.opt.cough" },
      { id: "dyspnoea", labelKey: "intake.opt.dyspnoea" },
      { id: "fatigue", labelKey: "intake.opt.fatigue" },
      { id: "stomach", labelKey: "intake.opt.stomach" },
      { id: "headache", labelKey: "intake.opt.headache" },
      { id: "other", labelKey: "intake.opt.other" },
    ],
  },
  {
    id: "duration",
    kind: "single",
    titleKey: "intake.q.duration",
    options: [
      { id: "today", labelKey: "intake.opt.today" },
      { id: "days", labelKey: "intake.opt.days" },
      { id: "week", labelKey: "intake.opt.week" },
      { id: "month", labelKey: "intake.opt.month" },
    ],
  },
  {
    id: "extra",
    kind: "text",
    titleKey: "intake.q.extra",
    hintKey: "intake.q.extra.hint",
  },
];

export function optionLabelKey(questionId: string, optionId: string): MessageKey | null {
  const q = intakeQuestions.find((x) => x.id === questionId);
  return q?.options?.find((o) => o.id === optionId)?.labelKey ?? null;
}

/**
 * Typed-intake question packs (INT-179/194). One question per screen (Alan
 * pacing), chips grid for multi-select steps (CVS Health pattern) — see
 * docs/design/mobile-ui.md §refs.
 *
 * Department packs make the intake branch-aware: Kardiyoloji/İç Hastalıkları,
 * Nöroloji and KBB each get their own anamnesis dimensions on top of the
 * shared core (complaint → duration → … → free note). These are UI FIXTURES
 * carrying neutral anamnesis dimensions only — no red-flag logic, no
 * thresholds, no triage: the real compiled packs (packages/protocols,
 * INT-096) replace this module wholesale, and severity words replace any
 * numeric scale on the clinical path (invariant 22).
 */
import type { MessageKey } from "../i18n";

export interface IntakeOption {
  id: string;
  labelKey: MessageKey;
}

export interface IntakeQuestion {
  id: string;
  kind: "chips" | "single" | "text";
  titleKey: MessageKey;
  hintKey?: MessageKey;
  /** Short label used for this answer's line in the HPI section. */
  hpiLabelKey?: MessageKey;
  options?: readonly IntakeOption[];
}

const complaint: IntakeQuestion = {
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
};

const duration: IntakeQuestion = {
  id: "duration",
  kind: "single",
  titleKey: "intake.q.duration",
  hpiLabelKey: "review.hpi.duration",
  options: [
    { id: "today", labelKey: "intake.opt.today" },
    { id: "days", labelKey: "intake.opt.days" },
    { id: "week", labelKey: "intake.opt.week" },
    { id: "month", labelKey: "intake.opt.month" },
  ],
};

const extra: IntakeQuestion = {
  id: "extra",
  kind: "text",
  titleKey: "intake.q.extra",
  hintKey: "intake.q.extra.hint",
};

const cardioInternal: IntakeQuestion[] = [
  complaint,
  duration,
  {
    id: "pain_character",
    kind: "chips",
    titleKey: "intake.q.character",
    hintKey: "intake.q.complaint.hint",
    hpiLabelKey: "intake.hpi.character",
    options: [
      { id: "pressure", labelKey: "intake.opt.pressure" },
      { id: "stabbing", labelKey: "intake.opt.stabbing" },
      { id: "burning", labelKey: "intake.opt.burning" },
      { id: "dull", labelKey: "intake.opt.dull" },
    ],
  },
  {
    id: "trigger",
    kind: "single",
    titleKey: "intake.q.trigger",
    hpiLabelKey: "intake.hpi.trigger",
    options: [
      { id: "exertion", labelKey: "intake.opt.exertion" },
      { id: "rest", labelKey: "intake.opt.rest" },
      { id: "meals", labelKey: "intake.opt.meals" },
      { id: "no_pattern", labelKey: "intake.opt.noPattern" },
    ],
  },
  {
    id: "associated",
    kind: "chips",
    titleKey: "intake.q.associated",
    hintKey: "intake.q.complaint.hint",
    hpiLabelKey: "intake.hpi.associated",
    options: [
      { id: "sweating", labelKey: "intake.opt.sweating" },
      { id: "nausea", labelKey: "intake.opt.nausea" },
      { id: "palpitations", labelKey: "intake.opt.palpitations" },
      { id: "dyspnoea", labelKey: "intake.opt.dyspnoea" },
      { id: "none", labelKey: "intake.opt.none" },
    ],
  },
  extra,
];

const neuro: IntakeQuestion[] = [
  complaint,
  duration,
  {
    id: "onset",
    kind: "single",
    titleKey: "intake.q.onset",
    hpiLabelKey: "intake.hpi.onset",
    options: [
      { id: "sudden", labelKey: "intake.opt.sudden" },
      { id: "gradual", labelKey: "intake.opt.gradual" },
    ],
  },
  {
    id: "severity",
    kind: "single",
    titleKey: "intake.q.severity",
    hpiLabelKey: "intake.hpi.severity",
    options: [
      { id: "mild", labelKey: "intake.opt.mild" },
      { id: "moderate", labelKey: "intake.opt.moderate" },
      { id: "severe", labelKey: "intake.opt.severe" },
    ],
  },
  {
    id: "neuro_assoc",
    kind: "chips",
    titleKey: "intake.q.associated",
    hintKey: "intake.q.complaint.hint",
    hpiLabelKey: "intake.hpi.associated",
    options: [
      { id: "nausea", labelKey: "intake.opt.nausea" },
      { id: "light", labelKey: "intake.opt.lightSensitivity" },
      { id: "sound", labelKey: "intake.opt.soundSensitivity" },
      { id: "vision", labelKey: "intake.opt.visionChange" },
      { id: "numbness", labelKey: "intake.opt.numbness" },
      { id: "none", labelKey: "intake.opt.none" },
    ],
  },
  extra,
];

const ent: IntakeQuestion[] = [
  complaint,
  duration,
  {
    id: "side",
    kind: "single",
    titleKey: "intake.q.side",
    hpiLabelKey: "intake.hpi.side",
    options: [
      { id: "right", labelKey: "intake.opt.right" },
      { id: "left", labelKey: "intake.opt.left" },
      { id: "both", labelKey: "intake.opt.both" },
    ],
  },
  {
    id: "ent_assoc",
    kind: "chips",
    titleKey: "intake.q.associated",
    hintKey: "intake.q.complaint.hint",
    hpiLabelKey: "intake.hpi.associated",
    options: [
      { id: "sore_throat", labelKey: "intake.opt.soreThroat" },
      { id: "congestion", labelKey: "intake.opt.congestion" },
      { id: "hearing", labelKey: "intake.opt.hearingLoss" },
      { id: "tinnitus", labelKey: "intake.opt.tinnitus" },
      { id: "fever", labelKey: "intake.opt.fever" },
      { id: "none", labelKey: "intake.opt.none" },
    ],
  },
  extra,
];

const general: IntakeQuestion[] = [complaint, duration, extra];

const PACKS: { match: RegExp; questions: IntakeQuestion[] }[] = [
  { match: /kardiyoloji|ic hastalik|dahiliye/, questions: cardioInternal },
  { match: /noroloji/, questions: neuro },
  { match: /kulak|kbb|burun bogaz/, questions: ent },
];

/**
 * ASCII-fold Turkish for matching: locale lowercasing plus diacritic
 * stripping, so "İç Hastalıkları", "iç hastalık" and a truncated
 * "ic hastalik" all land in the same pack (combining-mark regexes proved
 * environment-fragile).
 */
function foldDepartment(department: string): string {
  return department
    .toLocaleLowerCase("tr-TR")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/ı/g, "i");
}

/** Department string (as the visit carries it) → its question pack. */
export function packForDepartment(department: string | undefined): IntakeQuestion[] {
  if (!department) {
    return general;
  }
  const normalized = foldDepartment(department);
  for (const pack of PACKS) {
    if (pack.match.test(normalized)) {
      return pack.questions;
    }
  }
  return general;
}

/** Every question across packs, unique by id — the note builder's lookup. */
export const allQuestions: readonly IntakeQuestion[] = (() => {
  const seen = new Map<string, IntakeQuestion>();
  for (const q of [...cardioInternal, ...neuro, ...ent, ...general]) {
    if (!seen.has(q.id)) {
      seen.set(q.id, q);
    }
  }
  return [...seen.values()];
})();

/** Kept for the generic (no-department) flows and existing tests. */
export const intakeQuestions: readonly IntakeQuestion[] = general;

export function optionLabelKey(questionId: string, optionId: string): MessageKey | null {
  const q = allQuestions.find((x) => x.id === questionId);
  return q?.options?.find((o) => o.id === optionId)?.labelKey ?? null;
}

/**
 * Realtime section panel view model (INT-235): the muayene sections of
 * the clinician note as they fill DURING the spoken dialogue. Pure and
 * node-testable; the sheet component renders these rows.
 *
 * Labels are PACK-driven — `hpiLabelKey` where the pack carries one, and
 * the exact complaint/extra labelling `buildNote` uses (review.section.cc
 * and review.hpi.patientNote) — never a hardcoded section list, so every
 * department pack shows its own anamnesis dimensions.
 *
 * Status semantics (invariant 1 posture):
 * - `answered`: the patient confirmed or typed it — it is in the note.
 * - `suggested`: a candidate exists but is NOT committed. Only pending
 *   suggestions (not the current turn's own candidate) are confirmable
 *   from the panel — the current turn confirms in the turn, never twice.
 * - `empty`: nothing yet.
 * `filled` counts answered rows with content — the strip's "x/y bölüm".
 * The profile-derived meds line is appended exactly as buildNote appends
 * its medications section: display-only, outside the pack counts.
 */
import type { MessageKey } from "../i18n";
import type { IntakeQuestion } from "../intake/questions";
import type { DialogueStreamState } from "./stream";
import type { DialogueCandidate } from "./turn";

export type SectionRowStatus = "empty" | "suggested" | "answered";

export interface SectionRow {
  questionId: string;
  labelKey: MessageKey;
  status: SectionRowStatus;
  values: string[];
  /** Verbatim patient words as provenance — display only, never spoken. */
  quote: string;
  /** True only for pending suggestions the panel row may confirm. */
  confirmable: boolean;
}

export interface SectionPanelModel {
  rows: SectionRow[];
  /** Answered rows with content — the strip's numerator. */
  filled: number;
  /** Pack sections — the strip's denominator (meds line excluded). */
  total: number;
}

/** The section label for one pack question — buildNote's exact mapping. */
export function sectionLabelKey(question: IntakeQuestion): MessageKey {
  if (question.hpiLabelKey !== undefined) {
    return question.hpiLabelKey;
  }
  if (question.id === "complaint") {
    return "review.section.cc";
  }
  if (question.id === "extra") {
    return "review.hpi.patientNote";
  }
  return question.titleKey;
}

/** The candidate the CURRENT turn is holding, if any (shown as suggested
 * in the panel, but confirmed in the turn itself — never from the row). */
function turnCandidate(state: DialogueStreamState): {
  questionIndex: number;
  candidate: DialogueCandidate;
} | null {
  const { turn } = state;
  if (turn.phase === "confirming" || (turn.phase === "speaking" && turn.intent === "confirm")) {
    return { questionIndex: turn.step, candidate: turn.candidate };
  }
  return null;
}

export function sectionPanelModel(
  pack: readonly IntakeQuestion[],
  state: DialogueStreamState,
  medications: readonly string[],
): SectionPanelModel {
  const current = turnCandidate(state);
  let filled = 0;
  const rows: SectionRow[] = pack.map((question, index) => {
    const labelKey = sectionLabelKey(question);
    const answer = state.answers[question.id];
    if (answer !== undefined) {
      if (answer.values.some((v) => v.trim().length > 0)) {
        filled += 1;
      }
      return {
        questionId: question.id,
        labelKey,
        status: "answered",
        values: [...answer.values],
        quote: answer.quote,
        confirmable: false,
      };
    }
    if (current !== null && current.questionIndex === index) {
      return {
        questionId: question.id,
        labelKey,
        status: "suggested",
        values: [...current.candidate.values],
        quote: current.candidate.quote,
        confirmable: false,
      };
    }
    const pending = state.pending[question.id];
    if (pending !== undefined) {
      return {
        questionId: question.id,
        labelKey,
        status: "suggested",
        values: [...pending.values],
        quote: pending.quote,
        confirmable: true,
      };
    }
    return {
      questionId: question.id,
      labelKey,
      status: "empty",
      values: [],
      quote: "",
      confirmable: false,
    };
  });
  if (medications.length > 0) {
    rows.push({
      questionId: "medications",
      labelKey: "review.section.medications",
      status: "answered",
      values: [...medications],
      quote: "",
      confirmable: false,
    });
  }
  return { rows, filled, total: pack.length };
}

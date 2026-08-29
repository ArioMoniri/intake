/**
 * Pre-visit note state (INT-179): pure builder + reducer so the review-and-
 * send rules are unit-testable in node. In-memory only — persistence and the
 * real note pipeline (INT-084) replace this. Two rules are load-bearing:
 * scope-off excludes a section from what is sent, and scope choices NEVER
 * block sending (02 §5.1 — sending is the patient's call).
 *
 * INT-236 adds the intake mode context (02 §2: Hızlı default, Hastanedeyim
 * → Detaylı), the environment privacy self-check (02 §33: with a third
 * party present, sensitive sections are DEFERRED — not asked quieter, not
 * asked in text — and the clinician sees `eksik: ortam uygun değildi`) and
 * the clinic-interruptible checkpoint (02 §34: "Sıranız geldi" checkpoints
 * instantly at the reducer level, zero lost turns). The mechanics mirror
 * what the compiled packs (packages/protocols dsl.py) will drive, so they
 * slot in without UX change.
 *
 * INT-247 replaces the account's `medications: string[]` with carried facts
 * (./carriedFacts). A fact recorded at an earlier visit is not a fact about
 * this one until the patient or a clinician says so, so the medications
 * section is built only from a `FactReconciliation` — and a fact the patient
 * reports having STOPPED prints a line of its own, because to a clinician
 * that is a different finding from an absent medication.
 */
import { t, type MessageKey } from "../i18n";
import {
  factNoteMarkerKey,
  formatFactDate,
  reconcileCarriedFacts,
  type CarriedFact,
  type FactDecision,
  type FactReconciliation,
  type FactReview,
} from "./carriedFacts";
import { allQuestions, askIfMet, optionLabelKey } from "./questions";

export interface Answer {
  questionId: string;
  values: string[];
}

/** 02 §2: Hızlı (pre-hospital, default) vs Detaylı (in-hospital). */
export type IntakeMode = "hizli" | "detayli";

/** Environment privacy per 02 §33 — asked once in Detaylı, one calm question. */
export type PrivacyState = "unchecked" | "private" | "not_private";

/**
 * The only deferral consumer today is the wellbeing entry point: the dev
 * packs carry no sensitive-flagged questions (the wellbeing instruments
 * are a separate, licence-BLOCKED surface — HB-L2/HB-L3), so the deferral
 * MECHANISM is live while wellbeing is its sole subscriber. Compiled packs
 * with sensitive sections join the same list.
 */
export const WELLBEING_DEFERRAL = "wellbeing";

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
  /** Intake mode (INT-236): Hızlı by default, Hastanedeyim sets Detaylı. */
  mode: IntakeMode;
  /** Environment self-check result (02 §33); asked only in Detaylı. */
  privacy: PrivacyState;
  /** Deferred section ids carried into the note as `eksik` markers. */
  deferred: string[];
  /** "Sıranız geldi" checkpoint flag (02 §34) — instant, resumable. */
  checkpointed: boolean;
  /**
   * What the patient (or a clinician) said about each carried fact IN THIS
   * VISIT, keyed by fact id (INT-247). An id absent from the map is
   * undecided — which is a state of its own, never a silent yes and never
   * a silent no (invariant 12).
   */
  factReview: Record<string, FactDecision>;
}

export type NoteAction =
  | { type: "answer"; questionId: string; values: string[] }
  | { type: "scope"; sectionId: string; shared: boolean }
  | { type: "attachHealth"; lines: string[] }
  | { type: "send" }
  | { type: "mode"; mode: IntakeMode }
  | { type: "privacy"; alone: boolean }
  | { type: "checkpoint" }
  | { type: "resume" }
  /** Decide a carried fact for this visit; `null` takes the answer back. */
  | { type: "fact"; factId: string; decision: FactDecision | null };

export function emptyNoteState(): NoteState {
  return {
    answers: [],
    scopes: {},
    status: "draft",
    healthLines: null,
    mode: "hizli",
    privacy: "unchecked",
    deferred: [],
    checkpointed: false,
    factReview: {},
  };
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
    case "mode":
      // A sent note is frozen — the same rule as attachHealth.
      return state.status === "sent" ? state : { ...state, mode: action.mode };
    case "privacy": {
      if (state.status === "sent") {
        return state;
      }
      if (action.alone) {
        // Privacy established — the deferral lifts because nothing was
        // asked yet, so nothing is lost; the entry point simply reopens.
        return {
          ...state,
          privacy: "private",
          deferred: state.deferred.filter((id) => id !== WELLBEING_DEFERRAL),
        };
      }
      // Third party present (02 §33): sensitive sections are DEFERRED —
      // not asked quieter, not asked in text, not asked at all here.
      return {
        ...state,
        privacy: "not_private",
        deferred: state.deferred.includes(WELLBEING_DEFERRAL)
          ? state.deferred
          : [...state.deferred, WELLBEING_DEFERRAL],
      };
    }
    case "checkpoint":
      // Instant (02 §34): no dialog, no confirmation, and — pinned by test —
      // zero lost turns: every committed answer survives untouched.
      return state.status === "sent" ? state : { ...state, checkpointed: true };
    case "resume":
      return state.status === "sent" ? state : { ...state, checkpointed: false };
    case "fact": {
      // A sent note is frozen — the same rule as attachHealth.
      if (state.status === "sent") {
        return state;
      }
      const next = { ...state.factReview };
      if (action.decision === null) {
        delete next[action.factId];
      } else {
        next[action.factId] = action.decision;
      }
      return { ...state, factReview: next };
    }
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
/** The slice of the signed-in account the note needs — both the dev
 * fixtures and real OTP accounts (INT-131) satisfy it. */
export interface NoteAccount {
  /**
   * Facts recorded at earlier visits (INT-247). CARRIED, not current: the
   * type has no "current medications" to read, so no caller can print one
   * without going through `reconcileCarriedFacts` and this visit's review.
   */
  carriedFacts: readonly CarriedFact[];
}

/**
 * The medications section, built only from a `FactReconciliation`. Four line
 * forms, each carrying who said what and when the fact was first recorded:
 *
 *   current      Metoprolol — hasta bu ziyarette devam ettiğini söyledi — …
 *   conflict     Metoprolol — hasta değiştiğini söyledi; yeni bilgi alınmadı — …
 *   stopped      Metoprolol — hasta bıraktığını söyledi — önceki kayıt: 12 Mayıs 2026
 *   unconfirmed  Metoprolol — bu ziyarette onaylanmadı — önceki kayıt: 12 Mayıs 2026
 *
 * `stopped` is deliberately a line and not an omission: to a clinician
 * "absent" and "the patient says they stopped it" are different findings,
 * and reconciling them is the point of files/04 §2 `meds_allergies`. Same
 * reason `unconfirmed` is printed rather than dropped — files/04 §5 already
 * models an unconfirmed history item (`pmh.status`), and hiding an
 * unreconciled medication would trade one silent error for another.
 *
 * One section, not four, because the section id is also the share-scope unit
 * the patient toggles (02 §5.1) and the server's `SectionId` literal.
 */
function medicationLines(reconciliation: FactReconciliation): string[] {
  const previously = (iso: string) => `${t("note.fact.previousRecord")}: ${formatFactDate(iso)}`;
  const resolved = [
    ...reconciliation.current,
    ...reconciliation.conflicted,
    ...reconciliation.stopped,
  ].map(
    (entry) =>
      `${entry.fact.text} — ${t(factNoteMarkerKey(entry))} — ${previously(entry.fact.assertedAt)}`,
  );
  const open = reconciliation.unconfirmed.map(
    (fact) => `${fact.text} — ${t("note.fact.unconfirmed")} — ${previously(fact.assertedAt)}`,
  );
  return [...resolved, ...open];
}

export function buildNote(
  answers: Answer[],
  account: NoteAccount,
  healthLines?: readonly string[] | null,
  deferred?: readonly string[],
  factReview?: FactReview,
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
      // An edit that unmet this answer's gate keeps the answer — patient
      // words are never silently discarded — and marks the line so the
      // review reads honestly (INT-236 "koşul değişti").
      const stale = question.askIf !== undefined && !askIfMet(question.askIf, answers);
      const line = `${t(question.hpiLabelKey)}: ${answerLines(answer).join(", ")}`;
      hpiLines.push(stale ? `${line} (${t("review.hpi.staleCondition")})` : line);
    }
  }
  const extra = byId.get("extra");
  if (hasContent(extra)) {
    hpiLines.push(`${t("review.hpi.patientNote")}: ${answerLines(extra).join(" ")}`);
  }
  if (hpiLines.length > 0) {
    sections.push({ id: "hpi", titleKey: "review.section.hpi", lines: hpiLines });
  }

  const medications = medicationLines(
    reconcileCarriedFacts(account.carriedFacts, factReview ?? {}),
  );
  if (medications.length > 0) {
    sections.push({
      id: "medications",
      titleKey: "review.section.medications",
      lines: medications,
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

  // Environment deferral (02 §33, INT-236): the clinician-visible marker is
  // the verbatim `eksik: ortam uygun değildi`. Always the LAST section —
  // what the patient said stays first. Wellbeing is the only deferral
  // consumer today (see WELLBEING_DEFERRAL).
  if (deferred !== undefined && deferred.includes(WELLBEING_DEFERRAL)) {
    sections.push({
      id: "deferred",
      titleKey: "review.section.deferred",
      lines: [`${t("note.deferred.wellbeing")} — ${t("note.deferred.marker")}`],
    });
  }
  return sections;
}

/** What actually goes to the doctor: scope-off sections are excluded. */
export function sentSections(state: NoteState, account: NoteAccount): NoteSection[] {
  return buildNote(
    state.answers,
    account,
    state.healthLines,
    state.deferred,
    state.factReview,
  ).filter((s) => state.scopes[s.id] !== false);
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

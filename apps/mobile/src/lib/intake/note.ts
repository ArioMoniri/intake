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
 *
 * INT-256 adds the three universal history sections. Their ids are the
 * `PreVisitNote` field names of files/04 §5 — `pmh`, `allergies`,
 * `family_social` — which are what `packages/clinical-schemas`
 * `NOTE_SECTION_IDS` and the composition mapper already key on, so no
 * section vocabulary is invented here. The allergies section carries both
 * the answers given this visit and the carried allergy facts, reconciled
 * exactly as medications are: never current until this visit says so.
 */
import { t, type MessageKey } from "../i18n";
import {
  factNoteMarkerKey,
  formatFactDate,
  reconcileCarriedFacts,
  type CarriedFact,
  type CarriedFactKind,
  type FactDecision,
  type FactReconciliation,
  type FactReview,
} from "./carriedFacts";
import {
  allQuestions,
  askIfMet,
  optionLabelKey,
  FAMILY_HISTORY_DEFERRAL,
  type DeferralId,
  type IntakeMode,
  type NoteSectionId,
} from "./questions";

export interface Answer {
  questionId: string;
  values: string[];
}

/**
 * 02 §2: Hızlı (pre-hospital, default) vs Detaylı (in-hospital). Defined in
 * ./questions since INT-256, because the pack layer is what the mode selects
 * a profile from; re-exported here so every existing importer is unchanged.
 */
export type { IntakeMode };

/** Environment privacy per 02 §33 — asked once in Detaylı, one calm question. */
export type PrivacyState = "unchecked" | "private" | "not_private";

/**
 * The wellbeing entry point — INT-236's deferral consumer, and the first of
 * two since INT-256 added family history (./questions
 * `FAMILY_HISTORY_DEFERRAL`). The wellbeing instruments are a separate,
 * licence-BLOCKED surface (HB-L2/HB-L3), so this id defers an entry point
 * rather than a set of pack questions; family history defers actual
 * questions. Compiled packs with sensitive sections join the same list.
 */
export const WELLBEING_DEFERRAL = "wellbeing" satisfies DeferralId;

/**
 * What the environment self-check defers, and the label each one carries into
 * the note. 02 §33's marker is the same for every row — the clinician sees
 * `eksik: ortam uygun değildi`, never a reason invented per section.
 */
const DEFERRAL_LABEL: Record<DeferralId, MessageKey> = {
  wellbeing: "note.deferred.wellbeing",
  family_history: "note.deferred.familyHistory",
};

/** Every unit the privacy answer defers, in the order the note lists them. */
export const DEFERRABLE_SECTIONS: readonly DeferralId[] = [
  WELLBEING_DEFERRAL,
  FAMILY_HISTORY_DEFERRAL,
];

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
      const deferrable = new Set<string>(DEFERRABLE_SECTIONS);
      if (action.alone) {
        // Privacy established — the deferral lifts because nothing was
        // asked yet, so nothing is lost; the sections simply reopen.
        return {
          ...state,
          privacy: "private",
          deferred: state.deferred.filter((id) => !deferrable.has(id)),
        };
      }
      // Third party present (02 §33): sensitive sections are DEFERRED —
      // not asked quieter, not asked in text, not asked at all here.
      // INT-256: family history joins wellbeing, because it is a disclosure
      // about people who are not in the room to consent to it.
      return {
        ...state,
        privacy: "not_private",
        deferred: [
          ...state.deferred,
          ...DEFERRABLE_SECTIONS.filter((id) => !state.deferred.includes(id)),
        ],
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
 * The carried-fact lines of one section, built only from a
 * `FactReconciliation`. Four line forms, each carrying who said what and
 * when the fact was first recorded:
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
 * INT-256: the same four forms serve allergies, in allergy words — the
 * marker key is chosen from `fact.kind` inside `factNoteMarkerKey`, so this
 * builder never has to know which kind it is rendering.
 */
function carriedFactLines(reconciliation: FactReconciliation): string[] {
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

/**
 * The four universal history sections of files/04 §5, in `PreVisitNote`
 * field order. One section id, one title, and the carried-fact kind (if any)
 * whose reconciliation is appended after what the patient said this visit.
 *
 * `medications` keeps its own id rather than folding into a single
 * `meds_allergies` block because the section id is the share-scope unit the
 * patient toggles (02 §5.1) and the id the composition mapper already emits;
 * a patient may share the medication list and withhold the family history.
 */
const HISTORY_SECTIONS: readonly {
  id: NoteSectionId;
  titleKey: MessageKey;
  carries: CarriedFactKind | null;
}[] = [
  { id: "pmh", titleKey: "review.section.pmh", carries: null },
  { id: "medications", titleKey: "review.section.medications", carries: "medication" },
  { id: "allergies", titleKey: "review.section.allergies", carries: "allergy" },
  { id: "family_social", titleKey: "review.section.familySocial", carries: null },
];

/**
 * The answered lines of one history section, in `allQuestions` order — the
 * same single ordering authority the HPI lines use, so the note follows the
 * interview here too. A gate the answers no longer meet marks the line
 * rather than dropping it (INT-236 "koşul değişti"): a deferral or an edit
 * never silently deletes something the patient said.
 */
function historyLines(
  section: NoteSectionId,
  byId: Map<string, Answer>,
  answers: Answer[],
): string[] {
  const lines: string[] = [];
  for (const question of allQuestions) {
    if (question.noteSection !== section || question.lineLabelKey === undefined) {
      continue;
    }
    const answer = byId.get(question.id);
    if (!hasContent(answer)) {
      continue;
    }
    const stale = question.askIf !== undefined && !askIfMet(question.askIf, answers);
    const line = `${t(question.lineLabelKey)}: ${answerLines(answer).join(", ")}`;
    lines.push(stale ? `${line} (${t("review.hpi.staleCondition")})` : line);
  }
  return lines;
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

  // The universal history (04 §1 rows 5–6 → 04 §5's own section ids). What
  // the patient said THIS visit comes first; the carried block follows it,
  // and a carried fact stays out of the "current" reading until this visit's
  // review resolves it (invariant 12, INT-247).
  for (const section of HISTORY_SECTIONS) {
    const lines = historyLines(section.id, byId, answers);
    if (section.carries !== null) {
      lines.push(
        ...carriedFactLines(
          reconcileCarriedFacts(
            account.carriedFacts.filter((fact) => fact.kind === section.carries),
            factReview ?? {},
          ),
        ),
      );
    }
    if (lines.length > 0) {
      sections.push({ id: section.id, titleKey: section.titleKey, lines });
    }
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

  // Environment deferral (02 §33, INT-236, second consumer in INT-256): the
  // clinician-visible marker is the verbatim `eksik: ortam uygun değildi`,
  // the same for every deferred unit — the note says WHAT is missing and
  // WHY the setting was wrong, never a reason invented per section. Always
  // the LAST section: what the patient said stays first. One section with a
  // line each, so the share-scope ledger still has one thing to toggle.
  const deferredLines = DEFERRABLE_SECTIONS.filter((id) => deferred?.includes(id) === true).map(
    (id) => `${t(DEFERRAL_LABEL[id])} — ${t("note.deferred.marker")}`,
  );
  if (deferredLines.length > 0) {
    sections.push({
      id: "deferred",
      titleKey: "review.section.deferred",
      lines: deferredLines,
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

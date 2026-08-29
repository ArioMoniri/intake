/**
 * Carried-forward clinical facts and their per-visit reconciliation.
 *
 * Owner bug: the app said "Metoprolol" because an earlier visit recorded it,
 * with nothing on screen that let the patient say they had stopped. Two
 * things are wrong with that and only one of them is the fixture.
 *
 * Invariant 12 read literally — "`PatientOverlay` facts require patient or
 * clinician confirmation (type-level)" — means a fact carried out of an
 * earlier visit is not yet a fact about THIS one. So the type says so:
 *
 *   - `CarriedFact` has no field that can be read as "current". Holding one
 *     tells you what was recorded before, and nothing about today.
 *   - `ReconciledFact` REQUIRES a `FactDecision`. There is no value of that
 *     type describing a fact nobody decided on, so no note line can be built
 *     from one. Undecided facts stay in `FactReconciliation.unconfirmed`,
 *     which is a `CarriedFact[]` — a different type, that the current-
 *     medications renderer cannot accept.
 *   - `reconcileCarriedFacts` is the only producer of `FactReconciliation`,
 *     and it is total: every carried fact lands in exactly one bucket, so a
 *     fact is never silently dropped either.
 *
 * The vocabulary is borrowed, not invented:
 *   - provenance ("where from") is `clinical_schemas.overlay.LearnedFactSource`
 *     (files/09 §3) — the same three confirmed sources, no unconfirmed member;
 *   - who is speaking is INT-133's `Attribution` (`../profile/attribution`),
 *     not a parallel notion of "who said it";
 *   - the outcome vocabulary is files/04 §5 `medications.reconciliation`:
 *     `matches | new | stopped | conflict`.
 *
 * What this module deliberately does NOT decide: what stopping a drug means
 * clinically. It records what the patient said, who said it and when. A
 * patient who says a medication changed produces `conflict` — the recorded
 * value and the patient's report disagree, and the clinician resolves it.
 * No new value is captured here: a medication string is free text that would
 * carry a dose, and free numeric entry on the clinical critical path is
 * barred by invariant 22. The patient's own words go through the existing
 * `extra` ("Hasta notu") question, which is already a note field.
 */
import type { MessageKey } from "../i18n";
import { getLocale } from "../i18n";
import type { Attribution } from "../profile/attribution";

/**
 * The three confirmed provenances a learned fact may carry (files/09 §3;
 * invariant 12). Mirrors `LearnedFactSource` in
 * `packages/clinical-schemas` (generated `models.ts`) key-for-key —
 * there is deliberately no unconfirmed/LLM member.
 */
export type CarriedFactSource =
  "confirmed_intake_extraction" | "clinician_accepted_note" | "confirmed_imported_record";

/**
 * Medications and allergies — two of the `PatientOverlay` categories
 * files/09 §3 names ("medication list and adherence pattern, allergies").
 * `allergy` joined in INT-256 on exactly the condition this comment already
 * set: its note section (files/04 §5 `PreVisitNote.allergies[]`) now exists.
 * Conditions and baselines join the same way when theirs do.
 */
export type CarriedFactKind = "medication" | "allergy";

/** Who asserted something — INT-133's vocabulary, not a parallel one. */
export type FactAsserter = { role: "patient"; attribution: Attribution } | { role: "clinician" };

/**
 * A fact recorded at an earlier visit. Carried, not current: on its own it
 * says only "this was written down before, by this person, on this day".
 */
export interface CarriedFact {
  id: string;
  kind: CarriedFactKind;
  /** Verbatim as it was recorded. Never re-worded, never re-derived. */
  text: string;
  source: CarriedFactSource;
  assertedBy: FactAsserter;
  /** ISO date of that earlier assertion (files/09 §3 12-month rule). */
  assertedAt: string;
  /** The visit it came out of, where there was one. */
  sourceVisitId: string | null;
}

/**
 * What the patient (or a clinician) said about a carried fact THIS visit.
 * `changed` records disagreement without capturing a replacement value.
 */
export type FactOutcome = "confirmed" | "changed" | "stopped";

export interface FactDecision {
  outcome: FactOutcome;
  by: FactAsserter;
  /** ISO timestamp of the decision — the "when" that reaches the note. */
  at: string;
}

/** Per-visit decisions, keyed by fact id. An absent id means undecided. */
export type FactReview = Readonly<Record<string, FactDecision>>;

/** files/04 §5 `medications.reconciliation`. `new` is not produced here —
 * it belongs to a medication the patient adds, not to a carried one. */
export type Reconciliation = "matches" | "stopped" | "conflict";

/** A carried fact plus the decision that resolved it. The decision is not
 * optional: that is where invariant 12 lives. */
export interface ReconciledFact {
  fact: CarriedFact;
  decision: FactDecision;
  reconciliation: Reconciliation;
}

export interface FactReconciliation {
  /** Discriminant so the shape reads honestly at a call site. */
  readonly kind: "fact-reconciliation";
  /** Confirmed still true this visit — the only bucket the note may print
   * as a current medication. */
  readonly current: readonly ReconciledFact[];
  /** The patient reports it is not as recorded; no replacement captured. */
  readonly conflicted: readonly ReconciledFact[];
  /** Explicitly reported stopped. A first-class outcome, not a deletion:
   * "absent" and "the patient says they stopped" are different notes. */
  readonly stopped: readonly ReconciledFact[];
  /** Nobody decided this visit. Never current, and never dropped either. */
  readonly unconfirmed: readonly CarriedFact[];
}

const RECONCILIATION_OF: Record<FactOutcome, Reconciliation> = {
  confirmed: "matches",
  stopped: "stopped",
  // A patient reporting "it changed" IS the recorded value disagreeing with
  // the patient's report. Provisional mapping — flagged to the pack owners.
  changed: "conflict",
};

/**
 * The only producer of `FactReconciliation`. Total over `facts`: each one
 * lands in exactly one bucket, in the order it was carried. A decision for
 * a fact that is not carried is ignored — never a fact conjured from a key.
 */
export function reconcileCarriedFacts(
  facts: readonly CarriedFact[],
  review: FactReview,
): FactReconciliation {
  const current: ReconciledFact[] = [];
  const conflicted: ReconciledFact[] = [];
  const stopped: ReconciledFact[] = [];
  const unconfirmed: CarriedFact[] = [];

  for (const fact of facts) {
    const decision = review[fact.id];
    if (decision === undefined) {
      unconfirmed.push(fact);
      continue;
    }
    const reconciliation = RECONCILIATION_OF[decision.outcome];
    const entry: ReconciledFact = { fact, decision, reconciliation };
    if (reconciliation === "matches") {
      current.push(entry);
    } else if (reconciliation === "stopped") {
      stopped.push(entry);
    } else {
      conflicted.push(entry);
    }
  }

  return { kind: "fact-reconciliation", current, conflicted, stopped, unconfirmed };
}

/**
 * Catalogue keys are written out rather than assembled from the value, so
 * `MessageKey` checks every one of them at compile time. A composed
 * `` `carried.source.${source}` as MessageKey `` would type-check happily
 * against a key nobody had added to `tr.ts` and hand `t()` an undefined —
 * exactly the failure invariant 5 exists to prevent.
 */
const SOURCE_KEY: Record<CarriedFactSource, MessageKey> = {
  confirmed_intake_extraction: "carried.source.confirmed_intake_extraction",
  clinician_accepted_note: "carried.source.clinician_accepted_note",
  confirmed_imported_record: "carried.source.confirmed_imported_record",
};

/**
 * The three outcomes in the order the copy reads them — the screen's chip
 * row and any future surface walk this, so the order is declared once.
 */
export const FACT_OUTCOMES: readonly FactOutcome[] = ["confirmed", "changed", "stopped"];

/**
 * INT-256 makes the three lookups KIND-AWARE, because the medication copy is
 * not reusable as allergy copy: a patient does not "stop" an allergy, and a
 * note line reading "hasta bıraktığını söyledi" against a penicillin allergy
 * would be a false clinical statement, not an awkward one. Same three
 * outcomes, same reconciliation vocabulary (04 §5), different words.
 *
 * `changed` still records disagreement without capturing a replacement, and
 * `stopped` still means "the patient says this is not so" — for an allergy
 * that reads as "I do not have that allergy". Neither line says what the
 * retraction MEANS; the clinician resolves it, exactly as for a medication.
 */
const STATE_KEY: Record<CarriedFactKind, Record<FactOutcome, MessageKey>> = {
  medication: {
    confirmed: "carried.state.confirmed",
    changed: "carried.state.changed",
    stopped: "carried.state.stopped",
  },
  allergy: {
    confirmed: "carried.state.allergy.confirmed",
    changed: "carried.state.allergy.changed",
    stopped: "carried.state.allergy.stopped",
  },
};

const ACTION_KEY: Record<CarriedFactKind, Record<FactOutcome, MessageKey>> = {
  medication: {
    confirmed: "carried.action.confirm",
    changed: "carried.action.changed",
    stopped: "carried.action.stopped",
  },
  allergy: {
    confirmed: "carried.action.allergy.confirm",
    changed: "carried.action.allergy.changed",
    stopped: "carried.action.allergy.stopped",
  },
};

type MarkerByRole = Record<FactAsserter["role"], MessageKey>;

const NOTE_MARKER_KEY: Record<CarriedFactKind, Record<FactOutcome, MarkerByRole>> = {
  medication: {
    confirmed: {
      patient: "note.fact.confirmed.patient",
      clinician: "note.fact.confirmed.clinician",
    },
    changed: {
      patient: "note.fact.changed.patient",
      clinician: "note.fact.changed.clinician",
    },
    stopped: {
      patient: "note.fact.stopped.patient",
      clinician: "note.fact.stopped.clinician",
    },
  },
  allergy: {
    confirmed: {
      patient: "note.fact.allergy.confirmed.patient",
      clinician: "note.fact.allergy.confirmed.clinician",
    },
    changed: {
      patient: "note.fact.allergy.changed.patient",
      clinician: "note.fact.allergy.changed.clinician",
    },
    stopped: {
      patient: "note.fact.allergy.stopped.patient",
      clinician: "note.fact.allergy.stopped.clinician",
    },
  },
};

/** Patient-facing "where from" copy for one provenance (files/09 §3). */
export function factSourceKey(source: CarriedFactSource): MessageKey {
  return SOURCE_KEY[source];
}

/** The ledger's state chip. Undecided has its OWN copy — the screen never
 * renders silence as a no, and it reads the same for both kinds. */
export function factStateKey(
  kind: CarriedFactKind,
  decision: FactDecision | undefined,
): MessageKey {
  return decision === undefined ? "carried.state.unconfirmed" : STATE_KEY[kind][decision.outcome];
}

/** The label on one answer chip, in the words that kind of fact takes. */
export function factActionKey(kind: CarriedFactKind, outcome: FactOutcome): MessageKey {
  return ACTION_KEY[kind][outcome];
}

/** The note's marker for one resolved fact — who said it, in which role. */
export function factNoteMarkerKey(entry: ReconciledFact): MessageKey {
  return NOTE_MARKER_KEY[entry.fact.kind][entry.decision.outcome][entry.decision.by.role];
}

/**
 * Long-form date for the note and the ledger. The month is a word, so the
 * line is unambiguous in both catalogues; `formatVisitDate` is not reused
 * because it omits the year, and a carried fact is only meaningful with one.
 */
export function formatFactDate(iso: string): string {
  const locale = getLocale();
  return new Intl.DateTimeFormat(locale === "tr" ? "tr-TR" : "en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(new Date(`${iso.slice(0, 10)}T00:00:00`));
}

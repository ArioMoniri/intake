/**
 * INT-282 — the base layer taken from the owner's HBYS intake schema.
 *
 * `docs/sources/hbys_intake_schema.md` is a Turkish hospital information
 * system's own intake field set, supplied by the repository owner and
 * committed verbatim (a test pins its sha256). It has 103 fields. This file
 * is not a port of them: **the value of the source is the split, not the
 * volume.** A field lands here only if a PATIENT can answer it, and the
 * fields only a clinician or a lab can supply are asserted ABSENT from every
 * pack in `baseLayer.test.ts` — respiratory rate, pulse, pulse rhythm, both
 * blood pressures, the lab blood group, fall risk, the examination and
 * treatment notes, and the two clinician narratives (`Öykü`, `Özgeçmiş
 * Notu`). Those are not "not yet done"; they are refused.
 *
 * Composed, never copied. `packForVisit` puts this block onto every
 * department pack exactly as it puts INT-256's history block there — once,
 * after it, before the free note — so the wording is authored in one place
 * and every branch inherits the same words, the way 03 §6 resolves
 * `base.intake` under `specialty.*`.
 *
 * WHAT THIS FILE DOES NOT DO, stated once for all of it. No option list is
 * ordered by severity. No answer grades anything, is read to produce another
 * answer, or carries a threshold, a cut-off or a clinical meaning. The
 * schema's option lists are a VENDOR VOCABULARY, not a validated
 * instrument, and nothing here claims otherwise — the pain score in
 * particular is the vendor's `4229_LS` field and carries no anchor text,
 * because authoring the anchors of a self-report scale is authoring
 * instrument semantics and that belongs to the physician of record
 * (INT-043 → INT-044..051, HB-C1).
 *
 * The vendor field ids stay in the source file rather than in these
 * objects: they are what a CONNECTOR writes to (INT-163), and putting an
 * HBYS id on a mobile question would make the app look like it targets one
 * hospital's schema. Each block below names its rows in a comment instead.
 */
import { getLocale, t, type MessageKey } from "../i18n";
import { formatQuantity } from "../health/format";
import type { DeferralId, IntakeQuestion } from "./questions";

/**
 * 02 §33's family-history deferral, spelled as the literal rather than
 * imported from `./questions`: `questions.ts` imports the arrays below, so a
 * value import back would be a runtime cycle. The type still checks it.
 */
const FAMILY_HISTORY: DeferralId = "family_history";

/** Every question here is Detaylı-only — see `baseLayerForProfile`. */
const DETAYLI = ["detayli"] as const;

// ---- Sosyal · the schema's `Sosyal` section -------------------------------
// Rows 361_LS (sigara, five states), 363_LS (alkol), 476_LS (madde), and
// 449_TC (meslek) from the `Kişisel` section. 04 §5 `family_social` already
// models smoking, alcohol and occupation as its own fields, so the note
// vocabulary is inherited, not invented.

const smoking: IntakeQuestion = {
  id: "smoking",
  kind: "single",
  // INT-286: closed. The scripted question names the list — "hangisi en iyi
  // anlatıyor" — so an open form would need new scripted text, and rewriting a
  // scripted question is a pack change under invariant 10, not a delivery one.
  ask: "closed",
  section: "pmh_fh_sh",
  noteSection: "family_social",
  modes: DETAYLI,
  titleKey: "intake.q.smoking",
  lineLabelKey: "intake.note.smoking",
  // The schema's five states, in its own order. "Belirtilmedi" is the
  // vendor's word for an unfilled field; asked of a person it is a DECLINE,
  // so it is worded as one.
  options: [
    { id: "never", labelKey: "intake.opt.smokingNever" },
    { id: "former", labelKey: "intake.opt.smokingFormer" },
    { id: "daily", labelKey: "intake.opt.smokingDaily" },
    { id: "occasional", labelKey: "intake.opt.smokingOccasional" },
    { id: "not_stated", labelKey: "intake.opt.notStated" },
  ],
};

const smokingQuitWhen: IntakeQuestion = {
  id: "smoking_quit_when",
  kind: "single",
  ask: "open",
  section: "pmh_fh_sh",
  noteSection: "family_social",
  modes: DETAYLI,
  titleKey: "intake.q.smokingQuitWhen",
  lineLabelKey: "intake.note.smokingQuitWhen",
  // Structurally obvious: they said they stopped, so this asks when. It is
  // asked of ex-smokers and of nobody else — the same answer-dependence the
  // department packs use, one section over.
  askIf: { questionId: "smoking", includesAny: ["former"] },
  options: [
    { id: "this_year", labelKey: "intake.opt.quitThisYear" },
    { id: "few_years", labelKey: "intake.opt.quitFewYears" },
    { id: "long_ago", labelKey: "intake.opt.quitLongAgo" },
    { id: "dont_remember", labelKey: "intake.opt.dontRemember" },
  ],
};

const alcohol: IntakeQuestion = {
  id: "alcohol",
  kind: "single",
  ask: "open",
  section: "pmh_fh_sh",
  noteSection: "family_social",
  modes: DETAYLI,
  titleKey: "intake.q.alcohol",
  lineLabelKey: "intake.note.alcohol",
  options: [
    { id: "no", labelKey: "intake.opt.no" },
    { id: "yes", labelKey: "intake.opt.yes" },
    { id: "not_stated", labelKey: "intake.opt.notStated" },
  ],
};

const substance: IntakeQuestion = {
  id: "substance",
  kind: "single",
  // INT-286: closed, and the type would refuse anything else. files/13 §13
  // puts substance use in `text_first` so the answer does not travel on the
  // voice channel; an open ask makes speaking the primary act.
  ask: "closed",
  section: "pmh_fh_sh",
  noteSection: "family_social",
  modes: DETAYLI,
  // files/13 §13 names substance use `text_first` by name. Nothing here
  // decides that classification; it applies it.
  delivery: "text_first",
  titleKey: "intake.q.substance",
  lineLabelKey: "intake.note.substance",
  options: [
    { id: "no", labelKey: "intake.opt.no" },
    { id: "yes", labelKey: "intake.opt.yes" },
    { id: "not_stated", labelKey: "intake.opt.notStated" },
  ],
};

const occupation: IntakeQuestion = {
  id: "occupation",
  kind: "text",
  section: "pmh_fh_sh",
  noteSection: "family_social",
  modes: DETAYLI,
  titleKey: "intake.q.occupation",
  hintKey: "intake.q.occupation.hint",
  lineLabelKey: "intake.note.occupation",
};

const disability: IntakeQuestion = {
  id: "disability",
  kind: "single",
  // INT-286: closed. Row 1352_LS is an administrative register the patient is
  // placed in, not a narrative answer, and its seven states have no words
  // outside the list to map onto.
  ask: "closed",
  section: "pmh_fh_sh",
  noteSection: "family_social",
  modes: DETAYLI,
  titleKey: "intake.q.disability",
  lineLabelKey: "intake.note.disability",
  // Row 1352_LS's seven states. The list describes a situation the patient
  // reports; it grades nothing and no answer changes any other question.
  options: [
    { id: "none", labelKey: "intake.opt.disabilityNone" },
    { id: "physical", labelKey: "intake.opt.disabilityPhysical" },
    { id: "intellectual", labelKey: "intake.opt.disabilityIntellectual" },
    { id: "vision", labelKey: "intake.opt.disabilityVision" },
    { id: "hearing", labelKey: "intake.opt.disabilityHearing" },
    { id: "other", labelKey: "intake.opt.other" },
    { id: "not_stated", labelKey: "intake.opt.notStated" },
  ],
};

// ---- Geçmiş ve Kan · rows 1351_LS/1351_TC, 8997_LS, 324_CC ---------------
// `spnbloodgroup` (Kan Grubu (Lab), `readonly: true` in the source) is the
// deliberate omission: a lab result is not something a patient supplies, and
// the DECLARED group is a different datum that must never be read as it.

const injuryHistory: IntakeQuestion = {
  id: "injury_history",
  kind: "single",
  ask: "open",
  section: "pmh_fh_sh",
  noteSection: "pmh",
  modes: DETAYLI,
  titleKey: "intake.q.injuryHistory",
  lineLabelKey: "intake.note.injuryHistory",
  options: [
    { id: "yes", labelKey: "intake.opt.yes" },
    { id: "no", labelKey: "intake.opt.no" },
    { id: "not_sure", labelKey: "intake.opt.notSure" },
  ],
};

const injuryDetail: IntakeQuestion = {
  id: "injury_detail",
  kind: "text",
  section: "pmh_fh_sh",
  noteSection: "pmh",
  modes: DETAYLI,
  titleKey: "intake.q.injuryDetail",
  hintKey: "intake.q.injuryDetail.hint",
  lineLabelKey: "intake.note.injuryDetail",
  askIf: { questionId: "injury_history", includesAny: ["yes"] },
};

const bloodGroup: IntakeQuestion = {
  id: "blood_group",
  kind: "single",
  ask: "open",
  section: "pmh_fh_sh",
  noteSection: "pmh",
  modes: DETAYLI,
  titleKey: "intake.q.bloodGroup",
  hintKey: "intake.q.bloodGroup.hint",
  lineLabelKey: "intake.note.bloodGroup",
  // The schema's eight groups plus "Bilinmiyor". The zero group is spelled
  // `Sıfır` and not `0`: invariant 22 expands a digit to Turkish
  // orthography rather than letting a numeral into a string that a voice
  // profile could one day read.
  options: [
    { id: "ab_pos", labelKey: "intake.opt.bloodAbPos" },
    { id: "ab_neg", labelKey: "intake.opt.bloodAbNeg" },
    { id: "a_pos", labelKey: "intake.opt.bloodAPos" },
    { id: "a_neg", labelKey: "intake.opt.bloodANeg" },
    { id: "b_pos", labelKey: "intake.opt.bloodBPos" },
    { id: "b_neg", labelKey: "intake.opt.bloodBNeg" },
    { id: "o_pos", labelKey: "intake.opt.bloodOPos" },
    { id: "o_neg", labelKey: "intake.opt.bloodONeg" },
    { id: "unknown", labelKey: "intake.opt.bloodUnknown" },
  ],
};

const transfusion: IntakeQuestion = {
  id: "transfusion",
  kind: "single",
  ask: "open",
  section: "pmh_fh_sh",
  noteSection: "pmh",
  modes: DETAYLI,
  titleKey: "intake.q.transfusion",
  lineLabelKey: "intake.note.transfusion",
  // The source offers Evet/Hayır only; "Emin değilim" is added because a
  // person may genuinely not know, and a forced yes/no would manufacture an
  // answer. It maps to an unset field, never to "Hayır" (INT-163).
  options: [
    { id: "yes", labelKey: "intake.opt.yes" },
    { id: "no", labelKey: "intake.opt.no" },
    { id: "not_sure", labelKey: "intake.opt.notSure" },
  ],
};

// ---- Soygeçmiş · rows td382…td401, per relative --------------------------
// The source keeps FOUR relatives apart (anne · baba · erkek kardeş · kız
// kardeş) and asks the SAME five conditions of each. INT-256 had one
// free-text field; this is the schema's shape instead, and it is the shape
// that lets the note say whose condition it is.

const FAMILY_CONDITIONS = [
  { id: "ht", labelKey: "intake.opt.fhHt" },
  { id: "cardiac", labelKey: "intake.opt.fhCardiac" },
  { id: "cancer", labelKey: "intake.opt.fhCancer" },
  { id: "diabetes", labelKey: "intake.opt.fhDiabetes" },
  { id: "blood", labelKey: "intake.opt.fhBlood" },
  { id: "other", labelKey: "intake.opt.other" },
  { id: "not_sure", labelKey: "intake.opt.fhNotSure" },
] as const satisfies readonly { id: string; labelKey: MessageKey }[];

function familyConditions(
  relative: "mother" | "father" | "brother" | "sister",
  titleKey: MessageKey,
  lineLabelKey: MessageKey,
): IntakeQuestion {
  return {
    id: `fh_${relative}_conditions`,
    kind: "chips",
    // INT-286: closed. A named-condition checklist, per relative. files/13 §4
    // quotes Bent et al., Ann Intern Med 2006 (randomised, N = 214): a
    // checklist elicited 238 findings in 77 % of patients, an open question 11
    // in 14 %, p < 0.001. Opening a checklist is a measured loss of yield.
    ask: "closed",
    section: "pmh_fh_sh",
    noteSection: "family_social",
    modes: DETAYLI,
    // Family history is a disclosure about people who are not in the room,
    // so it defers with the rest of the block (02 §33, INT-256).
    deferrableAs: FAMILY_HISTORY,
    titleKey,
    hintKey: "intake.q.complaint.hint",
    lineLabelKey,
    askIf: { questionId: "fh_who", includesAny: [relative] },
    options: [...FAMILY_CONDITIONS],
  };
}

// ---- Ağrı ve Fiziksel · rows 633_LS, 4229_LS, 51_TC, 209_TC -------------
// Every step in this block is `text_only`, which is files/13 §13's own
// class and files/13 §9.5's build-time guarantee that such a step has no
// clip. Invariant 22's "no numeral reaches any TTS model" therefore holds
// structurally: `spokenPack` cannot return one of these.

const painPresent: IntakeQuestion = {
  id: "pain_present",
  kind: "single",
  ask: "open",
  modes: DETAYLI,
  titleKey: "intake.q.painPresent",
  lineLabelKey: "intake.note.painPresent",
  options: [
    { id: "yes", labelKey: "intake.opt.yes" },
    { id: "no", labelKey: "intake.opt.no" },
  ],
};

/** `Sıfır … On` — the label is the word, the numeral is the inline render. */
const PAIN_SCORE_LABELS: readonly MessageKey[] = [
  "intake.opt.numZero",
  "intake.opt.numOne",
  "intake.opt.numTwo",
  "intake.opt.numThree",
  "intake.opt.numFour",
  "intake.opt.numFive",
  "intake.opt.numSix",
  "intake.opt.numSeven",
  "intake.opt.numEight",
  "intake.opt.numNine",
  "intake.opt.numTen",
];

const painScore: IntakeQuestion = {
  id: "pain_score",
  kind: "single",
  // INT-286: closed, and the type would refuse anything else. files/13 §13
  // makes this `text_only` and invariant 22 forbids free numeric entry on the
  // clinical path, so the closed set of authored values IS the control.
  ask: "closed",
  modes: DETAYLI,
  delivery: "text_only",
  titleKey: "intake.q.painScore",
  lineLabelKey: "intake.note.painScore",
  askIf: { questionId: "pain_present", includesAny: ["yes"] },
  // A CLOSED set of authored values, which is what invariant 22 means by a
  // guarded control: there is no keyboard, no parser and no free numeral.
  // No anchor wording is authored for either end of the scale — see the
  // file header.
  options: PAIN_SCORE_LABELS.map((labelKey, value) => ({
    id: String(value),
    labelKey,
    inline: String(value),
  })),
};

const height: IntakeQuestion = {
  id: "height",
  kind: "measure",
  modes: DETAYLI,
  delivery: "text_only",
  titleKey: "intake.q.height",
  hintKey: "intake.q.measure.hint",
  lineLabelKey: "intake.note.height",
  // Bounds are CONTROL bounds. Nothing reads them, nothing outside them is
  // "abnormal", and no threshold is expressed by them.
  measure: { unitKey: "intake.unit.cm", min: 100, max: 220, start: 160, step: 1, coarseStep: 10 },
};

const weight: IntakeQuestion = {
  id: "weight",
  kind: "measure",
  modes: DETAYLI,
  delivery: "text_only",
  titleKey: "intake.q.weight",
  hintKey: "intake.q.measure.hint",
  lineLabelKey: "intake.note.weight",
  // The source's `Kilo Birimi` offers kg or gr; gr is a neonatal unit and
  // this is an adult self-report surface, so the unit is fixed at kg and the
  // connector writes that constant rather than asking for it (INT-163).
  measure: { unitKey: "intake.unit.kg", min: 20, max: 250, start: 60, step: 1, coarseStep: 10 },
};

/**
 * The patient-answerable base layer, in the order it is asked: social,
 * then the past/blood rows, then family history per relative.
 */
export const baseLayerQuestions: readonly IntakeQuestion[] = [
  smoking,
  smokingQuitWhen,
  alcohol,
  substance,
  occupation,
  disability,
  injuryHistory,
  injuryDetail,
  bloodGroup,
  transfusion,
  familyConditions("mother", "intake.q.fhMotherConditions", "intake.note.fhMother"),
  familyConditions("father", "intake.q.fhFatherConditions", "intake.note.fhFather"),
  familyConditions("brother", "intake.q.fhBrotherConditions", "intake.note.fhBrother"),
  familyConditions("sister", "intake.q.fhSisterConditions", "intake.note.fhSister"),
];

/**
 * The measured block. Separate from the list above because these answers are
 * not history: they render into their own note section, and files/04 §5's
 * `PreVisitNote` has no field for anthropometry at all — an honest gap
 * recorded in docs/evidence/INT-282.md rather than a note section invented
 * here to fill it.
 */
export const measurementQuestions: readonly IntakeQuestion[] = [
  painPresent,
  painScore,
  height,
  weight,
];

/** Question id → its unit key, for any surface that has to render a value. */
export const MEASURE_UNIT_OF: Readonly<Record<string, MessageKey>> = Object.fromEntries(
  measurementQuestions
    .filter((q) => q.measure !== undefined)
    .map((q) => [q.id, q.measure!.unitKey]),
);

/**
 * One measured answer as the clinician reads it.
 *
 * - a `measure` prints through `formatQuantity`, so `useGrouping:false` and
 *   the non-breaking number+unit atom of invariant 22 are the SAME code
 *   path the device-health block already uses;
 * - a scored answer prints its `inline` numeral, because the number is what
 *   a clinician wants on the page while the word is what a voice would say;
 * - anything else prints its own option label.
 */
export function measurementLine(question: IntakeQuestion, values: readonly string[]): string {
  if (question.measure !== undefined) {
    const value = Number(values[0]);
    if (!Number.isFinite(value)) {
      return values.join(" ");
    }
    return formatQuantity(value, t(question.measure.unitKey), getLocale());
  }
  return values
    .map((value) => {
      const option = question.options?.find((o) => o.id === value);
      if (option === undefined) {
        return value;
      }
      return option.inline ?? t(option.labelKey);
    })
    .join(", ");
}

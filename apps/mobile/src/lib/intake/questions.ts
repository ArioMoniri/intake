/**
 * Typed-intake question packs (INT-179/194/198). One question per screen
 * (Alan pacing), chips grid for multi-select steps (CVS Health pattern) —
 * see docs/design/mobile-ui.md §refs.
 *
 * Department packs make the intake branch-aware: ten branches (Kardiyoloji/
 * İç Hastalıkları, Nöroloji, KBB, Ortopedi, Dermatoloji, Göğüs, Kadın
 * Hastalıkları ve Doğum, Üroloji, Göz, Gastroenteroloji) each get their own
 * OLDCARTS-style anamnesis dimensions on top of the shared core
 * (complaint → duration → … → severity → free note). These are UI FIXTURES
 * carrying neutral anamnesis dimensions only — no red-flag logic, no
 * thresholds, no triage: the real compiled packs (packages/protocols,
 * INT-096) replace this module wholesale, and severity words replace any
 * numeric scale on the clinical path (invariant 22).
 *
 * Ordering contract: every pack lists its dimensions in the canonical
 * anamnesis order (onset → location/side → character → radiation →
 * triggers → timing/course → associated → severity), and `allQuestions`
 * repeats that order globally, so the note builder's HPI lines always
 * follow the interview (questions.test.ts pins this).
 *
 * Adaptive flow (INT-236, deepened in INT-239): `askIf` MIRRORS the DSL's
 * `ask_if` gate on packages/protocols/src/protocols/dsl.py `Slot` — a
 * serializable DATA predicate, never a function — so the compiled packs
 * slot into the same flow machinery without any UX change.
 *
 * THE ONE RULE FOR ADDING A GATE HERE: a gated question may only ask for a
 * further detail of something the patient has ALREADY named — the
 * character of the pain they reported, which side the spreading they
 * reported goes to, what happens when they swallow given they placed the
 * pain in the throat. No gate in this file encodes danger, severity, a
 * threshold or a differential; deciding that a question must be asked
 * *because a symptom might be dangerous* is clinical judgment and belongs
 * to the sourced chain — the L0 scaffolds and the protocol compiler
 * (INT-057/INT-041), reviewed by a CODEOWNER against a guideline snapshot.
 * These packs ASK; they never triage (invariant 1). What was deliberately
 * NOT invented here is listed for pack owners in docs/evidence/INT-239.md.
 *
 * Gates chain: a level-two follow-up is gated on a question that is itself
 * gated (complaint ⊇ pain → radiation → radiation_side). The compiler's
 * stratified-acyclicity rule (files/13 §9.5) is mirrored at the dev tier by
 * questions.test.ts: a gate may only reference a question EARLIER in the
 * same pack.
 *
 * `applicableQuestions` / `nextApplicableQuestion` / `missingQuestions` are
 * the shared flow layer: the typed StepFlow, the spoken dialogue engine
 * (lib/dialogue/stream.ts) and the realtime section panel all gate through
 * them, so the flow length is decided by the answers in every surface.
 *
 * INT-256 adds the UNIVERSAL history block — 04 §1 rows 5 and 6,
 * `meds_allergies` and `pmh_fh_sh`: allergies, medications, past medical
 * history, family history. It is COMPOSED onto a department pack by
 * `packForVisit`, never copied into the ten arrays, because that is what the
 * protocol registry itself does (03 §6: base → cluster → specialty), so the
 * base copy is authored once and every branch inherits the same wording.
 *
 * These are questions, not judgements. Nothing in the block grades a
 * severity, computes an interaction, infers anything from an answer or
 * carries a threshold; the answers are recorded and rendered and nothing is
 * concluded from them. The guideline-grounded, department-specific content
 * is INT-043 → INT-044..051 and is awaiting a physician (HB-C1). What was
 * deliberately NOT authored is listed in docs/evidence/INT-256.md.
 */
import type { MessageKey } from "../i18n";

export interface IntakeOption {
  id: string;
  labelKey: MessageKey;
}

/**
 * Gate predicate, mirroring dsl.py `Slot.ask_if` in shape discipline:
 * pure data (JSON round-trips), evaluated against committed answers. Met
 * when the referenced question's answer includes ANY of the listed option
 * ids; an unanswered gating question leaves the gate unmet, so gated
 * questions reveal themselves as answers land.
 */
export interface AskIf {
  questionId: string;
  includesAny: readonly string[];
}

/**
 * The 04 §1 protocol sections a question may belong to, spelled exactly as
 * `packages/protocols/base/intake.yaml` spells them. Absent means the HPI
 * dimensions the department packs already carry (04 §1 row 3).
 */
export type ProtocolSectionId = "meds_allergies" | "pmh_fh_sh";

/**
 * The note section a question's answer renders into — the `PreVisitNote`
 * field names of files/04 §5, which are also `NOTE_SECTION_IDS` in
 * packages/clinical-schemas and the ids `mappers/document.py` keys on. Two
 * vocabularies, deliberately: 04 §1 groups QUESTIONS into protocol sections,
 * 04 §5 groups ANSWERS into note sections, and `meds_allergies` splits in
 * two on the way across.
 */
export type NoteSectionId = "pmh" | "medications" | "allergies" | "family_social";

/** Which 04 §1 section owns the questions that fill each 04 §5 note section. */
export const PROTOCOL_SECTION_OF: Record<NoteSectionId, ProtocolSectionId> = {
  medications: "meds_allergies",
  allergies: "meds_allergies",
  pmh: "pmh_fh_sh",
  family_social: "pmh_fh_sh",
};

/** 02 §2: Hızlı (pre-hospital, default) vs Detaylı (in-hospital). */
export type IntakeMode = "hizli" | "detayli";

/**
 * A unit the 02 §33 environment self-check may push to a home session.
 * `wellbeing` is INT-236's; `family_history` is INT-256's second consumer —
 * family history is a disclosure about people who are not in the room, and
 * 02 §33's rule is that a sensitive section is deferred, never asked more
 * quietly.
 */
export type DeferralId = "wellbeing" | "family_history";

export const FAMILY_HISTORY_DEFERRAL = "family_history" satisfies DeferralId;

/**
 * The session-constant inputs of 02 §2 and 02 §33 — the DSL's own guard
 * whitelist calls the first of them `mode()` (files/13 §9.5). Neither
 * changes within a turn, so they select the PROFILE (which questions the
 * pack contains) rather than gating per answer: `askIf` stays purely
 * answer-driven, exactly as `dsl.py Slot.ask_if` is.
 */
export interface IntakeProfile {
  mode: IntakeMode;
  /** Deferral ids recorded by the environment self-check (02 §33). */
  deferred?: readonly string[];
}

export interface IntakeQuestion {
  id: string;
  kind: "chips" | "single" | "text";
  titleKey: MessageKey;
  hintKey?: MessageKey;
  /** Short label used for this answer's line in the HPI section. */
  hpiLabelKey?: MessageKey;
  /**
   * Short label for this answer's line in its own history section — the
   * `hpiLabelKey` of a question that is not part of the HPI. Exactly one of
   * the two is set (history.test.ts pins it), because the label names the
   * section the line lands in and a question lands in one section.
   */
  lineLabelKey?: MessageKey;
  options?: readonly IntakeOption[];
  /** Ask only when met (INT-236); absent means always applicable. */
  askIf?: AskIf;
  /** 04 §1 section owning this question; absent = the HPI dimensions. */
  section?: ProtocolSectionId;
  /** 04 §5 note section its answer renders into; set with `section`. */
  noteSection?: NoteSectionId;
  /** Modes this question is asked in; absent = every mode. */
  modes?: readonly IntakeMode[];
  /** Deferral unit this question belongs to (02 §33); absent = never deferred. */
  deferrableAs?: DeferralId;
}

/** The slice of an answer the gate evaluator needs (note.ts Answer fits). */
export interface AnsweredValues {
  questionId: string;
  values: readonly string[];
}

// ---- shared core -----------------------------------------------------------

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

const onset: IntakeQuestion = {
  id: "onset",
  kind: "single",
  titleKey: "intake.q.onset",
  hpiLabelKey: "intake.hpi.onset",
  options: [
    { id: "sudden", labelKey: "intake.opt.sudden" },
    { id: "gradual", labelKey: "intake.opt.gradual" },
  ],
};

const side: IntakeQuestion = {
  id: "side",
  kind: "single",
  titleKey: "intake.q.side",
  hpiLabelKey: "intake.hpi.side",
  options: [
    { id: "right", labelKey: "intake.opt.right" },
    { id: "left", labelKey: "intake.opt.left" },
    { id: "both", labelKey: "intake.opt.both" },
  ],
};

const severity: IntakeQuestion = {
  id: "severity",
  kind: "single",
  titleKey: "intake.q.severity",
  hpiLabelKey: "intake.hpi.severity",
  options: [
    { id: "mild", labelKey: "intake.opt.mild" },
    { id: "moderate", labelKey: "intake.opt.moderate" },
    { id: "severe", labelKey: "intake.opt.severe" },
  ],
};

const timeOfDay: IntakeQuestion = {
  id: "time_of_day",
  kind: "single",
  titleKey: "intake.q.timeOfDay",
  hpiLabelKey: "intake.hpi.timing",
  options: [
    { id: "night", labelKey: "intake.opt.atNight" },
    { id: "morning", labelKey: "intake.opt.inMorning" },
    { id: "all_day", labelKey: "intake.opt.allDay" },
  ],
};

const extra: IntakeQuestion = {
  id: "extra",
  kind: "text",
  titleKey: "intake.q.extra",
  hintKey: "intake.q.extra.hint",
};

// ---- shared answer-gated dimensions (INT-239) -------------------------------
// Two packs each ask these, so they live once: the breathing pair belongs to
// whichever pack the patient reached with "nefes darlığı", the fever timing
// to whichever pack they reached with "ateş".

const breathTiming: IntakeQuestion = {
  id: "breath_timing",
  kind: "single",
  titleKey: "intake.q.breathTiming",
  hpiLabelKey: "intake.hpi.breathTiming",
  // The patient named the shortness of breath; this asks when it happens.
  askIf: { questionId: "complaint", includesAny: ["dyspnoea"] },
  options: [
    { id: "exertion", labelKey: "intake.opt.exertion" },
    { id: "rest", labelKey: "intake.opt.rest" },
    { id: "lying", labelKey: "intake.opt.whenLying" },
    { id: "no_pattern", labelKey: "intake.opt.noPattern" },
  ],
};

const breathLying: IntakeQuestion = {
  id: "breath_lying",
  kind: "single",
  titleKey: "intake.q.breathLying",
  hpiLabelKey: "intake.hpi.breathLying",
  // Level two: they placed it in lying down, so ask what they do about it.
  askIf: { questionId: "breath_timing", includesAny: ["lying"] },
  options: [
    { id: "pillow", labelKey: "intake.opt.raisePillow" },
    { id: "sit_up", labelKey: "intake.opt.sitUp" },
    { id: "nothing", labelKey: "intake.opt.nothingSpecial" },
    { id: "not_sure", labelKey: "intake.opt.notSure" },
  ],
};

const feverPattern: IntakeQuestion = {
  id: "fever_pattern",
  kind: "single",
  titleKey: "intake.q.feverPattern",
  hpiLabelKey: "intake.hpi.feverPattern",
  // The patient named the fever; this asks when it rises. No number is
  // asked and none is offered (invariant 22 — words, never a reading).
  askIf: { questionId: "complaint", includesAny: ["fever"] },
  options: [
    { id: "night", labelKey: "intake.opt.atNight" },
    { id: "morning", labelKey: "intake.opt.inMorning" },
    { id: "all_day", labelKey: "intake.opt.allDay" },
    { id: "varies", labelKey: "intake.opt.varies" },
  ],
};

// ---- Kardiyoloji / İç Hastalıkları ----------------------------------------

const painCharacter: IntakeQuestion = {
  id: "pain_character",
  kind: "chips",
  titleKey: "intake.q.character",
  hintKey: "intake.q.complaint.hint",
  hpiLabelKey: "intake.hpi.character",
  // Structurally obvious (INT-236): the question asks how the PAIN feels.
  askIf: { questionId: "complaint", includesAny: ["pain"] },
  options: [
    { id: "pressure", labelKey: "intake.opt.pressure" },
    { id: "stabbing", labelKey: "intake.opt.stabbing" },
    { id: "burning", labelKey: "intake.opt.burning" },
    { id: "dull", labelKey: "intake.opt.dull" },
  ],
};

const radiation: IntakeQuestion = {
  id: "radiation",
  kind: "chips",
  titleKey: "intake.q.radiation",
  hintKey: "intake.q.complaint.hint",
  hpiLabelKey: "intake.hpi.radiation",
  // Structurally obvious (INT-236): where the PAIN spreads.
  askIf: { questionId: "complaint", includesAny: ["pain"] },
  options: [
    { id: "arm", labelKey: "intake.opt.radArm" },
    { id: "jaw_neck", labelKey: "intake.opt.radJawNeck" },
    { id: "back", labelKey: "intake.opt.radBack" },
    { id: "no_radiation", labelKey: "intake.opt.radNone" },
  ],
};

const radiationSide: IntakeQuestion = {
  id: "radiation_side",
  kind: "single",
  titleKey: "intake.q.radiationSide",
  hpiLabelKey: "intake.hpi.radiationSide",
  // Level two: they said it spreads somewhere, so ask which side.
  askIf: { questionId: "radiation", includesAny: ["arm", "jaw_neck", "back"] },
  options: [
    { id: "right", labelKey: "intake.opt.right" },
    { id: "left", labelKey: "intake.opt.left" },
    { id: "both", labelKey: "intake.opt.both" },
  ],
};

const cardioTrigger: IntakeQuestion = {
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
};

const cardioAssoc: IntakeQuestion = {
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
    { id: "dizziness", labelKey: "intake.opt.dizziness" },
    { id: "ankle_swelling", labelKey: "intake.opt.ankleSwelling" },
    { id: "none", labelKey: "intake.opt.none" },
  ],
};

const cardioPalpitation: IntakeQuestion = {
  id: "cardio_palpitation",
  kind: "single",
  titleKey: "intake.q.palpitation",
  hpiLabelKey: "intake.hpi.palpitation",
  // They ticked the palpitations chip; this asks them to describe it.
  askIf: { questionId: "associated", includesAny: ["palpitations"] },
  options: [
    { id: "fast_regular", labelKey: "intake.opt.fastRegular" },
    { id: "irregular", labelKey: "intake.opt.irregularBeat" },
    { id: "skipped", labelKey: "intake.opt.skippedBeats" },
    { id: "not_sure", labelKey: "intake.opt.notSure" },
  ],
};

const cardioInternal: IntakeQuestion[] = [
  complaint,
  duration,
  onset,
  painCharacter,
  radiation,
  radiationSide,
  breathTiming,
  breathLying,
  cardioTrigger,
  cardioAssoc,
  cardioPalpitation,
  severity,
  extra,
];

// ---- Nöroloji ---------------------------------------------------------------

const neuroHeadSide: IntakeQuestion = {
  id: "neuro_head_side",
  kind: "single",
  titleKey: "intake.q.headWhere",
  hpiLabelKey: "intake.hpi.region",
  // They named the headache; this asks where on the head it sits.
  askIf: { questionId: "complaint", includesAny: ["headache"] },
  options: [
    { id: "one_side", labelKey: "intake.opt.oneSide" },
    { id: "both_sides", labelKey: "intake.opt.bothSides" },
    { id: "forehead_eye", labelKey: "intake.opt.foreheadEye" },
    { id: "from_neck", labelKey: "intake.opt.fromNeck" },
  ],
};

const neuroHeadSame: IntakeQuestion = {
  id: "neuro_head_same",
  kind: "single",
  titleKey: "intake.q.headSameSide",
  hpiLabelKey: "intake.hpi.headSameSide",
  // Level two: they placed it on one side, so ask whether it stays there.
  askIf: { questionId: "neuro_head_side", includesAny: ["one_side"] },
  options: [
    { id: "always_same", labelKey: "intake.opt.alwaysSameSide" },
    { id: "changes", labelKey: "intake.opt.sideChanges" },
    { id: "not_sure", labelKey: "intake.opt.notSure" },
  ],
};

const neuroCharacter: IntakeQuestion = {
  id: "neuro_character",
  kind: "chips",
  titleKey: "intake.q.character",
  hintKey: "intake.q.complaint.hint",
  hpiLabelKey: "intake.hpi.character",
  // The question literally asks how the PAIN feels, so it needs a pain or
  // a headache to describe (the same reading as painCharacter).
  askIf: { questionId: "complaint", includesAny: ["pain", "headache"] },
  options: [
    { id: "throbbing", labelKey: "intake.opt.throbbing" },
    { id: "pressure", labelKey: "intake.opt.pressure" },
    { id: "stabbing", labelKey: "intake.opt.stabbing" },
    { id: "electric", labelKey: "intake.opt.electric" },
  ],
};

const neuroTrigger: IntakeQuestion = {
  id: "neuro_trigger",
  kind: "chips",
  titleKey: "intake.q.trigger",
  hintKey: "intake.q.complaint.hint",
  hpiLabelKey: "intake.hpi.trigger",
  options: [
    { id: "movement", labelKey: "intake.opt.withMovement" },
    { id: "light_noise", labelKey: "intake.opt.withLightNoise" },
    { id: "sleepless", labelKey: "intake.opt.withSleepless" },
    { id: "no_pattern", labelKey: "intake.opt.noPattern" },
  ],
};

const neuroCourse: IntakeQuestion = {
  id: "neuro_course",
  kind: "single",
  titleKey: "intake.q.course",
  hpiLabelKey: "intake.hpi.course",
  options: [
    { id: "attacks", labelKey: "intake.opt.inAttacks" },
    { id: "constant", labelKey: "intake.opt.constant" },
    { id: "varies", labelKey: "intake.opt.varies" },
  ],
};

const neuroAssoc: IntakeQuestion = {
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
    { id: "balance", labelKey: "intake.opt.balance" },
    { id: "none", labelKey: "intake.opt.none" },
  ],
};

const neuroNumbWhere: IntakeQuestion = {
  id: "neuro_numb_where",
  kind: "chips",
  titleKey: "intake.q.numbWhere",
  hintKey: "intake.q.complaint.hint",
  hpiLabelKey: "intake.hpi.numbWhere",
  // They ticked the numbness chip; this asks where they feel it.
  askIf: { questionId: "neuro_assoc", includesAny: ["numbness"] },
  options: [
    { id: "face", labelKey: "intake.opt.face" },
    { id: "arms", labelKey: "intake.opt.arms" },
    { id: "legs", labelKey: "intake.opt.legs" },
    { id: "trunk", labelKey: "intake.opt.trunk" },
    { id: "several", labelKey: "intake.opt.severalPlaces" },
  ],
};

const neuro: IntakeQuestion[] = [
  complaint,
  duration,
  onset,
  neuroHeadSide,
  neuroHeadSame,
  neuroCharacter,
  neuroTrigger,
  neuroCourse,
  neuroAssoc,
  neuroNumbWhere,
  severity,
  extra,
];

// ---- Kulak Burun Boğaz ------------------------------------------------------

const entPainWhere: IntakeQuestion = {
  id: "ent_pain_where",
  kind: "single",
  titleKey: "intake.q.painWhere",
  hpiLabelKey: "intake.hpi.region",
  // They named the pain; this asks where in the head and neck it sits.
  askIf: { questionId: "complaint", includesAny: ["pain"] },
  options: [
    { id: "ear", labelKey: "intake.opt.inEar" },
    { id: "throat", labelKey: "intake.opt.inThroat" },
    { id: "face", labelKey: "intake.opt.faceForehead" },
    { id: "jaw", labelKey: "intake.opt.inJaw" },
  ],
};

const entSwallow: IntakeQuestion = {
  id: "ent_swallow",
  kind: "single",
  titleKey: "intake.q.swallow",
  hpiLabelKey: "intake.hpi.swallow",
  // Level two: they placed the pain in the throat, so ask about swallowing.
  askIf: { questionId: "ent_pain_where", includesAny: ["throat"] },
  options: [
    { id: "pain_more", labelKey: "intake.opt.painIncreases" },
    { id: "stuck", labelKey: "intake.opt.stuckFeeling" },
    { id: "voice", labelKey: "intake.opt.voiceChange" },
    { id: "no_change", labelKey: "intake.opt.noChange" },
  ],
};

const entTrigger: IntakeQuestion = {
  id: "ent_trigger",
  kind: "chips",
  titleKey: "intake.q.trigger",
  hintKey: "intake.q.complaint.hint",
  hpiLabelKey: "intake.hpi.trigger",
  options: [
    { id: "swallow", labelKey: "intake.opt.withSwallow" },
    { id: "cold_air", labelKey: "intake.opt.withColdAir" },
    { id: "night", labelKey: "intake.opt.atNight" },
    { id: "no_pattern", labelKey: "intake.opt.noPattern" },
  ],
};

const entAssoc: IntakeQuestion = {
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
    { id: "dizziness", labelKey: "intake.opt.dizziness" },
    { id: "hoarseness", labelKey: "intake.opt.hoarseness" },
    { id: "fever", labelKey: "intake.opt.fever" },
    { id: "none", labelKey: "intake.opt.none" },
  ],
};

const entHearSide: IntakeQuestion = {
  id: "ent_hear_side",
  kind: "single",
  titleKey: "intake.q.hearSide",
  hpiLabelKey: "intake.hpi.hearSide",
  // They ticked the hearing chip; this asks which ear.
  askIf: { questionId: "ent_assoc", includesAny: ["hearing"] },
  options: [
    { id: "right", labelKey: "intake.opt.right" },
    { id: "left", labelKey: "intake.opt.left" },
    { id: "both", labelKey: "intake.opt.both" },
  ],
};

const ent: IntakeQuestion[] = [
  complaint,
  duration,
  onset,
  entPainWhere,
  entSwallow,
  side,
  entTrigger,
  entAssoc,
  entHearSide,
  severity,
  extra,
];

// ---- Ortopedi ----------------------------------------------------------------

const orthoMechanism: IntakeQuestion = {
  id: "ortho_mechanism",
  kind: "single",
  titleKey: "intake.q.mechanism",
  hpiLabelKey: "intake.hpi.mechanism",
  options: [
    { id: "fall", labelKey: "intake.opt.afterFall" },
    { id: "strain", labelKey: "intake.opt.afterStrain" },
    { id: "no_event", labelKey: "intake.opt.noEvent" },
  ],
};

const orthoFallHow: IntakeQuestion = {
  id: "ortho_fall_how",
  kind: "single",
  titleKey: "intake.q.fallHow",
  hpiLabelKey: "intake.hpi.fallHow",
  // They said it began with a fall or a blow; this asks how it happened.
  askIf: { questionId: "ortho_mechanism", includesAny: ["fall"] },
  options: [
    { id: "slipped", labelKey: "intake.opt.slipped" },
    { id: "stairs", labelKey: "intake.opt.onStairs" },
    { id: "height", labelKey: "intake.opt.fromHeight" },
    { id: "sport", labelKey: "intake.opt.duringSport" },
  ],
};

const orthoRegion: IntakeQuestion = {
  id: "ortho_region",
  kind: "chips",
  titleKey: "intake.q.region",
  hintKey: "intake.q.complaint.hint",
  hpiLabelKey: "intake.hpi.region",
  options: [
    { id: "knee", labelKey: "intake.opt.knee" },
    { id: "hip", labelKey: "intake.opt.hip" },
    { id: "shoulder", labelKey: "intake.opt.shoulder" },
    { id: "low_back", labelKey: "intake.opt.lowBack" },
    { id: "neck", labelKey: "intake.opt.neckRegion" },
    { id: "hand_wrist", labelKey: "intake.opt.handWrist" },
    { id: "foot_ankle", labelKey: "intake.opt.footAnkle" },
    { id: "other", labelKey: "intake.opt.other" },
  ],
};

const orthoSpread: IntakeQuestion = {
  id: "ortho_spread",
  kind: "single",
  titleKey: "intake.q.spineSpread",
  hpiLabelKey: "intake.hpi.spineSpread",
  // They placed it in the back or the neck; this asks whether it travels.
  askIf: { questionId: "ortho_region", includesAny: ["low_back", "neck"] },
  options: [
    { id: "arm", labelKey: "intake.opt.radArm" },
    { id: "leg", labelKey: "intake.opt.radLeg" },
    { id: "no_spread", labelKey: "intake.opt.radNone" },
  ],
};

const orthoSpreadFeel: IntakeQuestion = {
  id: "ortho_spread_feel",
  kind: "single",
  titleKey: "intake.q.spreadFeel",
  hpiLabelKey: "intake.hpi.spreadFeel",
  // Level two: it travels somewhere, so ask what that place feels like.
  askIf: { questionId: "ortho_spread", includesAny: ["arm", "leg"] },
  options: [
    { id: "tingling", labelKey: "intake.opt.tingling" },
    { id: "numb", labelKey: "intake.opt.numbFeeling" },
    { id: "both", labelKey: "intake.opt.bothOfThem" },
    { id: "none", labelKey: "intake.opt.none" },
  ],
};

const orthoTrigger: IntakeQuestion = {
  id: "ortho_trigger",
  kind: "chips",
  titleKey: "intake.q.trigger",
  hintKey: "intake.q.complaint.hint",
  hpiLabelKey: "intake.hpi.trigger",
  options: [
    { id: "movement", labelKey: "intake.opt.withMovement" },
    { id: "rest_eases", labelKey: "intake.opt.restEases" },
    { id: "morning_stiff", labelKey: "intake.opt.morningStiff" },
    { id: "night_pain", labelKey: "intake.opt.nightPain" },
  ],
};

const orthoAssoc: IntakeQuestion = {
  id: "ortho_assoc",
  kind: "chips",
  titleKey: "intake.q.associated",
  hintKey: "intake.q.complaint.hint",
  hpiLabelKey: "intake.hpi.associated",
  options: [
    { id: "swelling", labelKey: "intake.opt.swelling" },
    { id: "redness", labelKey: "intake.opt.redness" },
    { id: "limited_motion", labelKey: "intake.opt.limitedMotion" },
    { id: "numbness", labelKey: "intake.opt.numbness" },
    { id: "none", labelKey: "intake.opt.none" },
  ],
};

const ortho: IntakeQuestion[] = [
  complaint,
  duration,
  orthoMechanism,
  orthoFallHow,
  orthoRegion,
  orthoSpread,
  orthoSpreadFeel,
  side,
  painCharacter,
  orthoTrigger,
  orthoAssoc,
  severity,
  extra,
];

// ---- Dermatoloji ---------------------------------------------------------------

const dermLocation: IntakeQuestion = {
  id: "derm_location",
  kind: "chips",
  titleKey: "intake.q.skinWhere",
  hintKey: "intake.q.complaint.hint",
  hpiLabelKey: "intake.hpi.region",
  options: [
    { id: "face", labelKey: "intake.opt.face" },
    { id: "scalp", labelKey: "intake.opt.scalp" },
    { id: "trunk", labelKey: "intake.opt.trunk" },
    { id: "arms", labelKey: "intake.opt.arms" },
    { id: "legs", labelKey: "intake.opt.legs" },
    { id: "hands_feet", labelKey: "intake.opt.handsFeet" },
    { id: "widespread", labelKey: "intake.opt.widespread" },
  ],
};

const dermCharacter: IntakeQuestion = {
  id: "derm_character",
  kind: "chips",
  titleKey: "intake.q.skinLook",
  hintKey: "intake.q.complaint.hint",
  hpiLabelKey: "intake.hpi.appearance",
  options: [
    { id: "itchy", labelKey: "intake.opt.itchy" },
    { id: "painful", labelKey: "intake.opt.painful" },
    { id: "flaking", labelKey: "intake.opt.flaking" },
    { id: "blisters", labelKey: "intake.opt.blisters" },
    { id: "raised", labelKey: "intake.opt.raised" },
  ],
};

const dermItchWhen: IntakeQuestion = {
  id: "derm_itch_when",
  kind: "single",
  titleKey: "intake.q.itchWhen",
  hpiLabelKey: "intake.hpi.itchWhen",
  // They ticked the itching chip; this asks when it gets worse.
  askIf: { questionId: "derm_character", includesAny: ["itchy"] },
  options: [
    { id: "night", labelKey: "intake.opt.atNight" },
    { id: "heat", labelKey: "intake.opt.inHeat" },
    { id: "sweat", labelKey: "intake.opt.withSweat" },
    { id: "no_pattern", labelKey: "intake.opt.noPattern" },
  ],
};

const dermItchSleep: IntakeQuestion = {
  id: "derm_itch_sleep",
  kind: "single",
  titleKey: "intake.q.itchSleep",
  hpiLabelKey: "intake.hpi.itchSleep",
  // Level two: they placed the itching at night, so ask about their sleep.
  askIf: { questionId: "derm_itch_when", includesAny: ["night"] },
  options: [
    { id: "yes", labelKey: "intake.opt.yes" },
    { id: "sometimes", labelKey: "intake.opt.sometimes" },
    { id: "no", labelKey: "intake.opt.no" },
  ],
};

const dermTrigger: IntakeQuestion = {
  id: "derm_trigger",
  kind: "single",
  titleKey: "intake.q.trigger",
  hpiLabelKey: "intake.hpi.trigger",
  options: [
    { id: "sun", labelKey: "intake.opt.withSun" },
    { id: "sweat", labelKey: "intake.opt.withSweat" },
    { id: "new_product", labelKey: "intake.opt.afterProduct" },
    { id: "no_pattern", labelKey: "intake.opt.noPattern" },
  ],
};

const dermCourse: IntakeQuestion = {
  id: "derm_course",
  kind: "single",
  titleKey: "intake.q.course",
  hpiLabelKey: "intake.hpi.course",
  options: [
    { id: "spreading", labelKey: "intake.opt.spreading" },
    { id: "same", labelKey: "intake.opt.same" },
    { id: "improving", labelKey: "intake.opt.improving" },
    { id: "comes_goes", labelKey: "intake.opt.comesGoes" },
  ],
};

const dermAssoc: IntakeQuestion = {
  id: "derm_assoc",
  kind: "chips",
  titleKey: "intake.q.associated",
  hintKey: "intake.q.complaint.hint",
  hpiLabelKey: "intake.hpi.associated",
  options: [
    { id: "fever", labelKey: "intake.opt.fever" },
    { id: "joint_pain", labelKey: "intake.opt.jointPain" },
    { id: "nail_change", labelKey: "intake.opt.nailChange" },
    { id: "none", labelKey: "intake.opt.none" },
  ],
};

const dermFeverOrder: IntakeQuestion = {
  id: "derm_fever_order",
  kind: "single",
  titleKey: "intake.q.feverSkinOrder",
  hpiLabelKey: "intake.hpi.feverSkinOrder",
  // They named a fever alongside the skin complaint; this asks the order.
  askIf: { questionId: "complaint", includesAny: ["fever"] },
  options: [
    { id: "fever_first", labelKey: "intake.opt.feverFirst" },
    { id: "skin_first", labelKey: "intake.opt.skinFirst" },
    { id: "same_time", labelKey: "intake.opt.sameTime" },
    { id: "dont_remember", labelKey: "intake.opt.dontRemember" },
  ],
};

const derm: IntakeQuestion[] = [
  complaint,
  duration,
  dermLocation,
  dermCharacter,
  dermItchWhen,
  dermItchSleep,
  dermTrigger,
  dermCourse,
  dermAssoc,
  dermFeverOrder,
  severity,
  extra,
];

// ---- Göğüs Hastalıkları -----------------------------------------------------

const pulmoCharacter: IntakeQuestion = {
  id: "pulmo_character",
  kind: "chips",
  titleKey: "intake.q.breathCharacter",
  hintKey: "intake.q.complaint.hint",
  hpiLabelKey: "intake.hpi.quality",
  options: [
    { id: "dry_cough", labelKey: "intake.opt.dryCough" },
    { id: "phlegm_cough", labelKey: "intake.opt.phlegmCough" },
    { id: "wheeze", labelKey: "intake.opt.wheeze" },
    { id: "painful_breath", labelKey: "intake.opt.painfulBreath" },
  ],
};

const pulmoTrigger: IntakeQuestion = {
  id: "pulmo_trigger",
  kind: "chips",
  titleKey: "intake.q.trigger",
  hintKey: "intake.q.complaint.hint",
  hpiLabelKey: "intake.hpi.trigger",
  options: [
    { id: "exertion", labelKey: "intake.opt.exertion" },
    { id: "lying", labelKey: "intake.opt.whenLying" },
    { id: "cold_air", labelKey: "intake.opt.withColdAir" },
    { id: "no_pattern", labelKey: "intake.opt.noPattern" },
  ],
};

const pulmoAssoc: IntakeQuestion = {
  id: "pulmo_assoc",
  kind: "chips",
  titleKey: "intake.q.associated",
  hintKey: "intake.q.complaint.hint",
  hpiLabelKey: "intake.hpi.associated",
  options: [
    { id: "fever", labelKey: "intake.opt.fever" },
    { id: "night_sweats", labelKey: "intake.opt.nightSweats" },
    { id: "phlegm_color", labelKey: "intake.opt.phlegmColor" },
    { id: "weight_loss", labelKey: "intake.opt.weightLoss" },
    { id: "none", labelKey: "intake.opt.none" },
  ],
};

const pulmo: IntakeQuestion[] = [
  complaint,
  duration,
  onset,
  pulmoCharacter,
  breathTiming,
  breathLying,
  pulmoTrigger,
  timeOfDay,
  pulmoAssoc,
  feverPattern,
  severity,
  extra,
];

// ---- Kadın Hastalıkları ve Doğum ---------------------------------------------

const gynPainWhere: IntakeQuestion = {
  id: "gyn_pain_where",
  kind: "single",
  titleKey: "intake.q.painWhere",
  hpiLabelKey: "intake.hpi.region",
  // They named the pain; this asks where they feel it most.
  askIf: { questionId: "complaint", includesAny: ["pain"] },
  options: [
    { id: "lower_abdomen", labelKey: "intake.opt.lowerAbdomen" },
    { id: "low_back", labelKey: "intake.opt.inLowerBack" },
    { id: "groin", labelKey: "intake.opt.inGroin" },
    { id: "widespread", labelKey: "intake.opt.widespread" },
  ],
};

const gynCycle: IntakeQuestion = {
  id: "gyn_cycle",
  kind: "single",
  titleKey: "intake.q.cycleRelation",
  hpiLabelKey: "intake.hpi.cycle",
  options: [
    { id: "during_period", labelKey: "intake.opt.duringPeriod" },
    { id: "before_period", labelKey: "intake.opt.beforePeriod" },
    { id: "no_relation", labelKey: "intake.opt.noCycleRelation" },
    { id: "no_period", labelKey: "intake.opt.noPeriod" },
  ],
};

const gynAssoc: IntakeQuestion = {
  id: "gyn_assoc",
  kind: "chips",
  titleKey: "intake.q.associated",
  hintKey: "intake.q.complaint.hint",
  hpiLabelKey: "intake.hpi.associated",
  options: [
    { id: "cycle_change", labelKey: "intake.opt.cycleChange" },
    { id: "bleeding_change", labelKey: "intake.opt.bleedingChange" },
    { id: "discharge_change", labelKey: "intake.opt.dischargeChange" },
    { id: "urine_burning", labelKey: "intake.opt.urineBurning" },
    { id: "none", labelKey: "intake.opt.none" },
  ],
};

const gyn: IntakeQuestion[] = [
  complaint,
  duration,
  onset,
  gynPainWhere,
  painCharacter,
  gynCycle,
  gynAssoc,
  severity,
  extra,
];

// ---- Üroloji -------------------------------------------------------------------

const uroUrination: IntakeQuestion = {
  id: "uro_urination",
  kind: "chips",
  titleKey: "intake.q.urination",
  hintKey: "intake.q.complaint.hint",
  hpiLabelKey: "intake.hpi.urination",
  options: [
    { id: "urine_burning", labelKey: "intake.opt.urineBurning" },
    { id: "frequent", labelKey: "intake.opt.frequentUrination" },
    { id: "night", labelKey: "intake.opt.nightUrination" },
    { id: "weak_stream", labelKey: "intake.opt.weakStream" },
    { id: "leakage", labelKey: "intake.opt.leakage" },
    { id: "none", labelKey: "intake.opt.none" },
  ],
};

const uroAssoc: IntakeQuestion = {
  id: "uro_assoc",
  kind: "chips",
  titleKey: "intake.q.associated",
  hintKey: "intake.q.complaint.hint",
  hpiLabelKey: "intake.hpi.associated",
  options: [
    { id: "flank_pain", labelKey: "intake.opt.flankPain" },
    { id: "urine_color", labelKey: "intake.opt.urineColor" },
    { id: "fever", labelKey: "intake.opt.fever" },
    { id: "nausea", labelKey: "intake.opt.nausea" },
    { id: "none", labelKey: "intake.opt.none" },
  ],
};

const uroFlankSide: IntakeQuestion = {
  id: "uro_flank_side",
  kind: "single",
  titleKey: "intake.q.flankSide",
  hpiLabelKey: "intake.hpi.flankSide",
  // They ticked the flank-pain chip; this asks which side.
  askIf: { questionId: "uro_assoc", includesAny: ["flank_pain"] },
  options: [
    { id: "right", labelKey: "intake.opt.right" },
    { id: "left", labelKey: "intake.opt.left" },
    { id: "both", labelKey: "intake.opt.both" },
  ],
};

const uro: IntakeQuestion[] = [
  complaint,
  duration,
  onset,
  uroUrination,
  timeOfDay,
  uroAssoc,
  uroFlankSide,
  feverPattern,
  severity,
  extra,
];

// ---- Göz Hastalıkları ------------------------------------------------------------

const eyeCharacter: IntakeQuestion = {
  id: "eye_character",
  kind: "chips",
  titleKey: "intake.q.eyeFeel",
  hintKey: "intake.q.complaint.hint",
  hpiLabelKey: "intake.hpi.quality",
  options: [
    { id: "gritty", labelKey: "intake.opt.gritty" },
    { id: "burning", labelKey: "intake.opt.burningFeel" },
    { id: "itchy", labelKey: "intake.opt.itchy" },
    { id: "watering", labelKey: "intake.opt.watering" },
    { id: "pain", labelKey: "intake.opt.pain" },
  ],
};

const eyePainMove: IntakeQuestion = {
  id: "eye_pain_move",
  kind: "single",
  titleKey: "intake.q.eyePainMove",
  hpiLabelKey: "intake.hpi.eyePainMove",
  // They ticked the pain chip; this asks whether moving the eye changes it.
  askIf: { questionId: "eye_character", includesAny: ["pain"] },
  options: [
    { id: "yes", labelKey: "intake.opt.yes" },
    { id: "sometimes", labelKey: "intake.opt.sometimes" },
    { id: "no", labelKey: "intake.opt.no" },
  ],
};

const eyeVision: IntakeQuestion = {
  id: "eye_vision",
  kind: "chips",
  titleKey: "intake.q.vision",
  hintKey: "intake.q.complaint.hint",
  hpiLabelKey: "intake.hpi.vision",
  options: [
    { id: "blurry", labelKey: "intake.opt.blurry" },
    { id: "double", labelKey: "intake.opt.doubleVision" },
    { id: "floaters", labelKey: "intake.opt.floaters" },
    { id: "halos", labelKey: "intake.opt.halos" },
    { id: "none", labelKey: "intake.opt.none" },
  ],
};

const eyeAssoc: IntakeQuestion = {
  id: "eye_assoc",
  kind: "chips",
  titleKey: "intake.q.associated",
  hintKey: "intake.q.complaint.hint",
  hpiLabelKey: "intake.hpi.associated",
  options: [
    { id: "redness", labelKey: "intake.opt.redness" },
    { id: "discharge", labelKey: "intake.opt.eyeDischarge" },
    { id: "light", labelKey: "intake.opt.lightSensitivity" },
    { id: "headache", labelKey: "intake.opt.headache" },
    { id: "none", labelKey: "intake.opt.none" },
  ],
};

const eyeHeadacheLink: IntakeQuestion = {
  id: "eye_headache_link",
  kind: "single",
  titleKey: "intake.q.eyeHeadache",
  hpiLabelKey: "intake.hpi.eyeHeadache",
  // They named a headache alongside the eye complaint; this asks the order.
  askIf: { questionId: "complaint", includesAny: ["headache"] },
  options: [
    { id: "together", labelKey: "intake.opt.together" },
    { id: "headache_first", labelKey: "intake.opt.headacheFirst" },
    { id: "eye_first", labelKey: "intake.opt.eyeFirst" },
    { id: "separately", labelKey: "intake.opt.separately" },
  ],
};

const eye: IntakeQuestion[] = [
  complaint,
  duration,
  onset,
  side,
  eyeCharacter,
  eyePainMove,
  eyeVision,
  eyeAssoc,
  eyeHeadacheLink,
  severity,
  extra,
];

// ---- Gastroenteroloji --------------------------------------------------------------

const gastroLocation: IntakeQuestion = {
  id: "gastro_location",
  kind: "chips",
  titleKey: "intake.q.abdomenWhere",
  hintKey: "intake.q.complaint.hint",
  hpiLabelKey: "intake.hpi.region",
  options: [
    { id: "upper", labelKey: "intake.opt.upperAbdomen" },
    { id: "lower", labelKey: "intake.opt.lowerAbdomen" },
    { id: "right", labelKey: "intake.opt.abdomenRight" },
    { id: "left", labelKey: "intake.opt.abdomenLeft" },
    { id: "navel", labelKey: "intake.opt.aroundNavel" },
    { id: "whole", labelKey: "intake.opt.wholeAbdomen" },
  ],
};

const gastroCharacter: IntakeQuestion = {
  id: "gastro_character",
  kind: "chips",
  titleKey: "intake.q.character",
  hintKey: "intake.q.complaint.hint",
  hpiLabelKey: "intake.hpi.character",
  options: [
    { id: "burning", labelKey: "intake.opt.burning" },
    { id: "cramping", labelKey: "intake.opt.cramping" },
    { id: "bloating", labelKey: "intake.opt.bloatingFeel" },
    { id: "dull", labelKey: "intake.opt.dull" },
  ],
};

const gastroMeal: IntakeQuestion = {
  id: "gastro_meal",
  kind: "single",
  titleKey: "intake.q.mealRelation",
  hpiLabelKey: "intake.hpi.mealRelation",
  // Structurally obvious (INT-236): meal relation of the stomach complaint.
  askIf: { questionId: "complaint", includesAny: ["stomach"] },
  options: [
    { id: "after_meal", labelKey: "intake.opt.afterMeal" },
    { id: "hungry", labelKey: "intake.opt.whenHungry" },
    { id: "eased_by_meal", labelKey: "intake.opt.easedByMeal" },
    { id: "no_pattern", labelKey: "intake.opt.noPattern" },
  ],
};

const gastroBowel: IntakeQuestion = {
  id: "gastro_bowel",
  kind: "chips",
  titleKey: "intake.q.bowel",
  hintKey: "intake.q.complaint.hint",
  hpiLabelKey: "intake.hpi.bowel",
  // Structurally obvious (INT-236): bowel habit of the stomach complaint.
  askIf: { questionId: "complaint", includesAny: ["stomach"] },
  options: [
    { id: "constipation", labelKey: "intake.opt.constipation" },
    { id: "diarrhea", labelKey: "intake.opt.diarrhea" },
    { id: "alternating", labelKey: "intake.opt.alternatingBowel" },
    { id: "none", labelKey: "intake.opt.none" },
  ],
};

const gastroBowelRelief: IntakeQuestion = {
  id: "gastro_bowel_relief",
  kind: "single",
  titleKey: "intake.q.bowelRelief",
  hpiLabelKey: "intake.hpi.bowelRelief",
  // Level two: they named a change in bowel habit, so ask what going to the
  // toilet does to the complaint they came with.
  askIf: {
    questionId: "gastro_bowel",
    includesAny: ["constipation", "diarrhea", "alternating"],
  },
  options: [
    { id: "eases", labelKey: "intake.opt.itEases" },
    { id: "same", labelKey: "intake.opt.noChange" },
    { id: "worse", labelKey: "intake.opt.itIncreases" },
    { id: "not_sure", labelKey: "intake.opt.notSure" },
  ],
};

const gastroAssoc: IntakeQuestion = {
  id: "gastro_assoc",
  kind: "chips",
  titleKey: "intake.q.associated",
  hintKey: "intake.q.complaint.hint",
  hpiLabelKey: "intake.hpi.associated",
  options: [
    { id: "nausea", labelKey: "intake.opt.nausea" },
    { id: "vomiting", labelKey: "intake.opt.vomiting" },
    { id: "heartburn", labelKey: "intake.opt.heartburn" },
    { id: "appetite_loss", labelKey: "intake.opt.appetiteLoss" },
    { id: "none", labelKey: "intake.opt.none" },
  ],
};

const gastro: IntakeQuestion[] = [
  complaint,
  duration,
  gastroLocation,
  gastroCharacter,
  gastroMeal,
  gastroBowel,
  gastroBowelRelief,
  gastroAssoc,
  feverPattern,
  severity,
  extra,
];

// ---- the universal history block (INT-256) ----------------------------------
//
// 04 §1 rows 5 and 6, authored once and inherited by every branch the way
// base.intake is (03 §6). Wording follows base/intake.yaml's own `ask_tr` and
// `follow_up_tr` — that file's header records that question copy is product
// copy an agent may write, while every clinical VALUE in it is left empty for
// the physician. The same line is drawn here.
//
// WHAT THESE QUESTIONS DO NOT DO, stated once for all of them: no option list
// is ordered by severity, no answer grades anything, no answer is read to
// produce another answer, and no gate below crosses a section boundary. The
// only gates are the INT-236 shape — a further detail of something the
// patient has ALREADY named. Deciding that an answer MEANS something is the
// sourced chain's job (INT-057/041/096) and it is awaiting HB-C1.

// -- 04 §1 row 5 · meds_allergies. Both modes: 04 §1 puts the whole row in the
//    fast column. Only three of the eight cost an unconditional turn.

const allergyKnown: IntakeQuestion = {
  id: "allergy_known",
  kind: "single",
  section: "meds_allergies",
  noteSection: "allergies",
  titleKey: "intake.q.allergyKnown",
  lineLabelKey: "intake.note.allergyKnown",
  options: [
    { id: "yes", labelKey: "intake.opt.yes" },
    { id: "no", labelKey: "intake.opt.no" },
    { id: "not_sure", labelKey: "intake.opt.notSure" },
  ],
};

const allergyKind: IntakeQuestion = {
  id: "allergy_kind",
  kind: "chips",
  section: "meds_allergies",
  noteSection: "allergies",
  titleKey: "intake.q.allergyKind",
  hintKey: "intake.q.complaint.hint",
  lineLabelKey: "intake.note.allergyKind",
  // The patient said they have one; this asks what it is against.
  askIf: { questionId: "allergy_known", includesAny: ["yes"] },
  options: [
    { id: "medicine", labelKey: "intake.opt.allergyMedicine" },
    { id: "food", labelKey: "intake.opt.allergyFood" },
    { id: "sting", labelKey: "intake.opt.allergySting" },
    { id: "latex", labelKey: "intake.opt.allergyLatex" },
    { id: "pollen_dust", labelKey: "intake.opt.allergyPollenDust" },
    { id: "other", labelKey: "intake.opt.other" },
  ],
};

const allergyDetail: IntakeQuestion = {
  id: "allergy_detail",
  kind: "text",
  section: "meds_allergies",
  noteSection: "allergies",
  titleKey: "intake.q.allergyDetail",
  hintKey: "intake.q.allergyDetail.hint",
  lineLabelKey: "intake.note.allergyDetail",
  // Level two: they placed the allergy in a group, so ask them to name it.
  askIf: {
    questionId: "allergy_kind",
    includesAny: ["medicine", "food", "sting", "latex", "pollen_dust", "other"],
  },
};

const allergyReaction: IntakeQuestion = {
  id: "allergy_reaction",
  kind: "chips",
  section: "meds_allergies",
  noteSection: "allergies",
  titleKey: "intake.q.allergyReaction",
  hintKey: "intake.q.complaint.hint",
  lineLabelKey: "intake.note.allergyReaction",
  askIf: { questionId: "allergy_known", includesAny: ["yes"] },
  // The three named options are base/intake.yaml's own follow_up_tr, in the
  // order that file names them. THAT ORDER IS NOT A SEVERITY ORDER and no
  // reading of this list grades anything: what a reaction means is the
  // physician's determination, and nothing here computes it.
  options: [
    { id: "rash", labelKey: "intake.opt.reactionRash" },
    { id: "swelling", labelKey: "intake.opt.reactionSwelling" },
    { id: "breathing", labelKey: "intake.opt.dyspnoea" },
    { id: "nausea", labelKey: "intake.opt.nausea" },
    { id: "other", labelKey: "intake.opt.other" },
    { id: "not_sure", labelKey: "intake.opt.notSure" },
  ],
};

const medsOther: IntakeQuestion = {
  id: "meds_other",
  kind: "single",
  section: "meds_allergies",
  noteSection: "medications",
  titleKey: "intake.q.medsOther",
  lineLabelKey: "intake.note.medsOther",
  options: [
    { id: "yes", labelKey: "intake.opt.yes" },
    { id: "no", labelKey: "intake.opt.no" },
    { id: "not_sure", labelKey: "intake.opt.notSure" },
  ],
};

const medsOtherDetail: IntakeQuestion = {
  id: "meds_other_detail",
  kind: "text",
  section: "meds_allergies",
  noteSection: "medications",
  titleKey: "intake.q.medsOtherDetail",
  hintKey: "intake.q.medsOtherDetail.hint",
  lineLabelKey: "intake.note.medsOtherDetail",
  askIf: { questionId: "meds_other", includesAny: ["yes"] },
  // Invariant 22, the concrete case: a dose is the patient's own words in a
  // plain text field. There is no numeric field anywhere on this path, and
  // the hint deliberately asks for a colour rather than a number.
};

const medsOtc: IntakeQuestion = {
  id: "meds_otc",
  kind: "single",
  section: "meds_allergies",
  noteSection: "medications",
  titleKey: "intake.q.medsOtc",
  lineLabelKey: "intake.note.medsOtc",
  options: [
    { id: "yes", labelKey: "intake.opt.yes" },
    { id: "no", labelKey: "intake.opt.no" },
    { id: "not_sure", labelKey: "intake.opt.notSure" },
  ],
};

const medsOtcDetail: IntakeQuestion = {
  id: "meds_otc_detail",
  kind: "text",
  section: "meds_allergies",
  noteSection: "medications",
  titleKey: "intake.q.medsOtcDetail",
  hintKey: "intake.q.medsOtcDetail.hint",
  lineLabelKey: "intake.note.medsOtcDetail",
  askIf: { questionId: "meds_otc", includesAny: ["yes"] },
};

// -- 04 §1 row 6 · pmh_fh_sh. Detaylı only: 02 §2 puts "PMH/FH/SH deltas" in
//    the detailed column and leaves the fast column at meds/allergies confirm.

const pmhKnown: IntakeQuestion = {
  id: "pmh_known",
  kind: "single",
  section: "pmh_fh_sh",
  noteSection: "pmh",
  modes: ["detayli"],
  titleKey: "intake.q.pmhKnown",
  lineLabelKey: "intake.note.pmhKnown",
  options: [
    { id: "yes", labelKey: "intake.opt.yes" },
    { id: "no", labelKey: "intake.opt.no" },
    { id: "not_sure", labelKey: "intake.opt.notSure" },
  ],
};

const pmhConditions: IntakeQuestion = {
  id: "pmh_conditions",
  kind: "chips",
  section: "pmh_fh_sh",
  noteSection: "pmh",
  modes: ["detayli"],
  titleKey: "intake.q.pmhConditions",
  hintKey: "intake.q.complaint.hint",
  lineLabelKey: "intake.note.pmhConditions",
  askIf: { questionId: "pmh_known", includesAny: ["yes"] },
  // The five named conditions are quoted from 04 §2.1 `cluster.medical`
  // ("chronic-disease deltas (DM, HTN, COPD/asthma, CKD, thyroid)") — the
  // blueprint's own list, not a clinical selection made here. Anything the
  // list does not name reaches the note through the free-text step below.
  options: [
    { id: "diabetes", labelKey: "intake.opt.pmhDiabetes" },
    { id: "blood_pressure", labelKey: "intake.opt.pmhBloodPressure" },
    { id: "asthma_copd", labelKey: "intake.opt.pmhAsthmaCopd" },
    { id: "kidney", labelKey: "intake.opt.pmhKidney" },
    { id: "thyroid", labelKey: "intake.opt.pmhThyroid" },
    { id: "other", labelKey: "intake.opt.other" },
  ],
};

const pmhOtherDetail: IntakeQuestion = {
  id: "pmh_other_detail",
  kind: "text",
  section: "pmh_fh_sh",
  noteSection: "pmh",
  modes: ["detayli"],
  titleKey: "intake.q.pmhOtherDetail",
  lineLabelKey: "intake.note.pmhOtherDetail",
  // Level two: they ticked the "other" chip, so ask them to name it.
  askIf: { questionId: "pmh_conditions", includesAny: ["other"] },
};

const pmhSurgery: IntakeQuestion = {
  id: "pmh_surgery",
  kind: "single",
  section: "pmh_fh_sh",
  noteSection: "pmh",
  modes: ["detayli"],
  titleKey: "intake.q.pmhSurgery",
  lineLabelKey: "intake.note.pmhSurgery",
  options: [
    { id: "yes", labelKey: "intake.opt.yes" },
    { id: "no", labelKey: "intake.opt.no" },
    { id: "dont_remember", labelKey: "intake.opt.dontRemember" },
  ],
};

const pmhSurgeryDetail: IntakeQuestion = {
  id: "pmh_surgery_detail",
  kind: "text",
  section: "pmh_fh_sh",
  noteSection: "pmh",
  modes: ["detayli"],
  titleKey: "intake.q.pmhSurgeryDetail",
  hintKey: "intake.q.pmhSurgeryDetail.hint",
  lineLabelKey: "intake.note.pmhSurgeryDetail",
  askIf: { questionId: "pmh_surgery", includesAny: ["yes"] },
  // The hint invites a year, and a year typed into a free-text field is not
  // a numeric entry: there is no numeric field, no unit and no arithmetic.
};

const pmhRecentChange: IntakeQuestion = {
  id: "pmh_recent_change",
  kind: "single",
  section: "pmh_fh_sh",
  noteSection: "pmh",
  modes: ["detayli"],
  titleKey: "intake.q.pmhRecentChange",
  lineLabelKey: "intake.note.pmhRecentChange",
  // 04 §1 row 6 is a DELTA row ("new diagnoses/hospitalisations since last
  // visit"), so the question asks for the change, not for a full history.
  options: [
    { id: "yes", labelKey: "intake.opt.yes" },
    { id: "no", labelKey: "intake.opt.no" },
    { id: "not_sure", labelKey: "intake.opt.notSure" },
  ],
};

const pmhRecentDetail: IntakeQuestion = {
  id: "pmh_recent_detail",
  kind: "text",
  section: "pmh_fh_sh",
  noteSection: "pmh",
  modes: ["detayli"],
  titleKey: "intake.q.pmhRecentDetail",
  hintKey: "intake.q.pmhRecentDetail.hint",
  lineLabelKey: "intake.note.pmhRecentDetail",
  askIf: { questionId: "pmh_recent_change", includesAny: ["yes"] },
};

const fhKnown: IntakeQuestion = {
  id: "fh_known",
  kind: "single",
  section: "pmh_fh_sh",
  noteSection: "family_social",
  modes: ["detayli"],
  deferrableAs: FAMILY_HISTORY_DEFERRAL,
  titleKey: "intake.q.fhKnown",
  lineLabelKey: "intake.note.fhKnown",
  options: [
    { id: "yes", labelKey: "intake.opt.yes" },
    { id: "no", labelKey: "intake.opt.no" },
    { id: "not_sure", labelKey: "intake.opt.notSure" },
  ],
};

const fhWho: IntakeQuestion = {
  id: "fh_who",
  kind: "chips",
  section: "pmh_fh_sh",
  noteSection: "family_social",
  modes: ["detayli"],
  deferrableAs: FAMILY_HISTORY_DEFERRAL,
  titleKey: "intake.q.fhWho",
  hintKey: "intake.q.complaint.hint",
  lineLabelKey: "intake.note.fhWho",
  askIf: { questionId: "fh_known", includesAny: ["yes"] },
  // WHO is a relationship list — structural, and the same for every branch.
  // WHAT is deliberately free text below: which familial conditions matter
  // is a per-specialty determination (04 §2.2 names "family history of GI
  // cancer/IBD" for gastroenterology alone), so no checklist is authored.
  options: [
    { id: "mother", labelKey: "intake.opt.fhMother" },
    { id: "father", labelKey: "intake.opt.fhFather" },
    { id: "sibling", labelKey: "intake.opt.fhSibling" },
    { id: "child", labelKey: "intake.opt.fhChild" },
    { id: "grandparent", labelKey: "intake.opt.fhGrandparent" },
    { id: "other", labelKey: "intake.opt.other" },
  ],
};

const fhDetail: IntakeQuestion = {
  id: "fh_detail",
  kind: "text",
  section: "pmh_fh_sh",
  noteSection: "family_social",
  modes: ["detayli"],
  deferrableAs: FAMILY_HISTORY_DEFERRAL,
  titleKey: "intake.q.fhDetail",
  lineLabelKey: "intake.note.fhDetail",
  // Level two: they named the relatives, so ask what it is they have.
  askIf: {
    questionId: "fh_who",
    includesAny: ["mother", "father", "sibling", "child", "grandparent", "other"],
  },
};

/**
 * The block, in 04 §1's own section order (row 5 then row 6) and inside each
 * section in the order base/intake.yaml lists the slots.
 */
export const historyQuestions: readonly IntakeQuestion[] = [
  allergyKnown,
  allergyKind,
  allergyDetail,
  allergyReaction,
  medsOther,
  medsOtherDetail,
  medsOtc,
  medsOtcDetail,
  pmhKnown,
  pmhConditions,
  pmhOtherDetail,
  pmhSurgery,
  pmhSurgeryDetail,
  pmhRecentChange,
  pmhRecentDetail,
  fhKnown,
  fhWho,
  fhDetail,
];

// ---- resolution --------------------------------------------------------------------

const general: IntakeQuestion[] = [complaint, duration, extra];

const PACKS: { match: RegExp; questions: IntakeQuestion[] }[] = [
  { match: /kardiyoloji|ic hastalik|dahiliye/, questions: cardioInternal },
  { match: /noroloji/, questions: neuro },
  { match: /kulak|kbb|burun bogaz/, questions: ent },
  { match: /ortopedi|travmatoloji/, questions: ortho },
  { match: /cilt|cildiye|dermatoloji/, questions: derm },
  { match: /gogus|pulmonoloji/, questions: pulmo },
  { match: /kadin dogum|jinekoloji|kadin hastaliklari/, questions: gyn },
  { match: /uroloji|bevliye/, questions: uro },
  { match: /goz/, questions: eye },
  { match: /gastro|mide barsak|sindirim/, questions: gastro },
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

/**
 * The universal block narrowed to one session profile (INT-256). Two filters,
 * both session-constant:
 *
 * - `modes` — 02 §2. A question with no `modes` is asked in both; the
 *   `pmh_fh_sh` deltas declare `["detayli"]` because 02 §2 puts them in the
 *   detailed column and leaves the fast column at meds/allergies confirm.
 * - `deferrableAs` — 02 §33. A deferred section is ABSENT from the flow, not
 *   asked more quietly and not moved to text; the clinician sees it as
 *   `eksik: ortam uygun değildi` on the note instead (buildNote).
 */
export function historyForProfile(profile: IntakeProfile): IntakeQuestion[] {
  const deferred = new Set(profile.deferred ?? []);
  return historyQuestions.filter(
    (q) =>
      (q.modes === undefined || q.modes.includes(profile.mode)) &&
      (q.deferrableAs === undefined || !deferred.has(q.deferrableAs)),
  );
}

/**
 * The pack a visit actually runs: the department's anamnesis dimensions,
 * then the universal history block, then the free note — 04 §1's own section
 * order (hpi → meds_allergies → pmh_fh_sh → expectations_wrapup).
 *
 * Composition rather than duplication is the point: `packForDepartment` stays
 * the ten authored HPI packs, and the base block is authored once, exactly as
 * 03 §6 resolves base.intake under specialty.*.
 */
export function packForVisit(
  department: string | undefined,
  profile: IntakeProfile,
): IntakeQuestion[] {
  const pack = packForDepartment(department);
  const dimensions = pack.filter((q) => q.id !== extra.id);
  const closing = pack.filter((q) => q.id === extra.id);
  return [...dimensions, ...historyForProfile(profile), ...closing];
}

/**
 * Every question across packs, unique by id, in the canonical anamnesis
 * order — the note builder walks this list, so it is the single ordering
 * authority for the note's lines. Each pack must read as a subsequence of
 * this list (questions.test.ts enforces both coverage and order), and the
 * history block sits where `packForVisit` composes it: after the last
 * department dimension, before the free note.
 */
export const allQuestions: readonly IntakeQuestion[] = [
  complaint,
  duration,
  onset,
  // location and side
  orthoMechanism,
  orthoFallHow,
  orthoRegion,
  orthoSpread,
  orthoSpreadFeel,
  neuroHeadSide,
  neuroHeadSame,
  entPainWhere,
  entSwallow,
  dermLocation,
  gastroLocation,
  gynPainWhere,
  side,
  // character
  painCharacter,
  neuroCharacter,
  pulmoCharacter,
  dermCharacter,
  dermItchWhen,
  dermItchSleep,
  eyeCharacter,
  eyePainMove,
  uroUrination,
  gastroCharacter,
  // radiation and breathing
  radiation,
  radiationSide,
  eyeVision,
  breathTiming,
  breathLying,
  // triggers
  cardioTrigger,
  neuroTrigger,
  entTrigger,
  orthoTrigger,
  dermTrigger,
  pulmoTrigger,
  gynCycle,
  gastroMeal,
  // timing and course
  neuroCourse,
  timeOfDay,
  dermCourse,
  gastroBowel,
  gastroBowelRelief,
  // associated
  cardioAssoc,
  cardioPalpitation,
  neuroAssoc,
  neuroNumbWhere,
  entAssoc,
  entHearSide,
  orthoAssoc,
  dermAssoc,
  dermFeverOrder,
  pulmoAssoc,
  gynAssoc,
  uroAssoc,
  uroFlankSide,
  eyeAssoc,
  eyeHeadacheLink,
  gastroAssoc,
  feverPattern,
  severity,
  // the universal history block (04 §1 rows 5–6), composed by packForVisit
  ...historyQuestions,
  extra,
];

/** Kept for the generic (no-department) flows and existing tests. */
export const intakeQuestions: readonly IntakeQuestion[] = general;

// ---- adaptive flow (INT-236) ------------------------------------------------

/**
 * Whether a gate is met by the committed answers. Mirrors the dev-tier
 * reading of dsl.py `ask_if`: met when the referenced question's answer
 * includes any listed option id; unanswered gating question → unmet, so
 * the gated question stays hidden until its condition is established.
 */
export function askIfMet(askIf: AskIf | undefined, answers: readonly AnsweredValues[]): boolean {
  if (askIf === undefined) {
    return true;
  }
  const gating = answers.find((a) => a.questionId === askIf.questionId);
  if (gating === undefined) {
    return false;
  }
  return askIf.includesAny.some((id) => gating.values.includes(id));
}

/**
 * The pack filtered to the questions applicable under the given answers —
 * the single source of truth for the dynamic progress denominator, the
 * step flow and any dialogue engine consuming packs. Re-evaluate whenever
 * answers change: an edit that unmets a gate removes the question from
 * this list while its committed answer stays in the note, marked
 * "koşul değişti" by the note builder (never silently discarded).
 */
export function applicableQuestions(
  pack: readonly IntakeQuestion[],
  answers: readonly AnsweredValues[],
): IntakeQuestion[] {
  return pack.filter((q) => askIfMet(q.askIf, answers));
}

/**
 * The next applicable question after `currentId` in pack order, or null at
 * the end — robust even when the current question itself just left the
 * applicable list, because it walks the FULL pack from the current
 * position and gates each candidate.
 */
export function nextApplicableQuestion(
  pack: readonly IntakeQuestion[],
  answers: readonly AnsweredValues[],
  currentId: string,
): IntakeQuestion | null {
  const at = pack.findIndex((q) => q.id === currentId);
  for (const q of pack.slice(at + 1)) {
    if (askIfMet(q.askIf, answers)) {
      return q;
    }
  }
  return null;
}

/**
 * The checkpoint's eksik list (02 §34 v2-partial semantics): applicable
 * questions without a contentful answer, in pack order. A question whose
 * gate is unmet is SKIPPED, not missing — it never appears here.
 */
export function missingQuestions(
  pack: readonly IntakeQuestion[],
  answers: readonly AnsweredValues[],
): IntakeQuestion[] {
  const answered = new Set(
    answers.filter((a) => a.values.some((v) => v.trim().length > 0)).map((a) => a.questionId),
  );
  return applicableQuestions(pack, answers).filter((q) => !answered.has(q.id));
}

export function optionLabelKey(questionId: string, optionId: string): MessageKey | null {
  const q = allQuestions.find((x) => x.id === questionId);
  return q?.options?.find((o) => o.id === optionId)?.labelKey ?? null;
}

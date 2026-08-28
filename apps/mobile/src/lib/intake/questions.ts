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

// ---- Kardiyoloji / İç Hastalıkları ----------------------------------------

const painCharacter: IntakeQuestion = {
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
};

const radiation: IntakeQuestion = {
  id: "radiation",
  kind: "chips",
  titleKey: "intake.q.radiation",
  hintKey: "intake.q.complaint.hint",
  hpiLabelKey: "intake.hpi.radiation",
  options: [
    { id: "arm", labelKey: "intake.opt.radArm" },
    { id: "jaw_neck", labelKey: "intake.opt.radJawNeck" },
    { id: "back", labelKey: "intake.opt.radBack" },
    { id: "no_radiation", labelKey: "intake.opt.radNone" },
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

const cardioInternal: IntakeQuestion[] = [
  complaint,
  duration,
  onset,
  painCharacter,
  radiation,
  cardioTrigger,
  cardioAssoc,
  severity,
  extra,
];

// ---- Nöroloji ---------------------------------------------------------------

const neuroCharacter: IntakeQuestion = {
  id: "neuro_character",
  kind: "chips",
  titleKey: "intake.q.character",
  hintKey: "intake.q.complaint.hint",
  hpiLabelKey: "intake.hpi.character",
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

const neuro: IntakeQuestion[] = [
  complaint,
  duration,
  onset,
  neuroCharacter,
  neuroTrigger,
  neuroCourse,
  neuroAssoc,
  severity,
  extra,
];

// ---- Kulak Burun Boğaz ------------------------------------------------------

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

const ent: IntakeQuestion[] = [
  complaint,
  duration,
  onset,
  side,
  entTrigger,
  entAssoc,
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
  orthoRegion,
  side,
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

const derm: IntakeQuestion[] = [
  complaint,
  duration,
  dermLocation,
  dermCharacter,
  dermTrigger,
  dermCourse,
  dermAssoc,
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
  pulmoTrigger,
  timeOfDay,
  pulmoAssoc,
  severity,
  extra,
];

// ---- Kadın Hastalıkları ve Doğum ---------------------------------------------

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

const uro: IntakeQuestion[] = [
  complaint,
  duration,
  onset,
  uroUrination,
  timeOfDay,
  uroAssoc,
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

const eye: IntakeQuestion[] = [
  complaint,
  duration,
  onset,
  side,
  eyeCharacter,
  eyeVision,
  eyeAssoc,
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
  options: [
    { id: "constipation", labelKey: "intake.opt.constipation" },
    { id: "diarrhea", labelKey: "intake.opt.diarrhea" },
    { id: "alternating", labelKey: "intake.opt.alternatingBowel" },
    { id: "none", labelKey: "intake.opt.none" },
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
  gastroAssoc,
  severity,
  extra,
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
 * Every question across packs, unique by id, in the canonical anamnesis
 * order — the note builder walks this list, so it is the single ordering
 * authority for HPI lines. Each pack must read as a subsequence of this
 * list (questions.test.ts enforces both coverage and order).
 */
export const allQuestions: readonly IntakeQuestion[] = [
  complaint,
  duration,
  onset,
  orthoMechanism,
  orthoRegion,
  dermLocation,
  gastroLocation,
  side,
  painCharacter,
  neuroCharacter,
  pulmoCharacter,
  dermCharacter,
  eyeCharacter,
  uroUrination,
  gastroCharacter,
  radiation,
  eyeVision,
  cardioTrigger,
  neuroTrigger,
  entTrigger,
  orthoTrigger,
  dermTrigger,
  pulmoTrigger,
  gynCycle,
  gastroMeal,
  neuroCourse,
  timeOfDay,
  dermCourse,
  gastroBowel,
  cardioAssoc,
  neuroAssoc,
  entAssoc,
  orthoAssoc,
  dermAssoc,
  pulmoAssoc,
  gynAssoc,
  uroAssoc,
  eyeAssoc,
  gastroAssoc,
  severity,
  extra,
];

/** Kept for the generic (no-department) flows and existing tests. */
export const intakeQuestions: readonly IntakeQuestion[] = general;

export function optionLabelKey(questionId: string, optionId: string): MessageKey | null {
  const q = allQuestions.find((x) => x.id === questionId);
  return q?.options?.find((o) => o.id === optionId)?.labelKey ?? null;
}

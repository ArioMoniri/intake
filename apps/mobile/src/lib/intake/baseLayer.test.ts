/**
 * INT-282 — the HBYS base layer, and the branching the owner asked for.
 *
 * Two halves, one issue.
 *
 * HALF 1. `docs/sources/hbys_intake_schema.md` is a real Turkish hospital
 * intake field set, committed verbatim. The value of it is THE SPLIT: what a
 * patient can answer becomes a base-layer question composed onto every
 * department; what only a clinician or a lab can supply is never asked of a
 * patient at all, and this file asserts each of those by name.
 *
 * HALF 2. The owner widened the issue: "dont use only my schema use dyanimc
 * department based resposive to previosus questions and asnwering plus the
 * schema". So the packs must also branch on what the patient already said,
 * in both modes — Hızlı short, Detaylı deep — with the mode filter as the
 * lever.
 *
 * WHAT THIS FILE REFUSES TO ASSERT, stated once. No threshold, no cut-off,
 * no red-flag level, no "this answer is concerning". Every gate below turns
 * on STRUCTURE — did they say yes, how long has it been, which relative —
 * never on clinical significance. Deciding what an answer MEANS is
 * INT-043 → INT-044..051 and is awaiting a physician (HB-C1).
 */
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { en } from "../i18n/en";
import { tr } from "../i18n/tr";
import { buildNote } from "./note";
import { baseLayerQuestions, measurementQuestions, MEASURE_UNIT_OF } from "./baseLayer";
import {
  allQuestions,
  applicableQuestions,
  historyQuestions,
  packForDepartment,
  packForVisit,
  spokenPack,
  PROTOCOL_SECTION_OF,
  type IntakeProfile,
  type IntakeQuestion,
} from "./questions";

const HIZLI: IntakeProfile = { mode: "hizli" };
const DETAYLI: IntakeProfile = { mode: "detayli" };

const BRANCHES = [
  "Kardiyoloji",
  "Nöroloji",
  "Kulak Burun Boğaz",
  "Ortopedi ve Travmatoloji",
  "Dermatoloji",
  "Göğüs Hastalıkları",
  "Kadın Hastalıkları ve Doğum",
  "Üroloji",
  "Göz Hastalıkları",
  "Gastroenteroloji",
];

function ids(pack: readonly IntakeQuestion[]): string[] {
  return pack.map((q) => q.id);
}

// ---- the source is a source: byte-identical or the mapping is fiction -----

describe("the owner's schema is committed verbatim and never edited", () => {
  const SCHEMA = join(
    __dirname,
    "..",
    "..",
    "..",
    "..",
    "..",
    "docs",
    "sources",
    "hbys_intake_schema.md",
  );

  /**
   * Recorded on 2026-09-02 from the file as the owner supplied it. A mapping
   * built against a source nobody can re-check is a mapping built against
   * nothing, so the sha is the check.
   */
  const SHA256 = "433c5cae87566b34baf7783b1fbd59305b0325a8d6ba1ce9292b26fcda08e490";

  it("hashes to the recorded sha256", () => {
    const bytes = readFileSync(SCHEMA);
    expect(createHash("sha256").update(bytes).digest("hex")).toBe(SHA256);
  });

  it("still carries the vendor field ids the connector will write to", () => {
    const source = readFileSync(SCHEMA, "utf8");
    for (const id of ["361_LS", "1353_LM", "td382", "8997_LS", "4229_LS", "1352_LS"]) {
      expect(source, id).toContain(id);
    }
  });
});

// ---- HALF 1a: the patient-answerable subset, composed once ----------------

describe("the base layer is composed onto every department, never copied into one", () => {
  it("packForDepartment stays HPI-only — no base-layer question leaks into a pack", () => {
    const baseIds = new Set([...ids(baseLayerQuestions), ...ids(measurementQuestions)]);
    for (const branch of [...BRANCHES, "Aile Hekimliği", undefined]) {
      for (const q of packForDepartment(branch)) {
        expect(baseIds.has(q.id), `${branch}/${q.id}`).toBe(false);
      }
    }
  });

  it("every branch and the no-department fallback gets the whole base layer", () => {
    for (const branch of [...BRANCHES, "Aile Hekimliği", undefined]) {
      const pack = ids(packForVisit(branch, DETAYLI));
      for (const q of [...baseLayerQuestions, ...measurementQuestions]) {
        expect(pack, `${branch}/${q.id}`).toContain(q.id);
      }
    }
  });

  it("it sits after the universal history block and before the free note", () => {
    const pack = ids(packForVisit("Kardiyoloji", DETAYLI));
    const lastHistory = pack.indexOf(historyQuestions[historyQuestions.length - 1].id);
    const firstBase = pack.indexOf(baseLayerQuestions[0].id);
    expect(firstBase).toBeGreaterThan(lastHistory);
    expect(pack[pack.length - 1]).toBe("extra");
  });

  it("the schema's own nine patient-answerable topics are each asked exactly once", () => {
    expect(ids(baseLayerQuestions)).toEqual([
      "smoking",
      "smoking_quit_when",
      "alcohol",
      "substance",
      "occupation",
      "disability",
      "injury_history",
      "injury_detail",
      "blood_group",
      "transfusion",
      "fh_mother_conditions",
      "fh_father_conditions",
      "fh_brother_conditions",
      "fh_sister_conditions",
    ]);
  });

  it("smoking keeps the schema's five states", () => {
    const smoking = baseLayerQuestions.find((q) => q.id === "smoking")!;
    expect(smoking.options!.map((o) => o.id)).toEqual([
      "never",
      "former",
      "daily",
      "occasional",
      "not_stated",
    ]);
  });

  it("the chronic-condition checklist covers the schema's seven named rows", () => {
    const conditions = allQuestions.find((q) => q.id === "pmh_conditions")!;
    const optionIds = conditions.options!.map((o) => o.id);
    // HT · kalp-damar · kanser · DM · kan hastalıkları · KBH · diğer
    for (const id of [
      "blood_pressure",
      "heart",
      "cancer",
      "diabetes",
      "blood",
      "kidney",
      "other",
    ]) {
      expect(optionIds, id).toContain(id);
    }
  });

  it("the declared blood group offers the schema's eight groups plus 'bilmiyorum'", () => {
    const group = baseLayerQuestions.find((q) => q.id === "blood_group")!;
    expect(group.options!.map((o) => o.id)).toEqual([
      "ab_pos",
      "ab_neg",
      "a_pos",
      "a_neg",
      "b_pos",
      "b_neg",
      "o_pos",
      "o_neg",
      "unknown",
    ]);
  });

  it("every base-layer question declares a 04 §1 section that agrees with its note section", () => {
    for (const q of baseLayerQuestions) {
      expect(q.section, q.id).toBe("pmh_fh_sh");
      expect(q.noteSection, q.id).toBeDefined();
      expect(PROTOCOL_SECTION_OF[q.noteSection!], q.id).toBe(q.section);
      expect(q.lineLabelKey, q.id).toBeDefined();
      expect(q.hpiLabelKey, q.id).toBeUndefined();
    }
  });
});

// ---- HALF 1b: what a patient is NEVER asked ------------------------------

describe("clinician- and lab-measured fields are never asked of a patient", () => {
  /**
   * Each row is a field of the owner's schema that only a clinician or a lab
   * can supply, with the marker text that would appear if someone ever wrote
   * it as a patient question. `id` is the id such a question would take.
   */
  const NEVER_ASKED: { id: string; tr: RegExp; why: string }[] = [
    { id: "respiratory_rate", tr: /solunum say/i, why: "49_TC — counted by a clinician" },
    { id: "pulse", tr: /nab[ıi]z/i, why: "174_TC — counted by a clinician" },
    { id: "pulse_rhythm", tr: /ritmik|aritmik/i, why: "4328_LS — clinician judgement" },
    { id: "bp_systolic", tr: /mmhg/i, why: "173_TC — measured with a cuff" },
    { id: "bp_diastolic", tr: /diyastol/i, why: "354_TC — measured with a cuff" },
    { id: "lab_blood_group", tr: /kan grubu \(lab/i, why: "spnbloodgroup — a lab result" },
    { id: "fall_risk", tr: /d[üu][şs]me riski/i, why: "281008_LS — a clinician's assessment" },
    { id: "examination_note", tr: /muayene notu/i, why: "337_TC — the clinician's own note" },
    { id: "treatment_note", tr: /tedavi notu/i, why: "349_TC — the clinician's own note" },
    { id: "history_narrative", tr: /^öykü$/i, why: "9900_TC — the clinician's narrative" },
    { id: "past_history_note", tr: /özgeçmiş notu/i, why: "327_TC — the clinician's narrative" },
  ];

  function everyPackFacingString(): { key: string; text: string }[] {
    const out: { key: string; text: string }[] = [];
    for (const q of allQuestions) {
      for (const key of [q.titleKey, q.hintKey, q.hpiLabelKey, q.lineLabelKey]) {
        if (key) {
          out.push({ key, text: (tr as Record<string, string>)[key] });
        }
      }
      for (const option of q.options ?? []) {
        out.push({ key: option.labelKey, text: (tr as Record<string, string>)[option.labelKey] });
      }
    }
    return out;
  }

  for (const row of NEVER_ASKED) {
    it(`no question is ${row.id} (${row.why})`, () => {
      expect(allQuestions.map((q) => q.id)).not.toContain(row.id);
    });
  }

  it("and no patient-facing string asks for one of them either", () => {
    for (const { key, text } of everyPackFacingString()) {
      for (const row of NEVER_ASKED) {
        expect(row.tr.test(text), `${key} = "${text}" looks like ${row.id}`).toBe(false);
      }
    }
  });

  it("the whole pack of every branch, in both modes, is free of them", () => {
    for (const branch of BRANCHES) {
      for (const profile of [HIZLI, DETAYLI]) {
        for (const q of packForVisit(branch, profile)) {
          for (const row of NEVER_ASKED) {
            expect(q.id, `${branch}/${q.id}`).not.toBe(row.id);
          }
        }
      }
    }
  });
});

// ---- HALF 1c: family history is per relative, and stays theirs -----------

describe("family history takes the schema's per-relative shape", () => {
  const RELATIVES = ["mother", "father", "brother", "sister"];

  it("fh_who names the four relatives the schema distinguishes", () => {
    const who = allQuestions.find((q) => q.id === "fh_who")!;
    const optionIds = who.options!.map((o) => o.id);
    for (const relative of RELATIVES) {
      expect(optionIds, relative).toContain(relative);
    }
    // The undifferentiated "sibling" is gone: the schema keeps erkek/kız
    // kardeş apart and the note has to as well.
    expect(optionIds).not.toContain("sibling");
  });

  it("each relative gets the schema's own five conditions, plus an escape", () => {
    for (const relative of RELATIVES) {
      const q = baseLayerQuestions.find((x) => x.id === `fh_${relative}_conditions`)!;
      expect(q.kind, relative).toBe("chips");
      expect(
        q.options!.map((o) => o.id),
        relative,
      ).toEqual(["ht", "cardiac", "cancer", "diabetes", "blood", "other", "not_sure"]);
      expect(q.askIf, relative).toEqual({ questionId: "fh_who", includesAny: [relative] });
    }
  });

  it("naming one relative opens that relative's checklist and no other", () => {
    const pack = packForVisit("Kardiyoloji", DETAYLI);
    const shown = ids(
      applicableQuestions(pack, [
        { questionId: "fh_known", values: ["yes"] },
        { questionId: "fh_who", values: ["mother"] },
      ]),
    );
    expect(shown).toContain("fh_mother_conditions");
    expect(shown).not.toContain("fh_father_conditions");
    expect(shown).not.toContain("fh_brother_conditions");
    expect(shown).not.toContain("fh_sister_conditions");
  });

  it("the free-text detail survives only for the relatives with no checklist", () => {
    const detail = allQuestions.find((q) => q.id === "fh_detail")!;
    expect(detail.askIf).toEqual({
      questionId: "fh_who",
      includesAny: ["child", "grandparent", "other"],
    });
  });

  it("the note attributes the condition to the RELATIVE, never to the patient", () => {
    const sections = buildNote(
      [
        { questionId: "complaint", values: ["pain"] },
        { questionId: "fh_known", values: ["yes"] },
        { questionId: "fh_who", values: ["mother"] },
        { questionId: "fh_mother_conditions", values: ["diabetes"] },
      ],
      { carriedFacts: [] },
    );
    const family = sections.find((s) => s.id === "family_social")!;
    expect(family.lines).toContain("Annede: Şeker hastalığı");
    // The patient's own history section must not have acquired it.
    expect(sections.find((s) => s.id === "pmh")).toBeUndefined();
    for (const section of sections) {
      if (section.id === "family_social") {
        continue;
      }
      expect(section.lines.join(" "), section.id).not.toContain("Şeker hastalığı");
    }
  });

  it("the family deferral takes the per-relative questions with it (02 §33)", () => {
    const pack = ids(
      packForVisit("Kardiyoloji", { mode: "detayli", deferred: ["family_history"] }),
    );
    for (const relative of RELATIVES) {
      expect(pack, relative).not.toContain(`fh_${relative}_conditions`);
    }
    expect(pack).toContain("smoking");
  });
});

// ---- HALF 1d: invariant 22 — guarded controls, inline renders ------------

describe("invariant 22 — numbers never cross a representation boundary unguarded", () => {
  it("height and weight are guarded measures, never a free numeric text field", () => {
    for (const id of ["height", "weight"]) {
      const q = measurementQuestions.find((x) => x.id === id)!;
      expect(q.kind, id).toBe("measure");
      expect(q.measure, id).toBeDefined();
      expect(q.measure!.min, id).toBeLessThan(q.measure!.max);
      expect(q.measure!.step, id).toBeGreaterThan(0);
      expect(MEASURE_UNIT_OF[id], id).toBeDefined();
    }
  });

  it("no question anywhere collects a quantity as free text", () => {
    for (const q of allQuestions) {
      if (q.kind === "measure") {
        expect(q.options, q.id).toBeUndefined();
      }
      if (q.kind === "text") {
        expect(q.measure, q.id).toBeUndefined();
      }
    }
  });

  it("the pain score is a closed set of authored values, not a typed number", () => {
    const score = measurementQuestions.find((q) => q.id === "pain_score")!;
    expect(score.kind).toBe("single");
    expect(score.options).toHaveLength(11);
    expect(score.askIf).toEqual({ questionId: "pain_present", includesAny: ["yes"] });
  });

  it("every numeral in the pack is an INLINE render beside a word label, never a string", () => {
    for (const q of allQuestions) {
      for (const option of q.options ?? []) {
        const label = (tr as Record<string, string>)[option.labelKey];
        expect(label, `${q.id}/${option.id}`).not.toMatch(/[0-9]/);
        if (option.inline !== undefined) {
          expect(option.inline, `${q.id}/${option.id}`).toMatch(/^[0-9]+$/);
        }
      }
    }
  });

  it("the pain score's numerals are inline, and its labels are Turkish words", () => {
    const score = measurementQuestions.find((q) => q.id === "pain_score")!;
    expect(score.options!.map((o) => o.inline)).toEqual([
      "0",
      "1",
      "2",
      "3",
      "4",
      "5",
      "6",
      "7",
      "8",
      "9",
      "10",
    ]);
    expect((tr as Record<string, string>)[score.options![0].labelKey]).toBe("Sıfır");
    expect((tr as Record<string, string>)[score.options![10].labelKey]).toBe("On");
  });

  it("no numeral reaches the spoken surface: every numeral-bearing step is text_only", () => {
    for (const q of allQuestions) {
      const carriesNumeral =
        q.kind === "measure" || (q.options ?? []).some((o) => o.inline !== undefined);
      if (carriesNumeral) {
        expect(q.delivery, q.id).toBe("text_only");
      }
    }
    const spoken = spokenPack(packForVisit("Kardiyoloji", DETAYLI));
    for (const q of spoken) {
      expect(q.kind, q.id).not.toBe("measure");
      for (const option of q.options ?? []) {
        expect(option.inline, `${q.id}/${option.id}`).toBeUndefined();
      }
    }
  });

  it("the screen actually wires the spoken lane through spokenPack", () => {
    // The filter is only worth anything if the dialogue lane is built from
    // it, so this asserts the wiring and not just the function.
    const screen = readFileSync(
      join(__dirname, "..", "..", "app", "(tabs)", "visits", "[visitId]", "intake.tsx"),
      "utf8",
    );
    expect(screen).toMatch(/questions=\{spokenPack\(intakeQuestions\)\}/);
  });

  it("substance use is text_first, exactly as files/13 §13 classifies it", () => {
    const substance = baseLayerQuestions.find((q) => q.id === "substance")!;
    expect(substance.delivery).toBe("text_first");
  });

  it("the note prints a measure as one non-breaking number+unit atom, ungrouped", () => {
    const sections = buildNote(
      [
        { questionId: "complaint", values: ["pain"] },
        { questionId: "height", values: ["175"] },
        { questionId: "weight", values: ["70"] },
        { questionId: "pain_present", values: ["yes"] },
        { questionId: "pain_score", values: ["3"] },
      ],
      { carriedFacts: [] },
    );
    const measurements = sections.find((s) => s.id === "measurements")!;
    expect(measurements.lines).toEqual([
      "Ağrı var mı: Evet",
      "Ağrı puanı: 3",
      "Boy: 175 cm",
      "Kilo: 70 kg",
    ]);
  });
});

// ---- HALF 2: the flow branches on what the patient already said ----------

describe("duration branches: 'today' and 'this month' ask different questions", () => {
  const pack = packForDepartment("Kardiyoloji");

  const after = (duration: string) =>
    ids(
      applicableQuestions(pack, [
        { questionId: "complaint", values: ["pain"] },
        { questionId: "duration", values: [duration] },
      ]),
    );

  it("'bugün' opens the time-of-day follow-up and not the course one", () => {
    const today = after("today");
    expect(today).toContain("onset_today_when");
    expect(today).not.toContain("duration_course");
  });

  it("'bir aydır' opens the course follow-up and not the time-of-day one", () => {
    const month = after("month");
    expect(month).toContain("duration_course");
    expect(month).not.toContain("onset_today_when");
  });

  it("the two flows are genuinely different in both directions", () => {
    const today = after("today");
    const month = after("month");
    expect(today.filter((id) => !month.includes(id))).toEqual(["onset_today_when"]);
    expect(month.filter((id) => !today.includes(id))).toEqual(["duration_course"]);
  });

  it("with the duration unanswered, neither is on the frontier (a gate opens only on TRUE)", () => {
    const opening = ids(applicableQuestions(pack, [{ questionId: "complaint", values: ["pain"] }]));
    expect(opening).not.toContain("onset_today_when");
    expect(opening).not.toContain("duration_course");
  });

  it("every department pack carries the duration branch", () => {
    for (const branch of BRANCHES) {
      const branchPack = ids(packForDepartment(branch));
      expect(branchPack, branch).toContain("onset_today_when");
      expect(branchPack, branch).toContain("duration_course");
    }
  });
});

describe("the mode filter is the depth lever (02 §2: Hızlı short, Detaylı deep)", () => {
  /** The level-two department follow-ups — a gate on an already-gated step. */
  const DEEP = [
    "radiation_side",
    "breath_lying",
    "neuro_head_same",
    "ent_swallow",
    "ortho_spread_feel",
    "derm_itch_sleep",
    "gastro_bowel_relief",
  ];

  it("Hızlı asks one level of follow-up; Detaylı asks two", () => {
    for (const branch of BRANCHES) {
      const fast = ids(packForVisit(branch, HIZLI));
      const deep = ids(packForVisit(branch, DETAYLI));
      for (const id of DEEP) {
        if (deep.includes(id)) {
          expect(fast, `${branch}/${id}`).not.toContain(id);
        }
      }
    }
  });

  it("Hızlı is strictly shorter than Detaylı in every branch", () => {
    for (const branch of BRANCHES) {
      const fast = packForVisit(branch, HIZLI).length;
      const deep = packForVisit(branch, DETAYLI).length;
      expect(fast, branch).toBeLessThan(deep);
    }
  });

  it("Hızlı still branches — it is short, not flat", () => {
    const pack = packForVisit("Kardiyoloji", HIZLI);
    const pain = ids(applicableQuestions(pack, [{ questionId: "complaint", values: ["pain"] }]));
    const breath = ids(
      applicableQuestions(pack, [{ questionId: "complaint", values: ["dyspnoea"] }]),
    );
    expect(pain).not.toEqual(breath);
    expect(pain).toContain("pain_character");
    expect(breath).toContain("breath_timing");
  });

  it("Hızlı carries no base-layer question at all (02 §2 puts them in the detailed column)", () => {
    const fast = ids(packForVisit("Kardiyoloji", HIZLI));
    for (const q of [...baseLayerQuestions, ...measurementQuestions]) {
      expect(fast, q.id).not.toContain(q.id);
    }
  });
});

describe("the base layer branches on its own answers too", () => {
  const pack = packForVisit("Nöroloji", DETAYLI);

  it("an ex-smoker is asked when they stopped; a never-smoker is not", () => {
    const former = ids(applicableQuestions(pack, [{ questionId: "smoking", values: ["former"] }]));
    const never = ids(applicableQuestions(pack, [{ questionId: "smoking", values: ["never"] }]));
    expect(former).toContain("smoking_quit_when");
    expect(never).not.toContain("smoking_quit_when");
  });

  it("an injury reported opens the detail; none reported closes it", () => {
    const yes = ids(applicableQuestions(pack, [{ questionId: "injury_history", values: ["yes"] }]));
    const no = ids(applicableQuestions(pack, [{ questionId: "injury_history", values: ["no"] }]));
    expect(yes).toContain("injury_detail");
    expect(no).not.toContain("injury_detail");
  });

  it("no pain means no pain score", () => {
    const no = ids(applicableQuestions(pack, [{ questionId: "pain_present", values: ["no"] }]));
    expect(no).not.toContain("pain_score");
  });
});

// ---- the refusals, and the register --------------------------------------

describe("the base layer records; it never grades and never concludes", () => {
  const everyNew = [...baseLayerQuestions, ...measurementQuestions];

  it("no option is a severity word", () => {
    for (const q of everyNew) {
      for (const option of q.options ?? []) {
        expect(["mild", "moderate", "severe"], `${q.id}/${option.id}`).not.toContain(option.id);
      }
    }
  });

  it("every closed question offers an escape, or a free-text path out of it", () => {
    for (const q of everyNew) {
      if (q.kind !== "chips" && q.kind !== "single") {
        continue;
      }
      const optionIds = (q.options ?? []).map((o) => o.id);
      const escape = optionIds.some((id) =>
        ["other", "not_sure", "not_stated", "unknown", "none", "dont_remember"].includes(id),
      );
      const freeText = everyNew.some((x) => x.kind === "text" && x.askIf?.questionId === q.id);
      // Two exemptions, stated rather than silent. `pain_present` is the
      // schema's own bare Evet/Hayır and the whole pain block hangs off it,
      // so a third state there would be a state the source does not have.
      // `pain_score` is a closed numeric scale: "diğer" on a scale from zero
      // to ten is not a value, and adding a twelfth option would be
      // authoring the instrument.
      const numericScale = (q.options ?? []).every((o) => o.inline !== undefined);
      expect(escape || freeText || numericScale || q.id === "pain_present", q.id).toBe(true);
    }
  });

  it("every gate names an option of a question asked EARLIER in the composed pack", () => {
    const pack = packForVisit("Kardiyoloji", DETAYLI);
    pack.forEach((q, index) => {
      if (q.askIf === undefined) {
        return;
      }
      const gatingIndex = pack.findIndex((x) => x.id === q.askIf!.questionId);
      expect(gatingIndex, `${q.id} gates on ${q.askIf.questionId}`).toBeGreaterThanOrEqual(0);
      expect(gatingIndex, `${q.id} must follow ${q.askIf.questionId}`).toBeLessThan(index);
      const optionIds = (pack[gatingIndex].options ?? []).map((o) => o.id);
      for (const value of q.askIf.includesAny) {
        expect(optionIds, `${q.id} ← ${q.askIf.questionId}/${value}`).toContain(value);
      }
    });
  });

  it("every new string exists non-empty in tr AND en (invariant 5 — tr is the source)", () => {
    for (const key of newKeys()) {
      expect((tr as Record<string, string>)[key]?.trim(), `tr ${key}`).toBeTruthy();
      expect((en as Record<string, string>)[key]?.trim(), `en ${key}`).toBeTruthy();
    }
  });

  it("the register is siz throughout — never sen, never a bare 'sen' ending", () => {
    for (const key of newKeys()) {
      const text = (tr as Record<string, string>)[key];
      expect(text, `tr ${key}`).not.toMatch(/\bsen\b|\bsana\b|\bseni\b|\bsenin\b/i);
      expect(text, `tr ${key}`).not.toMatch(/\bmisin\?|\bmusun\?|\bm[ıi]s[ıi]n\?/);
    }
  });
});

function newKeys(): Set<string> {
  const keys = new Set<string>();
  for (const q of [...baseLayerQuestions, ...measurementQuestions]) {
    keys.add(q.titleKey);
    if (q.hintKey) {
      keys.add(q.hintKey);
    }
    if (q.lineLabelKey) {
      keys.add(q.lineLabelKey);
    }
    if (q.measure) {
      keys.add(q.measure.unitKey);
    }
    for (const option of q.options ?? []) {
      keys.add(option.labelKey);
    }
  }
  return keys;
}

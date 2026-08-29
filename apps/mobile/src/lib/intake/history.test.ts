/**
 * INT-256 — the universal history sections, and what they refuse to do.
 *
 * The owner asked for a complete pre-visit: "like allergy previous medicine
 * familial issues and so on", in both modes. Those are 04 §1 rows 5 and 6 —
 * `meds_allergies` and `pmh_fh_sh` — and they are QUESTIONS, not judgements.
 * Every assertion below is either about composition (does the block reach
 * every branch, in the right place, in the right mode) or about a refusal
 * (nothing graded, nothing inferred, nothing numeric, nothing carried in as
 * current). The guideline-grounded content is INT-043 → INT-044..051 and is
 * awaiting a physician (HB-C1); none of it is here.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { getTestAccount } from "../dev/accounts";
import { en } from "../i18n/en";
import { tr } from "../i18n/tr";
import type { FactDecision } from "./carriedFacts";
import { buildNote, emptyNoteState, noteReducer } from "./note";
import {
  allQuestions,
  applicableQuestions,
  historyQuestions,
  packForDepartment,
  packForVisit,
  FAMILY_HISTORY_DEFERRAL,
  PROTOCOL_SECTION_OF,
  type IntakeProfile,
  type IntakeQuestion,
} from "./questions";

const HIZLI: IntakeProfile = { mode: "hizli" };
const DETAYLI: IntakeProfile = { mode: "detayli" };

/** The ten branch names, one spelling each (questions.test.ts pins folding). */
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

// ---- composition: base.intake inherited by every branch --------------------

describe("the history block is composed onto every pack, never copied into it", () => {
  it("packForDepartment is untouched — the department packs stay HPI-only", () => {
    for (const branch of [...BRANCHES, "Aile Hekimliği"]) {
      for (const q of packForDepartment(branch)) {
        expect(q.section, `${branch}/${q.id}`).toBeUndefined();
      }
    }
  });

  it("every branch, and the no-department fallback, gets the history block", () => {
    for (const branch of [...BRANCHES, "Aile Hekimliği", undefined]) {
      const pack = ids(packForVisit(branch, DETAYLI));
      for (const q of historyQuestions) {
        expect(pack, `${branch}/${q.id}`).toContain(q.id);
      }
    }
  });

  it("history sits after the last department dimension and before the free note", () => {
    for (const branch of BRANCHES) {
      const pack = ids(packForVisit(branch, DETAYLI));
      const dimensions = ids(packForDepartment(branch)).filter((id) => id !== "extra");
      const firstHistory = pack.indexOf(historyQuestions[0].id);
      expect(pack[0], branch).toBe("complaint");
      expect(pack[pack.length - 1], branch).toBe("extra");
      for (const id of dimensions) {
        expect(pack.indexOf(id), `${branch}/${id}`).toBeLessThan(firstHistory);
      }
    }
  });

  it("allQuestions carries the history block once, in composed order", () => {
    const all = ids(allQuestions);
    expect(new Set(all).size).toBe(all.length);
    const composed = ids(packForVisit("Kardiyoloji", DETAYLI));
    const filtered = all.filter((id) => composed.includes(id));
    expect(filtered).toEqual(composed);
  });
});

// ---- 04 §1 sections, and the two modes -------------------------------------

describe("mode profiles (02 §2 — Hızlı confirms, Detaylı adds the deltas)", () => {
  it("Hızlı carries meds_allergies and never pmh_fh_sh", () => {
    const pack = packForVisit("Kardiyoloji", HIZLI);
    const sections = new Set(pack.map((q) => q.section).filter((s) => s !== undefined));
    expect(sections).toEqual(new Set(["meds_allergies"]));
  });

  it("Detaylı carries both history sections", () => {
    const pack = packForVisit("Kardiyoloji", DETAYLI);
    const sections = new Set(pack.map((q) => q.section).filter((s) => s !== undefined));
    expect(sections).toEqual(new Set(["meds_allergies", "pmh_fh_sh"]));
  });

  it("Hızlı costs exactly three unconditional history turns (02 §2 budget)", () => {
    const opening = applicableQuestions(packForVisit("Kardiyoloji", HIZLI), []).filter(
      (q) => q.section !== undefined,
    );
    expect(ids(opening)).toEqual(["allergy_known", "meds_other", "meds_otc"]);
  });

  it("Detaylı opens with seven — the same three plus the four delta openers", () => {
    const opening = applicableQuestions(packForVisit("Kardiyoloji", DETAYLI), []).filter(
      (q) => q.section !== undefined,
    );
    expect(ids(opening)).toEqual([
      "allergy_known",
      "meds_other",
      "meds_otc",
      "pmh_known",
      "pmh_surgery",
      "pmh_recent_change",
      "fh_known",
    ]);
  });
});

// ---- 02 §33: family history is the second deferral consumer ----------------

describe("the environment self-check can defer family history (02 §33)", () => {
  const notPrivate: IntakeProfile = {
    mode: "detayli",
    deferred: [FAMILY_HISTORY_DEFERRAL],
  };

  it("a deferred section is absent from the flow — not asked quieter, not asked", () => {
    const pack = ids(packForVisit("Nöroloji", notPrivate));
    expect(pack).not.toContain("fh_known");
    expect(pack).not.toContain("fh_who");
    expect(pack).not.toContain("fh_detail");
  });

  it("the rest of the history block is untouched by the deferral", () => {
    const pack = ids(packForVisit("Nöroloji", notPrivate));
    expect(pack).toContain("allergy_known");
    expect(pack).toContain("pmh_known");
  });

  it("the privacy answer defers family history alongside wellbeing", () => {
    let s = noteReducer(emptyNoteState(), { type: "mode", mode: "detayli" });
    s = noteReducer(s, { type: "privacy", alone: false });
    expect(s.deferred).toEqual(["wellbeing", "family_history"]);
    s = noteReducer(s, { type: "privacy", alone: true });
    expect(s.deferred).toEqual([]);
  });

  it("the note carries the family-history deferral with the verbatim marker", () => {
    const sections = buildNote([], { carriedFacts: [] }, null, [FAMILY_HISTORY_DEFERRAL]);
    const deferred = sections.find((s) => s.id === "deferred")!;
    expect(deferred.lines).toEqual(["Aile öyküsü — eksik: ortam uygun değildi"]);
  });
});

// ---- gates: structurally obvious only, and never across sections -----------

/** Gate-chain depth: 0 = ungated, 1 = gated on an ungated question, … */
function gateDepth(questionId: string, seen: Set<string> = new Set()): number {
  const question = allQuestions.find((q) => q.id === questionId);
  if (question?.askIf === undefined || seen.has(questionId)) {
    return 0;
  }
  seen.add(questionId);
  return 1 + gateDepth(question.askIf.questionId, seen);
}

describe("history gates ask for a further detail, and nothing else", () => {
  it("a history gate never reads a question outside its own section", () => {
    for (const q of historyQuestions) {
      if (q.askIf === undefined) {
        continue;
      }
      const gating = historyQuestions.find((x) => x.id === q.askIf!.questionId);
      expect(gating, `${q.id} gates on ${q.askIf.questionId}`).toBeDefined();
      expect(gating!.section, q.id).toBe(q.section);
    }
  });

  it("no history question is gated on the chief complaint — history is universal", () => {
    for (const q of historyQuestions) {
      expect(q.askIf?.questionId, q.id).not.toBe("complaint");
    }
  });

  it("each 'is there one?' opener carries a chain two gates deep", () => {
    // allergy_known → allergy_kind → allergy_detail
    // pmh_known     → pmh_conditions → pmh_other_detail
    // fh_known      → fh_who → fh_detail
    const deep = historyQuestions.filter((q) => gateDepth(q.id) >= 2).map((q) => q.id);
    expect(deep).toEqual(["allergy_detail", "pmh_other_detail", "fh_detail"]);
  });

  it("the flat follow-ups are one gate deep, on their own opener", () => {
    const one = historyQuestions.filter((q) => gateDepth(q.id) === 1).map((q) => q.id);
    expect(one).toEqual([
      "allergy_kind",
      "allergy_reaction",
      "meds_other_detail",
      "meds_otc_detail",
      "pmh_conditions",
      "pmh_surgery_detail",
      "pmh_recent_detail",
      "fh_who",
    ]);
  });

  it("answering the chain opens the detail, and changing it closes it again", () => {
    const pack = packForVisit("Kardiyoloji", HIZLI);
    const none = ids(applicableQuestions(pack, [{ questionId: "allergy_known", values: ["no"] }]));
    expect(none).not.toContain("allergy_kind");
    expect(none).not.toContain("allergy_detail");

    const yes = ids(applicableQuestions(pack, [{ questionId: "allergy_known", values: ["yes"] }]));
    expect(yes).toContain("allergy_kind");
    expect(yes).toContain("allergy_reaction");
    expect(yes).not.toContain("allergy_detail");

    const named = ids(
      applicableQuestions(pack, [
        { questionId: "allergy_known", values: ["yes"] },
        { questionId: "allergy_kind", values: ["medicine"] },
      ]),
    );
    expect(named).toContain("allergy_detail");
  });
});

// ---- the refusals: nothing graded, nothing concluded, nothing numeric ------

describe("the history block records; it never concludes", () => {
  it("no history question offers a severity grade", () => {
    const graded = new Set(["mild", "moderate", "severe"]);
    for (const q of historyQuestions) {
      for (const option of q.options ?? []) {
        expect(graded.has(option.id), `${q.id}/${option.id}`).toBe(false);
      }
    }
  });

  it("no history question feeds an HPI line — each renders in its own section", () => {
    for (const q of historyQuestions) {
      expect(q.hpiLabelKey, q.id).toBeUndefined();
      expect(q.lineLabelKey, q.id).toBeDefined();
      expect(q.section, q.id).toBeDefined();
    }
  });

  it("every closed question offers an escape: 'other', 'not sure' or a free-text path", () => {
    for (const q of historyQuestions) {
      if (q.kind === "text") {
        continue;
      }
      const optionIds = (q.options ?? []).map((o) => o.id);
      const escape = optionIds.some((id) => ["other", "not_sure", "dont_remember"].includes(id));
      const freeText = historyQuestions.some(
        (x) => x.kind === "text" && x.askIf?.questionId === q.id,
      );
      expect(escape || freeText, q.id).toBe(true);
    }
  });
});

describe("invariant 22 — no free numeric entry on the clinical critical path", () => {
  const CLINICAL_PATH = [
    join(__dirname, "..", "..", "app", "(tabs)", "visits", "[visitId]", "intake.tsx"),
    join(__dirname, "..", "..", "components", "DialogueIntake.tsx"),
  ];

  it("the pack model has no numeric question kind at all", () => {
    for (const q of allQuestions) {
      expect(["chips", "single", "text"], q.id).toContain(q.kind);
    }
  });

  it("no clinical-path screen asks the keyboard for digits", () => {
    for (const path of CLINICAL_PATH) {
      const source = readFileSync(path, "utf8");
      expect(source, path).not.toMatch(/keyboardType/);
      expect(source, path).not.toMatch(/inputMode/);
    }
  });

  it("a dose is asked as words: the medication detail step is a text question", () => {
    const detail = historyQuestions.find((q) => q.id === "meds_other_detail")!;
    expect(detail.kind).toBe("text");
    expect(detail.options).toBeUndefined();
  });

  it("no history string, tr or en, contains a numeral", () => {
    for (const key of historyKeys()) {
      expect((tr as Record<string, string>)[key], `tr ${key}`).not.toMatch(/[0-9]/);
      expect((en as Record<string, string>)[key], `en ${key}`).not.toMatch(/[0-9]/);
    }
  });

  it("every history string exists non-empty in tr AND en (tr is the source of truth)", () => {
    for (const key of historyKeys()) {
      expect((tr as Record<string, string>)[key]?.trim(), `tr ${key}`).toBeTruthy();
      expect((en as Record<string, string>)[key]?.trim(), `en ${key}`).toBeTruthy();
    }
  });
});

function historyKeys(): Set<string> {
  const keys = new Set<string>();
  for (const q of historyQuestions) {
    keys.add(q.titleKey);
    if (q.hintKey) {
      keys.add(q.hintKey);
    }
    if (q.lineLabelKey) {
      keys.add(q.lineLabelKey);
    }
    for (const option of q.options ?? []) {
      keys.add(option.labelKey);
    }
  }
  return keys;
}

// ---- the note: four sections, ids from files/04 §5 PreVisitNote ------------

describe("the note renders the history in the schema's own sections", () => {
  const answers = [
    { questionId: "complaint", values: ["pain"] },
    { questionId: "duration", values: ["days"] },
    { questionId: "allergy_known", values: ["yes"] },
    { questionId: "allergy_kind", values: ["medicine"] },
    { questionId: "allergy_detail", values: ["Penisilin iğnesi"] },
    { questionId: "meds_otc", values: ["yes"] },
    { questionId: "pmh_known", values: ["yes"] },
    { questionId: "pmh_conditions", values: ["diabetes"] },
    { questionId: "fh_known", values: ["yes"] },
    { questionId: "fh_who", values: ["mother"] },
  ];

  it("uses the PreVisitNote ids of files/04 §5, in that file's own order", () => {
    const sections = buildNote(answers, { carriedFacts: [] }).map((s) => s.id);
    expect(sections).toEqual([
      "chief_complaint",
      "hpi",
      "pmh",
      "medications",
      "allergies",
      "family_social",
    ]);
  });

  it("renders labelled lines, in the composed question order", () => {
    const sections = buildNote(answers, { carriedFacts: [] });
    expect(sections.find((s) => s.id === "allergies")!.lines).toEqual([
      "Bilinen alerji: Evet",
      "Alerji türü: İlaç",
      "Alerji ayrıntısı: Penisilin iğnesi",
    ]);
    // The OTC answer is a medication fact, so it files under medications —
    // `meds_allergies` is one protocol section and two note sections.
    expect(sections.find((s) => s.id === "medications")!.lines).toEqual([
      "Reçetesiz ya da bitkisel ürün: Evet",
    ]);
    expect(sections.find((s) => s.id === "family_social")!.lines).toEqual([
      "Ailede bilinen hastalık: Evet",
      "Yakınlık derecesi: Anne",
    ]);
  });

  it("the two vocabularies agree: every question's note section maps to its protocol section", () => {
    for (const q of historyQuestions) {
      expect(q.noteSection, q.id).toBeDefined();
      expect(PROTOCOL_SECTION_OF[q.noteSection!], q.id).toBe(q.section);
    }
  });

  it("an unanswered section produces no section at all", () => {
    const sections = buildNote([{ questionId: "complaint", values: ["pain"] }], {
      carriedFacts: [],
    }).map((s) => s.id);
    expect(sections).not.toContain("allergies");
    expect(sections).not.toContain("pmh");
    expect(sections).not.toContain("family_social");
  });
});

// ---- INT-247 consumed: a carried allergy is not a current allergy ----------

const ayse = getTestAccount("ayse")!;
const AYSE_ALLERGY = "cf-ayse-penisilin";
const AYSE_ALLERGY_TEXT = "Penisilin (deri döküntüsü)";

const patientNow: FactDecision = {
  outcome: "confirmed",
  by: { role: "patient", attribution: "self_report" },
  at: "2026-08-29",
};

describe("a carried allergy arrives UNCONFIRMED (invariant 12, INT-247)", () => {
  const answers = [{ questionId: "complaint", values: ["pain"] }];

  it("the fixture carries one, and it is an allergy, not a medication", () => {
    const fact = ayse.carriedFacts.find((f) => f.id === AYSE_ALLERGY)!;
    expect(fact.kind).toBe("allergy");
    expect(fact.text).toBe(AYSE_ALLERGY_TEXT);
  });

  it("it never lands in the medications section", () => {
    const meds = buildNote(answers, ayse).find((s) => s.id === "medications")!;
    expect(meds.lines.join(" ")).not.toContain(AYSE_ALLERGY_TEXT);
  });

  it("it is NOT printed as a current allergy — the bare text is not a line", () => {
    const allergies = buildNote(answers, ayse).find((s) => s.id === "allergies")!;
    expect(allergies.lines).not.toContain(AYSE_ALLERGY_TEXT);
  });

  it("it is shown, marked unconfirmed, with the earlier record's date", () => {
    const allergies = buildNote(answers, ayse).find((s) => s.id === "allergies")!;
    const line = allergies.lines.join(" ");
    expect(line).toContain(AYSE_ALLERGY_TEXT);
    expect(line).toContain("bu ziyarette onaylanmadı");
    expect(line).toContain("önceki kayıt");
  });

  it("confirming for this visit is what makes it current", () => {
    const allergies = buildNote(answers, ayse, null, [], { [AYSE_ALLERGY]: patientNow })!.find(
      (s) => s.id === "allergies",
    )!;
    const line = allergies.lines.join(" ");
    expect(line).not.toContain("bu ziyarette onaylanmadı");
    expect(line).toContain("hasta bu ziyarette doğruladı");
  });

  it("retracting it says so — an allergy is never 'stopped' like a medicine", () => {
    const retracted: FactDecision = {
      outcome: "stopped",
      by: { role: "patient", attribution: "self_report" },
      at: "2026-08-29",
    };
    const line = buildNote(answers, ayse, null, [], { [AYSE_ALLERGY]: retracted })!
      .find((s) => s.id === "allergies")!
      .lines.join(" ");
    expect(line).toContain("hasta böyle bir alerjisi olmadığını söyledi");
    expect(line).not.toContain("bıraktığını");
  });
});

// ---- the owner's complaint, restated at the section level ------------------

describe("two chief complaints in one department still ask different questions", () => {
  it("the history block is identical; only the HPI dimensions diverge", () => {
    const pack = packForVisit("Göğüs Hastalıkları", DETAYLI);
    const seq = (complaint: string) =>
      ids(applicableQuestions(pack, [{ questionId: "complaint", values: [complaint] }]));
    const breathless = seq("dyspnoea");
    const fever = seq("fever");

    expect(breathless).not.toEqual(fever);
    expect(breathless.filter((id) => !fever.includes(id))).toEqual(["breath_timing"]);
    expect(fever.filter((id) => !breathless.includes(id))).toEqual(["fever_pattern"]);

    const history = historyQuestions.filter((q) => q.askIf === undefined).map((q) => q.id);
    for (const id of history) {
      expect(breathless, id).toContain(id);
      expect(fever, id).toContain(id);
    }
  });
});

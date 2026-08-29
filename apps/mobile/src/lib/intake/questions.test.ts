import { describe, expect, it } from "vitest";

import { en } from "../i18n/en";
import { tr } from "../i18n/tr";
import {
  allQuestions,
  applicableQuestions,
  missingQuestions,
  nextApplicableQuestion,
  optionLabelKey,
  packForDepartment,
  type AskIf,
  type IntakeQuestion,
} from "./questions";

/**
 * Department strings exactly as visits carry them (MHRS-style, Turkish
 * diacritics included) → a question id that only that branch's pack asks.
 * Resolution goes through foldDepartment, so each row also pins the
 * diacritic folding for that department name.
 */
const RESOLUTION: { department: string; marker: string }[] = [
  { department: "Kardiyoloji", marker: "radiation" },
  { department: "İç Hastalıkları", marker: "radiation" },
  { department: "Nöroloji", marker: "neuro_assoc" },
  { department: "Kulak Burun Boğaz", marker: "ent_assoc" },
  { department: "Ortopedi ve Travmatoloji", marker: "ortho_region" },
  { department: "Dermatoloji", marker: "derm_character" },
  { department: "Cildiye", marker: "derm_character" },
  { department: "Göğüs Hastalıkları", marker: "pulmo_character" },
  { department: "Kadın Hastalıkları ve Doğum", marker: "gyn_cycle" },
  { department: "Jinekoloji", marker: "gyn_cycle" },
  { department: "Üroloji", marker: "uro_urination" },
  { department: "Göz Hastalıkları", marker: "eye_vision" },
  { department: "Gastroenteroloji", marker: "gastro_meal" },
  { department: "Sindirim Sistemi Hastalıkları", marker: "gastro_meal" },
];

/** One pack per branch, deduped by reference (spellings share the array). */
function branchPacks(): IntakeQuestion[][] {
  return [...new Set(RESOLUTION.map((row) => packForDepartment(row.department)))];
}

describe("packForDepartment resolution", () => {
  for (const { department, marker } of RESOLUTION) {
    it(`"${department}" resolves to the pack asking ${marker}`, () => {
      const pack = packForDepartment(department);
      expect(pack.map((q) => q.id)).toContain(marker);
    });
  }

  it("unknown or missing departments fall back to the general pack", () => {
    const general = packForDepartment(undefined);
    expect(general.map((q) => q.id)).toEqual(["complaint", "duration", "extra"]);
    expect(packForDepartment("Aile Hekimliği")).toBe(general);
  });

  it("covers ten distinct branch packs", () => {
    expect(branchPacks()).toHaveLength(10);
  });
});

describe("pack shape invariants", () => {
  const packs = branchPacks();

  it("every branch pack has 9–13 steps, opens with the complaint, closes with the free note", () => {
    for (const pack of packs) {
      expect(pack.length).toBeGreaterThanOrEqual(9);
      expect(pack.length).toBeLessThanOrEqual(13);
      expect(pack[0].id).toBe("complaint");
      expect(pack[pack.length - 1].id).toBe("extra");
    }
  });

  it("no branch pack is a fixed-length flow — every one carries answer-gated depth", () => {
    for (const pack of packs) {
      const base = applicableQuestions(pack, []).length;
      // Unanswered gates stay shut, so the opening flow is strictly shorter
      // than the pack: the length is decided by the answers, not the file.
      expect(base, pack.map((q) => q.id).join(",")).toBeLessThan(pack.length);
      expect(base).toBeGreaterThanOrEqual(7);
    }
  });

  it("every non-text question carries at least two options, all resolvable via optionLabelKey", () => {
    for (const pack of packs) {
      for (const q of pack) {
        if (q.kind === "text") {
          continue;
        }
        expect(q.options, q.id).toBeDefined();
        expect(q.options!.length, q.id).toBeGreaterThanOrEqual(2);
        for (const option of q.options!) {
          expect(optionLabelKey(q.id, option.id), `${q.id}/${option.id}`).toBe(option.labelKey);
        }
      }
    }
  });

  it("every dimension question carries hpiLabelKey (complaint feeds the CC section, extra the patient-note line)", () => {
    for (const pack of packs) {
      for (const q of pack) {
        if (q.id === "complaint" || q.id === "extra") {
          continue;
        }
        expect(q.hpiLabelKey, q.id).toBeDefined();
      }
    }
  });

  it("every chips question explains multi-select via a hint", () => {
    for (const pack of packs) {
      for (const q of pack) {
        if (q.kind === "chips") {
          expect(q.hintKey, q.id).toBeDefined();
        }
      }
    }
  });

  it("severity is asked in words in every branch pack", () => {
    for (const pack of packs) {
      const severity = pack.find((q) => q.id === "severity");
      expect(severity).toBeDefined();
      expect(severity!.options!.map((o) => o.id)).toEqual(["mild", "moderate", "severe"]);
    }
  });
});

describe("catalog coverage and invariant 22 (no numerals)", () => {
  function referencedKeys(): Set<string> {
    const keys = new Set<string>();
    for (const pack of [...branchPacks(), packForDepartment(undefined)]) {
      for (const q of pack) {
        keys.add(q.titleKey);
        if (q.hintKey) {
          keys.add(q.hintKey);
        }
        if (q.hpiLabelKey) {
          keys.add(q.hpiLabelKey);
        }
        for (const option of q.options ?? []) {
          keys.add(option.labelKey);
        }
      }
    }
    return keys;
  }

  it("every referenced key exists non-empty in tr AND en (tr is the source of truth)", () => {
    for (const key of referencedKeys()) {
      expect((tr as Record<string, string>)[key]?.trim(), `tr ${key}`).toBeTruthy();
      expect((en as Record<string, string>)[key]?.trim(), `en ${key}`).toBeTruthy();
    }
  });

  it("no numeral characters in any pack-facing string — invariant 22", () => {
    for (const key of referencedKeys()) {
      expect((tr as Record<string, string>)[key], `tr ${key}`).not.toMatch(/[0-9]/);
      expect((en as Record<string, string>)[key], `en ${key}`).not.toMatch(/[0-9]/);
    }
  });
});

// ---- INT-236/239: answer-dependent flow — askIf gates mirroring the DSL ----

describe("askIf gates (INT-236/239 — serializable data, mirroring dsl.py ask_if)", () => {
  /**
   * Exactly the structurally-obvious gates, nothing else: every gate below
   * asks for a further detail of something the patient has ALREADY named —
   * the character of the pain they reported, the side the spreading they
   * reported goes to, what happens when they swallow given they placed the
   * pain in the throat. No gate encodes danger, severity or a threshold;
   * those belong to the physician-gated compiled packs (INT-057/041/096).
   */
  const GATES: Record<string, AskIf> = {
    // level one — gated on the opening complaint
    pain_character: { questionId: "complaint", includesAny: ["pain"] },
    radiation: { questionId: "complaint", includesAny: ["pain"] },
    breath_timing: { questionId: "complaint", includesAny: ["dyspnoea"] },
    neuro_head_side: { questionId: "complaint", includesAny: ["headache"] },
    neuro_character: { questionId: "complaint", includesAny: ["pain", "headache"] },
    ent_pain_where: { questionId: "complaint", includesAny: ["pain"] },
    gyn_pain_where: { questionId: "complaint", includesAny: ["pain"] },
    gastro_meal: { questionId: "complaint", includesAny: ["stomach"] },
    gastro_bowel: { questionId: "complaint", includesAny: ["stomach"] },
    derm_fever_order: { questionId: "complaint", includesAny: ["fever"] },
    fever_pattern: { questionId: "complaint", includesAny: ["fever"] },
    eye_headache_link: { questionId: "complaint", includesAny: ["headache"] },
    // level one — gated on an ungated dimension the patient just described
    ortho_fall_how: { questionId: "ortho_mechanism", includesAny: ["fall"] },
    ortho_spread: { questionId: "ortho_region", includesAny: ["low_back", "neck"] },
    derm_itch_when: { questionId: "derm_character", includesAny: ["itchy"] },
    eye_pain_move: { questionId: "eye_character", includesAny: ["pain"] },
    cardio_palpitation: { questionId: "associated", includesAny: ["palpitations"] },
    neuro_numb_where: { questionId: "neuro_assoc", includesAny: ["numbness"] },
    ent_hear_side: { questionId: "ent_assoc", includesAny: ["hearing"] },
    uro_flank_side: { questionId: "uro_assoc", includesAny: ["flank_pain"] },
    // level two — gated on a question that is itself gated
    radiation_side: { questionId: "radiation", includesAny: ["arm", "jaw_neck", "back"] },
    breath_lying: { questionId: "breath_timing", includesAny: ["lying"] },
    neuro_head_same: { questionId: "neuro_head_side", includesAny: ["one_side"] },
    ent_swallow: { questionId: "ent_pain_where", includesAny: ["throat"] },
    ortho_spread_feel: { questionId: "ortho_spread", includesAny: ["arm", "leg"] },
    derm_itch_sleep: { questionId: "derm_itch_when", includesAny: ["night"] },
    gastro_bowel_relief: {
      questionId: "gastro_bowel",
      includesAny: ["constipation", "diarrhea", "alternating"],
    },
  };

  it("exactly the declared structurally-obvious gates exist — nothing else is gated", () => {
    for (const q of allQuestions) {
      if (q.id in GATES) {
        expect(q.askIf, q.id).toEqual(GATES[q.id]);
      } else {
        expect(q.askIf, q.id).toBeUndefined();
      }
    }
  });

  it("askIf is data, never a function — it survives a JSON round-trip (DSL parity)", () => {
    for (const q of allQuestions.filter((x) => x.askIf !== undefined)) {
      expect(JSON.parse(JSON.stringify(q.askIf)), q.id).toEqual(q.askIf);
    }
  });

  it("every gate names a real question, a real option of it, and never itself", () => {
    for (const q of allQuestions) {
      if (q.askIf === undefined) {
        continue;
      }
      expect(q.askIf.questionId, q.id).not.toBe(q.id);
      const gating = allQuestions.find((x) => x.id === q.askIf!.questionId);
      expect(gating, `${q.id} gates on ${q.askIf.questionId}`).toBeDefined();
      const optionIds = (gating!.options ?? []).map((o) => o.id);
      for (const value of q.askIf.includesAny) {
        expect(optionIds, `${q.id} ← ${gating!.id}/${value}`).toContain(value);
      }
    }
  });

  it("gates are stratified: a gate only ever looks backwards inside its own pack", () => {
    for (const pack of branchPacks()) {
      pack.forEach((q, index) => {
        if (q.askIf === undefined) {
          return;
        }
        const gatingIndex = pack.findIndex((x) => x.id === q.askIf!.questionId);
        expect(gatingIndex, `${q.id} in pack`).toBeGreaterThanOrEqual(0);
        expect(gatingIndex, `${q.id} must follow ${q.askIf.questionId}`).toBeLessThan(index);
      });
    }
  });
});

// ---- INT-239: the flow is answer-driven, not a fixed nine ------------------

/** Gate-chain depth: 0 = ungated, 1 = gated on an ungated question, … */
function gateDepth(questionId: string, seen: Set<string> = new Set()): number {
  const question = allQuestions.find((q) => q.id === questionId);
  if (question?.askIf === undefined || seen.has(questionId)) {
    return 0;
  }
  seen.add(questionId);
  return 1 + gateDepth(question.askIf.questionId, seen);
}

describe("branching depth (INT-239)", () => {
  it("at least four branch packs carry a level-two follow-up (a gate on a gated question)", () => {
    const deep = branchPacks().filter((pack) => pack.some((q) => gateDepth(q.id) >= 2));
    expect(deep.length).toBeGreaterThanOrEqual(4);
  });

  it("the depth-two follow-ups are reachable: answering the chain opens them", () => {
    const cardio = packForDepartment("Kardiyoloji");
    const shallow = applicableQuestions(cardio, [
      { questionId: "complaint", values: ["pain"] },
    ]).map((q) => q.id);
    expect(shallow).toContain("radiation");
    expect(shallow).not.toContain("radiation_side");
    const deep = applicableQuestions(cardio, [
      { questionId: "complaint", values: ["pain"] },
      { questionId: "radiation", values: ["arm"] },
    ]).map((q) => q.id);
    expect(deep).toContain("radiation_side");
  });

  it("a level-two follow-up closes again when its parent answer changes", () => {
    const cardio = packForDepartment("Kardiyoloji");
    const ids = applicableQuestions(cardio, [
      { questionId: "complaint", values: ["pain"] },
      { questionId: "radiation", values: ["no_radiation"] },
    ]).map((q) => q.id);
    expect(ids).not.toContain("radiation_side");
  });
});

/**
 * The owner-visible proof: inside ONE department, two different opening
 * answers produce two different question sequences. `onlyA`/`onlyB` are the
 * exact symmetric difference — a rename or a lost gate fails the row.
 */
const DIVERGENCE: {
  department: string;
  a: string[];
  b: string[];
  onlyA: string[];
  onlyB: string[];
}[] = [
  {
    department: "Kardiyoloji",
    a: ["pain"],
    b: ["dyspnoea"],
    onlyA: ["pain_character", "radiation"],
    onlyB: ["breath_timing"],
  },
  {
    department: "Göğüs Hastalıkları",
    a: ["dyspnoea"],
    b: ["fever"],
    onlyA: ["breath_timing"],
    onlyB: ["fever_pattern"],
  },
  {
    department: "Gastroenteroloji",
    a: ["stomach"],
    b: ["fever"],
    onlyA: ["gastro_meal", "gastro_bowel"],
    onlyB: ["fever_pattern"],
  },
  {
    department: "Nöroloji",
    a: ["headache"],
    b: ["fatigue"],
    onlyA: ["neuro_head_side", "neuro_character"],
    onlyB: [],
  },
  {
    department: "Kulak Burun Boğaz",
    a: ["pain"],
    b: ["cough"],
    onlyA: ["ent_pain_where"],
    onlyB: [],
  },
  {
    department: "Ortopedi ve Travmatoloji",
    a: ["pain"],
    b: ["fatigue"],
    onlyA: ["pain_character"],
    onlyB: [],
  },
  { department: "Dermatoloji", a: ["fever"], b: ["other"], onlyA: ["derm_fever_order"], onlyB: [] },
  { department: "Üroloji", a: ["fever"], b: ["pain"], onlyA: ["fever_pattern"], onlyB: [] },
  {
    department: "Göz Hastalıkları",
    a: ["headache"],
    b: ["pain"],
    onlyA: ["eye_headache_link"],
    onlyB: [],
  },
  {
    department: "Kadın Hastalıkları ve Doğum",
    a: ["pain"],
    b: ["fever"],
    onlyA: ["gyn_pain_where", "pain_character"],
    onlyB: [],
  },
];

describe("the asked set differs by first answer (INT-239 — the owner's complaint)", () => {
  it("covers well over the four departments the acceptance asks for", () => {
    expect(DIVERGENCE.length).toBeGreaterThanOrEqual(4);
  });

  for (const { department, a, b, onlyA, onlyB } of DIVERGENCE) {
    it(`${department}: "${a.join("+")}" and "${b.join("+")}" ask different questions`, () => {
      const pack = packForDepartment(department);
      const seqA = applicableQuestions(pack, [{ questionId: "complaint", values: a }]).map(
        (q) => q.id,
      );
      const seqB = applicableQuestions(pack, [{ questionId: "complaint", values: b }]).map(
        (q) => q.id,
      );
      expect(seqA).not.toEqual(seqB);
      expect(seqA.filter((id) => !seqB.includes(id))).toEqual(onlyA);
      expect(seqB.filter((id) => !seqA.includes(id))).toEqual(onlyB);
    });
  }

  it("three departments diverge in BOTH directions — neither flow is a prefix of the other", () => {
    const both = DIVERGENCE.filter((row) => row.onlyA.length > 0 && row.onlyB.length > 0);
    expect(both.length).toBeGreaterThanOrEqual(3);
  });
});

describe("applicableQuestions (skip unmet gates; re-evaluate as answers change)", () => {
  const cardio = packForDepartment("Kardiyoloji");
  const gastro = packForDepartment("Gastroenteroloji");

  it("with no answers, gated questions are not applicable yet — dynamic denominator", () => {
    expect(applicableQuestions(cardio, []).map((q) => q.id)).toEqual([
      "complaint",
      "duration",
      "onset",
      "trigger",
      "associated",
      "severity",
      "extra",
    ]);
  });

  it("a complaint including pain reveals pain_character and radiation, in pack order", () => {
    const answers = [{ questionId: "complaint", values: ["pain"] }];
    expect(applicableQuestions(cardio, answers).map((q) => q.id)).toEqual([
      "complaint",
      "duration",
      "onset",
      "pain_character",
      "radiation",
      "trigger",
      "associated",
      "severity",
      "extra",
    ]);
  });

  it("a stomach complaint in the gastro pack reveals the meal and bowel dimensions", () => {
    const answers = [{ questionId: "complaint", values: ["stomach", "fatigue"] }];
    const ids = applicableQuestions(gastro, answers).map((q) => q.id);
    expect(ids).toContain("gastro_meal");
    expect(ids).toContain("gastro_bowel");
  });

  it("an edit that unmets the gate hides the question again — its answer is kept upstream", () => {
    const answered = [
      { questionId: "complaint", values: ["pain"] },
      { questionId: "pain_character", values: ["pressure"] },
    ];
    expect(applicableQuestions(cardio, answered).map((q) => q.id)).toContain("pain_character");
    const edited = [
      { questionId: "complaint", values: ["fever"] },
      { questionId: "pain_character", values: ["pressure"] },
    ];
    expect(applicableQuestions(cardio, edited).map((q) => q.id)).not.toContain("pain_character");
  });
});

describe("nextApplicableQuestion (the flow's single advance rule)", () => {
  const cardio = packForDepartment("Kardiyoloji");

  it("skips both gated questions after onset when the complaint is not pain", () => {
    const answers = [{ questionId: "complaint", values: ["fever"] }];
    expect(nextApplicableQuestion(cardio, answers, "onset")?.id).toBe("trigger");
  });

  it("walks into the gated question when the gate is met", () => {
    const answers = [{ questionId: "complaint", values: ["pain"] }];
    expect(nextApplicableQuestion(cardio, answers, "onset")?.id).toBe("pain_character");
  });

  it("returns null after the closing free note", () => {
    expect(nextApplicableQuestion(cardio, [], "extra")).toBeNull();
  });
});

describe("missingQuestions (checkpoint eksik list — applicable and unanswered only)", () => {
  const gastro = packForDepartment("Gastroenteroloji");

  it("lists the applicable questions without a contentful answer, in pack order", () => {
    const answers = [
      { questionId: "complaint", values: ["stomach"] },
      { questionId: "duration", values: ["week"] },
      { questionId: "gastro_location", values: [""] },
    ];
    expect(missingQuestions(gastro, answers).map((q) => q.id)).toEqual([
      "gastro_location",
      "gastro_character",
      "gastro_meal",
      "gastro_bowel",
      "gastro_assoc",
      "severity",
      "extra",
    ]);
  });

  it("never lists a question whose gate is unmet — skipped is not missing", () => {
    const answers = [{ questionId: "complaint", values: ["fever"] }];
    const ids = missingQuestions(gastro, answers).map((q) => q.id);
    expect(ids).not.toContain("gastro_meal");
    expect(ids).not.toContain("gastro_bowel");
  });
});

describe("allQuestions ordering (the note builder renders HPI lines in this order)", () => {
  it("contains every pack question exactly once", () => {
    const ids = allQuestions.map((q) => q.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const pack of [...branchPacks(), packForDepartment(undefined)]) {
      for (const q of pack) {
        expect(ids, q.id).toContain(q.id);
      }
    }
  });

  it("preserves each pack's own question order, so HPI lines follow the interview", () => {
    for (const pack of [...branchPacks(), packForDepartment(undefined)]) {
      const packIds = new Set(pack.map((q) => q.id));
      const filtered = allQuestions.filter((q) => packIds.has(q.id)).map((q) => q.id);
      expect(filtered).toEqual(pack.map((q) => q.id));
    }
  });
});

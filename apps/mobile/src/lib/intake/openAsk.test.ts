/**
 * INT-286 — how a question is ASKED, declared on the pack.
 *
 * The owner's report, verbatim: *"still ... it goes completly written and
 * option based but should be voice and open end questios (still with the
 * dyanmicness and standardized versions) as much as possible"*, against a
 * photograph of "Nefes darlığınız ne zaman oluyor?" rendered as a title over
 * two tappable cards.
 *
 * The parenthesis is half the requirement and it is what these tests hold:
 * the patient answers in their OWN WORDS, and the answer still lands on the
 * SAME standardised value a clinician reads and a gate branches on. So the
 * option list is not deleted — it stops being the interaction and becomes
 * three other things: the value space extraction resolves onto, the spoken
 * confirmation read-back, and the typed fallback.
 *
 * Three refusals are TYPE-LEVEL, each with a control that must fail to
 * compile. `@ts-expect-error` is the assertion: if the refused shape ever
 * becomes constructible, `tsc --noEmit` fails on an unused directive, which
 * is `pnpm -r typecheck` in `make check`.
 */
import { describe, expect, it } from "vitest";

import {
  allQuestions,
  askIfMet,
  isOpenAsk,
  missingQuestions,
  packForVisit,
  type AnsweredValues,
  type IntakeQuestion,
} from "./questions";

/** Every step that has an option list — the ones an ask style applies to. */
const choiceQuestions = allQuestions.filter((q) => q.kind === "chips" || q.kind === "single");

/**
 * The closed set, pinned by exact equality, with the reason each member is
 * not asked in the patient's own words. Three reasons, and no fourth:
 *
 * 1. `delivery` is not `voice`. files/13 §13 puts substance use in
 *    `text_first` and the numeral-bearing pain score in `text_only`
 *    precisely so the answer does not travel on the voice channel; an open
 *    ask makes speaking the primary act, which is the thing that section
 *    exists to prevent. This one is also refused by the type.
 * 2. An enumerated condition CHECKLIST. files/13 §4 quotes Bent et al.,
 *    *Ann Intern Med* 2006 (randomised, N = 214): a 53-item checklist
 *    elicited 238 adverse events in 77 % of patients; an open-ended
 *    question elicited 11, in 14 %, p < 0.001. Converting a named-condition
 *    checklist to an open question is a measured loss, not a style choice.
 * 3. The question itself names the list — "hangisi en iyi anlatıyor" — so
 *    an open form would need new scripted text, and invariant 10 makes
 *    rewriting a scripted question a pack change with a CODEOWNER, not a
 *    delivery change. Left closed rather than rewritten here.
 *
 * The set may only shrink for reasons 2 and 3 (a pack owner may open one);
 * a NEW member is a decision that has to be visible in review, which is
 * what exact equality buys.
 */
const CLOSED: Readonly<Record<string, string>> = {
  substance: "files/13 §13 text_first — the answer must not travel on the voice channel",
  pain_score: "files/13 §13 text_only + invariant 22 — a guarded closed numeric set",
  pmh_conditions: "named-condition checklist (files/13 §4, Bent 2006)",
  fh_mother_conditions: "named-condition checklist (files/13 §4, Bent 2006)",
  fh_father_conditions: "named-condition checklist (files/13 §4, Bent 2006)",
  fh_brother_conditions: "named-condition checklist (files/13 §4, Bent 2006)",
  fh_sister_conditions: "named-condition checklist (files/13 §4, Bent 2006)",
  smoking: "the scripted question names the list; rewriting it is a pack change (invariant 10)",
  disability: "a closed administrative register, not a narrative answer",
};

describe("the asking style is declared, never defaulted", () => {
  it("every choice step in every shipped pack declares an ask style", () => {
    expect(choiceQuestions.length).toBeGreaterThan(80);
    for (const question of choiceQuestions) {
      expect(question.ask, `${question.id} declares no ask style`).toMatch(/^(open|closed)$/);
    }
  });

  it("the closed set is exactly the recorded one, and each member states its reason", () => {
    const closed = choiceQuestions.filter((q) => q.ask === "closed").map((q) => q.id);
    expect([...closed].sort()).toEqual(Object.keys(CLOSED).sort());
    for (const reason of Object.values(CLOSED)) {
      expect(reason.length).toBeGreaterThan(20);
    }
  });

  it("the open form is the rule and the closed form the exception", () => {
    const open = choiceQuestions.filter((q) => q.ask === "open");
    expect(open.length).toBeGreaterThan(choiceQuestions.length - open.length);
  });

  it("a step with no option list carries no ask style at all", () => {
    // `text` is already the patient's own words and `measure` is a guarded
    // control; neither has an option set for an open ask to be an
    // alternative TO, so the field does not apply rather than defaulting.
    for (const question of allQuestions) {
      if (question.kind === "text" || question.kind === "measure") {
        expect(question.ask, `${question.id}`).toBeUndefined();
      }
    }
  });
});

describe("the standardised value space survives the open form", () => {
  it("every open question still carries its options", () => {
    for (const question of choiceQuestions.filter(isOpenAsk)) {
      expect(question.options.length, `${question.id} lost its value space`).toBeGreaterThan(1);
    }
  });

  it("every gate still reads a declared option id of the question it gates on", () => {
    // (c) branching preserved: the ask style is a DELIVERY property, so no
    // gate's meaning moves. This is INT-236's rule re-asserted after the
    // type change, because a union that silently dropped `options` from an
    // arm would break exactly here.
    const byId = new Map(allQuestions.map((q) => [q.id, q]));
    for (const question of allQuestions) {
      if (question.askIf === undefined) {
        continue;
      }
      const gating = byId.get(question.askIf.questionId);
      expect(gating, `${question.id} gates on unknown ${question.askIf.questionId}`).toBeDefined();
      const ids = new Set((gating?.options ?? []).map((o) => o.id));
      for (const value of question.askIf.includesAny) {
        expect(ids.has(value), `${question.id} gates on undeclared ${value}`).toBe(true);
      }
    }
  });

  it("mode depth is untouched: Detaylı still asks strictly more than Hızlı", () => {
    const hizli = packForVisit("Kardiyoloji", { mode: "hizli" }).map((q) => q.id);
    const detayli = packForVisit("Kardiyoloji", { mode: "detayli" }).map((q) => q.id);
    expect(detayli.length).toBeGreaterThan(hizli.length);
    for (const id of hizli) {
      expect(detayli).toContain(id);
    }
  });
});

describe("a free-text answer is never a slot value (invariant 1)", () => {
  const gated = allQuestions.find((q) => q.id === "breath_timing")!;

  it("words alone open no gate", () => {
    const inWords: AnsweredValues[] = [
      { questionId: "complaint", values: [], words: "nefesim daralıyor" },
    ];
    expect(gated.askIf).toBeDefined();
    expect(askIfMet(gated.askIf, inWords)).toBe(false);
  });

  it("the same words plus the declared value do open it", () => {
    const resolved: AnsweredValues[] = [
      { questionId: "complaint", values: ["dyspnoea"], words: "nefesim daralıyor" },
    ];
    expect(askIfMet(gated.askIf, resolved)).toBe(true);
  });

  it("words still count as an answer, so the patient is not asked twice", () => {
    const pack = packForVisit("Kardiyoloji", { mode: "hizli" });
    const answered: AnsweredValues[] = [{ questionId: "complaint", values: [], words: "göğsüm" }];
    expect(missingQuestions(pack, answered).map((q) => q.id)).not.toContain("complaint");
  });

  it("an answer with neither a value nor words is still missing", () => {
    const pack = packForVisit("Kardiyoloji", { mode: "hizli" });
    const blank: AnsweredValues[] = [{ questionId: "complaint", values: [], words: "   " }];
    expect(missingQuestions(pack, blank).map((q) => q.id)).toContain("complaint");
  });
});

// --- the three type-level refusals ---------------------------------------------------
//
// Each is a shape that must not be constructible. The negative control is
// `@ts-expect-error` on the assignment; the positive control beside it is the
// same object with the offending field removed, which must compile — without
// it the directive would pass for the wrong reason.

const CHOICE_BASE = {
  id: "int286_control",
  kind: "single",
  titleKey: "intake.q.duration",
  options: [{ id: "yes", labelKey: "intake.opt.yes" }],
} as const;

describe("an instrument item can never be asked openly (invariant 10)", () => {
  it("refuses the shape at compile time", () => {
    const instrumentItem = {
      ...CHOICE_BASE,
      ask: "open",
      instrument: { instrumentId: "phq9", itemId: "item_1" },
    } as const;
    // @ts-expect-error — CLAUDE.md invariant 10 and files/13 §4: an
    // instrument is administered verbatim with explicit option selection.
    // An open-ended PHQ-9 item is not a PHQ-9 item.
    const refused: IntakeQuestion = instrumentItem;
    expect(refused.id).toBe("int286_control");
  });

  it("accepts the same item asked closed", () => {
    const permitted: IntakeQuestion = {
      ...CHOICE_BASE,
      ask: "closed",
      instrument: { instrumentId: "phq9", itemId: "item_1" },
    };
    expect(permitted.instrument?.instrumentId).toBe("phq9");
  });

  it("no shipped question carries an instrument reference yet", () => {
    // The instruments are HB-C1 (the authored pack) and HB-L2/HB-L3 (the
    // licences). The mechanism is wired and fails closed; the content is
    // empty, which is what CLAUDE.md asks of a blocked dependency.
    for (const question of allQuestions) {
      expect(question.instrument, `${question.id}`).toBeUndefined();
    }
  });
});

describe("a step not delivered by voice can never be asked openly (files/13 §13)", () => {
  it("refuses the shape at compile time", () => {
    const sensitive = { ...CHOICE_BASE, delivery: "text_only", ask: "open" } as const;
    // @ts-expect-error — files/13 §13: `text_only` means text only, no clip
    // and no `speech_tr` ever, and `text_first` exists so the answer does
    // not travel on the voice channel. An open ask makes speaking primary.
    const refused: IntakeQuestion = sensitive;
    expect(refused.id).toBe("int286_control");
  });

  it("accepts the same step asked closed", () => {
    const permitted: IntakeQuestion = { ...CHOICE_BASE, delivery: "text_only", ask: "closed" };
    expect(permitted.delivery).toBe("text_only");
  });

  it("every open question in the shipped packs is voice-delivered", () => {
    for (const question of choiceQuestions.filter(isOpenAsk)) {
      expect(question.delivery ?? "voice", `${question.id}`).toBe("voice");
    }
  });
});

describe("a guarded numeric measure carries no ask style at all (invariant 22)", () => {
  it("refuses the shape at compile time", () => {
    const measured = {
      id: "int286_measure_control",
      kind: "measure",
      titleKey: "intake.q.height",
      measure: {
        unitKey: "intake.unit.cm",
        min: 100,
        max: 220,
        start: 160,
        step: 1,
        coarseStep: 10,
      },
      ask: "open",
    } as const;
    // @ts-expect-error — invariant 22: no numeral reaches any TTS model and
    // there is no free numeric text entry on the clinical critical path, so
    // a measure is never answered in words.
    const refused: IntakeQuestion = measured;
    expect(refused.id).toBe("int286_measure_control");
  });

  it("accepts the same measure with no ask style", () => {
    const permitted: IntakeQuestion = {
      id: "int286_measure_control",
      kind: "measure",
      titleKey: "intake.q.height",
      measure: {
        unitKey: "intake.unit.cm",
        min: 100,
        max: 220,
        start: 160,
        step: 1,
        coarseStep: 10,
      },
    };
    expect(permitted.measure?.unitKey).toBe("intake.unit.cm");
  });
});

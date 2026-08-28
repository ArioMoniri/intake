/**
 * INT-233 agent speech composition: everything the agent SPEAKS is composed
 * from catalog tr strings only — never LLM output, never patient words
 * (invariant 2/10 posture for the dev tier). Patient quotes and free-text
 * values are DISPLAYED, never synthesized. Option hints are enumerated only
 * when the list fits spoken working memory (files/13 §5.3, Cowan ~4 chunks);
 * longer lists point to the screen. No numeral may ever reach the TTS
 * (invariant 22 — FreyaTTS rejects digits and the guard throws first).
 */
import { describe, expect, it } from "vitest";

import { en } from "../i18n/en";
import { tr, type MessageKey } from "../i18n/tr";
import { allQuestions, packForDepartment } from "../intake/questions";
import { confirmSpeechTr, MAX_SPOKEN_OPTION_HINTS, questionSpeechTr } from "./speech";
import { assertSpeakableTr } from "./tts";

const cardio = packForDepartment("Kardiyoloji");
const duration = cardio.find((q) => q.id === "duration")!;
const severity = cardio.find((q) => q.id === "severity")!;
const complaint = cardio.find((q) => q.id === "complaint")!;
const extra = cardio.find((q) => q.id === "extra")!;

describe("questionSpeechTr", () => {
  it("speaks the tr question text with enumerated hints when the options fit (≤ four)", () => {
    const speech = questionSpeechTr(duration);
    expect(speech).toContain(tr["intake.q.duration"]);
    expect(speech).toContain(tr["dialogue.optionsIntro"]);
    expect(speech).toContain(tr["intake.opt.today"]);
    expect(speech).toContain(tr["intake.opt.days"]);
    expect(speech).toContain(tr["intake.opt.week"]);
    expect(speech).toContain(tr["intake.opt.month"]);
    // ordinality-preserving list: forward order, "veya" before the last item
    expect(speech).toContain(`${tr["dialogue.or"]} ${tr["intake.opt.month"]}`);
    expect(speech.indexOf(tr["intake.opt.today"])).toBeLessThan(
      speech.indexOf(tr["intake.opt.days"]),
    );
  });

  it("points to the screen instead of enumerating when the list exceeds the spoken bound", () => {
    expect(complaint.options!.length).toBeGreaterThan(MAX_SPOKEN_OPTION_HINTS);
    const speech = questionSpeechTr(complaint);
    expect(speech).toContain(tr["intake.q.complaint"]);
    expect(speech).toContain(tr["dialogue.optionsOnScreen"]);
    expect(speech).not.toContain(tr["intake.opt.headache"]);
  });

  it("speaks the hint where the question has one", () => {
    expect(questionSpeechTr(extra)).toContain(tr["intake.q.extra.hint"]);
  });
});

describe("confirmSpeechTr", () => {
  it("echoes the candidate's catalog labels for option questions", () => {
    const speech = confirmSpeechTr(severity, ["moderate"]);
    expect(speech).toContain(tr["dialogue.confirmIntro"]);
    expect(speech).toContain(tr["intake.opt.moderate"]);
    expect(speech).toContain(tr["dialogue.confirmAsk"]);
  });

  it("joins multi-select labels with the catalog 'and'", () => {
    const speech = confirmSpeechTr(complaint, ["pain", "fever"]);
    expect(speech).toContain(tr["intake.opt.pain"]);
    expect(speech).toContain(`${tr["dialogue.and"]} ${tr["intake.opt.fever"]}`);
  });

  it("NEVER speaks a free-text value — text steps get the generic catalog line", () => {
    const speech = confirmSpeechTr(extra, ["merdiven çıkarken üç kat artıyor"]);
    expect(speech).toBe(tr["dialogue.confirmTextGeneric"]);
    expect(speech).not.toContain("merdiven");
  });

  it("drops unknown option ids and still asks a speakable question", () => {
    const speech = confirmSpeechTr(severity, ["not_an_option"]);
    expect(speech).toContain(tr["dialogue.confirmAsk"]);
    expect(speech).not.toContain("not_an_option");
    expect(() => assertSpeakableTr(speech)).not.toThrow();
  });
});

describe("everything speakable across every pack (invariant 22 mirror)", () => {
  it("every question's speech and every option's confirm speech carry no digit", () => {
    for (const question of allQuestions) {
      expect(() => assertSpeakableTr(questionSpeechTr(question)), question.id).not.toThrow();
      for (const option of question.options ?? []) {
        expect(
          () => assertSpeakableTr(confirmSpeechTr(question, [option.id])),
          `${question.id}:${option.id}`,
        ).not.toThrow();
      }
    }
  });
});

describe("dialogue copy (tr source of truth + en mirror, invariant 5)", () => {
  const newKeys = [
    "dialogue.start",
    "dialogue.kicker",
    "dialogue.offerHint",
    "dialogue.preparing",
    "dialogue.speakingHint",
    "dialogue.listeningHint",
    "dialogue.optionsIntro",
    "dialogue.optionsOnScreen",
    "dialogue.and",
    "dialogue.or",
    "dialogue.confirmIntro",
    "dialogue.confirmAsk",
    "dialogue.confirmTextGeneric",
    "dialogue.confirm",
    "dialogue.speakCorrection",
    "dialogue.typeThisStep",
  ] as const satisfies readonly MessageKey[];

  it("every key exists non-empty in tr and in the en mirror", () => {
    for (const key of newKeys) {
      expect(tr[key]?.trim().length, key).toBeGreaterThan(0);
      expect(en[key]?.trim().length, key).toBeGreaterThan(0);
    }
  });

  it("no numeral in any dialogue key — these strings feed the TTS (invariant 22)", () => {
    for (const key of newKeys) {
      expect(tr[key], key).not.toMatch(/\p{Nd}/u);
      expect(en[key], key).not.toMatch(/\p{Nd}/u);
    }
  });

  it("nothing reads as a finding: no diagnosis words (invariant 1/2 posture)", () => {
    for (const key of newKeys) {
      expect(tr[key].toLocaleLowerCase("tr-TR"), key).not.toContain("tanı");
      expect(tr[key].toLocaleLowerCase("tr-TR"), key).not.toContain("teşhis");
    }
  });

  it("the entry offer is the dialogue path in the owner's sense", () => {
    expect(tr["dialogue.start"]).toBe("Karşılıklı konuşarak ilerleyin");
  });
});

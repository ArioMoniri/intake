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
import {
  confirmSpeechTr,
  MAX_SPOKEN_OPTION_HINTS,
  questionAsideTr,
  questionSpeechTr,
} from "./speech";
import { assertSpeakableTr } from "./tts";

const cardio = packForDepartment("Kardiyoloji");
const duration = cardio.find((q) => q.id === "duration")!;
const severity = cardio.find((q) => q.id === "severity")!;
const complaint = cardio.find((q) => q.id === "complaint")!;
const extra = cardio.find((q) => q.id === "extra")!;
const breathTiming = allQuestions.find((q) => q.id === "breath_timing")!;
/** The shipped CLOSED step with a list short enough to enumerate (INT-286). */
const substance = allQuestions.find((q) => q.id === "substance")!;

describe("questionSpeechTr", () => {
  it("speaks the tr question text with enumerated hints when a CLOSED list fits (≤ four)", () => {
    // INT-286: enumeration is what a CLOSED question gets. `substance` is
    // closed because files/13 §13 makes it `text_first`.
    expect(substance.ask).toBe("closed");
    const speech = questionSpeechTr(substance);
    expect(speech).toContain(tr["intake.q.substance"]);
    expect(speech).toContain(tr["dialogue.optionsIntro"]);
    expect(speech).toContain(tr["intake.opt.no"]);
    expect(speech).toContain(tr["intake.opt.yes"]);
    expect(speech).toContain(tr["intake.opt.notStated"]);
    // ordinality-preserving list: forward order, "veya" before the last item
    expect(speech).toContain(`${tr["dialogue.or"]} ${tr["intake.opt.notStated"]}`);
    expect(speech.indexOf(tr["intake.opt.no"])).toBeLessThan(speech.indexOf(tr["intake.opt.yes"]));
  });

  it("asks openly instead of enumerating when the list exceeds the spoken bound", () => {
    expect(complaint.options!.length).toBeGreaterThan(MAX_SPOKEN_OPTION_HINTS);
    const speech = questionSpeechTr(complaint);
    expect(speech).toContain(tr["intake.q.complaint"]);
    expect(speech).not.toContain(tr["intake.opt.headache"]);
  });
});

// INT-286 — the owner's report: "it goes completly written and option based
// but should be voice and open end questios (still with the dyanmicness and
// standardized versions) as much as possible".
//
// A question the pack declares `ask: "open"` is never enumerated, at ANY list
// length. The photographed case is exactly here: `breath_timing` has four
// options, which fits the Cowan bound, so the agent read
// "Seçenekler: hareket ya da eforla, dinlenirken de oluyor, …" — a
// multiple-choice question delivered by voice. Now the agent asks the
// scripted question verbatim and invites the patient's own words; the option
// list survives as the CONFIRMATION read-back, and on the typed screen.
describe("an open question is asked, never enumerated (INT-286)", () => {
  it("the photographed four-option question is no longer read out as a list", () => {
    expect(breathTiming.ask).toBe("open");
    expect(breathTiming.options!.length).toBeLessThanOrEqual(MAX_SPOKEN_OPTION_HINTS);
    const speech = questionSpeechTr(breathTiming);
    expect(speech).toContain(tr["intake.q.breathTiming"]);
    expect(speech).not.toContain(tr["dialogue.optionsIntro"]);
    expect(speech).not.toContain(tr["intake.opt.exertion"]);
    expect(speech).not.toContain(tr["intake.opt.rest"]);
  });

  it("an open question adds no spoken aside — the invitation moved to the top of the flow (INT-318)", () => {
    // The per-turn "kendi sözlerinizle" invitation read as noise repeated on
    // every open turn, so it was dropped from the spoken lane (INT-318's
    // questionAsideTr change); the typed flow now shows it once at the top
    // instead. An open question is asked verbatim, with nothing appended.
    expect(questionAsideTr(breathTiming)).toBeNull();
    expect(questionSpeechTr(duration)).toBe(tr["intake.q.duration"]);
  });

  it("no open question in any pack enumerates its options", () => {
    for (const question of allQuestions) {
      if (question.ask !== "open") {
        continue;
      }
      const speech = questionSpeechTr(question);
      expect(speech, question.id).not.toContain(tr["dialogue.optionsIntro"]);
      for (const option of question.options) {
        expect(speech, `${question.id}:${option.id}`).not.toContain(tr[option.labelKey]);
      }
    }
  });

  it("the options survive as the spoken confirmation — the read-back is unchanged", () => {
    const speech = confirmSpeechTr(breathTiming, ["exertion"]);
    expect(speech).toContain(tr["dialogue.confirmIntro"]);
    expect(speech).toContain(tr["intake.opt.exertion"]);
    expect(speech).toContain(tr["dialogue.confirmAsk"]);
  });

  it("the invitation is one sentence and adds no second question", () => {
    // files/03 §4.2: ≤ 2 sentences and ONE question per turn. The aside
    // replaces an aside, so the turn's shape is exactly what it was.
    expect(tr["dialogue.openInvite"]).not.toContain("?");
    expect(en["dialogue.openInvite"]).not.toContain("?");
    expect(tr["dialogue.openInvite"].split(".").filter((s) => s.trim().length > 0)).toHaveLength(1);
  });
});

// INT-261 — the second half of the field report. On screen, in the voice
// phase, under the "Karşılıklı konuşma" kicker, the first bubble read:
//
//     Sizi bugün hekime getiren nedir?
//     Birden fazla seçebilirsiniz.
//
// The agent said that too. It is the TYPED form's control hint — the pack
// carries it as `hintKey` so the chips screen can tell you the grid is
// multi-select — and in a spoken turn it is simply false: no chips are
// rendered during a question turn (they open at `confirming`), so there is
// nothing to select more than one of. Same for `intake.q.extra.hint`
// ("you may leave it blank": no field), and same for the composed
// "Seçenekleri ekranda görebilirsiniz." — the options are NOT on screen.
//
// The rule, and it is invariant 10's rule: what the agent says in a turn is
// the question and what belongs to asking it. Copy that describes a CONTROL
// belongs to the lane that has the control. `questionAsideTr` is the only
// thing the agent adds to a question now, and the bubble renders the same
// aside — so a patient whose voice lane went silent reads exactly what a
// patient who can hear it is told.
describe("questionSpeechTr — the typed lane's control copy never crosses (INT-261)", () => {
  const controlHints = ["intake.q.complaint.hint", "intake.q.extra.hint"] as const;

  it("no question in any pack speaks a control hint", () => {
    for (const question of allQuestions) {
      const speech = questionSpeechTr(question);
      for (const key of controlHints) {
        expect(speech, `${question.id} / ${key}`).not.toContain(tr[key]);
      }
    }
  });

  it("a question turn never claims the options are on screen — they are not", () => {
    for (const question of allQuestions) {
      expect(questionSpeechTr(question), question.id).not.toContain(
        "Seçenekleri ekranda görebilirsiniz.",
      );
    }
  });

  it("the aside is the ONLY thing the agent adds, and the bubble can render it", () => {
    // A CLOSED list of ≤ four: the spoken enumeration, which IS part of
    // asking that question (INT-286 narrowed this to the closed form).
    expect(questionAsideTr(substance)).toBe(
      `${tr["dialogue.optionsIntro"]} ${tr["intake.opt.no"]}, ${tr["intake.opt.yes"]} ${tr["dialogue.or"]} ${tr["intake.opt.notStated"]}.`,
    );
    // An open question adds nothing spoken — the invitation is a once-at-top
    // affordance now (INT-318), not a per-turn aside.
    expect(questionAsideTr(complaint)).toBeNull();
    // Free text is already the patient's own words: nothing to add.
    expect(questionAsideTr(extra)).toBeNull();
    // Speech is exactly question + aside, so the two channels cannot drift.
    expect(questionSpeechTr(substance)).toBe(
      `${tr["intake.q.substance"]} ${questionAsideTr(substance)}`,
    );
    // …and an open question is spoken as just the scripted question.
    expect(questionSpeechTr(duration)).toBe(tr["intake.q.duration"]);
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
    "dialogue.kicker",
    "dialogue.entryTitle",
    "dialogue.entryBody",
    "dialogue.preparing",
    "dialogue.speakingHint",
    "dialogue.listeningHint",
    "dialogue.optionsIntro",
    "dialogue.and",
    "dialogue.or",
    "dialogue.confirmIntro",
    "dialogue.confirmAsk",
    "dialogue.confirmTextGeneric",
    // INT-286 — what an OPEN question is asked with instead of its list.
    "dialogue.openInvite",
    "dialogue.confirm",
    "dialogue.speakCorrection",
    "dialogue.typeThisStep",
    "dialogue.voiceMuted",
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

  it("the false 'options are on screen' line is gone from both catalogs (INT-261)", () => {
    // It was only ever spoken during a question turn, and during a question
    // turn there are no options on screen. A string that is never true is
    // not copy to keep behind a flag; it is copy to delete.
    expect((tr as Record<string, string>)["dialogue.optionsOnScreen"]).toBeUndefined();
    expect((en as Record<string, string>)["dialogue.optionsOnScreen"]).toBeUndefined();
  });

  it("the entry IS the conversation — no chooser copy survives (INT-239)", () => {
    expect(tr["dialogue.kicker"]).toBe("Karşılıklı konuşma");
    expect(tr["dialogue.entryTitle"]).toBe("Sizinle konuşarak ilerleyelim");
    // Typing is named inside the entry body as the second door, so the
    // patient never has to pick a mode before the conversation starts.
    expect(tr["dialogue.entryBody"].toLocaleLowerCase("tr-TR")).toContain("yazarak");
  });
});

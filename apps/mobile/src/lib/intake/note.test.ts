import { describe, expect, it } from "vitest";

import { getTestAccount, type TestAccount } from "../dev/accounts";
import type { FactDecision } from "./carriedFacts";
import {
  buildNote,
  emptyNoteState,
  noteReducer,
  sentSections,
  type Answer,
  type NoteAccount,
  type NoteState,
} from "./note";

// ---- INT-198: labelled HPI lines from the department packs -----------------

/** Synthetic — invented person, nothing carried so the meds section stays out. */
const account: TestAccount = {
  id: "synthetic-note-test",
  name: "Test Hasta",
  ageYears: 44,
  locale: "tr",
  consents: { core: true, voice: false, wellbeing: false, documents: false, health: false },
  visits: [],
  carriedFacts: [],
  records: [],
};

describe("buildNote labelled HPI lines — department packs", () => {
  it("renders the Üroloji pack's dimensions as labelled lines in pack order", () => {
    // Deliberately shuffled: line order must come from the pack, not from
    // the order the patient happened to answer in.
    const answers: Answer[] = [
      { questionId: "severity", values: ["moderate"] },
      { questionId: "complaint", values: ["pain"] },
      { questionId: "uro_assoc", values: ["flank_pain"] },
      { questionId: "duration", values: ["days"] },
      { questionId: "time_of_day", values: ["night"] },
      { questionId: "uro_urination", values: ["frequent", "night"] },
      { questionId: "onset", values: ["gradual"] },
      { questionId: "extra", values: ["Su içtikçe rahatladığımı fark ettim."] },
    ];

    const sections = buildNote(answers, account);
    expect(sections.map((s) => s.id)).toEqual(["chief_complaint", "hpi"]);
    expect(sections[0].lines).toEqual(["Ağrı"]);
    expect(sections[1].lines).toEqual([
      "Süre: Birkaç gündür",
      "Başlangıç: Yavaş yavaş gelişti",
      "İdrar şikâyetleri: Sık idrara çıkma, Gece idrara kalkma",
      "Zamanlama: Gece artıyor",
      "Eşlik edenler: Yan tarafta ya da belde ağrı",
      "Şiddet: Orta",
      "Hasta notu: Su içtikçe rahatladığımı fark ettim.",
    ]);
  });

  it("renders the Gastroenteroloji pack's dimensions as labelled lines in pack order", () => {
    const answers: Answer[] = [
      { questionId: "complaint", values: ["stomach"] },
      { questionId: "duration", values: ["week"] },
      { questionId: "gastro_location", values: ["upper"] },
      { questionId: "gastro_character", values: ["burning"] },
      { questionId: "gastro_meal", values: ["after_meal"] },
      { questionId: "gastro_bowel", values: ["alternating"] },
      { questionId: "gastro_assoc", values: ["nausea", "heartburn"] },
      { questionId: "severity", values: ["mild"] },
    ];

    const sections = buildNote(answers, account);
    expect(sections.map((s) => s.id)).toEqual(["chief_complaint", "hpi"]);
    expect(sections[0].lines).toEqual(["Mide şikâyeti"]);
    expect(sections[1].lines).toEqual([
      "Süre: Bir haftadan uzun süredir",
      "Bölge: Karnın üst kısmında",
      "Ağrının niteliği: Yanma gibi",
      "Yemekle ilişkisi: Yemekten sonra artıyor",
      "Bağırsak alışkanlığı: Bazen kabızlık bazen ishal",
      "Eşlik edenler: Bulantı, Göğse doğru yanma ya da ekşime",
      "Şiddet: Hafif",
    ]);
  });

  it("skips unanswered dimensions instead of rendering empty labels", () => {
    const answers: Answer[] = [
      { questionId: "complaint", values: ["pain"] },
      { questionId: "uro_urination", values: [""] },
      { questionId: "severity", values: ["severe"] },
    ];

    const sections = buildNote(answers, account);
    expect(sections[1].lines).toEqual(["Şiddet: Şiddetli"]);
  });
});

// ---- INT-208: device health summary attachment ------------------------------

const ayse = getTestAccount("ayse")!;

const HEALTH_LINES = ["Adımlar (son 7 gün): 2026-08-27 8123 adım", "Dinlenme nabzı: 58–64 atım/dk"];

function withHealth(state: NoteState = emptyNoteState()): NoteState {
  return noteReducer(state, { type: "attachHealth", lines: HEALTH_LINES });
}

describe("attachHealth — device health summary into the note draft (INT-208)", () => {
  it("empty state carries no health attachment", () => {
    expect(emptyNoteState().healthLines).toBeNull();
    const sections = buildNote([], ayse, null);
    expect(sections.find((s) => s.id === "device_health")).toBeUndefined();
  });

  it("attaching stores the lines; a second attach replaces, never duplicates", () => {
    const once = withHealth();
    expect(once.healthLines).toEqual(HEALTH_LINES);
    const twice = noteReducer(once, { type: "attachHealth", lines: ["Uyku: 6,5 saat"] });
    expect(twice.healthLines).toEqual(["Uyku: 6,5 saat"]);
  });

  it("the attached block becomes a labelled device_health section", () => {
    const state = withHealth();
    const sections = buildNote(state.answers, ayse, state.healthLines);
    const health = sections.find((s) => s.id === "device_health");
    expect(health).toBeDefined();
    expect(health!.titleKey).toBe("review.section.health");
    expect(health!.lines).toEqual(HEALTH_LINES);
  });

  it("scope-off excludes the health section from what is sent — and never blocks sending", () => {
    let state = withHealth();
    state = noteReducer(state, { type: "scope", sectionId: "device_health", shared: false });
    expect(sentSections(state, ayse).find((s) => s.id === "device_health")).toBeUndefined();
    state = noteReducer(state, { type: "send" });
    expect(state.status).toBe("sent");
  });

  it("a sent note is immutable — attach after send is a no-op", () => {
    let state = withHealth();
    state = noteReducer(state, { type: "send" });
    const after = noteReducer(state, { type: "attachHealth", lines: ["x"] });
    expect(after.healthLines).toEqual(HEALTH_LINES);
  });

  it("existing sections and answers are untouched by the attachment", () => {
    let state = emptyNoteState();
    state = noteReducer(state, { type: "answer", questionId: "complaint", values: ["pain"] });
    state = withHealth(state);
    const ids = buildNote(state.answers, ayse, state.healthLines).map((s) => s.id);
    expect(ids).toContain("chief_complaint");
    expect(ids[ids.length - 1]).toBe("device_health");
  });
});

// ---- INT-236: Hızlı/Detaylı mode, environment deferral, checkpoint ----------

describe("mode context (02 §2 — Hızlı default, Hastanedeyim sets Detaylı)", () => {
  it("a fresh note starts in Hızlı with the environment unchecked and nothing deferred", () => {
    const s = emptyNoteState();
    expect(s.mode).toBe("hizli");
    expect(s.privacy).toBe("unchecked");
    expect(s.deferred).toEqual([]);
    expect(s.checkpointed).toBe(false);
  });

  it("the Hastanedeyim switch sets Detaylı and is reversible", () => {
    const on = noteReducer(emptyNoteState(), { type: "mode", mode: "detayli" });
    expect(on.mode).toBe("detayli");
    const off = noteReducer(on, { type: "mode", mode: "hizli" });
    expect(off.mode).toBe("hizli");
  });

  it("a sent note is frozen — mode, privacy and checkpoint are no-ops after send", () => {
    let s = noteReducer(emptyNoteState(), { type: "send" });
    s = noteReducer(s, { type: "mode", mode: "detayli" });
    s = noteReducer(s, { type: "privacy", alone: false });
    s = noteReducer(s, { type: "checkpoint" });
    expect(s.mode).toBe("hizli");
    expect(s.privacy).toBe("unchecked");
    expect(s.deferred).toEqual([]);
    expect(s.checkpointed).toBe(false);
  });
});

describe("environment privacy self-check (02 §33 — deferred, not asked)", () => {
  const detayli = () => noteReducer(emptyNoteState(), { type: "mode", mode: "detayli" });

  it("alone establishes privacy and defers nothing", () => {
    const s = noteReducer(detayli(), { type: "privacy", alone: true });
    expect(s.privacy).toBe("private");
    expect(s.deferred).toEqual([]);
  });

  it("someone present defers every sensitive section — wellbeing and, since INT-256, family history", () => {
    const s = noteReducer(detayli(), { type: "privacy", alone: false });
    expect(s.privacy).toBe("not_private");
    expect(s.deferred).toEqual(["wellbeing", "family_history"]);
  });

  it("re-establishing privacy lifts the deferral — nothing was asked, nothing is lost", () => {
    let s = noteReducer(detayli(), { type: "privacy", alone: false });
    s = noteReducer(s, { type: "privacy", alone: true });
    expect(s.privacy).toBe("private");
    expect(s.deferred).toEqual([]);
  });

  it("the deferral is carried into the note verbatim: eksik: ortam uygun değildi", () => {
    const sections = buildNote([], account, null, ["wellbeing"]);
    const deferred = sections.find((s) => s.id === "deferred");
    expect(deferred).toBeDefined();
    expect(deferred!.titleKey).toBe("review.section.deferred");
    expect(deferred!.lines).toEqual(["İyilik hâli taraması — eksik: ortam uygun değildi"]);
  });

  it("no deferral, no deferred section — and the section always renders last", () => {
    expect(buildNote([], account, null, []).find((s) => s.id === "deferred")).toBeUndefined();
    const answers: Answer[] = [{ questionId: "complaint", values: ["pain"] }];
    const ids = buildNote(answers, account, HEALTH_LINES, ["wellbeing"]).map((s) => s.id);
    expect(ids[ids.length - 1]).toBe("deferred");
  });

  it("sentSections carries the deferral by default; scope-off excludes it (patient's call)", () => {
    let s = noteReducer(detayli(), { type: "privacy", alone: false });
    expect(sentSections(s, ayse).find((x) => x.id === "deferred")).toBeDefined();
    s = noteReducer(s, { type: "scope", sectionId: "deferred", shared: false });
    expect(sentSections(s, ayse).find((x) => x.id === "deferred")).toBeUndefined();
  });
});

describe("clinic-interruptible checkpoint (02 §34 — instant, zero lost turns)", () => {
  it("checkpoint keeps every committed answer and the note stays a draft", () => {
    let s = emptyNoteState();
    s = noteReducer(s, { type: "answer", questionId: "complaint", values: ["pain"] });
    s = noteReducer(s, { type: "answer", questionId: "duration", values: ["days"] });
    const cp = noteReducer(s, { type: "checkpoint" });
    expect(cp.answers).toEqual(s.answers);
    expect(cp.checkpointed).toBe(true);
    expect(cp.status).toBe("draft");
  });

  it("resume clears the checkpoint and keeps the answers", () => {
    let s = noteReducer(emptyNoteState(), {
      type: "answer",
      questionId: "complaint",
      values: ["pain"],
    });
    s = noteReducer(s, { type: "checkpoint" });
    s = noteReducer(s, { type: "resume" });
    expect(s.checkpointed).toBe(false);
    expect(s.answers).toEqual([{ questionId: "complaint", values: ["pain"] }]);
  });
});

describe("koşul değişti (an edit that unmets a gate keeps the answer, marked)", () => {
  it("renders the stale answer's line with the marker instead of discarding it", () => {
    const answers: Answer[] = [
      { questionId: "complaint", values: ["fever"] },
      { questionId: "gastro_meal", values: ["after_meal"] },
    ];
    const hpi = buildNote(answers, account).find((s) => s.id === "hpi")!;
    expect(hpi.lines).toContain("Yemekle ilişkisi: Yemekten sonra artıyor (koşul değişti)");
  });

  it("a met gate renders the plain line, no marker", () => {
    const answers: Answer[] = [
      { questionId: "complaint", values: ["stomach"] },
      { questionId: "gastro_meal", values: ["after_meal"] },
    ];
    const hpi = buildNote(answers, account).find((s) => s.id === "hpi")!;
    expect(hpi.lines).toContain("Yemekle ilişkisi: Yemekten sonra artıyor");
  });
});

// ---- INT-247: carried-forward facts are UNCONFIRMED until this visit -------
// Owner bug: "it says patient uses metoprolol from previous ones but these
// should be updateble mayne they stopped using". Invariant 12 read literally:
// a PatientOverlay fact requires patient or clinician confirmation, so a fact
// carried from an earlier visit may not be printed as current until someone
// confirms it FOR THIS VISIT.

/** Ayşe's one carried fact — recorded at the filed 2026-05-12 visit. */
const AYSE_FACT = "cf-ayse-metoprolol";
const AYSE_FACT_TEXT = "Metoprolol (düzenli kullanım)";

/** Nobody carries anything: the "absent" control for the stopped test. */
const noFacts: NoteAccount = { carriedFacts: [] };

const patientNow: FactDecision = {
  outcome: "confirmed",
  by: { role: "patient", attribution: "self_report" },
  at: "2026-08-29",
};

describe("carried facts never reach the note as current (invariant 12)", () => {
  const answers: Answer[] = [{ questionId: "complaint", values: ["pain"] }];

  it("an unconfirmed carried fact is NOT printed as a current medication", () => {
    const meds = buildNote(answers, ayse).find((s) => s.id === "medications");
    // The bug: today this section prints the bare fact text, which a
    // clinician reads as "the patient takes this now".
    expect(meds?.lines ?? []).not.toContain(AYSE_FACT_TEXT);
  });

  it("an unconfirmed carried fact is still shown, marked unconfirmed", () => {
    const meds = buildNote(answers, ayse).find((s) => s.id === "medications");
    expect(meds).toBeDefined();
    expect(meds!.lines.join(" ")).toContain(AYSE_FACT_TEXT);
    expect(meds!.lines.join(" ")).toContain("bu ziyarette onaylanmadı");
  });

  it("confirming for this visit is what makes it current", () => {
    const meds = buildNote(answers, ayse, null, [], { [AYSE_FACT]: patientNow }).find(
      (s) => s.id === "medications",
    );
    expect(meds!.lines.join(" ")).not.toContain("bu ziyarette onaylanmadı");
    expect(meds!.lines.join(" ")).toContain("hasta bu ziyarette devam ettiğini söyledi");
  });
});

describe("a stopped fact is not an absent fact", () => {
  const answers: Answer[] = [{ questionId: "complaint", values: ["pain"] }];
  const stopped: FactDecision = {
    outcome: "stopped",
    by: { role: "patient", attribution: "self_report" },
    at: "2026-08-29",
  };

  it("stopped renders distinguishably from absent — absent says nothing at all", () => {
    const absent = buildNote(answers, noFacts);
    const retracted = buildNote(answers, ayse, null, [], { [AYSE_FACT]: stopped });

    // Absent: no medications section exists, because there is nothing to say.
    expect(absent.find((s) => s.id === "medications")).toBeUndefined();

    // Stopped: the note SAYS it — previously recorded, patient reports stopping.
    const meds = retracted.find((s) => s.id === "medications")!;
    expect(meds.lines.join(" ")).toContain(AYSE_FACT_TEXT);
    expect(meds.lines.join(" ")).toContain("hasta bıraktığını söyledi");
  });

  it("stopped renders distinguishably from confirmed", () => {
    const asStopped = buildNote(answers, ayse, null, [], { [AYSE_FACT]: stopped });
    const asCurrent = buildNote(answers, ayse, null, [], { [AYSE_FACT]: patientNow });
    expect(asStopped.find((s) => s.id === "medications")!.lines).not.toEqual(
      asCurrent.find((s) => s.id === "medications")!.lines,
    );
  });

  it("provenance survives: who asserted it before, and when", () => {
    const meds = buildNote(answers, ayse, null, [], { [AYSE_FACT]: stopped }).find(
      (s) => s.id === "medications",
    )!;
    expect(meds.lines.join(" ")).toContain("önceki kayıt");
    expect(meds.lines.join(" ")).toContain("12 Mayıs 2026");
  });
});

describe("the fact decision is per-visit note state", () => {
  it("a fresh note has decided nothing", () => {
    expect(emptyNoteState().factReview).toEqual({});
  });

  it("deciding records the outcome, the asserter and the moment", () => {
    const s = noteReducer(emptyNoteState(), {
      type: "fact",
      factId: AYSE_FACT,
      decision: patientNow,
    });
    expect(s.factReview[AYSE_FACT]).toEqual(patientNow);
  });

  it("a decision can be taken back — undecided is a real state, not a default yes", () => {
    let s = noteReducer(emptyNoteState(), {
      type: "fact",
      factId: AYSE_FACT,
      decision: patientNow,
    });
    s = noteReducer(s, { type: "fact", factId: AYSE_FACT, decision: null });
    expect(s.factReview[AYSE_FACT]).toBeUndefined();
    expect(
      buildNote([], ayse, null, [], s.factReview)
        .find((x) => x.id === "medications")!
        .lines.join(" "),
    ).toContain("bu ziyarette onaylanmadı");
  });

  it("a sent note is frozen — deciding after send is a no-op", () => {
    let s = noteReducer(emptyNoteState(), { type: "send" });
    s = noteReducer(s, { type: "fact", factId: AYSE_FACT, decision: patientNow });
    expect(s.factReview).toEqual({});
  });

  it("sentSections carries the reviewed facts", () => {
    let s = noteReducer(emptyNoteState(), {
      type: "answer",
      questionId: "complaint",
      values: ["pain"],
    });
    s = noteReducer(s, { type: "fact", factId: AYSE_FACT, decision: patientNow });
    const meds = sentSections(s, ayse).find((x) => x.id === "medications")!;
    expect(meds.lines.join(" ")).toContain("hasta bu ziyarette devam ettiğini söyledi");
  });
});

// ---- INT-286: the patient's own words reach the clinician -------------------
//
// Open-ended asking buys nothing if the words evaporate on the way to the
// note: the clinician would read the same coded label either way. So an
// answer carries `words` — the verbatim span the dialogue already holds as a
// quote and the typed screen now collects — and the note prints it after the
// coded labels, quoted, so it reads as the patient's utterance and not as a
// second finding. `values` stays the coded value space and nothing else, so
// no free text can reach a gate or a rule (invariant 1).

describe("an open answer carries the patient's own words (INT-286)", () => {
  it("prints the words quoted, after the coded label, on the same line", () => {
    const answers: Answer[] = [
      { questionId: "complaint", values: ["dyspnoea"] },
      {
        questionId: "breath_timing",
        values: ["exertion"],
        words: "merdiven çıkarken nefesim daralıyor",
      },
    ];
    const sections = buildNote(answers, account);
    const hpi = sections.find((s) => s.id === "hpi")!;
    expect(hpi.lines).toContain(
      "Nefes darlığının zamanı: Hareket ya da eforla, “merdiven çıkarken nefesim daralıyor”",
    );
  });

  it("prints the words alone when extraction resolved no coded value", () => {
    // (d) — the honest end state of an open turn nothing could be mapped
    // from. The patient's sentence is not thrown away and nothing is
    // invented in its place.
    const answers: Answer[] = [
      { questionId: "complaint", values: ["dyspnoea"] },
      { questionId: "breath_timing", values: [], words: "tarif etmesi zor, bazen oluyor" },
    ];
    const hpi = buildNote(answers, account).find((s) => s.id === "hpi")!;
    expect(hpi.lines).toContain("Nefes darlığının zamanı: “tarif etmesi zor, bazen oluyor”");
  });

  it("an answer with neither a value nor words prints nothing", () => {
    const answers: Answer[] = [
      { questionId: "complaint", values: ["dyspnoea"] },
      { questionId: "breath_timing", values: [], words: "  " },
    ];
    // Nothing at all: whitespace is not an answer, so the question does not
    // even open an HPI section on its own.
    const sections = buildNote(answers, account);
    expect(sections.map((s) => s.id)).not.toContain("hpi");
    expect(sections.flatMap((s) => s.lines).join("\n")).not.toContain("Nefes darlığının zamanı");
  });

  it("the reducer keeps the words with the answer it belongs to", () => {
    const state = noteReducer(emptyNoteState(), {
      type: "answer",
      questionId: "breath_timing",
      values: ["exertion"],
      words: "yürürken oluyor",
    });
    expect(state.answers).toEqual([
      { questionId: "breath_timing", values: ["exertion"], words: "yürürken oluyor" },
    ]);
  });

  it("re-answering without words drops the old words rather than keeping a stale quote", () => {
    // The words are provenance FOR a value. A patient who changes their
    // answer on the review screen has not re-said the old sentence, so
    // carrying it forward would attribute words to an answer they were
    // never said about.
    const first = noteReducer(emptyNoteState(), {
      type: "answer",
      questionId: "breath_timing",
      values: ["exertion"],
      words: "yürürken oluyor",
    });
    const second = noteReducer(first, {
      type: "answer",
      questionId: "breath_timing",
      values: ["rest"],
    });
    expect(second.answers).toEqual([{ questionId: "breath_timing", values: ["rest"] }]);
  });
});

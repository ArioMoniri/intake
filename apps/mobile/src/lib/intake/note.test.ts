import { describe, expect, it } from "vitest";

import { getTestAccount, type TestAccount } from "../dev/accounts";
import {
  buildNote,
  emptyNoteState,
  noteReducer,
  sentSections,
  type Answer,
  type NoteState,
} from "./note";

// ---- INT-198: labelled HPI lines from the department packs -----------------

/** Synthetic — invented person, no medications so the meds section stays out. */
const account: TestAccount = {
  id: "synthetic-note-test",
  name: "Test Hasta",
  ageYears: 44,
  locale: "tr",
  consents: { core: true, voice: false, wellbeing: false, documents: false, health: false },
  visits: [],
  medications: [],
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

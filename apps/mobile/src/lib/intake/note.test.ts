import { describe, expect, it } from "vitest";

import type { TestAccount } from "../dev/accounts";
import { buildNote, type Answer } from "./note";

/** Synthetic — invented person, no medications so the meds section stays out. */
const account: TestAccount = {
  id: "synthetic-note-test",
  name: "Test Hasta",
  ageYears: 44,
  locale: "tr",
  consents: { core: true, voice: false, wellbeing: false, documents: false },
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

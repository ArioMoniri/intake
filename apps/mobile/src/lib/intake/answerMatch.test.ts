/**
 * INT-293 — the deterministic floor under the extractor.
 *
 * The walkthrough (docs/evidence/INT-293.md) answered three questions on the
 * dialogue surface and the note stayed at "0 / 10 bölüm". The issue names the
 * first thing to test: the typed Turkish carried no diacritics, so the answer
 * may simply never have been mapped. These tests pin the mapping itself —
 * option labels in, option ids out — in both directions of the Turkish fold,
 * over the whole authored vocabulary.
 *
 * What this matcher is NOT: an interpreter. It recognises a declared option's
 * own label inside the patient's words and nothing else. It never scores,
 * never ranks by similarity and never guesses between two readings — an
 * ambiguous single-select yields nothing, exactly as `lib/extract.ts` drops an
 * ambiguous candidate off the wire. What it produces is a SUGGESTION the
 * patient still confirms (invariant 1 posture); it is not an answer until the
 * confirm turn commits it.
 */
import { describe, expect, it } from "vitest";

import { t } from "../i18n";
import { foldedWords, matchOptionsInWords } from "./answerMatch";
import { baseLayerQuestions, measurementQuestions } from "./baseLayer";
import { allQuestions, packForDepartment, type IntakeQuestion } from "./questions";

const cardio = packForDepartment("İç Hastalıkları");

function question(id: string): IntakeQuestion {
  const found = [...allQuestions, ...baseLayerQuestions, ...measurementQuestions].find(
    (q) => q.id === id,
  );
  if (found === undefined) {
    throw new Error(`no such question: ${id}`);
  }
  return found;
}

/**
 * What a phone keyboard without a Turkish layout produces — the walkthrough's
 * own input. Deliberately a DIFFERENT implementation from the matcher's fold
 * (NFD strip plus the two dotless letters the decomposition does not reach),
 * so a round-trip through both is a real round-trip and not the same function
 * agreeing with itself.
 */
function withoutDiacritics(value: string): string {
  return value
    .replace(/ı/g, "i")
    .replace(/İ/g, "I")
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .normalize("NFC");
}

describe("matchOptionsInWords — the reported reproduction", () => {
  it("'Bugun basladi', with no diacritics, is the `today` option", () => {
    // The exact words the walkthrough typed into the composer.
    expect(matchOptionsInWords(question("duration"), "Bugun basladi")).toEqual(["today"]);
  });

  it("'Bugün başladı', fully diacritised, is the same option", () => {
    expect(matchOptionsInWords(question("duration"), "Bugün başladı")).toEqual(["today"]);
  });

  it("the answer inside a sentence still lands: 'Aniden basladi bu sabah'", () => {
    expect(matchOptionsInWords(question("onset"), "Aniden basladi bu sabah")).toEqual(["sudden"]);
  });
});

describe("matchOptionsInWords — the Turkish fold, explicitly", () => {
  it("the dotted/dotless i pair folds by table, not by a naive lowercase", () => {
    const drug = t("intake.opt.allergyMedicine", "tr"); // "İlaç"
    expect(drug.startsWith("İ")).toBe(true);
    // The naive route: toLowerCase() leaves a combining dot on the capital İ
    // and leaves ı as ı, so neither side of the pair reaches plain ASCII.
    expect(drug.toLowerCase()).not.toBe("ilac");
    expect("Ağrı".toLowerCase()).not.toBe("agri");
    // The table route reaches it from both directions.
    expect(foldedWords(drug)).toEqual(["ilac"]);
    expect(foldedWords("ilac")).toEqual(["ilac"]);
    expect(foldedWords("Ağrı")).toEqual(["agri"]);
    expect(foldedWords("AĞRI")).toEqual(["agri"]);
  });

  it("matches whole words only — a label inside a longer word is not an answer", () => {
    // "Sol" is an option of `radiation_side`; "solunum" is not that answer.
    expect(matchOptionsInWords(question("radiation_side"), "solunum sıkıntım var")).toBeNull();
    expect(matchOptionsInWords(question("radiation_side"), "Sol tarafa")).toEqual(["left"]);
  });
});

describe("matchOptionsInWords — the whole authored vocabulary round-trips", () => {
  const packs = [...allQuestions, ...baseLayerQuestions, ...measurementQuestions];
  const withOptions = packs.filter(
    (q): q is IntakeQuestion & { options: NonNullable<IntakeQuestion["options"]> } =>
      q.options !== undefined && q.options.length > 0,
  );

  it("covers every option of every authored question", () => {
    expect(withOptions.length).toBeGreaterThan(50);
    expect(withOptions.flatMap((q) => q.options).length).toBeGreaterThan(200);
  });

  it("every option label, stripped of its diacritics, maps back to its own id", () => {
    const misses: string[] = [];
    for (const q of withOptions) {
      for (const option of q.options) {
        const label = t(option.labelKey, "tr");
        const typed = withoutDiacritics(label);
        const matched = matchOptionsInWords(q, typed);
        if (matched === null || matched.length !== 1 || matched[0] !== option.id) {
          misses.push(`${q.id}/${option.id} "${typed}" → ${JSON.stringify(matched)}`);
        }
      }
    }
    expect(misses).toEqual([]);
  });

  it("every option label, fully diacritised, maps back to its own id", () => {
    const misses: string[] = [];
    for (const q of withOptions) {
      for (const option of q.options) {
        const matched = matchOptionsInWords(q, t(option.labelKey, "tr"));
        if (matched === null || matched.length !== 1 || matched[0] !== option.id) {
          misses.push(`${q.id}/${option.id} → ${JSON.stringify(matched)}`);
        }
      }
    }
    expect(misses).toEqual([]);
  });
});

describe("matchOptionsInWords — what it refuses", () => {
  it("a single-select answered two ways at once yields nothing, never a guess", () => {
    expect(
      matchOptionsInWords(question("duration"), "Bugün başladı, aslında birkaç gündür"),
    ).toBeNull();
  });

  it("a multi-select takes every option the patient named, in pack order", () => {
    expect(matchOptionsInWords(question("complaint"), "Ateş ve ağrı var")).toEqual([
      "pain",
      "fever",
    ]);
  });

  it("a longer label wins over the shorter one it contains", () => {
    // "Baş ağrısı" and "Ağrı" are both `complaint` options; the sentence names
    // one symptom, so it must not also count as the other.
    expect(matchOptionsInWords(question("complaint"), "Baş ağrısı var")).toEqual(["headache"]);
  });

  it("words that name no option yield nothing", () => {
    expect(matchOptionsInWords(question("duration"), "pek hatırlamıyorum")).toBeNull();
    expect(matchOptionsInWords(question("duration"), "   ")).toBeNull();
  });

  it("a free-text or measured step has no option vocabulary to match", () => {
    expect(matchOptionsInWords(question("extra"), "canım sıkkın")).toBeNull();
    expect(matchOptionsInWords(question("height"), "yüz yetmiş")).toBeNull();
  });

  it("the pack the dialogue actually runs is matched question by question", () => {
    // Every option-bearing question of a real department pack answers with its
    // own vocabulary and nothing else — a label from another question does not
    // leak across.
    const duration = cardio.find((q) => q.id === "duration");
    expect(duration).toBeDefined();
    expect(matchOptionsInWords(duration!, "Aniden başladı")).toBeNull();
  });
});

/**
 * INT-293 follow-up — the negation guard.
 *
 * Turkish negation is POST-POSED: the word that cancels the sentence arrives
 * after the thing it cancels. A matcher that reads whole words in sequence
 * and stops there therefore reads *"Ateş yok"* — "I have no fever" — as the
 * `fever` option, and `DialogueIntake` pre-ticks that suggestion and commits
 * it into the clinician's note in one tap. A dropped answer is visibly
 * missing; an inverted one looks like data, so this is the worse of the two
 * failures and it is the one the guard exists to stop.
 *
 * The guard REFUSES; it does not interpret. Turkish `-ma-/-me-` collides with
 * real stems (`Kanama` is a noun, not a negated verb — the lesson INT-248
 * recorded for the converbs), so every failure mode here has to fall toward
 * NOT matching: the worst case is the behaviour the surface had before the
 * matcher existed, and the extract lane still receives the same utterance and
 * can place it properly.
 */
describe("matchOptionsInWords — post-posed negation is refused, never read", () => {
  const associated = question("associated");

  it("'Ateş yok' is not the `fever` option", () => {
    expect(matchOptionsInWords(question("complaint"), "Ateş yok")).toBeNull();
  });

  it("'Terleme var, bulantı yok' is not one flat set of all three", () => {
    // The mixed sentence cannot be a flat set at all: sweating is asserted,
    // nausea is denied, and `none` denies both. There is no correct subset to
    // pick here, so nothing is picked.
    expect(matchOptionsInWords(associated, "Terleme var, bulantı yok")).toBeNull();
  });

  it("a denial with no `none` option to land on is refused too", () => {
    expect(matchOptionsInWords(associated, "Bulantı yok")).toBeNull();
    expect(matchOptionsInWords(associated, "Terleme yok")).toBeNull();
  });

  it("the verbal negative is refused across its tense forms", () => {
    expect(matchOptionsInWords(associated, "Bulantı hissetmedim")).toBeNull();
    expect(matchOptionsInWords(associated, "Terleme olmuyor")).toBeNull();
    expect(matchOptionsInWords(associated, "Bulantı olmaz")).toBeNull();
    expect(matchOptionsInWords(associated, "Terleme olmamış")).toBeNull();
  });

  it("'değil' and 'hayır' are refused", () => {
    expect(matchOptionsInWords(associated, "Bulantı değil")).toBeNull();
    expect(matchOptionsInWords(question("complaint"), "Hayır, ateş çıkmadı")).toBeNull();
  });

  /**
   * files/04 §8.2 `turkish_negation_adversarial_set`, verbatim — the
   * committed source, so a test built from it is a near-miss negative control
   * by construction. Each phrase is run against EVERY option-bearing authored
   * question: a phrase that inverts anywhere in the vocabulary inverts.
   */
  const ADVERSARIAL_SET = [
    "ağrım yok değil hani",
    "bayılmadım ama bayılacak gibi oldum",
    "kanama yoktu, sadece siyahtı",
  ] as const;

  const optionBearing = [...allQuestions, ...baseLayerQuestions, ...measurementQuestions].filter(
    (q): q is IntakeQuestion & { options: NonNullable<IntakeQuestion["options"]> } =>
      q.options !== undefined && q.options.length > 0,
  );

  it("no phrase in the adversarial set binds any option of any question", () => {
    const bound: string[] = [];
    for (const phrase of ADVERSARIAL_SET) {
      for (const q of optionBearing) {
        const matched = matchOptionsInWords(q, phrase);
        if (matched !== null) {
          bound.push(`"${phrase}" → ${q.id} ${JSON.stringify(matched)}`);
        }
      }
    }
    expect(bound).toEqual([]);
  });
});

describe("matchOptionsInWords — what the guard still accepts", () => {
  it("a bare 'Yok' is the `none` option, because the word IS that label", () => {
    // The negation marker here is not evidence against a reading — it is the
    // declared label itself, spoken alone. Refusing it would refuse the
    // answer the pack authored.
    expect(matchOptionsInWords(question("associated"), "Yok")).toEqual(["none"]);
    expect(matchOptionsInWords(question("associated"), "Şu an yok")).toEqual(["none"]);
  });

  it("a bare 'Hayır' is the `no` option", () => {
    expect(matchOptionsInWords(question("pain_present"), "Hayır")).toEqual(["no"]);
  });

  it("a label that carries its own negation word still binds: 'Belirli bir düzeni yok'", () => {
    expect(matchOptionsInWords(question("trigger"), "Belirli bir düzeni yok")).toEqual([
      "no_pattern",
    ]);
  });

  it("plain affirmatives are untouched", () => {
    expect(matchOptionsInWords(question("complaint"), "Ateş ve ağrı var")).toEqual([
      "pain",
      "fever",
    ]);
    expect(matchOptionsInWords(question("duration"), "Bugun basladi")).toEqual(["today"]);
  });
});

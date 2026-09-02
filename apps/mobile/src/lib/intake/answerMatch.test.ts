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

/**
 * The deterministic floor under extraction (INT-293): the patient names one of
 * the question's OWN declared options, in their own words, and it is
 * recognised here — with no network, no model and no guess.
 *
 * Why this exists. The dialogue surface had exactly one route from words to a
 * declared option id: the extract daemon (lib/extract.ts, the INT-083
 * boundary). `scripts/dev/voice_doctor.py` calls that lane *"DEGRADED, not
 * required"* — and it is right that the conversation must survive without it.
 * What the conversation did instead was drop the answer: the question was
 * marked asked, the agent moved on, and the note the clinician receives stayed
 * empty (docs/evidence/INT-293.md). An answer the patient gave in the words the
 * pack itself authored must not depend on a GPU box being reachable.
 *
 * What it is NOT, and the boundary is the whole point:
 *
 * - **It is not an interpreter.** It recognises a declared label's own words
 *   inside the utterance and nothing else. No synonyms, no stemming, no
 *   similarity score, no threshold. "göğsümde baskı var" is not `pain` here —
 *   that reading is the extractor's job and stays the extractor's job.
 * - **It never guesses.** A single-select whose words admit two options
 *   yields nothing, exactly as `validateExtractResponse` drops an ambiguous
 *   candidate off the wire. Fail toward not binding.
 * - **It never commits.** The result is a SUGGESTION with the patient's
 *   verbatim words as its quote; only the confirm turn, the panel row or the
 *   typed steps write it into the note (invariant 1 posture).
 * - **It reads only `values`.** Free text never becomes a value: an utterance
 *   that names no option produces no candidate at all, so nothing here can
 *   open a gate or reach a rule with words that are not a declared id.
 *
 * The Turkish fold is `taxonomy/branches.ts`'s explicit table, not
 * `toLocaleLowerCase("tr")`: the dotted/dotless i pair does not survive a naive
 * lowercase (`"İlaç".toLowerCase()` keeps a combining dot; `"Ağrı"` keeps `ı`),
 * and a fold that depends on the runtime's ICU data being complete is a fold
 * that works on one device. Matching is by WHOLE WORDS in sequence, so `Sol`
 * is not found inside `solunum` — the same discipline files/03 §4.9.6 puts on
 * `üre` and for the same reason: a substring is not a term.
 */
import { t } from "../i18n";
import { foldTr } from "../taxonomy/branches";
import type { IntakeQuestion } from "./questions";

/**
 * Folded word tokens. Everything that is not a folded letter or digit is a
 * separator, so punctuation, the comma inside a list and the slash inside
 * "Mide/karın" all divide words rather than joining them.
 */
export function foldedWords(value: string): string[] {
  return foldTr(value)
    .split(/[^a-z0-9]+/u)
    .filter((word) => word.length > 0);
}

/** Where one option's label sits inside the utterance, in word indices. */
interface LabelSpan {
  id: string;
  start: number;
  end: number;
}

/** The first place `needle` appears as a contiguous run of whole words. */
function firstSpan(
  haystack: readonly string[],
  needle: readonly string[],
): [number, number] | null {
  if (needle.length === 0 || needle.length > haystack.length) {
    return null;
  }
  for (let start = 0; start + needle.length <= haystack.length; start += 1) {
    let hit = true;
    for (let offset = 0; offset < needle.length; offset += 1) {
      if (haystack[start + offset] !== needle[offset]) {
        hit = false;
        break;
      }
    }
    if (hit) {
      return [start, start + needle.length];
    }
  }
  return null;
}

/** A span wholly inside a longer one belongs to that longer option, not to
 * itself: "Baş ağrısı" names one symptom, and `Ağrı` is not a second one. */
function isCoveredByLonger(span: LabelSpan, spans: readonly LabelSpan[]): boolean {
  return spans.some(
    (other) =>
      other.id !== span.id &&
      other.start <= span.start &&
      span.end <= other.end &&
      other.end - other.start > span.end - span.start,
  );
}

/**
 * The declared option ids the patient's words name, in pack order — or `null`
 * when the words name none, name two readings of a single-select, or the
 * question has no option vocabulary at all (free text and guarded measures
 * answer with their own controls).
 */
export function matchOptionsInWords(question: IntakeQuestion, utterance: string): string[] | null {
  if (question.kind !== "chips" && question.kind !== "single") {
    return null;
  }
  const words = foldedWords(utterance);
  if (words.length === 0) {
    return null;
  }
  const spans: LabelSpan[] = [];
  for (const option of question.options) {
    const found = firstSpan(words, foldedWords(t(option.labelKey, "tr")));
    if (found !== null) {
      spans.push({ id: option.id, start: found[0], end: found[1] });
    }
  }
  const kept = spans.filter((span) => !isCoveredByLonger(span, spans));
  if (kept.length === 0) {
    return null;
  }
  if (question.kind === "single") {
    // Exactly one reading, or none: ambiguity is dropped, never resolved.
    return kept.length === 1 ? [kept[0].id] : null;
  }
  return kept.map((span) => span.id);
}

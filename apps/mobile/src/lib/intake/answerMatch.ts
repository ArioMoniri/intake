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
 * - **It does not read a negated sentence.** Turkish negation is post-posed,
 *   so whole words in sequence turn "Ateş yok" into `fever` — the patient
 *   says they have no fever and the note says fever. A marker outside every
 *   matched label refuses the whole read, and "nothing" alongside a named
 *   finding refuses it too; see `isNegationMarker` for why this is a detector
 *   and never a parser.
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
 * The declared option ids that assert NOTHING — the absence of everything the
 * question asks about, or a refusal to say. They cannot be true at the same
 * time as a named positive finding, so an utterance that produces one of them
 * ALONGSIDE another option has not been read: it has been flattened. "Terleme
 * var, bulantı yok" is sweating asserted, nausea denied and `none` denying
 * both, and no subset of the three is the sentence. The set is the escape
 * vocabulary the pack already declares (`baseLayer.test.ts`'s
 * `every_closed_question_offers_an_escape`), minus `other`, which names a
 * positive finding the pack did not enumerate.
 */
const NOTHING_OPTION_IDS: ReadonlySet<string> = new Set([
  "none",
  "no",
  "not_sure",
  "not_stated",
  "unknown",
  "dont_remember",
  "no_pattern",
  "no_relation",
]);

/**
 * Turkish negation, POST-POSED: the word that cancels the sentence arrives
 * after the thing it cancels, so reading whole words in sequence and stopping
 * there turns *"Ateş yok"* — "I have no fever" — into the `fever` option, and
 * one tap writes **fever** into the clinician's note. A dropped answer is
 * visibly missing; an inverted one looks like data.
 *
 * This is a DETECTOR, not a parser, and the distinction is the whole design.
 * It never decides what a negated sentence means; it decides that the local
 * read has no business answering. Every failure mode is therefore built to
 * fall toward NOT matching: an over-firing detector costs one round trip to
 * the extract lane, which receives the same utterance and can place it
 * properly, while an under-firing one costs a false clinical fact.
 *
 * Two classes, and one that is deliberately absent:
 *
 * - **Lexical**, by folded prefix so the copular and tense tails come free:
 *   `yok` (yoktu, yoktur, yokmuş, yoksa), `değil` (değildi, değilim,
 *   değilse), `hayır`. Nothing in the authored vocabulary begins with these
 *   but the labels that ARE them, and those are handled below.
 * - **Verbal**, `-ma-/-me-` — but ONLY where a TAM morpheme follows it, the
 *   same discipline INT-248 put on `koy(?!m)`: no affirmative finite form
 *   attaches a tense/aspect suffix to a bare `-ma`, so `-madı`, `-mıyor`,
 *   `-maz`, `-mayacak`, `-mamış`, `-mam` and the `-madan` converb are
 *   negatives, while a bare token-final `-ma/-me` is not tested at all.
 * - **Absent, on purpose**: bare `-ma/-me`. It is the productive deverbal
 *   NOUN suffix, and the authored vocabulary is full of it — `Kanama`,
 *   `Terleme`, `Şişme`, `Bulanma`. Testing it would refuse the very options
 *   it is meant to protect. This is INT-248's converb lesson: Turkish
 *   morphology does not survive being guessed at, so the guard only fires
 *   where the morphology is unambiguous.
 *
 * Known residual, stated rather than hidden: the ablative of a `-ma` noun
 * (`kanamadan sonra`, "after the bleeding") satisfies the `-madan` shape and
 * is read as a negative. It over-refuses — which is the direction this whole
 * function is built to fail in — and it cannot reach a label, because labels
 * are bare nouns.
 */
const NEGATED_VERB = /m[ae]d(?:i|[ae]n)|m[ae]mis|m[ae]m$|m[iu]yor|m[ae]y[ae]c|m[ae]z(?:$|[sdklm])/u;

/** Whether one folded word can carry a negation. Whole words only — the same
 * rule the label match itself follows, because a substring is not a term. */
export function isNegationMarker(word: string): boolean {
  return (
    word.startsWith("yok") ||
    word.startsWith("degil") ||
    word.startsWith("hayir") ||
    NEGATED_VERB.test(word)
  );
}

/**
 * The declared option ids the patient's words name, in pack order — or `null`
 * when the words name none, name two readings of a single-select, carry a
 * negation the local read must not interpret, or the question has no option
 * vocabulary at all (free text and guarded measures answer with their own
 * controls).
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
  // A negation marker OUTSIDE every matched label refuses the whole read.
  // Inside one it is not evidence against anything — it IS the label: `Yok`,
  // `Hayır` and `Belirli bir düzeni yok` are options the pack authored, and
  // an answer spoken in the pack's own words must still bind. Outside one, a
  // marker means the sentence says something about the option that this
  // function cannot read, so it says nothing.
  const escaped = words.some(
    (word, index) =>
      isNegationMarker(word) &&
      !kept.some((span) => span.start <= index && index < span.end),
  );
  if (escaped) {
    return null;
  }
  // "Nothing" and a named finding cannot be one flat set (see
  // NOTHING_OPTION_IDS) — the utterance said something structured and the
  // structure is the extractor's to read.
  if (kept.length > 1 && kept.some((span) => NOTHING_OPTION_IDS.has(span.id))) {
    return null;
  }
  if (question.kind === "single") {
    // Exactly one reading, or none: ambiguity is dropped, never resolved.
    return kept.length === 1 ? [kept[0].id] : null;
  }
  return kept.map((span) => span.id);
}

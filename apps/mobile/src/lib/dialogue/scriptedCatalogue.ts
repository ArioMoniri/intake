/**
 * INT-443: the app's scripted-text catalogue — the server's half of "patient
 * words never reach the vendor" for the texts this app actually speaks.
 *
 * The George route (services/api `dev_voice.py`) admits a `text_tr` only when
 * it is a row of a catalogue the server reads itself (INT-326). The compiled
 * pack manifests are one source, but no pack compiles on today's tree (HB-C1)
 * and the dialogue does not speak pack `text_tr` anyway: it speaks the
 * composition in `speech.ts` over the i18n question catalogue. This module
 * enumerates that composition, and `scriptedCatalogue.test.ts` holds the
 * committed `scriptedCatalogue.tr.json` byte-equal to it, so the server's
 * allow-list cannot drift from what the app says.
 *
 * Only finite, committed, scripted text is listed — never a patient word:
 *
 * - every spoken question as `questionSpeechTr` composes it;
 * - every confirmation the clip store can ask for with no value or exactly
 *   one option (`confirmSpeechTr`). A confirmation naming two or more options
 *   is combinatorial and is not listed; the route refuses it and the client
 *   falls back to the self-hosted lane.
 *
 * A text that any TTS guard would refuse (a numeral of any kind, invariant 22;
 * SSML or an audio-tag bracket, INT-424) is left out rather than listed. An
 * instrument item's question is pinned to the `instrument` delivery context;
 * every other row is `routine`. Nothing is ever `red`: the RED script is
 * pre-positioned on the device and never fetched (invariant 21).
 */
import {
  allQuestions,
  historyQuestions,
  spokenPack,
  type IntakeQuestion,
} from "../intake/questions";
import type { DeliveryContext } from "./deliveryContext";
import { confirmSpeechTr, questionSpeechTr } from "./speech";

/** One admitted text and the one delivery context it may be spoken in. */
export interface ScriptedCatalogueRow {
  subject: string;
  text_tr: string;
  delivery_context: Exclude<DeliveryContext, "red">;
}

export interface ScriptedCatalogue {
  version: 1;
  locale: "tr";
  source: string;
  rows: ScriptedCatalogueRow[];
}

/** Any Unicode number, or the markup brackets the server's guard refuses. */
const UNSPEAKABLE = /[\p{N}<>[\]]/u;

export const CATALOGUE_SOURCE =
  "apps/mobile/src/lib/dialogue/scriptedCatalogue.ts (speech.ts over the intake question catalogue)";

function spokenQuestions(): IntakeQuestion[] {
  const seen = new Set<string>();
  const out: IntakeQuestion[] = [];
  for (const question of [...spokenPack(allQuestions), ...spokenPack(historyQuestions)]) {
    if (!seen.has(question.id)) {
      seen.add(question.id);
      out.push(question);
    }
  }
  return out;
}

/** The catalogue, rows sorted by subject (code-unit order, locale-free). */
export function buildScriptedCatalogue(): ScriptedCatalogue {
  const byText = new Map<string, ScriptedCatalogueRow>();
  const add = (
    subject: string,
    text: string,
    context: ScriptedCatalogueRow["delivery_context"],
  ) => {
    if (text.trim().length === 0 || UNSPEAKABLE.test(text)) {
      return;
    }
    const existing = byText.get(text);
    if (
      existing === undefined ||
      (context === "instrument" && existing.delivery_context !== "instrument")
    ) {
      // one row per text; an instrument item's pin wins over a routine use
      byText.set(text, { subject, text_tr: text, delivery_context: context });
    }
  };
  for (const question of spokenQuestions()) {
    add(
      `question.${question.id}`,
      questionSpeechTr(question),
      question.instrument ? "instrument" : "routine",
    );
    // a confirmation is a dialogue line, not the validated item: routine
    add(`confirm.${question.id}`, confirmSpeechTr(question, []), "routine");
    for (const option of question.options ?? []) {
      add(`confirm.${question.id}.${option.id}`, confirmSpeechTr(question, [option.id]), "routine");
    }
  }
  const rows = [...byText.values()].sort((a, b) =>
    a.subject < b.subject ? -1 : a.subject > b.subject ? 1 : 0,
  );
  return { version: 1, locale: "tr", source: CATALOGUE_SOURCE, rows };
}

/** The committed file's exact bytes. */
export function serialiseScriptedCatalogue(catalogue: ScriptedCatalogue): string {
  return `${JSON.stringify(catalogue, null, 2)}\n`;
}

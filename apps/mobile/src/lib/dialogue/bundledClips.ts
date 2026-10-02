/**
 * Bundled agent-voice clips (INT-440, ADR-028 offline clip-gen). Pure and
 * node-testable; the Metro asset context lives in bundledClipAssets.ts.
 *
 * The fast path for the owner's "robotic and laggy": the scripted lines the
 * dev dialogue speaks are rendered ONCE, offline, in George's voice on
 * `eleven_multilingual_v2` under the delivery profile of their context
 * (scripts/voice/render_bundled_clips.py), and the app plays the rendered clip
 * from its own bundle. No synthesis on the turn, no network on the turn.
 *
 * What may be rendered is exactly {@link bundledClipSet}: the composition the
 * app itself speaks (speech.ts) over the dev test visits' packs. Catalogue text
 * only — `questionSpeechTr`, the generic text confirm line, and option
 * read-backs built from catalogue labels; never the patient's own words
 * (invariants 2/10) — and every line passes the invariant-22 numeral guard
 * before it is listed. The committed bundledClipSet.json is that list; a test
 * holds it equal to this function, so the render can never be handed a line
 * the app does not say.
 *
 * A clip is addressed by its delivery context and `clip_text_hash`
 * (protocols.dsl: sha256 of the NFC text, hex — the ADR-028 manifest key), as
 * the server's clip cache is: `<context>/<hash>.wav`. The same words in two
 * contexts are two clips, because the profiles differ.
 */
import { sha256 } from "@noble/hashes/sha2.js";
import { bytesToHex, utf8ToBytes } from "@noble/hashes/utils.js";

import { DELIVERY_CONTEXTS, type DeliveryContext } from "./deliveryContext";
import { packForVisit, spokenPack, type IntakeMode } from "../intake/questions";
import { confirmSpeechTr, questionSpeechTr } from "./speech";
import { assertSpeakableTr } from "./tts";

/** The departments of the dev test visits (lib/dev/accounts.ts) — what a
 * simulator run actually asks. */
export const BUNDLED_CLIP_DEPARTMENTS: readonly string[] = [
  "İç Hastalıkları",
  "Kulak Burun Boğaz Hastalıkları",
];

const MODES: readonly IntakeMode[] = ["hizli", "detayli"];

/** One line to render: the words and the context they are delivered in. */
export interface BundledClipLine {
  readonly context: DeliveryContext;
  readonly text_tr: string;
}

/** sha256 of the NFC text, lower-case hex — protocols.dsl `clip_text_hash`. */
export function clipTextHash(text: string): string {
  return bytesToHex(sha256(utf8ToBytes(text.normalize("NFC"))));
}

/** The bundle address of one line: `<context>/<clip_text_hash>`. */
export function bundledClipAddress(text: string, context: DeliveryContext): string {
  return `${context}/${clipTextHash(text)}`;
}

function byContextThenText(a: BundledClipLine, b: BundledClipLine): number {
  if (a.context !== b.context) {
    return a.context < b.context ? -1 : 1;
  }
  return a.text_tr < b.text_tr ? -1 : a.text_tr > b.text_tr ? 1 : 0;
}

/**
 * Every scripted line the dev dialogue can speak for the given departments,
 * once per (context, text), in a stable order. Questions and confirms are
 * requested under `routine` (useDialogueSession → clips.ts).
 */
export function bundledClipSet(
  departments: readonly string[] = BUNDLED_CLIP_DEPARTMENTS,
): BundledClipLine[] {
  const lines = new Map<string, BundledClipLine>();
  const add = (context: DeliveryContext, text_tr: string) => {
    assertSpeakableTr(text_tr); // invariant 22 — a numeral is never listed
    lines.set(`${context}\u0000${text_tr}`, { context, text_tr });
  };
  for (const department of departments) {
    for (const mode of MODES) {
      for (const question of spokenPack(packForVisit(department, { mode }))) {
        add("routine", questionSpeechTr(question));
        // The confirm turn's line. A text step has one generic line (patient
        // words are never synthesized); an option step reads back catalogue
        // LABELS, so each single-option read-back and the bare ask are fixed
        // catalogue strings too. Multi-option read-backs are combinations and
        // stay on the live lanes.
        add("routine", confirmSpeechTr(question, []));
        if (question.kind === "chips" || question.kind === "single") {
          for (const option of question.options) {
            add("routine", confirmSpeechTr(question, [option.id]));
          }
        }
      }
    }
  }
  return [...lines.values()].sort(byContextThenText);
}

/** The bundled asset for a line in its context, or null. */
export function bundledClipFor<T>(
  text: string,
  context: DeliveryContext,
  assets: ReadonlyMap<string, T>,
): T | null {
  return assets.get(bundledClipAddress(text, context)) ?? null;
}

/** `./<context>/<hash>.wav` → `<context>/<hash>`, for the Metro asset
 * context's file names; null for any name that is not a clip of a known
 * context (a stray file is ignored, never guessed at). */
export function bundledClipAddressFromFile(file: string): string | null {
  const match = /(?:^|\/)([a-z]+)\/([0-9a-f]{64})\.wav$/.exec(file);
  if (match === null || !(DELIVERY_CONTEXTS as readonly string[]).includes(match[1])) {
    return null;
  }
  return `${match[1]}/${match[2]}`;
}

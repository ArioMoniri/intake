/**
 * Confirm cards and their source boxes, client side (INT-138).
 *
 * INT-121 built the server half: a document becomes an `UnconfirmedRecordItem`
 * with a defaultless `SourceBox`, and `confirm_record_item` is the one bridge
 * to something a note or the FHIR boundary will accept. It takes no `by=` —
 * the actor is read off a closed vocabulary rather than passed by a caller who
 * could pass something else — and it carries the observation over unchanged,
 * because *confirming is agreeing with what was extracted, never restating it*.
 *
 * This module is the client half of that sentence, and it keeps three
 * properties the screen could otherwise quietly lose:
 *
 * 1. **A value with no source box is not a card.** The server refuses to write
 *    one down; this refuses to draw one.
 * 2. **A document may not triage** (CLAUDE.md invariant 1). A level-shaped key
 *    refuses the extraction WHOLE, exactly as `extract_record_items` does —
 *    dropping the offending key and keeping the rest is how the remainder of a
 *    hallucinated answer gets through.
 * 3. **The client is a courier for the number, not a second renderer**
 *    (invariant 22). `summary` arrives already rendered: `useGrouping:false`,
 *    plain positional notation, number and unit joined by a NO-BREAK SPACE.
 *    There is no number parser and no number formatter in this file, and a
 *    test asserts their absence — `1.500` reads two ways (files/03 §4.9.6) and
 *    a second reading of it on this side would differ by a factor of 1000.
 *
 * **Nothing publishes this feed yet.** No API route serves document extraction
 * and no route accepts a confirmation; the producer is INT-124 (the extraction
 * LLM, P2) and the transport that would carry its output belongs to an issue
 * that does not exist. So the only production `ExtractionSource` is
 * `noExtractionFeed`, which answers "not read" and acknowledges nothing — the
 * same fail-closed seam `NoLayout` and `NoTerminology` already are on the
 * server. The mechanism is built, the gate is wired, and it fails closed with
 * the content empty (HUMAN_BLOCKERS.md rule 2).
 */
import { NBSP } from "@/lib/health/format";
import { t } from "@/lib/i18n";

/**
 * `RecordItemKind` from `packages/clinical-schemas` (generated `models.ts`),
 * mirrored member-for-member; a test compares the two.
 */
export type RecordItemKind =
  "lab" | "imaging" | "procedure" | "medication" | "diagnosis" | "allergy";

export const RECORD_ITEM_KINDS: readonly RecordItemKind[] = [
  "lab",
  "imaging",
  "procedure",
  "medication",
  "diagnosis",
  "allergy",
];

/**
 * `intake_platform.records.LEVEL_SHAPED_KEYS`, mirrored. A key naming a triage
 * level, a RED axis or a delivery priority is refused SPECIFICALLY, so the
 * failure reads "the document tried to triage" rather than "an unknown key".
 */
export const LEVEL_SHAPED_KEYS: readonly string[] = [
  "level",
  "triage",
  "priority",
  "preempt",
  "register",
  "severity",
  "urgency",
  "acuity",
  "triage_level",
];

/** Everything an item may declare. Closed, like the server's `ITEM_KEYS`. */
const ITEM_KEYS: readonly string[] = [
  "id",
  "kind",
  "summary",
  "unit_conflict",
  "date",
  "provenance",
];

const FEED_STATES: readonly string[] = ["read", "reading", "unread"];

/** Where on which page a value came from, normalised to the page (0…1). */
export interface SourceBox {
  documentRef: string;
  page: number;
  bbox: readonly [number, number, number, number];
}

/**
 * What the app puts in front of the patient, and nothing more — the mobile
 * mirror of `clinical_schemas.record_extraction.ConfirmCard`. There is no
 * field a confirmation, a triage level or a clinical interpretation could
 * occupy: the card asks *does this say what your report says?* and nothing else.
 *
 * `summary` is the document's own line. It is not authored patient copy, so it
 * carries no `tr` resource key, and it is never re-worded or re-formatted.
 */
export interface ConfirmCardModel {
  id: string;
  kind: RecordItemKind;
  summary: string;
  box: SourceBox;
  unitConflict: boolean;
  date: string | null;
}

/**
 * What a patient may say about a card. Two members, and the missing third is
 * the design: a patient who disagrees produces a REFUSAL, not an edited
 * extraction, because `confirm_record_item` has no path that takes a restated
 * value. It is also INT-133's `FactOutcome` shape — disagreement recorded
 * without capturing a replacement.
 */
export type CardDecision = "confirmed" | "declined";

/** What the app knows about a card right now. `pending` until a write lands. */
export type CardState = "pending" | "confirmed" | "declined";

export type ExtractionFeed =
  | { kind: "cards"; cards: ConfirmCardModel[] }
  | { kind: "reading" }
  | { kind: "unread" }
  | { kind: "refused" };

// --- parsing ---------------------------------------------------------------------------------

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readBox(raw: unknown): SourceBox | null {
  if (!isRecord(raw)) {
    return null;
  }
  const { document_ref: ref, page, bbox } = raw;
  if (typeof ref !== "string" || ref.trim() === "") {
    return null;
  }
  if (typeof page !== "number" || !Number.isInteger(page) || page < 1) {
    return null;
  }
  if (!Array.isArray(bbox) || bbox.length !== 4 || bbox.some((n) => typeof n !== "number")) {
    return null;
  }
  const [x0, y0, x1, y1] = bbox as [number, number, number, number];
  if ([x0, y0, x1, y1].some((n) => n < 0 || n > 1)) {
    return null; // a rectangle outside the page points at nothing checkable
  }
  if (x1 <= x0 || y1 <= y0) {
    return null; // inverted or empty: it encloses no area
  }
  return { documentRef: ref.trim(), page, bbox: [x0, y0, x1, y1] };
}

function readCard(raw: unknown): ConfirmCardModel | null {
  if (!isRecord(raw)) {
    return null;
  }
  for (const key of Object.keys(raw)) {
    if (!ITEM_KEYS.includes(key)) {
      return null; // closed key set — refused whole, never trimmed
    }
  }
  const kind = RECORD_ITEM_KINDS.find((member) => member === raw.kind);
  const box = readBox(raw.provenance);
  if (kind === undefined || box === null) {
    return null;
  }
  if (typeof raw.id !== "string" || raw.id.trim() === "") {
    return null;
  }
  if (typeof raw.summary !== "string" || raw.summary.trim() === "") {
    return null; // nothing to agree with
  }
  if (raw.unit_conflict !== undefined && typeof raw.unit_conflict !== "boolean") {
    return null;
  }
  if (raw.date !== undefined && raw.date !== null && typeof raw.date !== "string") {
    return null;
  }
  return {
    id: raw.id,
    kind,
    // verbatim: whatever the server rendered is what the patient is shown
    summary: raw.summary,
    box,
    unitConflict: raw.unit_conflict === true,
    date: typeof raw.date === "string" ? raw.date : null,
  };
}

/**
 * One extraction payload → a feed. Every failure is `refused`: no message here
 * names a printed value, a magnitude or a line of the document, because an
 * exception message reaches a log (invariant 6).
 */
export function parseExtraction(raw: unknown): ExtractionFeed {
  if (!isRecord(raw) || typeof raw.state !== "string" || !FEED_STATES.includes(raw.state)) {
    return { kind: "refused" };
  }
  if (raw.state === "reading") {
    return { kind: "reading" };
  }
  if (raw.state === "unread") {
    return { kind: "unread" };
  }
  if (!Array.isArray(raw.items)) {
    return { kind: "refused" };
  }
  const cards: ConfirmCardModel[] = [];
  for (const entry of raw.items) {
    if (isRecord(entry) && Object.keys(entry).some((key) => LEVEL_SHAPED_KEYS.includes(key))) {
      return { kind: "refused" };
    }
    const card = readCard(entry);
    if (card === null) {
      return { kind: "refused" };
    }
    cards.push(card);
  }
  return { kind: "cards", cards };
}

// --- the confirmation, and what may travel with it -------------------------------------------

/**
 * The confirmation body: which card, and the patient's verdict. Nothing else,
 * and in particular no magnitude and no unit — the server carries the
 * observation over unchanged, so a value sent from here could only disagree
 * with the one being confirmed.
 */
export function decisionBody(
  cardId: string,
  decision: CardDecision,
): { card_id: string; decision: CardDecision } {
  return { card_id: cardId, decision };
}

/**
 * The record of a decision, applied only when the write was ACKNOWLEDGED.
 *
 * There is no optimistic path, deliberately: INT-140 took the same line on the
 * erasure screens, and the cost of a wrong "confirmed" here is a value the
 * patient believes they checked sitting in a clinician's note.
 */
export function applyDecision(
  states: Readonly<Record<string, CardState>>,
  cardId: string,
  decision: CardDecision,
  acknowledged: boolean,
): Record<string, CardState> {
  if (!acknowledged) {
    return { ...states };
  }
  return { ...states, [cardId]: decision };
}

/** How many of these cards still await the patient. */
export function pendingCount(
  cardIds: readonly string[],
  states: Readonly<Record<string, CardState>>,
): number {
  return cardIds.filter((id) => (states[id] ?? "pending") === "pending").length;
}

// --- the provenance locator ------------------------------------------------------------------

function percent(value: number): string {
  return `${Math.round(value * 1000) / 10}%`;
}

/** The normalised box as offsets into a page-shaped frame. */
export function boxFrame(bbox: readonly [number, number, number, number]): {
  left: string;
  top: string;
  width: string;
  height: string;
} {
  const [x0, y0, x1, y1] = bbox;
  return {
    left: percent(x0),
    top: percent(y0),
    width: percent(x1 - x0),
    height: percent(y1 - y0),
  };
}

/**
 * Where the box sits on the page, in words. A rectangle is invisible to a
 * screen reader, and "somewhere on page 2" is not provenance.
 */
export function boxRegionKey(
  bbox: readonly [number, number, number, number],
): "records.prov.top" | "records.prov.middle" | "records.prov.bottom" {
  const middle = (bbox[1] + bbox[3]) / 2;
  if (middle < 1 / 3) {
    return "records.prov.top";
  }
  return middle < 2 / 3 ? "records.prov.middle" : "records.prov.bottom";
}

/**
 * `Sayfa␣2` — the word and the number as one non-breaking atom, ungrouped.
 * A page is not a clinical quantity, but one rendering rule for numbers on a
 * screen is cheaper than two, and `1.200` is the exact shape files/03 §4.9.6
 * calls ambiguous.
 */
export function pageAtom(page: number): string {
  return `${t("records.prov.page")}${NBSP}${page}`;
}

// --- the seam --------------------------------------------------------------------------------

/** Where a feed and a confirmation arrive through. */
export interface ExtractionSource {
  read(visitId: string, documentId: string): Promise<ExtractionFeed>;
  record(
    visitId: string,
    documentId: string,
    cardId: string,
    decision: CardDecision,
  ): Promise<boolean>;
}

/**
 * The only production source, and it refuses. No route publishes document
 * extraction and none accepts a confirmation, so answering anything else would
 * be inventing a feed; `record` acknowledges nothing, which — with
 * `applyDecision`'s no-optimistic-write rule — means no card can ever show as
 * confirmed while this is the source. Reopen against INT-124 and the transport
 * issue that carries its output.
 */
export const noExtractionFeed: ExtractionSource = {
  read(): Promise<ExtractionFeed> {
    return Promise.resolve({ kind: "unread" });
  },
  record(): Promise<boolean> {
    return Promise.resolve(false);
  },
};

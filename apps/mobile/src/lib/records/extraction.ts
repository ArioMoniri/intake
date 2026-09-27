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
 * **The feed arrives over one route and a verdict leaves over another**
 * (`records/api.ts`, `apiExtractionSource`). The fail-closed default is the
 * server's: its source answers `unread` for every document while every
 * producer is shut, so this module holds no second gate that could disagree
 * with it. What it holds instead is the rule that a card is settled only when
 * the server echoes the verdict (`isAcknowledgement`), and the backoff with
 * which a document still being read is asked about again (`pollDelayMs`).
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
  "decision",
];

/** The route's closed `state`. `refused` is the server's own refusal (invariant 14). */
const FEED_STATES: readonly string[] = ["read", "reading", "unread", "refused"];

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
  /** The verdict the server already holds for this card, if any. */
  decision: CardDecision | null;
}

/**
 * What a patient may say about a card. Two members, and the missing third is
 * the design: a patient who disagrees produces a REFUSAL, not an edited
 * extraction, because `confirm_record_item` has no path that takes a restated
 * value. It is also INT-133's `FactOutcome` shape — disagreement recorded
 * without capturing a replacement.
 */
export type CardDecision = "confirmed" | "declined";

const CARD_DECISIONS: readonly CardDecision[] = ["confirmed", "declined"];

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
  const decision =
    raw.decision === undefined || raw.decision === null
      ? null
      : (CARD_DECISIONS.find((member) => member === raw.decision) ?? undefined);
  if (decision === undefined) {
    return null; // a verdict the server cannot hold is not one to show
  }
  return {
    id: raw.id,
    kind,
    // verbatim: whatever the server rendered is what the patient is shown
    summary: raw.summary,
    box,
    unitConflict: raw.unit_conflict === true,
    date: typeof raw.date === "string" ? raw.date : null,
    decision,
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
  if (raw.state === "refused") {
    return { kind: "refused" };
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

/**
 * What a card shows: a verdict acknowledged in this session first, then the
 * one the server already held when it was read, and otherwise pending. Both
 * sources are server acknowledgements — nothing here is a local guess.
 */
export function cardStateOf(
  states: Readonly<Record<string, CardState>>,
  card: Pick<ConfirmCardModel, "id" | "decision">,
): CardState {
  return states[card.id] ?? card.decision ?? "pending";
}

/**
 * Whether a response to a verdict IS an acknowledgement of that verdict: the
 * server echoes the card and the decision it recorded. A success that names
 * another card or another verdict, or names nothing, did not record this one.
 */
export function isAcknowledgement(body: unknown, cardId: string, decision: CardDecision): boolean {
  return isRecord(body) && body.card_id === cardId && body.decision === decision;
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

// --- processing: asking again about a document still being read -----------------------------

/**
 * The waits between asks, in milliseconds. Doubling from two seconds to a
 * half-minute ceiling, then a few more at the ceiling, then stop: about two
 * and a half minutes in all. A document still being read after that keeps its
 * "reading" line, and the next visit to the screen asks again — a phone that
 * polled a server forever from a backgrounded tab would be the worse failure.
 */
const POLL_DELAYS_MS: readonly number[] = [2000, 4000, 8000, 16000, 30000, 30000, 30000, 30000];

/** The wait before ask number `attempt + 1`, or `null` when it is time to stop. */
export function pollDelayMs(attempt: number): number | null {
  return POLL_DELAYS_MS[attempt] ?? null;
}

/**
 * One round of asking. `feeds` holds every answer that came back; `again`
 * names what is still being read and what could not be asked at all. A read
 * that failed is not an answer, so it shows nothing and is asked again rather
 * than drawn as "not read".
 */
export async function readRound(
  source: ExtractionSource,
  visitId: string,
  documentIds: readonly string[],
): Promise<{ feeds: Record<string, ExtractionFeed>; again: string[] }> {
  const feeds: Record<string, ExtractionFeed> = {};
  const again: string[] = [];
  for (const documentId of documentIds) {
    try {
      const feed = await source.read(visitId, documentId);
      feeds[documentId] = feed;
      if (feed.kind === "reading") {
        again.push(documentId);
      }
    } catch {
      again.push(documentId);
    }
  }
  return { feeds, again };
}

/**
 * Ask about these documents, then ask again — with `pollDelayMs` between
 * rounds — about whatever is still being read, handing each round's answers
 * to `onFeeds`. Returns the function that stops it; nothing is asked or
 * handed over after that.
 *
 * The timer lives here rather than in the section that renders the answers so
 * a unit test can drive it on a fake clock. It is a wait, not a time limit:
 * when the asking stops, nothing is taken from the patient (SC 2.2.1).
 */
export function pollExtraction(
  source: ExtractionSource,
  visitId: string,
  documentIds: readonly string[],
  onFeeds: (feeds: Record<string, ExtractionFeed>) => void,
): () => void {
  let live = true;
  let timer: ReturnType<typeof setTimeout> | null = null;
  const ask = async (ids: readonly string[], attempt: number): Promise<void> => {
    const round = await readRound(source, visitId, ids);
    if (!live) {
      return;
    }
    onFeeds(round.feeds);
    const delay = pollDelayMs(attempt);
    if (round.again.length > 0 && delay !== null) {
      timer = setTimeout(() => void ask(round.again, attempt + 1), delay);
    }
  };
  void ask(documentIds, 0);
  return () => {
    live = false;
    if (timer !== null) {
      clearTimeout(timer);
    }
  };
}

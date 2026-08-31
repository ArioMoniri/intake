/**
 * Validated instruments on the device (INT-136): the licence gate, and the
 * one place an authored item becomes something a screen can render.
 *
 * CLAUDE.md invariant 10, in its own words: scripted protocol questions,
 * red-flag action scripts and validated instruments are delivered **verbatim**
 * from `text_tr`; paraphrase only where the protocol sets
 * `allow_paraphrase: true`, which an instrument item never does. files/04's
 * header says the same thing from the clinical side and adds the half that is
 * easy to miss — *"an LLM may not infer a score from narrative"*, and
 * *"response options are presented verbatim and require an explicit
 * selection"*. A PHQ-9 whose items were reworded, or whose result was
 * concluded from prose, is not the PHQ-9 and the Turkish validation no longer
 * refers to it.
 *
 * Three consequences shape this module, and each one is a thing it refuses to
 * do rather than a thing it does.
 *
 * **Item text is not a catalog string.** Nothing here imports the i18n
 * catalog. A `MessageKey` would give every item an `en` mirror maintained
 * beside the Turkish, which is a translation this project has no rights to
 * make (files/04: a translation is an *işlenme eser* with its own rights
 * holder under FSEK 5846) and a paraphrase surface invariant 10 forbids. Item
 * text arrives as `textTr` and leaves as `textTr`, the same string object.
 *
 * **A non-GO licence is a wall, not a warning.** `INSTRUMENT_LICENCES` mirrors
 * `packages/protocols/src/protocols/licences.py` row for row, fails closed to
 * `UNKNOWN`, and `resolveInstrument` refuses anything that is not `GO` —
 * before it looks at whether items exist at all. C-SSRS is licence-BLOCKED
 * (HB-L2: Clario holds the exclusive RFMH electronic licence) and WHO-5 is
 * licence-BLOCKED (HB-L3: CC BY-NC-SA 3.0 IGO, NonCommercial with a
 * ShareAlike copyleft that reaches any adaptation, and reformatting for
 * mobile counts). Neither may render anywhere, and handing this module a full
 * set of items for either does not open the gate.
 *
 * **No instrument has items today, and none was invented.**
 * `packages/protocols/base/intake.yaml` states it in its own comment:
 * *"Instrument ITEM text is not authored here: the verbatim Turkish items
 * belong to the instrument engine (INT-116), and an item reworded by anyone
 * is no longer the instrument its validation refers to."* No verbatim Turkish
 * item text exists anywhere in this repository, so `INSTRUMENT_ITEMS` is
 * empty, every lookup refuses with `items_not_authored`, and every surface
 * that asks gets nothing to draw (HUMAN_BLOCKERS Rule 2 — build the
 * mechanism, wire the gate, make it fail closed, leave the content empty).
 *
 * What this module deliberately does NOT contain: any scoring, any threshold,
 * any interpretation, and any sentence describing an instrument's measurement
 * properties. Scoring belongs to the instrument engine (INT-116); measurement
 * claims belong to docs/evidence with a date and a named corpus and to
 * nowhere else (invariant 20).
 */

/** The verdicts of the files/04 header table, plus the fail-closed default. */
export type InstrumentLicence = "GO" | "NEEDS_PERMISSION" | "BLOCKED" | "UNKNOWN";

/** Registry spellings, exactly as the files/04 header table spells them. */
export type InstrumentId = "PHQ-9" | "PHQ-2" | "GAD-7" | "GAD-2" | "C-SSRS" | "WHO-5" | "HAQ-DI";

export type LicenceTable = Readonly<Record<string, InstrumentLicence>>;

/**
 * Mirrors `packages/protocols/src/protocols/licences.py`, and
 * `e2e/typed_intake.spec.ts` parses that file and compares the two so the
 * mirror cannot go stale. The citations live in the Python source and in the
 * files/04 header; they are not restated here, because two copies of a
 * licence argument is how one of them ends up wrong.
 */
export const INSTRUMENT_LICENCES: LicenceTable = {
  "PHQ-9": "GO",
  "PHQ-2": "GO",
  "GAD-7": "GO",
  "GAD-2": "GO",
  "C-SSRS": "BLOCKED",
  "WHO-5": "BLOCKED",
  "HAQ-DI": "NEEDS_PERMISSION",
};

/** Look up a licence, failing closed: never recorded means never allowed. */
export function instrumentLicence(id: string, registry: LicenceTable = INSTRUMENT_LICENCES): InstrumentLicence {
  return registry[id] ?? "UNKNOWN";
}

/**
 * One instrument item, in the shape `packages/protocols` `InstrumentItem`
 * already uses: a stable id, the verbatim Turkish, and a paraphrase
 * permission that is `false` at the type level rather than by convention.
 */
export interface InstrumentItem {
  readonly id: string;
  /** The authored Turkish, byte for byte. Never a catalog key. */
  readonly textTr: string;
  /** Always false for a validated instrument (files/04 §1). */
  readonly allowParaphrase: false;
  /** The authored response options, verbatim and in authored order. */
  readonly choicesTr: readonly string[];
}

export type ItemRegistry = Readonly<Partial<Record<string, readonly InstrumentItem[]>>>;

/**
 * The authored items — empty, and that is the delivered state.
 *
 * See the module header: no verbatim Turkish instrument item exists in this
 * repository, INT-116 owns them, and inventing one would produce a document
 * that reads as authoritative with no diff showing it wrong (HUMAN_BLOCKERS
 * Rule 1). The moment items are committed here, every surface below starts
 * rendering them without another change.
 */
export const INSTRUMENT_ITEMS: ItemRegistry = {};

/** Why an instrument cannot be rendered. Both reasons are permanent today. */
export type InstrumentRefusal = "licence_not_go" | "items_not_authored";

export class InstrumentUnavailable extends Error {
  readonly instrumentId: string;
  readonly reason: InstrumentRefusal;

  constructor(instrumentId: string, reason: InstrumentRefusal, detail: string) {
    super(`${instrumentId}: ${detail}`);
    this.name = "InstrumentUnavailable";
    this.instrumentId = instrumentId;
    this.reason = reason;
  }
}

export interface InstrumentLookup {
  readonly licences?: LicenceTable;
  readonly items?: ItemRegistry;
}

/**
 * The items a surface may render, or a refusal naming which wall it hit.
 *
 * Licence first, always. Checking content first would let a BLOCKED
 * instrument with no items report `items_not_authored`, and the day someone
 * authored them the refusal would silently change meaning.
 */
export function resolveInstrument(
  id: InstrumentId,
  lookup: InstrumentLookup = {},
): readonly InstrumentItem[] {
  const licence = instrumentLicence(id, lookup.licences ?? INSTRUMENT_LICENCES);
  if (licence !== "GO") {
    throw new InstrumentUnavailable(
      id,
      "licence_not_go",
      `licence is ${licence}, not GO — it does not render, failing closed ` +
        "(files/04 header table; HUMAN_BLOCKERS HB-L2, HB-L3)",
    );
  }
  const items = (lookup.items ?? INSTRUMENT_ITEMS)[id] ?? [];
  if (items.length === 0) {
    throw new InstrumentUnavailable(
      id,
      "items_not_authored",
      "no verbatim Turkish items are authored — they belong to the instrument " +
        "engine (INT-116) and none was invented here",
    );
  }
  return items;
}

/**
 * The same question asked without an exception: what may this surface draw?
 *
 * `null` means draw nothing at all — not an empty frame and not an apology.
 * An instrument the patient was never going to be offered should leave no
 * trace on their screen, and a surface that has to remember to check a flag
 * is a surface that will one day forget.
 */
export function instrumentOffer(
  id: InstrumentId,
  lookup: InstrumentLookup = {},
): readonly InstrumentItem[] | null {
  try {
    return resolveInstrument(id, lookup);
  } catch (error) {
    if (error instanceof InstrumentUnavailable) {
      return null;
    }
    throw error;
  }
}

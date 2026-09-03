/**
 * Validated instruments on the typed surface (INT-136) — a licence gate and a
 * verbatim carrier, with no instrument content in it.
 *
 * CLAUDE.md invariant 10: *"validated instruments are spoken verbatim from
 * `text_tr`; paraphrase only where the protocol sets `allow_paraphrase:
 * true`"*, and the clinical content rules add *"conversational delivery may
 * paraphrase the lead-in, never the item"*. An item that has been reworded is
 * not that instrument any more, so the only thing this module is allowed to do
 * with an item's words is hand them on unchanged.
 *
 * That is why there is no `t()` in this file and no `MessageKey` anywhere in
 * its types. The app's catalogue is the app's own copy; an instrument's item
 * text belongs to the pack, and routing it through a second store would make
 * the app the place the wording is decided. `docs/evidence/INT-136.md` records
 * the consequence for review: the only assertion of verbatimness worth having
 * compares the app to `packages/protocols`, never to itself.
 *
 * ── What is here today, and why it is empty ─────────────────────────────────
 * `INSTRUMENT_ITEMS` is `{}`. Three independent reasons, none of them fixable
 * in this repo:
 *
 *   - **HB-C1** — the `clinical_signoff` block of the packs is unsigned, so no
 *     pack is servable at all. docs/evidence/INT-096.md F4 measured it: all 93
 *     committed packs are `maturity: L0`, `packages/protocols/dist/` holds only
 *     `.gitkeep`, and `base.intake` refuses with `PACK_NOT_SERVABLE`.
 *   - **HB-L2 / HB-L3** — C-SSRS and WHO-5 are licence-BLOCKED. A pack that
 *     references a non-`GO` instrument must fail the build.
 *   - `packages/protocols/base/intake.yaml` states the third itself: *"Instrument
 *     ITEM text is not authored here: the verbatim Turkish items belong to the
 *     instrument engine (INT-116)"*.
 *
 * An empty registry is therefore the CORRECT state, and the mechanism is built
 * around that rather than despite it: every entry point refuses, the refusal
 * carries a reason a screen can render, and nothing anywhere falls back to an
 * app-authored string.
 *
 * The licence table mirrors `packages/protocols/src/protocols/licences.py` row
 * for row; `apps/mobile/e2e/typed_intake.spec.ts` parses the Python and fails
 * on drift, so this copy cannot quietly diverge from the one the compiler uses.
 */

/** The verdicts of the files/04 header table, plus the fail-closed default. */
export type InstrumentLicence = "GO" | "NEEDS_PERMISSION" | "BLOCKED" | "UNKNOWN";

/** An instrument-licence lookup table (id → verdict); tests may inject one. */
export type LicenceTable = Readonly<Record<string, InstrumentLicence>>;

export const INSTRUMENT_LICENCES: LicenceTable = {
  // files/04 header: Pfizer's blanket permission covers PHQ/GAD.
  "PHQ-9": "GO",
  "PHQ-2": "GO",
  "GAD-7": "GO",
  "GAD-2": "GO",
  // HB-L2: Clario holds the exclusive RFMH electronic licence.
  "C-SSRS": "BLOCKED",
  // HB-L3: CC BY-NC-SA 3.0 IGO since 2024 — NonCommercial.
  "WHO-5": "BLOCKED",
  // HB-L4: Stanford's permission covers the English version only.
  "HAQ-DI": "NEEDS_PERMISSION",
};

/**
 * Look up an instrument's licence, failing closed to `UNKNOWN`.
 *
 * `Object.hasOwn` rather than bracket access with `??`: a plain object literal
 * answers `constructor`, `toString` and `valueOf` from `Object.prototype`, so
 * the nullish fallback never fires for those names and the lookup would return
 * a function where the caller expects a verdict.
 */
export function instrumentLicence(
  instrumentId: string,
  table: LicenceTable = INSTRUMENT_LICENCES,
): InstrumentLicence {
  return Object.hasOwn(table, instrumentId) ? table[instrumentId] : "UNKNOWN";
}

/**
 * One instrument item as the pack carries it — `dsl.py InstrumentItem` plus the
 * response options the section authors beside it.
 *
 * `allowParaphrase` is the literal `false`, not `boolean`: files/04 §1 requires
 * it to be exactly false on an instrument item, so `true` is a compile error
 * here rather than a validator finding.
 *
 * `choicesTr` is the verbatim Turkish response set. It is on this record and
 * not derived from the app's catalogue for the same reason `textTr` is: a
 * PHQ-9 item's options are validated content, and re-labelling them in the app
 * changes what the patient was asked.
 */
export interface InstrumentItem {
  readonly id: string;
  readonly textTr: string;
  readonly allowParaphrase: false;
  readonly choicesTr: readonly string[];
}

export type ItemRegistry = Readonly<Record<string, readonly InstrumentItem[]>>;

/**
 * Empty, and see the header for the three reasons. Nothing is standing in for
 * absent content here: this IS the state the licences and HB-C1 put the
 * product in, and every caller below is written so that authoring the rows is
 * the only change needed.
 */
export const INSTRUMENT_ITEMS: ItemRegistry = {};

export type InstrumentRefusal = "licence_not_go" | "items_not_authored" | "item_not_in_instrument";

/** Why an instrument cannot be administered. Carries no patient-facing copy. */
export class InstrumentUnavailable extends Error {
  readonly instrumentId: string;
  readonly itemId: string | undefined;
  readonly reason: InstrumentRefusal;

  constructor(instrumentId: string, reason: InstrumentRefusal, itemId?: string) {
    super(`instrument_unavailable:${instrumentId}:${reason}`);
    this.name = "InstrumentUnavailable";
    this.instrumentId = instrumentId;
    this.itemId = itemId;
    this.reason = reason;
  }
}

export interface InstrumentLookup {
  readonly licences?: LicenceTable;
  readonly items?: ItemRegistry;
}

export interface InstrumentItemRef {
  readonly instrumentId: string;
  readonly itemId: string;
}

/**
 * The instrument's items, or a refusal.
 *
 * **The licence is checked before the content, and the order is the point.**
 * With an empty registry both orders refuse, so nothing today distinguishes
 * them — but the day someone authors C-SSRS items to "see the layout", the
 * content-first order would render a blocked instrument. `typed_intake.spec.ts`
 * holds the ordering with a fully-authored blocked instrument.
 *
 * The authored array is returned BY REFERENCE. Copying it — mapping, spreading,
 * trimming — is how verbatim quietly stops being verbatim, so the caller gets
 * the pack's own records and a byte-identity test can say so.
 */
export function resolveInstrument(
  instrumentId: string,
  lookup: InstrumentLookup = {},
): readonly InstrumentItem[] {
  const licence = instrumentLicence(instrumentId, lookup.licences ?? INSTRUMENT_LICENCES);
  if (licence !== "GO") {
    throw new InstrumentUnavailable(instrumentId, "licence_not_go");
  }
  const registry = lookup.items ?? INSTRUMENT_ITEMS;
  if (!Object.hasOwn(registry, instrumentId)) {
    throw new InstrumentUnavailable(instrumentId, "items_not_authored");
  }
  const items = registry[instrumentId];
  if (items.length === 0) {
    throw new InstrumentUnavailable(instrumentId, "items_not_authored");
  }
  return items;
}

/** One item of an instrument, or a refusal. */
export function resolveInstrumentItem(
  ref: InstrumentItemRef,
  lookup: InstrumentLookup = {},
): InstrumentItem {
  const item = resolveInstrument(ref.instrumentId, lookup).find(
    (candidate) => candidate.id === ref.itemId,
  );
  if (item === undefined) {
    throw new InstrumentUnavailable(ref.instrumentId, "item_not_in_instrument", ref.itemId);
  }
  return item;
}

/**
 * The non-throwing form for a render path: the item, or `null` when it is
 * unavailable.
 *
 * Only `InstrumentUnavailable` is absorbed. A malformed registry is a bug, and
 * a bare `catch` would turn every such bug into a blank card that reads as a
 * blocked instrument — the failure mode this whole module exists to avoid.
 */
export function instrumentItemOffer(
  ref: InstrumentItemRef,
  lookup: InstrumentLookup = {},
): InstrumentItem | null {
  try {
    return resolveInstrumentItem(ref, lookup);
  } catch (error) {
    if (error instanceof InstrumentUnavailable) {
      return null;
    }
    throw error;
  }
}

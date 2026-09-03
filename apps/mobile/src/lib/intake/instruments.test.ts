/**
 * INT-136 — the instrument half of the typed intake, tested as a refusal.
 *
 * CLAUDE.md invariant 10: validated instruments are rendered verbatim from
 * `text_tr`, and `allow_paraphrase` is false on an instrument item. The
 * clinical content rules add the reason: *"an instrument whose licence is not
 * `GO` does not compile into a pack"*, and *"conversational delivery may
 * paraphrase the lead-in, never the item"*.
 *
 * So the property under test is not "the app renders the right words". It is
 * that there is EXACTLY ONE route from a pack's `text_tr` to the screen, that
 * the route copies nothing, and that it refuses rather than improvising when
 * the words are not there. Today they are never there: no committed pack is
 * servable (HB-C1, and docs/evidence/INT-096.md F4 — all 93 packs are L0),
 * C-SSRS and WHO-5 are licence-BLOCKED (HB-L2, HB-L3), and HAQ-DI is
 * NEEDS_PERMISSION (HB-L4). An empty registry is the correct state; a test
 * that only asserts it is empty is a test of what the author typed, so every
 * behavioural claim below is exercised against an INJECTED synthetic
 * instrument and its near-miss negative control.
 *
 * The fixture content is deliberately not any real instrument's wording.
 */
import { describe, expect, it } from "vitest";

import {
  INSTRUMENT_ITEMS,
  INSTRUMENT_LICENCES,
  InstrumentUnavailable,
  instrumentItemOffer,
  instrumentLicence,
  resolveInstrument,
  resolveInstrumentItem,
  type InstrumentItem,
  type ItemRegistry,
  type LicenceTable,
} from "./instruments";

/**
 * A synthetic instrument, invented for these tests and belonging to no
 * validated scale. The item text carries Turkish diacritics on purpose: it
 * gives the near-miss control below a decomposed (NFD) twin that looks
 * identical on screen and is a different string.
 */
const FIXTURE_ITEMS: readonly InstrumentItem[] = [
  {
    id: "ornek_1",
    textTr: "Örnek madde: son günlerde işlerinizi sürdürebildiniz mi?",
    allowParaphrase: false,
    choicesTr: ["Hiçbir zaman", "Bazı günler", "Çoğu gün", "Her gün"],
  },
  {
    id: "ornek_2",
    textTr: "Örnek madde: gün içinde dinlenmeye ihtiyaç duydunuz mu?",
    allowParaphrase: false,
    choicesTr: ["Hiçbir zaman", "Bazı günler", "Çoğu gün", "Her gün"],
  },
];

const FIXTURE_ID = "FIXTURE-ORNEK";

const goLicences: LicenceTable = { [FIXTURE_ID]: "GO" };
const authored: ItemRegistry = { [FIXTURE_ID]: FIXTURE_ITEMS };

describe("the licence table mirrors packages/protocols and fails closed", () => {
  it("carries the four files/04 header verdicts", () => {
    expect(INSTRUMENT_LICENCES["PHQ-9"]).toBe("GO");
    expect(INSTRUMENT_LICENCES["GAD-7"]).toBe("GO");
    // HB-L2 / HB-L3 — the two blocked ones, by name.
    expect(INSTRUMENT_LICENCES["C-SSRS"]).toBe("BLOCKED");
    expect(INSTRUMENT_LICENCES["WHO-5"]).toBe("BLOCKED");
    expect(INSTRUMENT_LICENCES["HAQ-DI"]).toBe("NEEDS_PERMISSION");
  });

  it("answers UNKNOWN for an instrument it has never recorded", () => {
    expect(instrumentLicence("SF-36")).toBe("UNKNOWN");
    expect(instrumentLicence("")).toBe("UNKNOWN");
  });

  it("answers UNKNOWN for a prototype key rather than an inherited value", () => {
    // Bare bracket access on an object literal hands back Object.prototype's
    // members, so `registry[id] ?? "UNKNOWN"` never fires for these names.
    for (const key of ["constructor", "toString", "valueOf", "__proto__"]) {
      expect(instrumentLicence(key), key).toBe("UNKNOWN");
    }
  });
});

describe("the item registry is empty, and that is the delivered state", () => {
  it("authors no instrument item anywhere in the app", () => {
    expect(Object.keys(INSTRUMENT_ITEMS)).toEqual([]);
  });

  it("refuses every instrument the app could reference today", () => {
    for (const id of Object.keys(INSTRUMENT_LICENCES)) {
      expect(() => resolveInstrument(id), id).toThrow(InstrumentUnavailable);
    }
  });
});

describe("the licence is checked BEFORE the content", () => {
  it("refuses a blocked instrument even when its items are fully authored", () => {
    // The ordering is the whole test: with an empty registry both orderings
    // refuse, so only a fully-authored blocked instrument tells them apart.
    for (const id of ["C-SSRS", "WHO-5", "HAQ-DI"]) {
      let caught: InstrumentUnavailable | null = null;
      try {
        resolveInstrument(id, { items: { [id]: FIXTURE_ITEMS } });
      } catch (error) {
        caught = error as InstrumentUnavailable;
      }
      expect(caught, id).toBeInstanceOf(InstrumentUnavailable);
      expect(caught?.reason, id).toBe("licence_not_go");
    }
  });

  it("refuses a GO instrument whose items nobody has authored", () => {
    let caught: InstrumentUnavailable | null = null;
    try {
      resolveInstrument("PHQ-9");
    } catch (error) {
      caught = error as InstrumentUnavailable;
    }
    expect(caught?.reason).toBe("items_not_authored");
  });

  it("refuses an item id the instrument does not contain", () => {
    let caught: InstrumentUnavailable | null = null;
    try {
      resolveInstrumentItem(
        { instrumentId: FIXTURE_ID, itemId: "ornek_9" },
        { licences: goLicences, items: authored },
      );
    } catch (error) {
      caught = error as InstrumentUnavailable;
    }
    expect(caught?.reason).toBe("item_not_in_instrument");
  });
});

describe("a resolved item reaches the caller verbatim", () => {
  const resolved = resolveInstrument(FIXTURE_ID, { licences: goLicences, items: authored });

  it("hands back the authored records themselves, not copies of them", () => {
    // Byte identity, not deep equality: a resolver that rebuilt each record —
    // trimming, normalising, or re-wrapping the text — would satisfy toEqual
    // and fail this. Invariant 10 is about the bytes.
    expect(resolved).toBe(FIXTURE_ITEMS);
    resolved.forEach((item, index) => {
      expect(item).toBe(FIXTURE_ITEMS[index]);
      expect(item.textTr).toBe(FIXTURE_ITEMS[index].textTr);
      expect(item.choicesTr).toBe(FIXTURE_ITEMS[index].choicesTr);
    });
  });

  it("resolves one item by id without touching its text", () => {
    const item = resolveInstrumentItem(
      { instrumentId: FIXTURE_ID, itemId: "ornek_2" },
      { licences: goLicences, items: authored },
    );
    expect(item).toBe(FIXTURE_ITEMS[1]);
  });

  it("rejects a near-miss the eye cannot see (NFD control)", () => {
    // The control has to be shown to discriminate before it proves anything.
    const decomposed = FIXTURE_ITEMS[0].textTr.normalize("NFD");
    expect(decomposed).not.toBe(FIXTURE_ITEMS[0].textTr);
    expect(decomposed.normalize("NFC")).toBe(FIXTURE_ITEMS[0].textTr);

    const drifted: ItemRegistry = {
      [FIXTURE_ID]: [{ ...FIXTURE_ITEMS[0], textTr: decomposed }],
    };
    const item = resolveInstrumentItem(
      { instrumentId: FIXTURE_ID, itemId: "ornek_1" },
      { licences: goLicences, items: drifted },
    );
    // The resolver does not normalise, so the drift survives to the screen
    // where a reviewer can see it — rather than being silently absorbed.
    expect(item.textTr).toBe(decomposed);
    expect(item.textTr).not.toBe(FIXTURE_ITEMS[0].textTr);
  });
});

describe("the offer form refuses without throwing, and never guesses", () => {
  it("answers null for every instrument the app ships with", () => {
    for (const id of Object.keys(INSTRUMENT_LICENCES)) {
      expect(instrumentItemOffer({ instrumentId: id, itemId: "item_1" }), id).toBeNull();
    }
  });

  it("answers the authored item when one exists", () => {
    const item = instrumentItemOffer(
      { instrumentId: FIXTURE_ID, itemId: "ornek_1" },
      { licences: goLicences, items: authored },
    );
    expect(item).toBe(FIXTURE_ITEMS[0]);
  });

  it("lets a programming error through instead of swallowing it", () => {
    // A malformed registry is a bug, not a blocked instrument. `catch (e) {}`
    // around the resolver would turn every such bug into a silent blank card.
    const malformed = { [FIXTURE_ID]: null } as unknown as ItemRegistry;
    expect(() =>
      instrumentItemOffer(
        { instrumentId: FIXTURE_ID, itemId: "ornek_1" },
        { licences: goLicences, items: malformed },
      ),
    ).toThrow(TypeError);
  });
});

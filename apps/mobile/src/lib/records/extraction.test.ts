/**
 * INT-138 — the confirm-card reader: what the app is allowed to believe about
 * a document it did not read itself.
 *
 * INT-121 put "patient confirms before use" in the type system on the server
 * (`UnconfirmedRecordItem` → `confirm_record_item` → `ConfirmedRecordItem`,
 * with no `by=` because the actor is read off a closed vocabulary). This
 * module is the client half, and the properties it has to keep are the same
 * three, restated for a screen:
 *
 * 1. **A value with no source box cannot be rendered.** The server refuses to
 *    write one down; the client refuses to draw one.
 * 2. **A document may not triage** (invariant 1). The extraction is refused
 *    WHOLE on a level-shaped key, exactly as `extract_record_items` refuses it
 *    — trimming the offending key and keeping the rest is how the remainder of
 *    a hallucinated answer gets through.
 * 3. **The client is a courier for the number, not a second renderer**
 *    (invariant 22). `summary` arrives already rendered — `useGrouping:false`,
 *    plain positional notation, number and unit joined by a NO-BREAK SPACE —
 *    and a second formatter on this side is a second answer to one question.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import {
  LEVEL_SHAPED_KEYS,
  RECORD_ITEM_KINDS,
  applyDecision,
  boxFrame,
  boxRegionKey,
  decisionBody,
  noExtractionFeed,
  parseExtraction,
  pageAtom,
  pendingCount,
  type CardState,
  type ExtractionSource,
} from "./extraction";
import { NBSP } from "@/lib/health/format";
import { t } from "@/lib/i18n";

const BOX = { document_ref: "doc-1", page: 2, bbox: [0.1, 0.2, 0.5, 0.3] };

function item(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: "item-1",
    kind: "lab",
    summary: `ALT 30${NBSP}U/L`,
    unit_conflict: false,
    date: "2026-08-20",
    provenance: BOX,
    ...overrides,
  };
}

function payload(items: readonly Record<string, unknown>[]): Record<string, unknown> {
  return { state: "read", items };
}

describe("the closed vocabulary is the schema's, not a parallel one", () => {
  it("mirrors RecordItemKind from packages/clinical-schemas key-for-key", () => {
    const models = readFileSync(
      join(
        __dirname,
        "..",
        "..",
        "..",
        "..",
        "..",
        "packages",
        "clinical-schemas",
        "src",
        "generated",
        "models.ts",
      ),
      "utf8",
    );
    const declared = /export type RecordItemKind = ([^;]+);/.exec(models);
    expect(declared, "RecordItemKind is no longer declared in the generated models").not.toBeNull();
    const members = [...declared![1].matchAll(/"([a-z_]+)"/g)].map((m) => m[1]);
    expect([...RECORD_ITEM_KINDS].sort()).toEqual(members.sort());
  });

  it("has exactly two verdicts, and neither of them is an edit", () => {
    // `confirm_record_item` carries the observation over UNCHANGED: "confirming
    // is agreeing with what was extracted, never restating it". A third member
    // here would be the client asserting a value the server cannot accept.
    const body = decisionBody("item-1", "confirmed");
    expect(Object.keys(body).sort()).toEqual(["card_id", "decision"]);
    expect(decisionBody("item-1", "declined").decision).toBe("declined");
  });
});

describe("a card that cannot point at the page is not a card", () => {
  it("reads a well-formed item into a card with its box", () => {
    const feed = parseExtraction(payload([item()]));
    expect(feed.kind).toBe("cards");
    if (feed.kind !== "cards") return;
    expect(feed.cards).toHaveLength(1);
    expect(feed.cards[0].box).toEqual({
      documentRef: "doc-1",
      page: 2,
      bbox: [0.1, 0.2, 0.5, 0.3],
    });
  });

  it("refuses an item with no provenance at all", () => {
    expect(parseExtraction(payload([item({ provenance: undefined })])).kind).toBe("refused");
  });

  it("refuses an item whose provenance names no page or no rectangle", () => {
    expect(
      parseExtraction(
        payload([item({ provenance: { document_ref: "d", page: null, bbox: null } })]),
      ).kind,
    ).toBe("refused");
  });

  it("refuses a rectangle that is not normalised to the page", () => {
    expect(
      parseExtraction(payload([item({ provenance: { ...BOX, bbox: [0.1, 0.2, 1.4, 0.3] } })])).kind,
    ).toBe("refused");
  });

  it("refuses an inverted or empty rectangle — it encloses nothing to check", () => {
    expect(
      parseExtraction(payload([item({ provenance: { ...BOX, bbox: [0.5, 0.2, 0.5, 0.3] } })])).kind,
    ).toBe("refused");
  });

  it("refuses a page number below one", () => {
    expect(parseExtraction(payload([item({ provenance: { ...BOX, page: 0 } })])).kind).toBe(
      "refused",
    );
  });
});

describe("invariant 1 — a document is not a rules engine", () => {
  it.each([...LEVEL_SHAPED_KEYS])("refuses the WHOLE extraction over a `%s` key", (key) => {
    const feed = parseExtraction(payload([item(), item({ id: "item-2", [key]: "RED" })]));
    expect(feed.kind).toBe("refused");
  });

  it("names at least the nine keys the server refuses", () => {
    for (const key of [
      "level",
      "triage",
      "priority",
      "preempt",
      "register",
      "severity",
      "urgency",
      "acuity",
      "triage_level",
    ]) {
      expect(LEVEL_SHAPED_KEYS).toContain(key);
    }
  });

  it("NEAR MISS: `unit_conflict` is a flag, not a level, and is accepted", () => {
    // Without this control the refusal above passes for a parser that rejects
    // every optional key, which would delete the unit guard from the screen.
    const feed = parseExtraction(payload([item({ unit_conflict: true })]));
    expect(feed.kind).toBe("cards");
    if (feed.kind !== "cards") return;
    expect(feed.cards[0].unitConflict).toBe(true);
  });

  it("refuses a card carrying any key the shape does not declare", () => {
    expect(parseExtraction(payload([item({ interpretation: "high" })])).kind).toBe("refused");
  });
});

describe("invariant 22 — the number is carried, never re-rendered", () => {
  it("keeps the summary byte-for-byte, non-breaking space included", () => {
    const feed = parseExtraction(payload([item({ summary: `Kreatinin 1.500${NBSP}mg/dL` })]));
    expect(feed.kind).toBe("cards");
    if (feed.kind !== "cards") return;
    // 1.500 is exactly the string files/03 §4.9.6 says reads two ways. The
    // server resolved it; a client that re-parsed it would resolve it again,
    // possibly differently, and the two answers would differ by 1000x.
    expect(feed.cards[0].summary).toBe(`Kreatinin 1.500${NBSP}mg/dL`);
  });

  it("holds no number formatter and no number parser", () => {
    const source = readFileSync(join(__dirname, "extraction.ts"), "utf8");
    for (const token of ["parseFloat", "parseInt", "toFixed", "NumberFormat", "toLocaleString"]) {
      expect(source, `extraction.ts reaches ${token}`).not.toContain(token);
    }
  });

  it("refuses a summary that is empty — there is nothing to agree with", () => {
    expect(parseExtraction(payload([item({ summary: "   " })])).kind).toBe("refused");
  });
});

describe("the feed states, and the one that ships", () => {
  it("reads the reading state without inventing cards for it", () => {
    expect(parseExtraction({ state: "reading", items: [] }).kind).toBe("reading");
  });

  it("reads the not-read state", () => {
    expect(parseExtraction({ state: "unread", items: [] }).kind).toBe("unread");
  });

  it("refuses a state outside the closed set rather than guessing one", () => {
    expect(parseExtraction({ state: "done", items: [] }).kind).toBe("refused");
  });

  it("ships an extraction source that refuses: nothing publishes cards yet", () => {
    // The producer is INT-124 (the extraction LLM) and no endpoint publishes
    // its output. The seam exists, it is shut, and it fails closed — the shape
    // `NoLayout`/`NoTerminology` already have on the server side.
    return Promise.all([
      noExtractionFeed.read("visit-1", "doc-1").then((feed) => expect(feed.kind).toBe("unread")),
      noExtractionFeed
        .record("visit-1", "doc-1", "item-1", "confirmed")
        .then((ok) => expect(ok).toBe(false)),
    ]);
  });
});

describe("no optimistic write — a card is confirmed when the record says so", () => {
  const states: Record<string, CardState> = { "item-1": "pending" };

  it("leaves the card pending when the write was not acknowledged", () => {
    expect(applyDecision(states, "item-1", "confirmed", false)).toEqual({ "item-1": "pending" });
  });

  it("marks it confirmed only on an acknowledged write", () => {
    expect(applyDecision(states, "item-1", "confirmed", true)).toEqual({ "item-1": "confirmed" });
  });

  it("records a decline the same way", () => {
    expect(applyDecision(states, "item-1", "declined", true)).toEqual({ "item-1": "declined" });
  });

  it("counts what still awaits the patient", () => {
    expect(pendingCount(["a", "b", "c"], { a: "confirmed", b: "pending" })).toBe(2);
  });
});

describe("the provenance locator is geometry, never a score", () => {
  it("projects the normalised box onto percentage offsets", () => {
    expect(boxFrame([0.1, 0.2, 0.5, 0.6])).toEqual({
      left: "10%",
      top: "20%",
      width: "40%",
      height: "40%",
    });
  });

  it("names where on the page the box sits, for a reader who cannot see it", () => {
    expect(boxRegionKey([0.1, 0.02, 0.5, 0.2])).toBe("records.prov.top");
    expect(boxRegionKey([0.1, 0.45, 0.5, 0.55])).toBe("records.prov.middle");
    expect(boxRegionKey([0.1, 0.8, 0.5, 0.95])).toBe("records.prov.bottom");
  });
});

describe("the page number is an atom, and it is not grouped", () => {
  it("joins the word and the number with a NO-BREAK SPACE", () => {
    expect(pageAtom(2)).toBe(`${t("records.prov.page")}${NBSP}2`);
  });

  it("never groups the digits of a long document's page", () => {
    // `1.200` in Turkish grouping is the exact shape files/03 §4.9.6 calls
    // ambiguous. A page number is not a clinical quantity, but one rendering
    // rule for numbers on this screen is cheaper than two.
    expect(pageAtom(1200)).toBe(`${t("records.prov.page")}${NBSP}1200`);
  });
});

describe("the seam, exercised end to end against a stub source", () => {
  /** Mocks live in tests only (CLAUDE.md): this is the shape a real feed has. */
  const stub: ExtractionSource = {
    read: () => Promise.resolve(parseExtraction(payload([item(), item({ id: "item-2" })]))),
    record: (_visit, _doc, cardId) => Promise.resolve(cardId === "item-1"),
  };

  it("reads two cards, confirms the one the write acknowledged, and holds the other", async () => {
    const feed = await stub.read("visit-1", "doc-1");
    expect(feed.kind).toBe("cards");
    if (feed.kind !== "cards") return;
    const ids = feed.cards.map((card) => card.id);
    let states: Record<string, CardState> = {};
    for (const id of ids) {
      const acknowledged = await stub.record("visit-1", "doc-1", id, "confirmed");
      states = applyDecision(states, id, "confirmed", acknowledged);
    }
    expect(states).toEqual({ "item-1": "confirmed" });
    expect(pendingCount(ids, states)).toBe(1);
  });
});

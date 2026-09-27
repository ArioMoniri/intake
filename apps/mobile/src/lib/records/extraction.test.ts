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
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  LEVEL_SHAPED_KEYS,
  RECORD_ITEM_KINDS,
  applyDecision,
  boxFrame,
  boxRegionKey,
  cardStateOf,
  decisionBody,
  isAcknowledgement,
  parseExtraction,
  pageAtom,
  pendingCount,
  pollDelayMs,
  pollExtraction,
  readRound,
  type CardState,
  type ExtractionFeed,
  type ExtractionSource,
} from "./extraction";
import { NBSP, formatQuantity } from "@/lib/health/format";
import { t, type Locale } from "@/lib/i18n";

const BOX = { document_ref: "doc-1", page: 2, bbox: [0.1, 0.2, 0.5, 0.3] };

/**
 * INT-385's shared table: one row per (magnitude, locale), and the exact atom
 * the server's `quantity_atom` writes for it. `tests/records/test_quantity_render.py`
 * holds the server to the same file.
 */
interface RenderRow {
  value: string;
  unit: string;
  locale: Locale;
  atom: string;
}

const RENDER_TABLE = JSON.parse(
  readFileSync(
    join(
      __dirname,
      "..",
      "..",
      "..",
      "..",
      "..",
      "tests",
      "fixtures",
      "records",
      "quantity_render.json",
    ),
    "utf8",
  ),
) as { rows: RenderRow[] };

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

describe("INT-385 — the server and the app write a quantity the same way", () => {
  // A Turkish reader takes a full stop as grouping, so `12.500` on a Turkish
  // screen is twelve thousand five hundred. The server writes the locale's
  // decimal separator, no grouping, and one NO-BREAK SPACE before the unit.
  // The card carries that atom as it arrives. When the app writes a clinical
  // quantity itself, it writes the same bytes.

  it("reads a table that covers INT-385's four magnitudes in both locales", () => {
    const covered = new Set(RENDER_TABLE.rows.map((row) => `${row.value}|${row.locale}`));
    for (const value of ["12.5", "12500", "0.05", "1.5"]) {
      for (const locale of ["tr", "en"]) {
        expect(covered.has(`${value}|${locale}`), `${value} in ${locale}`).toBe(true);
      }
    }
  });

  it.each(RENDER_TABLE.rows)(
    "$value in $locale: the app's renderer writes the server's atom",
    (row) => {
      expect(formatQuantity(Number(row.value), row.unit, row.locale)).toBe(row.atom);
    },
  );

  it.each(RENDER_TABLE.rows)(
    "$value in $locale: the card carries the atom byte for byte",
    (row) => {
      const summary = `Kreatinin ${row.atom}`;
      const feed = parseExtraction(payload([item({ summary })]));
      expect(feed.kind).toBe("cards");
      if (feed.kind !== "cards") return;
      expect(feed.cards[0].summary).toBe(summary);
    },
  );

  it.each(RENDER_TABLE.rows)(
    "$value in $locale: the locale's decimal point, no grouping, one NO-BREAK SPACE",
    (row) => {
      const [number, unit, ...rest] = row.atom.split(NBSP);
      expect(rest).toEqual([]);
      expect(unit).toBe(row.unit);
      expect(row.atom).not.toContain(" ");
      // The other locale's point would be grouping to this reader.
      expect(number).not.toContain(row.locale === "tr" ? "." : ",");
    },
  );

  it("never groups 12500 (useGrouping:false)", () => {
    for (const locale of ["tr", "en"] as const) {
      const written = formatQuantity(12500, "U/L", locale);
      expect(written).toBe(`12500${NBSP}U/L`);
      expect(written).not.toContain(`12.500${NBSP}`);
      expect(written).not.toContain(`12,500${NBSP}`);
    }
  });

  it("NEAR MISS: 12.5 in Turkish is 12,5 and never 12.500", () => {
    expect(formatQuantity(12.5, "mg/dL", "tr")).toBe(`12,5${NBSP}mg/dL`);
    expect(formatQuantity(12.5, "mg/dL", "tr")).not.toBe(`12.500${NBSP}mg/dL`);
    expect(formatQuantity(12.5, "mg/dL", "en")).toBe(`12.5${NBSP}mg/dL`);
  });

  it("keeps a clinical quantity's precision: 0.05 is 0,05, never 0,1", () => {
    expect(formatQuantity(0.05, "mg/L", "tr")).toBe(`0,05${NBSP}mg/L`);
    expect(formatQuantity(0.05, "mg/L", "en")).toBe(`0.05${NBSP}mg/L`);
  });

  it("the joiner is U+00A0 NO-BREAK SPACE", () => {
    expect(NBSP).toBe(" ");
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

  it("reads the server's own refusal as a refusal, not as a guess", () => {
    // The route answers `refused` when an item carries the data-boundary
    // control token or a box into another document (invariant 14).
    expect(parseExtraction({ state: "refused", items: [] }).kind).toBe("refused");
  });

  it("no longer ships a source that refuses on the client: the gate is the server's", () => {
    // The route exists (INT-138) and its production source answers `unread`
    // for every document, so the fail-closed default lives where the
    // producers are — one gate, not two that could disagree.
    const source = readFileSync(join(__dirname, "extraction.ts"), "utf8");
    expect(source).not.toContain("noExtractionFeed");
  });
});

describe("what the server already recorded is what the card shows", () => {
  it("carries a verdict the server holds for a card", () => {
    const feed = parseExtraction(
      payload([item({ decision: "confirmed" }), item({ id: "item-2", decision: "declined" })]),
    );
    expect(feed.kind).toBe("cards");
    if (feed.kind !== "cards") return;
    expect(feed.cards.map((card) => card.decision)).toEqual(["confirmed", "declined"]);
  });

  it("reads an absent or null verdict as none", () => {
    const feed = parseExtraction(payload([item({ decision: null }), item({ id: "item-2" })]));
    expect(feed.kind).toBe("cards");
    if (feed.kind !== "cards") return;
    expect(feed.cards.map((card) => card.decision)).toEqual([null, null]);
  });

  it("NEAR MISS: a verdict outside the two refuses the whole extraction", () => {
    // `edited` is the verdict the server cannot accept, so a feed carrying it
    // is not a feed this app can render truthfully.
    expect(parseExtraction(payload([item({ decision: "edited" })])).kind).toBe("refused");
  });

  it("shows the acknowledged local verdict first, then the server's, then pending", () => {
    const feed = parseExtraction(payload([item({ decision: "declined" }), item({ id: "item-2" })]));
    expect(feed.kind).toBe("cards");
    if (feed.kind !== "cards") return;
    const [held, open] = feed.cards;
    expect(cardStateOf({}, held)).toBe("declined");
    expect(cardStateOf({}, open)).toBe("pending");
    expect(cardStateOf({ "item-2": "confirmed" }, open)).toBe("confirmed");
  });
});

describe("the acknowledgement is asserted, never assumed", () => {
  it("counts a write as landed only when the server echoes the card and the verdict", () => {
    expect(
      isAcknowledgement({ card_id: "item-1", decision: "confirmed" }, "item-1", "confirmed"),
    ).toBe(true);
  });

  it.each([
    [{ card_id: "item-2", decision: "confirmed" }],
    [{ card_id: "item-1", decision: "declined" }],
    [{ card_id: "item-1" }],
    [{ error: "already_decided" }],
    [{}],
    [null],
    ["ok"],
  ])("NEAR MISS: %j is not an acknowledgement", (body) => {
    expect(isAcknowledgement(body, "item-1", "confirmed")).toBe(false);
  });
});

describe("processing: a document still being read is asked again, with backoff", () => {
  it("waits longer each time and stops asking after a bounded while", () => {
    const delays: number[] = [];
    for (let attempt = 0; ; attempt += 1) {
      const delay = pollDelayMs(attempt);
      if (delay === null) break;
      delays.push(delay);
      expect(attempt, "polling never stops").toBeLessThan(50);
    }
    expect(delays.length).toBeGreaterThan(2);
    for (let i = 1; i < delays.length; i += 1) {
      expect(delays[i]).toBeGreaterThanOrEqual(delays[i - 1]);
    }
    expect(delays[delays.length - 1]).toBeGreaterThan(delays[0]);
    // a patient on a slow day is asked about, not hammered: at most one read
    // every two seconds, and no single wait longer than half a minute
    expect(Math.min(...delays)).toBeGreaterThanOrEqual(2000);
    expect(Math.max(...delays)).toBeLessThanOrEqual(30000);
  });

  it("asks again only about what is still being read, or could not be asked", async () => {
    const answers: Record<string, ExtractionFeed | Error> = {
      reading: { kind: "reading" },
      unread: { kind: "unread" },
      refused: { kind: "refused" },
      cards: parseExtraction(payload([item()])),
      offline: new Error("network"),
    };
    const source: ExtractionSource = {
      read: (_visit, docId) => {
        const answer = answers[docId];
        return answer instanceof Error ? Promise.reject(answer) : Promise.resolve(answer);
      },
      record: () => Promise.resolve(false),
    };
    const round = await readRound(source, "visit-1", Object.keys(answers));
    expect(round.again.sort()).toEqual(["offline", "reading"]);
    // a failed read is not an answer: nothing is shown for it
    expect(Object.keys(round.feeds).sort()).toEqual(["cards", "reading", "refused", "unread"]);
  });

  describe("on a fake clock", () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });
    afterEach(() => {
      vi.useRealTimers();
    });

    function counting(answers: ExtractionFeed[]): { source: ExtractionSource; asked: string[] } {
      const asked: string[] = [];
      const source: ExtractionSource = {
        read: (_visit, docId) => {
          asked.push(docId);
          return Promise.resolve(answers[Math.min(asked.length - 1, answers.length - 1)]);
        },
        record: () => Promise.resolve(false),
      };
      return { source, asked };
    }

    it("asks again after each wait until the cards arrive, then stops", async () => {
      const cards = parseExtraction(payload([item()]));
      const { source, asked } = counting([{ kind: "reading" }, { kind: "reading" }, cards]);
      const seen: ExtractionFeed[] = [];
      pollExtraction(source, "visit-1", ["doc-1"], (feeds) => seen.push(feeds["doc-1"]));
      await vi.advanceTimersByTimeAsync(0);
      expect(asked).toHaveLength(1);
      await vi.advanceTimersByTimeAsync(pollDelayMs(0)! - 1);
      expect(asked, "asked before the wait was over").toHaveLength(1);
      await vi.advanceTimersByTimeAsync(1);
      expect(asked).toHaveLength(2);
      await vi.advanceTimersByTimeAsync(pollDelayMs(1)!);
      expect(asked).toHaveLength(3);
      expect(seen.map((feed) => feed.kind)).toEqual(["reading", "reading", "cards"]);
      await vi.advanceTimersByTimeAsync(10 * 60 * 1000);
      expect(asked, "asked again after the cards arrived").toHaveLength(3);
    });

    it("gives up after the schedule and hands nothing over once stopped", async () => {
      const { source, asked } = counting([{ kind: "reading" }]);
      const seen: string[] = [];
      const stop = pollExtraction(source, "visit-1", ["doc-1"], () => seen.push("round"));
      await vi.advanceTimersByTimeAsync(10 * 60 * 1000);
      let rounds = 0;
      while (pollDelayMs(rounds) !== null) rounds += 1;
      expect(asked).toHaveLength(rounds + 1);

      const second = counting([{ kind: "reading" }]);
      const halt = pollExtraction(second.source, "visit-1", ["doc-2"], () => seen.push("late"));
      await vi.advanceTimersByTimeAsync(0);
      halt();
      await vi.advanceTimersByTimeAsync(10 * 60 * 1000);
      expect(second.asked).toHaveLength(1);
      stop();
    });
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

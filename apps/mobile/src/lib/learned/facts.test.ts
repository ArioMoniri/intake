/**
 * INT-140 — the ledger view behind *Me → Hakkımda öğrendikleri*.
 *
 * files/09 §3: "every learned fact shows 'where from' and can be corrected or
 * deleted by the patient". Two rules make that safe rather than merely
 * present:
 *
 * - **Invariant 12 at the type level.** `LedgerFact.source` is the closed
 *   three-member confirmed vocabulary. A server row carrying anything else —
 *   an unconfirmed guess, a model provenance — is not rendered with a
 *   fallback: it is dropped. A fact with no confirmation is not a fact.
 * - **Invariant 22 at the render boundary.** A value is patient copy only
 *   when it is already a sentence the patient said. A bare number has no
 *   unit and no question attached to it here, so it is not printed as text;
 *   the row falls back to a catalogue label and keeps its provenance, its
 *   scope and its delete control.
 */
import { describe, expect, it } from "vitest";

import type { CarriedFact } from "../intake/carriedFacts";
import {
  ledgerFactFromCarried,
  parseLearnedFact,
  parseLearnedFacts,
  readableValue,
  withoutFact,
  withSharedFact,
} from "./facts";

function row(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    key: "ilaclar.metoprolol",
    value: "Metoprolol (düzenli kullanım)",
    source: "confirmed_intake_extraction",
    source_ref: "sentetik-onay-karti",
    confirmed_by: "patient",
    confirmed_at: "2026-05-12T08:00:00Z",
    confidence: 0.9,
    shared: true,
    needs_reconfirmation: false,
    ...overrides,
  };
}

const CARRIED: CarriedFact = {
  id: "cf-1",
  kind: "medication",
  text: "Metoprolol (düzenli kullanım)",
  source: "clinician_accepted_note",
  assertedBy: { role: "clinician" },
  assertedAt: "2026-05-12",
  sourceVisitId: "v-0",
};

describe("readableValue", () => {
  it("takes a recorded phrase as it stands", () => {
    expect(readableValue("Metoprolol (düzenli kullanım)")).toBe("Metoprolol (düzenli kullanım)");
  });

  it("has no reading for a yes/no, a number or a structure", () => {
    expect(readableValue(true)).toBeNull();
    expect(readableValue(12)).toBeNull();
    expect(readableValue({ dose: "5" })).toBeNull();
    expect(readableValue(null)).toBeNull();
  });

  it("has no reading for an empty or blank string", () => {
    expect(readableValue("   ")).toBeNull();
  });
});

describe("parseLearnedFact", () => {
  it("reads a fact with its provenance, its scope and its twelve-month state", () => {
    expect(parseLearnedFact(row())).toEqual({
      id: "ilaclar.metoprolol",
      origin: "record",
      text: "Metoprolol (düzenli kullanım)",
      source: "confirmed_intake_extraction",
      recordedAt: "2026-05-12T08:00:00Z",
      shared: true,
      needsReconfirmation: false,
    });
  });

  it("keeps the fact but not the text when the value has no reading", () => {
    const parsed = parseLearnedFact(row({ key: "oyku.belirti_var", value: true }));
    expect(parsed?.text).toBeNull();
    expect(parsed?.id).toBe("oyku.belirti_var");
  });

  it.each(["unconfirmed_extraction", "llm_candidate", "system", ""])(
    "drops a row whose provenance is %s (invariant 12)",
    (source) => {
      expect(parseLearnedFact(row({ source }))).toBeNull();
    },
  );

  it.each(["key", "source_ref", "confirmed_at"])("drops a row missing %s", (field) => {
    expect(parseLearnedFact(row({ [field]: null }))).toBeNull();
  });

  it("drops a row whose share scope or reconfirmation state is not a yes/no", () => {
    expect(parseLearnedFact(row({ shared: "yes" }))).toBeNull();
    expect(parseLearnedFact(row({ needs_reconfirmation: 1 }))).toBeNull();
  });

  it("reads the twelve-month state the server computed, never a local clock", () => {
    expect(parseLearnedFact(row({ needs_reconfirmation: true }))?.needsReconfirmation).toBe(true);
  });
});

describe("parseLearnedFacts", () => {
  it("reads the route's envelope and drops what it cannot read", () => {
    const facts = parseLearnedFacts({
      version: 3,
      facts: [row(), row({ key: "x", source: "guess" })],
    });
    expect(facts.map((f) => f.id)).toEqual(["ilaclar.metoprolol"]);
  });

  it("reads a missing or malformed envelope as no facts", () => {
    expect(parseLearnedFacts({})).toEqual([]);
    expect(parseLearnedFacts(null)).toEqual([]);
  });
});

describe("ledgerFactFromCarried", () => {
  it("marks a fact this device holds as device-held, with no share scope to claim", () => {
    expect(ledgerFactFromCarried(CARRIED)).toEqual({
      id: "cf-1",
      origin: "device",
      text: "Metoprolol (düzenli kullanım)",
      source: "clinician_accepted_note",
      recordedAt: "2026-05-12",
      shared: null,
      needsReconfirmation: false,
    });
  });
});

describe("editing the list", () => {
  const facts = [parseLearnedFact(row())!, ledgerFactFromCarried(CARRIED)];

  it("turns one fact's share scope without touching its neighbours", () => {
    const next = withSharedFact(facts, "ilaclar.metoprolol", false);
    expect(next[0].shared).toBe(false);
    expect(next[1]).toBe(facts[1]);
    expect(facts[0].shared).toBe(true);
  });

  it("leaves the list alone when the id is not in it", () => {
    expect(withSharedFact(facts, "nope", false)).toEqual(facts);
  });

  it("removes exactly one fact", () => {
    expect(withoutFact(facts, "cf-1").map((f) => f.id)).toEqual(["ilaclar.metoprolol"]);
  });
});

import { describe, expect, it } from "vitest";

import {
  factActionKey,
  factSourceKey,
  factStateKey,
  reconcileCarriedFacts,
  type CarriedFact,
  type FactDecision,
} from "./carriedFacts";

const carried: CarriedFact = {
  id: "cf-test-1",
  kind: "medication",
  text: "Metoprolol (düzenli kullanım)",
  source: "clinician_accepted_note",
  assertedBy: { role: "clinician" },
  assertedAt: "2026-05-12",
  sourceVisitId: "v-test-0",
};

function decide(outcome: FactDecision["outcome"]): FactDecision {
  return {
    outcome,
    by: { role: "patient", attribution: "self_report" },
    at: "2026-08-29",
  };
}

describe("reconcileCarriedFacts — invariant 12 at the type level", () => {
  it("with no decision the fact lands in `unconfirmed`, never in `current`", () => {
    const r = reconcileCarriedFacts([carried], {});
    expect(r.current).toEqual([]);
    expect(r.conflicted).toEqual([]);
    expect(r.stopped).toEqual([]);
    expect(r.unconfirmed).toEqual([carried]);
  });

  it("a decision for a fact that is not carried is ignored, never invented", () => {
    const r = reconcileCarriedFacts([], { "cf-ghost": decide("confirmed") });
    expect(r.current).toEqual([]);
    expect(r.unconfirmed).toEqual([]);
  });

  it("confirmed → files/04 §5 reconciliation `matches`, carrying the decision", () => {
    const decision = decide("confirmed");
    const r = reconcileCarriedFacts([carried], { [carried.id]: decision });
    expect(r.current).toHaveLength(1);
    expect(r.current[0].reconciliation).toBe("matches");
    expect(r.current[0].decision).toEqual(decision);
    expect(r.current[0].fact).toEqual(carried);
    expect(r.unconfirmed).toEqual([]);
  });

  it("stopped → reconciliation `stopped`, in its own bucket, not deleted", () => {
    const r = reconcileCarriedFacts([carried], { [carried.id]: decide("stopped") });
    expect(r.stopped).toHaveLength(1);
    expect(r.stopped[0].reconciliation).toBe("stopped");
    expect(r.current).toEqual([]);
    // A retraction is an outcome, not an erasure: the fact object survives.
    expect(r.stopped[0].fact).toEqual(carried);
  });

  it("changed → reconciliation `conflict`; the clinician resolves it, not us", () => {
    const r = reconcileCarriedFacts([carried], { [carried.id]: decide("changed") });
    expect(r.conflicted).toHaveLength(1);
    expect(r.conflicted[0].reconciliation).toBe("conflict");
    expect(r.current).toEqual([]);
  });

  it("carried order is preserved inside every bucket", () => {
    const second: CarriedFact = { ...carried, id: "cf-test-2", text: "Ramipril" };
    const third: CarriedFact = { ...carried, id: "cf-test-3", text: "Asetilsalisilik asit" };
    const r = reconcileCarriedFacts([carried, second, third], {
      [carried.id]: decide("confirmed"),
      [third.id]: decide("confirmed"),
    });
    expect(r.current.map((f) => f.fact.id)).toEqual(["cf-test-1", "cf-test-3"]);
    expect(r.unconfirmed.map((f) => f.id)).toEqual(["cf-test-2"]);
  });

  it("every bucket is total: nothing carried is ever silently dropped", () => {
    const b: CarriedFact = { ...carried, id: "b" };
    const c: CarriedFact = { ...carried, id: "c" };
    const d: CarriedFact = { ...carried, id: "d" };
    const r = reconcileCarriedFacts([carried, b, c, d], {
      [b.id]: decide("confirmed"),
      [c.id]: decide("stopped"),
      [d.id]: decide("changed"),
    });
    const seen = r.current.length + r.conflicted.length + r.stopped.length + r.unconfirmed.length;
    expect(seen).toBe(4);
  });
});

describe("catalogue keys for the ledger", () => {
  it("each of the three overlay provenances has patient-facing copy", () => {
    expect(factSourceKey("confirmed_intake_extraction")).toBe(
      "carried.source.confirmed_intake_extraction",
    );
    expect(factSourceKey("clinician_accepted_note")).toBe("carried.source.clinician_accepted_note");
    expect(factSourceKey("confirmed_imported_record")).toBe(
      "carried.source.confirmed_imported_record",
    );
  });

  it("undecided has its own state copy — it is not rendered as a no", () => {
    expect(factStateKey("medication", undefined)).toBe("carried.state.unconfirmed");
    expect(factStateKey("medication", decide("confirmed"))).toBe("carried.state.confirmed");
    expect(factStateKey("medication", decide("changed"))).toBe("carried.state.changed");
    expect(factStateKey("medication", decide("stopped"))).toBe("carried.state.stopped");
  });

  // INT-256: the same three outcomes, in the words that kind of fact takes.
  it("an allergy takes allergy words — nothing about it is 'stopped'", () => {
    expect(factStateKey("allergy", undefined)).toBe("carried.state.unconfirmed");
    expect(factStateKey("allergy", decide("stopped"))).toBe("carried.state.allergy.stopped");
    expect(factActionKey("allergy", "stopped")).toBe("carried.action.allergy.stopped");
    expect(factActionKey("medication", "stopped")).toBe("carried.action.stopped");
  });
});

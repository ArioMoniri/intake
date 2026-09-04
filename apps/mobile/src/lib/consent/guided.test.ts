/**
 * Guided-sweep selector (INT consent UX redesign).
 *
 * The İzinleriniz redesign lets a patient grant every permission in a single
 * pass, without leaving the screen. The optional "grant each remaining
 * permission in turn" affordance walks the patient through the still-off,
 * text-loaded purposes ONE AT A TIME — expand → show the hash-bound text →
 * Grant → advance to the next. `remainingGrantable` / `firstGrantable` are the
 * pure ordering behind that walk: read-only projections of `viewOf`, never a
 * second copy of the grant rules.
 *
 * The properties that matter and are pinned here:
 * - fail closed: with no loaded text NOTHING is grantable, so the sweep has
 *   nowhere to go and never offers a grant (invariant 18);
 * - registry order: the walk follows the 06 §2 order the list already shows;
 * - it grows mid-sweep: granting `voice` makes `lane:affect` grantable (the
 *   lane rides the voice stream), so a selector computed from live views must
 *   pick it up rather than skip it;
 * - it ends: once every grantable purpose is on, the sweep is complete.
 */
import { describe, expect, it } from "vitest";

import { applyTexts, freshLedger, grant, viewOf, type TextEntry } from "./ledger";
import { firstGrantable, remainingGrantable } from "./guided";

const loaded = (version: string, hash: string): TextEntry => ({
  status: "loaded",
  text: { version, textHash: hash, body: "Deneme metni — yalnızca test." },
});

describe("guided sweep — remainingGrantable / firstGrantable", () => {
  it("offers nothing while no text is loaded (fail closed, invariant 18)", () => {
    const views = viewOf(freshLedger());
    expect(remainingGrantable(views)).toEqual([]);
    expect(firstGrantable(views)).toBeNull();
  });

  it("lists the text-loaded, still-off purposes in 06 §2 registry order", () => {
    // documents' text lands before voice's in the payload; the walk still
    // follows registry order, not payload order.
    const state = applyTexts(freshLedger(), {
      documents: loaded("v1", "d".repeat(64)),
      voice: loaded("v1", "1".repeat(64)),
      wellbeing: loaded("v1", "w".repeat(64)),
    });
    const views = viewOf(state);
    expect(remainingGrantable(views)).toEqual(["voice", "wellbeing", "documents"]);
    expect(firstGrantable(views)).toBe("voice");
  });

  it("does not offer lane:affect until voice is actually granted (it rides voice)", () => {
    const state = applyTexts(freshLedger(), {
      voice: loaded("v1", "1".repeat(64)),
      "lane:affect": loaded("v1", "2".repeat(64)),
    });
    const views = viewOf(state);
    // lane:affect is loaded but blocked while voice is off — not in the walk
    expect(remainingGrantable(views)).toEqual(["voice"]);
  });

  it("grows mid-sweep: granting voice opens lane:affect for the next step", () => {
    let state = applyTexts(freshLedger(), {
      voice: loaded("v1", "1".repeat(64)),
      "lane:affect": loaded("v1", "2".repeat(64)),
    });
    state = grant(state, "voice", "2026-09-04T00:00:00Z").state;
    const views = viewOf(state);
    // voice is now on and drops out; lane:affect is now reachable and joins
    expect(remainingGrantable(views)).toEqual(["lane:affect"]);
    expect(firstGrantable(views)).toBe("lane:affect");
  });

  it("a granted purpose leaves the walk; the earliest remaining one is next", () => {
    let state = applyTexts(freshLedger(), {
      voice: loaded("v1", "1".repeat(64)),
      wellbeing: loaded("v1", "w".repeat(64)),
    });
    state = grant(state, "voice", "2026-09-04T00:00:00Z").state;
    const views = viewOf(state);
    expect(remainingGrantable(views)).toEqual(["wellbeing"]);
    expect(firstGrantable(views)).toBe("wellbeing");
  });

  it("ends the sweep once every grantable purpose is on", () => {
    let state = applyTexts(freshLedger(), {
      voice: loaded("v1", "1".repeat(64)),
      wellbeing: loaded("v1", "w".repeat(64)),
    });
    state = grant(state, "voice", "2026-09-04T00:00:00Z").state;
    state = grant(state, "wellbeing", "2026-09-04T00:00:01Z").state;
    const views = viewOf(state);
    expect(remainingGrantable(views)).toEqual([]);
    expect(firstGrantable(views)).toBeNull();
  });

  it("never offers core — information has no grant action", () => {
    // even if some payload row for core existed, core is ui:info and viewOf
    // never marks it grantable; the sweep must never surface it.
    const views = viewOf(freshLedger());
    expect(remainingGrantable(views)).not.toContain("core");
  });
});

/**
 * INT-537 — the visit-start gate. A visit and its note need the `core` açık
 * rıza scope (services/api visits.py and notes.py declare it), so the app
 * asks for it where it is needed, before a visit is added, and reads the
 * answer from the consent ledger the İzinleriniz screens write.
 *
 * What this file pins:
 * - the gate opens on an honoured core grant and on nothing else;
 * - a core grant whose text moved is stale: the gate stays shut and says so,
 *   so the screen can ask for the new text rather than the first one;
 * - the optional purposes never open or shut it (files/02 §7);
 * - a core withdrawal shuts it at once.
 *
 * Fixture texts live here, inline, and nowhere else (the ledger.test.ts rule).
 */
import { describe, expect, it } from "vitest";

import { coreGate } from "./gate";
import {
  applyServerScopes,
  applyTexts,
  freshLedger,
  grant,
  seedFromSession,
  withdraw,
  type LedgerState,
  type TextEntry,
} from "./ledger";
import { PURPOSES } from "./purposes";

const NOW = "2026-10-16T09:00:00Z";

const text = (version: string, fill: string): TextEntry => ({
  status: "loaded",
  text: {
    version,
    textHash: fill.repeat(64).slice(0, 64),
    body: `Deneme onay metni ${version}; yalnızca test dosyasında yaşar.`,
  },
});

/** Every optional purpose granted against a loaded text — core untouched. */
function everythingButCore(): LedgerState {
  let state = freshLedger();
  for (const def of PURPOSES) {
    if (def.id !== "core") {
      state = applyTexts(state, { [def.id]: text("v1", "9") });
    }
  }
  for (const def of PURPOSES) {
    if (def.id !== "core") {
      state = grant(state, def.id, NOW).state;
    }
  }
  return state;
}

describe("coreGate — the one consent a visit needs (INT-537)", () => {
  it("a fresh account has no core consent: the gate is shut, not stale", () => {
    expect(coreGate(freshLedger())).toEqual({ open: false, stale: false });
  });

  it("a loaded text alone opens nothing: only the patient's grant does", () => {
    const state = applyTexts(freshLedger(), { core: text("v1", "c") });
    expect(coreGate(state)).toEqual({ open: false, stale: false });
    expect(coreGate(grant(state, "core", NOW).state)).toEqual({ open: true });
  });

  it("a core grant whose text moved is stale: shut, and the screen is told why", () => {
    const granted = grant(applyTexts(freshLedger(), { core: text("v1", "c") }), "core", NOW).state;
    const bumped = applyTexts(granted, { core: text("v2", "e") });
    expect(coreGate(bumped)).toEqual({ open: false, stale: true });
    expect(coreGate(grant(bumped, "core", NOW).state)).toEqual({ open: true });
  });

  it("the server's stale verdict shuts the gate before the new text arrives", () => {
    const state = applyServerScopes(freshLedger(), [
      { scope: "core", reason: "stale", version: "v1", textHash: "c".repeat(64) },
    ]);
    expect(coreGate(state)).toEqual({ open: false, stale: true });
  });

  it("a dev-seeded core grant is honoured until a text exists, then re-asked", () => {
    const seeded = seedFromSession({
      core: true,
      voice: false,
      wellbeing: false,
      documents: false,
      health: false,
    });
    expect(coreGate(seeded)).toEqual({ open: true });
    expect(coreGate(applyTexts(seeded, { core: text("v1", "c") }))).toEqual({
      open: false,
      stale: true,
    });
  });

  it("every optional purpose granted still leaves the gate shut without core", () => {
    expect(coreGate(everythingButCore())).toEqual({ open: false, stale: false });
  });

  it("core alone opens it: no optional purpose is asked for (files/02 §7)", () => {
    let state = applyTexts(freshLedger(), { core: text("v1", "c") });
    state = grant(state, "core", NOW).state;
    for (const def of PURPOSES) {
      if (def.id !== "core" && def.basis === "explicit_consent") {
        expect(state.records[def.id].granted, def.id).toBe(false);
      }
    }
    expect(coreGate(state)).toEqual({ open: true });
  });

  it("withdrawing core shuts it at once", () => {
    const granted = grant(applyTexts(freshLedger(), { core: text("v1", "c") }), "core", NOW).state;
    expect(coreGate(withdraw(granted, "core", NOW).state)).toEqual({ open: false, stale: false });
  });
});

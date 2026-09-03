import { describe, expect, it } from "vitest";

import { applyTexts, freshLedger, grant, type LoadedText } from "../consent/ledger";
import {
  CSAT_REASONS,
  CSAT_SCORES,
  csatCollectable,
  csatReducer,
  csatResponse,
  emptyCsat,
} from "./csat";

const NOW = "2026-09-03T09:00:00.000Z";

function text(version: string, hash: string): { status: "loaded"; text: LoadedText } {
  return { status: "loaded", text: { version, textHash: hash, body: "…" } };
}

describe("the chips are 02 §5.4's, and nothing is preselected", () => {
  it("carries exactly the five reason chips the spec names, in the schema's order", () => {
    expect(CSAT_REASONS.map((r) => r.id)).toEqual([
      "too_long",
      "didnt_understand_me",
      "felt_rushed",
      "helpful",
      "felt_heard",
    ]);
  });

  it("offers the 1–5 scale as five options and starts with none chosen", () => {
    expect(CSAT_SCORES.map((s) => s.score)).toEqual([1, 2, 3, 4, 5]);
    expect(emptyCsat()).toEqual({ score: null, reason: null });
  });

  it("records one tap as one tap — a score never fabricates a reason", () => {
    const tapped = csatReducer(emptyCsat(), { type: "score", score: 4 });
    expect(tapped.score).toBe(4);
    expect(tapped.reason).toBeNull();
    expect(csatResponse(tapped)).toBeNull();
  });

  it("forms a csat.v1 body only once both halves are the patient's own answer", () => {
    let state = csatReducer(emptyCsat(), { type: "score", score: 2 });
    state = csatReducer(state, { type: "reason", reason: "felt_rushed" });
    expect(csatResponse(state)).toEqual({ score: 2, reason: "felt_rushed" });
  });
});

describe("consent gates collection, and it fails closed", () => {
  it("refuses on a fresh ledger — nothing granted, nothing collectable", () => {
    expect(csatCollectable(freshLedger())).toBe(false);
  });

  it("refuses while the satisfaction text has not landed (INT-210)", () => {
    const state = grant(freshLedger(), "satisfaction", NOW).state;
    expect(csatCollectable(state)).toBe(false);
  });

  it("refuses when some other purpose is granted instead", () => {
    let state = applyTexts(freshLedger(), { documents: text("v1", "a") });
    state = grant(state, "documents", NOW).state;
    expect(csatCollectable(state)).toBe(false);
  });

  it("allows only a satisfaction grant bound to a loaded text", () => {
    let state = applyTexts(freshLedger(), { satisfaction: text("v1", "b") });
    state = grant(state, "satisfaction", NOW).state;
    expect(csatCollectable(state)).toBe(true);
  });
});

describe("the module cannot reach the note, so it cannot gate the send", () => {
  it("imports nothing from the note layer and holds no note value", async () => {
    const { readFileSync } = await import("node:fs");
    const { join } = await import("node:path");
    const source = readFileSync(join(__dirname, "csat.ts"), "utf8");
    expect(source).not.toMatch(/from "\.\/note"|NoteState|updateNote|sentSections/);
  });
});

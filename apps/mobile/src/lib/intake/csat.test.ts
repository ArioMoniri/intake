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

  it("forms a one-tap csat.v1 body from the score alone — reason absent, never fabricated", () => {
    const tapped = csatReducer(emptyCsat(), { type: "score", score: 4 });
    expect(tapped.score).toBe(4);
    expect(tapped.reason).toBeNull();
    // INT-305: one tap is a complete event. The score is the whole answer and
    // the reason is simply absent — not defaulted, not inferred from the score,
    // and not even a key on the body a rollup could later mistake for a real one.
    const body = csatResponse(tapped);
    expect(body).toEqual({ score: 4 });
    expect(body !== null && "reason" in body).toBe(false);
  });

  it("carries the reason only when the patient tapped one — both halves, verbatim", () => {
    let state = csatReducer(emptyCsat(), { type: "score", score: 2 });
    state = csatReducer(state, { type: "reason", reason: "felt_rushed" });
    expect(csatResponse(state)).toEqual({ score: 2, reason: "felt_rushed" });
  });

  it("still forms nothing before the score — a reason alone is not a rating", () => {
    const reasonOnly = csatReducer(emptyCsat(), { type: "reason", reason: "helpful" });
    expect(reasonOnly.score).toBeNull();
    expect(csatResponse(reasonOnly)).toBeNull();
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

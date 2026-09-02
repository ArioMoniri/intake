import { describe, expect, it } from "vitest";

import { buildNote, emptyNoteState, noteReducer, type NoteAccount, type NoteState } from "./note";
import { SHARE_EXPIRY_ANCHOR, shareSummary } from "./share";

const ACCOUNT: NoteAccount = { carriedFacts: [] };

function answered(): NoteState {
  return noteReducer(emptyNoteState(), {
    type: "answer",
    questionId: "complaint",
    values: ["chest_pain"],
  });
}

describe("consent summary — what is shared", () => {
  it("names the sections that will actually be sent, in note order", () => {
    const summary = shareSummary(answered(), ACCOUNT, null);
    expect(summary.sections.length).toBeGreaterThan(0);
    expect(new Set(summary.sections).size).toBe(summary.sections.length);
  });

  it("drops a section the patient scoped off — the summary cannot promise more than the send", () => {
    const state = answered();
    const before = shareSummary(state, ACCOUNT, null).sections;
    const off = noteReducer(state, {
      type: "scope",
      sectionId: "chief_complaint",
      shared: false,
    });
    const after = shareSummary(off, ACCOUNT, null).sections;
    expect(after.length).toBe(before.length - 1);
  });

  it("says 'nothing' as an empty list rather than inventing a section", () => {
    let state = answered();
    for (const section of buildNote(state.answers, ACCOUNT, null, [], {})) {
      state = noteReducer(state, { type: "scope", sectionId: section.id, shared: false });
    }
    expect(shareSummary(state, ACCOUNT, null).sections).toEqual([]);
  });
});

describe("consent summary — with whom", () => {
  it("names the visit's recipient when there is one", () => {
    const summary = shareSummary(answered(), ACCOUNT, {
      hospital: "Acıbadem Maslak",
      department: "Kardiyoloji",
    });
    expect(summary.recipient).toEqual({ hospital: "Acıbadem Maslak", department: "Kardiyoloji" });
  });

  it("leaves the recipient null rather than filling in a plausible one", () => {
    expect(shareSummary(answered(), ACCOUNT, null).recipient).toBeNull();
  });
});

describe("consent summary — until when", () => {
  it("states the anchor 02 §2 pins, never issue time", () => {
    expect(SHARE_EXPIRY_ANCHOR).toBe("visit_datetime");
    expect(shareSummary(answered(), ACCOUNT, null).expiryAnchor).toBe("visit_datetime");
  });

  it("computes no clock of its own — the module reaches no Date at all", async () => {
    const { readFileSync } = await import("node:fs");
    const { join } = await import("node:path");
    const source = readFileSync(join(__dirname, "share.ts"), "utf8");
    expect(source).not.toMatch(/new Date|Date\.now|getTime\(/);
  });
});

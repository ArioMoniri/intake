import { describe, expect, it } from "vitest";

import { buildNote, emptyNoteState, noteReducer, type NoteAccount, type NoteState } from "./note";
import { SHARE_EXPIRY_ANCHOR, SHARE_OPENER, shareSummary } from "./share";

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
    const summary = shareSummary(answered(), ACCOUNT);
    expect(summary.sections.length).toBeGreaterThan(0);
    expect(new Set(summary.sections).size).toBe(summary.sections.length);
  });

  it("drops a section the patient scoped off — the summary cannot promise more than the send", () => {
    const state = answered();
    const before = shareSummary(state, ACCOUNT).sections;
    const off = noteReducer(state, {
      type: "scope",
      sectionId: "chief_complaint",
      shared: false,
    });
    const after = shareSummary(off, ACCOUNT).sections;
    expect(after.length).toBe(before.length - 1);
  });

  it("says 'nothing' as an empty list rather than inventing a section", () => {
    let state = answered();
    for (const section of buildNote(state.answers, ACCOUNT, null, [], {})) {
      state = noteReducer(state, { type: "scope", sectionId: section.id, shared: false });
    }
    expect(shareSummary(state, ACCOUNT).sections).toEqual([]);
  });
});

describe("consent summary — with whom (INT-589)", () => {
  // The visit's hospital receives nothing: no reader is registered for it.
  // share.tr.md's "Kimler görür" is the truth — whoever holds the link and
  // the code the patient creates and shows can open the note.
  it("names who can open the note: the holder of the link the patient creates", () => {
    expect(SHARE_OPENER).toBe("link_holder");
    expect(shareSummary(answered(), ACCOUNT).opener).toBe("link_holder");
  });

  it("near miss: the summary carries no hospital or department at all", () => {
    const summary = shareSummary(answered(), ACCOUNT) as unknown as Record<string, unknown>;
    expect(Object.keys(summary).sort()).toEqual(["expiryAnchor", "opener", "sections"]);
    expect(JSON.stringify(summary)).not.toMatch(/hospital|department/);
  });
});

describe("consent summary — until when", () => {
  it("states the anchor 02 §2 pins, never issue time", () => {
    expect(SHARE_EXPIRY_ANCHOR).toBe("visit_datetime");
    expect(shareSummary(answered(), ACCOUNT).expiryAnchor).toBe("visit_datetime");
  });

  it("computes no clock of its own — the module reaches no Date at all", async () => {
    const { readFileSync } = await import("node:fs");
    const { join } = await import("node:path");
    const source = readFileSync(join(__dirname, "share.ts"), "utf8");
    expect(source).not.toMatch(/new Date|Date\.now|getTime\(/);
  });
});

import { describe, expect, it } from "vitest";

import { getTestAccount } from "../dev/accounts";
import { buildNote, emptyNoteState, noteReducer, sentSections, type NoteState } from "./note";

const ayse = getTestAccount("ayse")!;

const HEALTH_LINES = ["Adımlar (son 7 gün): 2026-08-27 8123 adım", "Dinlenme nabzı: 58–64 atım/dk"];

function withHealth(state: NoteState = emptyNoteState()): NoteState {
  return noteReducer(state, { type: "attachHealth", lines: HEALTH_LINES });
}

describe("attachHealth — device health summary into the note draft (INT-200)", () => {
  it("empty state carries no health attachment", () => {
    expect(emptyNoteState().healthLines).toBeNull();
    const sections = buildNote([], ayse, null);
    expect(sections.find((s) => s.id === "device_health")).toBeUndefined();
  });

  it("attaching stores the lines; a second attach replaces, never duplicates", () => {
    const once = withHealth();
    expect(once.healthLines).toEqual(HEALTH_LINES);
    const twice = noteReducer(once, { type: "attachHealth", lines: ["Uyku: 6,5 saat"] });
    expect(twice.healthLines).toEqual(["Uyku: 6,5 saat"]);
  });

  it("the attached block becomes a labelled device_health section", () => {
    const state = withHealth();
    const sections = buildNote(state.answers, ayse, state.healthLines);
    const health = sections.find((s) => s.id === "device_health");
    expect(health).toBeDefined();
    expect(health!.titleKey).toBe("review.section.health");
    expect(health!.lines).toEqual(HEALTH_LINES);
  });

  it("scope-off excludes the health section from what is sent — and never blocks sending", () => {
    let state = withHealth();
    state = noteReducer(state, { type: "scope", sectionId: "device_health", shared: false });
    expect(sentSections(state, ayse).find((s) => s.id === "device_health")).toBeUndefined();
    state = noteReducer(state, { type: "send" });
    expect(state.status).toBe("sent");
  });

  it("a sent note is immutable — attach after send is a no-op", () => {
    let state = withHealth();
    state = noteReducer(state, { type: "send" });
    const after = noteReducer(state, { type: "attachHealth", lines: ["x"] });
    expect(after.healthLines).toEqual(HEALTH_LINES);
  });

  it("existing sections and answers are untouched by the attachment", () => {
    let state = emptyNoteState();
    state = noteReducer(state, { type: "answer", questionId: "complaint", values: ["pain"] });
    state = withHealth(state);
    const ids = buildNote(state.answers, ayse, state.healthLines).map((s) => s.id);
    expect(ids).toContain("chief_complaint");
    expect(ids[ids.length - 1]).toBe("device_health");
  });
});

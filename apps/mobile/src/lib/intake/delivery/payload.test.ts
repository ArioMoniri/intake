/**
 * INT-587 — the body the app PUTs to `/v1/visits/{id}/note`, built from the
 * same `buildNote` the review screen renders and checked against the server's
 * own `NotePut` bounds before anything leaves the phone.
 *
 * The rule the clinician depends on is the share scope: every section the note
 * holds travels with an explicit shared/withheld flag, so the server records
 * the withholding as a fact (INT-304) rather than inferring it from an absence.
 */
import { describe, expect, it } from "vitest";

import type { TestAccount } from "../../types/account";
import { NOTE_SECTION_IDS, emptyNoteState, noteReducer, type NoteState } from "../note";
import { NOTE_LIMITS, isNotePutBody, notePutBody } from "./payload";

/** Synthetic — an invented person with nothing carried. */
const account: TestAccount = {
  id: "synthetic-delivery-test",
  name: "Test Hasta",
  ageYears: 40,
  locale: "tr",
  consents: { core: true, voice: false, wellbeing: false, documents: false, health: false },
  visits: [],
  carriedFacts: [],
  records: [],
};

function answered(): NoteState {
  let state = emptyNoteState();
  state = noteReducer(state, { type: "answer", questionId: "complaint", values: ["pain"] });
  state = noteReducer(state, { type: "answer", questionId: "duration", values: ["days"] });
  return state;
}

describe("the PUT body mirrors the server's NotePut contract", () => {
  it("carries every built section with a rendered title, its lines and status sent", () => {
    const result = notePutBody(answered(), account);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.body.status).toBe("sent");
    expect(result.body.sections.map((s) => s.id)).toEqual(["chief_complaint", "hpi"]);
    expect(result.body.sections[0]).toEqual({
      id: "chief_complaint",
      title: "Başvuru nedeni",
      lines: ["Ağrı"],
    });
  });

  it("states the scope of every section affirmatively — shared AND withheld", () => {
    let state = answered();
    state = noteReducer(state, { type: "scope", sectionId: "hpi", shared: false });
    const result = notePutBody(state, account);
    expect(result.ok && result.body.scopes).toEqual({ chief_complaint: true, hpi: false });
  });

  it("sends the withheld section's content to the patient's own record, flagged off", () => {
    // The server stores the whole note under core and serves the clinic side
    // only the scoped-on sections (notes.read_note). The near miss is a
    // client that drops the section instead: the withholding would then be
    // recorded nowhere and a later re-send could not restore it.
    let state = answered();
    state = noteReducer(state, { type: "scope", sectionId: "hpi", shared: false });
    const result = notePutBody(state, account);
    expect(result.ok && result.body.sections.map((s) => s.id)).toContain("hpi");
  });

  it("never invents a scope for a section the note does not hold", () => {
    let state = answered();
    state = noteReducer(state, { type: "scope", sectionId: "allergies", shared: false });
    const result = notePutBody(state, account);
    expect(result.ok && Object.keys(result.body.scopes)).toEqual(["chief_complaint", "hpi"]);
  });

  it("keys every section on the one shared vocabulary", () => {
    const result = notePutBody(answered(), account);
    for (const section of result.ok ? result.body.sections : []) {
      expect(NOTE_SECTION_IDS).toContain(section.id);
    }
  });
});

describe("a body the server would refuse never leaves the phone", () => {
  it("refuses an empty note — the server requires one section", () => {
    expect(notePutBody(emptyNoteState(), account)).toEqual({ ok: false, reason: "empty" });
  });

  it("refuses a line over the server's character bound", () => {
    const state = noteReducer(answered(), {
      type: "answer",
      questionId: "extra",
      values: ["a".repeat(NOTE_LIMITS.lineChars + 1)],
    });
    expect(notePutBody(state, account)).toEqual({ ok: false, reason: "too_long" });
  });

  it("accepts a line exactly at the bound — the near miss of the refusal above", () => {
    // `Hasta notu: ` is prefixed to the extra answer, so the value is sized so
    // the rendered line lands on the bound itself.
    const prefix = "Hasta notu: ";
    const state = noteReducer(answered(), {
      type: "answer",
      questionId: "extra",
      values: ["a".repeat(NOTE_LIMITS.lineChars - prefix.length)],
    });
    expect(notePutBody(state, account).ok).toBe(true);
  });

  it("counts characters the way the server does, not UTF-16 units", () => {
    // pydantic's max_length counts code points; an astral character is two
    // UTF-16 units. A client counting units would refuse a note the server
    // accepts.
    const prefix = "Hasta notu: ";
    const state = noteReducer(answered(), {
      type: "answer",
      questionId: "extra",
      values: ["\u{1F600}".repeat(NOTE_LIMITS.lineChars - prefix.length)],
    });
    expect(notePutBody(state, account).ok).toBe(true);
  });
});

describe("a stored body is validated before it is trusted", () => {
  it("accepts what the builder produced", () => {
    const result = notePutBody(answered(), account);
    expect(result.ok && isNotePutBody(result.body)).toBe(true);
  });

  it("refuses a shape with an unknown section id or a draft status", () => {
    const result = notePutBody(answered(), account);
    if (!result.ok) throw new Error("fixture");
    expect(isNotePutBody({ ...result.body, status: "draft" })).toBe(false);
    expect(
      isNotePutBody({
        ...result.body,
        sections: [{ id: "free_text", title: "x", lines: ["y"] }],
      }),
    ).toBe(false);
    expect(isNotePutBody(null)).toBe(false);
  });
});

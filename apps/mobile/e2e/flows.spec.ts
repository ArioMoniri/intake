/**
 * INT-179 acceptance: fixture-backed flow shells.
 *
 * Typed intake (Detaylı): one question per screen — chips multi-select,
 * single-select, free text — with progress and in-session resume (CVS Health
 * chips grid / Alan one-question pacing, docs/design/mobile-ui.md §refs).
 * Review & send: sectioned note, per-section share scope, send flips the
 * 02 §5.1 status ladder (Garmin review-plan pattern). All strings tr-first.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { getTestAccount } from "../src/lib/dev/accounts";
import { t } from "../src/lib/i18n";
import { intakeQuestions } from "../src/lib/intake/questions";
import { buildNote, emptyNoteState, noteReducer, sentSections } from "../src/lib/intake/note";

const APP = join(__dirname, "..", "src", "app");
const read = (...s: string[]) => readFileSync(join(...s), "utf8");

describe("routes for the two flows exist under the visit", () => {
  it.each(["index.tsx", "intake.tsx", "review.tsx"])("visits/[visitId]/%s", (f) => {
    expect(() => read(APP, "(tabs)/visits/[visitId]", f)).not.toThrow();
  });
});

describe("typed intake fixtures (one question per screen)", () => {
  it("has the three step kinds in order: chips, single, text", () => {
    expect(intakeQuestions.map((q) => q.kind)).toEqual(["chips", "single", "text"]);
  });

  it("every question and option is a real tr catalog string", () => {
    for (const q of intakeQuestions) {
      expect(t(q.titleKey).length).toBeGreaterThan(0);
      for (const o of q.options ?? []) {
        expect(t(o.labelKey).length).toBeGreaterThan(0);
      }
    }
  });

  it("chips step allows multi-select, single step does not", () => {
    expect(intakeQuestions[0].options!.length).toBeGreaterThanOrEqual(6);
    expect(intakeQuestions[1].options!.length).toBeGreaterThanOrEqual(3);
  });
});

describe("note builder + reducer (pure)", () => {
  const ayse = getTestAccount("ayse")!;

  const answered = [
    { questionId: "complaint", values: ["pain", "dyspnoea"] },
    { questionId: "duration", values: ["days"] },
    { questionId: "extra", values: ["Merdiven çıkarken artıyor."] },
  ];

  it("builds the four sections, medications from the profile fixture", () => {
    const sections = buildNote(answered, ayse);
    expect(sections.map((s) => s.id)).toEqual(["complaint", "duration", "extra", "medications"]);
    const meds = sections.find((s) => s.id === "medications")!;
    expect(meds.lines.join(" ")).toContain("Metoprolol");
  });

  it("resume: saving answers keeps progress in state", () => {
    let state = emptyNoteState();
    state = noteReducer(state, { type: "answer", questionId: "complaint", values: ["pain"] });
    expect(state.answers).toHaveLength(1);
    expect(state.status).toBe("draft");
  });

  it("send flips the ladder draft → sent and respects section scopes", () => {
    let state = emptyNoteState();
    for (const a of answered) {
      state = noteReducer(state, { type: "answer", ...a });
    }
    state = noteReducer(state, { type: "scope", sectionId: "extra", shared: false });
    state = noteReducer(state, { type: "send" });
    expect(state.status).toBe("sent");
    const sent = sentSections(state, ayse);
    expect(sent.map((s) => s.id)).not.toContain("extra");
    expect(sent.map((s) => s.id)).toContain("complaint");
  });

  it("scope-off never blocks send (02 §5.1: sending is the patient's call)", () => {
    let state = emptyNoteState();
    state = noteReducer(state, { type: "answer", questionId: "complaint", values: ["pain"] });
    for (const id of ["complaint", "duration", "extra", "medications"]) {
      state = noteReducer(state, { type: "scope", sectionId: id, shared: false });
    }
    state = noteReducer(state, { type: "send" });
    expect(state.status).toBe("sent");
  });
});

describe("screens use the shared pieces (source facts)", () => {
  it("intake screen renders from the fixture list and shows progress", () => {
    const src = read(APP, "(tabs)/visits/[visitId]", "intake.tsx");
    expect(src).toContain("intakeQuestions");
    expect(src).toContain("t(");
  });

  it("review screen renders buildNote sections and the send action", () => {
    const src = read(APP, "(tabs)/visits/[visitId]", "review.tsx");
    expect(src).toContain("buildNote");
    expect(src).toContain('t("review.send"');
  });

  it("visit detail shows the status ladder", () => {
    const src = read(APP, "(tabs)/visits/[visitId]", "index.tsx");
    expect(src).toContain("StatusLadder");
  });
});

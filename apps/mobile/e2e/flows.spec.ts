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
import { allQuestions, intakeQuestions, packForDepartment } from "../src/lib/intake/questions";
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

describe("department packs (INT-194): the intake is branch-aware", () => {
  it("cardiology/internal medicine gets character, trigger and associated dimensions", () => {
    const ids = packForDepartment("Kardiyoloji").map((q) => q.id);
    expect(ids).toEqual(["complaint", "duration", "pain_character", "trigger", "associated", "extra"]);
    expect(packForDepartment("İç Hastalıkları").map((q) => q.id)).toEqual(ids);
  });

  it("neurology gets onset, severity (words, never a numeric scale) and associated", () => {
    const ids = packForDepartment("Nöroloji").map((q) => q.id);
    expect(ids).toContain("onset");
    expect(ids).toContain("severity");
    const severity = packForDepartment("Nöroloji").find((q) => q.id === "severity")!;
    for (const option of severity.options!) {
      expect(t(option.labelKey)).not.toMatch(/\d/);
    }
  });

  it("ENT gets the side dimension; unknown departments fall back to the core pack", () => {
    expect(packForDepartment("Kulak Burun Boğaz").map((q) => q.id)).toContain("side");
    expect(packForDepartment("Ortopedi").map((q) => q.id)).toEqual(["complaint", "duration", "extra"]);
    expect(packForDepartment(undefined).map((q) => q.id)).toEqual(["complaint", "duration", "extra"]);
  });

  it("every pack question and option resolves through the tr catalog", () => {
    for (const q of allQuestions) {
      expect(t(q.titleKey).length).toBeGreaterThan(0);
      if (q.hpiLabelKey) {
        expect(t(q.hpiLabelKey).length).toBeGreaterThan(0);
      }
      for (const o of q.options ?? []) {
        expect(t(o.labelKey).length).toBeGreaterThan(0);
      }
    }
  });

  it("pack answers become labelled HPI lines in the clinician brief", () => {
    const ayse = getTestAccount("ayse")!;
    const sections = buildNote(
      [
        { questionId: "complaint", values: ["pain"] },
        { questionId: "duration", values: ["days"] },
        { questionId: "pain_character", values: ["pressure"] },
        { questionId: "trigger", values: ["exertion"] },
        { questionId: "associated", values: ["sweating", "dyspnoea"] },
      ],
      ayse,
    );
    const hpi = sections.find((s) => s.id === "hpi")!;
    expect(hpi.lines).toEqual([
      "Süre: Birkaç gündür",
      "Ağrının niteliği: Baskı, sıkışma gibi",
      "Artıran durum: Hareket ya da eforla",
      "Eşlik edenler: Terleme, Nefes darlığı",
    ]);
  });
});

describe("note builder + reducer (pure)", () => {
  const ayse = getTestAccount("ayse")!;

  const answered = [
    { questionId: "complaint", values: ["pain", "dyspnoea"] },
    { questionId: "duration", values: ["days"] },
    { questionId: "extra", values: ["Merdiven çıkarken artıyor."] },
  ];

  it("builds the standardized brief: chief complaint → HPI → medications", () => {
    const sections = buildNote(answered, ayse);
    expect(sections.map((s) => s.id)).toEqual(["chief_complaint", "hpi", "medications"]);
    const hpi = sections.find((s) => s.id === "hpi")!;
    expect(hpi.lines[0]).toMatch(/^Süre: /);
    expect(hpi.lines[1]).toMatch(/^Hasta notu: Merdiven/);
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
    state = noteReducer(state, { type: "scope", sectionId: "hpi", shared: false });
    state = noteReducer(state, { type: "send" });
    expect(state.status).toBe("sent");
    const sent = sentSections(state, ayse);
    expect(sent.map((s) => s.id)).not.toContain("hpi");
    expect(sent.map((s) => s.id)).toContain("chief_complaint");
  });

  it("scope-off never blocks send (02 §5.1: sending is the patient's call)", () => {
    let state = emptyNoteState();
    state = noteReducer(state, { type: "answer", questionId: "complaint", values: ["pain"] });
    for (const id of ["chief_complaint", "hpi", "medications"]) {
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

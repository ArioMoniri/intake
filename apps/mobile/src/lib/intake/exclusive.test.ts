/**
 * INT-604 (ADR-043) — an exclusive "Yok" in both intake lanes.
 *
 * Owner decision M1 (17 Nov 2026, D18 scope: synthetic host, simulated patients;
 * a licensed physician signs before any real patient): every "Yok"/"Hiçbiri"
 * option of a multi-select step is exclusive. Selecting it clears the other
 * selections; selecting another option clears it. The clearing happens on
 * screen, BEFORE submit, in the one function both lanes call (`toggleOption`),
 * so the patient sees it. Nothing after submit trims a set: the note stores
 * what was submitted, and the triage request carries exactly that.
 */
import { describe, expect, it } from "vitest";

import { tr } from "../i18n/tr";
import { triageRequest } from "../red/hop";
import { emptyNoteState, noteReducer } from "./note";
import {
  allQuestions,
  exclusiveOptionIds,
  reconcileExclusive,
  toggleOption,
  type IntakeQuestion,
} from "./questions";

const NONE_LABELS = new Set(["yok", "hiçbiri", "hiçbiri yok"]);

function question(id: string): IntakeQuestion {
  const found = allQuestions.find((q) => q.id === id);
  if (found === undefined) {
    throw new Error(id);
  }
  return found;
}

const ASSOCIATED = question("associated");
const ORIGIN = { sessionId: "visit-1", visitId: "visit-1" };

describe("the served-candidate packs mark every Yok/Hiçbiri exclusive", () => {
  it("every chips option labelled Yok or Hiçbiri is exclusive", () => {
    const unmarked: string[] = [];
    for (const q of allQuestions) {
      if (q.kind !== "chips") {
        continue;
      }
      for (const option of q.options) {
        const label = tr[option.labelKey].trim().toLocaleLowerCase("tr");
        if (NONE_LABELS.has(label) && option.exclusive !== true) {
          unmarked.push(`${q.id}.${option.id}`);
        }
      }
    }
    expect(unmarked).toEqual([]);
  });

  it("no single-select step carries an exclusive option (near miss: it would assert nothing)", () => {
    const offenders = allQuestions.filter(
      (q) => q.kind === "single" && q.options.some((o) => o.exclusive === true),
    );
    expect(offenders.map((q) => q.id)).toEqual([]);
  });

  it("no step carries two exclusive options", () => {
    const offenders = allQuestions.filter(
      (q) => (q.kind === "chips" || q.kind === "single") && exclusiveOptionIds(q).size > 1,
    );
    expect(offenders.map((q) => q.id)).toEqual([]);
  });

  it("at least the associated-symptoms step has one", () => {
    expect([...exclusiveOptionIds(ASSOCIATED)]).toEqual(["none"]);
  });
});

describe("toggleOption — the one selection rule both lanes call", () => {
  it("Yok after symptoms clears them", () => {
    let selected: string[] = [];
    selected = toggleOption(ASSOCIATED, selected, "sweating");
    selected = toggleOption(ASSOCIATED, selected, "nausea");
    expect(selected).toEqual(["sweating", "nausea"]);
    expect(toggleOption(ASSOCIATED, selected, "none")).toEqual(["none"]);
  });

  it("a symptom after Yok clears Yok", () => {
    expect(toggleOption(ASSOCIATED, ["none"], "sweating")).toEqual(["sweating"]);
  });

  it("near miss: two symptoms accumulate, and a tap on a selected one removes only it", () => {
    const two = toggleOption(ASSOCIATED, ["sweating"], "nausea");
    expect(two).toEqual(["sweating", "nausea"]);
    expect(toggleOption(ASSOCIATED, two, "sweating")).toEqual(["nausea"]);
  });

  it("tapping a selected Yok deselects it", () => {
    expect(toggleOption(ASSOCIATED, ["none"], "none")).toEqual([]);
  });

  it("a single-select step keeps exactly the tapped option", () => {
    expect(toggleOption(question("duration"), ["days"], "today")).toEqual(["today"]);
  });
});

describe("reconcileExclusive — a suggested set never drops a symptom", () => {
  it("a suggestion holding a symptom AND Yok keeps the symptom and drops Yok", () => {
    // A voice suggestion arrives pre-selected; it is on screen before any
    // submit, so the patient sees the symptom and can still choose Yok.
    expect(reconcileExclusive(ASSOCIATED, ["none", "sweating"])).toEqual(["sweating"]);
  });

  it("near miss: Yok alone and symptoms alone pass unchanged", () => {
    expect(reconcileExclusive(ASSOCIATED, ["none"])).toEqual(["none"]);
    expect(reconcileExclusive(ASSOCIATED, ["sweating", "nausea"])).toEqual(["sweating", "nausea"]);
  });
});

describe("triage only ever sees the final submitted set", () => {
  it("the selections before submit never reach the note or the triage request", () => {
    let selected: string[] = [];
    selected = toggleOption(ASSOCIATED, selected, "sweating");
    selected = toggleOption(ASSOCIATED, selected, "none");
    // Nothing is committed while the patient taps; the submit is one action.
    let note = emptyNoteState();
    note = noteReducer(note, { type: "mode", mode: "hizli" });
    note = noteReducer(note, { type: "answer", questionId: "associated", values: selected });
    const request = triageRequest(note.answers, "UNKNOWN", new Date(0), ORIGIN);
    expect(request.answers).toEqual({ associated: "none" });
  });

  it("near miss: a symptom chosen after Yok is submitted whole", () => {
    const selected = toggleOption(ASSOCIATED, toggleOption(ASSOCIATED, [], "none"), "sweating");
    const note = noteReducer(emptyNoteState(), {
      type: "answer",
      questionId: "associated",
      values: selected,
    });
    expect(triageRequest(note.answers, "UNKNOWN", new Date(0), ORIGIN).answers).toEqual({
      associated: "sweating",
    });
  });

  it("the note never trims a submitted set: what was submitted is what triage reads", () => {
    // A set that bypassed the lanes reaches the reducer and the request whole,
    // so the symptom in it still reaches the rules engine (ADR-043).
    const note = noteReducer(emptyNoteState(), {
      type: "answer",
      questionId: "associated",
      values: ["sweating", "none"],
    });
    expect(triageRequest(note.answers, "UNKNOWN", new Date(0), ORIGIN).answers).toEqual({
      associated: ["sweating", "none"],
    });
  });
});

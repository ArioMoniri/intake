/**
 * INT-235 realtime section panel view model: the muayene sections of the
 * clinician note, filling in AS the conversation runs. Labels come from the
 * PACK (hpiLabelKey, with the same complaint/extra labelling buildNote
 * uses) — never a hardcoded section list, so a different department pack
 * renders its own dimensions. Rows carry the chosen values plus the
 * patient's verbatim quote as provenance; pending suggestions are marked
 * confirmable (the panel-row confirm), the current turn's candidate shows
 * as suggested but is confirmed in the turn itself, never twice.
 *
 * The meds line mirrors buildNote exactly: carried from earlier visits,
 * display-only, outside the pack counts, and marked `carried` rather than
 * `answered` (INT-247). No clinical content is invented here.
 */
import { describe, expect, it } from "vitest";

import type { CarriedFact } from "../intake/carriedFacts";
import { applicableQuestions, intakeQuestions, packForDepartment } from "../intake/questions";
import { sectionLabelKey, sectionPanelModel } from "./sectionPanel";
import type { DialogueStreamState } from "./stream";

const cardio = packForDepartment("Kardiyoloji");
const general = intakeQuestions;

/** Synthetic carried facts (INT-247) — recorded at an earlier visit. */
const CARRIED: CarriedFact[] = ["Metoprolol", "Aspirin"].map((text, index) => ({
  id: `cf-${index}`,
  kind: "medication",
  text,
  source: "clinician_accepted_note",
  assertedBy: { role: "clinician" },
  assertedAt: "2026-05-12",
  sourceVisitId: "v-0",
}));

function idle(overrides: Partial<DialogueStreamState> = {}): DialogueStreamState {
  return {
    turn: { phase: "speaking", step: 0, intent: "question" },
    pending: {},
    answers: {},
    asked: [],
    inflight: [],
    seq: {},
    stream: [],
    ...overrides,
  };
}

describe("sectionLabelKey — pack-driven labels, buildNote's mapping", () => {
  it("mirrors the note builder for every cardio section", () => {
    expect(cardio.map(sectionLabelKey)).toEqual([
      "review.section.cc", // complaint — chief complaint section
      "review.hpi.duration",
      "intake.hpi.onset",
      "intake.hpi.character",
      "intake.hpi.radiation",
      "intake.hpi.radiationSide",
      "intake.hpi.breathTiming",
      "intake.hpi.breathLying",
      "intake.hpi.trigger",
      "intake.hpi.associated",
      "intake.hpi.palpitation",
      "intake.hpi.severity",
      "review.hpi.patientNote", // extra — the free note line
    ]);
  });
});

describe("sectionPanelModel — rows fill in realtime", () => {
  const cardioBase = applicableQuestions(cardio, []);

  it("empty dialogue: every row empty, nothing filled, total is the APPLICABLE set", () => {
    const model = sectionPanelModel(cardio, idle(), []);
    expect(model.total).toBe(cardioBase.length);
    expect(model.total).toBeLessThan(cardio.length); // gated sections stay out
    expect(model.filled).toBe(0);
    expect(model.rows).toHaveLength(cardioBase.length);
    for (const row of model.rows) {
      expect(row.status).toBe("empty");
      expect(row.confirmable).toBe(false);
    }
  });

  it("the denominator GROWS when an answer opens a gate — the note has no fixed length", () => {
    const opened = sectionPanelModel(
      cardio,
      idle({ answers: { complaint: { values: ["pain"], quote: "göğsümde baskı var" } } }),
      [],
    );
    expect(opened.total).toBe(cardioBase.length + 2); // pain_character + radiation
    expect(opened.rows.map((row) => row.questionId)).toContain("pain_character");
  });

  it("a section the flow does not ask never appears, suggestion or not", () => {
    const model = sectionPanelModel(
      cardio,
      idle({
        answers: { complaint: { values: ["fever"], quote: "ateşim var" } },
        pending: { radiation: { values: ["arm"], quote: "koluma vuruyor" } },
      }),
      [],
    );
    expect(model.rows.map((row) => row.questionId)).not.toContain("radiation");
  });

  it("answered rows carry the committed values and the quote as provenance", () => {
    const model = sectionPanelModel(
      general,
      idle({
        turn: { phase: "speaking", step: 1, intent: "question" },
        answers: { complaint: { values: ["pain"], quote: "göğsümde baskı var" } },
      }),
      [],
    );
    expect(model.rows[0]).toEqual({
      questionId: "complaint",
      labelKey: "review.section.cc",
      status: "answered",
      values: ["pain"],
      quote: "göğsümde baskı var",
      confirmable: false,
    });
    expect(model.filled).toBe(1);
  });

  it("pending suggestions show as suggested AND confirmable — the panel-row confirm", () => {
    const model = sectionPanelModel(
      cardio,
      idle({ pending: { duration: { values: ["days"], quote: "birkaç gündür böyle" } } }),
      [],
    );
    const duration = model.rows[1];
    expect(duration.status).toBe("suggested");
    expect(duration.confirmable).toBe(true);
    expect(duration.values).toEqual(["days"]);
    expect(duration.quote).toBe("birkaç gündür böyle");
    expect(model.filled).toBe(0); // suggestions are not answers (invariant 1)
  });

  it("the current turn's candidate shows as suggested but NOT panel-confirmable", () => {
    const confirming = sectionPanelModel(
      cardio,
      idle({
        turn: {
          phase: "confirming",
          step: 0,
          candidate: { values: ["pain"], quote: "göğsümde baskı var" },
        },
      }),
      [],
    );
    expect(confirming.rows[0].status).toBe("suggested");
    expect(confirming.rows[0].confirmable).toBe(false);

    const confirmSpeech = sectionPanelModel(
      cardio,
      idle({
        turn: {
          phase: "speaking",
          step: 1,
          intent: "confirm",
          candidate: { values: ["days"], quote: "birkaç gündür böyle" },
        },
      }),
      [],
    );
    expect(confirmSpeech.rows[1].status).toBe("suggested");
    expect(confirmSpeech.rows[1].confirmable).toBe(false);
  });

  it("a committed-empty answer reads answered but never counts as a filled section", () => {
    const model = sectionPanelModel(
      general,
      idle({ answers: { extra: { values: [], quote: "" } } }),
      [],
    );
    expect(model.rows[2].status).toBe("answered");
    expect(model.filled).toBe(0);
  });

  it("appends the carried meds line exactly as buildNote does — outside the counts", () => {
    const model = sectionPanelModel(general, idle(), CARRIED);
    const last = model.rows[model.rows.length - 1];
    expect(last).toEqual({
      questionId: "medications",
      labelKey: "review.section.medications",
      // INT-247: carried, NOT answered — the panel may not show an earlier
      // visit's record as something the patient told us in this one.
      status: "carried",
      values: ["Metoprolol", "Aspirin"],
      quote: "",
      confirmable: false,
    });
    expect(model.total).toBe(general.length); // pack sections only
    expect(model.filled).toBe(0);

    const withoutMeds = sectionPanelModel(general, idle(), []);
    expect(withoutMeds.rows).toHaveLength(general.length);
  });
});

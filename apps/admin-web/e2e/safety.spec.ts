/**
 * INT-185 — Clinical Quality & Safety module, console side (files/08 §4 D/E;
 * INT-175, INT-180).
 *
 * Acceptance, verbatim: *"triage events, false-RED queue, PolicyGuard classes,
 * acceptance by specialty"*.
 *
 * **What this runs against.** `e2e/fixtures/safety.payload.json` is the
 * `GET /admin/quality-safety` composite, recorded from the real sources by
 * `scripts/dev/record_safety_fixture.py` (the same "record, do not hand-mock"
 * discipline as models/compliance/protocols): triage events are keyed by
 * `clinical_schemas.triage.TriageLevel` and the metric id `triage.events_total`;
 * the false-RED queue's contract (scope, roles, verdict labels, section
 * reasons, the `HB-L6` content blocker) is `intake_platform.observability.
 * annotation`'s `false_red_review` queue verbatim; the PolicyGuard classes are
 * `intake_voice_runtime.talker.policy_guard.ViolationClass`; and acceptance is
 * `note.acceptance_rate` rolled up over the real intake branches of the
 * taxonomy. Asserting on the presentation tree the renderer returns — not a
 * DOM — matches the repo's node lane (there is no browser runner).
 *
 * **The negative controls.** Every property the acceptance and the invariants
 * turn on is paired with a near-miss the renderer must refuse: a RED/YELLOW
 * routing count attributed to the LLM (invariant 1), a candidate cap above
 * YELLOW_REVIEW (invariant 1), a false-RED item that would downgrade the RED
 * (invariant 1 — the queue annotates, never downgrades), a queue pointer
 * carrying free-text patient content (invariant 6), a payload claiming a
 * granted content-read path (HB-L6), a review verdict outside the closed
 * annotation vocabulary, a PolicyGuard class outside the sealed set
 * (invariant 2), an acceptance rate shown without a corpus and a date
 * (invariant 20), and impossible acceptance counts. The emptyable surfaces are
 * exercised with rows constructed inline, exactly as compliance.spec.ts and
 * protocols.spec.ts do.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { UnlabelledMeasurement } from "../src/models/measurement";
import {
  AcceptanceCountsInconsistent,
  ClinicalContentLeaked,
  ContentReadNotRefused,
  ForbiddenReviewVerdict,
  PolicyGuardCountWithoutScrape,
  renderAcceptanceBySpecialty,
  renderFalseRedQueue,
  renderPolicyGuardClasses,
  renderQualitySafetyModule,
  renderTriageEvents,
  TriageDowngradeInFalseRedQueue,
  TriageNotFromRulesEngine,
  UnknownPolicyClass,
  type AcceptanceBySpecialtyPayload,
  type AcceptanceRow,
  type FalseRedItem,
  type FalseRedQueuePayload,
  type PolicyGuardPayload,
  type QualitySafetyPayload,
  type TriageEventsPayload,
} from "../src/safety/module";

const FIXTURES = join(__dirname, "fixtures");

function payload(): QualitySafetyPayload {
  return JSON.parse(
    readFileSync(join(FIXTURES, "safety.payload.json"), "utf8"),
  ) as QualitySafetyPayload;
}

/** A well-formed false-RED item: pointers only, no review yet. Tests override
 * one field to build each near-miss — the shape the queue would carry once an
 * item store lands (it is empty today). */
function falseRedItem(overrides: Partial<FalseRedItem> = {}): FalseRedItem {
  return {
    item_id: "item-0001",
    session_id_hash: "sess.9f3a2c",
    work_id: "work.0007",
    span_ref: "span:triage/0007",
    rule_id: "cardiac.acs.chest_pain",
    branch_id: "kardiyoloji",
    created_at_utc: "2026-09-06T10:00:00Z",
    review: null,
    ...overrides,
  };
}

function queue(items: readonly FalseRedItem[]): FalseRedQueuePayload {
  return { ...payload().false_red_queue, items };
}

describe("triage events (RED/YELLOW/GREEN distribution)", () => {
  it("paints one row per triage level, each attributed to the rules engine", () => {
    const view = renderTriageEvents(payload().triage_events);
    expect(view.levels.map((r) => r.level)).toEqual(["GREEN", "YELLOW", "RED"]);
    for (const row of view.levels) {
      expect(row.producedBy).toEqual("rules_engine");
    }
    // the LLM's only triage output is a candidate flag, capped here (invariant 1)
    expect(view.candidateFlagCap).toEqual("YELLOW_REVIEW");
  });

  it("shows the honest empty state: the metric is planned and counts are 0 (inv 17)", () => {
    const view = renderTriageEvents(payload().triage_events);
    expect(view.metricStatus).toEqual("planned");
    for (const row of view.levels) {
      expect(row.count).toEqual("0");
    }
    expect(view.note.length).toBeGreaterThan(0);
  });

  it("renders counts as non-grouped atoms a reader cannot misread (inv 22)", () => {
    const live = payload().triage_events;
    const tampered: TriageEventsPayload = {
      ...live,
      levels: [{ level: "RED", count: 1200, produced_by: "rules_engine" }],
    };
    const view = renderTriageEvents(tampered);
    expect(view.levels[0]!.count).toEqual("1200");
    expect(view.levels[0]!.count).not.toMatch(/[,. ]/);
  });

  it("refuses a RED count attributed to anything but the rules engine (invariant 1)", () => {
    const live = payload().triage_events;
    const tampered: TriageEventsPayload = {
      ...live,
      levels: [{ level: "RED", count: 3, produced_by: "llm" }],
    };
    expect(() => renderTriageEvents(tampered)).toThrow(TriageNotFromRulesEngine);
  });

  it("refuses a YELLOW count attributed to the LLM (invariant 1)", () => {
    const live = payload().triage_events;
    const tampered: TriageEventsPayload = {
      ...live,
      levels: [{ level: "YELLOW", count: 5, produced_by: "extraction" }],
    };
    expect(() => renderTriageEvents(tampered)).toThrow(TriageNotFromRulesEngine);
  });

  it("refuses a candidate cap above the YELLOW_REVIEW ceiling (invariant 1)", () => {
    const live = payload().triage_events;
    const tampered: TriageEventsPayload = { ...live, candidate_flag_cap: "RED" };
    expect(() => renderTriageEvents(tampered)).toThrow(TriageNotFromRulesEngine);
  });
});

describe("false-RED queue (annotation only, never a downgrade)", () => {
  it("carries the false_red_review contract from INT-175, and is empty today", () => {
    const view = renderFalseRedQueue(payload().false_red_queue);
    expect(view.queueId).toEqual("false_red_review");
    expect(view.reviewerRoles).toContain("clinical_lead");
    expect(view.labels).toEqual(["accept", "edit", "reject"]);
    expect(view.items).toEqual([]);
    expect(view.empty).toBe(true);
  });

  it("shows the content read is refused, not granted (HB-L6, files/08 §2.6)", () => {
    const view = renderFalseRedQueue(payload().false_red_queue);
    expect(view.contentReadState).toEqual("refused");
    expect(view.contentBlocker).toEqual("HB-L6");
  });

  it("renders a pointer item and a closed-enum review with no free text", () => {
    const view = renderFalseRedQueue(
      queue([
        falseRedItem({
          review: {
            label: "reject",
            section_reason: "red_flags",
            reviewer_role: "clinical_lead",
            recorded_at_utc: "2026-09-06T11:00:00Z",
          },
        }),
      ]),
    );
    const item = view.items[0]!;
    expect(item.ruleId).toEqual("cardiac.acs.chest_pain");
    expect(item.review?.label).toEqual("reject");
    expect(view.empty).toBe(false);
  });

  it("refuses an item that would downgrade the RED (invariant 1)", () => {
    // near-miss: a tampered body slips a level mutation onto a review surface
    // whose only job is to annotate — a rules-engine RED is inviolable
    const tampered = { ...falseRedItem(), downgrades_to: "GREEN" } as unknown as FalseRedItem;
    expect(() => renderFalseRedQueue(queue([tampered]))).toThrow(TriageDowngradeInFalseRedQueue);
  });

  it("refuses a queue pointer carrying free-text patient content (invariant 6)", () => {
    const tampered = falseRedItem({ span_ref: "hastanın göğsü ağrıyor" });
    expect(() => renderFalseRedQueue(queue([tampered]))).toThrow(ClinicalContentLeaked);
  });

  it("refuses a payload asserting a granted content-read path (HB-L6)", () => {
    const tampered: FalseRedQueuePayload = {
      ...payload().false_red_queue,
      content_read_state: "granted",
    };
    expect(() => renderFalseRedQueue(tampered)).toThrow(ContentReadNotRefused);
  });

  it("refuses a review verdict outside the closed annotation vocabulary", () => {
    const tampered = falseRedItem({
      review: {
        label: "downgrade",
        section_reason: "red_flags",
        reviewer_role: "clinical_lead",
        recorded_at_utc: "2026-09-06T11:00:00Z",
      },
    });
    expect(() => renderFalseRedQueue(queue([tampered]))).toThrow(ForbiddenReviewVerdict);
  });

  it("refuses a reviewer role the queue does not permit (four-eyes roles, files/08 §2.1)", () => {
    const tampered = falseRedItem({
      review: {
        label: "reject",
        section_reason: "red_flags",
        reviewer_role: "support_engineer",
        recorded_at_utc: "2026-09-06T11:00:00Z",
      },
    });
    expect(() => renderFalseRedQueue(queue([tampered]))).toThrow(ForbiddenReviewVerdict);
  });
});

describe("PolicyGuard classes (invariant 2 categories)", () => {
  it("paints one row per sealed violation class", () => {
    const view = renderPolicyGuardClasses(payload().policyguard_classes);
    expect(view.classes.map((c) => c.className)).toEqual([
      "diagnosis",
      "treatment",
      "prognosis",
      "multi_question",
      "too_long",
      "register",
      "jargon",
    ]);
    expect(view.metricStatus).toEqual("live");
  });

  it("with no scrape behind it, says why and paints no count (INT-565; inv 17)", () => {
    const view = renderPolicyGuardClasses(payload().policyguard_classes);
    expect(view.sourceAvailable).toBe(false);
    expect(view.sourceReason).toEqual("prometheus_unconfigured");
    expect(view.window).toEqual("24h");
    expect(view.classes.every((c) => c.count === null)).toBe(true);
  });

  it("renders counts as non-grouped atoms once a scrape backs them (inv 22)", () => {
    const live = payload().policyguard_classes;
    const tampered: PolicyGuardPayload = {
      ...live,
      source_available: true,
      source_reason: null,
      classes: [{ class: "diagnosis", count: 4200 }],
    };
    const view = renderPolicyGuardClasses(tampered);
    expect(view.classes[0]!.count).toEqual("4200");
    expect(view.classes[0]!.count).not.toMatch(/[,. ]/);
  });

  it("refuses a count while no scrape backs the section — a zero included (inv 17)", () => {
    const live = payload().policyguard_classes;
    const tampered: PolicyGuardPayload = { ...live, classes: [{ class: "jargon", count: 0 }] };
    expect(() => renderPolicyGuardClasses(tampered)).toThrow(PolicyGuardCountWithoutScrape);
  });

  it("refuses a class outside the sealed set (invariant 2)", () => {
    const live = payload().policyguard_classes;
    const tampered: PolicyGuardPayload = {
      ...live,
      classes: [...live.classes, { class: "made_up_class", count: 1 }],
    };
    expect(() => renderPolicyGuardClasses(tampered)).toThrow(UnknownPolicyClass);
  });
});

describe("acceptance by specialty (counts, never an accuracy claim)", () => {
  it("paints one row per intake specialty, all empty today (inv 17)", () => {
    const view = renderAcceptanceBySpecialty(payload().acceptance_by_specialty);
    expect(view.rows.length).toBeGreaterThan(0);
    const kardiyoloji = view.rows.find((r) => r.branchId === "kardiyoloji");
    expect(kardiyoloji).toBeDefined();
    expect(kardiyoloji!.nameTr).toEqual("Kardiyoloji");
    expect(kardiyoloji!.hasData).toBe(false);
    expect(kardiyoloji!.rate).toBeNull();
    // Acil Tıp is not an intake specialty — no note is produced for it
    expect(view.rows.some((r) => r.branchId === "acil_tip")).toBe(false);
  });

  it("renders a rate only as a labelled measurement — corpus and date (invariant 20)", () => {
    const rows: AcceptanceRow[] = [
      {
        branch_id: "kardiyoloji",
        name_tr: "Kardiyoloji",
        cluster: "medical",
        delivered: 40,
        accepted: 34,
        measurement: {
          metric: "note acceptance",
          value: 0.85,
          unit: "ratio",
          corpus: "internal pilot notes",
          measuredOn: "2026-09-06",
        },
      },
    ];
    const withData: AcceptanceBySpecialtyPayload = {
      ...payload().acceptance_by_specialty,
      rows,
    };
    const view = renderAcceptanceBySpecialty(withData);
    expect(view.rows[0]!.hasData).toBe(true);
    expect(view.rows[0]!.rate).toContain("measured 2026-09-06");
    expect(view.rows[0]!.rate).toContain("internal pilot notes");
  });

  it("refuses a rate shown as a bare number with no corpus or date (invariant 20)", () => {
    const rows: AcceptanceRow[] = [
      {
        branch_id: "kardiyoloji",
        name_tr: "Kardiyoloji",
        cluster: "medical",
        delivered: 40,
        accepted: 34,
        measurement: {
          metric: "note acceptance",
          value: 0.85,
          unit: "ratio",
          corpus: "",
          measuredOn: "",
        },
      },
    ];
    const tampered: AcceptanceBySpecialtyPayload = {
      ...payload().acceptance_by_specialty,
      rows,
    };
    expect(() => renderAcceptanceBySpecialty(tampered)).toThrow(UnlabelledMeasurement);
  });

  it("refuses impossible counts (accepted cannot exceed delivered)", () => {
    const rows: AcceptanceRow[] = [
      {
        branch_id: "kardiyoloji",
        name_tr: "Kardiyoloji",
        cluster: "medical",
        delivered: 3,
        accepted: 9,
        measurement: null,
      },
    ];
    const tampered: AcceptanceBySpecialtyPayload = {
      ...payload().acceptance_by_specialty,
      rows,
    };
    expect(() => renderAcceptanceBySpecialty(tampered)).toThrow(AcceptanceCountsInconsistent);
  });
});

describe("the whole module composes", () => {
  it("renders every surface from the recorded composite", () => {
    const view = renderQualitySafetyModule(payload());
    expect(view.triageEvents.levels.length).toEqual(3);
    expect(view.falseRedQueue.queueId).toEqual("false_red_review");
    expect(view.policyGuardClasses.classes.length).toEqual(7);
    expect(view.acceptanceBySpecialty.rows.length).toBeGreaterThan(0);
  });
});

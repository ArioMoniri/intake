/**
 * INT-186 — Experience & Satisfaction module, console side (files/08 §3, §4
 * group F/G; INT-240, INT-241, INT-180).
 *
 * Acceptance, verbatim: *"filters by branch/profile/clinic; SDS-01-style export
 * for hospital tenants"*.
 *
 * **What this runs against.** `e2e/fixtures/experience.payload.json` is the
 * `GET /admin/experience` composite, recorded from the real sources by
 * `scripts/dev/record_experience_fixture.py` (the same "record, do not
 * hand-mock" discipline as models/compliance/protocols/safety): CSAT / NPS /
 * clinician-pulse are the INT-240 rollups keyed by the catalogued metric ids
 * (`csat.score`, `csat.reason`, `nps.monthly`, `clinician.pulse`), each produced
 * by the real rollup over an empty response set so its empty state is the
 * platform's; the CSAT reason enum is `clinical_schemas.events.CsatReason`; the
 * k floor is `intake_platform.analytics.K_ANONYMITY_FLOOR`; and the SDS-01
 * export is `intake_metrics.sds01.sds01_table` over the real `WAIT_SOURCES`, its
 * column set the committed `SDS01_COLUMNS`. Asserting on the presentation tree
 * the renderer returns — not a DOM — matches the repo's node lane.
 *
 * **The negative controls.** Every property the acceptance and the invariants
 * turn on is paired with a near-miss the renderer must refuse: a small-cohort
 * mean or distribution shown below the k floor (files/06 §8; files/08 §0c F9), a
 * free-text or non-id-shaped distribution key (invariant 6), a CSAT reason
 * outside the sealed enum, a target rendered beside a figure (invariant 20), a
 * branch/profile/clinic filter asserted available (files/08 §0c F9; invariant
 * 18), a tenant scope taken from a query parameter (F9 IDOR), an SDS-01 column
 * that would re-identify a cohort, a mis-sized export row, and an export cell
 * that would evaluate in a spreadsheet (invariant 47). The emptyable surfaces
 * are exercised with rows constructed inline, exactly as safety.spec.ts does.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import {
  ExperienceFilterEnabled,
  renderCsat,
  renderExperienceModule,
  renderFilters,
  renderNps,
  renderPulse,
  renderSds01Export,
  SatisfactionFigureLeaked,
  SatisfactionTargetRendered,
  SdsColumnForbidden,
  SdsRowArityMismatch,
  SuppressedCohortLeaked,
  TenantFromQuery,
  UnknownCsatReason,
  UnsafeExportCell,
  type CsatRollupPayload,
  type ExperiencePayload,
  type FiltersPayload,
  type NpsRollupPayload,
  type PulseRollupPayload,
  type Sds01ExportPayload,
} from "../src/experience/module";

const FIXTURES = join(__dirname, "fixtures");

function payload(): ExperiencePayload {
  return JSON.parse(
    readFileSync(join(FIXTURES, "experience.payload.json"), "utf8"),
  ) as ExperiencePayload;
}

/** A well-formed CSAT rollup ABOVE the floor, built inline — the shape the
 * console will carry once responses land (the fixture is empty today). */
function csatWithData(overrides: Partial<CsatRollupPayload> = {}): CsatRollupPayload {
  return {
    ...payload().csat,
    n: 40,
    suppressed: false,
    mean_score: 4.4,
    score_counts: { "1": 1, "2": 2, "3": 5, "4": 12, "5": 20 },
    reason_counts: { helpful: 20, felt_heard: 12, too_long: 8 },
    ...overrides,
  };
}

function npsWithData(overrides: Partial<NpsRollupPayload> = {}): NpsRollupPayload {
  return {
    ...payload().nps,
    n: 30,
    suppressed: false,
    promoters: 18,
    passives: 8,
    detractors: 4,
    nps: 46.67,
    ...overrides,
  };
}

function pulseWithData(overrides: Partial<PulseRollupPayload> = {}): PulseRollupPayload {
  return {
    ...payload().pulse,
    n: 12,
    suppressed: false,
    mean_score: 3.8,
    score_counts: { "2": 1, "3": 3, "4": 5, "5": 3 },
    ...overrides,
  };
}

describe("CSAT (score distribution + sealed reason enum)", () => {
  it("shows the honest empty state: below the k floor, only the count survives (inv 17)", () => {
    const view = renderCsat(payload().csat);
    expect(view.metricId).toEqual("csat.score");
    expect(view.reasonMetricId).toEqual("csat.reason");
    expect(view.metricStatus).toEqual("live");
    expect(view.n).toEqual("0");
    expect(view.suppressed).toBe(true);
    expect(view.hasData).toBe(false);
    expect(view.meanScore).toBeNull();
    expect(view.scores).toEqual([]);
    expect(view.reasons).toEqual([]);
    // the figure names its cohort and window (invariant 20)
    expect(view.cohort.windowStart.length).toBeGreaterThan(0);
    expect(view.cohort.measuredAt.length).toBeGreaterThan(0);
  });

  it("paints the score distribution and reason counts once above the floor", () => {
    const view = renderCsat(csatWithData());
    expect(view.hasData).toBe(true);
    expect(view.meanScore).toEqual("4.4");
    expect(view.scores.map((b) => b.key)).toEqual(["1", "2", "3", "4", "5"]);
    expect(view.reasons.find((b) => b.key === "helpful")?.count).toEqual("20");
  });

  it("renders counts as non-grouped atoms a reader cannot misread (inv 22)", () => {
    const view = renderCsat(csatWithData({ n: 1200, score_counts: { "5": 1200 } }));
    expect(view.n).toEqual("1200");
    expect(view.n).not.toMatch(/[,. ]/);
    expect(view.scores[0]!.count).toEqual("1200");
  });

  it("refuses a mean shown for a cohort below the k floor (files/06 §8, F9)", () => {
    // near-miss: a suppressed cohort that kept its mean — the exact small-cohort
    // re-identification the floor exists to stop
    const tampered: CsatRollupPayload = {
      ...payload().csat,
      n: 4,
      suppressed: true,
      mean_score: 4.5,
    };
    expect(() => renderCsat(tampered)).toThrow(SuppressedCohortLeaked);
  });

  it("refuses a distribution shown for a suppressed cohort (files/06 §8, F9)", () => {
    const tampered: CsatRollupPayload = {
      ...payload().csat,
      n: 6,
      suppressed: true,
      score_counts: { "5": 6 },
    };
    expect(() => renderCsat(tampered)).toThrow(SuppressedCohortLeaked);
  });

  it("refuses a non-id-shaped distribution key — the transcript reappearing (inv 6)", () => {
    const tampered = csatWithData({ score_counts: { "hastanın notu": 3 } });
    expect(() => renderCsat(tampered)).toThrow(SatisfactionFigureLeaked);
  });

  it("refuses a CSAT reason outside the sealed enum", () => {
    const tampered = csatWithData({ reason_counts: { made_up_reason: 3 } });
    expect(() => renderCsat(tampered)).toThrow(UnknownCsatReason);
  });

  it("refuses a target rendered beside the figure (invariant 20)", () => {
    // near-miss: csat.score's catalogue target (>= 4.3) leaks onto the body as a
    // verdict — a measurement is not a claim
    const tampered = { ...csatWithData(), target: ">= 4.3" } as unknown as CsatRollupPayload;
    expect(() => renderCsat(tampered)).toThrow(SatisfactionTargetRendered);
  });
});

describe("NPS (promoter/passive/detractor split)", () => {
  it("shows the honest empty state below the floor (inv 17)", () => {
    const view = renderNps(payload().nps);
    expect(view.metricId).toEqual("nps.monthly");
    expect(view.suppressed).toBe(true);
    expect(view.hasData).toBe(false);
    expect(view.nps).toBeNull();
    expect(view.cells).toEqual([]);
  });

  it("paints the split and the NPS once above the floor", () => {
    const view = renderNps(npsWithData());
    expect(view.hasData).toBe(true);
    expect(view.nps).toEqual("46.67");
    expect(view.cells.map((c) => c.label)).toEqual(["promoters", "passives", "detractors"]);
    expect(view.cells.find((c) => c.label === "promoters")?.value).toEqual("18");
  });

  it("refuses an NPS shown for a cohort below the k floor (files/06 §8, F9)", () => {
    const tampered: NpsRollupPayload = {
      ...payload().nps,
      n: 5,
      suppressed: true,
      nps: 40,
    };
    expect(() => renderNps(tampered)).toThrow(SuppressedCohortLeaked);
  });

  it("refuses a promoter count shown for a suppressed cohort", () => {
    const tampered: NpsRollupPayload = {
      ...payload().nps,
      n: 5,
      suppressed: true,
      promoters: 3,
    };
    expect(() => renderNps(tampered)).toThrow(SuppressedCohortLeaked);
  });
});

describe("clinician pulse (counts only, never a clinician_ref)", () => {
  it("shows the honest empty state below the floor (inv 17)", () => {
    const view = renderPulse(payload().pulse);
    expect(view.metricId).toEqual("clinician.pulse");
    expect(view.suppressed).toBe(true);
    expect(view.hasData).toBe(false);
    expect(view.meanScore).toBeNull();
    expect(view.scores).toEqual([]);
  });

  it("paints the score distribution once above the floor", () => {
    const view = renderPulse(pulseWithData());
    expect(view.hasData).toBe(true);
    expect(view.meanScore).toEqual("3.8");
    expect(view.scores.find((b) => b.key === "4")?.count).toEqual("5");
  });

  it("refuses a mean shown for a cohort below the k floor", () => {
    const tampered: PulseRollupPayload = {
      ...payload().pulse,
      n: 3,
      suppressed: true,
      mean_score: 4.0,
    };
    expect(() => renderPulse(tampered)).toThrow(SuppressedCohortLeaked);
  });
});

describe("filters by branch / profile / clinic (mechanism, fail closed)", () => {
  it("offers every named dimension and marks all unavailable with a reason (inv 17, 18)", () => {
    const view = renderFilters(payload().filters);
    expect(view.dimensions.map((d) => d.id)).toEqual(["branch", "profile", "clinic"]);
    for (const dim of view.dimensions) {
      expect(dim.available).toBe(false);
      expect(dim.reason.length).toBeGreaterThan(0);
    }
    // the window is required and tenant scope is a token claim (invariant 20; F9)
    expect(view.windowRequired).toBe(true);
    expect(view.tenantScope).toEqual("token_claim");
    expect(view.kFloor).toEqual("10");
  });

  it("refuses a branch filter asserted available — the F9 slice the data cannot support", () => {
    const dims = payload().filters.dimensions.map((d) =>
      d.id === "branch" ? { ...d, available: true } : d,
    );
    const tampered: FiltersPayload = { ...payload().filters, dimensions: dims };
    expect(() => renderFilters(tampered)).toThrow(ExperienceFilterEnabled);
  });

  it("refuses a clinic filter asserted available (files/08 §0c F9)", () => {
    const dims = payload().filters.dimensions.map((d) =>
      d.id === "clinic" ? { ...d, available: true } : d,
    );
    const tampered: FiltersPayload = { ...payload().filters, dimensions: dims };
    expect(() => renderFilters(tampered)).toThrow(ExperienceFilterEnabled);
  });

  it("refuses tenant scope taken from a query parameter (F9 IDOR, files/08 §8 (a))", () => {
    const tampered: FiltersPayload = { ...payload().filters, tenant_scope: "query_param" };
    expect(() => renderFilters(tampered)).toThrow(TenantFromQuery);
  });

  it("refuses a tenant filter dimension — tenant is scope, never a filter (F9)", () => {
    const dims = [
      ...payload().filters.dimensions,
      { id: "tenant", label_tr: "Tenant", label_en: "Tenant", available: false, reason: "x" },
    ];
    const tampered: FiltersPayload = { ...payload().filters, dimensions: dims };
    expect(() => renderFilters(tampered)).toThrow(TenantFromQuery);
  });
});

describe("SDS-01 style export (committed shape, aggregate only)", () => {
  it("carries the committed SDS01_COLUMNS and no re-identifying column (F9)", () => {
    const view = renderSds01Export(payload().sds01_export);
    expect(view.columns).toEqual([
      "metric_id",
      "unit",
      "window_start",
      "window_end",
      "measured_at",
      "n",
      "mean",
      "status",
      "note",
    ]);
    expect(view.aggregateOnly).toBe(true);
    expect(view.tenantScope).toEqual("token_claim");
    // recorded from the real serialiser: five wait sources, none observed yet
    expect(view.rows.length).toEqual(5);
    expect(view.empty).toBe(false);
    const first = view.rows[0]!;
    expect(first[0]).toEqual("wait.time_to_first_question_s");
    expect(first[7]).toEqual("source_unavailable");
  });

  it("renders a genuinely empty export as empty, not as a zero row (inv 17)", () => {
    const view = renderSds01Export({ ...payload().sds01_export, rows: [] });
    expect(view.empty).toBe(true);
    expect(view.rows).toEqual([]);
  });

  it("refuses a clinic column — SDS-01's branch-level analysis is F9 here", () => {
    const tampered: Sds01ExportPayload = {
      ...payload().sds01_export,
      columns: [...payload().sds01_export.columns, "clinic"],
    };
    expect(() => renderSds01Export(tampered)).toThrow(SdsColumnForbidden);
  });

  it("refuses a branch column (files/08 §0c F9; INT-241 §4)", () => {
    const tampered: Sds01ExportPayload = {
      ...payload().sds01_export,
      columns: [...payload().sds01_export.columns, "branch"],
    };
    expect(() => renderSds01Export(tampered)).toThrow(SdsColumnForbidden);
  });

  it("refuses an export not marked aggregate-only", () => {
    const tampered: Sds01ExportPayload = { ...payload().sds01_export, aggregate_only: false };
    expect(() => renderSds01Export(tampered)).toThrow(SdsColumnForbidden);
  });

  it("refuses a tenant scope not from the token claim (F9 IDOR)", () => {
    const tampered: Sds01ExportPayload = { ...payload().sds01_export, tenant_scope: "query_param" };
    expect(() => renderSds01Export(tampered)).toThrow(TenantFromQuery);
  });

  it("refuses a row whose width does not match the columns", () => {
    const tampered: Sds01ExportPayload = {
      ...payload().sds01_export,
      rows: [["only", "three", "cells"]],
    };
    expect(() => renderSds01Export(tampered)).toThrow(SdsRowArityMismatch);
  });

  it("refuses a cell that would evaluate in a spreadsheet (invariant 47)", () => {
    const width = payload().sds01_export.columns.length;
    const hostile = Array.from({ length: width }, (_, i) => (i === 8 ? "=HYPERLINK(evil)" : "x"));
    const tampered: Sds01ExportPayload = { ...payload().sds01_export, rows: [hostile] };
    expect(() => renderSds01Export(tampered)).toThrow(UnsafeExportCell);
  });
});

describe("the whole module composes", () => {
  it("renders every surface from the recorded composite", () => {
    const view = renderExperienceModule(payload());
    expect(view.csat.metricId).toEqual("csat.score");
    expect(view.nps.metricId).toEqual("nps.monthly");
    expect(view.pulse.metricId).toEqual("clinician.pulse");
    expect(view.filters.dimensions.length).toEqual(3);
    expect(view.sds01Export.columns.length).toEqual(9);
  });
});

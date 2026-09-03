/**
 * INT-183 — Models & self-hosting registry module, console side.
 *
 * Acceptance, verbatim: *"registry rendered; benchmark trigger; red cell
 * blocks release visibly"*.
 *
 * **What this file runs against.** `e2e/fixtures/models.payload.json` is the
 * body `GET /admin/models` actually serves, recorded from the API. It is not
 * a hand-written mock: `tests/admin/test_models_module.py::
 * TestFixtureIsRecordedFromTheApi` fails the Python lane the moment the
 * served payload and this file diverge, and the payload is itself projected
 * out of `observability/registry.yaml` rather than restated (invariant 13).
 * So a drift between what the console renders and what the registry declares
 * cannot survive `make check`.
 *
 * **Why the assertions are on a presentation tree and not on a DOM.** The
 * repo has no browser test runner and adding one for a table would be a
 * second way to build a module (see the same reasoning in
 * `apps/mobile/e2e/*.spec.ts`, which assert the tree the renderer is built
 * from rather than a rendered screen). `renderModelsModule` returns exactly
 * what the page paints: the release tile, the enabled/disabled state of the
 * release control with its reason, one presentation row per registry
 * component, and the benchmark control per row. Asserting that structure
 * proves the block is *visible* — a reason string a reader can act on — and
 * proves the control is *dead*, which is the half a colour cannot carry.
 *
 * **The negative control.** Every "red blocks" assertion here is paired with
 * an amber payload that must NOT block. Without it the suite would equally
 * pass an implementation that blocks the release on any imperfection, which
 * would prove nothing about redness specifically.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { renderModelsModule, type ModelsPayload, type ModelsRow } from "../src/models/module";
import { UnlabelledMeasurement, renderMeasurement } from "../src/models/measurement";

const FIXTURES = join(__dirname, "fixtures");

function payload(): ModelsPayload {
  return JSON.parse(readFileSync(join(FIXTURES, "models.payload.json"), "utf8")) as ModelsPayload;
}

/** The same payload with every blocking row demoted to amber and the server's
 * release decision cleared — the near-miss the acceptance turns on. */
function amberPayload(): ModelsPayload {
  const live = payload();
  const rows: ModelsRow[] = live.rows.map((row) =>
    row.severity === "blocking"
      ? {
          ...row,
          severity: "attention",
          findings: [
            {
              code: "licence_not_verified_from_blob",
              detail: "licence has not been read from a raw LICENSE blob",
            },
          ],
        }
      : row,
  );
  return { ...live, rows, release: { blocked: false, reasons: [] } };
}

describe("registry rendered", () => {
  it("paints one row per registry component, in registry order", () => {
    const view = renderModelsModule(payload());
    expect(view.rows.map((r) => r.component)).toEqual(payload().rows.map((r) => r.component));
    expect(view.rows.length).toBeGreaterThan(0);
  });

  it("carries every column files/08 §148 names, as readable text", () => {
    const view = renderModelsModule(payload());
    const postgres = view.rows.find((r) => r.component === "postgres");
    expect(postgres).toBeDefined();
    const labels = postgres!.cells.map((c) => c.label);
    expect(labels).toEqual([
      "host",
      "licence",
      "self-hostable",
      "self-hosted now",
      "probe",
      "budget",
      "fallback",
      "PHI path",
    ]);
    for (const cell of postgres!.cells) {
      expect(cell.value.trim()).not.toEqual("");
    }
  });

  it("shows a pinned model as model_id@revision, never as a friendly name", () => {
    const view = renderModelsModule(payload());
    const vox = view.rows.find((r) => r.component === "voxcpm2-tts");
    expect(vox).toBeDefined();
    expect(vox!.pin).toMatch(/^[\w./-]+@[0-9a-f]{40}$/);
  });

  it("renders a licence that was never read from a blob as a finding, not as a licence", () => {
    const view = renderModelsModule(payload());
    const whisper = view.rows.find((r) => r.component === "whisper-tr-medical");
    expect(whisper).toBeDefined();
    expect(whisper!.findings.join(" ")).toContain("LICENSE blob");
  });
});

describe("red cell blocks release visibly", () => {
  it("disables the release control when any cell is red", () => {
    const view = renderModelsModule(payload());
    expect(view.rows.some((r) => r.severity === "blocking")).toBe(true);
    expect(view.releaseControl.enabled).toBe(false);
    expect(view.releaseControl.disabledReason).not.toBeNull();
  });

  it("states the reason on the tile, naming each blocking component", () => {
    const view = renderModelsModule(payload());
    const blocking = view.rows.filter((r) => r.severity === "blocking").map((r) => r.component);
    expect(view.releaseTile.blocked).toBe(true);
    for (const component of blocking) {
      expect(view.releaseTile.reasons.some((line) => line.includes(component))).toBe(true);
    }
    for (const line of view.releaseTile.reasons) {
      expect(line.length).toBeGreaterThan(component_min_reason_length);
    }
  });

  it("marks the blocking row itself so the reader can find it in the table", () => {
    const view = renderModelsModule(payload());
    const blocked = view.rows.filter((r) => r.severity === "blocking");
    for (const row of blocked) {
      expect(row.blocksRelease).toBe(true);
      expect(row.findings.length).toBeGreaterThan(0);
    }
  });

  it("refuses to render an allowed release while a red cell is present", () => {
    // A stale or tampered payload cannot buy a green console: the renderer
    // holds the server's decision against the cells it was given.
    const tampered = { ...payload(), release: { blocked: false, reasons: [] } };
    expect(() => renderModelsModule(tampered)).toThrow(/blocking/);
  });
});

describe("near-miss negative control — amber does not block", () => {
  it("leaves the release control live when the worst cell is amber", () => {
    const view = renderModelsModule(amberPayload());
    expect(view.rows.some((r) => r.severity === "attention")).toBe(true);
    expect(view.rows.some((r) => r.severity === "blocking")).toBe(false);
    expect(view.releaseControl.enabled).toBe(true);
    expect(view.releaseControl.disabledReason).toBeNull();
    expect(view.releaseTile.blocked).toBe(false);
  });

  it("still shows the amber findings — not blocking is not the same as not saying", () => {
    const view = renderModelsModule(amberPayload());
    const amber = view.rows.filter((r) => r.severity === "attention");
    expect(amber.length).toBeGreaterThan(0);
    for (const row of amber) {
      expect(row.findings.length).toBeGreaterThan(0);
      expect(row.blocksRelease).toBe(false);
    }
  });
});

describe("benchmark trigger", () => {
  it("offers a benchmark control on every row", () => {
    const view = renderModelsModule(payload());
    for (const row of view.rows) {
      expect(row.benchmark.route).toEqual(`POST /admin/models/${row.component}/benchmark`);
    }
  });

  it("offers the latency lane and refuses the quality lane, with the reason shown", () => {
    const view = renderModelsModule(payload());
    const row = view.rows.find((r) => r.component === "whisper-tr-medical")!;
    expect(row.benchmark.lanes.latency.enabled).toBe(true);
    expect(row.benchmark.lanes.quality.enabled).toBe(false);
    expect(row.benchmark.lanes.quality.disabledReason).toContain("corpus");
  });

  it("never renders a number without the corpus and date it was measured on", () => {
    expect(
      renderMeasurement({
        metric: "latency_ms",
        value: 12,
        unit: "ms",
        corpus: "synthetic probe http_health",
        measuredOn: "2026-09-03",
      }),
    ).toContain("synthetic probe http_health");
    expect(() =>
      renderMeasurement({
        metric: "latency_ms",
        value: 12,
        unit: "ms",
        corpus: "",
        measuredOn: "2026-09-03",
      }),
    ).toThrow(UnlabelledMeasurement);
  });
});

/** A reason short enough to be a label is not a reason. */
const component_min_reason_length = 12;

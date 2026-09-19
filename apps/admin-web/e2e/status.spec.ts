/**
 * INT-181 (seed) — live service-status surface, console side.
 *
 * The read path is a pure projection of the Prometheus text a service serves on
 * `/metrics` (via `intake_platform.health`), so — exactly as the models,
 * safety and experience specs — the assertions are on the presentation tree the
 * page paints, not on a DOM, and the fixture is a recorded exposition rather
 * than a hand-written mock. `status.metrics.txt` is the shape
 * `prometheus_client.generate_latest` writes for the api: the two live families
 * (`http_requests_total` + the `process_*` gauges), one route rendered as a
 * template (`/visits/{visit_id}/utterance`) so the label-block parser is
 * exercised against braces inside a value.
 *
 * The negative controls are the point: a scrape carrying a PHI-risk label, and
 * `http_requests_total` carrying a label outside its catalogued set, must both
 * be REFUSED — without them "renders the scrape" would be satisfied by an
 * implementation that paints whatever bytes arrive, which is the invariant-6
 * failure this surface exists to prevent. The fetch path is driven with an
 * injected fetch so the suite never dials a live endpoint (CLAUDE.md).
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { parsePrometheusText } from "../src/status/prometheus";
import {
  fetchServiceStatus,
  ForbiddenMetricLabel,
  PhiLabelPresent,
  renderServiceStatus,
  type FetchLike,
} from "../src/status/module";

const FIXTURES = join(__dirname, "fixtures");
const OBSERVED_AT = "2026-09-19T10:00:00.000Z";

function exposition(): string {
  return readFileSync(join(FIXTURES, "status.metrics.txt"), "utf8");
}

function view() {
  return renderServiceStatus(parsePrometheusText(exposition()), { observedAt: OBSERVED_AT });
}

describe("the Prometheus parser reads the exposition prometheus_client writes", () => {
  it("keeps a route template's own braces inside the label value", () => {
    const samples = parsePrometheusText(exposition());
    const utterance = samples.find(
      (s) => s.name === "http_requests_total" && s.labels.status === "500",
    );
    expect(utterance).toBeDefined();
    expect(utterance!.labels.route).toBe("/visits/{visit_id}/utterance");
    expect(utterance!.value).toBe(3);
  });

  it("reads a scientific-notation gauge and skips comment lines", () => {
    const samples = parsePrometheusText(exposition());
    const mem = samples.find((s) => s.name === "process_resident_memory_bytes");
    expect(mem!.value).toBe(188743680);
    expect(samples.every((s) => !s.name.startsWith("#"))).toBe(true);
  });
});

describe("service status renders from the live scrape", () => {
  it("marks the scrape reachable and live from a process-start reading", () => {
    const v = view();
    expect(v.scrape.reachable).toBe(true);
    expect(v.scrape.live).toBe(true);
    expect(v.observedAt).toBe(OBSERVED_AT);
  });

  it("rolls http_requests_total up per service with the served 5xx share", () => {
    const v = view();
    const api = v.services.find((s) => s.service === "api");
    expect(api).toBeDefined();
    // 1240 + 1180 + 88 + 342 + 3 = 2853 handled, 3 of them 5xx.
    expect(api!.requestsTotal).toBe("2853");
    expect(api!.serverErrors).toBe("3");
    expect(api!.errorRatio).toBe(
      (3 / 2853).toLocaleString("en-GB", { useGrouping: false, maximumFractionDigits: 6 }),
    );
  });

  it("paints the resident-memory and requests gauges as readings, with no verdict beside them", () => {
    const v = view();
    const mem = v.gauges.find((g) => g.label === "resident memory");
    expect(mem).toEqual({ label: "resident memory", value: "188743680", unit: "bytes" });
    expect(v.gauges.some((g) => g.label === "requests handled" && g.value === "2853")).toBe(true);
    // invariant 20: no target/SLA/pass-fail badge is carried on the surface.
    const serialised = JSON.stringify(v);
    for (const claim of ["target", "sla", "verdict", "pass", "fail"]) {
      expect(serialised.toLowerCase()).not.toContain(`"${claim}"`);
    }
  });
});

describe("negative controls — a tampered or mis-instrumented scrape is refused", () => {
  it("refuses the whole scrape when any series carries a PHI-risk label (invariant 6)", () => {
    const tampered =
      exposition() +
      '\nhttp_requests_total{service="api",method="GET",route="/x",status="200",patient="A123"} 1\n';
    expect(() =>
      renderServiceStatus(parsePrometheusText(tampered), { observedAt: OBSERVED_AT }),
    ).toThrow(PhiLabelPresent);
  });

  it("refuses http_requests_total carrying a label outside its catalogued set (invariant 13)", () => {
    const drifted =
      '# TYPE http_requests_total counter\nhttp_requests_total{service="api",method="GET",route="/x",status="200",tenant="t1"} 1\n';
    expect(() =>
      renderServiceStatus(parsePrometheusText(drifted), { observedAt: OBSERVED_AT }),
    ).toThrow(ForbiddenMetricLabel);
  });
});

describe("the fetch path fails closed and never dials a live endpoint in tests", () => {
  it("projects the injected scrape body without touching the network", async () => {
    const body = exposition();
    const fetchImpl: FetchLike = async (url) => {
      expect(url).toBe("http://localhost:8000/metrics");
      return { ok: true, text: async () => body };
    };
    const v = await fetchServiceStatus("http://localhost:8000", {
      fetchImpl,
      now: () => new Date(OBSERVED_AT),
    });
    expect(v.scrape.reachable).toBe(true);
    expect(v.services.some((s) => s.service === "api")).toBe(true);
  });

  it("shows the service down when /metrics does not answer", async () => {
    const fetchImpl: FetchLike = async () => {
      throw new Error("ECONNREFUSED");
    };
    const v = await fetchServiceStatus("http://localhost:8000", {
      fetchImpl,
      now: () => new Date(OBSERVED_AT),
    });
    expect(v.scrape.reachable).toBe(false);
    expect(v.scrape.live).toBe(false);
    expect(v.gauges).toEqual([]);
    expect(v.note).toContain("fail-closed");
  });
});

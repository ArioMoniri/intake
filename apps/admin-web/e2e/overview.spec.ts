/**
 * INT-181 — the rendered overview: SLO tiles and burn rates, the synthetic
 * probe matrix, and dependency health (files/08 §3 Overview, Reliability).
 *
 * **What this runs against.** Every response is a recording, in tests only,
 * made by `scripts/dev/record_reliability_fixture.py`:
 * - `reliability.payload.json` — the real composite
 *   (`intake_api.admin.reliability_console`) over the committed SLO files and
 *   registry, **a real probe sweep** (the runner's own `--once` output on the
 *   recording host) and the Prometheus answers in
 *   `tests/fixtures/reliability/prometheus_responses.json` (constructed in the
 *   documented HTTP API shape — no Prometheus runs there, as in INT-351);
 * - `reliability.stale.payload.json` — the same sources an hour later;
 * - `reliability.unconfigured.payload.json` — no Prometheus, no sweep;
 * - `overview.api.json` — **the live dev API's** `/readyz` and `/version`.
 *
 * The spec drives the page's own server-side loader through an injected
 * `fetch` and renders the page's own React tree to static markup.
 *
 * **The properties, each with a near-miss.** Admission is the API's gate; one
 * tile per declared SLO with the file's own windows; a burn condition or a
 * budget that disagrees with its figures is refused, not painted; every tile
 * fails closed to unknown on its own; a stale probe result is never shown as
 * current; ids only (invariant 6); no target beside a figure (invariant 20).
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { opsConfigFromEnv } from "../src/ops/access";
import type { FetchLike } from "../src/ops/load";
import {
  OpsLabelLeaked,
  OpsSchemaMismatch,
  OpsTargetRendered,
  OpsUnknownCarriesFigure,
  type Probe,
} from "../src/ops/module";
import { OverviewConsole } from "../src/overview/console";
import { loadOverview, type OverviewState } from "../src/overview/load";
import {
  OverviewBudgetInconsistent,
  OverviewBurnInconsistent,
  OverviewStaleRenderedFresh,
  renderOverview,
  type ReliabilityPayload,
} from "../src/overview/module";

const FIXTURES = join(__dirname, "fixtures");
const API = "https://api.intake.test";

function read<T>(name: string): T {
  return JSON.parse(readFileSync(join(FIXTURES, name), "utf8")) as T;
}

const payload = (): ReliabilityPayload => read<ReliabilityPayload>("reliability.payload.json");
const stale = (): ReliabilityPayload => read<ReliabilityPayload>("reliability.stale.payload.json");
const unconfigured = (): ReliabilityPayload =>
  read<ReliabilityPayload>("reliability.unconfigured.payload.json");
const liveApi = (): Record<string, { status: number; body: unknown }> =>
  read<Record<string, { status: number; body: unknown }>>("overview.api.json");

interface Recorded {
  status: number;
  body: unknown;
}

function recordedFetch(routes: Record<string, Recorded | "network_error">): {
  fetch: FetchLike;
  calls: { url: string; authorization: string | null }[];
} {
  const calls: { url: string; authorization: string | null }[] = [];
  const fetch: FetchLike = async (url, init) => {
    const headers = new Headers(init?.headers);
    calls.push({ url, authorization: headers.get("authorization") });
    const answer = routes[new URL(url).pathname];
    if (answer === undefined || answer === "network_error") throw new TypeError("fetch failed");
    return new Response(JSON.stringify(answer.body), {
      status: answer.status,
      headers: { "content-type": "application/json" },
    });
  };
  return { fetch, calls };
}

const readyzRoute = (): Record<string, Recorded> => ({ "/readyz": liveApi()["readyz"]! });
const liveReadyz = (): Probe => ({ ok: true, ...liveApi()["readyz"]! });

async function load(
  routes: Record<string, Recorded | "network_error">,
  authorization: string | null = "Bearer kc:sre_oncall",
): Promise<{ state: OverviewState; calls: { url: string; authorization: string | null }[] }> {
  const { fetch, calls } = recordedFetch(routes);
  const config = opsConfigFromEnv({ INTAKE_ADMIN_API_BASE: API });
  return { state: await loadOverview({ config, authorization, fetch }), calls };
}

function html(state: OverviewState, lang: "tr" | "en" = "en"): string {
  return renderToStaticMarkup(createElement(OverviewConsole, { state, lang }));
}

async function page(body: ReliabilityPayload, lang: "tr" | "en" = "en"): Promise<string> {
  const { state } = await load({ "/admin/reliability": { status: 200, body }, ...readyzRoute() });
  expect(state.kind).toEqual("console");
  return html(state, lang);
}

function tileState(markup: string, tile: string): string | undefined {
  const escaped = tile.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`data-tile="${escaped}"[^>]*data-tile-state="(ok|unknown)"`).exec(markup)?.[1];
}

type Slo = ReliabilityPayload["slos"]["tiles"][number];

function withSlo(key: string, patch: (tile: Slo) => Slo, base = payload()): ReliabilityPayload {
  const tiles = base.slos.tiles.map((t) => (`${t.service}.${t.slo}` === key ? patch(t) : t));
  return { ...base, slos: { ...base.slos, tiles } };
}

const DECLARED = [
  "api.availability",
  "api.latency",
  "langfuse.trace_emission",
  "learning.availability",
  "metrics.availability",
  "probes.availability",
  "siem.alert_scrub",
  "voice-runtime.availability",
];

// ------------------------------------------------------------------ admission

describe("admission (admin OIDC role behind the allow-list; HB-A16 fails closed)", () => {
  it("admits nobody without a bearer and never dials the API", async () => {
    const { state, calls } = await load(
      { "/admin/reliability": { status: 200, body: payload() } },
      null,
    );
    expect(state).toEqual({ kind: "not_admitted", reason: "no_credentials" });
    expect(calls).toEqual([]);
    expect(html(state)).not.toContain("data-tile");
  });

  it("reads readiness only after the admin gate answers 200, forwarding the bearer once", async () => {
    const { state, calls } = await load({
      "/admin/reliability": { status: 200, body: payload() },
      ...readyzRoute(),
    });
    expect(state.kind).toEqual("console");
    expect(calls.map((c) => new URL(c.url).pathname)).toEqual(["/admin/reliability", "/readyz"]);
    expect(calls[0]!.authorization).toEqual("Bearer kc:sre_oncall");
    expect(calls[1]!.authorization).toBeNull();
  });

  it.each([
    [401, { detail: { error: "unauthorized" } }, "token_refused"],
    [403, { detail: { error: "role_not_permitted" } }, "role_not_permitted"],
    [403, { detail: { error: "source_ip_refused" } }, "source_ip_refused"],
    [503, { detail: { error: "admin_console_unconfigured" } }, "console_unconfigured"],
  ])("a %i from the admin gate is a refusal, not a page (%j)", async (status, body, reason) => {
    const { state, calls } = await load({
      "/admin/reliability": { status, body },
      ...readyzRoute(),
    });
    expect(state).toEqual({ kind: "not_admitted", reason });
    // near-miss: a refused caller must not learn the API's readiness either
    expect(calls.map((c) => new URL(c.url).pathname)).toEqual(["/admin/reliability"]);
    expect(html(state)).not.toContain("data-tile");
  });

  it("an unconfigured API base admits nobody and dials nothing", async () => {
    const { fetch, calls } = recordedFetch({});
    const state = await loadOverview({
      config: opsConfigFromEnv({}),
      authorization: "Bearer kc:sre_oncall",
      fetch,
    });
    expect(state).toEqual({ kind: "unavailable", reason: "api_base_unconfigured" });
    expect(calls).toEqual([]);
  });

  it("a payload the view-model refuses is unavailable, never half-painted", async () => {
    const bent = { ...payload(), schema: "intake.admin.reliability.v0" } as never;
    const { state } = await load({
      "/admin/reliability": { status: 200, body: bent },
      ...readyzRoute(),
    });
    expect(state).toEqual({ kind: "unavailable", reason: "payload_refused" });
  });
});

// ------------------------------------------------------------------ SLO tiles

describe("SLO tiles — one per declared SLO, the file's own windows", () => {
  it("renders one tile per SLO the docs/slo files declare, in file order", async () => {
    const view = renderOverview(payload(), liveReadyz());
    expect(view.slos.tiles.map((t) => t.key)).toEqual(DECLARED);
    const markup = await page(payload());
    for (const key of DECLARED) expect(tileState(markup, `slo:${key}`)).toBeDefined();
    expect(tileState(markup, "slo:api.availability")).toEqual("ok");
    // a service with no series is unknown with its reason, never 100 %
    expect(tileState(markup, "slo:langfuse.trace_emission")).toEqual("unknown");
  });

  it("shows objective, SLI, budget remaining and every lane's burn on both windows", () => {
    const tile = renderOverview(payload(), liveReadyz()).slos.tiles[0]!;
    expect(tile).toMatchObject({
      key: "api.availability",
      state: "ok",
      objective: "99.9 %",
      window: "28d",
      sli: "99.960 %",
      budgetRemaining: "60.0 %",
      budgetOverspent: false,
    });
    expect(tile.lanes).toEqual([
      {
        lane: "fast",
        severity: "page",
        factor: "14.4 ×",
        longWindow: "1h",
        shortWindow: "5m",
        longBurn: "0.60 ×",
        shortBurn: "0.00 ×",
        conditionMet: false,
      },
      {
        lane: "slow",
        severity: "page",
        factor: "6 ×",
        longWindow: "6h",
        shortWindow: "30m",
        longBurn: "0.50 ×",
        shortBurn: "0.40 ×",
        conditionMet: false,
      },
      {
        lane: "ticket",
        severity: "ticket",
        factor: "1 ×",
        longWindow: "3d",
        shortWindow: "6h",
        longBurn: "0.30 ×",
        shortBurn: "0.50 ×",
        conditionMet: false,
      },
    ]);
  });

  it("marks a lane whose both windows are above its factor, and cites the windows", async () => {
    const markup = await page(payload());
    const voice = renderOverview(payload(), liveReadyz()).slos.tiles.find(
      (t) => t.key === "voice-runtime.availability",
    )!;
    expect(voice.lanes.map((l) => l.conditionMet)).toEqual([true, false, true]);
    expect(markup).toContain('data-condition="met"');
    for (const window of ["1h", "5m", "6h", "30m", "3d", "28d"]) expect(markup).toContain(window);
  });

  it("renders an overspent budget as negative, not clamped", () => {
    const bent = withSlo("api.availability", (t) => ({
      ...t,
      sli_percent: 99.75,
      error_budget_remaining: -1.5,
    }));
    const tile = renderOverview(bent, liveReadyz()).slos.tiles[0]!;
    expect(tile.budgetRemaining).toEqual("-150.0 %");
    expect(tile.budgetOverspent).toBe(true);
  });

  it("refuses a burn condition that disagrees with its own two windows", () => {
    const hidden = withSlo("voice-runtime.availability", (t) => ({
      ...t,
      burn_rates: t.burn_rates.map((l) => (l.lane === "fast" ? { ...l, condition_met: false } : l)),
    }));
    expect(() => renderOverview(hidden, liveReadyz())).toThrow(OverviewBurnInconsistent);
    // near-miss: a condition claimed while a window has no observation
    const guessed = withSlo("api.availability", (t) => ({
      ...t,
      burn_rates: t.burn_rates.map((l) =>
        l.lane === "fast" ? { ...l, short_burn: null, condition_met: false } : l,
      ),
    }));
    expect(() => renderOverview(guessed, liveReadyz())).toThrow(OverviewBurnInconsistent);
  });

  it("refuses a budget that disagrees with the SLI and objective beside it", () => {
    const bent = withSlo("api.availability", (t) => ({ ...t, error_budget_remaining: 0.95 }));
    expect(() => renderOverview(bent, liveReadyz())).toThrow(OverviewBudgetInconsistent);
  });

  it("refuses a service label that is not id-shaped (invariant 6)", () => {
    const bent = withSlo("api.availability", (t) => ({ ...t, service: "Hasta Adı" }));
    expect(() => renderOverview(bent, liveReadyz())).toThrow(OpsLabelLeaked);
  });
});

describe("each SLO tile fails closed (invariant 17)", () => {
  it.each(DECLARED)(
    "%s reads unknown with its reason when Prometheus is unconfigured",
    async (key) => {
      const markup = await page(unconfigured());
      expect(tileState(markup, `slo:${key}`)).toEqual("unknown");
      const tile = renderOverview(unconfigured(), liveReadyz()).slos.tiles.find(
        (t) => t.key === key,
      )!;
      expect(tile.reason).toEqual("prometheus_unconfigured");
      expect(tile.sli).toBeNull();
      expect(tile.lanes.every((l) => l.longBurn === null && l.conditionMet === null)).toBe(true);
    },
  );

  it("refuses an unknown SLO tile that still carries a figure", () => {
    const bent = withSlo("api.availability", (t) => ({ ...t, sli_percent: 99.9 }), unconfigured());
    expect(() => renderOverview(bent, liveReadyz())).toThrow(OpsUnknownCarriesFigure);
  });

  it("an unreadable SLO directory is one unknown section, not an empty page", async () => {
    const bent = {
      ...payload(),
      slos: { state: "unknown" as const, reason: "slo_files_unreadable", tiles: [] },
    };
    const markup = await page(bent);
    expect(tileState(markup, "slos")).toEqual("unknown");
    expect(markup).toContain('data-reason="slo_files_unreadable"');
  });
});

// --------------------------------------------------------------- probe matrix

describe("the synthetic probe matrix (the runner's real sweep)", () => {
  it("lists every registry probe with its last result and age", async () => {
    const view = renderOverview(payload(), liveReadyz());
    expect(view.probeMatrix.state).toEqual("ok");
    expect(view.probeMatrix.rows).toHaveLength(payload().probe_matrix.rows.length);
    const postgres = view.probeMatrix.rows.find((r) => r.component === "postgres")!;
    expect(postgres).toMatchObject({
      probe: "postgres_select1",
      status: "unhealthy",
      latency: "100 ms",
      budget: "500 ms",
      age: { value: "0", unit: "s" },
      stale: false,
    });
    const markup = await page(payload());
    expect(tileState(markup, "probe_matrix")).toEqual("ok");
    expect(markup).toContain("postgres_select1");
  });

  it("never shows the runner's free-text detail", async () => {
    const markup = await page(payload());
    expect(markup).not.toContain("Connection refused");
    expect(markup).not.toContain("127.0.0.1");
  });

  it("flags every result of an hour-old sweep as stale, with its age", async () => {
    const view = renderOverview(stale(), liveReadyz());
    expect(view.probeMatrix.rows.every((r) => r.stale)).toBe(true);
    expect(view.probeMatrix.rows[0]!.age).toEqual({ value: "1", unit: "h" });
    const markup = await page(stale());
    expect(markup).toContain('data-stale="true"');
  });

  it("refuses a row rendered fresh past three sweeps, or with no age", () => {
    const p = stale();
    const rows = p.probe_matrix.rows.map((r, i) => (i === 0 ? { ...r, stale: false } : r));
    const bent = { ...p, probe_matrix: { ...p.probe_matrix, rows } };
    expect(() => renderOverview(bent, liveReadyz())).toThrow(OverviewStaleRenderedFresh);
    const q = payload();
    const aged = q.probe_matrix.rows.map((r, i) => (i === 0 ? { ...r, age_s: null } : r));
    const noAge = { ...q, probe_matrix: { ...q.probe_matrix, rows: aged } };
    expect(() => renderOverview(noAge, liveReadyz())).toThrow(OverviewStaleRenderedFresh);
  });

  it("fails closed to unknown when no sweep is configured", async () => {
    const markup = await page(unconfigured());
    expect(tileState(markup, "probe_matrix")).toEqual("unknown");
    expect(markup).toContain('data-reason="probe_results_unconfigured"');
  });

  it("refuses an unknown matrix that still lists a row", () => {
    const p = unconfigured();
    const bent = {
      ...p,
      probe_matrix: { ...p.probe_matrix, rows: payload().probe_matrix.rows.slice(0, 1) },
    };
    expect(() => renderOverview(bent, liveReadyz())).toThrow(OpsUnknownCarriesFigure);
  });
});

// ----------------------------------------------------------- dependency health

describe("dependency health — every section from its own live source", () => {
  it("shows each self-hosted component with its fallback edge", () => {
    const rows = renderOverview(payload(), liveReadyz()).dependencies.components.rows;
    expect(rows.map((r) => r.component)).toEqual(
      payload().dependencies.components.rows.map((r) => r.component),
    );
    for (const store of ["postgres", "redis", "openbao", "minio"]) {
      expect(rows.some((r) => r.component === store)).toBe(true);
    }
    expect(rows.find((r) => r.component === "postgres")).toMatchObject({
      health: "unhealthy",
      fallbackKind: "component",
      fallback: "backups",
      fallbackHealth: "unhealthy",
    });
  });

  it("reads a stale sweep as unknown health, never the last value", () => {
    const rows = renderOverview(stale(), liveReadyz()).dependencies.components.rows;
    expect(rows.every((r) => r.health === "unknown" && r.healthReason === "sweep_stale")).toBe(
      true,
    );
    expect(rows.every((r) => r.checkedAt === null)).toBe(true);
  });

  it("shows Prometheus, the GPU hosts and INT-100's vendor breakers", async () => {
    const deps = renderOverview(payload(), liveReadyz()).dependencies;
    expect(deps.prometheus).toMatchObject({ state: "ok", health: "healthy" });
    expect(deps.gpuHosts.rows).toEqual([{ hostId: "gpu-a", health: "healthy" }]);
    expect(deps.vendors.rows).toEqual([
      { component: "freya-tts", breaker: "closed", health: "healthy" },
      { component: "voxcpm2-tts", breaker: "half_open", health: "degraded" },
    ]);
    const markup = await page(payload());
    for (const tile of ["dep_components", "dep_prometheus", "dep_gpu_hosts", "dep_vendors"]) {
      expect(tileState(markup, tile)).toEqual("ok");
    }
  });

  it("shows the live API's own readiness checks (recorded from the dev stack)", async () => {
    const readiness = renderOverview(payload(), liveReadyz()).dependencies.apiReadiness;
    expect(readiness).toEqual({
      state: "ok",
      reason: null,
      checks: [
        { check: "db", health: "healthy" },
        { check: "audit_store", health: "healthy" },
      ],
    });
    expect(tileState(await page(payload()), "dep_api_readiness")).toEqual("ok");
  });

  it("marks a failing readiness check by its name only", () => {
    const failing: Probe = {
      ok: true,
      status: 503,
      body: { checks: { db: "error", audit_store: "ok" } },
    };
    const checks = renderOverview(payload(), failing).dependencies.apiReadiness.checks;
    expect(checks).toEqual([
      { check: "db", health: "unhealthy" },
      { check: "audit_store", health: "healthy" },
    ]);
  });

  it.each([
    ["unreachable", { ok: false, reason: "unreachable" } as Probe, "api_unreachable"],
    [
      "not id-shaped",
      { ok: true, status: 200, body: { checks: { "Ayşe Y.": "ok" } } } as Probe,
      "readiness_malformed",
    ],
    [
      "200 over a failing check",
      { ok: true, status: 200, body: { checks: { db: "error" } } } as Probe,
      "readiness_malformed",
    ],
    [
      "no checks",
      { ok: true, status: 200, body: { status: "alive" } } as Probe,
      "readiness_malformed",
    ],
  ])("API readiness fails closed when %s", (_, probe, reason) => {
    const readiness = renderOverview(payload(), probe).dependencies.apiReadiness;
    expect(readiness).toEqual({ state: "unknown", reason, checks: [] });
  });

  it("the API-readiness tile renders unknown when /readyz is unreachable", async () => {
    const { state } = await load({
      "/admin/reliability": { status: 200, body: payload() },
      "/readyz": "network_error",
    });
    const markup = html(state);
    expect(tileState(markup, "dep_api_readiness")).toEqual("unknown");
    expect(tileState(markup, "dep_components")).toEqual("ok");
  });

  it.each([
    ["dep_components", "probe_results_unconfigured"],
    ["dep_prometheus", "prometheus_unconfigured"],
    ["dep_gpu_hosts", "prometheus_unconfigured"],
    ["dep_vendors", "prometheus_unconfigured"],
  ])("%s fails closed to unknown when its source is absent", async (tile, reason) => {
    const markup = await page(unconfigured());
    expect(tileState(markup, tile)).toEqual("unknown");
    expect(markup).toMatch(new RegExp(`data-tile="${tile}"[\\s\\S]*?data-reason="${reason}"`));
  });

  it("refuses an unknown component row that still carries an instant", () => {
    const p = stale();
    const rows = p.dependencies.components.rows.map((r, i) =>
      i === 0 ? { ...r, checked_at: "2026-09-26T22:19:41Z" } : r,
    );
    const bent = {
      ...p,
      dependencies: { ...p.dependencies, components: { ...p.dependencies.components, rows } },
    };
    expect(() => renderOverview(bent, liveReadyz())).toThrow(OpsUnknownCarriesFigure);
  });

  it("refuses a vendor label that is not id-shaped (invariant 6)", () => {
    const p = payload();
    const rows = [{ component: "Ayşe Yılmaz", breaker: "open", health: "unhealthy" }];
    const bent = {
      ...p,
      dependencies: { ...p.dependencies, vendors: { ...p.dependencies.vendors, rows } },
    };
    expect(() => renderOverview(bent, liveReadyz())).toThrow(OpsLabelLeaked);
  });

  it("refuses a breaker state outside INT-100's vocabulary", () => {
    const p = payload();
    const rows = [{ component: "freya-tts", breaker: "melting", health: "healthy" }];
    const bent = {
      ...p,
      dependencies: { ...p.dependencies, vendors: { ...p.dependencies.vendors, rows } },
    };
    expect(() => renderOverview(bent, liveReadyz())).toThrow(OpsLabelLeaked);
  });
});

// ------------------------------------------------------ schema, claims, language

describe("no targets, one schema, tr first", () => {
  it("refuses a target rendered beside a figure (invariant 20)", () => {
    const bent = withSlo("api.availability", (t) => ({ ...t, target: "99.9" }) as never);
    expect(() => renderOverview(bent, liveReadyz())).toThrow(OpsTargetRendered);
  });

  it("refuses a payload of another schema", () => {
    expect(() => renderOverview({ ...payload(), schema: "other" } as never, liveReadyz())).toThrow(
      OpsSchemaMismatch,
    );
  });

  it("renders Turkish by default, with the link to the ops console", async () => {
    const markup = await page(payload(), "tr");
    expect(markup).toContain('lang="tr"');
    expect(markup).toContain("Genel bakış");
    expect(markup).toContain('href="/ops"');
  });
});

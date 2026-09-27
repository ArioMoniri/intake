/**
 * INT-351 — the rendered ops console (files/08 §3 Ops; audit F26: the console
 * was headless view-models only).
 *
 * **What this runs against.** Every response below is recorded, in tests only:
 * `e2e/fixtures/ops.payload.json` and `ops.unconfigured.payload.json` are the
 * `GET /admin/ops` bodies the real composite (`intake_api.admin.ops_console`)
 * produced — once over the recorded Prometheus answers in
 * `tests/fixtures/ops/prometheus_responses.json`, once with no Prometheus at
 * all — and `ops.health.json` is `/healthz`, `/readyz` and `/version` as the
 * shared `intake_platform.health.mount_health` contract serves them. All three
 * come from `scripts/dev/record_ops_fixture.py`. The spec drives the same
 * server-side loader the page calls, through an injected `fetch`, and renders
 * the same React tree the App Router route renders — to static markup, the
 * repo's headless node lane (no browser is needed to prove what the server
 * sends).
 *
 * **The properties, each with a near-miss.**
 * - Nobody is admitted without the console's own gate: no bearer, a refused
 *   token, a role outside the platform scope, an empty IP allow-list
 *   (HB-A16) or an unconfigured OIDC verifier each render a refusal and not
 *   one tile — and the loader never even dials the API without a bearer.
 * - Unknown is rendered as unknown (invariant 17): a source that is absent,
 *   failing or silent yields the word and a reason, never a zero.
 * - No PHI (invariant 6): a label that is not id-shaped refuses the payload.
 * - The k ≥ 10 floor (files/06 §8) and no target beside a figure
 *   (invariant 20) hold on the page too.
 * - The CSP is nonce-based with no `unsafe-*` in production (files/08 §0c
 *   F14; invariant 48 on the admin-console row).
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { buildCsp } from "../src/ops/csp";
import { OpsConsole } from "../src/ops/console";
import { bearerFrom, opsConfigFromEnv } from "../src/ops/access";
import { loadOpsConsole, type FetchLike, type OpsConsoleState } from "../src/ops/load";
import {
  OpsLabelLeaked,
  OpsSchemaMismatch,
  OpsSuppressedCohortLeaked,
  OpsTargetRendered,
  OpsUnknownCarriesFigure,
  renderOps,
  type HealthResponses,
  type OpsPayload,
} from "../src/ops/module";

const FIXTURES = join(__dirname, "fixtures");
const API = "https://api.intake.test";

function read<T>(name: string): T {
  return JSON.parse(readFileSync(join(FIXTURES, name), "utf8")) as T;
}

const payload = (): OpsPayload => read<OpsPayload>("ops.payload.json");
const unconfigured = (): OpsPayload => read<OpsPayload>("ops.unconfigured.payload.json");
const health = (): Record<string, { status: number; body: unknown }> =>
  read<Record<string, { status: number; body: unknown }>>("ops.health.json");

interface Recorded {
  status: number;
  body: unknown;
}

/** A fetch that answers from recorded responses and records what it was asked. */
function recordedFetch(routes: Record<string, Recorded | "network_error">): {
  fetch: FetchLike;
  calls: { url: string; authorization: string | null }[];
} {
  const calls: { url: string; authorization: string | null }[] = [];
  const fetch: FetchLike = async (url, init) => {
    const headers = new Headers(init?.headers);
    calls.push({ url, authorization: headers.get("authorization") });
    const path = new URL(url).pathname;
    const answer = routes[path];
    if (answer === undefined || answer === "network_error") {
      throw new TypeError("fetch failed");
    }
    return new Response(JSON.stringify(answer.body), {
      status: answer.status,
      headers: { "content-type": "application/json" },
    });
  };
  return { fetch, calls };
}

function healthRoutes(): Record<string, Recorded> {
  const h = health();
  return {
    "/healthz": h["healthz"]!,
    "/readyz": h["readyz"]!,
    "/version": h["version"]!,
  };
}

async function load(
  routes: Record<string, Recorded | "network_error">,
  authorization: string | null = "Bearer kc:sre_oncall",
): Promise<{ state: OpsConsoleState; calls: { url: string; authorization: string | null }[] }> {
  const { fetch, calls } = recordedFetch(routes);
  const config = opsConfigFromEnv({ INTAKE_ADMIN_API_BASE: API });
  const state = await loadOpsConsole({ config, authorization, fetch });
  return { state, calls };
}

function html(state: OpsConsoleState, lang: "tr" | "en" = "en"): string {
  return renderToStaticMarkup(createElement(OpsConsole, { state, lang }));
}

function withTile<K extends keyof OpsPayload["tiles"]>(
  key: K,
  tile: Partial<OpsPayload["tiles"][K]>,
): OpsPayload {
  const p = payload();
  return { ...p, tiles: { ...p.tiles, [key]: { ...p.tiles[key], ...tile } } };
}

const responses = (): HealthResponses => ({
  healthz: { ok: true, status: 200, body: health()["healthz"]!.body },
  readyz: { ok: true, status: 200, body: health()["readyz"]!.body },
  version: { ok: true, status: 200, body: health()["version"]!.body },
});

// ------------------------------------------------------------------ admission

describe("admission (admin OIDC role; HB-A16 fails closed)", () => {
  it("admits nobody without a bearer and never dials the API", async () => {
    const { state, calls } = await load({ "/admin/ops": { status: 200, body: payload() } }, null);
    expect(state).toEqual({ kind: "not_admitted", reason: "no_credentials" });
    expect(calls).toEqual([]);
    expect(html(state)).not.toContain("data-tile");
  });

  it("renders the console only when the API's admin gate answers 200", async () => {
    const { state, calls } = await load({
      "/admin/ops": { status: 200, body: payload() },
      ...healthRoutes(),
    });
    expect(state.kind).toEqual("console");
    // the bearer is forwarded to the one authorising call, verbatim
    const ops = calls.find((c) => c.url.endsWith("/admin/ops"))!;
    expect(ops.authorization).toEqual("Bearer kc:sre_oncall");
    // health is read only after admission
    expect(calls[0]!.url).toEqual(`${API}/admin/ops`);
  });

  it.each([
    [401, { detail: { error: "unauthorized" } }, "token_refused"],
    [403, { detail: { error: "role_not_permitted" } }, "role_not_permitted"],
    [403, { detail: { error: "source_ip_refused" } }, "source_ip_refused"],
    [503, { detail: { error: "admin_console_unconfigured" } }, "console_unconfigured"],
  ])("a %i from the admin gate is a refusal, not a page (%j)", async (status, body, reason) => {
    const { state, calls } = await load({ "/admin/ops": { status, body }, ...healthRoutes() });
    expect(state).toEqual({ kind: "not_admitted", reason });
    // near-miss: a refused caller must not learn the API's health either
    expect(calls.map((c) => new URL(c.url).pathname)).toEqual(["/admin/ops"]);
    const page = html(state);
    expect(page).not.toContain("data-tile");
    expect(page).toContain(`data-refusal="${reason}"`);
  });

  it("an unconfigured API base admits nobody (no default origin is guessed)", async () => {
    const { fetch, calls } = recordedFetch({});
    const state = await loadOpsConsole({
      config: opsConfigFromEnv({}),
      authorization: "Bearer kc:sre_oncall",
      fetch,
    });
    expect(state).toEqual({ kind: "unavailable", reason: "api_base_unconfigured" });
    expect(calls).toEqual([]);
  });

  it("an unreachable API is unavailable, not an empty console", async () => {
    const { state } = await load({ "/admin/ops": "network_error" });
    expect(state).toEqual({ kind: "unavailable", reason: "api_unreachable" });
  });

  it("a payload the view-model refuses is unavailable, never half-painted", async () => {
    const bent = { ...payload(), schema: "intake.admin.ops.v0" };
    const { state } = await load({ "/admin/ops": { status: 200, body: bent }, ...healthRoutes() });
    expect(state).toEqual({ kind: "unavailable", reason: "payload_refused" });
  });

  it.each([
    [{ INTAKE_ADMIN_API_BASE: "api.intake.test" }],
    [{ INTAKE_ADMIN_API_BASE: "ftp://api.intake.test" }],
    [{ INTAKE_ADMIN_API_BASE: "https://user:pw@api.intake.test" }],
    [{ INTAKE_ADMIN_API_BASE: "https://api.intake.test/?tenant=b" }],
  ])("refuses an API base that is not a plain http(s) origin: %j", (env) => {
    expect(opsConfigFromEnv(env)).toBeNull();
  });

  it("reads only a well-formed bearer", () => {
    expect(bearerFrom(new Headers({ authorization: "Bearer abc.def.ghi" }))).toEqual(
      "Bearer abc.def.ghi",
    );
    expect(bearerFrom(new Headers({ authorization: "Basic dXNlcjpwdw==" }))).toBeNull();
    expect(bearerFrom(new Headers({ authorization: "Bearer " }))).toBeNull();
    expect(bearerFrom(new Headers({ authorization: "Bearer a b" }))).toBeNull();
    expect(bearerFrom(new Headers())).toBeNull();
  });
});

// --------------------------------------------------------------------- tiles

describe("the rendered tiles (recorded composite)", () => {
  it("paints every tile from its source", async () => {
    const { state } = await load({
      "/admin/ops": { status: 200, body: payload() },
      ...healthRoutes(),
    });
    const page = html(state);
    for (const tile of [
      "api_health",
      "models",
      "gpu",
      "model_usage",
      "clip_cache",
      "wait_time",
      "satisfaction",
      "cicd",
    ]) {
      expect(page).toContain(`data-tile="${tile}"`);
      expect(page).toContain(`data-tile-state="ok"`);
    }
    expect(page).toContain("whisper-tr-medical");
    expect(page).toContain("gpu-a");
    expect(page).toContain("extract_slots");
    expect(page).toContain("6dd1f2a");
    expect(page).toContain("base.intake");
  });

  it("shows the clip manifest coverage per pack, locale and voice", () => {
    const view = renderOps(payload(), responses());
    expect(view.tiles.clipCache.manifests).toEqual([
      {
        pack: "base.intake",
        locale: "tr",
        voice: "george",
        rows: "44",
        present: "41",
        coverage: "93\u00a0%",
      },
    ]);
    expect(view.tiles.clipCache.hitRatio).toEqual("93\u00a0%");
  });

  it("refuses a manifest pack label that is not id-shaped (invariant 6)", () => {
    const p = payload();
    const manifests = p.tiles.clip_cache.manifests.map((m) => ({ ...m, pack: "Hasta Adı" }));
    expect(() => renderOps(withTile("clip_cache", { manifests }), responses())).toThrow(
      OpsLabelLeaked,
    );
  });

  it("renders an unreadable registry as an unknown models tile", async () => {
    const bent = withTile("models", {
      state: "unknown",
      reason: "registry_unreadable",
      release_blocked: null,
      rows: [],
    });
    const { state } = await load({ "/admin/ops": { status: 200, body: bent }, ...healthRoutes() });
    const page = html(state);
    expect(page).toMatch(/data-tile="models"[^>]*data-tile-state="unknown"/);
    expect(page).toContain('data-reason="registry_unreadable"');
  });

  it("renders a refused probe-results file as an unknown models tile (INT-377)", async () => {
    const bent = withTile("models", {
      state: "unknown",
      reason: "probe_results_unreadable",
      release_blocked: null,
      rows: [],
    });
    const { state } = await load({ "/admin/ops": { status: 200, body: bent }, ...healthRoutes() });
    const page = html(state);
    expect(page).toMatch(/data-tile="models"[^>]*data-tile-state="unknown"/);
    expect(page).toContain('data-reason="probe_results_unreadable"');
    // the copy, not the raw code twice (the fallback when a reason has no copy)
    expect(page).toContain("Probe results file unreadable");
  });

  it("shows the API's health, readiness and build from the configured base", () => {
    const view = renderOps(payload(), responses());
    expect(view.health.alive).toEqual("alive");
    expect(view.health.ready).toEqual("ready");
    expect(view.health.gitSha).toEqual(
      health()["version"]!.body && (health()["version"]!.body as { git_sha: string }).git_sha,
    );
    expect(view.health.builtAt.length).toBeGreaterThan(0);
  });

  it("marks a failing readiness check by its name only", () => {
    const view = renderOps(payload(), {
      ...responses(),
      readyz: { ok: true, status: 503, body: { checks: { registry: "failed", db: "ok" } } },
    });
    expect(view.health.ready).toEqual("not_ready");
    expect(view.health.failingChecks).toEqual(["registry"]);
  });

  it("renders an unreachable health endpoint as unknown", () => {
    const view = renderOps(payload(), {
      healthz: { ok: false, reason: "unreachable" },
      readyz: { ok: false, reason: "unreachable" },
      version: { ok: false, reason: "unreachable" },
    });
    expect(view.health.alive).toEqual("unknown");
    expect(view.health.ready).toEqual("unknown");
    expect(view.health.gitSha).toEqual("unknown");
  });

  it("refuses a version body whose sha is not a sha", () => {
    const view = renderOps(payload(), {
      ...responses(),
      version: { ok: true, status: 200, body: { git_sha: "<script>", built_at: "x" } },
    });
    expect(view.health.gitSha).toEqual("unknown");
  });

  it("formats counts and bytes as atoms a reader cannot misread (inv 22)", () => {
    const view = renderOps(payload(), responses());
    const gpu = view.tiles.gpu.hosts[0]!.gpus[0]!;
    expect(gpu.memoryUsed).toEqual("50.0 GiB");
    expect(gpu.memoryTotal).toEqual("140.4 GiB");
    expect(gpu.utilization).toEqual("37 %");
    const lane = view.tiles.modelUsage.lanes.find((l) => l.lane === "extract_slots")!;
    expect(lane.requests).toEqual("412");
    expect(lane.p95).toEqual("2311 ms");
  });
});

describe("unknown is a state, not a zero (invariant 17)", () => {
  it("renders every Prometheus-fed tile unknown with its reason when unconfigured", async () => {
    const { state } = await load({
      "/admin/ops": { status: 200, body: unconfigured() },
      ...healthRoutes(),
    });
    const page = html(state);
    for (const tile of ["gpu", "model_usage", "clip_cache", "wait_time", "satisfaction", "cicd"]) {
      expect(page).toMatch(new RegExp(`data-tile="${tile}"[^>]*data-tile-state="unknown"`));
    }
    expect(page).toContain("prometheus_unconfigured");
    // the registry still answers: models is known without Prometheus
    expect(page).toMatch(/data-tile="models"[^>]*data-tile-state="ok"/);
  });

  it("refuses an unknown tile that carries a figure", () => {
    const bent = { ...unconfigured() };
    bent.tiles = { ...bent.tiles, clip_cache: { ...bent.tiles.clip_cache, hit: 12 } };
    expect(() => renderOps(bent, responses())).toThrow(OpsUnknownCarriesFigure);
  });

  it("refuses an unknown GPU tile that still lists a host", () => {
    const bent = { ...unconfigured() };
    bent.tiles = {
      ...bent.tiles,
      gpu: { ...bent.tiles.gpu, hosts: [{ host_id: "gpu-a", up: true, gpus: [] }] },
    };
    expect(() => renderOps(bent, responses())).toThrow(OpsUnknownCarriesFigure);
  });
});

describe("no PHI, the k floor, no targets", () => {
  it("refuses a lane label that is not id-shaped (invariant 6)", () => {
    const bent = withTile("model_usage", {
      lanes: [{ kind: "work", lane: "Ayşe Yılmaz", requests: 4, p95_ms: null, failures: 0 }],
    });
    expect(() => renderOps(bent, responses())).toThrow(OpsLabelLeaked);
  });

  it("refuses a workflow name that is not id-shaped (invariant 6)", () => {
    const p = payload();
    const workflows = p.tiles.cicd.workflows.map((w) => ({ ...w, workflow: "fix: Hasta Adı" }));
    expect(() => renderOps(withTile("cicd", { workflows }), responses())).toThrow(OpsLabelLeaked);
  });

  it("refuses a CSAT mean shown for a suppressed cohort (files/06 §8)", () => {
    const bent = withTile("satisfaction", { csat_n: 4, csat_suppressed: true, csat_mean: 4.5 });
    expect(() => renderOps(bent, responses())).toThrow(OpsSuppressedCohortLeaked);
  });

  it("refuses a wait mean for a cohort below the floor even if not flagged", () => {
    const bent = withTile("wait_time", { n: 3, suppressed: false, mean_min: 12 });
    expect(() => renderOps(bent, responses())).toThrow(OpsSuppressedCohortLeaked);
  });

  it("renders a suppressed cohort as its count only", () => {
    const view = renderOps(
      withTile("satisfaction", { csat_n: 4, csat_suppressed: true, csat_mean: null }),
      responses(),
    );
    expect(view.tiles.satisfaction.csatN).toEqual("4");
    expect(view.tiles.satisfaction.csatMean).toBeNull();
    expect(view.tiles.satisfaction.csatSuppressed).toBe(true);
  });

  it("refuses a target rendered beside a figure (invariant 20)", () => {
    const bent = withTile("satisfaction", {
      ...(payload().tiles.satisfaction as object),
      target: ">= 4.3",
    } as never);
    expect(() => renderOps(bent, responses())).toThrow(OpsTargetRendered);
  });

  it("refuses a payload of another schema", () => {
    expect(() => renderOps({ ...payload(), schema: "other" as never }, responses())).toThrow(
      OpsSchemaMismatch,
    );
  });
});

describe("language (tr is the source of truth; invariant 5)", () => {
  it("renders Turkish by default with the lang attribute set", async () => {
    const { state } = await load({
      "/admin/ops": { status: 200, body: payload() },
      ...healthRoutes(),
    });
    const page = html(state, "tr");
    expect(page).toContain('lang="tr"');
    expect(page).toContain("Bilinmiyor");
  });
});

describe("CSP (files/08 §0c F14)", () => {
  it("is nonce-based with no unsafe-* in production", () => {
    const csp = buildCsp("bm9uY2U=", "production");
    expect(csp).toContain("script-src 'self' 'nonce-bm9uY2U=' 'strict-dynamic'");
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("object-src 'none'");
    expect(csp).not.toMatch(/unsafe-/);
    // no third-party frame source — the iframe pattern is deleted (F1)
    expect(csp).toContain("frame-src 'none'");
  });

  it("allows eval only in development, where React needs it", () => {
    expect(buildCsp("bm9uY2U=", "development")).toContain("'unsafe-eval'");
  });

  it("refuses a nonce that is not base64", () => {
    expect(() => buildCsp("'; script-src *", "production")).toThrow();
  });
});

/**
 * INT-187 — the CI/CD & releases module: workflow runs, required gates,
 * releases, deploy state, Argo CD and the canary, the error budget, the deploy
 * freeze and the gate they decide (files/08 §3 "CI/CD & releases", §8.2).
 *
 * **What this runs against.** `cicd.payload.json` and
 * `cicd.unconfigured.payload.json` are recordings, in tests only, made by
 * `scripts/dev/record_cicd_fixture.py` with the shipped composite
 * (`intake_api.admin.cicd_console`) over the ops collector's own output for
 * recorded GitHub API answers — `tests/admin/test_cicd_console.py` fails if
 * they drift. The spec drives the page's own server-side loader through an
 * injected `fetch`, renders the page's own React tree to static markup, and
 * drives the form handler's own planner.
 *
 * **The properties, each with a near-miss.** Admission is the API's gate;
 * every tile fails closed to unknown on its own; Argo CD and a canary read
 * "not deployed" and nothing may paint them deployed; "deploys allowed" is
 * never painted beside a freeze, an exhausted budget or an unreadable freeze;
 * freezing is one key and lifting is a request for a second; there is no
 * approve form and no rollback form; ids only (invariant 6); no target beside
 * a figure (invariant 20); numbers ungrouped (invariant 22).
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { planCicdAction, submitCicdAction, type ResultCode } from "../src/cicd/actions";
import { CicdConsole } from "../src/cicd/console";
import { loadCicd, resultFrom, type CicdState } from "../src/cicd/load";
import {
  CicdFreezeIncoherent,
  CicdGateIncoherent,
  CicdNotWired,
  renderCicd,
  type CicdPayload,
} from "../src/cicd/module";
import { opsConfigFromEnv } from "../src/ops/access";
import {
  NBSP,
  OpsLabelLeaked,
  OpsSchemaMismatch,
  OpsTargetRendered,
  OpsUnknownCarriesFigure,
} from "../src/ops/guards";
import type { FetchLike } from "../src/ops/load";

const FIXTURES = join(__dirname, "fixtures");
const API = "https://api.intake.test";

function read<T>(name: string): T {
  return JSON.parse(readFileSync(join(FIXTURES, name), "utf8")) as T;
}

const payload = (): CicdPayload => read<CicdPayload>("cicd.payload.json");
const unconfigured = (): CicdPayload => read<CicdPayload>("cicd.unconfigured.payload.json");

interface Recorded {
  status: number;
  body: unknown;
}

interface Call {
  url: string;
  method: string;
  authorization: string | null;
  body: unknown;
}

function recordedFetch(routes: Record<string, Recorded | "network_error">): {
  fetch: FetchLike;
  calls: Call[];
} {
  const calls: Call[] = [];
  const fetch: FetchLike = async (url, init) => {
    const headers = new Headers(init?.headers);
    calls.push({
      url,
      method: init?.method ?? "GET",
      authorization: headers.get("authorization"),
      body: typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : null,
    });
    const answer = routes[new URL(url).pathname];
    if (answer === undefined || answer === "network_error") throw new TypeError("fetch failed");
    return new Response(JSON.stringify(answer.body), {
      status: answer.status,
      headers: { "content-type": "application/json" },
    });
  };
  return { fetch, calls };
}

async function load(
  body: unknown,
  authorization: string | null = "Bearer kc:sre_oncall",
  status = 200,
): Promise<{ state: CicdState; calls: Call[] }> {
  const { fetch, calls } = recordedFetch({ "/admin/cicd": { status, body } });
  const config = opsConfigFromEnv({ INTAKE_ADMIN_API_BASE: API });
  return { state: await loadCicd({ config, authorization, fetch }), calls };
}

function html(
  state: CicdState,
  lang: "tr" | "en" = "en",
  result: ResultCode | null = null,
): string {
  return renderToStaticMarkup(createElement(CicdConsole, { state, lang, result }));
}

async function page(body: CicdPayload, lang: "tr" | "en" = "en"): Promise<string> {
  const { state } = await load(body);
  expect(state.kind).toEqual("console");
  return html(state, lang);
}

function tileState(markup: string, tile: string): string | undefined {
  return new RegExp(`data-tile="${tile}"[^>]*data-tile-state="(ok|unknown)"`).exec(markup)?.[1];
}

type Tiles = CicdPayload["tiles"];

function withTile<K extends keyof Tiles>(
  key: K,
  patch: (tile: Tiles[K]) => Tiles[K],
  base = payload(),
): CicdPayload {
  return { ...base, tiles: { ...base.tiles, [key]: patch(base.tiles[key]) } };
}

const PROM_TILES = ["pipelines", "gates", "releases"] as const;

// ------------------------------------------------------------------ admission

describe("admission (the API's admin gate decides; HB-A16 fails closed)", () => {
  it("admits nobody without a bearer and never dials the API", async () => {
    const { state, calls } = await load(payload(), null);
    expect(state).toEqual({ kind: "not_admitted", reason: "no_credentials" });
    expect(calls).toEqual([]);
    expect(html(state)).not.toContain("data-tile");
  });

  it("forwards the bearer once to GET /admin/cicd", async () => {
    const { state, calls } = await load(payload());
    expect(state.kind).toEqual("console");
    expect(calls.map((c) => [c.method, new URL(c.url).pathname, c.authorization])).toEqual([
      ["GET", "/admin/cicd", "Bearer kc:sre_oncall"],
    ]);
  });

  it("a 403 from the gate is a refusal, not a page", async () => {
    const { state } = await load({ detail: { error: "role_not_permitted" } }, undefined, 403);
    expect(state).toEqual({ kind: "not_admitted", reason: "role_not_permitted" });
    expect(html(state)).not.toContain("<form");
  });

  it("a payload the view-model refuses is unavailable, never half-painted", async () => {
    const { state } = await load({ ...payload(), schema: "intake.admin.cicd.v0" });
    expect(state).toEqual({ kind: "unavailable", reason: "payload_refused" });
  });
});

// ------------------------------------------------------------------ the tiles

describe("the tiles — recorded from the collector's own output for real GitHub answers", () => {
  it("renders every tile, each with its state", async () => {
    const markup = await page(payload());
    for (const tile of [
      ...PROM_TILES,
      "deployments",
      "argo_cd",
      "canary",
      "freeze",
      "error_budget",
      "deploy_gate",
      "pending",
    ]) {
      expect(tileState(markup, tile), tile).toBeDefined();
    }
    for (const tile of PROM_TILES) expect(tileState(markup, tile), tile).toEqual("ok");
  });

  it("lists recent runs per workflow, newest first, with failing jobs by name", () => {
    const view = renderCicd(payload());
    expect(view.pipelines.branch).toEqual("main");
    const workflows = view.pipelines.workflows.map((w) => w.workflow);
    expect(workflows).toEqual([...workflows].sort());
    for (const w of view.pipelines.workflows) {
      const numbers = w.runs.map((r) => Number(r.runNumber));
      expect(numbers).toEqual([...numbers].sort((a, b) => b - a));
    }
    const failed = view.pipelines.workflows
      .flatMap((w) => w.runs)
      .find((r) => r.conclusion === "failure" && r.failedJobs.length > 0);
    expect(failed, "the recording holds a failed run with its failing jobs").toBeDefined();
    expect(failed!.duration).toMatch(new RegExp(`^[0-9]+${NBSP}s$`));
  });

  it("shows every required gate per ref, and that GitHub enforces none on main today", async () => {
    const view = renderCicd(payload());
    expect(view.gates.checksEnforced).toBe(false);
    expect(view.gates.required.length).toBeGreaterThan(0);
    const main = view.gates.refs.find((r) => r.kind === "branch" && r.ref === "main");
    expect(main).toBeDefined();
    expect(Number(main!.total)).toEqual(view.gates.required.length);
    const markup = await page(payload());
    expect(markup).toContain('data-checks-enforced="false"');
  });

  it("lists releases with their signing state, not a guess", () => {
    const releases = renderCicd(payload()).releases.rows;
    expect(releases.map((r) => r.tag)).toContain("deid-tr-ner-v1");
    const deid = releases.find((r) => r.tag === "deid-tr-ner-v1")!;
    expect(deid.signing).toEqual("not_applicable");
  });

  it("shows this deployment's own /version, and an unstamped build as unstamped", () => {
    const rows = renderCicd(payload()).deployments.rows;
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ source: "this_api", stamped: true });
    const dev = renderCicd(unconfigured()).deployments.rows[0]!;
    expect(dev).toMatchObject({ stamped: false, sha: null, sbomDigest: null });
  });

  it("says Argo CD and a canary are not deployed, and the rollback button says why", async () => {
    const markup = await page(payload());
    expect(markup).toContain('data-basis="no_argocd_in_infra"');
    expect(markup).toContain('data-basis="no_canary_controller_in_infra"');
    expect(markup).toMatch(/<button[^>]*disabled=""[^>]*data-reason="no_deploy_controller"/);
  });

  it("with nothing configured, the GitHub tiles are unknown and the gate refuses", async () => {
    const markup = await page(unconfigured());
    for (const tile of PROM_TILES) expect(tileState(markup, tile), tile).toEqual("unknown");
    expect(markup).toContain('data-reason="prometheus_unconfigured"');
    expect(tileState(markup, "freeze")).toEqual("unknown");
    expect(markup).toContain('data-reason="release_freeze_unconfigured"');
    expect(markup).toContain('data-verdict="refused"');
    expect(markup).toContain('data-refusal="release_freeze_unconfigured"');
  });

  it("paints the recorded freeze and the gate it closes", async () => {
    const view = renderCicd(payload());
    expect(view.freeze).toMatchObject({ state: "ok", engaged: true, lastChange: "freeze_engage" });
    expect(view.deployGate.allowed).toBe(false);
    expect(view.deployGate.refusals).toContain("deploy_freeze_engaged");
    expect(view.deployGate.enforcement).toContainEqual({
      point: "infra/staging/deploy.sh",
      status: "enforced",
    });
    const markup = await page(payload());
    expect(markup).toContain('data-freeze="engaged"');
    expect(markup).toContain('data-enforcement="not_deployed"');
  });

  it("no number is grouped (invariant 22)", async () => {
    const markup = await page(payload());
    expect(markup).not.toMatch(/\d,\d{3}\b/);
  });
});

// ------------------------------------------------------------------ the refusals

describe("what the view-model refuses rather than paints", () => {
  it("a document of another schema", () => {
    expect(() => renderCicd({ ...payload(), schema: "x" } as never)).toThrow(OpsSchemaMismatch);
  });

  it("'deploys allowed' beside an engaged freeze (near miss: refused beside it)", () => {
    const bent = withTile("deploy_gate", (t) => ({ ...t, allowed: true, refusals: [] }));
    expect(() => renderCicd(bent)).toThrow(CicdGateIncoherent);
    expect(() => renderCicd(payload())).not.toThrow();
  });

  it("'deploys allowed' beside an exhausted budget or an unreadable freeze", () => {
    const lifted = withTile("freeze", (t) => ({
      ...t,
      engaged: false,
      last_change: "freeze_lift",
      approved_by: "kc-sub-qms-owner",
    }));
    const open = withTile("deploy_gate", (t) => ({ ...t, allowed: true, refusals: [] }), lifted);
    expect(() => renderCicd(open)).not.toThrow();
    const spent = withTile(
      "error_budget",
      (t) => ({ ...t, state: "ok", reason: null, exhausted: ["api/availability"] }),
      open,
    );
    expect(() => renderCicd(spent)).toThrow(CicdGateIncoherent);
    const blind = withTile(
      "deploy_gate",
      (t) => ({ ...t, allowed: true, refusals: [] }),
      unconfigured(),
    );
    expect(() => renderCicd(blind)).toThrow(CicdGateIncoherent);
  });

  it("a freeze record the server could not hold", () => {
    const noKey = withTile("freeze", (t) => ({
      ...t,
      engaged: false,
      last_change: "freeze_lift",
      approved_by: null,
    }));
    expect(() => renderCicd(noKey)).toThrow(CicdFreezeIncoherent);
    const liftedButEngaged = withTile("freeze", (t) => ({
      ...t,
      last_change: "freeze_lift",
      approved_by: "kc-sub-qms-owner",
    }));
    expect(() => renderCicd(liftedButEngaged)).toThrow(CicdFreezeIncoherent);
  });

  it("Argo CD or a canary painted as deployed", () => {
    expect(() => renderCicd(withTile("argo_cd", (t) => ({ ...t, deployed: true })))).toThrow(
      CicdNotWired,
    );
    expect(() => renderCicd(withTile("canary", (t) => ({ ...t, deployed: true })))).toThrow(
      CicdNotWired,
    );
  });

  it("an unknown tile that still carries a figure", () => {
    const bent = withTile("releases", (t) => ({ ...t, state: "unknown", reason: "no_series" }));
    expect(() => renderCicd(bent)).toThrow(OpsUnknownCarriesFigure);
  });

  it("a workflow, a job or a PR that is not id-shaped", () => {
    const workflow = withTile("pipelines", (t) => ({
      ...t,
      workflows: t.workflows.map((w, i) => (i === 0 ? { ...w, workflow: "CI Workflow" } : w)),
    }));
    expect(() => renderCicd(workflow)).toThrow(OpsLabelLeaked);
    const pr = withTile("gates", (t) => ({
      ...t,
      refs: [
        ...t.refs,
        {
          kind: "pull_request" as const,
          ref: "Fix Ayşe's note",
          results: [],
          passing: 0,
          total: 0,
        },
      ],
    }));
    expect(() => renderCicd(pr)).toThrow(OpsLabelLeaked);
  });

  it("a signing state or a gate conclusion outside its vocabulary", () => {
    const signing = withTile("releases", (t) => ({
      ...t,
      releases: t.releases.map((r) => ({ ...r, signing: "trusted" })),
    }));
    expect(() => renderCicd(signing)).toThrow(OpsLabelLeaked);
  });

  it("a target beside a figure (invariant 20)", () => {
    const bent = withTile("pipelines", (t) => ({ ...t, target: "p95 < 10 min" }) as never);
    expect(() => renderCicd(bent)).toThrow(OpsTargetRendered);
  });
});

// ------------------------------------------------------------------ controls

describe("the controls — one key to freeze, a request for two to lift", () => {
  it("offers exactly two forms posting to the page's own handler, the step-up's Onayla per pending lift, and no rollback form", async () => {
    const markup = await page(payload());
    const pending = renderCicd(payload()).pending.actions.length;
    expect(markup.match(/action="\/cicd\/action" method="post"/g)?.length).toEqual(2);
    // INT-563: approval is the step-up, one form per pending request
    expect(markup.match(/action="\/step-up\/start"/g)?.length ?? 0).toEqual(pending);
    expect(markup.match(/<form /g)?.length).toEqual(2 + pending);
    expect(markup).toContain('data-control="freeze_engage" data-tier="1"');
    expect(markup).toContain('data-control="freeze_lift" data-tier="2"');
    expect(markup).not.toContain("step_up_unwired");
    expect(markup).not.toMatch(/name="(assertion_id|step_up_grant)"/);
  });

  it("names who may request and approve from the server's registry", () => {
    const catalogue = renderCicd(payload()).catalogue;
    const lift = catalogue.find((row) => row.control === "freeze_lift")!;
    expect(lift.approverRoles).toEqual(["platform_owner", "qms_owner"]);
    const engage = catalogue.find((row) => row.control === "freeze_engage")!;
    expect(engage.approverRoles).toEqual([]);
  });

  it("lists pending lift requests with the requester's role", async () => {
    const view = renderCicd(payload());
    expect(view.pending.actions).toHaveLength(1);
    expect(view.pending.actions[0]).toMatchObject({
      control: "freeze_lift",
      requestedRole: "platform_admin",
    });
  });

  it("shows a result code it knows and nothing it does not", async () => {
    const { state } = await load(payload());
    expect(html(state, "en", resultFrom("engaged"))).toContain('data-result="engaged"');
    expect(resultFrom("<script>")).toBeNull();
    expect(resultFrom(["engaged", "requested"])).toBeNull();
    expect(resultFrom("release_freeze_not_engaged")).toEqual("release_freeze_not_engaged");
  });

  it("renders in Turkish, the source of truth", async () => {
    const markup = await page(payload(), "tr");
    expect(markup).toContain("CI/CD ve sürümler");
    expect(markup).toContain("Dağıtım dondurma");
  });
});

// ------------------------------------------------------------------ the form handler

function form(fields: Record<string, string>): FormData {
  const data = new FormData();
  for (const [key, value] of Object.entries(fields)) data.set(key, value);
  return data;
}

const REASON = {
  reason_class: "incident_mitigation",
  justification: "Error budget burning on the api; hold every deploy.",
};

async function submit(
  fields: Record<string, string>,
  opts: { site?: string | null; authorization?: string | null; answer?: Recorded } = {},
): Promise<{ code: string; calls: Call[] }> {
  const answer = opts.answer ?? { status: 200, body: { changed: true } };
  const { fetch, calls } = recordedFetch({
    "/admin/cicd/freeze": answer,
    "/admin/cicd/freeze/lift": answer,
  });
  const outcome = await submitCicdAction({
    config: opsConfigFromEnv({ INTAKE_ADMIN_API_BASE: API }),
    authorization: opts.authorization === undefined ? "Bearer kc:sre_oncall" : opts.authorization,
    fetchSite: opts.site === undefined ? "same-origin" : opts.site,
    form: form(fields),
    fetch,
  });
  return { code: outcome.code, calls };
}

describe("the form handler — nothing reaches the API that the API would refuse", () => {
  it("freezes with one POST, the bearer, and the closed body", async () => {
    const { code, calls } = await submit({ action: "freeze_engage", ...REASON });
    expect(code).toEqual("engaged");
    expect(calls).toEqual([
      {
        url: `${API}/admin/cicd/freeze`,
        method: "POST",
        authorization: "Bearer kc:sre_oncall",
        body: REASON,
      },
    ]);
  });

  it("a frozen deployment frozen again is reported unchanged", async () => {
    const { code } = await submit(
      { action: "freeze_engage", ...REASON },
      { answer: { status: 200, body: { changed: false } } },
    );
    expect(code).toEqual("unchanged");
  });

  it("a lift is only a request", async () => {
    const { code, calls } = await submit(
      { action: "freeze_lift", ...REASON },
      { answer: { status: 200, body: { action_id: "a1", state: "pending" } } },
    );
    expect(code).toEqual("requested");
    expect(calls[0]).toMatchObject({ method: "POST", url: `${API}/admin/cicd/freeze/lift` });
  });

  it("refuses a cross-site post before anything is dialled (near miss: same-origin)", async () => {
    for (const site of ["cross-site", "same-site", "none", null]) {
      const { code, calls } = await submit({ action: "freeze_engage", ...REASON }, { site });
      expect(code).toEqual("cross_site_refused");
      expect(calls).toEqual([]);
    }
  });

  it.each([
    [{ action: "approve" }, "action_unknown"],
    [{ action: "rollback" }, "action_unknown"],
    [
      { action: "freeze_engage", reason_class: "Because I said so" },
      "release_freeze_reason_class_unknown",
    ],
  ])("refuses %j as %s without dialling", async (fields, expected) => {
    const { code, calls } = await submit({ ...REASON, ...fields });
    expect(code).toEqual(expected);
    expect(calls).toEqual([]);
  });

  it("carries the API's refusal code back, and only a code", async () => {
    const { code } = await submit(
      { action: "freeze_lift", ...REASON },
      { answer: { status: 409, body: { error: "release_freeze_not_engaged" } } },
    );
    expect(code).toEqual("release_freeze_not_engaged");
    const { code: prose } = await submit(
      { action: "freeze_lift", ...REASON },
      { answer: { status: 409, body: { error: "Ayşe could not lift it" } } },
    );
    expect(prose).toEqual("api_refused");
  });

  it("plans exactly the two controls", () => {
    expect(planCicdAction(form({ action: "freeze_engage", ...REASON }))).toEqual({
      ok: true,
      path: "/admin/cicd/freeze",
      body: REASON,
    });
    expect(planCicdAction(form({ action: "freeze_lift", ...REASON }))).toMatchObject({
      ok: true,
      path: "/admin/cicd/freeze/lift",
    });
  });
});

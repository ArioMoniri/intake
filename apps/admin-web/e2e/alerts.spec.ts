/**
 * INT-481 — the Alerts page: what Alertmanager holds right now, counted by
 * severity and listed by id, plus a plain link to the staff Grafana.
 *
 * **What this runs against.** `alerts.payload.json` and
 * `alerts.unknown.payload.json` are test fixtures written to the
 * `intake.admin.alerts.v1` contract that `GET /admin/alerts`
 * (`intake_api.admin.alerts_console`) serves, in its order: severity, then
 * `starts_at`, then name, with label keys sorted. The alert names and labels
 * are the ones `infra/observability/*-rules.yaml` declares.
 * The spec drives the page's own server-side loader through an injected
 * `fetch` and renders the page's own React tree to static markup, the same
 * headless node lane as every other console spec.
 *
 * **The properties, each with a near-miss.**
 * - Admission belongs to the API's gate. With no base or no bearer, nothing is
 *   dialled. A refusal from the gate is rendered as a refusal, with no second
 *   call and no Grafana link.
 * - The view-model refuses any payload that is not the contract exactly:
 *   schema, closed key sets, closed vocabularies, id-shaped labels and names
 *   (invariant 6), exact timestamps, and counts that agree with the rows.
 * - Unknown is a state, not a zero (invariant 17). An unknown source renders
 *   the word and the reason code, never a digit.
 * - The Grafana link is a plain anchor to a validated https origin, read on the
 *   server. Nothing is framed or embedded, and the CSP keeps `frame-src 'none'`
 *   (files/08 §0b F1, invariant 48).
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AlertsConsole } from "../src/alerts/console";
import { ENV_GRAFANA_URL, grafanaFromEnv, loadAlerts, type AlertsState } from "../src/alerts/load";
import {
  AlertsCountsIncoherent,
  AlertsShapeRefused,
  renderAlerts,
  type AlertsPayload,
} from "../src/alerts/module";
import { opsConfigFromEnv } from "../src/ops/access";
import { buildCsp } from "../src/ops/csp";
import {
  OpsLabelLeaked,
  OpsPayloadRefused,
  OpsSchemaMismatch,
  OpsUnknownCarriesFigure,
} from "../src/ops/guards";
import type { FetchLike } from "../src/ops/load";
import { ConsoleNav } from "../src/ops/nav";

const FIXTURES = join(__dirname, "fixtures");
const API = "https://api.intake.test";
const GRAFANA = "https://grafana.intake.test";

function read<T>(name: string): T {
  return JSON.parse(readFileSync(join(FIXTURES, name), "utf8")) as T;
}

const payload = (): AlertsPayload => read<AlertsPayload>("alerts.payload.json");
const unknownPayload = (): AlertsPayload => read<AlertsPayload>("alerts.unknown.payload.json");

interface Recorded {
  status: number;
  body: unknown;
}

interface Call {
  url: string;
  method: string;
  authorization: string | null;
  accept: string | null;
}

/** A fetch that answers from recorded responses and records what it was asked. */
function recordedFetch(routes: Record<string, Recorded | "network_error" | "not_json">): {
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
      accept: headers.get("accept"),
    });
    const answer = routes[new URL(url).pathname];
    if (answer === undefined || answer === "network_error") throw new TypeError("fetch failed");
    if (answer === "not_json") return new Response("<html>", { status: 200 });
    return new Response(JSON.stringify(answer.body), {
      status: answer.status,
      headers: { "content-type": "application/json" },
    });
  };
  return { fetch, calls };
}

/** A fetch that must never be called: every call is recorded as a violation. */
function forbiddenFetch(): { fetch: FetchLike; violations: string[] } {
  const violations: string[] = [];
  const fetch: FetchLike = async (url) => {
    violations.push(url);
    throw new Error(`dialled ${url} where nothing may be dialled`);
  };
  return { fetch, violations };
}

async function load(
  body: unknown,
  authorization: string | null = "Bearer kc:sre_oncall",
  status = 200,
): Promise<{ state: AlertsState; calls: Call[] }> {
  const { fetch, calls } = recordedFetch({ "/admin/alerts": { status, body } });
  const config = opsConfigFromEnv({ INTAKE_ADMIN_API_BASE: API });
  return { state: await loadAlerts({ config, authorization, fetch }), calls };
}

function html(state: AlertsState, lang: "tr" | "en" = "en", grafana: string | null = null): string {
  return renderToStaticMarkup(createElement(AlertsConsole, { state, lang, grafana }));
}

async function page(
  body: unknown,
  lang: "tr" | "en" = "en",
  grafana: string | null = null,
): Promise<string> {
  const { state } = await load(body);
  expect(state.kind).toEqual("console");
  return html(state, lang, grafana);
}

/** The markup of one tile, so an assertion cannot be satisfied by the header. */
function tile(markup: string, id: string): string {
  const match = new RegExp(`<section data-tile="${id}"[\\s\\S]*?</section>`).exec(markup);
  expect(match, `tile ${id} is rendered`).not.toBeNull();
  return match![0];
}

type Alert = AlertsPayload["alerts"][number];

function withAlert(index: number, patch: Record<string, unknown>): unknown {
  const base = payload();
  const alerts = base.alerts.map((alert, i) => (i === index ? { ...alert, ...patch } : alert));
  return { ...base, alerts };
}

function withLabels(labels: Record<string, unknown>): unknown {
  return withAlert(0, { labels });
}

/** The record without one of its keys — a missing field, not a null one. */
function omit(record: object, key: string): Record<string, unknown> {
  return Object.fromEntries(Object.entries(record).filter(([k]) => k !== key));
}

function refuses(body: unknown, refusal: typeof OpsPayloadRefused): void {
  expect(() => renderAlerts(body)).toThrow(refusal);
}

function accepts(body: unknown): void {
  expect(() => renderAlerts(body)).not.toThrow();
}

// ------------------------------------------------------------------ admission

describe("admission (the API's admin gate decides; nothing is dialled without a bearer)", () => {
  it("admits nobody without a bearer and never dials the API", async () => {
    const { fetch, violations } = forbiddenFetch();
    const state = await loadAlerts({
      config: opsConfigFromEnv({ INTAKE_ADMIN_API_BASE: API }),
      authorization: null,
      fetch,
    });
    expect(state).toEqual({ kind: "not_admitted", reason: "no_credentials" });
    expect(violations).toEqual([]);
    expect(html(state, "en", GRAFANA)).not.toContain("data-tile");
  });

  it("an unconfigured API base is unavailable and nothing is dialled", async () => {
    const { fetch, violations } = forbiddenFetch();
    const state = await loadAlerts({
      config: opsConfigFromEnv({}),
      authorization: "Bearer kc:sre_oncall",
      fetch,
    });
    expect(state).toEqual({ kind: "unavailable", reason: "api_base_unconfigured" });
    expect(violations).toEqual([]);
  });

  it("forwards the bearer once to GET {base}/admin/alerts", async () => {
    const { state, calls } = await load(payload());
    expect(state.kind).toEqual("console");
    expect(calls).toEqual([
      {
        url: `${API}/admin/alerts`,
        method: "GET",
        authorization: "Bearer kc:sre_oncall",
        accept: "application/json",
      },
    ]);
  });

  it.each([
    [401, { detail: { error: "unauthorized" } }, "token_refused"],
    [403, { detail: { error: "role_not_permitted" } }, "role_not_permitted"],
    [403, { detail: { error: "source_ip_refused" } }, "source_ip_refused"],
    [503, { detail: { error: "admin_console_unconfigured" } }, "console_unconfigured"],
  ])("a %i from the gate is a refusal, not a page (%j)", async (status, body, reason) => {
    const { state, calls } = await load(body, undefined, status);
    expect(state).toEqual({ kind: "not_admitted", reason });
    // near-miss: exactly the one authorising call, and nothing after it
    expect(calls.map((c) => new URL(c.url).pathname)).toEqual(["/admin/alerts"]);
    const markup = html(state, "en", GRAFANA);
    expect(markup).not.toContain("data-tile");
    expect(markup).toContain(`data-refusal="${reason}"`);
    // a refused caller is not handed the Grafana origin either
    expect(markup).not.toContain(GRAFANA);
  });

  it("an unreachable API is unavailable, not an empty page", async () => {
    const { fetch } = recordedFetch({ "/admin/alerts": "network_error" });
    const state = await loadAlerts({
      config: opsConfigFromEnv({ INTAKE_ADMIN_API_BASE: API }),
      authorization: "Bearer kc:sre_oncall",
      fetch,
    });
    expect(state).toEqual({ kind: "unavailable", reason: "api_unreachable" });
    expect(html(state, "en", GRAFANA)).not.toContain(GRAFANA);
  });

  it("a body that is not JSON is refused", async () => {
    const { fetch } = recordedFetch({ "/admin/alerts": "not_json" });
    const state = await loadAlerts({
      config: opsConfigFromEnv({ INTAKE_ADMIN_API_BASE: API }),
      authorization: "Bearer kc:sre_oncall",
      fetch,
    });
    expect(state).toEqual({ kind: "unavailable", reason: "payload_refused" });
  });

  it("a payload the view-model refuses is unavailable, never half-painted", async () => {
    const { state } = await load({ ...payload(), schema: "intake.admin.alerts.v0" });
    expect(state).toEqual({ kind: "unavailable", reason: "payload_refused" });
    const markup = html(state, "en", GRAFANA);
    expect(markup).not.toContain("data-tile");
    expect(markup).toContain('data-unavailable="payload_refused"');
  });
});

// ------------------------------------------------------- the view-model refuses

describe("the view-model refuses anything but the contract", () => {
  it("accepts both recorded shapes (the control for every refusal below)", () => {
    accepts(payload());
    accepts(unknownPayload());
  });

  it("refuses a document of another schema", () => {
    refuses({ ...payload(), schema: "intake.admin.alerts.v0" }, OpsSchemaMismatch);
    refuses({ ...payload(), schema: "intake.admin.ops.v1" }, OpsSchemaMismatch);
  });

  it("refuses an extra top-level key, and a missing one", () => {
    refuses({ ...payload(), annotations: {} }, AlertsShapeRefused);
    refuses({ ...payload(), target: 0 }, AlertsShapeRefused);
    refuses(omit(payload(), "withheld"), AlertsShapeRefused);
  });

  it("refuses a body that is not an object", () => {
    refuses(null, AlertsShapeRefused);
    refuses([payload()], AlertsShapeRefused);
    refuses("intake.admin.alerts.v1", AlertsShapeRefused);
  });

  it("refuses a source outside its two states, or with extra keys", () => {
    refuses({ ...payload(), source: { state: "degraded", reason: null } }, OpsPayloadRefused);
    refuses({ ...payload(), source: { state: "ok", reason: null, url: "x" } }, AlertsShapeRefused);
  });

  it("an ok source names no reason; an unknown one names a known code", () => {
    refuses(
      { ...payload(), source: { state: "ok", reason: "alertmanager_unreachable" } },
      OpsPayloadRefused,
    );
    refuses({ ...unknownPayload(), source: { state: "unknown", reason: null } }, OpsPayloadRefused);
    for (const reason of [
      "prometheus_unreachable",
      "alertmanager_http_50",
      "alertmanager_http_5000",
      "alertmanager_http_abc",
      "Alertmanager_unreachable",
    ]) {
      refuses({ ...unknownPayload(), source: { state: "unknown", reason } }, OpsPayloadRefused);
    }
    // near-miss: each known code, and a three-digit status
    for (const reason of [
      "alertmanager_unconfigured",
      "alertmanager_misconfigured",
      "alertmanager_unreachable",
      "alertmanager_bad_response",
      "alertmanager_http_502",
    ]) {
      accepts({ ...unknownPayload(), source: { state: "unknown", reason } });
    }
  });

  it("unknown carries no figure: counts, rows and withheld stay empty (invariant 17)", () => {
    refuses(
      { ...unknownPayload(), counts: { page: 0, ticket: 0, other: 0 } },
      OpsUnknownCarriesFigure,
    );
    refuses({ ...unknownPayload(), alerts: payload().alerts }, OpsUnknownCarriesFigure);
    refuses({ ...unknownPayload(), withheld: 1 }, OpsUnknownCarriesFigure);
    // near-miss: the empty forms
    accepts({ ...unknownPayload(), counts: null, alerts: [], withheld: 0 });
  });

  it("an ok source always carries counts", () => {
    refuses({ ...payload(), counts: null }, AlertsCountsIncoherent);
  });

  it("refuses counts with a key outside page/ticket/other, or one missing", () => {
    refuses(
      { ...payload(), counts: { page: 2, ticket: 2, other: 0, critical: 0 } },
      AlertsShapeRefused,
    );
    refuses({ ...payload(), counts: { page: 2, ticket: 2 } }, AlertsShapeRefused);
  });

  it("refuses a count that is not a non-negative integer", () => {
    for (const bad of [2.5, -1, "2", null, Number.NaN]) {
      refuses({ ...payload(), counts: { page: bad, ticket: 2, other: 0 } }, OpsPayloadRefused);
    }
    for (const bad of [-1, 0.5, "1", null]) {
      refuses({ ...payload(), withheld: bad }, OpsPayloadRefused);
    }
  });

  it("refuses a count that is not exactly its severity's rows", () => {
    // two page rows are listed: a page count of one hides a row that is shown
    refuses({ ...payload(), counts: { page: 1, ticket: 2, other: 0 } }, AlertsCountsIncoherent);
    // counts cover the listed rows only; the withheld one is not an "other"
    refuses({ ...payload(), counts: { page: 2, ticket: 2, other: 1 } }, AlertsCountsIncoherent);
    refuses({ ...payload(), counts: { page: 3, ticket: 2, other: 0 } }, AlertsCountsIncoherent);
    // near-miss: exactly the rows, with the withheld count left apart
    accepts({ ...payload(), counts: { page: 2, ticket: 2, other: 0 }, withheld: 7 });
  });

  it("refuses a severity outside page/ticket/other", () => {
    refuses(withAlert(0, { severity: "critical" }), OpsLabelLeaked);
    refuses(withAlert(0, { severity: "Page" }), OpsLabelLeaked);
    // near-miss: "other" is in the set (and the counts still bound the rows)
    accepts({
      ...(withAlert(0, { severity: "other" }) as AlertsPayload),
      counts: { page: 1, ticket: 2, other: 1 },
    });
  });

  it("refuses a state outside active/suppressed/unprocessed", () => {
    refuses(withAlert(0, { state: "firing" }), OpsLabelLeaked);
    refuses(withAlert(0, { state: "resolved" }), OpsLabelLeaked);
    accepts(withAlert(0, { state: "unprocessed" }));
  });

  it("refuses an alert with a key outside the contract (no annotations, ever)", () => {
    refuses(withAlert(0, { annotations: { summary: "api availability" } }), AlertsShapeRefused);
    refuses(withAlert(0, { fingerprint: "a1b2c3" }), AlertsShapeRefused);
    const missing = omit(payload().alerts[0]!, "labels");
    refuses({ ...payload(), alerts: [missing, ...payload().alerts.slice(1)] }, AlertsShapeRefused);
  });

  it("refuses a label key outside the closed set", () => {
    for (const key of ["instance", "job", "patient_id", "Service", "severity"]) {
      refuses(withLabels({ service: "api", [key]: "x" }), OpsLabelLeaked);
    }
    // near-miss: every key of the closed set at once
    accepts(
      withLabels({
        service: "api",
        slo: "availability",
        component: "asr",
        budget_id: "all-vendors-day",
        scope: "all_vendors",
        period: "day",
      }),
    );
  });

  it("refuses a label value that is not id-shaped (invariant 6)", () => {
    for (const value of ["Ayşe Yılmaz", "API", "-api", "", "a b", "api/v2", "x".repeat(65), 7]) {
      refuses(withLabels({ service: value }), OpsLabelLeaked);
    }
    // near-miss: the edges of the shape
    accepts(withLabels({ service: "api-v2.eu_1" }));
    accepts(withLabels({ service: "0" }));
    accepts(withLabels({ service: "x".repeat(64) }));
  });

  it("refuses labels that are not an object", () => {
    refuses(withLabels(["service=api"] as never), AlertsShapeRefused);
    refuses(withAlert(0, { labels: null }), AlertsShapeRefused);
  });

  it("refuses an alertname that is not an identifier", () => {
    for (const name of ["api availability", "9Lives", "Api-Burn", "_Api", "", "A".repeat(129)]) {
      refuses(withAlert(0, { alertname: name }), OpsLabelLeaked);
    }
    // near-miss: the edges of the shape
    accepts(withAlert(0, { alertname: "A" }));
    accepts(withAlert(0, { alertname: `A${"b_9".repeat(42)}` }));
  });

  it("refuses a timestamp that is not exactly YYYY-MM-DDTHH:MM:SSZ", () => {
    for (const when of [
      "2026-10-04T08:57:00.123Z",
      "2026-10-04 08:57:00Z",
      "2026-10-04T08:57:00+03:00",
      "2026-10-04",
      "2026-13-04T08:57:00Z",
      "2026-02-30T08:57:00Z",
      "2026-10-04T24:00:00Z",
    ]) {
      refuses(withAlert(0, { starts_at: when }), OpsPayloadRefused);
      refuses({ ...payload(), generated_at: when }, OpsPayloadRefused);
    }
    accepts(withAlert(0, { starts_at: "2026-02-28T23:59:59Z" }));
  });
});

// ----------------------------------------------------------------- the view

describe("the view (ids only; numbers as plain strings, invariant 22)", () => {
  it("projects counts, rows and labels in the closed-set order", () => {
    const view = renderAlerts(payload());
    expect(view.generatedAt).toEqual("2026-10-04T09:12:30Z");
    expect(view.source).toEqual({ state: "ok", reason: null });
    expect(view.counts).toEqual({ page: "2", ticket: "2", other: "0" });
    expect(view.withheld).toEqual("1");
    expect(view.alerts.map((a) => a.alertname)).toEqual([
      "AuditChainVerificationFailed",
      "ApiAvailabilityFastBurn",
      "CostBudgetNotConfigured",
      "ApiLatencyTicketBurn",
    ]);
    const cost = view.alerts[2]!;
    expect(cost.labels).toEqual([
      { key: "budget_id", value: "all-vendors-day" },
      { key: "scope", value: "all_vendors" },
      { key: "period", value: "day" },
    ]);
  });

  it("an unknown source projects no figure at all", () => {
    const view = renderAlerts(unknownPayload());
    expect(view.source).toEqual({ state: "unknown", reason: "alertmanager_unreachable" });
    expect(view.counts).toBeNull();
    expect(view.withheld).toBeNull();
    expect(view.alerts).toEqual([]);
  });
});

// --------------------------------------------------------------- the rendering

describe("the rendered page", () => {
  it("shows the counts by severity, then the alerts by id", async () => {
    const markup = await page(payload());
    const counts = tile(markup, "alert_counts");
    expect(counts).toContain('data-tile-state="ok"');
    expect(counts).toMatch(/data-count="page"[^>]*>2</);
    expect(counts).toMatch(/data-count="ticket"[^>]*>2</);
    expect(counts).toMatch(/data-count="other"[^>]*>0</);
    expect(counts).toMatch(/data-count="withheld"[^>]*>1</);

    const list = tile(markup, "alerts");
    expect(list).toContain("<table");
    expect(list).toContain("<code>ApiAvailabilityFastBurn</code>");
    expect(list).toContain('data-severity="page"');
    expect(list).toContain('data-alert-state="suppressed"');
    expect(list).toContain("<time>2026-10-04T08:57:00Z</time>");
    expect(list).toContain(">service=api<");
    expect(list).toContain(">budget_id=all-vendors-day<");
    // the counts tile comes first
    expect(markup.indexOf('data-tile="alert_counts"')).toBeLessThan(
      markup.indexOf('data-tile="alerts"'),
    );
  });

  it("renders an unknown source as the word and its reason, with no digit", async () => {
    const markup = await page(unknownPayload());
    for (const id of ["alert_counts", "alerts"]) {
      const section = tile(markup, id);
      expect(section).toContain('data-tile-state="unknown"');
      expect(section).toContain('data-reason="alertmanager_unreachable"');
      expect(section).toContain("Unknown");
      expect(section).toContain("<code>alertmanager_unreachable</code>");
      // the text a reader sees (tags such as <h2> carry digits of their own)
      expect(section.replace(/<[^>]*>/g, "")).not.toMatch(/[0-9]/);
      expect(section).not.toContain("<table");
    }
  });

  it("names an HTTP status reason by its code", async () => {
    const markup = await page({
      ...unknownPayload(),
      source: { state: "unknown", reason: "alertmanager_http_502" },
    });
    const section = tile(markup, "alert_counts");
    expect(section).toContain("<code>alertmanager_http_502</code>");
    expect(section).toContain("Alertmanager answered with an unexpected HTTP status");
  });

  it("an empty list says so in words", async () => {
    const markup = await page({
      ...payload(),
      counts: { page: 0, ticket: 0, other: 0 },
      alerts: [] as Alert[],
      withheld: 0,
    });
    const list = tile(markup, "alerts");
    expect(list).toContain('data-tile-state="ok"');
    expect(list).not.toContain("<table");
    expect(list).toContain("none");
  });

  it("renders Turkish by default, with the nav entry marked current", async () => {
    const markup = await page(payload(), "tr");
    expect(markup).toContain('lang="tr"');
    expect(markup).toContain('<span aria-current="page">Uyarılar</span>');
    expect(markup).toContain('href="/cicd"');
    const en = await page(payload(), "en");
    expect(en).toContain('<span aria-current="page">Alerts</span>');
    expect(en).toContain('href="/cicd?lang=en"');
  });

  it("every other console page links to /alerts from its nav, after CI/CD", () => {
    const nav = renderToStaticMarkup(createElement(ConsoleNav, { current: "ops", lang: "tr" }));
    expect(nav).toContain('<a href="/alerts">Uyarılar</a>');
    expect(nav.indexOf('href="/cicd"')).toBeLessThan(nav.indexOf('href="/alerts"'));
    expect(nav.endsWith('<a href="/alerts">Uyarılar</a></nav>')).toBe(true);
    const en = renderToStaticMarkup(createElement(ConsoleNav, { current: "cicd", lang: "en" }));
    expect(en).toContain('<a href="/alerts?lang=en">Alerts</a>');
  });
});

// ------------------------------------------------------------- the Grafana link

describe("the staff Grafana link (a plain anchor; files/08 §0b F1)", () => {
  it("reads only a plain https origin from the server env", () => {
    expect(ENV_GRAFANA_URL).toEqual("INTAKE_ADMIN_GRAFANA_URL");
    expect(grafanaFromEnv({ INTAKE_ADMIN_GRAFANA_URL: GRAFANA })).toEqual(`${GRAFANA}/`);
    expect(grafanaFromEnv({ INTAKE_ADMIN_GRAFANA_URL: `${GRAFANA}/` })).toEqual(`${GRAFANA}/`);
    expect(grafanaFromEnv({ INTAKE_ADMIN_GRAFANA_URL: ` ${GRAFANA} ` })).toEqual(`${GRAFANA}/`);
    expect(
      grafanaFromEnv({ INTAKE_ADMIN_GRAFANA_URL: "https://grafana.intake.test:3000" }),
    ).toEqual("https://grafana.intake.test:3000/");
  });

  it.each([
    ["unset", {}],
    ["empty", { INTAKE_ADMIN_GRAFANA_URL: "" }],
    ["http", { INTAKE_ADMIN_GRAFANA_URL: "http://grafana.intake.test" }],
    ["userinfo", { INTAKE_ADMIN_GRAFANA_URL: "https://admin:pw@grafana.intake.test" }],
    ["user only", { INTAKE_ADMIN_GRAFANA_URL: "https://admin@grafana.intake.test" }],
    ["empty userinfo", { INTAKE_ADMIN_GRAFANA_URL: "https://@grafana.intake.test" }],
    ["path", { INTAKE_ADMIN_GRAFANA_URL: "https://grafana.intake.test/d/api-slo" }],
    ["query", { INTAKE_ADMIN_GRAFANA_URL: "https://grafana.intake.test/?orgId=1" }],
    ["bare query", { INTAKE_ADMIN_GRAFANA_URL: "https://grafana.intake.test/?" }],
    ["fragment", { INTAKE_ADMIN_GRAFANA_URL: "https://grafana.intake.test/#panel" }],
    ["bare fragment", { INTAKE_ADMIN_GRAFANA_URL: "https://grafana.intake.test#" }],
    ["no scheme", { INTAKE_ADMIN_GRAFANA_URL: "grafana.intake.test" }],
    ["script", { INTAKE_ADMIN_GRAFANA_URL: "javascript:alert(1)" }],
    ["no host", { INTAKE_ADMIN_GRAFANA_URL: "https://" }],
    ["inner space", { INTAKE_ADMIN_GRAFANA_URL: "https://grafana .intake.test" }],
    ["backslash", { INTAKE_ADMIN_GRAFANA_URL: "https:\\\\grafana.intake.test" }],
    ["no slashes", { INTAKE_ADMIN_GRAFANA_URL: "https:grafana.intake.test" }],
    ["dot segment", { INTAKE_ADMIN_GRAFANA_URL: "https://grafana.intake.test/." }],
  ])("refuses a Grafana URL that is not a plain https origin (%s)", async (_, env) => {
    const grafana = grafanaFromEnv(env);
    expect(grafana).toBeNull();
    const markup = await page(payload(), "en", grafana);
    expect(markup).not.toContain('data-link="grafana"');
    expect(markup).not.toContain("grafana.intake.test");
    expect(markup).not.toContain("Grafana");
  });

  it("renders the valid origin as a plain anchor, never a frame", async () => {
    const markup = await page(
      payload(),
      "en",
      grafanaFromEnv({ INTAKE_ADMIN_GRAFANA_URL: GRAFANA }),
    );
    expect(markup).toMatch(
      /<a href="https:\/\/grafana\.intake\.test\/" rel="noopener noreferrer" data-link="grafana">[^<]+<\/a>/,
    );
    expect(markup.match(/data-link="grafana"/g)?.length).toEqual(1);
    for (const tag of ["<iframe", "<frame", "<embed", "<object", "<script"]) {
      expect(markup).not.toContain(tag);
    }
  });

  it("is still offered when Alertmanager is unknown, since the caller was admitted", async () => {
    const markup = await page(unknownPayload(), "tr", `${GRAFANA}/`);
    expect(markup).toContain('data-link="grafana"');
    expect(markup).not.toContain("<iframe");
  });

  it("leaves the CSP untouched: no frame source and no Grafana origin", () => {
    const csp = buildCsp("bm9uY2U=", "production");
    expect(csp).toContain("frame-src 'none'");
    expect(csp).not.toContain("grafana");
  });
});

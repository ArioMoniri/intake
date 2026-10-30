/**
 * INT-564 — the Compliance, Models and Experience pages, rendered.
 *
 * Each page's own loader runs over a recording fetch answered from the
 * committed fixtures (recorded from the real sources by scripts/dev), and the
 * spec renders the very tree the App Router page renders. Held: every read
 * goes with the caller's bearer to the API and nowhere else; a refusal or a
 * refused body paints no tile; consent counts below k ≥ 10 never show; the
 * benchmark control sends exactly a registry id and a lane; the Experience
 * window is always explicit; and every page passes axe in tr and en.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { createElement, type ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ComplianceConsole } from "../src/compliance/console";
import { loadCompliance, compliancePaths } from "../src/compliance/load";
import { ExperienceConsole } from "../src/experience/console";
import { loadExperience, windowFrom, windowQuery } from "../src/experience/load";
import { submitBenchmark } from "../src/models/actions";
import { ModelsConsole } from "../src/models/console";
import { benchmarkResultFrom, loadModels } from "../src/models/load";
import { opsConfigFromEnv } from "../src/ops/access";
import type { FetchLike } from "../src/ops/load";
import { AXE_TIMEOUT_MS, documentFor, violations } from "./support/axe";

const API = "https://api.intake.test";
const config = opsConfigFromEnv({ INTAKE_ADMIN_API_BASE: API });
const BEARER = "Bearer synthetic.console.token";
const NOW = new Date("2026-10-28T09:00:00Z");

function fixture(name: string): unknown {
  return JSON.parse(readFileSync(join(__dirname, "fixtures", name), "utf8"));
}

interface Seen {
  url: string;
  auth: string | null;
}

function recorded(routes: Record<string, [number, unknown]>): { fetch: FetchLike; seen: Seen[] } {
  const seen: Seen[] = [];
  return {
    seen,
    fetch: async (url, init) => {
      seen.push({ url, auth: new Headers(init?.headers).get("authorization") });
      const path = new URL(url).pathname;
      const [status, body] = routes[path] ?? [404, { error: "not_found" }];
      return new Response(JSON.stringify(body), { status });
    },
  };
}

function html(tree: ReactElement): string {
  return renderToStaticMarkup(tree);
}

const COMPLIANCE = fixture("compliance.payload.json") as Record<string, unknown>;

function complianceRoutes(
  overrides: Record<string, unknown> = {},
): Record<string, [number, unknown]> {
  const body = { ...COMPLIANCE, ...overrides } as Record<string, unknown>;
  return {
    "/admin/compliance/vendor-register": [200, body["vendor_register"]],
    "/admin/compliance/consents": [200, body["consents"]],
    "/admin/compliance/dsar": [200, body["dsar"]],
    "/admin/compliance/audit-search": [200, body["audit_search"]],
    "/admin/compliance/evidence-export": [200, body["evidence"]],
  };
}

describe("/compliance", () => {
  it("reads the five compliance routes with the caller's bearer, the audit search for one day", async () => {
    const api = recorded(complianceRoutes());
    const state = await loadCompliance({
      config,
      authorization: BEARER,
      fetch: api.fetch,
      now: NOW,
    });
    expect(state.kind).toBe("console");
    expect(api.seen.map((s) => new URL(s.url).pathname)).toEqual(
      Object.values(compliancePaths(NOW)).map((p) => p.split("?")[0]),
    );
    expect(api.seen.every((s) => s.auth === BEARER && s.url.startsWith(API))).toBe(true);
    expect(api.seen[3]!.url).toContain("since=2026-10-27T09%3A00%3A00.000Z");
  });

  it("paints every register row with its basis and deadline, in Turkish", async () => {
    const api = recorded(complianceRoutes());
    const state = await loadCompliance({
      config,
      authorization: BEARER,
      fetch: api.fetch,
      now: NOW,
    });
    const markup = html(createElement(ComplianceConsole, { state, lang: "tr" }));
    expect(markup).toContain('data-host="pypi.org"');
    expect(markup).toContain("Hukuki dayanak");
    expect(markup).toContain("<time>2026-09-08</time>");
    expect(markup).not.toContain("due by");
  });

  it("never shows a consent count between 1 and 9 (k ≥ 10)", async () => {
    const consents = {
      rows: [
        { scope: "intake.core", version: "v1", granted: 3, withdrawn: 0 },
        { scope: "research.optional", version: "v2", granted: 12, withdrawn: 9 },
      ],
    };
    const api = recorded(complianceRoutes({ consents }));
    const state = await loadCompliance({
      config,
      authorization: BEARER,
      fetch: api.fetch,
      now: NOW,
    });
    const markup = html(createElement(ComplianceConsole, { state, lang: "en" }));
    expect(markup).toContain("<td>fewer than 10</td><td>0</td>");
    expect(markup).toContain("<td>12</td><td>fewer than 10</td>");
    const tile = markup.slice(markup.indexOf('data-tile="consents"'));
    expect(tile.slice(0, tile.indexOf("</article>"))).not.toMatch(/<td>[1-9]<\/td>/);
  });

  it("refuses a transfer with no lawful basis: no tile is painted", async () => {
    const register = COMPLIANCE["vendor_register"] as { rows: Array<Record<string, unknown>> };
    const broken = { rows: register.rows.map((row) => ({ ...row, basis: " " })) };
    const api = recorded(complianceRoutes({ vendor_register: broken }));
    const state = await loadCompliance({
      config,
      authorization: BEARER,
      fetch: api.fetch,
      now: NOW,
    });
    expect(state).toEqual({ kind: "unavailable", reason: "payload_refused" });
    expect(html(createElement(ComplianceConsole, { state, lang: "tr" }))).not.toContain(
      "data-tile",
    );
  });

  it("a role refused at the first read stops the load there", async () => {
    const api = recorded({
      "/admin/compliance/vendor-register": [403, { detail: { error: "forbidden" } }],
    });
    const state = await loadCompliance({
      config,
      authorization: BEARER,
      fetch: api.fetch,
      now: NOW,
    });
    expect(state).toEqual({ kind: "not_admitted", reason: "role_not_permitted" });
    expect(api.seen).toHaveLength(1);
  });
});

const MODELS = fixture("models.payload.json") as Record<string, unknown>;

describe("/models", () => {
  it("puts the release gate first, then every registry row in registry order", async () => {
    const api = recorded({ "/admin/models": [200, MODELS] });
    const state = await loadModels({ config, authorization: BEARER, fetch: api.fetch });
    const markup = html(createElement(ModelsConsole, { state, lang: "tr", result: null }));
    expect(markup.indexOf('data-tile="release"')).toBeLessThan(
      markup.indexOf('data-tile="registry"'),
    );
    expect(markup).toContain('data-release-blocked="true"');
    const rows = [...markup.matchAll(/data-component="([^"]+)"/g)].map((m) => m[1]);
    expect(rows).toEqual((MODELS["rows"] as Array<{ component: string }>).map((r) => r.component));
  });

  it("an enabled lane is a form; a disabled one says why and posts nothing", async () => {
    const api = recorded({ "/admin/models": [200, MODELS] });
    const state = await loadModels({ config, authorization: BEARER, fetch: api.fetch });
    const markup = html(createElement(ModelsConsole, { state, lang: "en", result: null }));
    expect(markup).toMatch(/data-lane="latency" action="\/models\/action" method="post"/);
    expect(markup).toMatch(
      /<button type="button" disabled="" data-lane="quality" title="[^"]+">Quality/,
    );
  });

  it("refuses a clear release over a blocking row", async () => {
    const lying = { ...MODELS, release: { blocked: false, reasons: [] } };
    const api = recorded({ "/admin/models": [200, lying] });
    const state = await loadModels({ config, authorization: BEARER, fetch: api.fetch });
    expect(state).toEqual({ kind: "unavailable", reason: "payload_refused" });
  });

  it("the benchmark sends exactly a registry id and a lane, same-origin only", async () => {
    const api = recorded({ "/admin/models/postgres/benchmark": [200, { plan: {} }] });
    const form = new FormData();
    form.set("component", "postgres");
    form.set("kind", "latency");
    const ok = await submitBenchmark({
      config,
      authorization: BEARER,
      fetchSite: "same-origin",
      form,
      fetch: api.fetch,
    });
    expect(ok.code).toBe("benchmark_requested");
    expect(api.seen.map((s) => s.url)).toEqual([`${API}/admin/models/postgres/benchmark`]);
    for (const [component, kind, site] of [
      ["postgres", "latency", "cross-site"],
      ["../ops", "latency", "same-origin"],
      ["postgres", "accuracy", "same-origin"],
    ] as const) {
      const bad = new FormData();
      bad.set("component", component);
      bad.set("kind", kind);
      const refused = await submitBenchmark({
        config,
        authorization: BEARER,
        fetchSite: site,
        form: bad,
        fetch: api.fetch,
      });
      expect(refused.code).not.toBe("benchmark_requested");
    }
    expect(api.seen).toHaveLength(1);
  });

  it("shows the API's corpus refusal as a code, never its prose", async () => {
    const api = recorded({
      "/admin/models/postgres/benchmark": [
        409,
        { detail: { error: "no_named_corpus", reason: "prose" } },
      ],
    });
    const form = new FormData();
    form.set("component", "postgres");
    form.set("kind", "quality");
    const refused = await submitBenchmark({
      config,
      authorization: BEARER,
      fetchSite: "same-origin",
      form,
      fetch: api.fetch,
    });
    expect(refused.code).toBe("no_named_corpus");
    expect(benchmarkResultFrom("no_named_corpus")).toBe("no_named_corpus");
    expect(benchmarkResultFrom("<b>")).toBeNull();
  });
});

const EXPERIENCE = fixture("experience.payload.json");

describe("/experience", () => {
  it("always asks for an explicit window: the page's own, or the 30 days before today", () => {
    expect(windowFrom({}, NOW)).toEqual({ from: "2026-09-28", to: "2026-10-27" });
    expect(windowFrom({ from: "2026-08-01", to: "2026-08-31" }, NOW)).toEqual({
      from: "2026-08-01",
      to: "2026-08-31",
    });
    for (const bad of [
      { from: "2026-08-31", to: "2026-08-01" },
      { from: "2025-01-01", to: "2026-08-31" },
      { from: "2026-02-30", to: "2026-03-01" },
      { from: "yesterday", to: "today" },
    ]) {
      expect(windowFrom(bad, NOW)).toEqual({ from: "2026-09-28", to: "2026-10-27" });
    }
    expect(windowQuery({ from: "2026-08-01", to: "2026-08-31" })).toBe(
      "window_start=2026-08-01T00%3A00%3A00%2B00%3A00&window_end=2026-09-01T00%3A00%3A00%2B00%3A00",
    );
  });

  it("reads the composite for that window and says which window it shows; no tenant is named", async () => {
    const api = recorded({ "/admin/experience": [200, EXPERIENCE] });
    const window = { from: "2026-08-01", to: "2026-08-31" };
    const state = await loadExperience({ config, authorization: BEARER, fetch: api.fetch, window });
    expect(api.seen[0]!.url).toBe(`${API}/admin/experience?${windowQuery(window)}`);
    expect(api.seen[0]!.url).not.toContain("tenant");
    const markup = html(createElement(ExperienceConsole, { state, lang: "tr" }));
    expect(markup).toContain("<time>2026-08-01</time> – <time>2026-08-31</time>");
    expect(markup).toContain("Yanıt sayısı 10&#x27;un altında");
    expect(markup).toContain('data-dimension="branch" data-available="false"');
  });

  it("a body that carries a figure below the floor paints nothing", async () => {
    const body = JSON.parse(JSON.stringify(EXPERIENCE)) as { csat: Record<string, unknown> };
    body.csat["score_counts"] = { "5": 3 };
    const api = recorded({ "/admin/experience": [200, body] });
    const state = await loadExperience({
      config,
      authorization: BEARER,
      fetch: api.fetch,
      window: windowFrom({}, NOW),
    });
    expect(state).toEqual({ kind: "unavailable", reason: "payload_refused" });
  });
});

describe("the three pages pass axe in both languages", () => {
  it(
    "compliance, models and experience",
    async () => {
      for (const lang of ["tr", "en"] as const) {
        const compliance = await loadCompliance({
          config,
          authorization: BEARER,
          fetch: recorded(complianceRoutes()).fetch,
          now: NOW,
        });
        const models = await loadModels({
          config,
          authorization: BEARER,
          fetch: recorded({ "/admin/models": [200, MODELS] }).fetch,
        });
        const experience = await loadExperience({
          config,
          authorization: BEARER,
          fetch: recorded({ "/admin/experience": [200, EXPERIENCE] }).fetch,
          window: windowFrom({}, NOW),
        });
        for (const tree of [
          createElement(ComplianceConsole, { state: compliance, lang }),
          createElement(ModelsConsole, { state: models, lang, result: "benchmark_requested" }),
          createElement(ExperienceConsole, { state: experience, lang }),
        ]) {
          expect(await violations(documentFor(tree, lang))).toEqual([]);
        }
      }
    },
    AXE_TIMEOUT_MS * 3,
  );
});

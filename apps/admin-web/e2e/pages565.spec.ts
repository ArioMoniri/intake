/**
 * INT-565 — the Protocols, Clinical quality & safety, Security and Cost pages,
 * rendered.
 *
 * Each page's own loader runs over a recording fetch answered from the
 * committed fixtures — each recorded by `scripts/dev` through the API route's
 * own builder — and the spec renders the very tree the App Router page
 * renders. Held: every read goes with the caller's bearer to its one API route
 * and nowhere else, and nothing is dialled without a bearer; a refusal or a
 * refused body keeps the shell and paints no tile; a figure with no source
 * behind it is a word, never a zero; no chain head reaches the Security page;
 * and every page passes axe in tr and en.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { createElement, type ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { CostConsole } from "../src/cost/console";
import { loadCost } from "../src/cost/load";
import { opsConfigFromEnv } from "../src/ops/access";
import type { FetchLike } from "../src/ops/load";
import { ProtocolsConsole } from "../src/protocols/console";
import { loadProtocols } from "../src/protocols/load";
import { QualitySafetyConsole } from "../src/safety/console";
import { loadQualitySafety } from "../src/safety/load";
import { SecurityConsole } from "../src/security/console";
import { loadSecurity } from "../src/security/load";
import { AXE_TIMEOUT_MS, documentFor, violations } from "./support/axe";

const API = "https://api.intake.test";
const config = opsConfigFromEnv({ INTAKE_ADMIN_API_BASE: API });
const BEARER = "Bearer synthetic.console.token";

type Json = Record<string, unknown>;

function fixture(name: string): Json {
  return JSON.parse(readFileSync(join(__dirname, "fixtures", name), "utf8")) as Json;
}

function clone(body: Json): Json {
  return JSON.parse(JSON.stringify(body)) as Json;
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
      const [status, body] = routes[new URL(url).pathname] ?? [404, { error: "not_found" }];
      return new Response(JSON.stringify(body), { status });
    },
  };
}

function html(tree: ReactElement): string {
  return renderToStaticMarkup(tree);
}

const PROTOCOLS = fixture("protocols.payload.json");
const SAFETY = fixture("safety.payload.json");
const SECURITY = fixture("security.payload.json");
const COST = fixture("cost.payload.json");
const COST_PRICED = fixture("cost.priced.payload.json");

const PAGES = [
  { page: "protocols", path: "/admin/protocols", body: PROTOCOLS, load: loadProtocols },
  { page: "quality-safety", path: "/admin/quality-safety", body: SAFETY, load: loadQualitySafety },
  { page: "security", path: "/admin/security", body: SECURITY, load: loadSecurity },
  { page: "cost", path: "/admin/cost", body: COST, load: loadCost },
] as const;

function tree(page: (typeof PAGES)[number]["page"], state: never, lang: "tr" | "en"): ReactElement {
  switch (page) {
    case "protocols":
      return createElement(ProtocolsConsole, { state, lang });
    case "quality-safety":
      return createElement(QualitySafetyConsole, { state, lang });
    case "security":
      return createElement(SecurityConsole, { state, lang });
    case "cost":
      return createElement(CostConsole, { state, lang });
  }
}

describe("every page reads its one route with the caller's bearer, and nothing without one", () => {
  for (const { page, path, body, load } of PAGES) {
    it(page, async () => {
      const api = recorded({ [path]: [200, body] });
      const state = await load({ config, authorization: BEARER, fetch: api.fetch });
      expect(state.kind).toBe("console");
      expect(api.seen).toEqual([{ url: `${API}${path}`, auth: BEARER }]);

      const none = recorded({ [path]: [200, body] });
      const refused = await load({ config, authorization: null, fetch: none.fetch });
      expect(refused).toEqual({ kind: "not_admitted", reason: "no_credentials" });
      expect(none.seen).toEqual([]);
    });
  }
});

describe("a refusal keeps the shell, names the next step and paints no tile", () => {
  for (const { page, path, load } of PAGES) {
    it(page, async () => {
      const api = recorded({ [path]: [403, { detail: { error: "forbidden" } }] });
      const state = await load({ config, authorization: BEARER, fetch: api.fetch });
      expect(state).toEqual({ kind: "not_admitted", reason: "role_not_permitted" });
      const markup = html(tree(page, state as never, "tr"));
      expect(markup).toContain(`aria-current="page" data-page-link="${page}"`);
      expect(markup).toContain('data-next-step="role_not_permitted"');
      expect(markup).not.toContain("data-tile=");
    });
  }
});

describe("/protocols", () => {
  it("paints every branch, never an L0 draft as served, and the empty review queue", async () => {
    const state = await loadProtocols({
      config,
      authorization: BEARER,
      fetch: recorded({ "/admin/protocols": [200, PROTOCOLS] }).fetch,
    });
    const markup = html(createElement(ProtocolsConsole, { state, lang: "tr" }));
    const coverage = PROTOCOLS["coverage"] as { rows: unknown[] };
    expect(markup.match(/data-branch="/g)).toHaveLength(coverage.rows.length);
    expect(markup).not.toContain('data-servable="true"');
    expect(markup).toContain("L0 · taslak, sunulmuyor");
    expect(markup).toContain('data-empty="review"');
    expect(markup).toContain('data-target="CandidateRedFlag"');
    expect(markup).not.toContain("<button");
  });

  it("refuses a body that counts an L0 pack as coverage: no tile is painted", async () => {
    const body = clone(PROTOCOLS);
    const rows = (body["coverage"] as { rows: Json[] }).rows;
    rows[0] = {
      ...rows[0],
      status: "DIRECT",
      served_pack_id: "specialty.x",
      served_maturity: "L0",
    };
    const state = await loadProtocols({
      config,
      authorization: BEARER,
      fetch: recorded({ "/admin/protocols": [200, body] }).fetch,
    });
    expect(state).toEqual({ kind: "unavailable", reason: "payload_refused" });
    expect(html(createElement(ProtocolsConsole, { state, lang: "en" }))).not.toContain("data-tile");
  });
});

describe("/quality-safety", () => {
  it("with no scrape, PolicyGuard is an unknown tile with its cause and fill, and no count", async () => {
    const state = await loadQualitySafety({
      config,
      authorization: BEARER,
      fetch: recorded({ "/admin/quality-safety": [200, SAFETY] }).fetch,
    });
    const markup = html(createElement(QualitySafetyConsole, { state, lang: "tr" }));
    expect(markup).toContain('data-tile="policyguard" data-tile-state="unknown"');
    expect(markup).toContain("Prometheus adresi yapılandırılmamış");
    expect(markup).not.toMatch(/data-class="[a-z_]+"><td><code>[a-z_]+<\/code><\/td><td>0</);
    expect(markup).toContain('data-content-read="refused"');
    expect(markup).toContain("<code>HB-L6</code>");
    expect(markup).toContain('data-empty="items"');
  });

  it("a scraped body paints its counts over the stated window", async () => {
    const body = clone(SAFETY);
    const guard = body["policyguard_classes"] as Json & { classes: Json[] };
    guard["source_available"] = true;
    guard["source_reason"] = null;
    guard["classes"] = guard.classes.map((row, i) => ({ ...row, count: i }));
    const state = await loadQualitySafety({
      config,
      authorization: BEARER,
      fetch: recorded({ "/admin/quality-safety": [200, body] }).fetch,
    });
    const markup = html(createElement(QualitySafetyConsole, { state, lang: "en" }));
    expect(markup).toContain('data-tile="policyguard" data-tile-state="ok"');
    expect(markup).toContain('data-class="treatment"><td><code>treatment</code></td><td>1</td>');
    expect(markup).toContain("Window: 24h");
  });

  it("refuses a PolicyGuard zero with no scrape behind it", async () => {
    const body = clone(SAFETY);
    const guard = body["policyguard_classes"] as { classes: Json[] };
    guard.classes[0] = { ...guard.classes[0], count: 0 };
    const state = await loadQualitySafety({
      config,
      authorization: BEARER,
      fetch: recorded({ "/admin/quality-safety": [200, body] }).fetch,
    });
    expect(state).toEqual({ kind: "unavailable", reason: "payload_refused" });
  });
});

describe("/security", () => {
  it("says the feed is not wired per detector, egress is unknown, the chain is not attested", async () => {
    const state = await loadSecurity({
      config,
      authorization: BEARER,
      fetch: recorded({ "/admin/security": [200, SECURITY] }).fetch,
    });
    const markup = html(createElement(SecurityConsole, { state, lang: "tr" }));
    expect(markup).toContain('data-feed-configured="false"');
    expect(markup.match(/data-detector="/g)).toHaveLength(3);
    expect(markup).toContain('data-tile="egress" data-tile-state="unknown"');
    expect(markup).toContain('data-outcome="anchor_missing"');
    expect(markup).toContain("HB-I12");
    expect(markup).not.toMatch(/\b[0-9a-f]{64}\b/);
  });

  it("refuses a body that carries a chain head", async () => {
    const body = clone(SECURITY);
    (body["audit_chain"] as Json)["local_head"] = "0".repeat(64);
    const state = await loadSecurity({
      config,
      authorization: BEARER,
      fetch: recorded({ "/admin/security": [200, body] }).fetch,
    });
    expect(state).toEqual({ kind: "unavailable", reason: "payload_refused" });
  });
});

describe("/cost", () => {
  it("with no price configured, every price and budget says so and no money is painted", async () => {
    const state = await loadCost({
      config,
      authorization: BEARER,
      fetch: recorded({ "/admin/cost": [200, COST] }).fetch,
    });
    const markup = html(createElement(CostConsole, { state, lang: "tr" }));
    expect(markup).toContain("fiyat girilmemiş");
    expect(markup).toContain("bütçe girilmemiş");
    expect(markup).not.toMatch(/\d USD/);
    expect(markup).toMatch(/<code>[0-9a-f]{32}<\/code>/);
    expect(markup).toContain('data-source-configured="false"');
  });

  it("the priced recording paints money atoms and withholds an incomplete total", async () => {
    const state = await loadCost({
      config,
      authorization: BEARER,
      fetch: recorded({ "/admin/cost": [200, COST_PRICED] }).fetch,
    });
    const markup = html(createElement(CostConsole, { state, lang: "en" }));
    expect(markup).toMatch(/\d USD/);
    expect(markup).toContain("a part is missing; no total shown");
  });

  it("refuses a cost figure on a row with no price", async () => {
    const body = clone(COST);
    const window = (body["windows"] as Json[])[0] as { per_session: Json[] };
    window.per_session[0] = { ...window.per_session[0], usd_per_session: 0 };
    const state = await loadCost({
      config,
      authorization: BEARER,
      fetch: recorded({ "/admin/cost": [200, body] }).fetch,
    });
    expect(state).toEqual({ kind: "unavailable", reason: "payload_refused" });
  });
});

describe("the four pages pass axe in both languages", () => {
  it(
    "protocols, quality-safety, security and cost",
    async () => {
      for (const lang of ["tr", "en"] as const) {
        for (const { page, path, body, load } of PAGES) {
          const state = await load({
            config,
            authorization: BEARER,
            fetch: recorded({ [path]: [200, body] }).fetch,
          });
          expect(await violations(documentFor(tree(page, state as never, lang), lang))).toEqual([]);
        }
      }
    },
    AXE_TIMEOUT_MS * 4,
  );
});

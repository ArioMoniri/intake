/**
 * INT-490 — the Analytics page (LD-06): anonymised aggregates only.
 *
 * **What this runs against.** Every payload is a recording, in tests only,
 * made by `scripts/dev/record_analytics_fixture.py` from the real
 * `build_release` / `release_payload` over a SYNTHETIC population
 * (`tests/fixtures/analytics/synthetic_population.json`, counts of simulated
 * people and nothing else):
 * - `analytics.payload.json` — the release as the live API builds it today
 *   (funnel and language live; triage, platform and per-question views not
 *   collected; retention undecided);
 * - `analytics.full.payload.json` — every view kind collected, the page's
 *   per-question rendering and both withheld reasons;
 * - `analytics.unconfigured.payload.json` — no tenant admitted.
 *
 * **The properties, each with a near miss.** A withheld table shows `<10` and
 * no figure; a shown cell of 1..9 is refused, 10 is painted; a withheld table
 * that kept a cell is refused; k under ten is refused; free text, an unknown
 * dimension key or a target beside a figure is refused (invariants 6, 20);
 * the loader forwards a closed ISO week and nothing else (no free-form
 * filter); no `style` attribute (the CSP is unchanged).
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AnalyticsConsole } from "../src/analytics/console";
import { COPY } from "../src/analytics/copy";
import { loadAnalytics, periodFrom, type AnalyticsState } from "../src/analytics/load";
import {
  AnalyticsFloorLowered,
  AnalyticsThinCellRendered,
  AnalyticsWithheldCarriesCells,
  renderAnalytics,
  type AnalyticsPayload,
  type ShownViewPayload,
} from "../src/analytics/module";
import { opsConfigFromEnv } from "../src/ops/access";
import { OpsLabelLeaked, OpsSchemaMismatch, OpsTargetRendered } from "../src/ops/guards";
import type { FetchLike } from "../src/ops/load";

const FIXTURES = join(__dirname, "fixtures");
const API = "https://api.intake.test";
const BEARER = "Bearer unit-lane-researcher";

function read(name: string): AnalyticsPayload {
  return JSON.parse(readFileSync(join(FIXTURES, name), "utf8")) as AnalyticsPayload;
}

const live = (): AnalyticsPayload => read("analytics.payload.json");
const full = (): AnalyticsPayload => read("analytics.full.payload.json");
const unconfigured = (): AnalyticsPayload => read("analytics.unconfigured.payload.json");

function html(state: AnalyticsState, lang: "tr" | "en" = "tr"): string {
  return renderToStaticMarkup(createElement(AnalyticsConsole, { state, lang }));
}

function page(payload: AnalyticsPayload, lang: "tr" | "en" = "tr"): string {
  return html({ kind: "console", view: renderAnalytics(payload) }, lang);
}

function tile(markup: string, id: string): string {
  const start = markup.indexOf(`data-tile="${id}"`);
  expect(start).toBeGreaterThan(-1);
  const end = markup.indexOf("</section>", start);
  return markup.slice(start, end);
}

function firstShown(payload: AnalyticsPayload): ShownViewPayload {
  const view = payload.views.find((v) => v.state === "shown");
  if (view === undefined || view.state !== "shown") throw new Error("fixture has no shown view");
  return view;
}

describe("the recorded release", () => {
  it("paints the funnel as people reaching at least each stage, with the loss between", () => {
    const view = renderAnalytics(live());
    const family = view.families.find((f) => f.protocol === "previsit.dev.visit");
    const funnel = family?.tables.find((t) => t.kind === "funnel");
    expect(funnel?.state).toBe("shown");
    expect(funnel?.rows.map((r) => [r.value, r.people, r.dropOff])).toEqual([
      ["invited", "61", null],
      ["started", "47", "14"],
      ["finished", "33", "14"],
      ["shared", "23", "10"],
    ]);
    expect(funnel?.rows[3]?.share).toBe("38 %");
  });

  it("marks a withheld table <10 and paints no figure in it", () => {
    const markup = page(live());
    const withheld = tile(markup, "funnel:base.intake:1.0.0");
    expect(withheld).toContain('data-view-state="withheld"');
    expect(withheld).toContain("&lt;10");
    expect(withheld).toContain("below_k");
    expect(withheld).not.toMatch(/<td>/);
    expect(withheld.replace("&lt;10", "")).not.toMatch(/\b(4|12|16)\b/);
  });

  it("says what is not collected, and why, instead of estimating it", () => {
    const markup = page(live());
    const block = tile(markup, "not_collected");
    for (const kind of ["triage", "platform", "question_outcome", "question_asr"]) {
      expect(block).toContain(`data-kind="${kind}"`);
    }
    expect(block).toContain("triage_level_not_recorded");
    expect(block).toContain("raw_telemetry_retention_undecided");
  });

  it("reports retention as undecided and keeps nothing", () => {
    const markup = page(live());
    expect(tile(markup, "release")).toContain('data-retention="undecided"');
    expect(markup).toContain(COPY.tr.kept);
  });

  it("renders every per-question table and both withheld reasons when collected", () => {
    const markup = page(full());
    expect(markup).toContain('data-question="visit.onset"');
    expect(tile(markup, "question_outcome:previsit.dev.visit:int197-dev:visit.onset")).toContain(
      "below_k",
    );
    expect(
      tile(markup, "question_mode:previsit.dev.visit:int197-dev:visit.chief_complaint"),
    ).toContain("cross_view");
    expect(markup).toContain(COPY.tr.views.question_asr);
  });

  it("an unconfigured registry says no tenant is admitted, with no table", () => {
    const markup = page(unconfigured());
    expect(markup).toContain('data-empty="true"');
    expect(markup).toContain(COPY.tr.tenants.unconfigured);
    expect(markup).not.toContain("data-view-state");
  });

  it("is server-rendered with no style attribute (the CSP is unchanged)", () => {
    for (const payload of [live(), full(), unconfigured()]) {
      for (const lang of ["tr", "en"] as const) {
        expect(page(payload, lang)).not.toMatch(/\sstyle=/);
      }
    }
  });

  it("has the same copy keys in tr and en, and English renders", () => {
    const keys = (value: object): string[] => Object.keys(value).sort();
    expect(keys(COPY.en)).toEqual(keys(COPY.tr));
    expect(keys(COPY.en.views)).toEqual(keys(COPY.tr.views));
    expect(keys(COPY.en.values)).toEqual(keys(COPY.tr.values));
    expect(page(live(), "en")).toContain("Analytics — research and improvement");
  });
});

describe("refusals, each with its near miss", () => {
  it("a shown cell of 9 is refused, a cell of 10 is painted", () => {
    const at = (subjects: number): AnalyticsPayload => {
      const payload = live();
      const view = firstShown(payload);
      view.cells = [
        { value: view.cells[0]!.value, subjects },
        ...view.cells.slice(1).map((cell) => ({ ...cell, subjects: 10 })),
      ];
      return payload;
    };
    expect(() => renderAnalytics(at(9))).toThrow(AnalyticsThinCellRendered);
    expect(() => renderAnalytics(at(10))).not.toThrow();
  });

  it("a withheld table that kept a cell is refused", () => {
    const payload = live();
    const withheld = payload.views.find((v) => v.state === "withheld")!;
    (withheld as unknown as { cells: unknown }).cells = [{ value: "invited", subjects: 12 }];
    expect(() => renderAnalytics(payload)).toThrow(AnalyticsWithheldCarriesCells);
  });

  it("k under the product floor is refused; ten is not", () => {
    expect(() => renderAnalytics({ ...live(), k: 9 })).toThrow(AnalyticsFloorLowered);
    expect(() => renderAnalytics({ ...live(), k: 10 })).not.toThrow();
  });

  it("free text, an unknown dimension key or another schema is refused", () => {
    const text = live();
    firstShown(text).dimensions.protocol = "göğüs ağrısı";
    expect(() => renderAnalytics(text)).toThrow(OpsLabelLeaked);

    const key = live();
    (firstShown(key).dimensions as unknown as Record<string, string>)["patient_id"] = "p1";
    expect(() => renderAnalytics(key)).toThrow(OpsLabelLeaked);

    const outside = live();
    firstShown(outside).cells[0]!.value = "dropped_at_question_seven";
    expect(() => renderAnalytics(outside)).toThrow(OpsLabelLeaked);

    expect(() =>
      renderAnalytics({ ...live(), schema: "intake.admin.ops.v1" } as unknown as AnalyticsPayload),
    ).toThrow(OpsSchemaMismatch);
  });

  it("a target beside a figure is refused (invariant 20)", () => {
    const payload = live() as unknown as Record<string, unknown>;
    payload["completion_target"] = 90;
    expect(() => renderAnalytics(payload as unknown as AnalyticsPayload)).toThrow(
      OpsTargetRendered,
    );
  });
});

describe("the loader: one parameter, a closed week, the API's gate", () => {
  const now = new Date("2026-10-16T09:00:00Z");

  it("forwards only a closed ISO week", () => {
    expect(periodFrom("2026-W41", now)).toBe("2026-W41");
    expect(periodFrom("2026-W42", now)).toBeNull(); // still open on 16 Oct
    expect(periodFrom("2026-W60", now)).toBeNull();
    expect(periodFrom("2026-41", now)).toBeNull();
    expect(periodFrom(["2026-W41"], now)).toBeNull();
    expect(periodFrom(undefined, now)).toBeNull();
  });

  function recorded(status: number, body: unknown): { fetch: FetchLike; urls: string[] } {
    const urls: string[] = [];
    const fetch: FetchLike = async (url) => {
      urls.push(url);
      return new Response(JSON.stringify(body), { status });
    };
    return { fetch, urls };
  }

  it("dials the API with the period and nothing else", async () => {
    const { fetch, urls } = recorded(200, live());
    const state = await loadAnalytics({
      config: opsConfigFromEnv({ INTAKE_ADMIN_API_BASE: API }),
      authorization: BEARER,
      fetch,
      period: "2026-W41",
    });
    expect(state.kind).toBe("console");
    expect(urls).toEqual([`${API}/admin/analytics?period=2026-W41`]);
  });

  it("dials nothing without a bearer, and paints a refusal as a refusal", async () => {
    const none = recorded(200, live());
    const refused = await loadAnalytics({
      config: opsConfigFromEnv({ INTAKE_ADMIN_API_BASE: API }),
      authorization: null,
      fetch: none.fetch,
      period: null,
    });
    expect(refused).toEqual({ kind: "not_admitted", reason: "no_credentials" });
    expect(none.urls).toEqual([]);

    const forbidden = recorded(403, { error: "role_not_permitted" });
    const state = await loadAnalytics({
      config: opsConfigFromEnv({ INTAKE_ADMIN_API_BASE: API }),
      authorization: BEARER,
      fetch: forbidden.fetch,
      period: null,
    });
    expect(state).toEqual({ kind: "not_admitted", reason: "role_not_permitted" });
    expect(html(state)).toContain(COPY.tr.refusals.role_not_permitted);
  });

  it("a payload the view-model refuses is unavailable, never half-painted", async () => {
    const { fetch } = recorded(200, { ...live(), k: 3 });
    const state = await loadAnalytics({
      config: opsConfigFromEnv({ INTAKE_ADMIN_API_BASE: API }),
      authorization: BEARER,
      fetch,
      period: null,
    });
    expect(state).toEqual({ kind: "unavailable", reason: "payload_refused" });
  });
});

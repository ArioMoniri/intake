/**
 * INT-190 — Cost module, console side (files/08 §3 "Cost", §4 J; INT-101, INT-180).
 *
 * Acceptance, verbatim: *"per-session cost by component/vendor/profile; budgets +
 * alerts"*.
 *
 * **What this runs against.** Two payloads, both the `GET /admin/cost` composite
 * produced by `intake_platform.cost.compose_cost_payload` and written by
 * `scripts/dev/record_cost_fixture.py`; `tests/admin/test_cost_module.py` fails
 * the Python lane the moment either file and the module disagree.
 *
 * - `cost.payload.json` is the committed state: `infra/costs/unit-prices.yaml`
 *   with every price and every budget empty (HB-O8), and no Prometheus source
 *   configured for the console. Nothing on it may carry money.
 * - `cost.priced.payload.json` is the same module over a TEST-ONLY price file
 *   (`tests/fixtures/cost/unit-prices.priced.yaml`, synthetic rates) and the
 *   recorded metric responses in `tests/fixtures/cost/prometheus_responses.json`.
 *   It is the only place a figure appears, and it exists to prove the renderer
 *   paints what the module computed.
 *
 * Assertions are on the presentation tree the renderer returns, not a DOM — the
 * same node lane as the other admin-web modules.
 *
 * **The negative controls.** Every property the acceptance and the invariants
 * turn on is paired with a near-miss the renderer must refuse: a cost figure on
 * a component with no price (the invented zero), a figure where usage is not
 * observed, a partial total shown as a total, a budget declared kept on a lower
 * bound, a price with no source, a retired profile, an identifier that is not
 * id-shaped (invariant 6) and a currency the catalogue does not denominate in.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import {
  CostContentLeaked,
  CostFigureWithoutPrice,
  CostFigureWithoutUsage,
  CurrencyNotCatalogued,
  PartialTotalRendered,
  renderCostModule,
  UnknownCostProfile,
  UnknownCostState,
  UnsoundBudgetVerdict,
  UnsourcedPrice,
  type CostPayload,
  type CostPresentation,
  type WindowPresentation,
} from "../src/cost/module";

const FIXTURES = join(__dirname, "fixtures");

function load(name: string): CostPayload {
  return JSON.parse(readFileSync(join(FIXTURES, name), "utf8")) as CostPayload;
}

const committed = (): CostPayload => load("cost.payload.json");
const priced = (): CostPayload => load("cost.priced.payload.json");

/** The wire shape with every readonly removed, so a test can tamper with it. */
type Mutable<T> = T extends readonly (infer U)[]
  ? Mutable<U>[]
  : T extends object
    ? { -readonly [K in keyof T]: Mutable<T[K]> }
    : T;

type Wire = Mutable<CostPayload>;

/** A deep, mutable copy to tamper with. */
function tamper(payload: CostPayload): Wire {
  return JSON.parse(JSON.stringify(payload)) as Wire;
}

function dayWire(payload: Wire): Wire["windows"][number] {
  const window = payload.windows.find((w) => w.period === "day");
  expect(window).toBeDefined();
  return window!;
}

function budgetWire(payload: Wire, budgetId: string): Wire["budgets"][number] {
  const budget = payload.budgets.find((b) => b.budget_id === budgetId);
  expect(budget).toBeDefined();
  return budget!;
}

function day(view: CostPresentation): WindowPresentation {
  const window = view.windows.find((w) => w.period === "day");
  expect(window).toBeDefined();
  return window!;
}

/** Quantity and unit cross the boundary as one atom (invariant 22). */
const NBSP = String.fromCharCode(0xa0);

describe("the committed state — nothing is priced, nothing is invented", () => {
  it("shows every component as price not configured", () => {
    const view = renderCostModule(committed());
    expect(view.components.length).toBeGreaterThan(0);
    for (const component of view.components) {
      expect(component.priceConfigured).toBe(false);
      expect(component.price).toBe("price not configured");
    }
  });

  it("carries no money anywhere on the page", () => {
    const view = renderCostModule(committed());
    const painted = JSON.stringify(view);
    expect(painted).not.toMatch(new RegExp(`\\d${NBSP}USD`));
    for (const window of view.windows) {
      for (const row of window.perSession) {
        expect(row.hasFigure).toBe(false);
      }
      for (const total of [...window.byProfile, ...window.byVendor]) {
        expect(total.complete).toBe(false);
      }
    }
  });

  it("states that the usage source is not configured rather than showing zeros", () => {
    const view = renderCostModule(committed());
    expect(view.source.configured).toBe(false);
    expect(view.source.text).toContain("not configured");
  });

  it("renders every budget as not configured, each with its alert", () => {
    const view = renderCostModule(committed());
    expect(view.budgets.length).toBeGreaterThan(0);
    for (const budget of view.budgets) {
      expect(budget.status).toBe("not_configured");
      expect(budget.limit).toBe("budget not configured");
      expect(budget.alerts).toContain("CostBudgetNotConfigured");
    }
  });

  it("names the owner-filled file and the blocker that keeps it empty", () => {
    const view = renderCostModule(committed());
    expect(view.config.path).toBe("infra/costs/unit-prices.yaml");
    expect(view.config.blocker).toBe("HB-O8");
    expect(view.config.sha256_prefix).toMatch(/^[0-9a-f]{32}$/);
  });
});

describe("per-session cost by component / vendor / profile", () => {
  it("paints a priced, observed component as one quantity-and-unit atom and one money atom", () => {
    const row = day(renderCostModule(priced())).perSession.find(
      (r) => r.component === "tts_dynamic" && r.profile === "residency_tr",
    );
    expect(row).toBeDefined();
    expect(row!.hasFigure).toBe(true);
    expect(row!.cost).toBe(`2400${NBSP}USD`);
    expect(row!.quantity).toBe(`1200${NBSP}characters`);
    expect(row!.vendor).toBe("self-hosted");
  });

  it("has a row per component per profile it spends in, and none for the others", () => {
    const rows = day(renderCostModule(priced())).perSession;
    const typed = rows.filter((r) => r.profile === "typed").map((r) => r.component);
    expect(typed).not.toContain("tts_dynamic");
    expect(typed).not.toContain("asr");
    expect(typed).toContain("llm_extraction");
    const profiles = new Set(rows.map((r) => r.profile));
    expect([...profiles].sort()).toEqual(["residency_tr", "typed"]);
  });

  it("shows price not configured for an unpriced component whose usage is known", () => {
    const sms = day(renderCostModule(priced())).perSession.find(
      (r) => r.component === "sms" && r.profile === "typed",
    );
    expect(sms).toBeDefined();
    expect(sms!.quantity).toBe(`0.5${NBSP}messages`);
    expect(sms!.hasFigure).toBe(false);
    expect(sms!.cost).toBe("price not configured");
    expect(sms!.vendor).toBe("vendor not configured");
  });

  it("names why an unmetered component has no figure", () => {
    const asr = day(renderCostModule(priced())).perSession.find(
      (r) => r.component === "asr" && r.profile === "residency_tr",
    );
    expect(asr!.hasFigure).toBe(false);
    expect(asr!.cost).toBe("unknown");
    expect(asr!.reasons.join(" ")).toContain("voice_stt_audio_s");
  });

  it("withholds a profile total that would be partial, and says what is missing", () => {
    const total = day(renderCostModule(priced())).byProfile.find(
      (p) => p.profile === "residency_tr",
    );
    expect(total!.complete).toBe(false);
    expect(total!.cost).toContain("withheld");
    expect(total!.missing).toContain("asr");
  });

  it("rolls up by vendor per profile, with unassigned components under no vendor", () => {
    const byVendor = day(renderCostModule(priced())).byVendor;
    expect(byVendor.some((v) => v.vendor === "self-hosted" && v.profile === "residency_tr")).toBe(
      true,
    );
    expect(byVendor.some((v) => v.vendor === "vendor not configured")).toBe(true);
  });

  it("paints a complete total when every component is known", () => {
    const payload = tamper(priced());
    dayWire(payload).by_profile[0] = {
      profile: "residency_tr",
      state: "complete",
      usd_per_session: 12.5,
      missing: [],
    };
    const total = day(renderCostModule(payload)).byProfile[0]!;
    expect(total.complete).toBe(true);
    expect(total.cost).toBe(`12.5${NBSP}USD`);
  });
});

describe("budgets", () => {
  it("marks a lower bound over the limit as exceeded, and says it is a bound", () => {
    const budget = renderCostModule(priced()).budgets.find((b) => b.budgetId === "self-hosted-day");
    expect(budget!.status).toBe("exceeded");
    expect(budget!.spend).toBe(`at least 96000${NBSP}USD`);
    expect(budget!.limit).toContain(`50000${NBSP}USD`);
    expect(budget!.alerts).toContain("CostBudgetExceeded");
  });

  it("refuses to call a budget kept on a lower bound under the limit", () => {
    const budget = renderCostModule(priced()).budgets.find(
      (b) => b.budgetId === "self-hosted-month",
    );
    expect(budget!.status).toBe("not_evaluable");
    expect(budget!.statusText).toContain("cannot be evaluated");
    expect(budget!.alerts).toContain("CostBudgetIncomplete");
  });

  it("shows unknown spend as unknown, never as zero", () => {
    const budget = renderCostModule(priced()).budgets.find(
      (b) => b.budgetId === "elevenlabs-month",
    );
    expect(budget!.spend).toBe("unknown");
    expect(budget!.status).toBe("not_evaluable");
  });

  it("paints a kept budget only over a complete spend", () => {
    const payload = tamper(priced());
    Object.assign(budgetWire(payload, "self-hosted-day"), {
      spend_state: "complete",
      spend_usd: 10,
      status: "within",
      missing: [],
    });
    const view = renderCostModule(payload).budgets.find((b) => b.budgetId === "self-hosted-day");
    expect(view!.status).toBe("within");
    expect(view!.spend).toBe(`10${NBSP}USD`);
    expect(view!.statusText).toBe("within budget");
  });
});

describe("alerts", () => {
  it("lists the generated rule file and a rule for every budget", () => {
    const view = renderCostModule(priced());
    expect(view.alerts.rulesPath).toBe("infra/observability/cost-rules.yaml");
    for (const budget of view.budgets) {
      expect(budget.alerts.length).toBeGreaterThan(0);
    }
  });
});

describe("negative controls — what a tampered or drifted body cannot buy", () => {
  it("refuses a cost figure on a component with no price (the invented zero)", () => {
    const payload = tamper(committed());
    dayWire(payload).per_session[0]!.usd_per_session = 0;
    expect(() => renderCostModule(payload)).toThrow(CostFigureWithoutPrice);
  });

  it("refuses a cost figure where usage was not observed", () => {
    const payload = tamper(priced());
    dayWire(payload).per_session.find((r) => r.component === "asr")!.usd_per_session = 1;
    expect(() => renderCostModule(payload)).toThrow(CostFigureWithoutUsage);
  });

  it("refuses a partial total presented as the total", () => {
    const payload = tamper(priced());
    dayWire(payload).by_profile[0]!.usd_per_session = 2400;
    expect(() => renderCostModule(payload)).toThrow(PartialTotalRendered);
  });

  it("refuses a kept budget on a lower bound", () => {
    const payload = tamper(priced());
    budgetWire(payload, "self-hosted-month").status = "within";
    expect(() => renderCostModule(payload)).toThrow(UnsoundBudgetVerdict);
  });

  it("refuses a budget verdict with no limit configured", () => {
    const payload = tamper(committed());
    payload.budgets[0]!.status = "exceeded";
    expect(() => renderCostModule(payload)).toThrow(UnsoundBudgetVerdict);
  });

  it("refuses a price with no source", () => {
    const payload = tamper(priced());
    payload.components.find((c) => c.component === "tts_dynamic")!.price.source = null;
    expect(() => renderCostModule(payload)).toThrow(UnsourcedPrice);
  });

  it("refuses a retired profile (invariant 19)", () => {
    const payload = tamper(priced());
    dayWire(payload).per_session[0]!.profile = "s2s" + "_cloud";
    expect(() => renderCostModule(payload)).toThrow(UnknownCostProfile);
  });

  it("refuses an identifier that is not id-shaped (invariant 6)", () => {
    const payload = tamper(priced());
    payload.components[0]!.vendor = "Dr. Demir's clinic";
    expect(() => renderCostModule(payload)).toThrow(CostContentLeaked);
  });

  it("refuses a state outside the sealed vocabulary", () => {
    const payload = tamper(priced());
    dayWire(payload).per_session[0]!.usage_state = "estimated";
    expect(() => renderCostModule(payload)).toThrow(UnknownCostState);
  });

  it("refuses a currency the catalogue does not denominate cost in", () => {
    const payload = tamper(priced());
    payload.currency = "TRY";
    expect(() => renderCostModule(payload)).toThrow(CurrencyNotCatalogued);
  });

  it("near miss: the untampered payloads both render", () => {
    expect(() => renderCostModule(committed())).not.toThrow();
    expect(() => renderCostModule(priced())).not.toThrow();
  });
});

/**
 * Cost module — the console side (INT-190; files/08 §3 "Cost", §4 J; INT-101,
 * INT-180).
 *
 * Acceptance, verbatim: *"per-session cost by component/vendor/profile; budgets +
 * alerts"*.
 *
 * Like the other admin-web modules this is a pure projection: it turns the
 * `GET /admin/cost` composite (`intake_platform.cost.compose_cost_payload`) into
 * exactly what the page paints, opens no socket and decides nothing the server
 * did not already decide. What it adds is a set of refusals, because the one
 * failure a cost page must never have is a number nobody supplied:
 *
 * - **No figure without a price.** A component whose price is not configured
 *   renders "price not configured". A cost figure on such a row — a zero
 *   included, since zero is the claim that something was free — is refused
 *   (`CostFigureWithoutPrice`), and so is a figure where the usage was not
 *   observed (`CostFigureWithoutUsage`). A price shown without the source and
 *   date it came from is refused too (`UnsourcedPrice`): the owner-filled file
 *   `infra/costs/unit-prices.yaml` is the only source of money (HB-O8).
 * - **No partial total.** A per-vendor or per-profile total with a missing part
 *   is withheld, not summed over what is known (`PartialTotalRendered`).
 * - **No budget kept on a bound.** A lower bound on the spend can prove a
 *   budget exceeded and can never prove it kept; "within" requires a complete
 *   spend and a configured limit (`UnsoundBudgetVerdict`).
 * - **Ids only (invariant 6), two profiles only (invariant 19), one currency.**
 *   Component, vendor and budget ids must be id-shaped (`CostContentLeaked`),
 *   profiles are the closed pair (`UnknownCostProfile`), every state is from a
 *   sealed vocabulary (`UnknownCostState`) and the currency is the catalogue's
 *   (`CurrencyNotCatalogued`).
 *
 * Per-session cost is a mean over the sessions metered in a window, so no
 * session identifier exists anywhere in the payload. Every quantity and every
 * amount is rendered with `useGrouping: false` and joined to its unit by a
 * non-breaking space, so number and unit cross the boundary as one atom
 * (invariant 22). No figure here is a measurement of the product (invariant 20).
 */

import {
  CostContentLeaked,
  CostFigureWithoutPrice,
  CostFigureWithoutUsage,
  CurrencyNotCatalogued,
  PartialTotalRendered,
  UnknownCostProfile,
  UnknownCostState,
  UnsoundBudgetVerdict,
  UnsourcedPrice,
} from "./refusals";
import { renderSpendCap } from "./spendCap";
import {
  PROFILES,
  type BudgetPresentation,
  type BudgetWire,
  type ComponentPresentation,
  type ComponentWire,
  type CostPayload,
  type CostPresentation,
  type PerSessionRowPresentation,
  type PerSessionWire,
  type SpendPresentation,
  type SpendWire,
  type TotalPresentation,
  type TotalWire,
  type WindowPresentation,
  type WindowWire,
} from "./types";

export * from "./refusals";
export * from "./spendCap";
export * from "./types";

/* ------------------------------------------------------------------ */
/* Vocabularies                                                        */
/* ------------------------------------------------------------------ */

const USAGE_STATES = [
  "observed",
  "no_samples",
  "not_emitted",
  "not_metered",
  "source_unavailable",
  "source_error",
] as const;
const PRICE_STATES = ["configured", "not_configured"] as const;
const TOTAL_STATES = ["complete", "incomplete"] as const;
const SPEND_STATES = ["complete", "lower_bound", "unknown"] as const;
const BUDGET_STATUSES = ["within", "exceeded", "not_evaluable", "not_configured"] as const;
const ATTRIBUTIONS = ["direct", "allocated"] as const;
const CURRENCY = "USD";
const ID = /^[a-z0-9][a-z0-9_.-]{0,63}$/;
const NBSP = String.fromCharCode(0xa0);

export const PRICE_NOT_CONFIGURED = "price not configured";
export const BUDGET_NOT_CONFIGURED = "budget not configured";
export const VENDOR_NOT_CONFIGURED = "vendor not configured";

const UNIT_LABEL: Readonly<Record<string, string>> = {
  audio_second: "audio seconds",
  character: "characters",
  token: "tokens",
  message: "messages",
  clip: "clips",
  host_hour: "host hours",
};

function sealed(field: string, value: string, allowed: readonly string[]): string {
  if (!allowed.includes(value)) {
    throw new UnknownCostState(field, value);
  }
  return value;
}

function id(field: string, value: string): string {
  if (!ID.test(value)) {
    throw new CostContentLeaked(field);
  }
  return value;
}

function vendorLabel(vendor: string | null): string {
  return vendor === null ? VENDOR_NOT_CONFIGURED : id("a vendor id", vendor);
}

function profile(value: string): string {
  if (!(PROFILES as readonly string[]).includes(value)) {
    throw new UnknownCostProfile(value);
  }
  return value;
}

function unitLabel(unit: string): string {
  const label = UNIT_LABEL[unit];
  if (label === undefined) {
    throw new UnknownCostState("unit", unit);
  }
  return label;
}

/** A number as one atom with its unit: no grouping separator, a non-breaking space. */
function atom(value: number, unit: string, maximumFractionDigits: number): string {
  const text = value.toLocaleString("en-GB", { useGrouping: false, maximumFractionDigits });
  return `${text}${NBSP}${unit}`;
}

function usd(value: number): string {
  return atom(value, CURRENCY, 6);
}

/**
 * A unit price (INT-439). A list price per token is 1.5e-7 USD, which six
 * fraction digits would paint as "0" — the invented zero this module refuses
 * everywhere else. Significant digits keep every published figure visible.
 */
function usdRate(value: number): string {
  const text = value.toLocaleString("en-GB", {
    useGrouping: false,
    maximumSignificantDigits: 6,
  });
  return `${text}${NBSP}${CURRENCY}`;
}

/* ------------------------------------------------------------------ */
/* Renderers                                                           */
/* ------------------------------------------------------------------ */

/** The provenance suffix of a configured value, or null for an empty one. */
function sourced(
  where: string,
  value: number | null,
  source: string | null,
  asOf: string | null,
): string | null {
  if (value === null) {
    return null;
  }
  if (!source || !source.trim() || !asOf) {
    throw new UnsourcedPrice(where);
  }
  return `— ${source}, as of ${asOf}`;
}

function renderComponent(wire: ComponentWire): ComponentPresentation {
  const component = id("a component id", wire.component);
  const state = sealed("price state", wire.price.state, PRICE_STATES);
  const configured = state === "configured";
  if (configured !== (wire.price.usd_per_unit !== null)) {
    throw new UnsourcedPrice(`component ${component}`);
  }
  const provenance = sourced(
    `component ${component}`,
    wire.price.usd_per_unit,
    wire.price.source,
    wire.price.as_of,
  );
  const unit = unitLabel(wire.unit);
  const url = wire.price.url ?? null;
  if (url !== null && (wire.price.usd_per_unit === null || !/^https:\/\/\S+$/.test(url))) {
    throw new UnsourcedPrice(`component ${component}`);
  }
  const page = url === null ? "" : ` (${url})`;
  const price =
    wire.price.usd_per_unit === null
      ? PRICE_NOT_CONFIGURED
      : `${usdRate(wire.price.usd_per_unit)} per ${unit.replace(/s$/, "")} ${provenance}${page}`;
  const usage =
    wire.usage_metric === null
      ? `not metered — ${wire.usage_note ?? ""}`.trim()
      : `${id("a usage series", wire.usage_metric)} (${sealed(
          "usage series status",
          wire.usage_metric_status ?? "",
          ["live", "planned"],
        )})`;
  return {
    component,
    vendor: vendorLabel(wire.vendor),
    unit,
    attribution: sealed("attribution", wire.attribution, ATTRIBUTIONS),
    usage,
    priceConfigured: configured,
    price,
  };
}

function renderPerSession(wire: PerSessionWire): PerSessionRowPresentation {
  const component = id("a component id", wire.component);
  const where = `${component} (${profile(wire.profile)})`;
  const usageState = sealed("usage state", wire.usage_state, USAGE_STATES);
  const priceState = sealed("price state", wire.price_state, PRICE_STATES);
  if (wire.usd_per_session !== null) {
    if (priceState !== "configured") {
      throw new CostFigureWithoutPrice(where);
    }
    if (usageState !== "observed") {
      throw new CostFigureWithoutUsage(where, usageState);
    }
  }
  const cost =
    wire.usd_per_session !== null
      ? usd(wire.usd_per_session)
      : priceState === "not_configured"
        ? PRICE_NOT_CONFIGURED
        : "unknown";
  return {
    component,
    vendor: vendorLabel(wire.vendor),
    profile: wire.profile,
    attribution: sealed("attribution", wire.attribution, ATTRIBUTIONS),
    quantity:
      wire.quantity_per_session === null
        ? null
        : atom(wire.quantity_per_session, unitLabel(wire.unit), 3),
    hasFigure: wire.usd_per_session !== null,
    cost,
    reasons: wire.reasons,
  };
}

function renderTotal(wire: TotalWire, where: string): TotalPresentation {
  const state = sealed("total state", wire.state, TOTAL_STATES);
  const complete = state === "complete" && wire.missing.length === 0;
  if (!complete && wire.usd_per_session !== null) {
    throw new PartialTotalRendered(where);
  }
  if (complete && wire.usd_per_session === null) {
    throw new PartialTotalRendered(where);
  }
  return {
    vendor: wire.vendor === undefined ? null : vendorLabel(wire.vendor),
    profile: profile(wire.profile),
    complete,
    cost:
      wire.usd_per_session !== null
        ? usd(wire.usd_per_session)
        : `withheld — incomplete: ${wire.missing.map((c) => id("a component id", c)).join(", ")}`,
    missing: wire.missing,
  };
}

function renderSpend(wire: SpendWire): SpendPresentation {
  const component = id("a component id", wire.component);
  const usageState = sealed("usage state", wire.usage_state, USAGE_STATES);
  const priceState = sealed("price state", wire.price_state, PRICE_STATES);
  if (wire.usd !== null) {
    if (priceState !== "configured") {
      throw new CostFigureWithoutPrice(`${component} spend`);
    }
    if (usageState !== "observed") {
      throw new CostFigureWithoutUsage(`${component} spend`, usageState);
    }
  }
  return {
    component,
    vendor: vendorLabel(wire.vendor),
    quantity: wire.quantity === null ? null : atom(wire.quantity, unitLabel(wire.unit), 3),
    cost:
      wire.usd !== null
        ? usd(wire.usd)
        : priceState === "not_configured"
          ? PRICE_NOT_CONFIGURED
          : "unknown",
  };
}

function renderWindow(wire: WindowWire): WindowPresentation {
  const period = sealed("period", wire.period, ["day", "month"]);
  const sessionsState = sealed("session count state", wire.sessions.state, USAGE_STATES);
  return {
    period,
    window: wire.window,
    sessions: {
      state: sessionsState,
      byProfile: PROFILES.map((p) => {
        const count = wire.sessions.by_profile[p];
        return { profile: p, count: count == null ? null : atom(count, "sessions", 0) };
      }),
      note: wire.sessions.reason,
    },
    perSession: wire.per_session.map(renderPerSession),
    byVendor: wire.by_vendor.map((t) =>
      renderTotal(t, `vendor ${t.vendor ?? "unassigned"} (${t.profile}), ${period}`),
    ),
    byProfile: wire.by_profile.map((t) => renderTotal(t, `profile ${t.profile}, ${period}`)),
    spend: wire.spend.map(renderSpend),
  };
}

const STATUS_TEXT: Readonly<Record<string, string>> = {
  within: "within budget",
  exceeded: "budget exceeded",
  not_configured: BUDGET_NOT_CONFIGURED,
};

function renderBudget(wire: BudgetWire): BudgetPresentation {
  const budgetId = id("a budget id", wire.budget_id);
  const status = sealed("budget status", wire.status, BUDGET_STATUSES);
  const spendState = sealed("spend state", wire.spend_state, SPEND_STATES);
  const limitState = sealed("limit state", wire.limit.state, PRICE_STATES);
  if ((limitState === "configured") !== (wire.limit.usd !== null)) {
    throw new UnsourcedPrice(`budget ${budgetId}`);
  }
  const provenance = sourced(
    `budget ${budgetId}`,
    wire.limit.usd,
    wire.limit.source,
    wire.limit.as_of,
  );
  const limit = wire.limit.usd;

  if (limit === null && status !== "not_configured") {
    throw new UnsoundBudgetVerdict(budgetId, `status '${status}' with no limit configured`);
  }
  if (limit !== null && status === "not_configured") {
    throw new UnsoundBudgetVerdict(budgetId, "a configured limit rendered as not configured");
  }
  if (spendState === "unknown" && wire.spend_usd !== null) {
    throw new UnsoundBudgetVerdict(budgetId, "a spend figure where the spend is unknown");
  }
  if (spendState !== "unknown" && wire.spend_usd === null) {
    throw new UnsoundBudgetVerdict(budgetId, "a known spend with no figure");
  }
  if (spendState === "complete" && wire.missing.length > 0) {
    throw new UnsoundBudgetVerdict(budgetId, "a complete spend with missing components");
  }
  if (
    status === "within" &&
    (spendState !== "complete" || limit === null || (wire.spend_usd ?? limit + 1) > limit)
  ) {
    throw new UnsoundBudgetVerdict(budgetId, "'within' on a spend that is not complete");
  }
  if (
    status === "exceeded" &&
    (wire.spend_usd === null || limit === null || wire.spend_usd <= limit)
  ) {
    throw new UnsoundBudgetVerdict(budgetId, "'exceeded' on a spend that is not above the limit");
  }

  const spend =
    wire.spend_usd === null
      ? "unknown"
      : spendState === "lower_bound"
        ? `at least ${usd(wire.spend_usd)}`
        : usd(wire.spend_usd);
  const missing = wire.missing.map((c) => id("a component id", c));
  return {
    budgetId,
    scope: wire.vendor === null ? "all vendors" : id("a vendor id", wire.vendor),
    period: sealed("period", wire.period, ["day", "month"]),
    limit: limit === null ? BUDGET_NOT_CONFIGURED : `${usd(limit)} ${provenance}`,
    spend,
    status,
    statusText:
      STATUS_TEXT[status] ?? `cannot be evaluated: no spend is known for ${missing.join(", ")}`,
    missing,
    alerts: wire.alerts,
  };
}

/**
 * Build the page from the served payload.
 *
 * @throws the refusal named for the first property the payload violates — a
 * figure without a price or without observed usage, a partial total, an
 * unsound budget verdict, an unsourced value, a retired profile, a non-id
 * identifier, a state off its vocabulary, or a foreign currency.
 */
export function renderCostModule(payload: CostPayload): CostPresentation {
  if (payload.currency !== CURRENCY) {
    throw new CurrencyNotCatalogued(payload.currency);
  }
  return {
    currency: CURRENCY,
    config: payload.config,
    source: {
      configured: payload.source.configured,
      text: payload.source.configured
        ? payload.source.reason
        : `usage source not configured — ${payload.source.reason}`,
    },
    allocationRule: payload.allocation_rule,
    components: payload.components.map(renderComponent),
    windows: payload.windows.map(renderWindow),
    budgets: payload.budgets.map(renderBudget),
    spendCaps: (payload.spend_caps ?? []).map((cap) => renderSpendCap(cap, usd, id)),
    alerts: {
      rulesPath: payload.alerts.rules_path,
      rules: payload.alerts.rules.map((rule) => ({
        alert: rule.alert,
        budgetId: id("a budget id", rule.budget_id),
      })),
    },
  };
}

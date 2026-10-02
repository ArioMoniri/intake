/**
 * Cost module wire contract and presentation tree (INT-190).
 *
 * The recorded shape of `GET /admin/cost` (`intake_platform.cost.compose_cost_payload`)
 * and the tree `renderCostModule` returns. See `./module.ts` for what the renderer
 * refuses and why.
 */

/** The two voice profiles (CLAUDE.md invariant 19). */
export const PROFILES = ["residency_tr", "typed"] as const;

/* ------------------------------------------------------------------ */
/* Wire contract — the recorded shape of GET /admin/cost               */
/* ------------------------------------------------------------------ */

export interface PriceWire {
  readonly state: string;
  readonly usd_per_unit: number | null;
  readonly source: string | null;
  readonly as_of: string | null;
  /** INT-439: the published price page, when the rate is a list price. */
  readonly url?: string | null;
}

export interface ComponentWire {
  readonly component: string;
  /** null when no vendor has been chosen; `vendor_note` says why. */
  readonly vendor: string | null;
  readonly vendor_note: string | null;
  readonly unit: string;
  /** direct (spent by a profile) | allocated (split across all sessions). */
  readonly attribution: string;
  readonly profiles: readonly string[];
  /** The catalogued usage series, or null when nothing meters the component. */
  readonly usage_metric: string | null;
  readonly usage_metric_status: string | null;
  readonly usage_note: string | null;
  readonly price: PriceWire;
}

export interface PerSessionWire {
  readonly component: string;
  readonly vendor: string | null;
  readonly profile: string;
  readonly attribution: string;
  readonly unit: string;
  readonly usage_state: string;
  readonly price_state: string;
  readonly quantity_per_session: number | null;
  readonly usd_per_session: number | null;
  readonly reasons: readonly string[];
}

export interface TotalWire {
  readonly vendor?: string | null;
  readonly profile: string;
  readonly state: string;
  readonly usd_per_session: number | null;
  readonly missing: readonly string[];
}

export interface SpendWire {
  readonly component: string;
  readonly vendor: string | null;
  readonly unit: string;
  readonly usage_state: string;
  readonly price_state: string;
  readonly quantity: number | null;
  readonly usd: number | null;
  readonly reasons: readonly string[];
}

export interface SessionsWire {
  readonly state: string;
  readonly reason: string | null;
  readonly by_profile: Readonly<Record<string, number | null>>;
}

export interface WindowWire {
  readonly period: string;
  readonly window: string;
  readonly sessions: SessionsWire;
  readonly per_session: readonly PerSessionWire[];
  readonly by_vendor: readonly TotalWire[];
  readonly by_profile: readonly TotalWire[];
  readonly spend: readonly SpendWire[];
}

export interface LimitWire {
  readonly state: string;
  readonly usd: number | null;
  readonly source: string | null;
  readonly as_of: string | null;
}

export interface BudgetWire {
  readonly budget_id: string;
  readonly scope: string;
  readonly vendor: string | null;
  readonly period: string;
  readonly window: string;
  readonly limit: LimitWire;
  readonly spend_state: string;
  readonly spend_usd: number | null;
  readonly status: string;
  readonly missing: readonly string[];
  readonly reason: string;
  readonly alerts: readonly string[];
}

/** INT-439 / D19: the monthly elective model-spend cap. */
export interface SpendCapWire {
  readonly cap_id: string;
  readonly covers: string;
  readonly period: string;
  readonly limit: { readonly usd: number; readonly source: string; readonly as_of: string };
  readonly warn_ratio: number;
  readonly warn_at_usd: number;
  readonly spend_metric: string;
  readonly spend_usd: number | null;
  readonly status: string;
  readonly reason: string;
  readonly alerts: readonly string[];
}

export interface AlertRuleWire {
  readonly alert: string;
  readonly budget_id: string;
  readonly severity: string;
}

export interface CostPayload {
  readonly currency: string;
  readonly config: { readonly path: string; readonly sha256: string; readonly blocker: string };
  readonly source: { readonly configured: boolean; readonly reason: string };
  readonly sessions_metric: string;
  readonly allocation_rule: string;
  readonly components: readonly ComponentWire[];
  readonly windows: readonly WindowWire[];
  readonly budgets: readonly BudgetWire[];
  readonly spend_caps?: readonly SpendCapWire[];
  readonly alerts: { readonly rules_path: string; readonly rules: readonly AlertRuleWire[] };
}

/* ------------------------------------------------------------------ */
/* Presentation tree — what the page paints                            */
/* ------------------------------------------------------------------ */

export interface ComponentPresentation {
  readonly component: string;
  readonly vendor: string;
  readonly unit: string;
  readonly attribution: string;
  readonly usage: string;
  readonly priceConfigured: boolean;
  /** "price not configured", or the rate with its source and date. */
  readonly price: string;
}

export interface PerSessionRowPresentation {
  readonly component: string;
  readonly vendor: string;
  readonly profile: string;
  readonly attribution: string;
  /** The per-session quantity as one atom, or null when it is not known. */
  readonly quantity: string | null;
  readonly hasFigure: boolean;
  /** A money atom, "price not configured", or "unknown". Never a bare 0. */
  readonly cost: string;
  readonly reasons: readonly string[];
}

export interface TotalPresentation {
  readonly vendor: string | null;
  readonly profile: string;
  readonly complete: boolean;
  readonly cost: string;
  readonly missing: readonly string[];
}

export interface SpendPresentation {
  readonly component: string;
  readonly vendor: string;
  readonly quantity: string | null;
  readonly cost: string;
}

export interface WindowPresentation {
  readonly period: string;
  readonly window: string;
  readonly sessions: {
    readonly state: string;
    readonly byProfile: readonly { readonly profile: string; readonly count: string | null }[];
    readonly note: string | null;
  };
  readonly perSession: readonly PerSessionRowPresentation[];
  readonly byVendor: readonly TotalPresentation[];
  readonly byProfile: readonly TotalPresentation[];
  readonly spend: readonly SpendPresentation[];
}

export interface BudgetPresentation {
  readonly budgetId: string;
  readonly scope: string;
  readonly period: string;
  readonly limit: string;
  readonly spend: string;
  readonly status: string;
  readonly statusText: string;
  readonly missing: readonly string[];
  readonly alerts: readonly string[];
}

export interface SpendCapPresentation {
  readonly capId: string;
  readonly covers: string;
  readonly period: string;
  readonly limit: string;
  readonly warnAt: string;
  readonly spend: string;
  readonly status: string;
  readonly statusText: string;
  readonly alerts: readonly string[];
}

export interface CostPresentation {
  readonly currency: string;
  readonly config: { readonly path: string; readonly sha256: string; readonly blocker: string };
  readonly source: { readonly configured: boolean; readonly text: string };
  readonly allocationRule: string;
  readonly components: readonly ComponentPresentation[];
  readonly windows: readonly WindowPresentation[];
  readonly budgets: readonly BudgetPresentation[];
  readonly spendCaps: readonly SpendCapPresentation[];
  readonly alerts: {
    readonly rulesPath: string;
    readonly rules: readonly { readonly alert: string; readonly budgetId: string }[];
  };
}

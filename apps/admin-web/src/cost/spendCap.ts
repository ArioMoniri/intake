/**
 * INT-439 — the monthly elective model-spend cap on the cost module (00_STATE §3 D19).
 *
 * Owner decision, 3 Oct 2026: "make limit 80 dollars". The served row carries the
 * cap, where it warns (80 %), the month-to-date spend from `model_spend_month_usd`
 * and a verdict. The renderer refuses any verdict the figures cannot support: a
 * spend shown where none was read, "within" above the warning point, "reached"
 * below the limit, or a limit with no source and date. An unknown spend is
 * "unknown", never "0 of 80".
 */

import { UnknownCostState, UnsoundBudgetVerdict, UnsourcedPrice } from "./refusals";
import type { SpendCapPresentation, SpendCapWire } from "./types";

const CAP_STATUSES = ["within", "warning", "reached", "not_evaluable"] as const;

const STATUS_TEXT: Readonly<Record<string, string>> = {
  within: "below the warning point",
  warning: "past the warning point — elective model work still runs",
  reached: "cap reached — elective model work is refused until the month ends",
  not_evaluable: "cannot be evaluated: the month's spend is unknown",
};

/** Formatting is injected so the cap paints money exactly as the module does. */
export type UsdFormat = (value: number) => string;

export function renderSpendCap(
  wire: SpendCapWire,
  usd: UsdFormat,
  id: (field: string, value: string) => string,
): SpendCapPresentation {
  const capId = id("a spend cap id", wire.cap_id);
  if (!(CAP_STATUSES as readonly string[]).includes(wire.status)) {
    throw new UnknownCostState("spend cap status", wire.status);
  }
  if (!wire.limit.source.trim() || !wire.limit.as_of) {
    throw new UnsourcedPrice(`spend cap ${capId}`);
  }
  const limit = wire.limit.usd;
  const warnAt = wire.warn_at_usd;
  if (!(wire.warn_ratio > 0 && wire.warn_ratio < 1) || !(limit > 0)) {
    throw new UnsoundBudgetVerdict(capId, "a cap needs a positive limit and a ratio inside (0, 1)");
  }
  if (Math.abs(warnAt - limit * wire.warn_ratio) > 1e-9 * limit) {
    throw new UnsoundBudgetVerdict(capId, "the warning point is not the ratio of the limit");
  }
  const spend = wire.spend_usd;
  if ((wire.status === "not_evaluable") !== (spend === null)) {
    throw new UnsoundBudgetVerdict(capId, "a verdict and a spend figure that disagree");
  }
  if (spend !== null) {
    const expected = spend >= limit ? "reached" : spend >= warnAt ? "warning" : "within";
    if (wire.status !== expected) {
      throw new UnsoundBudgetVerdict(capId, `'${wire.status}' on a spend that reads '${expected}'`);
    }
  }
  return {
    capId,
    covers: id("what a cap covers", wire.covers),
    period: wire.period === "calendar_month_utc" ? "calendar month (UTC)" : wire.period,
    limit: `${usd(limit)} — ${wire.limit.source}, as of ${wire.limit.as_of}`,
    warnAt: `${usd(warnAt)} (${Math.round(wire.warn_ratio * 100)} %)`,
    spend: spend === null ? "unknown" : usd(spend),
    status: wire.status,
    statusText: STATUS_TEXT[wire.status] ?? wire.status,
    alerts: wire.alerts,
  };
}

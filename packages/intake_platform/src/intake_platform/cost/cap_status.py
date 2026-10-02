"""INT-439 — the monthly spend cap on the admin cost module, and its two alerts.

The voice runtime counts every model call's USD against the calendar month in
``model_spend_month_usd`` (00_STATE §3 D19). This module turns that one series
into what an operator sees: the cap, where it warns, the month-to-date spend and
a verdict — plus the Prometheus rules that ticket at the warning ratio and at the
cap itself.

**Nothing unknown becomes a zero.** With no Prometheus source configured, the
spend is *unknown* and the verdict is ``not_evaluable``; it is never "0 of 80".
Every worker reports the same shared total, so the console reads ``max()``.
"""

from __future__ import annotations

import enum
from typing import Any, Final

from intake_platform.cost.caps import SpendCap
from intake_platform.cost.config import CostConfig
from intake_platform.cost.queries import QueryRefused, QueryRunner, parse_scalar, run_query

__all__ = [
    "ALERT_CAP_REACHED",
    "ALERT_CAP_WARNING",
    "CAP_GROUP_NAME",
    "SPEND_CAP_QUERY",
    "SPEND_METRIC",
    "CapStatus",
    "spend_cap_rows",
    "spend_cap_rules",
]

SPEND_METRIC: Final = "model_spend_month_usd"
SPEND_CAP_QUERY: Final = f"max({SPEND_METRIC})"
CAP_GROUP_NAME: Final = "model-spend-cap"
ALERT_CAP_WARNING: Final = "ModelSpendCapWarning"
ALERT_CAP_REACHED: Final = "ModelSpendCapReached"
_RUNBOOK: Final = "docs/runbooks/cost-budgets.md"
_ANCHOR: Final = {
    ALERT_CAP_WARNING: "spend-cap-warning",
    ALERT_CAP_REACHED: "spend-cap-reached",
}


class CapStatus(enum.StrEnum):
    WITHIN = "within"
    WARNING = "warning"
    REACHED = "reached"
    NOT_EVALUABLE = "not_evaluable"


def _read_spend(runner: QueryRunner | None) -> tuple[float | None, str | None]:
    if runner is None:
        return None, "usage source not configured"
    try:
        return parse_scalar(run_query(runner, SPEND_CAP_QUERY)), None
    except QueryRefused as refused:
        return None, f"source refused: {refused}"


def _row(cap: SpendCap, spend: float | None, why: str | None) -> dict[str, Any]:
    limit = float(cap.limit.usd)
    warn_at = float(cap.warn_at_usd)
    if spend is None:
        status = CapStatus.NOT_EVALUABLE
        reason = why or "no spend has been reported for the month"
    elif spend >= limit:
        status, reason = CapStatus.REACHED, "elective model work is refused until the month ends"
    elif spend >= warn_at:
        status, reason = CapStatus.WARNING, "the month's spend has passed the warning ratio"
    else:
        status, reason = CapStatus.WITHIN, "the month's spend is below the warning ratio"
    return {
        "cap_id": cap.cap_id,
        "covers": cap.covers,
        "period": cap.period.value,
        "limit": {
            "usd": limit,
            "source": cap.limit.source,
            "as_of": cap.limit.as_of.isoformat(),
        },
        "warn_ratio": float(cap.warn_ratio),
        "warn_at_usd": warn_at,
        "spend_metric": SPEND_METRIC,
        "spend_usd": spend,
        "status": status.value,
        "reason": reason,
        "alerts": [ALERT_CAP_WARNING, ALERT_CAP_REACHED],
    }


def spend_cap_rows(config: CostConfig, runner: QueryRunner | None) -> list[dict[str, Any]]:
    """One row per configured cap, for ``GET /admin/cost``."""
    if not config.spend_caps:
        return []
    spend, why = _read_spend(runner)
    return [_row(cap, spend, why) for cap in config.spend_caps]


def spend_cap_rules(config: CostConfig) -> list[dict[str, Any]]:
    """The warning and the reached alert per cap. Money, not a patient: a ticket."""
    rules: list[dict[str, Any]] = []
    for cap in config.spend_caps:
        labels = {
            "severity": "ticket",
            "budget_id": cap.cap_id,
            "scope": cap.covers,
            "period": cap.period.value,
        }
        limit, warn_at = float(cap.limit.usd), float(cap.warn_at_usd)
        rules.append(
            {
                "alert": ALERT_CAP_WARNING,
                "expr": f"{SPEND_CAP_QUERY} >= {warn_at!r} and {SPEND_CAP_QUERY} < {limit!r}",
                "labels": labels,
                "annotations": {
                    "summary": (
                        f"{cap.cap_id}: the month's model spend has passed "
                        f"{float(cap.warn_ratio):.0%} of {limit!r} USD"
                    ),
                    "runbook": f"{_RUNBOOK}#{_ANCHOR[ALERT_CAP_WARNING]}",
                },
            }
        )
        rules.append(
            {
                "alert": ALERT_CAP_REACHED,
                "expr": f"{SPEND_CAP_QUERY} >= {limit!r}",
                "labels": labels,
                "annotations": {
                    "summary": (
                        f"{cap.cap_id}: the month's model spend reached {limit!r} USD; "
                        "elective model work is refused until the month ends"
                    ),
                    "runbook": f"{_RUNBOOK}#{_ANCHOR[ALERT_CAP_REACHED]}",
                },
            }
        )
    return rules

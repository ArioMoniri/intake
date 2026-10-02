"""The ``GET /admin/cost`` composite the admin console renders (INT-190).

Acceptance, verbatim: *"per-session cost by component/vendor/profile; budgets +
alerts"*.

**Per-session cost** is, for each window, a component's usage over the window
divided by the sessions metered in the same window, times its price:

- a *direct* component (its usage series is labelled by profile) divides each
  profile's usage by that profile's sessions;
- an *allocated* component (no profile label: SMS, the clip build, a host)
  divides the window's total by every session metered in it, so each session
  carries an even share.

It is a mean per session, so no session identifier is ever needed or carried
(CLAUDE.md invariant 6).

**Nothing unknown becomes a zero.** A figure exists only when the price is
configured, the usage was observed and the divisor is a positive count;
otherwise the row carries ``None`` and the reasons, in order. A total — per
vendor, per profile, per budget — is shown only when every part of it is known;
a partial sum is withheld (per-session totals) or labelled a lower bound
(budget spend), which can prove a budget exceeded and can never prove it kept.

``runner`` is whatever answers PromQL instant queries; ``None`` is the honest
state of this repository — no Prometheus source is configured for the console —
and every quantity then reads *source unavailable*.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from intake_platform.cost.cap_status import spend_cap_rows
from intake_platform.cost.config import (
    PERIOD_WINDOW,
    BudgetScope,
    CostConfig,
    Period,
    Profile,
)
from intake_platform.cost.queries import (
    SESSIONS_METRIC,
    QueryRefused,
    QueryRunner,
    component_query,
    parse_by_profile,
    parse_scalar,
    run_query,
    sessions_query,
)
from intake_platform.cost.resolve import Attribution, ResolvedComponent, resolve_components
from intake_platform.cost.rules import RULES_PATH, budget_alert_names, cost_rule_groups
from intake_platform.slo import MetricsCatalog

__all__ = [
    "BudgetStatus",
    "PriceState",
    "SpendState",
    "TotalState",
    "UsageState",
    "compose_cost_payload",
]

#: files/HUMAN_BLOCKERS.md row that asks the owner for the rates and limits.
BLOCKER: Final = "HB-O8"
PRICE_NOT_CONFIGURED: Final = "price not configured"
_NO_SOURCE: Final = (
    "no Prometheus source is configured for the console, so no usage is read: every "
    "quantity is unavailable, not zero"
)
_ALLOCATION_RULE: Final = (
    "a component with no profile label is allocated evenly across every session metered "
    "in the window"
)


class UsageState(enum.StrEnum):
    OBSERVED = "observed"
    NO_SAMPLES = "no_samples"
    NOT_EMITTED = "not_emitted"
    NOT_METERED = "not_metered"
    SOURCE_UNAVAILABLE = "source_unavailable"
    SOURCE_ERROR = "source_error"


class PriceState(enum.StrEnum):
    CONFIGURED = "configured"
    NOT_CONFIGURED = "not_configured"


class TotalState(enum.StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


class SpendState(enum.StrEnum):
    COMPLETE = "complete"
    LOWER_BOUND = "lower_bound"
    UNKNOWN = "unknown"


class BudgetStatus(enum.StrEnum):
    WITHIN = "within"
    EXCEEDED = "exceeded"
    NOT_EVALUABLE = "not_evaluable"
    NOT_CONFIGURED = "not_configured"


@dataclass(frozen=True)
class _Reading:
    """One window's answer for one series: a state, and the numbers if observed."""

    state: UsageState
    reason: str | None = None
    by_profile: Mapping[Profile, float] = field(default_factory=dict)
    total: float | None = None


def _read_sessions(runner: QueryRunner | None, period: Period) -> _Reading:
    if runner is None:
        return _Reading(UsageState.SOURCE_UNAVAILABLE, _NO_SOURCE)
    try:
        by_profile = parse_by_profile(run_query(runner, sessions_query(period)))
    except QueryRefused as exc:
        return _Reading(UsageState.SOURCE_ERROR, f"the session count query was refused: {exc}")
    return _Reading(UsageState.OBSERVED, None, by_profile, sum(by_profile.values()))


def _read_usage(
    resolved: ResolvedComponent, runner: QueryRunner | None, period: Period
) -> _Reading:
    component = resolved.component
    usage = component.usage
    window = PERIOD_WINDOW[period]
    if usage is None:
        return _Reading(UsageState.NOT_METERED, f"usage not metered: {component.usage_note}")
    if resolved.catalog_status != "live":
        return _Reading(
            UsageState.NOT_EMITTED,
            f"usage series {usage.metric} is catalogued as planned and not emitted yet",
        )
    if runner is None:
        return _Reading(UsageState.SOURCE_UNAVAILABLE, _NO_SOURCE)
    try:
        samples = run_query(runner, component_query(resolved, period))
        if resolved.attribution is Attribution.DIRECT:
            by_profile = parse_by_profile(samples)
            total = sum(by_profile.values()) if by_profile else None
        else:
            by_profile, total = {}, parse_scalar(samples)
    except QueryRefused as exc:
        return _Reading(UsageState.SOURCE_ERROR, f"the usage query was refused: {exc}")
    if total is None:
        return _Reading(UsageState.NO_SAMPLES, f"no {usage.metric} samples in the last {window}")
    return _Reading(UsageState.OBSERVED, None, by_profile, total)


def _price_state(resolved: ResolvedComponent) -> PriceState:
    configured = resolved.component.price.usd_per_unit is not None
    return PriceState.CONFIGURED if configured else PriceState.NOT_CONFIGURED


def _per_session_row(
    resolved: ResolvedComponent,
    profile: Profile,
    usage: _Reading,
    sessions: _Reading,
    period: Period,
) -> dict[str, Any]:
    component = resolved.component
    window = PERIOD_WINDOW[period]
    direct = resolved.attribution is Attribution.DIRECT
    reasons: list[str] = []
    price_state = _price_state(resolved)
    if price_state is PriceState.NOT_CONFIGURED:
        reasons.append(PRICE_NOT_CONFIGURED)

    usage_state, quantity = usage.state, None
    if usage.state is UsageState.OBSERVED:
        quantity = usage.by_profile.get(profile) if direct else usage.total
        if quantity is None and component.usage is not None:
            usage_state = UsageState.NO_SAMPLES
            reasons.append(
                f"no {component.usage.metric} samples for {profile.value} in the last {window}"
            )
    else:
        reasons.append(usage.reason or usage.state.value)

    divisor: float | None = None
    if sessions.state is not UsageState.OBSERVED:
        if sessions.reason is not None and sessions.reason not in reasons:
            reasons.append(sessions.reason)
    else:
        divisor = sessions.by_profile.get(profile) if direct else sessions.total
        if not divisor:
            divisor = None
            whose = f"for {profile.value} " if direct else ""
            reasons.append(f"no metered sessions {whose}in the last {window}")

    per_session = quantity / divisor if quantity is not None and divisor is not None else None
    price = component.price.usd_per_unit
    usd = per_session * price if per_session is not None and price is not None else None
    return {
        "component": component.component,
        "vendor": component.vendor,
        "profile": profile.value,
        "attribution": resolved.attribution.value,
        "unit": component.unit.value,
        "usage_state": usage_state.value,
        "price_state": price_state.value,
        "quantity_per_session": per_session,
        "usd_per_session": usd,
        "reasons": reasons,
    }


def _total(rows: list[dict[str, Any]], **key: Any) -> dict[str, Any]:
    missing = [row["component"] for row in rows if row["usd_per_session"] is None]
    complete = not missing
    return {
        **key,
        "state": (TotalState.COMPLETE if complete else TotalState.INCOMPLETE).value,
        "usd_per_session": sum(row["usd_per_session"] for row in rows) if complete else None,
        "missing": missing,
    }


def _spend_row(resolved: ResolvedComponent, usage: _Reading) -> dict[str, Any]:
    component = resolved.component
    price = component.price.usd_per_unit
    quantity = usage.total if usage.state is UsageState.OBSERVED else None
    reasons = [] if price is not None else [PRICE_NOT_CONFIGURED]
    if usage.reason is not None:
        reasons.append(usage.reason)
    return {
        "component": component.component,
        "vendor": component.vendor,
        "unit": component.unit.value,
        "usage_state": usage.state.value,
        "price_state": _price_state(resolved).value,
        "quantity": quantity,
        "usd": quantity * price if quantity is not None and price is not None else None,
        "reasons": reasons,
    }


def _window(
    resolved: tuple[ResolvedComponent, ...], runner: QueryRunner | None, period: Period
) -> dict[str, Any]:
    sessions = _read_sessions(runner, period)
    readings = [(r, _read_usage(r, runner, period)) for r in resolved]
    per_session = [
        _per_session_row(r, profile, usage, sessions, period)
        for profile in Profile
        for r, usage in readings
        if r.attribution is Attribution.ALLOCATED or profile in r.component.profiles
    ]
    by_vendor: dict[tuple[str | None, str], list[dict[str, Any]]] = {}
    for row in per_session:
        by_vendor.setdefault((row["vendor"], row["profile"]), []).append(row)
    return {
        "period": period.value,
        "window": PERIOD_WINDOW[period],
        "sessions": {
            "state": sessions.state.value,
            "reason": sessions.reason,
            "by_profile": {p.value: sessions.by_profile.get(p) for p in Profile},
        },
        "per_session": per_session,
        "by_vendor": [
            _total(rows, vendor=vendor, profile=profile)
            for (vendor, profile), rows in by_vendor.items()
        ],
        "by_profile": [
            _total([row for row in per_session if row["profile"] == p.value], profile=p.value)
            for p in Profile
        ],
        "spend": [_spend_row(r, usage) for r, usage in readings],
    }


def _budget(
    config: CostConfig,
    budget_index: int,
    windows: Mapping[str, dict[str, Any]],
    alerts: Mapping[str, list[str]],
) -> dict[str, Any]:
    budget = config.budgets[budget_index]
    spend_rows = [
        row
        for row in windows[budget.period.value]["spend"]
        if budget.scope is BudgetScope.ALL_VENDORS or row["vendor"] == budget.vendor
    ]
    known = [row["usd"] for row in spend_rows if row["usd"] is not None]
    missing = [row["component"] for row in spend_rows if row["usd"] is None]
    if not missing:
        spend_state = SpendState.COMPLETE
    else:
        spend_state = SpendState.LOWER_BOUND if known else SpendState.UNKNOWN
    spend = sum(known) if known else None
    limit = budget.limit.usd

    if limit is None:
        status, reason = BudgetStatus.NOT_CONFIGURED, "budget not configured"
    elif spend_state is SpendState.COMPLETE and spend is not None and spend <= limit:
        status, reason = BudgetStatus.WITHIN, "the complete spend is within the limit"
    elif spend is not None and spend > limit:
        status = BudgetStatus.EXCEEDED
        reason = (
            "the complete spend is above the limit"
            if spend_state is SpendState.COMPLETE
            else "a lower bound on the spend is already above the limit"
        )
    else:
        status = BudgetStatus.NOT_EVALUABLE
        reason = f"cannot be evaluated: no spend is known for {', '.join(missing)}"

    return {
        "budget_id": budget.budget_id,
        "scope": budget.scope.value,
        "vendor": budget.vendor,
        "period": budget.period.value,
        "window": PERIOD_WINDOW[budget.period],
        "limit": {
            "state": (
                PriceState.CONFIGURED if limit is not None else PriceState.NOT_CONFIGURED
            ).value,
            "usd": limit,
            "source": budget.limit.source,
            "as_of": budget.limit.as_of.isoformat() if budget.limit.as_of else None,
        },
        "spend_state": spend_state.value,
        "spend_usd": spend,
        "status": status.value,
        "missing": missing,
        "reason": reason,
        "alerts": alerts.get(budget.budget_id, []),
    }


def _component(resolved: ResolvedComponent) -> dict[str, Any]:
    component = resolved.component
    price = component.price
    return {
        "component": component.component,
        "vendor": component.vendor,
        "vendor_note": component.vendor_note,
        "unit": component.unit.value,
        "attribution": resolved.attribution.value,
        "profiles": [p.value for p in component.profiles],
        "usage_metric": component.usage.metric if component.usage else None,
        "usage_metric_status": resolved.catalog_status,
        "usage_note": component.usage_note,
        "price": {
            "state": _price_state(resolved).value,
            "usd_per_unit": price.usd_per_unit,
            "source": price.source,
            "as_of": price.as_of.isoformat() if price.as_of else None,
            "url": price.url,
        },
    }


def compose_cost_payload(
    config: CostConfig,
    *,
    config_ref: str,
    config_sha256: str,
    catalog: MetricsCatalog,
    runner: QueryRunner | None,
) -> dict[str, Any]:
    """The cost module's body: components, per-window cost, budgets and alerts."""
    resolved = resolve_components(config, catalog)
    windows = {period.value: _window(resolved, runner, period) for period in Period}
    groups = cost_rule_groups(config, catalog)
    alerts = budget_alert_names(groups)
    return {
        "currency": config.currency,
        "config": {"path": config_ref, "sha256": config_sha256, "blocker": BLOCKER},
        "source": {
            "configured": runner is not None,
            "reason": (
                "Prometheus instant queries over the cost module's fixed query table"
                if runner is not None
                else _NO_SOURCE
            ),
        },
        "sessions_metric": SESSIONS_METRIC,
        "allocation_rule": _ALLOCATION_RULE,
        "components": [_component(r) for r in resolved],
        "windows": list(windows.values()),
        "budgets": [_budget(config, i, windows, alerts) for i in range(len(config.budgets))],
        "spend_caps": spend_cap_rows(config, runner),
        "alerts": {
            "rules_path": RULES_PATH,
            "rules": [
                {
                    "alert": rule["alert"],
                    "budget_id": rule["labels"]["budget_id"],
                    "severity": rule["labels"]["severity"],
                }
                for group in groups["groups"]
                for rule in group["rules"]
            ],
        },
    }

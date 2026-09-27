"""Budget alerts as Prometheus rules, derived from the price file (INT-190).

``infra/observability/cost-rules.yaml`` is generated from
``infra/costs/unit-prices.yaml`` and the metrics catalogue by
:func:`cost_rule_groups`, and ``tests/observability/test_cost_rules.py`` fails
on any drift between the two — the same generated-consistent discipline as the
SLO rules (INT-021). Per budget, up to three alerts, each carrying the
``budget_id``:

``CostBudgetNotConfigured``
    The limit is empty. ``vector(1)``: it fires until the owner sets one. An
    alert that simply did not exist would read as "within budget".

``CostBudgetExceeded``
    The spend over the budget's window is above its limit. The spend is the sum
    of ``(usage or vector(0)) * price`` over every in-scope component that has
    both a price and a catalogued usage series. ``or vector(0)`` makes each term
    a floor rather than a hole: without it, one component with no samples would
    make the whole sum vanish and the alert could never fire. So the expression
    is a sound lower bound, and a lower bound over the limit is a real overrun.

``CostBudgetIncomplete``
    Some in-scope component cannot be counted — unpriced, unmetered, or metered
    by a series the catalogue still lists as planned. ``vector(1)``, and it
    names them: the threshold above cannot see them, so somebody must.

Every series an expression names is catalogued (CLAUDE.md invariant 13); the
rules carry budget ids, vendor ids and periods, never anything patient-shaped
(invariant 6). Every alert links its heading in ``docs/runbooks/cost-budgets.md``
(files/10 §6; held for every loaded rule by tests/observability/test_alert_rules.py
since the INT-021 close-out).
"""

from __future__ import annotations

from typing import Any, Final

import yaml

from intake_platform.cost.config import PERIOD_WINDOW, Budget, BudgetScope, CostConfig
from intake_platform.cost.queries import usage_term
from intake_platform.cost.resolve import ResolvedComponent, resolve_components
from intake_platform.slo import MetricsCatalog

__all__ = [
    "ALERT_EXCEEDED",
    "ALERT_INCOMPLETE",
    "ALERT_NOT_CONFIGURED",
    "CONFIG_PATH",
    "RULES_PATH",
    "RUNBOOK",
    "budget_alert_names",
    "cost_rule_groups",
    "countable_gap",
    "render_cost_rules",
]

CONFIG_PATH: Final = "infra/costs/unit-prices.yaml"
RULES_PATH: Final = "infra/observability/cost-rules.yaml"
GROUP_NAME: Final = "cost-budgets"
ALERT_NOT_CONFIGURED: Final = "CostBudgetNotConfigured"
ALERT_EXCEEDED: Final = "CostBudgetExceeded"
ALERT_INCOMPLETE: Final = "CostBudgetIncomplete"
#: A budget overrun is money, not a patient: it opens a ticket, it does not page.
SEVERITY: Final = "ticket"
RUNBOOK: Final = "docs/runbooks/cost-budgets.md"
#: files/10 §6 — the heading each alert links, one per alert kind.
_RUNBOOK_ANCHOR: Final = {
    ALERT_NOT_CONFIGURED: "budget-not-configured",
    ALERT_EXCEEDED: "budget-exceeded",
    ALERT_INCOMPLETE: "budget-incomplete",
}


def _runbook(alert: str) -> str:
    return f"{RUNBOOK}#{_RUNBOOK_ANCHOR[alert]}"


_HEADER: Final = f"""\
# {RULES_PATH} — budget alerts for the cost module (INT-190).
#
# GENERATED-CONSISTENT: this file equals
# intake_platform.cost.cost_rule_groups({CONFIG_PATH}) over
# observability/metrics_catalog.yaml, and tests/observability/test_cost_rules.py
# fails on any drift. Do not edit it by hand: set prices and budget limits in
# {CONFIG_PATH} and re-emit:
#   uv run python scripts/observability/cost_rules.py --emit {RULES_PATH}
#
# CostBudgetNotConfigured fires for every budget whose limit is still empty
# (HB-O8); CostBudgetExceeded is a lower bound over the priced, metered
# components; CostBudgetIncomplete names the components the bound cannot see.
"""


def countable_gap(resolved: ResolvedComponent) -> str | None:
    """Why a component's spend cannot be counted, or ``None`` when it can."""
    component = resolved.component
    if component.price.usd_per_unit is None:
        return "price not configured"
    if component.usage is None:
        return "usage not metered"
    if resolved.catalog_status != "live":
        return f"usage series {component.usage.metric} not emitted yet"
    return None


def _in_scope(budget: Budget, resolved: tuple[ResolvedComponent, ...]) -> list[ResolvedComponent]:
    if budget.scope is BudgetScope.ALL_VENDORS:
        return list(resolved)
    return [r for r in resolved if r.component.vendor == budget.vendor]


def _labels(budget: Budget) -> dict[str, str]:
    return {
        "severity": SEVERITY,
        "budget_id": budget.budget_id,
        "scope": budget.vendor if budget.vendor is not None else BudgetScope.ALL_VENDORS.value,
        "period": budget.period.value,
    }


def _budget_rules(budget: Budget, resolved: tuple[ResolvedComponent, ...]) -> list[dict[str, Any]]:
    labels = _labels(budget)
    window = PERIOD_WINDOW[budget.period]
    who = labels["scope"]
    if budget.limit.usd is None:
        return [
            {
                "alert": ALERT_NOT_CONFIGURED,
                "expr": "vector(1)",
                "labels": labels,
                "annotations": {
                    "summary": f"cost budget {budget.budget_id} has no limit configured",
                    "description": (
                        f"{who} spend over the last {window} is not watched until limit.usd "
                        f"is set, with its source and as_of date, in {CONFIG_PATH} (HB-O8)"
                    ),
                    "runbook": _runbook(ALERT_NOT_CONFIGURED),
                },
            }
        ]

    rules: list[dict[str, Any]] = []
    scope = _in_scope(budget, resolved)
    terms = [
        f"({usage_term(r.component.usage, budget.period)} or vector(0)) "
        f"* {float(r.component.price.usd_per_unit)!r}"
        for r in scope
        if r.component.usage is not None and r.component.price.usd_per_unit is not None
    ]
    if terms:
        rules.append(
            {
                "alert": ALERT_EXCEEDED,
                "expr": f"({' + '.join(terms)}) > {float(budget.limit.usd)!r}",
                "labels": labels,
                "annotations": {
                    "summary": (
                        f"cost budget {budget.budget_id} exceeded: {who} spend over the last "
                        f"{window} is above {float(budget.limit.usd)!r} USD"
                    ),
                    "description": (
                        "the spend is a lower bound over the priced, metered components; "
                        f"any CostBudgetIncomplete for {budget.budget_id} names the rest"
                    ),
                    "runbook": _runbook(ALERT_EXCEEDED),
                },
            }
        )
    gaps = [(r.component.component, countable_gap(r)) for r in scope]
    missing = [f"{component}: {gap}" for component, gap in gaps if gap is not None]
    if missing:
        rules.append(
            {
                "alert": ALERT_INCOMPLETE,
                "expr": "vector(1)",
                "labels": labels,
                "annotations": {
                    "summary": f"cost budget {budget.budget_id} cannot be evaluated completely",
                    "missing": "; ".join(missing),
                    "runbook": _runbook(ALERT_INCOMPLETE),
                },
            }
        )
    return rules


def cost_rule_groups(config: CostConfig, catalog: MetricsCatalog) -> dict[str, Any]:
    """The Prometheus rule file body, derived from the price file and catalogue."""
    resolved = resolve_components(config, catalog)
    rules = [rule for budget in config.budgets for rule in _budget_rules(budget, resolved)]
    return {"groups": [{"name": GROUP_NAME, "rules": rules}]}


def budget_alert_names(groups: dict[str, Any]) -> dict[str, list[str]]:
    """budget_id -> the alert names its rules carry, in rule order."""
    names: dict[str, list[str]] = {}
    for group in groups["groups"]:
        for rule in group["rules"]:
            names.setdefault(rule["labels"]["budget_id"], []).append(rule["alert"])
    return names


def render_cost_rules(groups: dict[str, Any]) -> str:
    body = yaml.safe_dump(groups, sort_keys=False, allow_unicode=True, width=10_000)
    return _HEADER + body

"""INT-190 — the cost module: catalogued usage times owner-supplied prices.

Acceptance, verbatim: *"per-session cost by component/vendor/profile; budgets +
alerts"*.

Read in this order:

- :mod:`~intake_platform.cost.config` — ``infra/costs/unit-prices.yaml`` as a
  schema. It is the only source of money, every value in it travels with a
  source and a date, and an empty value stays empty ("not configured"), never
  zero.
- :mod:`~intake_platform.cost.resolve` — each priced component bound to the
  catalogued series that meters it (CLAUDE.md invariant 13), and whether it is
  spent directly by a profile or allocated across sessions.
- :mod:`~intake_platform.cost.queries` — the fixed PromQL table and the
  refusals that keep a malformed or identifying answer from being read.
- :mod:`~intake_platform.cost.console` — the ``GET /admin/cost`` composite:
  per-session cost by component, vendor and profile per window, and each
  budget's verdict.
- :mod:`~intake_platform.cost.rules` — the budget alerts as Prometheus rules,
  generated into ``infra/observability/cost-rules.yaml``.
"""

from __future__ import annotations

from intake_platform.cost.config import (
    Aggregation,
    Budget,
    BudgetScope,
    CostComponent,
    CostConfig,
    Limit,
    Period,
    Price,
    Profile,
    Unit,
    UsageSeries,
    config_identity,
    load_cost_config,
)
from intake_platform.cost.console import (
    BudgetStatus,
    PriceState,
    SpendState,
    TotalState,
    UsageState,
    compose_cost_payload,
)
from intake_platform.cost.queries import (
    SESSIONS_METRIC,
    QueryRefused,
    QueryRunner,
    component_query,
    sessions_query,
)
from intake_platform.cost.resolve import (
    Attribution,
    CostConfigError,
    ResolvedComponent,
    resolve_components,
)
from intake_platform.cost.rules import (
    CONFIG_PATH,
    RULES_PATH,
    cost_rule_groups,
    render_cost_rules,
)

__all__ = [
    "CONFIG_PATH",
    "RULES_PATH",
    "SESSIONS_METRIC",
    "Aggregation",
    "Attribution",
    "Budget",
    "BudgetScope",
    "BudgetStatus",
    "CostComponent",
    "CostConfig",
    "CostConfigError",
    "Limit",
    "Period",
    "Price",
    "PriceState",
    "Profile",
    "QueryRefused",
    "QueryRunner",
    "ResolvedComponent",
    "SpendState",
    "TotalState",
    "Unit",
    "UsageSeries",
    "UsageState",
    "component_query",
    "compose_cost_payload",
    "config_identity",
    "cost_rule_groups",
    "load_cost_config",
    "render_cost_rules",
    "resolve_components",
    "sessions_query",
]

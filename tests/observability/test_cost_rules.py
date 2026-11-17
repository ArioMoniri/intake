"""INT-190 — budget alerts are Prometheus rules generated from the price config.

Acceptance, verbatim: *"per-session cost by component/vendor/profile; budgets +
alerts"*. This file is the "alerts" clause.

``infra/observability/cost-rules.yaml`` equals
``intake_platform.cost.cost_rule_groups`` over ``infra/costs/unit-prices.yaml``
and the metrics catalogue, and a hand edit to either side fails here — the
same generated-consistent discipline as the SLO rules (INT-021). Three
properties the generator is held to:

- **Only catalogued series** appear in an expression (CLAUDE.md invariant 13).
- **An unset budget is loud, not silent.** A budget with no limit gets a
  ``CostBudgetNotConfigured`` alert that fires until the owner sets one; an
  alert that simply did not exist would read as "within budget".
- **A threshold is a sound lower bound.** Each priced term is ``or vector(0)``,
  so a component with no samples cannot make the whole sum vanish and the
  alert never fire; the components that cannot be counted at all get a
  ``CostBudgetIncomplete`` alert naming them.

The Prometheus the obs profile runs must mount the file and keep a month of
data, or the month budgets would be evaluated over a window it has deleted.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from intake_platform.cost import cost_rule_groups, load_cost_config, render_cost_rules
from intake_platform.slo import load_metrics_catalog, window_seconds

REPO = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO / "infra" / "costs" / "unit-prices.yaml"
PRICED_PATH = REPO / "tests" / "fixtures" / "cost" / "unit-prices.priced.yaml"
CATALOG_PATH = REPO / "observability" / "metrics_catalog.yaml"
RULES_PATH = REPO / "infra" / "observability" / "cost-rules.yaml"
COMPOSE_PATH = REPO / "infra" / "docker-compose.obs.yml"
PROMETHEUS_PATH = REPO / "infra" / "observability" / "prometheus.yml"


def _groups(path: Path) -> dict[str, Any]:
    return cost_rule_groups(load_cost_config(path), load_metrics_catalog(CATALOG_PATH))


def _alerts(groups: dict[str, Any]) -> list[dict[str, Any]]:
    return [rule for group in groups["groups"] for rule in group["rules"] if "alert" in rule]


def _for_budget(groups: dict[str, Any], budget_id: str) -> dict[str, dict[str, Any]]:
    return {
        rule["alert"]: rule for rule in _alerts(groups) if rule["labels"]["budget_id"] == budget_id
    }


class TestGeneratedConsistent:
    def test_the_committed_rules_equal_the_generator(self) -> None:
        committed = yaml.safe_load(RULES_PATH.read_text(encoding="utf-8"))
        assert committed == _groups(CONFIG_PATH), (
            "infra/observability/cost-rules.yaml drifted from infra/costs/unit-prices.yaml; "
            "re-run uv run python scripts/observability/cost_rules.py --emit "
            "infra/observability/cost-rules.yaml"
        )

    def test_the_rendered_text_parses_back_to_the_groups(self) -> None:
        groups = _groups(PRICED_PATH)
        text = render_cost_rules(groups)
        assert text.startswith("#")
        assert yaml.safe_load(text) == groups


class TestOnlyCataloguedSeries:
    def test_no_expression_references_an_uncatalogued_series(self) -> None:
        catalog = load_metrics_catalog(CATALOG_PATH)
        for path in (CONFIG_PATH, PRICED_PATH):
            for rule in _alerts(_groups(path)):
                assert catalog.unknown_references(rule["expr"]) == frozenset(), rule["alert"]

    def test_a_threshold_reads_the_usage_series_the_config_names(self) -> None:
        exceeded = _for_budget(_groups(PRICED_PATH), "self-hosted-day")["CostBudgetExceeded"]
        assert 'voice_tts_chars_sum{vendor="self-hosted"}[1d]' in exceeded["expr"]


class TestAnUnsetBudgetIsLoud:
    def test_every_budget_has_at_least_one_rule(self) -> None:
        config = load_cost_config(CONFIG_PATH)
        groups = _groups(CONFIG_PATH)
        for budget in config.budgets:
            assert _for_budget(groups, budget.budget_id), budget.budget_id

    def test_an_unset_limit_fires_not_configured_and_nothing_else(self) -> None:
        rules = _for_budget(_groups(PRICED_PATH), "elevenlabs-day")
        assert set(rules) == {"CostBudgetNotConfigured"}
        assert rules["CostBudgetNotConfigured"]["expr"] == "vector(1)"

    def test_the_committed_config_is_all_not_configured(self) -> None:
        # the state HB-O8 leaves: no limit is set, so every budget alert says so
        assert {rule["alert"] for rule in _alerts(_groups(CONFIG_PATH))} == {
            "CostBudgetNotConfigured"
        }


class TestThresholdIsASoundLowerBound:
    def test_the_threshold_multiplies_each_priced_term_and_compares_the_limit(self) -> None:
        exceeded = _for_budget(_groups(PRICED_PATH), "self-hosted-day")["CostBudgetExceeded"]
        expr = exceeded["expr"]
        assert "or vector(0)) * 2.0" in expr  # tts_dynamic at the fixture rate of 2
        assert "or vector(0)) * 3.0" in expr  # asr: catalogued, priced, not yet emitted
        assert expr.endswith("> 50000.0")
        assert exceeded["labels"]["period"] == "day"

    def test_a_component_that_cannot_be_counted_is_named_by_an_incomplete_alert(self) -> None:
        rules = _for_budget(_groups(PRICED_PATH), "self-hosted-day")
        incomplete = rules["CostBudgetIncomplete"]
        assert incomplete["expr"] == "vector(1)"
        # llm_extraction has no series; asr and llm_talker are planned
        for component in ("llm_extraction", "asr", "llm_talker"):
            assert component in incomplete["annotations"]["missing"]

    def test_an_unpriced_component_is_left_out_of_the_sum_and_named(self) -> None:
        rules = _for_budget(_groups(PRICED_PATH), "all-vendors-day")
        assert "notification_dispatch_total" not in rules["CostBudgetExceeded"]["expr"]
        assert "sms" in rules["CostBudgetIncomplete"]["annotations"]["missing"]

    def test_no_priced_metered_component_means_no_threshold(self) -> None:
        # elevenlabs-month has a limit, and its one component has no series:
        # a threshold over nothing would be `vector(0) > limit`, silent forever
        rules = _for_budget(_groups(PRICED_PATH), "elevenlabs-month")
        assert "CostBudgetExceeded" not in rules
        assert "CostBudgetIncomplete" in rules


class TestPrometheusRunsTheRules:
    def test_the_obs_prometheus_mounts_and_loads_the_cost_rules(self) -> None:
        compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
        volumes = [str(v) for v in compose["services"]["prometheus"]["volumes"]]
        assert any("observability/cost-rules.yaml" in v for v in volumes)
        config = yaml.safe_load(PROMETHEUS_PATH.read_text(encoding="utf-8"))
        assert "/etc/prometheus/rules/cost-rules.yaml" in config["rule_files"]

    def test_retention_covers_the_longest_budget_window(self) -> None:
        compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
        flags = [str(f) for f in compose["services"]["prometheus"]["command"]]
        retention = next(f for f in flags if f.startswith("--storage.tsdb.retention.time="))
        kept = window_seconds(retention.split("=", 1)[1])
        assert kept >= window_seconds("30d")

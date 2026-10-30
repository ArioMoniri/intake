"""INT-190 — the fixed query table and every refusal on its answers.

A refusal that no test ever takes is a gate nobody has proven. This file takes
each of the query table's and the schema's remaining refusals once, each beside
the near-miss that must pass:

- the three query shapes, including the ``gauge_hours`` shape that a 0/1
  host-uptime series will be read with once one is catalogued;
- every malformed answer the parser refuses (no result list, a non-object
  entry, a sample without a value pair, a profile twice, a labelled scalar);
- the schema refusals the config tests do not reach (a non-finite price, a
  malformed series or label name, duplicate profiles or budgets, a vendor
  budget with no vendor, two budgets for one slot).
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml
from intake_platform.cost import (
    Attribution,
    CostConfig,
    QueryRefused,
    component_query,
    compose_cost_payload,
    resolve_components,
)
from intake_platform.cost.config import Period
from intake_platform.cost.queries import parse_by_profile, parse_scalar, run_query
from intake_platform.slo import MetricsCatalog, load_metrics_catalog
from pydantic import ValidationError

REPO = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO / "infra" / "costs" / "unit-prices.yaml"
PRICED_PATH = REPO / "tests" / "fixtures" / "cost" / "unit-prices.priced.yaml"
CATALOG_PATH = REPO / "observability" / "metrics_catalog.yaml"


def _raw(path: Path = CONFIG_PATH) -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded


def _with_host_series() -> tuple[CostConfig, MetricsCatalog]:
    """The committed config with the AWS host metered by a 0/1 uptime gauge.

    The gauge is added to a copy of the catalogue for this test only — on main
    no host-uptime series is catalogued, which is why the committed row says
    "not metered".
    """
    catalog = load_metrics_catalog(CATALOG_PATH)
    extended = MetricsCatalog.model_validate(
        {
            "metrics": [m.model_dump(exclude_none=True) for m in catalog.metrics]
            + [
                {
                    "name": "host_up_under_test",
                    "type": "gauge",
                    "labels": ["host_id"],
                    "owner": "platform",
                    "unit": "bool (0/1)",
                    "description": "test-only host uptime gauge",
                }
            ]
        }
    )
    raw = copy.deepcopy(_raw())
    for row in raw["components"]:
        if row["component"] == "gpu_host_onvizit_api":
            row["usage"] = {
                "metric": "host_up_under_test",
                "aggregation": "gauge_hours",
                "selector": {"host_id": "onvizit-api"},
            }
            row["usage_note"] = None
    return CostConfig.model_validate(raw), extended


def _ok(result: Any) -> dict[str, Any]:
    return {"status": "success", "data": {"resultType": "vector", "result": result}}


class TestQueryShapes:
    def test_a_host_hour_is_the_mean_of_a_0_1_gauge_times_the_window_hours(self) -> None:
        config, catalog = _with_host_series()
        resolved = {r.component.component: r for r in resolve_components(config, catalog)}
        host = resolved["gpu_host_onvizit_api"]
        assert host.attribution is Attribution.ALLOCATED
        assert component_query(host, Period.DAY) == (
            'sum(avg_over_time(host_up_under_test{host_id="onvizit-api"}[1d])) * 24'
        )
        assert component_query(host, Period.MONTH).endswith("[30d])) * 720")

    def test_an_unmetered_component_has_no_query(self) -> None:
        resolved = {
            r.component.component: r
            for r in resolve_components(
                CostConfig.model_validate(_raw()), load_metrics_catalog(CATALOG_PATH)
            )
        }
        with pytest.raises(ValueError, match="no usage series"):
            component_query(resolved["llm_extraction"], Period.DAY)

    def test_a_selector_less_series_is_queried_bare(self) -> None:
        config, catalog = _with_host_series()
        raw = copy.deepcopy(config.model_dump(mode="json"))
        for row in raw["components"]:
            if row["component"] == "gpu_host_onvizit_api":
                row["usage"]["selector"] = {}
        resolved = {
            r.component.component: r
            for r in resolve_components(CostConfig.model_validate(raw), catalog)
        }
        query = component_query(resolved["gpu_host_onvizit_api"], Period.DAY)
        assert "host_up_under_test[1d]" in query

    def test_a_host_series_prices_through_to_the_console(self) -> None:
        config, catalog = _with_host_series()
        raw = config.model_dump(mode="json")
        for row in raw["components"]:
            if row["component"] == "gpu_host_onvizit_api":
                row["price"] = {"usd_per_unit": 5, "source": "synthetic", "as_of": "2026-09-26"}
        priced = CostConfig.model_validate(raw)
        host_query = component_query(
            next(
                r
                for r in resolve_components(priced, catalog)
                if r.component.component == "gpu_host_onvizit_api"
            ),
            Period.DAY,
        )

        def runner(promql: str) -> dict[str, Any]:
            if promql == host_query:
                return _ok([{"metric": {}, "value": [0, "24"]}])
            if "voice_sessions_metered_total" in promql:
                return _ok([{"metric": {"profile": "residency_tr"}, "value": [0, "12"]}])
            return _ok([])

        payload = compose_cost_payload(
            priced, config_ref="inline", config_digest="0" * 32, catalog=catalog, runner=runner
        )
        day = next(w for w in payload["windows"] if w["period"] == "day")
        row = next(
            r
            for r in day["per_session"]
            if r["component"] == "gpu_host_onvizit_api" and r["profile"] == "residency_tr"
        )
        # 24 host hours over 12 sessions at the synthetic 5 per hour
        assert row["quantity_per_session"] == pytest.approx(2.0)
        assert row["usd_per_session"] == pytest.approx(10.0)
        spend = next(s for s in day["spend"] if s["component"] == "gpu_host_onvizit_api")
        assert spend["usd"] == pytest.approx(120.0)


class TestAnswerRefusals:
    @pytest.mark.parametrize(
        ("response", "match"),
        [
            ({"status": "success", "data": {"resultType": "vector", "result": {}}}, "result list"),
            (_ok(["not-an-object"]), "not an object"),
            (_ok([{"metric": {}, "value": [0]}]), "labelled sample"),
            (_ok([{"metric": [], "value": [0, "1"]}]), "labelled sample"),
        ],
    )
    def test_a_malformed_answer_is_refused(self, response: Any, match: str) -> None:
        with pytest.raises(QueryRefused, match=match):
            run_query(lambda _promql: response, "sum(x)")

    def test_a_profile_twice_in_one_answer_is_refused(self) -> None:
        samples = [({"profile": "typed"}, 1.0), ({"profile": "typed"}, 2.0)]
        with pytest.raises(QueryRefused, match="twice"):
            parse_by_profile(samples)

    def test_a_labelled_or_repeated_scalar_is_refused(self) -> None:
        with pytest.raises(QueryRefused, match="labelled or repeated"):
            parse_scalar([({"channel": "sms"}, 1.0)])
        with pytest.raises(QueryRefused, match="labelled or repeated"):
            parse_scalar([({}, 1.0), ({}, 2.0)])

    def test_near_miss_one_bare_sample_and_no_sample(self) -> None:
        assert parse_scalar([({}, 3.0)]) == 3.0
        assert parse_scalar([]) is None

    def test_a_profile_absent_from_a_non_empty_answer_has_no_samples(self) -> None:
        config = CostConfig.model_validate(_raw(PRICED_PATH))
        catalog = load_metrics_catalog(CATALOG_PATH)

        def runner(promql: str) -> dict[str, Any]:
            if "voice_tts_chars_sum" in promql:
                # a typed sample only: residency_tr spent nothing the scrape saw
                return _ok([{"metric": {"profile": "typed"}, "value": [0, "5"]}])
            if "voice_sessions_metered_total" in promql:
                return _ok([{"metric": {"profile": "residency_tr"}, "value": [0, "4"]}])
            return _ok([])

        payload = compose_cost_payload(
            config, config_ref="inline", config_digest="0" * 32, catalog=catalog, runner=runner
        )
        day = next(w for w in payload["windows"] if w["period"] == "day")
        row = next(
            r
            for r in day["per_session"]
            if r["component"] == "tts_dynamic" and r["profile"] == "residency_tr"
        )
        assert row["usage_state"] == "no_samples"
        assert row["usd_per_session"] is None
        assert any("for residency_tr" in reason for reason in row["reasons"])


class TestRemainingSchemaRefusals:
    def _component(self, **overrides: Any) -> dict[str, Any]:
        raw = copy.deepcopy(_raw())
        for row in raw["components"]:
            if row["component"] == "tts_dynamic":
                row.update(overrides)
        return raw

    @pytest.mark.parametrize("value", [float("inf"), float("nan")])
    def test_a_non_finite_price_is_refused(self, value: float) -> None:
        raw = self._component(price={"usd_per_unit": value, "source": "q", "as_of": "2026-09-01"})
        with pytest.raises(ValidationError, match="finite"):
            CostConfig.model_validate(raw)

    def test_a_malformed_series_name_is_refused(self) -> None:
        usage = {"metric": "voice.tts_chars", "aggregation": "histogram_sum", "selector": {}}
        with pytest.raises(ValidationError, match="series name"):
            CostConfig.model_validate(self._component(usage=usage))

    def test_a_malformed_label_name_is_refused(self) -> None:
        usage = {
            "metric": "voice_tts_chars",
            "aggregation": "histogram_sum",
            "selector": {"Vendor-Name": "self-hosted"},
        }
        with pytest.raises(ValidationError, match="label name"):
            CostConfig.model_validate(self._component(usage=usage))

    def test_duplicate_profiles_are_refused(self) -> None:
        raw = self._component(profiles=["residency_tr", "residency_tr"])
        with pytest.raises(ValidationError, match="duplicate profiles"):
            CostConfig.model_validate(raw)

    def test_a_vendor_budget_without_a_vendor_is_refused(self) -> None:
        raw = copy.deepcopy(_raw())
        raw["budgets"][2]["vendor"] = None
        with pytest.raises(ValidationError, match="must name its vendor"):
            CostConfig.model_validate(raw)

    def test_duplicate_budget_ids_are_refused(self) -> None:
        raw = copy.deepcopy(_raw())
        raw["budgets"][1]["budget_id"] = raw["budgets"][0]["budget_id"]
        with pytest.raises(ValidationError, match="duplicate budget ids"):
            CostConfig.model_validate(raw)

    def test_two_budgets_for_one_slot_are_refused(self) -> None:
        raw = copy.deepcopy(_raw())
        extra = copy.deepcopy(raw["budgets"][0])
        extra["budget_id"] = "all-vendors-day-2"
        raw["budgets"].append(extra)
        with pytest.raises(ValidationError, match="cover one slot"):
            CostConfig.model_validate(raw)

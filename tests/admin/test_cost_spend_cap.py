"""INT-439 — the spend cap and model rates in the price file, and on the console.

00_STATE §3 D19 (owner, 3 Oct 2026: *"make limit 80 dollars"*). The schema must
refuse every way the cap or a rate could drift away from its source, and the
console verdict must never read an unknown spend as zero. Each rule has a
near-miss beside it.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml
from intake_platform.cost import CostConfig, load_cost_config
from intake_platform.cost.cap_status import SPEND_CAP_QUERY, CapStatus, spend_cap_rows
from pydantic import ValidationError

REPO = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO / "infra" / "costs" / "unit-prices.yaml"


def _raw() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    return loaded


def _validate(raw: dict[str, Any]) -> CostConfig:
    return CostConfig.model_validate(raw)


def _component(raw: dict[str, Any], name: str) -> dict[str, Any]:
    found: dict[str, Any] = next(c for c in raw["components"] if c["component"] == name)
    return found


class TestTheCommittedFile:
    def test_it_validates_with_the_cap_and_two_rates(self) -> None:
        config = load_cost_config(CONFIG_PATH)
        assert [cap.cap_id for cap in config.spend_caps] == ["elective-models-month"]
        assert {r.priced_by for r in config.model_rates} == {
            "gpu_host_onvizit_api",
            "clip_synthesis",
        }


class TestSpendCapSchema:
    @pytest.mark.parametrize("ratio", [0, 1, 1.5, -0.1])
    def test_a_warning_ratio_outside_the_open_interval_is_refused(self, ratio: float) -> None:
        raw = _raw()
        raw["spend_caps"][0]["warn_ratio"] = ratio
        with pytest.raises(ValidationError):
            _validate(raw)

    def test_near_miss_a_ratio_just_inside_is_accepted(self) -> None:
        raw = _raw()
        raw["spend_caps"][0]["warn_ratio"] = 0.99
        assert _validate(raw).spend_caps[0].warn_ratio > 0

    @pytest.mark.parametrize("field", ["source", "as_of"])
    def test_a_cap_without_its_provenance_is_refused(self, field: str) -> None:
        raw = _raw()
        del raw["spend_caps"][0]["limit"][field]
        with pytest.raises(ValidationError):
            _validate(raw)

    def test_a_zero_cap_is_refused(self) -> None:
        raw = _raw()
        raw["spend_caps"][0]["limit"]["usd"] = 0
        with pytest.raises(ValidationError):
            _validate(raw)

    def test_two_caps_over_the_same_spend_are_refused(self) -> None:
        raw = _raw()
        twin = copy.deepcopy(raw["spend_caps"][0])
        twin["cap_id"] = "elective-models-month-2"
        raw["spend_caps"].append(twin)
        with pytest.raises(ValidationError, match="same spend"):
            _validate(raw)


class TestModelRateSchema:
    def test_a_rate_on_an_unknown_component_is_refused(self) -> None:
        raw = _raw()
        raw["model_rates"][0]["priced_by"] = "no_such_component"
        with pytest.raises(ValidationError, match="unknown"):
            _validate(raw)

    def test_a_rate_on_an_unpriced_component_is_refused(self) -> None:
        raw = _raw()
        raw["model_rates"][0]["priced_by"] = "gpu_host_team"
        with pytest.raises(ValidationError):
            _validate(raw)

    def test_a_self_hosted_lane_charged_per_character_is_refused(self) -> None:
        raw = _raw()
        rate = raw["model_rates"][1]
        rate["route"] = "self_hosted"
        with pytest.raises(ValidationError, match="cannot be charged"):
            _validate(raw)

    def test_a_provider_that_does_not_bill_the_component_is_refused(self) -> None:
        raw = _raw()
        raw["model_rates"][1]["provider"] = "openai"
        with pytest.raises(ValidationError, match="billed by"):
            _validate(raw)

    def test_two_rates_for_one_lane_are_refused(self) -> None:
        raw = _raw()
        twin = copy.deepcopy(raw["model_rates"][0])
        twin["rate_id"] = "self-hosted-g6-2xlarge-twin"
        raw["model_rates"].append(twin)
        with pytest.raises(ValidationError, match="same lane"):
            _validate(raw)

    def test_near_miss_a_second_host_type_is_a_second_lane(self) -> None:
        raw = _raw()
        twin = copy.deepcopy(raw["model_rates"][0])
        twin["rate_id"] = "self-hosted-other"
        twin["model"] = "g6.4xlarge"
        raw["model_rates"].append(twin)
        assert len(_validate(raw).model_rates) == 3


class TestPriceUrl:
    def test_an_http_page_is_refused(self) -> None:
        raw = _raw()
        _component(raw, "clip_synthesis")["price"]["url"] = "http://elevenlabs.io/pricing/api"
        with pytest.raises(ValidationError, match="https"):
            _validate(raw)

    def test_a_page_with_no_price_is_refused(self) -> None:
        raw = _raw()
        _component(raw, "sms")["price"]["url"] = "https://example.invalid/price"
        with pytest.raises(ValidationError, match="no value"):
            _validate(raw)

    def test_near_miss_a_sourced_price_without_a_page_is_still_an_invoice_price(self) -> None:
        raw = _raw()
        del _component(raw, "clip_synthesis")["price"]["url"]
        assert _validate(raw)


def _runner(value: str | None) -> Any:
    def run(promql: str) -> dict[str, Any]:
        assert promql == SPEND_CAP_QUERY
        result = [] if value is None else [{"metric": {}, "value": [0, value]}]
        return {"status": "success", "data": {"resultType": "vector", "result": result}}

    return run


class TestConsoleVerdict:
    @pytest.mark.parametrize(
        ("spend", "status"),
        [
            ("63.99", CapStatus.WITHIN),
            ("64", CapStatus.WARNING),
            ("79.99", CapStatus.WARNING),
            ("80", CapStatus.REACHED),
            ("120", CapStatus.REACHED),
        ],
    )
    def test_the_verdict_follows_the_two_thresholds(self, spend: str, status: CapStatus) -> None:
        (row,) = spend_cap_rows(load_cost_config(CONFIG_PATH), _runner(spend))
        assert row["status"] == status.value
        assert row["spend_usd"] == float(spend)

    def test_no_source_is_unknown_never_zero(self) -> None:
        (row,) = spend_cap_rows(load_cost_config(CONFIG_PATH), None)
        assert row["spend_usd"] is None
        assert row["status"] == CapStatus.NOT_EVALUABLE.value
        assert "not configured" in row["reason"]

    def test_near_miss_a_source_with_no_sample_is_also_unknown(self) -> None:
        (row,) = spend_cap_rows(load_cost_config(CONFIG_PATH), _runner(None))
        assert row["status"] == CapStatus.NOT_EVALUABLE.value

    def test_a_refusing_source_is_named(self) -> None:
        def broken(promql: str) -> dict[str, Any]:
            return {"status": "error"}

        (row,) = spend_cap_rows(load_cost_config(CONFIG_PATH), broken)
        assert row["status"] == CapStatus.NOT_EVALUABLE.value
        assert row["reason"].startswith("source refused")

    def test_a_config_without_a_cap_has_no_row(self) -> None:
        config = load_cost_config(CONFIG_PATH).model_copy(update={"spend_caps": ()})
        assert spend_cap_rows(config, _runner("10")) == []

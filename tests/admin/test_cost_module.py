"""INT-190 — per-session cost by component/vendor/profile, and budget verdicts.

Acceptance, verbatim: *"per-session cost by component/vendor/profile; budgets +
alerts"*.

The arithmetic is one line — a catalogued quantity times an owner-supplied
price, divided by the sessions metered in the same window — and everything
else in this file is about what happens when one of the three is missing:

- **A missing price is "price not configured", never 0.** Zero is the claim
  that something was free (docs/evidence/INT-101.md §6). The row carries no
  figure and every total it belongs to is withheld, not shown partial.
- **A missing quantity is a named state, never 0.** Not metered (no catalogued
  series), not emitted (catalogued as planned), no samples in the window,
  source unavailable, source error — each one is distinguishable on the page.
- **A budget is "within" only when its spend is complete.** A lower bound can
  prove a budget exceeded; it can never prove one kept.

The recorded metric responses in ``tests/fixtures/cost/`` are the only usage
data here; the fixture drift tests at the bottom prove the console's recorded
payloads are exactly what this module computes from them.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml
from intake_platform.cost import (
    CostConfig,
    component_query,
    compose_cost_payload,
    config_identity,
    load_cost_config,
    resolve_components,
    sessions_query,
)
from intake_platform.cost.config import Period
from intake_platform.slo import PHI_RISK_LABEL_NAMES, MetricsCatalog, load_metrics_catalog

REPO = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO / "infra" / "costs" / "unit-prices.yaml"
PRICED_PATH = REPO / "tests" / "fixtures" / "cost" / "unit-prices.priced.yaml"
RESPONSES_PATH = REPO / "tests" / "fixtures" / "cost" / "prometheus_responses.json"
CATALOG_PATH = REPO / "observability" / "metrics_catalog.yaml"
FIXTURES = REPO / "apps" / "admin-web" / "e2e" / "fixtures"

Runner = Callable[[str], Mapping[str, Any]]


def _catalog() -> MetricsCatalog:
    return load_metrics_catalog(CATALOG_PATH)


def _recorded() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(RESPONSES_PATH.read_text(encoding="utf-8"))["queries"]
    return loaded


def recorded_runner(queries: Mapping[str, Any], issued: list[str] | None = None) -> Runner:
    def run(promql: str) -> Mapping[str, Any]:
        if issued is not None:
            issued.append(promql)
        response: Mapping[str, Any] = queries[promql]
        return response

    return run


def _compose(path: Path, runner: Runner | None, catalog: MetricsCatalog | None = None) -> Any:
    ref, sha = config_identity(path, REPO)
    return compose_cost_payload(
        load_cost_config(path),
        config_ref=ref,
        config_sha256=sha,
        catalog=catalog or _catalog(),
        runner=runner,
    )


def _priced() -> Any:
    return _compose(PRICED_PATH, recorded_runner(_recorded()))


def _window(payload: Any, period: str) -> dict[str, Any]:
    window: dict[str, Any] = next(w for w in payload["windows"] if w["period"] == period)
    return window


def _row(window: dict[str, Any], component: str, profile: str) -> dict[str, Any]:
    row: dict[str, Any] = next(
        r for r in window["per_session"] if r["component"] == component and r["profile"] == profile
    )
    return row


def _budget(payload: Any, budget_id: str) -> dict[str, Any]:
    budget: dict[str, Any] = next(b for b in payload["budgets"] if b["budget_id"] == budget_id)
    return budget


def _walk(node: Any, key: str | None = None) -> Iterator[tuple[str | None, Any]]:
    if isinstance(node, dict):
        for k, v in node.items():
            yield k, v
            yield from _walk(v, k)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item, key)


# --- per-session cost by component / vendor / profile ------------------------------


class TestPerSessionCost:
    def test_a_priced_observed_component_costs_quantity_times_price_over_sessions(self) -> None:
        day = _window(_priced(), "day")
        # 48000 characters over 40 residency_tr sessions, at the fixture rate of 2
        row = _row(day, "tts_dynamic", "residency_tr")
        assert row["usage_state"] == "observed"
        assert row["quantity_per_session"] == pytest.approx(1200.0)
        assert row["usd_per_session"] == pytest.approx(2400.0)
        assert row["vendor"] == "self-hosted"
        assert row["attribution"] == "direct"

    def test_the_month_window_divides_by_the_month_sessions(self) -> None:
        month = _window(_priced(), "month")
        row = _row(month, "tts_dynamic", "residency_tr")
        assert row["quantity_per_session"] == pytest.approx(1_080_000 / 900)
        assert row["usd_per_session"] == pytest.approx(2 * 1_080_000 / 900)

    def test_a_component_is_shown_only_for_the_profiles_it_spends_in(self) -> None:
        day = _window(_priced(), "day")
        typed = {r["component"] for r in day["per_session"] if r["profile"] == "typed"}
        # typed has no audio in either direction; the config says so, not a zero
        assert "tts_dynamic" not in typed
        assert "asr" not in typed
        assert {"llm_talker", "llm_extraction", "sms"} <= typed

    def test_a_missing_price_is_price_not_configured_never_zero(self) -> None:
        day = _window(_priced(), "day")
        row = _row(day, "sms", "residency_tr")
        # the quantity is known — 25 delivered messages over 50 sessions — and
        # the cost still is not, because nobody has priced a message
        assert row["usage_state"] == "observed"
        assert row["quantity_per_session"] == pytest.approx(0.5)
        assert row["price_state"] == "not_configured"
        assert row["usd_per_session"] is None
        assert "price not configured" in row["reasons"]

    def test_an_allocated_component_splits_evenly_across_all_sessions(self) -> None:
        day = _window(_priced(), "day")
        rt = _row(day, "sms", "residency_tr")
        typed = _row(day, "sms", "typed")
        assert rt["attribution"] == typed["attribution"] == "allocated"
        assert rt["quantity_per_session"] == typed["quantity_per_session"]

    def test_an_unemitted_series_is_a_named_state_not_a_zero(self) -> None:
        row = _row(_window(_priced(), "day"), "asr", "residency_tr")
        assert row["usage_state"] == "not_emitted"
        assert row["quantity_per_session"] is None
        assert row["usd_per_session"] is None
        assert any("voice_stt_audio_s" in reason for reason in row["reasons"])

    def test_an_unmetered_component_carries_its_reason(self) -> None:
        row = _row(_window(_priced(), "day"), "llm_extraction", "typed")
        assert row["usage_state"] == "not_metered"
        assert row["usd_per_session"] is None
        assert any("extraction tokens" in reason for reason in row["reasons"])

    def test_a_profile_total_is_withheld_while_any_component_is_unknown(self) -> None:
        day = _window(_priced(), "day")
        rt = next(p for p in day["by_profile"] if p["profile"] == "residency_tr")
        assert rt["state"] == "incomplete"
        assert rt["usd_per_session"] is None
        assert {"asr", "sms", "llm_extraction"} <= set(rt["missing"])

    def test_a_vendor_total_is_per_profile_and_withheld_when_partial(self) -> None:
        day = _window(_priced(), "day")
        keys = {(v["vendor"], v["profile"]) for v in day["by_vendor"]}
        assert ("self-hosted", "residency_tr") in keys
        assert ("elevenlabs", "typed") in keys
        # sms and the team GPU host have no vendor: grouped as unassigned
        assert (None, "residency_tr") in keys
        for vendor in day["by_vendor"]:
            if vendor["state"] == "incomplete":
                assert vendor["usd_per_session"] is None

    def test_no_sessions_in_a_profile_means_no_per_session_figure(self) -> None:
        queries = dict(_recorded())
        sessions = sessions_query(Period.DAY)
        queries[sessions] = {
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [{"metric": {"profile": "residency_tr"}, "value": [0, "40"]}],
            },
        }
        day = _window(_compose(PRICED_PATH, recorded_runner(queries)), "day")
        row = _row(day, "llm_talker", "typed")
        assert row["usd_per_session"] is None
        assert any("no metered sessions" in reason for reason in row["reasons"])


# --- fail closed on the source ------------------------------------------------------


class TestSourceFailsClosed:
    def test_no_prometheus_means_every_quantity_is_unavailable(self) -> None:
        payload = _compose(PRICED_PATH, None)
        assert payload["source"]["configured"] is False
        for window in payload["windows"]:
            assert window["sessions"]["state"] == "source_unavailable"
            for row in window["per_session"]:
                assert row["usd_per_session"] is None
                assert row["usage_state"] in {"source_unavailable", "not_emitted", "not_metered"}

    def _day_row_with(self, response: Any, component: str = "tts_dynamic") -> dict[str, Any]:
        queries = dict(_recorded())
        resolved = {
            r.component.component: r
            for r in resolve_components(load_cost_config(PRICED_PATH), _catalog())
        }
        queries[component_query(resolved[component], Period.DAY)] = response
        return _row(
            _window(_compose(PRICED_PATH, recorded_runner(queries)), "day"),
            component,
            "residency_tr",
        )

    def test_a_failed_query_is_a_source_error(self) -> None:
        row = self._day_row_with({"status": "error", "error": "query timed out"})
        assert row["usage_state"] == "source_error"
        assert row["usd_per_session"] is None

    def test_a_runner_exception_is_a_source_error(self) -> None:
        def broken(promql: str) -> Mapping[str, Any]:
            raise TimeoutError(promql)

        payload = _compose(PRICED_PATH, broken)
        row = _row(_window(payload, "day"), "tts_dynamic", "residency_tr")
        assert row["usage_state"] == "source_error"
        assert _window(payload, "day")["sessions"]["state"] == "source_error"

    def test_an_identifier_label_in_a_response_is_refused(self) -> None:
        # invariant 6: the queries aggregate every identifying label away, so a
        # response carrying one is not the query this module sent
        response = {
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [
                    {"metric": {"profile": "residency_tr", "session_id": "s-1"}, "value": [0, "1"]}
                ],
            },
        }
        row = self._day_row_with(response)
        assert row["usage_state"] == "source_error"
        assert any("label" in reason for reason in row["reasons"])

    def test_a_profile_outside_the_closed_set_is_refused(self) -> None:
        response = {
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [{"metric": {"profile": "s2s" + "_cloud"}, "value": [0, "1"]}],
            },
        }
        assert self._day_row_with(response)["usage_state"] == "source_error"

    @pytest.mark.parametrize("value", ["NaN", "+Inf", "-3", "many"])
    def test_a_non_quantity_is_refused(self, value: str) -> None:
        response = {
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [{"metric": {"profile": "residency_tr"}, "value": [0, value]}],
            },
        }
        assert self._day_row_with(response)["usage_state"] == "source_error"

    def test_a_non_vector_result_is_refused(self) -> None:
        response = {"status": "success", "data": {"resultType": "matrix", "result": []}}
        assert self._day_row_with(response)["usage_state"] == "source_error"

    def test_an_empty_result_is_no_samples_not_zero(self) -> None:
        response = {"status": "success", "data": {"resultType": "vector", "result": []}}
        row = self._day_row_with(response)
        assert row["usage_state"] == "no_samples"
        assert row["usd_per_session"] is None


# --- budgets -----------------------------------------------------------------------


def _single_vendor_config(limit_day: float, limit_month: float) -> CostConfig:
    """One live, priced component — the only shape on main whose spend can be
    complete, and therefore the only one that can prove a budget kept."""
    raw: dict[str, Any] = yaml.safe_load(PRICED_PATH.read_text(encoding="utf-8"))
    raw["components"] = [c for c in raw["components"] if c["component"] == "tts_dynamic"]
    sourced = {"source": "synthetic test limit, not a budget", "as_of": "2026-09-26"}
    raw["budgets"] = [
        {
            "budget_id": f"{scope}-{period}",
            "scope": "all_vendors" if scope == "all" else "vendor",
            "vendor": None if scope == "all" else "self-hosted",
            "period": period,
            "limit": {"usd": limit_day if period == "day" else limit_month, **sourced},
        }
        for scope in ("all", "self-hosted")
        for period in ("day", "month")
    ]
    return CostConfig.model_validate(raw)


class TestBudgets:
    def test_a_lower_bound_over_the_limit_is_exceeded(self) -> None:
        budget = _budget(_priced(), "self-hosted-day")
        assert budget["spend_state"] == "lower_bound"
        assert budget["spend_usd"] == pytest.approx(96_000.0)
        assert budget["status"] == "exceeded"
        assert {"asr", "llm_talker", "llm_extraction"} <= set(budget["missing"])

    def test_a_lower_bound_under_the_limit_proves_nothing(self) -> None:
        budget = _budget(_priced(), "self-hosted-month")
        assert budget["spend_state"] == "lower_bound"
        assert budget["spend_usd"] == pytest.approx(2_160_000.0)
        assert budget["status"] == "not_evaluable"

    def test_no_known_spend_is_unknown_not_zero(self) -> None:
        budget = _budget(_priced(), "elevenlabs-month")
        assert budget["spend_state"] == "unknown"
        assert budget["spend_usd"] is None
        assert budget["status"] == "not_evaluable"

    def test_an_unset_limit_is_not_configured(self) -> None:
        budget = _budget(_priced(), "elevenlabs-day")
        assert budget["limit"]["state"] == "not_configured"
        assert budget["status"] == "not_configured"

    def test_the_all_vendor_budget_counts_unassigned_components(self) -> None:
        budget = _budget(_priced(), "all-vendors-day")
        assert "sms" in budget["missing"]  # priced nowhere, so the spend is a bound
        assert budget["status"] == "exceeded"

    def _single(self, limit_day: float, limit_month: float) -> Any:
        return compose_cost_payload(
            _single_vendor_config(limit_day, limit_month),
            config_ref="tests/fixtures/cost/inline",
            config_sha256="0" * 64,
            catalog=_catalog(),
            runner=recorded_runner(_recorded()),
        )

    def test_a_complete_spend_under_the_limit_is_within(self) -> None:
        payload = self._single(limit_day=100_000.0, limit_month=10_000_000.0)
        budget = _budget(payload, "self-hosted-day")
        assert budget["spend_state"] == "complete"
        assert budget["missing"] == []
        assert budget["status"] == "within"

    def test_near_miss_a_complete_spend_over_the_limit_is_exceeded(self) -> None:
        payload = self._single(limit_day=95_999.0, limit_month=10_000_000.0)
        assert _budget(payload, "self-hosted-day")["status"] == "exceeded"

    def test_a_complete_profile_total_is_shown(self) -> None:
        payload = self._single(limit_day=1.0, limit_month=1.0)
        rt = next(
            p for p in _window(payload, "day")["by_profile"] if p["profile"] == "residency_tr"
        )
        assert rt["state"] == "complete"
        assert rt["usd_per_session"] == pytest.approx(2400.0)


# --- the payload carries ids and states, never content (invariant 6) ---------------


class TestNoPhiAndNoInventedZero:
    def test_the_committed_state_carries_only_sourced_money(self) -> None:
        """INT-439 / D19: two list prices, each with its page and retrieval day,
        the owner's cap, and no spend figure while no usage source is configured."""
        payload = _compose(CONFIG_PATH, None)
        priced = {
            c["component"]: c["price"]
            for c in payload["components"]
            if c["price"]["state"] == "configured"
        }
        assert set(priced) == {
            "clip_synthesis",
            "gpu_host_onvizit_api",
            "hosted_llm_input",
            "hosted_llm_output",
            "hosted_asr_input",
            "hosted_asr_output",
        }
        for price in priced.values():
            assert price["url"].startswith("https://")
            assert price["source"] and price["as_of"] == "2026-10-03"
        for key, value in _walk(payload):
            if key in {"spend_usd", "usd_per_session", "total_usd"}:
                assert value is None, f"{key} carries {value!r} with no usage source"
        for budget in payload["budgets"]:
            assert budget["status"] == "not_configured"
        (cap,) = payload["spend_caps"]
        assert (cap["limit"]["usd"], cap["warn_at_usd"]) == (80.0, 64.0)
        assert cap["spend_usd"] is None and cap["status"] == "not_evaluable"

    def test_near_miss_an_unpriced_component_still_carries_no_money(self) -> None:
        payload = _compose(CONFIG_PATH, None)
        sms = next(c for c in payload["components"] if c["component"] == "sms")
        assert sms["price"] == {
            "state": "not_configured",
            "usd_per_unit": None,
            "source": None,
            "as_of": None,
            "url": None,
        }

    def test_every_identifier_is_id_shaped_and_no_key_is_a_phi_label(self) -> None:
        payload = _priced()
        for key, value in _walk(payload):
            assert key not in PHI_RISK_LABEL_NAMES
            assert key not in {"session_id", "session_key", "patient_id"}
            if key in {"component", "profile", "budget_id"} or (key == "vendor" and value):
                assert isinstance(value, str)
                assert value == value.lower() and " " not in value

    def test_every_figure_is_finite(self) -> None:
        for key, value in _walk(_priced()):
            if isinstance(value, float):
                assert math.isfinite(value), key


# --- the console fixtures are what this module computes ----------------------------


class TestFixturesAreRecordedFromTheModule:
    def test_the_committed_state_fixture(self) -> None:
        recorded = json.loads((FIXTURES / "cost.payload.json").read_text(encoding="utf-8"))
        assert recorded == _compose(CONFIG_PATH, None), (
            "apps/admin-web/e2e/fixtures/cost.payload.json drifted from the module; re-run "
            "uv run python scripts/dev/record_cost_fixture.py"
        )

    def test_the_priced_fixture(self) -> None:
        recorded = json.loads((FIXTURES / "cost.priced.payload.json").read_text(encoding="utf-8"))
        assert recorded == _priced()

    def test_every_recorded_response_is_a_query_the_module_sends(self) -> None:
        issued: list[str] = []
        _compose(PRICED_PATH, recorded_runner(_recorded(), issued))
        assert set(issued) == set(_recorded()), (
            "tests/fixtures/cost/prometheus_responses.json and the fixed query table disagree"
        )

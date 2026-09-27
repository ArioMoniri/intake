"""INT-190 — the unit-price and budget config, and its binding to the catalogue.

Acceptance, verbatim: *"per-session cost by component/vendor/profile; budgets +
alerts"*.

This file holds the half of the acceptance that is about *where a number may
come from*. A cost is a catalogued quantity times an owner-supplied price, so
two properties carry the whole module:

- **No price and no budget is ever invented.** ``infra/costs/unit-prices.yaml``
  is the only source of money. A value there is refused unless it names a
  ``source`` and an ``as_of`` date, and a ``source`` with no value is refused
  too — a half-filled row is a claim nobody made (files/HUMAN_BLOCKERS.md
  rule 1, HB-O8).
- **Every quantity is a catalogued series** (CLAUDE.md invariant 13). A usage
  row that names an uncatalogued series, reads a histogram as a counter,
  prices a unit the series does not count, or reads a vendor-labelled series
  without selecting its vendor is refused at load time, before any arithmetic.

Each refusal is paired with the near-miss the schema must accept.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml
from intake_platform.cost import (
    SESSIONS_METRIC,
    Attribution,
    CostConfig,
    CostConfigError,
    Profile,
    load_cost_config,
    resolve_components,
)
from intake_platform.slo import load_metrics_catalog
from pydantic import ValidationError

REPO = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO / "infra" / "costs" / "unit-prices.yaml"
PRICED_PATH = REPO / "tests" / "fixtures" / "cost" / "unit-prices.priced.yaml"
CATALOG_PATH = REPO / "observability" / "metrics_catalog.yaml"


def _raw(path: Path = CONFIG_PATH) -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded


def _with_component(raw: dict[str, Any], target: str, **overrides: Any) -> dict[str, Any]:
    changed = copy.deepcopy(raw)
    for index, row in enumerate(changed["components"]):
        if row["component"] == target:
            changed["components"][index] = {**row, **overrides}
    return changed


# --- the committed config ----------------------------------------------------------


class TestTheCommittedConfig:
    def test_it_loads_and_resolves_against_the_catalogue(self) -> None:
        config = load_cost_config(CONFIG_PATH)
        resolved = resolve_components(config, load_metrics_catalog(CATALOG_PATH))
        assert [r.component.component for r in resolved] == [
            row["component"] for row in _raw()["components"]
        ]

    def test_currency_is_the_catalogue_denomination(self) -> None:
        catalog = load_metrics_catalog(CATALOG_PATH)
        cost_row = next(m for m in catalog.metrics if m.name == "cost_per_session")
        assert load_cost_config(CONFIG_PATH).currency == cost_row.unit == "USD"

    def test_every_configured_value_names_its_source_and_date(self) -> None:
        # the durable property: it holds whether the owner has filled a row
        # or not, so filling one does not require editing this test
        config = load_cost_config(CONFIG_PATH)
        for component in config.components:
            if component.price.usd_per_unit is not None:
                assert component.price.source and component.price.as_of
        for budget in config.budgets:
            if budget.limit.usd is not None:
                assert budget.limit.source and budget.limit.as_of

    def test_profiles_are_the_two_invariant_19_leaves(self) -> None:
        from intake_voice_runtime.profiles import VoiceProfile

        assert {p.value for p in Profile} == {p.value for p in VoiceProfile}
        assert {p.value for p in Profile} == {"residency_tr", "typed"}

    def test_the_session_denominator_is_a_live_catalogued_counter(self) -> None:
        catalog = load_metrics_catalog(CATALOG_PATH)
        entry = next(m for m in catalog.metrics if m.name == SESSIONS_METRIC)
        assert entry.type == "counter"
        assert entry.status == "live"
        assert "profile" in entry.labels
        # a per-session identifier on a series would make its cardinality the
        # number of patients seen (invariant 6)
        assert not {"session", "session_id", "session_key"} & set(entry.labels)

    def test_every_vendor_has_a_day_and_a_month_budget(self) -> None:
        config = load_cost_config(CONFIG_PATH)
        vendors = {c.vendor for c in config.components if c.vendor is not None}
        assert vendors == {"self-hosted", "elevenlabs", "aws"}
        for vendor in vendors:
            periods = {b.period.value for b in config.budgets if b.vendor == vendor}
            assert periods == {"day", "month"}
        all_vendor = {b.period.value for b in config.budgets if b.scope.value == "all_vendors"}
        assert all_vendor == {"day", "month"}

    def test_attribution_is_derived_from_the_catalogued_labels(self) -> None:
        resolved = {
            r.component.component: r
            for r in resolve_components(
                load_cost_config(CONFIG_PATH), load_metrics_catalog(CATALOG_PATH)
            )
        }
        assert resolved["tts_dynamic"].attribution is Attribution.DIRECT
        assert resolved["sms"].attribution is Attribution.ALLOCATED
        assert resolved["gpu_host_onvizit_api"].attribution is Attribution.ALLOCATED
        # a planned series is carried with its status, never as live
        assert resolved["asr"].catalog_status == "planned"
        assert resolved["tts_dynamic"].catalog_status == "live"
        assert resolved["llm_extraction"].catalog_status is None


# --- schema: a value always travels with its source -------------------------------


class TestAValueTravelsWithItsSource:
    def test_a_price_without_a_source_is_refused(self) -> None:
        raw = _with_component(
            _raw(), "tts_dynamic", price={"usd_per_unit": 1.0, "source": None, "as_of": None}
        )
        with pytest.raises(ValidationError, match="source"):
            CostConfig.model_validate(raw)

    def test_a_source_without_a_price_is_refused(self) -> None:
        raw = _with_component(
            _raw(),
            "tts_dynamic",
            price={"usd_per_unit": None, "source": "invoice 1", "as_of": "2026-09-01"},
        )
        with pytest.raises(ValidationError, match="no value"):
            CostConfig.model_validate(raw)

    def test_a_negative_price_is_refused(self) -> None:
        raw = _with_component(
            _raw(),
            "tts_dynamic",
            price={"usd_per_unit": -1.0, "source": "credit note", "as_of": "2026-09-01"},
        )
        with pytest.raises(ValidationError, match="negative"):
            CostConfig.model_validate(raw)

    def test_near_miss_a_sourced_price_is_accepted(self) -> None:
        raw = _with_component(
            _raw(),
            "tts_dynamic",
            price={"usd_per_unit": 0.5, "source": "quote Q-1", "as_of": "2026-09-01"},
        )
        config = CostConfig.model_validate(raw)
        tts = next(c for c in config.components if c.component == "tts_dynamic")
        assert tts.price.usd_per_unit == 0.5

    def test_a_budget_limit_without_a_source_is_refused(self) -> None:
        raw = copy.deepcopy(_raw())
        raw["budgets"][0]["limit"] = {"usd": 10.0, "source": None, "as_of": None}
        with pytest.raises(ValidationError, match="source"):
            CostConfig.model_validate(raw)

    def test_a_currency_other_than_the_catalogue_unit_is_refused(self) -> None:
        raw = copy.deepcopy(_raw())
        raw["currency"] = "TRY"
        with pytest.raises(ValidationError):
            CostConfig.model_validate(raw)


# --- schema: the rows are ids, and the profile set is closed ----------------------


class TestIdsAndProfiles:
    def test_a_retired_profile_is_refused(self) -> None:
        # invariant 19: a reference to a retired profile is a defect
        retired = "cascade" + "_fast"
        raw = _with_component(_raw(), "llm_talker", profiles=["residency_tr", retired])
        with pytest.raises(ValidationError):
            CostConfig.model_validate(raw)

    def test_a_component_id_that_is_not_id_shaped_is_refused(self) -> None:
        raw = _with_component(_raw(), "sms", component="SMS reminders, all clinics")
        with pytest.raises(ValidationError, match="id-shaped"):
            CostConfig.model_validate(raw)

    def test_a_missing_vendor_must_say_why(self) -> None:
        raw = _with_component(_raw(), "sms", vendor_note=None)
        with pytest.raises(ValidationError, match="vendor_note"):
            CostConfig.model_validate(raw)

    def test_an_unmetered_component_must_say_why(self) -> None:
        raw = _with_component(_raw(), "llm_extraction", usage_note=None)
        with pytest.raises(ValidationError, match="usage_note"):
            CostConfig.model_validate(raw)

    def test_duplicate_component_ids_are_refused(self) -> None:
        raw = copy.deepcopy(_raw())
        raw["components"].append(copy.deepcopy(raw["components"][0]))
        with pytest.raises(ValidationError, match="duplicate"):
            CostConfig.model_validate(raw)


# --- schema: budgets cover every vendor --------------------------------------------


class TestBudgetsCoverEveryVendor:
    def test_a_vendor_without_a_month_budget_is_refused(self) -> None:
        raw = copy.deepcopy(_raw())
        raw["budgets"] = [b for b in raw["budgets"] if b["budget_id"] != "aws-month"]
        with pytest.raises(ValidationError, match="aws"):
            CostConfig.model_validate(raw)

    def test_a_budget_for_a_vendor_no_component_has_is_refused(self) -> None:
        raw = copy.deepcopy(_raw())
        raw["budgets"].append(
            {
                "budget_id": "nobody-day",
                "scope": "vendor",
                "vendor": "nobody",
                "period": "day",
                "limit": {"usd": None, "source": None, "as_of": None},
            }
        )
        with pytest.raises(ValidationError, match="nobody"):
            CostConfig.model_validate(raw)

    def test_an_all_vendor_budget_cannot_name_a_vendor(self) -> None:
        raw = copy.deepcopy(_raw())
        raw["budgets"][0]["vendor"] = "aws"
        with pytest.raises(ValidationError, match="all_vendors"):
            CostConfig.model_validate(raw)


# --- the catalogue binding (invariant 13) ------------------------------------------


class TestCatalogueBinding:
    def _resolve(self, raw: dict[str, Any]) -> None:
        resolve_components(CostConfig.model_validate(raw), load_metrics_catalog(CATALOG_PATH))

    def test_an_uncatalogued_usage_series_is_refused(self) -> None:
        usage = {"metric": "voice_tts_characters", "aggregation": "histogram_sum", "selector": {}}
        with pytest.raises(CostConfigError, match="not catalogued"):
            self._resolve(_with_component(_raw(), "tts_dynamic", usage=usage))

    def test_a_histogram_read_as_a_counter_is_refused(self) -> None:
        usage = {
            "metric": "voice_tts_chars",
            "aggregation": "counter_increase",
            "selector": {"vendor": "self-hosted"},
        }
        with pytest.raises(CostConfigError, match="histogram"):
            self._resolve(_with_component(_raw(), "tts_dynamic", usage=usage))

    def test_a_unit_the_series_does_not_count_is_refused(self) -> None:
        # voice_tts_chars counts characters; pricing it per token would
        # multiply the right quantity by the wrong rate
        with pytest.raises(CostConfigError, match="unit"):
            self._resolve(_with_component(_raw(), "tts_dynamic", unit="token"))

    def test_a_vendor_labelled_series_must_select_its_vendor(self) -> None:
        usage = {"metric": "voice_tts_chars", "aggregation": "histogram_sum", "selector": {}}
        with pytest.raises(CostConfigError, match="vendor"):
            self._resolve(_with_component(_raw(), "tts_dynamic", usage=usage))

    def test_a_selector_label_the_series_does_not_carry_is_refused(self) -> None:
        usage = {
            "metric": "notification_dispatch_total",
            "aggregation": "counter_increase",
            "selector": {"channel": "sms", "tenant": "t1"},
        }
        with pytest.raises(CostConfigError, match="tenant"):
            self._resolve(_with_component(_raw(), "sms", usage=usage))

    def test_a_profile_labelled_series_needs_its_profiles_declared(self) -> None:
        with pytest.raises(CostConfigError, match="profile"):
            self._resolve(_with_component(_raw(), "tts_dynamic", profiles=[]))

    def test_an_unlabelled_series_cannot_be_directly_attributed(self) -> None:
        with pytest.raises(CostConfigError, match="profile"):
            self._resolve(_with_component(_raw(), "sms", profiles=["typed"]))

    def test_near_miss_the_priced_fixture_resolves(self) -> None:
        resolved = resolve_components(
            load_cost_config(PRICED_PATH), load_metrics_catalog(CATALOG_PATH)
        )
        assert {r.component.component for r in resolved} == {
            row["component"] for row in _raw()["components"]
        }

"""INT-021 — SLO-as-code schema gates (CLAUDE.md inv. 13/15; files/10 §6).

Pinned here:
- observability/metrics_catalog.yaml validates against the shared pydantic
  schema: known types only, unique names, and label names that can never carry
  PHI (``name``/``phone``/``tckn``/``text``/``transcript``-class labels are
  rejected at the schema, inv. 6).
- Every directory under services/ has docs/slo/<service>.yaml; every SLO file
  validates and its filename matches its ``service`` field.
- Every metric an SLI references exists in the catalogue, and every metric the
  platform actually serves over /metrics is catalogued — emit-without-catalogue
  fails CI (inv. 13; files/03 §19).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from intake_platform.health import mount_health
from intake_platform.metrics import mount_http_metrics
from intake_platform.slo import (
    PHI_RISK_LABEL_NAMES,
    MetricsCatalog,
    SLOFile,
    load_metrics_catalog,
    load_slo_file,
    window_seconds,
)
from prometheus_client.parser import text_string_to_metric_families
from pydantic import ValidationError

REPO = Path(__file__).resolve().parents[2]
CATALOG_PATH = REPO / "observability" / "metrics_catalog.yaml"
SLO_DIR = REPO / "docs" / "slo"
SERVICES_ROOT = REPO / "services"


def _catalog() -> MetricsCatalog:
    return load_metrics_catalog(CATALOG_PATH)


def _slo_paths() -> list[Path]:
    return sorted(SLO_DIR.glob("*.yaml"))


def _metric(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "name": "http_requests_total",
        "type": "counter",
        "labels": ["service", "method", "route", "status"],
        "owner": "platform",
        "unit": "count",
        "description": "HTTP requests handled, by route template and status.",
    }
    base.update(overrides)
    return base


def _slo_file(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "service": "api",
        "owner": "platform",
        "slos": [
            {
                "name": "availability",
                "sli": 'sum(rate(http_requests_total{service="api",status=~"5.."}[5m]))'
                ' / sum(rate(http_requests_total{service="api"}[5m]))',
                "objective": 99.9,
                "window": "28d",
                "burn_rate_alerts": {
                    "fast": {
                        "factor": 14.4,
                        "long_window": "1h",
                        "short_window": "5m",
                        "for_duration": "2m",
                        "severity": "page",
                    },
                    "slow": {
                        "factor": 6.0,
                        "long_window": "6h",
                        "short_window": "30m",
                        "for_duration": "15m",
                        "severity": "page",
                    },
                },
            }
        ],
    }
    base.update(overrides)
    return base


# --- the catalogue itself ---------------------------------------------------------


def test_catalog_exists_and_validates() -> None:
    catalog = _catalog()
    assert catalog.metrics, "the catalogue must not be empty"
    assert "http_requests_total" in catalog.names
    assert "http_request_duration_seconds" in catalog.names


def test_catalog_schema_rejects_duplicate_names() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        MetricsCatalog.model_validate({"metrics": [_metric(), _metric()]})


def test_catalog_schema_rejects_unknown_type() -> None:
    with pytest.raises(ValidationError):
        MetricsCatalog.model_validate({"metrics": [_metric(type="summary")]})


@pytest.mark.parametrize("label", ["name", "phone", "tckn", "text", "transcript"])
def test_catalog_schema_rejects_phi_risk_label_names(label: str) -> None:
    assert label in PHI_RISK_LABEL_NAMES
    with pytest.raises(ValidationError, match="PHI-risk"):
        MetricsCatalog.model_validate({"metrics": [_metric(labels=[label])]})


def test_catalog_schema_rejects_a_list_document() -> None:
    with pytest.raises(ValidationError):
        MetricsCatalog.model_validate([_metric()])


def test_histogram_suffixes_resolve_to_the_catalogued_family() -> None:
    catalog = _catalog()
    assert catalog.covers("http_request_duration_seconds_bucket")
    assert catalog.covers("http_request_duration_seconds_count")
    assert catalog.covers("http_request_duration_seconds_sum")
    # a counter must not be reachable through histogram suffixes
    assert not catalog.covers("http_requests_total_bucket")
    assert not catalog.covers("never_registered_series")


# --- SLO files --------------------------------------------------------------------


def test_every_service_dir_has_an_slo_file() -> None:
    if not SERVICES_ROOT.is_dir():
        # No service package has landed yet (services/api arrives with its own
        # issue); the gate binds the moment the first directory appears.
        return
    names = sorted(
        p.name for p in SERVICES_ROOT.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))
    )
    missing = [n for n in names if not (SLO_DIR / f"{n}.yaml").is_file()]
    assert missing == [], f"services without docs/slo/<service>.yaml: {missing}"


def test_slo_files_validate_and_match_their_filename() -> None:
    paths = _slo_paths()
    assert paths, "docs/slo/ must hold at least the api SLO file"
    for path in paths:
        slo_file = load_slo_file(path)
        assert slo_file.service == path.stem
        assert slo_file.slos


def test_api_slo_file_declares_availability_and_latency() -> None:
    api = load_slo_file(SLO_DIR / "api.yaml")
    names = {slo.name for slo in api.slos}
    assert {"availability", "latency"} <= names
    for slo in api.slos:
        assert slo.window == "28d"
        assert 0.0 < slo.objective < 100.0


def test_sli_expressions_reference_only_catalogued_metrics() -> None:
    catalog = _catalog()
    for path in _slo_paths():
        for slo in load_slo_file(path).slos:
            unknown = catalog.unknown_references(slo.sli)
            assert unknown == frozenset(), f"{path.name}:{slo.name} references {sorted(unknown)}"


# --- SLO schema negative controls -------------------------------------------------


def test_slo_schema_rejects_objective_bounds() -> None:
    for objective in (0.0, 100.0, 120.0):
        bad = _slo_file()
        bad["slos"][0]["objective"] = objective
        with pytest.raises(ValidationError):
            SLOFile.model_validate(bad)


def test_slo_schema_rejects_sli_without_base_range() -> None:
    bad = _slo_file()
    bad["slos"][0]["sli"] = 'sum(rate(http_requests_total{service="api"}[1h]))'
    with pytest.raises(ValidationError, match=r"\[5m\]"):
        SLOFile.model_validate(bad)


def test_slo_schema_requires_fast_and_slow_alerts() -> None:
    bad = _slo_file()
    del bad["slos"][0]["burn_rate_alerts"]["slow"]
    with pytest.raises(ValidationError):
        SLOFile.model_validate(bad)


def test_slo_schema_pins_page_and_ticket_severities() -> None:
    bad = _slo_file()
    bad["slos"][0]["burn_rate_alerts"]["fast"]["severity"] = "ticket"
    with pytest.raises(ValidationError, match="page"):
        SLOFile.model_validate(bad)


def test_slo_schema_rejects_short_window_not_shorter_than_long() -> None:
    bad = _slo_file()
    bad["slos"][0]["burn_rate_alerts"]["fast"]["short_window"] = "2h"
    with pytest.raises(ValidationError, match="short"):
        SLOFile.model_validate(bad)


def test_window_seconds_orders_and_rejects() -> None:
    assert window_seconds("5m") < window_seconds("1h") < window_seconds("3d")
    with pytest.raises(ValueError, match="window"):
        window_seconds("4w")


# --- inv. 13: emit-without-catalogue fails ----------------------------------------


def test_every_emitted_metric_family_is_catalogued() -> None:
    catalog = _catalog()
    app = FastAPI()
    mount_health(app)
    mount_http_metrics(app, "catalog_gate")
    client = TestClient(app)
    assert client.get("/healthz").status_code == 200
    exposition = client.get("/metrics").text
    uncatalogued: list[str] = []
    for family in text_string_to_metric_families(exposition):
        candidates = {family.name}
        if family.type == "counter":
            candidates.add(f"{family.name}_total")
        if not any(catalog.covers(name) for name in candidates):
            uncatalogued.append(family.name)
    assert uncatalogued == [], (
        "series served on /metrics but absent from observability/metrics_catalog.yaml "
        f"(inv. 13): {sorted(uncatalogued)}"
    )

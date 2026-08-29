"""INT-240 — services/metrics satisfies the monitoring contract (invariant 15).

*"every service exposes /healthz, /readyz, /metrics, /version via
packages/intake_platform/health, emits OTel through the shared setup, declares
its SLOs in docs/slo/<service>.yaml, and has a synthetic probe; a new service
without these fails make check"*.

The readiness check is the honest part, on the INT-091 precedent: the rollup
job reads the ``events`` table, and this branch does not deploy the service, so
``/readyz`` names its database dependency and reports **not ready** when the
URL is unset rather than answering healthy on a process that can roll nothing
up. The registry row says ``self_hosted_now: false`` for the same reason.

Invariant 20 gets its own gate here: the four satisfaction series carry
measurements, so no CSAT/NPS figure may appear in docs/regulatory/ or
docs/legal/ — the scan below is that rule made executable for this issue's
own vocabulary.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from intake_metrics.app import create_app
from intake_platform.health import discover_services, verify_service_declarations
from intake_platform.slo import load_metrics_catalog, load_slo_file
from intake_probes.registry import ProbeId, load_registry

REPO = Path(__file__).resolve().parents[2]
SERVICE_DIR = REPO / "services" / "metrics"
SLO_PATH = REPO / "docs" / "slo" / "metrics.yaml"
CATALOG_PATH = REPO / "observability" / "metrics_catalog.yaml"
REGISTRY_PATH = REPO / "observability" / "registry.yaml"

#: The four ids files/08 §4 group F names for satisfaction.
GROUP_F_IDS = ("csat.score", "csat.reason", "nps.monthly", "clinician.pulse")


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app(), raise_server_exceptions=False)


# --- the four endpoints -------------------------------------------------------------


def test_healthz_is_alive(client: TestClient) -> None:
    assert client.get("/healthz").json() == {"status": "alive"}


def test_version_returns_the_three_build_fields(client: TestClient) -> None:
    assert set(client.get("/version").json()) == {"git_sha", "built_at", "sbom_digest"}


def test_metrics_serves_prometheus_exposition(client: TestClient) -> None:
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]


def test_readyz_names_its_database_dependency_and_fails_closed(client: TestClient) -> None:
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["checks"] == {"events_db": "error"}


def test_http_metrics_carry_the_metrics_service_label(client: TestClient) -> None:
    client.get("/healthz")
    exposition = client.get("/metrics").text
    assert 'service="metrics"' in exposition


# --- declaration, workspace and build wiring -----------------------------------------


def test_the_service_declares_its_health_app_and_probe() -> None:
    declaration = next(
        service for service in discover_services(REPO / "services") if service.name == "metrics"
    )
    verify_service_declarations(declaration)
    assert declaration.health == "intake_metrics.app:create_app"
    assert declaration.probe == "metrics.http"


def test_the_service_is_a_workspace_member_and_a_mypy_root() -> None:
    root = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    assert "services/metrics" in root["tool"]["uv"]["workspace"]["members"]
    assert "services/metrics/src" in root["tool"]["mypy"]["files"]
    assert root["tool"]["uv"]["sources"]["intake-metrics"] == {"workspace": True}
    assert "intake-metrics" in root["project"]["dependencies"]


def test_check_py_type_checks_and_covers_the_new_service() -> None:
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    assert "services/metrics/src" in makefile
    assert "--cov=services/metrics/src --cov-branch --cov-fail-under=90" in makefile


def test_the_slo_file_exists_and_matches_its_filename() -> None:
    slo_file = load_slo_file(SLO_PATH)
    assert slo_file.service == "metrics"
    assert {slo.name for slo in slo_file.slos} == {"availability"}


def test_every_slo_reference_is_catalogued() -> None:
    catalog = load_metrics_catalog(CATALOG_PATH)
    for slo in load_slo_file(SLO_PATH).slos:
        assert catalog.unknown_references(slo.sli) == frozenset()


def test_the_registry_carries_a_probed_metrics_row() -> None:
    entry = next(row for row in load_registry(REGISTRY_PATH) if row.component == "metrics")
    assert entry.probe is ProbeId.HTTP_HEALTH
    assert entry.self_hostable is True
    assert entry.self_hosted_now is False
    # rollups are counts and scores; the free text never reaches this service
    assert entry.phi_path is False


# --- invariant 13: the four group-F series are catalogued and now honest -------------


def test_the_group_f_series_are_catalogued_as_live_now_that_they_are_emitted() -> None:
    catalog = load_metrics_catalog(CATALOG_PATH)
    by_id = {metric.spec_id: metric for metric in catalog.metrics}
    for spec_id in GROUP_F_IDS:
        assert by_id[spec_id].status == "live", f"{spec_id} is emitted; the catalogue must say so"


def test_no_label_on_a_satisfaction_series_can_carry_free_text() -> None:
    catalog = load_metrics_catalog(CATALOG_PATH)
    by_id = {metric.spec_id: metric for metric in catalog.metrics}
    assert list(by_id["csat.reason"].labels) == ["reason"]
    for spec_id in ("csat.score", "nps.monthly", "clinician.pulse"):
        assert list(by_id[spec_id].labels) == []


# --- invariant 20: a figure is never a property of the product -----------------------

#: An NPS/CSAT figure claimed as a property rather than reported as a
#: measurement: "NPS 62", "CSAT of 4.6", "%92 memnuniyet".
_CLAIM_PATTERNS = (
    re.compile(r"\b(?:NPS|CSAT)\b[^.\n]{0,20}?\b\d+(?:[.,]\d+)?", re.IGNORECASE),
    re.compile(r"[%\d][\d.,]*\s*(?:memnuniyet|satisfaction)", re.IGNORECASE),
)


@pytest.mark.parametrize("tree", ["regulatory", "legal"])
def test_no_satisfaction_figure_appears_in_the_regulatory_or_legal_trees(tree: str) -> None:
    root = REPO / "docs" / tree
    if not root.is_dir():
        return
    offenders: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".md", ".yaml", ".yml", ".txt"}:
            continue
        body = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in _CLAIM_PATTERNS:
            offenders.extend(
                f"{path.relative_to(REPO)}: {match.group(0)!r}" for match in pattern.finditer(body)
            )
    assert offenders == [], f"invariant 20 — satisfaction figures in docs/{tree}: {offenders}"

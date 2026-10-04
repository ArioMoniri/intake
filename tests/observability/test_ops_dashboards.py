"""INT-481 — the staff Grafana's operations dashboards are code, and honest.

- The committed JSON under infra/observability/grafana/ops-dashboards/ equals
  what :func:`intake_platform.ops_dashboards.ops_dashboards` renders from
  docs/slo, file for file, with no stray file (drift gate).
- Every expression reads a catalogued series, an ``slo:`` recording rule the
  committed SLO rules define, or Prometheus's own ``ALERTS`` — nothing a dashboard
  reads is ungoverned (invariant 13).
- Every SLO in docs/slo has its budget panel, and the budget follows the
  objective: change one and the dashboard changes.
- The triage dashboard is aggregate only: it never groups by tenant or rule.
- Every dashboard carries the deploy markers, read from the family deploy.sh
  writes, and the home dashboard Grafana opens exists.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from intake_platform.alert_rules import iter_rules, promql_series
from intake_platform.observability.labels import dashboard_label_keys
from intake_platform.ops_dashboards import (
    DASHBOARD_DIR,
    DEPLOY_MARKER,
    dashboard_filename,
    ops_dashboards,
    render_dashboard,
    slo_budget_expr,
)
from intake_platform.slo import SLOFile, load_metrics_catalog, load_slo_file

REPO = Path(__file__).resolve().parents[2]
DASHBOARDS = REPO / DASHBOARD_DIR
CATALOG_PATH = REPO / "observability" / "metrics_catalog.yaml"
SLO_RULES = REPO / "infra" / "observability" / "prometheus-rules.yaml"
OBS_COMPOSE = REPO / "infra" / "staging" / "compose.obs.yaml"
LIB = REPO / "infra" / "staging" / "lib.sh"
#: Series Prometheus synthesises itself; nothing emits them and the catalogue
#: has no entry for them.
PROMETHEUS_SYNTHETIC = frozenset({"ALERTS"})


def _slo_files() -> list[SLOFile]:
    return [load_slo_file(path) for path in sorted((REPO / "docs" / "slo").glob("*.yaml"))]


def _generated() -> dict[str, dict[str, Any]]:
    return ops_dashboards(_slo_files())


def _committed(slug: str) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(
        (DASHBOARDS / dashboard_filename(slug)).read_text(encoding="utf-8")
    )
    return loaded


def _exprs(dashboard: dict[str, Any]) -> list[str]:
    exprs = [target["expr"] for panel in dashboard["panels"] for target in panel["targets"]]
    exprs.extend(annotation["expr"] for annotation in dashboard["annotations"]["list"])
    return exprs


def test_committed_dashboards_are_the_generated_ones() -> None:
    for slug, dashboard in _generated().items():
        path = DASHBOARDS / dashboard_filename(slug)
        assert path.is_file(), f"{path.name} is not committed: run ops_dashboards.py --emit"
        assert path.read_text(encoding="utf-8") == render_dashboard(dashboard), (
            f"{path.name} drifted: run scripts/observability/ops_dashboards.py --emit"
        )


def test_no_stray_dashboard_in_the_directory() -> None:
    expected = {dashboard_filename(slug) for slug in _generated()}
    assert {path.name for path in DASHBOARDS.glob("*.json")} == expected


def test_every_expression_reads_governed_series_only() -> None:
    catalog = load_metrics_catalog(CATALOG_PATH)
    records = frozenset(
        str(rule["record"]) for _, rule in iter_rules(SLO_RULES) if "record" in rule
    )
    problems: list[str] = []
    for slug, dashboard in _generated().items():
        for expr in _exprs(dashboard):
            for series in promql_series(expr):
                if series in PROMETHEUS_SYNTHETIC or series in records:
                    continue
                if ":" in series or not catalog.covers(series):
                    problems.append(f"{slug}: {series}")
    assert problems == []


def test_near_miss_an_uncatalogued_series_would_be_caught() -> None:
    catalog = load_metrics_catalog(CATALOG_PATH)
    assert not catalog.covers("node_memory_MemTotal_bytes"), "only the lower-cased name is stored"
    assert catalog.covers("node_memory_memtotal_bytes")


def test_every_slo_has_a_budget_panel() -> None:
    exprs = _exprs(_generated()["slo-latency"])
    for slo_file in _slo_files():
        for slo in slo_file.slos:
            assert slo_budget_expr(slo) in exprs, f"{slo_file.service}/{slo.name}"


def test_the_api_availability_budget_is_the_slo_over_its_window() -> None:
    api = next(slo_file for slo_file in _slo_files() if slo_file.service == "api")
    availability = next(slo for slo in api.slos if slo.name == "availability")
    assert slo_budget_expr(availability) == (
        '1 - ((sum(rate(http_requests_total{service="api",status=~"5.."}[28d])) / '
        'sum(rate(http_requests_total{service="api"}[28d]))) / 0.001)'
    )


def test_near_miss_a_changed_objective_changes_the_dashboard() -> None:
    files = _slo_files()
    api = next(index for index, slo_file in enumerate(files) if slo_file.service == "api")
    changed = files[api].model_copy(deep=True)
    changed.slos[0] = changed.slos[0].model_copy(update={"objective": 99.5})
    files[api] = changed
    assert render_dashboard(ops_dashboards(files)["slo-latency"]) != render_dashboard(
        _committed("slo-latency")
    )


def test_the_triage_dashboard_is_aggregate_only() -> None:
    keys = dashboard_label_keys(_generated()["triage-safety"])
    assert not keys & {"tenant", "rule", "actor"}


def test_every_dashboard_is_locked_and_reads_the_provisioned_datasource() -> None:
    for slug, dashboard in _generated().items():
        assert dashboard["editable"] is False, slug
        assert dashboard["uid"] == f"intake-ops-{slug}"
        for panel in dashboard["panels"]:
            assert panel["datasource"] == {"type": "prometheus", "uid": "prometheus"}, slug


def test_every_dashboard_carries_the_deploy_markers() -> None:
    catalog = load_metrics_catalog(CATALOG_PATH)
    assert catalog.covers(DEPLOY_MARKER)
    assert DEPLOY_MARKER in LIB.read_text(encoding="utf-8"), "lib.sh writes the markers"
    for slug, dashboard in _generated().items():
        stages = {
            annotation["name"]
            for annotation in dashboard["annotations"]["list"]
            if DEPLOY_MARKER in annotation["expr"]
        }
        assert stages == {"Deploy started", "Deploy completed"}, slug


def test_the_home_dashboard_grafana_opens_exists() -> None:
    grafana = yaml.safe_load(OBS_COMPOSE.read_text(encoding="utf-8"))["services"]["grafana"]
    home = grafana["environment"]["GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH"]
    assert home.startswith("/etc/grafana/dashboards/ops/")
    assert (DASHBOARDS / Path(home).name).is_file()

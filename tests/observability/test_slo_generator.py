"""INT-021 — rules, dashboard and runbook are generated-consistent with the SLO file.

The acceptance's "generator emits Prometheus rules" is enforced structurally:
infra/observability/prometheus-rules.yaml must equal, group for group, what
``intake_platform.slo.prometheus_rule_groups`` derives from docs/slo/api.yaml.
A hand edit to either side fails here. On top of the equality this file pins
the Google SRE workbook shape (fast 14.4x over 1h+5m, slow 6x over 6h+30m,
both paging; ticket 1x over 3d+6h), that every alert's runbook link resolves
to a real heading in docs/runbooks/slo-burn.md, and that the Grafana
dashboard is valid JSON referencing only catalogued series or slo: records.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml
from intake_platform.slo import (
    alert_rule_name,
    load_metrics_catalog,
    load_slo_file,
    metric_references,
    prometheus_rule_groups,
    recording_rule_name,
)

REPO = Path(__file__).resolve().parents[2]
CATALOG_PATH = REPO / "observability" / "metrics_catalog.yaml"
API_SLO_PATH = REPO / "docs" / "slo" / "api.yaml"
RULES_PATH = REPO / "infra" / "observability" / "prometheus-rules.yaml"
DASHBOARD_PATH = REPO / "infra" / "observability" / "grafana" / "api-slo-dashboard.json"
RUNBOOK_PATH = REPO / "docs" / "runbooks" / "slo-burn.md"
RUNBOOK_REL = "docs/runbooks/slo-burn.md"

_RECORD_REF_RE = re.compile(r"slo:[a-z0-9_]+:[a-z0-9_]+")


def _committed_rules() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(RULES_PATH.read_text(encoding="utf-8"))
    return loaded


def _rules(kind: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for group in _committed_rules()["groups"]:
        for rule in group["rules"]:
            if kind in rule:
                out[rule[kind]] = rule
    return out


def _slugify(heading: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s-]", "", heading.lower())
    return re.sub(r"\s+", "-", cleaned.strip())


# --- workbook shape ---------------------------------------------------------------


def test_burn_rate_policy_matches_the_workbook_shape() -> None:
    api = load_slo_file(API_SLO_PATH)
    for slo in api.slos:
        alerts = slo.burn_rate_alerts
        assert (alerts.fast.factor, alerts.fast.long_window, alerts.fast.short_window) == (
            14.4,
            "1h",
            "5m",
        )
        assert alerts.fast.severity == "page"
        assert (alerts.slow.factor, alerts.slow.long_window, alerts.slow.short_window) == (
            6.0,
            "6h",
            "30m",
        )
        assert alerts.slow.severity == "page"
        assert alerts.ticket is not None
        assert (
            alerts.ticket.factor,
            alerts.ticket.long_window,
            alerts.ticket.short_window,
            alerts.ticket.severity,
        ) == (1.0, "3d", "6h", "ticket")


# --- rules file bound to the SLO file ---------------------------------------------


def test_committed_rules_equal_generated_rules() -> None:
    api = load_slo_file(API_SLO_PATH)
    assert _committed_rules() == prometheus_rule_groups(api, RUNBOOK_REL)


def test_every_slo_has_recording_rules_and_burn_alerts() -> None:
    api = load_slo_file(API_SLO_PATH)
    records = _rules("record")
    alerts = _rules("alert")
    for slo in api.slos:
        for kind, alert in slo.burn_rate_alerts.named_alerts():
            long_rule = recording_rule_name(api.service, slo.name, alert.long_window)
            short_rule = recording_rule_name(api.service, slo.name, alert.short_window)
            assert long_rule in records
            assert short_rule in records
            name = alert_rule_name(api.service, slo.name, kind)
            assert name in alerts, f"missing burn-rate alert {name}"
            rule = alerts[name]
            assert long_rule in rule["expr"] and short_rule in rule["expr"]
            assert rule["labels"]["severity"] == alert.severity
            assert rule["labels"]["service"] == api.service
            assert rule["for"] == alert.for_duration


def test_recording_rule_exprs_reference_only_catalogued_metrics() -> None:
    catalog = load_metrics_catalog(CATALOG_PATH)
    for name, rule in _rules("record").items():
        unknown = catalog.unknown_references(rule["expr"])
        assert unknown == frozenset(), f"{name} references {sorted(unknown)}"


# --- runbook ----------------------------------------------------------------------


def test_every_alert_links_a_runbook_heading() -> None:
    headings = {
        _slugify(line.lstrip("#").strip())
        for line in RUNBOOK_PATH.read_text(encoding="utf-8").splitlines()
        if line.startswith("#")
    }
    alerts = _rules("alert")
    assert alerts
    for name, rule in alerts.items():
        runbook = rule["annotations"]["runbook"]
        assert runbook.startswith(f"{RUNBOOK_REL}#"), f"{name} runbook link: {runbook}"
        anchor = runbook.split("#", 1)[1]
        assert anchor in headings, f"{name}: no heading in {RUNBOOK_REL} slugs to {anchor}"


# --- dashboard --------------------------------------------------------------------


def _dashboard_exprs() -> list[str]:
    dashboard = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
    panels = dashboard["panels"]
    assert panels, "dashboard must define panels"
    exprs: list[str] = []
    for panel in panels:
        for target in panel.get("targets", []):
            exprs.append(target["expr"])
    assert exprs, "dashboard panels must define Prometheus targets"
    return exprs


def test_dashboard_references_only_catalogued_series_or_slo_records() -> None:
    catalog = load_metrics_catalog(CATALOG_PATH)
    records = _rules("record")
    for expr in _dashboard_exprs():
        for ref in sorted(metric_references(expr)):
            assert catalog.covers(ref), f"dashboard references uncatalogued series {ref!r}"
        for match in _RECORD_REF_RE.finditer(expr):
            assert match.group(0) in records, f"dashboard references unknown {match.group(0)!r}"


def test_dashboard_covers_every_slo() -> None:
    api = load_slo_file(API_SLO_PATH)
    joined = "\n".join(_dashboard_exprs())
    for slo in api.slos:
        assert f"slo:{api.service}_{slo.name}:" in joined, f"no panel for SLO {slo.name}"

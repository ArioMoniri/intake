"""INT-021 — rules, dashboards and runbooks are generated-consistent with EVERY SLO file.

The acceptance's "generator emits Prometheus rules" is enforced structurally:
infra/observability/prometheus-rules.yaml must equal, group for group, what
``intake_platform.slo.prometheus_rule_groups`` derives from every
docs/slo/*.yaml — not only api.yaml, which is all the file held until the
INT-021 close-out (six SLO files had objectives and no alert). Likewise every
SLO file has a golden-signal dashboard under
infra/observability/grafana/dashboards/, equal to what
``intake_platform.slo_dashboards.slo_dashboard`` derives. A hand edit to
either side fails here.

On top of the equality this file pins the Google SRE workbook shape for every
SLO (fast 14.4x over 1h+5m, slow 6x over 6h+30m, both paging; ticket 1x over
3d+6h — files/10 §6), that every burn alert's runbook link resolves to a real
heading in docs/runbooks/slo-burn.md, and that every dashboard panel reads only
catalogued series or ``slo:`` recording rules the rules file defines.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from intake_platform.alert_rules import markdown_anchors, promql_series
from intake_platform.slo import (
    SLOFile,
    alert_rule_name,
    load_metrics_catalog,
    load_slo_file,
    prometheus_rule_groups,
    recording_rule_name,
    render_prometheus_rules,
)
from intake_platform.slo_dashboards import (
    DASHBOARD_DIR,
    dashboard_filename,
    render_dashboard,
    slo_dashboard,
)

REPO = Path(__file__).resolve().parents[2]
CATALOG_PATH = REPO / "observability" / "metrics_catalog.yaml"
SLO_DIR = REPO / "docs" / "slo"
RULES_PATH = REPO / "infra" / "observability" / "prometheus-rules.yaml"
DASHBOARDS = REPO / DASHBOARD_DIR
RUNBOOK_PATH = REPO / "docs" / "runbooks" / "slo-burn.md"
RUNBOOK_REL = "docs/runbooks/slo-burn.md"


def _slo_files() -> list[SLOFile]:
    return [load_slo_file(path) for path in sorted(SLO_DIR.glob("*.yaml"))]


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


# --- workbook shape ---------------------------------------------------------------


def test_every_slo_file_is_loaded() -> None:
    services = [slo_file.service for slo_file in _slo_files()]
    assert services == [
        "api",
        "langfuse",
        "learning",
        "metrics",
        "probes",
        "siem",
        "voice-runtime",
    ]


def test_burn_rate_policy_matches_the_workbook_shape_everywhere() -> None:
    for slo_file in _slo_files():
        for slo in slo_file.slos:
            where = f"{slo_file.service}/{slo.name}"
            alerts = slo.burn_rate_alerts
            assert (alerts.fast.factor, alerts.fast.long_window, alerts.fast.short_window) == (
                14.4,
                "1h",
                "5m",
            ), where
            assert alerts.fast.severity == "page", where
            assert (alerts.slow.factor, alerts.slow.long_window, alerts.slow.short_window) == (
                6.0,
                "6h",
                "30m",
            ), where
            assert alerts.slow.severity == "page", where
            assert alerts.ticket is not None, where
            assert (
                alerts.ticket.factor,
                alerts.ticket.long_window,
                alerts.ticket.short_window,
                alerts.ticket.severity,
            ) == (1.0, "3d", "6h", "ticket"), where


# --- rules file bound to the SLO files --------------------------------------------


def test_committed_rules_equal_generated_rules_for_every_slo_file() -> None:
    expected: list[dict[str, object]] = []
    for slo_file in _slo_files():
        expected.extend(prometheus_rule_groups(slo_file, RUNBOOK_REL)["groups"])
    assert _committed_rules() == {"groups": expected}


def test_committed_rules_text_is_the_rendered_text() -> None:
    body = RULES_PATH.read_text(encoding="utf-8").split("groups:", 1)[1]
    assert "groups:" + body == render_prometheus_rules(_slo_files(), RUNBOOK_REL)


def test_a_rules_file_rendered_from_one_slo_file_is_not_the_committed_one() -> None:
    # near-miss control: the pre-close-out state (api.yaml only) fails the gate
    api_only = prometheus_rule_groups(load_slo_file(SLO_DIR / "api.yaml"), RUNBOOK_REL)
    assert _committed_rules() != api_only


def test_every_slo_has_recording_rules_and_burn_alerts() -> None:
    records = _rules("record")
    alerts = _rules("alert")
    for slo_file in _slo_files():
        for slo in slo_file.slos:
            for kind, alert in slo.burn_rate_alerts.named_alerts():
                long_rule = recording_rule_name(slo_file.service, slo.name, alert.long_window)
                short_rule = recording_rule_name(slo_file.service, slo.name, alert.short_window)
                assert long_rule in records
                assert short_rule in records
                name = alert_rule_name(slo_file.service, slo.name, kind)
                assert name in alerts, f"missing burn-rate alert {name}"
                rule = alerts[name]
                assert long_rule in rule["expr"] and short_rule in rule["expr"]
                assert rule["labels"]["severity"] == alert.severity
                assert rule["labels"]["service"] == slo_file.service
                assert rule["for"] == alert.for_duration


def test_recording_rule_exprs_reference_only_catalogued_metrics() -> None:
    catalog = load_metrics_catalog(CATALOG_PATH)
    for name, rule in _rules("record").items():
        unknown = [ref for ref in promql_series(rule["expr"]) if not catalog.covers(ref)]
        assert unknown == [], f"{name} references {sorted(unknown)}"


# --- runbook ----------------------------------------------------------------------


def test_every_burn_alert_links_a_heading_in_the_burn_runbook() -> None:
    anchors = markdown_anchors(RUNBOOK_PATH.read_text(encoding="utf-8"))
    alerts = _rules("alert")
    assert len(alerts) == 3 * sum(len(f.slos) for f in _slo_files())
    for name, rule in alerts.items():
        runbook = rule["annotations"]["runbook"]
        assert runbook.startswith(f"{RUNBOOK_REL}#"), f"{name} runbook link: {runbook}"
        anchor = runbook.split("#", 1)[1]
        assert anchor in anchors, f"{name}: no heading in {RUNBOOK_REL} slugs to {anchor}"


# --- dashboards -------------------------------------------------------------------


def test_every_slo_file_has_its_committed_generated_dashboard() -> None:
    for slo_file in _slo_files():
        path = DASHBOARDS / dashboard_filename(slo_file.service)
        assert path.is_file(), f"no dashboard for {slo_file.service}"
        assert path.read_text(encoding="utf-8") == render_dashboard(slo_dashboard(slo_file)), (
            f"{path.name} drifted from docs/slo/{slo_file.service}.yaml — re-emit with "
            "scripts/observability/slo_report.py --emit-dashboards"
        )


def test_no_dashboard_without_an_slo_file() -> None:
    expected = {dashboard_filename(f.service) for f in _slo_files()}
    assert {path.name for path in DASHBOARDS.glob("*.json")} == expected


def _exprs(dashboard: dict[str, Any]) -> list[str]:
    exprs = [target["expr"] for panel in dashboard["panels"] for target in panel["targets"]]
    assert exprs, f"{dashboard['uid']} has no Prometheus targets"
    return exprs


def test_dashboards_reference_only_catalogued_series_or_slo_records() -> None:
    catalog = load_metrics_catalog(CATALOG_PATH)
    records = _rules("record")
    for path in sorted(DASHBOARDS.glob("*.json")):
        for expr in _exprs(json.loads(path.read_text(encoding="utf-8"))):
            for ref in sorted(promql_series(expr)):
                if ":" in ref:
                    assert ref in records, f"{path.name} references unknown {ref!r}"
                else:
                    assert catalog.covers(ref), f"{path.name} references uncatalogued {ref!r}"


def test_every_dashboard_covers_every_slo_and_the_golden_signals() -> None:
    for slo_file in _slo_files():
        dashboard = slo_dashboard(slo_file)
        joined = "\n".join(_exprs(dashboard))
        slug = slo_file.service.replace("-", "_")
        for slo in slo_file.slos:
            assert f"slo:{slug}_{slo.name}:" in joined, (
                f"{slo_file.service}: no panel for {slo.name}"
            )
        titles = " ".join(panel["title"] for panel in dashboard["panels"])
        assert "Traffic" in titles, slo_file.service
        assert "Errors" in titles or "error ratio" in titles, slo_file.service


def test_http_services_get_all_four_golden_signals() -> None:
    for service in ("api", "voice-runtime", "probes", "metrics", "learning"):
        dashboard = slo_dashboard(load_slo_file(SLO_DIR / f"{service}.yaml"))
        titles = [panel["title"].split(" — ")[0] for panel in dashboard["panels"]]
        for signal in ("Latency", "Traffic", "Errors", "Saturation"):
            assert signal in titles, f"{service}: no {signal} panel"
        assert f'service="{service}"' in "\n".join(_exprs(dashboard))


def test_dashboards_are_locked_and_use_the_provisioned_datasource() -> None:
    for path in sorted(DASHBOARDS.glob("*.json")):
        dashboard = json.loads(path.read_text(encoding="utf-8"))
        assert dashboard["editable"] is False
        assert dashboard["uid"] == f"intake-{path.name.removesuffix('-slo-dashboard.json')}-slo"
        for panel in dashboard["panels"]:
            assert panel["datasource"] == {"type": "prometheus", "uid": "prometheus"}


def test_a_dashboard_for_a_changed_objective_is_not_the_committed_one() -> None:
    # near-miss control: tightening an objective must re-emit the dashboard
    api = load_slo_file(SLO_DIR / "api.yaml")
    tightened = api.model_copy(
        update={"slos": [api.slos[0].model_copy(update={"objective": 99.95}), *api.slos[1:]]}
    )
    committed = (DASHBOARDS / dashboard_filename("api")).read_text(encoding="utf-8")
    assert render_dashboard(slo_dashboard(tightened)) != committed

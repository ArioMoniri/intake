"""INT-021 — rules, dashboards and runbook are generated-consistent with docs/slo/.

The acceptance's "generator emits Prometheus rules; golden-signal dashboards
provisioned; runbook per alert" is enforced structurally, and over **every** SLO
file rather than only api.yaml:

- infra/observability/prometheus-rules.yaml must equal what
  ``intake_platform.slo.render_prometheus_rules`` derives from every
  docs/slo/*.yaml. Until INT-021 closed this, the file was pinned to api.yaml
  alone, so five services declared objectives that generated no rule, no alert
  and no runbook entry — declared budgets nothing could ever burn.
- one dashboard per SLO file, each equal to
  ``intake_platform.slo.grafana_dashboard``, referencing only catalogued series
  or ``slo:`` records, and mounted by the obs compose profile.
- every alert's runbook link resolves to a real heading in
  docs/runbooks/slo-burn.md.

A hand edit to any of the three fails here. Re-emit with:
  uv run python scripts/observability/slo_report.py \\
    --emit-rules infra/observability/prometheus-rules.yaml \\
    --emit-dashboards infra/observability/grafana/dashboards
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml
from intake_platform.slo import (
    AWAITING_HUMAN,
    GOLDEN_SIGNALS,
    SLOFile,
    alert_rule_name,
    dashboard_filename,
    grafana_dashboard,
    load_metrics_catalog,
    load_slo_file,
    metric_references,
    prometheus_rule_groups,
    recording_rule_name,
    render_prometheus_rules,
)

REPO = Path(__file__).resolve().parents[2]
CATALOG_PATH = REPO / "observability" / "metrics_catalog.yaml"
SLO_DIR = REPO / "docs" / "slo"
API_SLO_PATH = SLO_DIR / "api.yaml"
RULES_PATH = REPO / "infra" / "observability" / "prometheus-rules.yaml"
GRAFANA_DIR = REPO / "infra" / "observability" / "grafana" / "dashboards"
RUNBOOK_PATH = REPO / "docs" / "runbooks" / "slo-burn.md"
RUNBOOK_REL = "docs/runbooks/slo-burn.md"
OBS_COMPOSE = REPO / "infra" / "docker-compose.obs.yml"

_RECORD_REF_RE = re.compile(r"slo:[a-z0-9_]+:[a-z0-9_]+")


def _slo_files() -> list[SLOFile]:
    paths = sorted(SLO_DIR.glob("*.yaml"))
    assert paths, "docs/slo/ must hold at least the api SLO file"
    return [load_slo_file(path) for path in paths]


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
    """The burn-rate numbers ARE stated — files/10 §6 and INT-021's acceptance
    both pin them — so unlike the objectives they are asserted here directly."""
    for slo_file in _slo_files():
        for slo in slo_file.slos:
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


# --- rules file bound to every SLO file -------------------------------------------


def test_committed_rules_equal_generated_rules() -> None:
    generated = yaml.safe_load(render_prometheus_rules(_slo_files(), RUNBOOK_REL))
    assert _committed_rules() == generated


def test_every_slo_file_contributes_recording_rules() -> None:
    """The gate that would have caught the api-only pin."""
    records = _rules("record")
    for slo_file in _slo_files():
        for slo in slo_file.slos:
            name = recording_rule_name(slo_file.service, slo.name, "1h")
            assert name in records, (
                f"docs/slo/{slo_file.service}.yaml declares {slo.name} and the rules file has "
                f"no {name} — a declared SLI that is never recorded is a budget nothing burns"
            )


def test_every_slo_with_an_objective_has_its_three_burn_alerts() -> None:
    records = _rules("record")
    alerts = _rules("alert")
    for slo_file in _slo_files():
        for slo in slo_file.slos:
            if slo.objective == AWAITING_HUMAN:
                continue
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
        unknown = catalog.unknown_references(rule["expr"])
        assert unknown == frozenset(), f"{name} references {sorted(unknown)}"


def test_rendered_rules_drop_empty_alert_groups() -> None:
    for group in _committed_rules()["groups"]:
        assert group["rules"], f"group {group['name']} is empty and should not be rendered"


def test_api_availability_is_the_one_alerting_slo_today() -> None:
    """A regression guard on the honest state, not a target.

    files/10 §6 states one availability commitment; the rest are HB-O5. If this
    list grows, either a human set an objective (good — update this test) or an
    agent invented one, which is the failure this test exists to surface.
    """
    assert sorted(_rules("alert")) == [
        "ApiAvailabilityFastBurn",
        "ApiAvailabilitySlowBurn",
        "ApiAvailabilityTicketBurn",
    ]


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


def test_the_runbook_covers_every_service_that_declares_an_slo() -> None:
    text = RUNBOOK_PATH.read_text(encoding="utf-8")
    for slo_file in _slo_files():
        assert slo_file.service in text, (
            f"docs/runbooks/slo-burn.md never mentions {slo_file.service}, which declares an SLO"
        )


# --- dashboards -------------------------------------------------------------------


def _committed_dashboard(service: str) -> dict[str, Any]:
    path = GRAFANA_DIR / dashboard_filename(service)
    assert path.is_file(), f"no dashboard for {service} at {path}"
    loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def _dashboard_exprs(dashboard: dict[str, Any]) -> list[str]:
    panels = dashboard["panels"]
    assert panels, "dashboard must define panels"
    exprs: list[str] = []
    for panel in panels:
        for target in panel.get("targets", []):
            exprs.append(target["expr"])
    assert exprs, "dashboard panels must define Prometheus targets"
    return exprs


def test_every_service_has_a_committed_dashboard_equal_to_the_generator() -> None:
    for slo_file in _slo_files():
        assert _committed_dashboard(slo_file.service) == json.loads(
            json.dumps(grafana_dashboard(slo_file))
        )


def test_dashboards_reference_only_catalogued_series_or_slo_records() -> None:
    catalog = load_metrics_catalog(CATALOG_PATH)
    records = _rules("record")
    for slo_file in _slo_files():
        for expr in _dashboard_exprs(_committed_dashboard(slo_file.service)):
            for ref in sorted(metric_references(expr)):
                assert catalog.covers(ref), f"dashboard references uncatalogued series {ref!r}"
            for match in _RECORD_REF_RE.finditer(expr):
                assert match.group(0) in records, f"dashboard references unknown {match.group(0)!r}"


def test_dashboards_cover_every_slo_and_every_golden_signal() -> None:
    for slo_file in _slo_files():
        dashboard = _committed_dashboard(slo_file.service)
        joined = "\n".join(_dashboard_exprs(dashboard))
        for slo in slo_file.slos:
            assert f"slo:{slo_file.service.replace('-', '_')}_{slo.name}:" in joined, (
                f"{slo_file.service}: no panel for SLO {slo.name}"
            )
        titles = " ".join(str(panel["title"]).lower() for panel in dashboard["panels"])
        for signal in GOLDEN_SIGNALS:
            assert signal in titles, f"{slo_file.service}: no {signal} panel (files/10 §6)"


def test_a_dashboard_never_divides_by_an_objective_nobody_set() -> None:
    """The panel that would have put an invented budget on a wall."""
    for slo_file in _slo_files():
        joined = "\n".join(_dashboard_exprs(_committed_dashboard(slo_file.service)))
        for slo in slo_file.slos:
            if slo.objective != AWAITING_HUMAN:
                continue
            rule = recording_rule_name(slo_file.service, slo.name, "1h")
            assert f"{rule} /" not in joined, (
                f"{slo_file.service}/{slo.name} has no objective, so no burn-rate panel may "
                "divide its error ratio by a budget"
            )


def test_the_obs_profile_mounts_the_generated_dashboards() -> None:
    """'Provisioned' means Grafana can see them, not that a JSON file exists."""
    compose = OBS_COMPOSE.read_text(encoding="utf-8")
    assert "./observability/grafana/dashboards:/var/lib/grafana/dashboards" in compose, (
        "docker-compose.obs.yml must mount the whole generated dashboard directory; mounting "
        "one file at a time silently drops every dashboard added afterwards"
    )


def test_the_generator_is_deterministic() -> None:
    files = _slo_files()
    assert render_prometheus_rules(files, RUNBOOK_REL) == render_prometheus_rules(
        files, RUNBOOK_REL
    )
    api = load_slo_file(API_SLO_PATH)
    assert prometheus_rule_groups(api, RUNBOOK_REL) == prometheus_rule_groups(api, RUNBOOK_REL)

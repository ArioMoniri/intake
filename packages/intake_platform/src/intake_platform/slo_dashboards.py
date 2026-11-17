"""Golden-signal Grafana dashboards generated from docs/slo/<service>.yaml (INT-021).

files/10 §6 asks for "golden signals (latency, traffic, errors, saturation)
dashboards per service"; INT-021's acceptance asks for them provisioned. Until
the close-out one dashboard existed, hand-written, for the api. This module
derives one per SLO file, so a new SLO file cannot ship without its dashboard
and an objective cannot change without the dashboard's budget lines changing
with it (tests/observability/test_slo_generator.py holds the committed JSON
equal to :func:`slo_dashboard`).

Each dashboard carries, per SLO: a burn-rate stat over the fast lane's long
window in multiples of the budget, with thresholds at the three lanes'
factors, and the error ratio over every window the burn-rate rules record.
Below that, the golden signals:

- an HTTP service (its SLIs select ``http_requests_total{service="<svc>"}``,
  emitted by :func:`intake_platform.metrics.mount_http_metrics`) gets all four
  — latency p50/p95, traffic, 5xx errors by status, and CPU / memory / file
  descriptors from the process collector under ``job="<svc>"``;
- a boundary tier (``langfuse``, ``siem``) is a library inside another
  process, not a process of its own, so it has no latency or saturation of its
  own to plot: its dashboard shows the SLO panels and the traffic through each
  boundary counter its SLIs read. Latency and saturation for that process are
  on the host service's dashboard.

Every expression reads only catalogued series or the ``slo:`` recording rules
:func:`intake_platform.slo.prometheus_rule_groups` defines.
"""

from __future__ import annotations

import json
import re
from typing import Any

from intake_platform.slo import (
    SLO,
    SLOFile,
    error_budget,
    metric_references,
    recording_rule_name,
    window_seconds,
)

__all__ = [
    "DASHBOARD_DIR",
    "DATASOURCE",
    "dashboard_filename",
    "dashboard_uid",
    "http_service_of",
    "render_dashboard",
    "slo_dashboard",
]

#: Mounted whole at /var/lib/grafana/dashboards by infra/docker-compose.obs.yml.
DASHBOARD_DIR = "infra/observability/grafana/dashboards"
#: The uid infra/observability/grafana/provisioning/datasources/datasources.yaml pins.
DATASOURCE: dict[str, str] = {"type": "prometheus", "uid": "prometheus"}

_HTTP_SERIES = frozenset(
    {
        "http_requests_total",
        "http_request_duration_seconds_bucket",
        "http_request_duration_seconds_count",
        "http_request_duration_seconds_sum",
    }
)
_SERVICE_MATCHER_RE = re.compile(r'service="([a-z0-9-]+)"')
_REF_IDS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_WIDTH = 24
_HEIGHT = 6


def dashboard_uid(service: str) -> str:
    return f"intake-{service}-slo"


def dashboard_filename(service: str) -> str:
    return f"{service}-slo-dashboard.json"


def http_service_of(slo_file: SLOFile) -> bool:
    """True when every SLI is an HTTP ratio over this service's own requests."""
    for slo in slo_file.slos:
        if not metric_references(slo.sli) <= _HTTP_SERIES:
            return False
        if set(_SERVICE_MATCHER_RE.findall(slo.sli)) != {slo_file.service}:
            return False
    return True


def _title(slo: SLO) -> str:
    return slo.name.replace("_", " ").capitalize()


def _targets(exprs: list[tuple[str, str]]) -> list[dict[str, str]]:
    return [
        {"refId": _REF_IDS[index], "expr": expr, "legendFormat": legend}
        for index, (expr, legend) in enumerate(exprs)
    ]


def _panel(
    panel_id: int,
    kind: str,
    title: str,
    grid: tuple[int, int, int, int],
    unit: str,
    exprs: list[tuple[str, str]],
    description: str | None = None,
    thresholds: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    x, y, w, h = grid
    defaults: dict[str, Any] = {"unit": unit}
    if thresholds is not None:
        defaults["thresholds"] = {"mode": "absolute", "steps": thresholds}
    panel: dict[str, Any] = {"id": panel_id, "type": kind, "title": title}
    if description is not None:
        panel["description"] = description
    panel.update(
        {
            "datasource": dict(DATASOURCE),
            "gridPos": {"h": h, "w": w, "x": x, "y": y},
            "fieldConfig": {"defaults": defaults, "overrides": []},
            "targets": _targets(exprs),
        }
    )
    return panel


def _windows(slo: SLO) -> list[str]:
    return sorted(
        {
            window
            for _, alert in slo.burn_rate_alerts.named_alerts()
            for window in (alert.long_window, alert.short_window)
        },
        key=window_seconds,
    )


def _slo_panels(slo_file: SLOFile, slo: SLO, first_id: int, y: int) -> list[dict[str, Any]]:
    budget = error_budget(slo.objective)
    lanes = slo.burn_rate_alerts.named_alerts()
    fast = slo.burn_rate_alerts.fast
    steps: list[dict[str, Any]] = [{"color": "green", "value": None}]
    colours = {"ticket": "yellow", "slow": "orange", "fast": "red"}
    for kind, alert in sorted(lanes, key=lambda lane: lane[1].factor):
        steps.append({"color": colours[kind], "value": alert.factor})
    policy = ", ".join(f"{kind} {alert.factor:g}x ({alert.severity})" for kind, alert in lanes)
    stat = _panel(
        first_id,
        "stat",
        f"{_title(slo)} burn rate ({fast.long_window}, multiples of budget)",
        (0, y, 6, _HEIGHT),
        "none",
        [
            (
                f"{recording_rule_name(slo_file.service, slo.name, fast.long_window)} / {budget!r}",
                f"burn {fast.long_window}",
            )
        ],
        description=(
            f"slo:{slo_file.service} {slo.name} error ratio over {fast.long_window} divided by "
            f"the {slo.objective:g} % objective's budget ({budget!r}); lanes: {policy} — "
            "see docs/runbooks/slo-burn.md."
        ),
        thresholds=steps,
    )
    ratio = _panel(
        first_id + 1,
        "timeseries",
        f"{_title(slo)} — error ratio by burn window",
        (6, y, _WIDTH - 6, _HEIGHT),
        "percentunit",
        [
            (recording_rule_name(slo_file.service, slo.name, window), window)
            for window in _windows(slo)
        ],
    )
    return [stat, ratio]


def _http_golden_signals(service: str, first_id: int, y: int) -> list[dict[str, Any]]:
    requests = f'http_requests_total{{service="{service}"}}'
    buckets = f'http_request_duration_seconds_bucket{{service="{service}"}}'
    job = f'job="{service}"'
    return [
        _panel(
            first_id,
            "timeseries",
            "Latency — p50 / p95",
            (0, y, 12, _HEIGHT),
            "s",
            [
                (f"histogram_quantile(0.50, sum by (le) (rate({buckets}[5m])))", "p50"),
                (f"histogram_quantile(0.95, sum by (le) (rate({buckets}[5m])))", "p95"),
            ],
        ),
        _panel(
            first_id + 1,
            "timeseries",
            "Traffic — requests per second",
            (12, y, 12, _HEIGHT),
            "reqps",
            [(f"sum(rate({requests}[5m]))", "requests/s")],
        ),
        _panel(
            first_id + 2,
            "timeseries",
            "Errors — 5xx per second by status",
            (0, y + _HEIGHT, 12, _HEIGHT),
            "reqps",
            [
                (
                    f'sum by (status) (rate(http_requests_total{{service="{service}",'
                    f'status=~"5.."}}[5m]))',
                    "{{status}}",
                )
            ],
        ),
        _panel(
            first_id + 3,
            "timeseries",
            "Saturation — CPU, memory, file descriptors",
            (12, y + _HEIGHT, 12, _HEIGHT),
            "none",
            [
                (f"rate(process_cpu_seconds_total{{{job}}}[5m])", "cpu seconds/s"),
                (f"process_resident_memory_bytes{{{job}}}", "resident bytes"),
                (f"process_open_fds{{{job}}} / process_max_fds{{{job}}}", "fd ratio"),
            ],
        ),
    ]


def _boundary_traffic(slo_file: SLOFile, first_id: int, y: int) -> list[dict[str, Any]]:
    counters = sorted({ref for slo in slo_file.slos for ref in metric_references(slo.sli)})
    return [
        _panel(
            first_id,
            "timeseries",
            "Traffic — boundary counters per second",
            (0, y, _WIDTH, _HEIGHT),
            "ops",
            [(f"sum(rate({counter}[5m]))", counter) for counter in counters],
            description=(
                f"{slo_file.service} is a boundary inside another process, not a process of "
                "its own: latency and saturation are on the host service's dashboard. The "
                "error signal is the SLO error ratio above."
            ),
        )
    ]


def slo_dashboard(slo_file: SLOFile) -> dict[str, Any]:
    """The Grafana dashboard for one SLO file (deterministic; drift-gated)."""
    panels: list[dict[str, Any]] = []
    y = 0
    for slo in slo_file.slos:
        panels.extend(_slo_panels(slo_file, slo, len(panels) + 1, y))
        y += _HEIGHT
    if http_service_of(slo_file):
        panels.extend(_http_golden_signals(slo_file.service, len(panels) + 1, y))
    else:
        panels.extend(_boundary_traffic(slo_file, len(panels) + 1, y))
    return {
        "__comment": (
            f"{DASHBOARD_DIR}/{dashboard_filename(slo_file.service)} — GENERATED from "
            f"docs/slo/{slo_file.service}.yaml by intake_platform.slo_dashboards (INT-021; "
            "files/10 §6 golden signals). Do not edit: change the SLO file and re-emit with "
            "scripts/observability/slo_report.py --emit-dashboards; "
            "tests/observability/test_slo_generator.py fails on drift."
        ),
        "uid": dashboard_uid(slo_file.service),
        "title": f"{slo_file.service} — SLOs, burn rate and golden signals",
        "tags": ["slo", slo_file.service, "intake"],
        "timezone": "utc",
        "schemaVersion": 39,
        "version": 1,
        "editable": False,
        "time": {"from": "now-24h", "to": "now"},
        "templating": {"list": []},
        "annotations": {"list": []},
        "panels": panels,
    }


def render_dashboard(dashboard: dict[str, Any]) -> str:
    """The committed JSON text: two-space indent, UTF-8, trailing newline."""
    return json.dumps(dashboard, indent=2, ensure_ascii=False) + "\n"

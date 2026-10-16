"""The staff Grafana's operations dashboards, generated (INT-481).

The owner asked for "grafana or related better options or more detailed things
for the admin panel and all telemetrics measurements" (4 Oct 2026). The SLO
dashboards already exist, one per docs/slo file (:mod:`intake_platform.
slo_dashboards`). These five add the rest, and like those they are code: the
committed JSON under :data:`DASHBOARD_DIR` is held equal to :func:`ops_dashboards`
by tests/observability/test_ops_dashboards.py, so a panel cannot drift from its
query and an objective cannot change without its budget panel changing too.

- ``staging-overview`` (the home dashboard): firing alerts, every synthetic
  probe, host CPU, memory, root disk and load, and Prometheus's own storage
  against its cap.
- ``slo-latency``: the error budget left over each SLO's own window for every
  SLO in docs/slo, the API's latency against its SLO bound, and the voice
  per-turn latencies (ASR, TTS, end of utterance, round trip) and Backend Work.
- ``model-lanes``: Backend Work volume, latency and failures by type, TTS
  characters by vendor, adapter failures and fallbacks, and the cost module's
  budget alerts.
- ``triage-safety``: triage events by level and the RED acknowledgement path,
  aggregate only — no tenant, no rule id, no patient.
- ``ci-runner``: CI runs by status (queued is the queue), run durations and
  the required gates, from the ops collector's GitHub read.

Every dashboard carries the deploy markers ``infra/staging/lib.sh`` writes.

**Every expression reads catalogued series, the ``slo:`` recording rules, or
Prometheus's own ``ALERTS``**, and every label it reads is on the reviewed
allow-list (invariant 6; tests/observability/test_metric_labels.py). A panel
over a series nothing emits on a given host shows "No data" there: the panel's
description says which emitter it waits for, and no figure is ever invented.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from intake_platform.ops_panels import (
    DASHBOARD_DIR,
    DEPLOY_MARKER,
    NO_EMITTER_ON_STAGING,
    UP_DOWN,
    Panel,
    dashboard,
    dashboard_filename,
    quantile,
    render_dashboard,
    slo_budget_expr,
)
from intake_platform.slo import SLOFile, error_budget, recording_rule_name

__all__ = [
    "DASHBOARD_DIR",
    "DEPLOY_MARKER",
    "Panel",
    "dashboard_filename",
    "ops_dashboards",
    "render_dashboard",
    "slo_budget_expr",
]


# --- the five dashboards --------------------------------------------------------------------


def _overview() -> dict[str, Any]:
    panels = [
        Panel(
            "stat",
            "Firing alerts by severity",
            "none",
            (('count by (severity) (ALERTS{alertstate="firing"})', "{{severity}}"),),
            "Alerts Prometheus is firing now, counted by severity. The admin console's "
            "Alerts page shows the same alerts from Alertmanager, ids only.",
            width=8,
            height=5,
        ),
        Panel(
            "table",
            "Firing alerts",
            "none",
            (
                (
                    "max by (alertname, severity, component, service, slo, budget_id) "
                    '(ALERTS{alertstate="firing"})',
                    "",
                ),
            ),
            "One row per firing alert with its id labels. Annotations are never shown "
            "here; the runbook is named by the alert (docs/runbooks/).",
            width=16,
            height=5,
            instant=True,
        ),
        Panel(
            "stat",
            "Synthetic probes (1 up, 0 down)",
            "none",
            (("min by (component) (probe_success)", "{{component}}"),),
            "Every staging service's own health endpoint, probed inside the host by the "
            "blackbox exporter every 30 s (infra/staging/observability/prometheus.yml).",
            width=24,
            height=5,
            thresholds=UP_DOWN,
        ),
        Panel(
            "timeseries",
            "Probe duration",
            "s",
            (("max by (component) (probe_duration_seconds)", "{{component}}"),),
            "How long each synthetic probe took, end to end, inside the host.",
        ),
        Panel(
            "timeseries",
            "Host CPU busy and memory used",
            "percentunit",
            (
                ('1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m]))', "cpu busy"),
                ("1 - node_memory_memavailable_bytes / node_memory_memtotal_bytes", "memory used"),
            ),
            "The whole host: staging, this telemetry tier and the CI runner slots share it.",
        ),
        Panel(
            "timeseries",
            "Root disk free",
            "bytes",
            (("node_filesystem_avail_bytes", "free"),),
            "Free bytes on the host's root disk. The line is the CI runner's own start "
            "guard (25 GB, docs/ci/aws-ci.md): below it every CI job is refused.",
            thresholds=(("red", None), ("green", 25e9)),
            extra={"options": {"legend": {"displayMode": "list", "placement": "bottom"}}},
        ),
        Panel(
            "timeseries",
            "Load average",
            "none",
            (("node_load1", "1 min"), ("node_load15", "15 min")),
            "Run-queue length; the host has 8 vCPU.",
        ),
        Panel(
            "timeseries",
            "Prometheus storage against its cap",
            "bytes",
            (
                ("prometheus_tsdb_storage_blocks_bytes", "stored"),
                ("prometheus_tsdb_retention_limit_bytes", "cap"),
            ),
            "Prometheus keeps 30 days or 4 GB, whichever comes first "
            "(infra/staging/compose.obs.yaml).",
        ),
        Panel(
            "timeseries",
            "Series in memory",
            "none",
            (("prometheus_tsdb_head_series", "series"),),
            "Active series. A jump here is a cardinality change worth reading.",
        ),
    ]
    return dashboard(
        "staging-overview",
        "Staging — alerts, probes, host and deploys",
        "The synthetic staging host at a glance. Deploy markers come from deploy.sh.",
        panels,
    )


def _slo_latency(slo_files: Sequence[SLOFile]) -> dict[str, Any]:
    panels: list[Panel] = []
    for slo_file in slo_files:
        for slo in slo_file.slos:
            fast = slo.burn_rate_alerts.fast
            panels.append(
                Panel(
                    "stat",
                    f"{slo_file.service} {slo.name}: budget left ({slo.window})",
                    "percentunit",
                    (
                        (slo_budget_expr(slo), "budget left"),
                        (
                            f"{recording_rule_name(slo_file.service, slo.name, fast.long_window)}"
                            f" / {error_budget(slo.objective)!r}",
                            f"burn {fast.long_window}",
                        ),
                    ),
                    f"docs/slo/{slo_file.service}.yaml: {slo.objective:g} % over {slo.window}. "
                    "Budget left is 1 when untouched and 0 when spent; burn is the error "
                    f"ratio over {fast.long_window} in multiples of the budget, paging at "
                    f"{fast.factor:g}x. A service with no series shows 'No data'.",
                    width=6,
                    height=5,
                    thresholds=(("red", None), ("orange", 0.25), ("green", 0.5)),
                )
            )
    api_buckets = 'http_request_duration_seconds_bucket{service="api"}'
    panels.extend(
        [
            Panel(
                "timeseries",
                "API latency against its SLO bound",
                "s",
                (
                    (f"histogram_quantile(0.50, sum by (le) (rate({api_buckets}[5m])))", "p50"),
                    (f"histogram_quantile(0.95, sum by (le) (rate({api_buckets}[5m])))", "p95"),
                    (f"histogram_quantile(0.99, sum by (le) (rate({api_buckets}[5m])))", "p99"),
                ),
                "docs/slo/api.yaml: 99 % of requests within 500 ms over 28 days; the line "
                "is that bound.",
                thresholds=(("green", None), ("red", 0.5)),
            ),
            Panel(
                "table",
                "Slowest API routes (p95, 1 h)",
                "s",
                (
                    (
                        "topk(10, histogram_quantile(0.95, sum by (le, route) "
                        f"(rate({api_buckets}[1h]))))",
                        "{{route}}",
                    ),
                ),
                "The route label is the route template, never the raw path (invariant 6).",
                instant=True,
            ),
        ]
    )
    for family, label in (
        ("voice_stt_duration_ms", "ASR"),
        ("voice_tts_ttfb_ms", "TTS first byte"),
        ("voice_eou_delay_ms", "end of utterance"),
        ("voice_round_trip_ms", "turn round trip"),
    ):
        panels.append(
            Panel(
                "timeseries",
                f"Voice {label} latency by profile",
                "ms",
                (
                    (
                        quantile("0.50", family, "le, profile", "5m"),
                        "p50 {{profile}}",
                    ),
                    (
                        quantile("0.95", family, "le, profile", "5m"),
                        "p95 {{profile}}",
                    ),
                ),
                f"{family}, per turn, from the voice runtime. docs/slo/voice-runtime.yaml "
                "declares no latency objective yet, so no budget is drawn: files/02 §8 sets "
                "the per-profile targets." + NO_EMITTER_ON_STAGING,
                width=6,
            )
        )
    return dashboard(
        "slo-latency",
        "SLOs, error budgets and latency — API and voice",
        "Every SLO in docs/slo with the budget it has left, and the latencies behind them.",
        panels,
    )


def _model_lanes() -> dict[str, Any]:
    panels = [
        Panel(
            "timeseries",
            "Backend Work requests by type (per minute)",
            "none",
            (("sum by (type) (rate(work_latency_ms_count[5m])) * 60", "{{type}}"),),
            "Model-lane usage: every Backend Work job the clinical agent runs (extraction "
            "and the rest), by type." + NO_EMITTER_ON_STAGING,
        ),
        Panel(
            "timeseries",
            "Backend Work p95 latency by type",
            "ms",
            (
                (
                    quantile("0.95", "work_latency_ms", "le, type", "5m"),
                    "{{type}}",
                ),
            ),
            "metrics_catalog target: extract_slots p50 below 3 s." + NO_EMITTER_ON_STAGING,
        ),
        Panel(
            "timeseries",
            "Backend Work failures by type (24 h)",
            "none",
            (("sum by (type) (increase(work_failed_total[24h]))", "{{type}}"),),
            "Failed jobs, receipts rather than crashes (INT-092)." + NO_EMITTER_ON_STAGING,
        ),
        Panel(
            "timeseries",
            "TTS characters by vendor (24 h)",
            "none",
            (("sum by (vendor) (increase(voice_tts_chars_sum[24h]))", "{{vendor}}"),),
            "Characters sent for dynamic synthesis, the quantity the cost module prices."
            + NO_EMITTER_ON_STAGING,
        ),
        Panel(
            "timeseries",
            "Adapter failures and fallbacks (24 h)",
            "none",
            (
                (
                    "sum by (adapter) (increase(vendor_adapter_failures_total[24h]))",
                    "fail {{adapter}}",
                ),
                (
                    "sum by (adapter) (increase(vendor_adapter_fallbacks_total[24h]))",
                    "fallback {{adapter}}",
                ),
            ),
            "Model-gateway adapter failures and the fallbacks they triggered (INT-024).",
        ),
        Panel(
            "table",
            "Spend against the budgets",
            "none",
            (
                (
                    "max by (alertname, budget_id, scope, period) "
                    '(ALERTS{alertname=~"CostBudget.*"})',
                    "",
                ),
            ),
            "The cost module's budget alerts (infra/observability/cost-rules.yaml, INT-190). "
            "CostBudgetNotConfigured means the budget has no limit in "
            "infra/costs/unit-prices.yaml (HB-O8); CostBudgetExceeded and "
            "CostBudgetIncomplete appear once limits and prices are set. No series on this "
            "branch meters hosted-model spend in USD, so no spend figure is drawn.",
            width=24,
            instant=True,
        ),
    ]
    return dashboard(
        "model-lanes",
        "Model lanes — usage, failures and spend",
        "What the model lanes did, how fast, how often they failed, and the budgets.",
        panels,
    )


def _triage_safety() -> dict[str, Any]:
    panels = [
        Panel(
            "timeseries",
            "Triage events by level (24 h)",
            "none",
            (("sum by (level) (increase(triage_events_total[24h]))", "{{level}}"),),
            "Triage outcomes from the rules engine, counted by level only: no rule id, no "
            "tenant, no patient." + NO_EMITTER_ON_STAGING,
        ),
        Panel(
            "stat",
            "RED alerts awaiting acknowledgement",
            "none",
            (("sum(clinic_red_unacknowledged_total)", "unacknowledged"),),
            "Every RED a clinic has not yet acknowledged, summed across tenants and age "
            "bands (INT-406, invariant 49).",
            thresholds=(("green", None), ("red", 1.0)),
        ),
        Panel(
            "timeseries",
            "RED acknowledgement latency",
            "m",
            (
                (
                    quantile("0.95", "clinic_red_ack_latency_min", "le", "1h"),
                    "p95",
                ),
            ),
            "Minutes from a RED reaching the inbox to a clinician's acknowledgement.",
        ),
        Panel(
            "timeseries",
            "RED inbox: oldest pending and route failures",
            "none",
            (
                ("max(clinic_red_inbox_pending_age_s)", "oldest pending (s)"),
                (
                    "sum(increase(clinic_red_inbox_route_failures_total[1h]))",
                    "route failures (1 h)",
                ),
            ),
            "The RED inbox's oldest unacknowledged entry and the routes that failed.",
        ),
        Panel(
            "timeseries",
            "PolicyGuard blocks by class (24 h)",
            "none",
            (("sum by (class) (increase(policyguard_blocks_total[24h]))", "{{class}}"),),
            "Patient-facing lines PolicyGuard refused, by phrase class (invariant 2)."
            + NO_EMITTER_ON_STAGING,
        ),
        Panel(
            "timeseries",
            "RED preempt latency p95",
            "ms",
            (
                (
                    quantile("0.95", "preempt_red_latency_ms", "le", "1h"),
                    "p95",
                ),
            ),
            "From the rules engine's RED to the pre-positioned script starting "
            "(files/08 §4: below 300 ms)." + NO_EMITTER_ON_STAGING,
        ),
    ]
    return dashboard(
        "triage-safety",
        "Triage and RED safety — aggregate only",
        "Counts and latencies only. Nothing here names a patient, a tenant or a rule.",
        panels,
    )


def _ci_runner() -> dict[str, Any]:
    running = '{status=~"queued|waiting|requested|pending|in_progress"}'
    panels = [
        Panel(
            "stat",
            "CI runs queued and running",
            "none",
            ((f"count by (status) (ops_cicd_run{running})", "{{status}}"),),
            "The newest runs of every workflow on main, by GitHub's status: queued is the "
            "queue. Read by the probes service's ops collector with a read-only token "
            "(INT-187)." + NO_EMITTER_ON_STAGING,
            width=8,
        ),
        Panel(
            "timeseries",
            "CI run duration by workflow",
            "s",
            (("max by (workflow) (ops_cicd_run_duration_seconds)", "{{workflow}}"),),
            "Seconds from a completed run's start to its end; a running run has none."
            + NO_EMITTER_ON_STAGING,
            width=16,
        ),
        Panel(
            "table",
            "Required gates on main's head",
            "none",
            (("max by (workflow, gate, conclusion) (ops_cicd_branch_gate)", ""),),
            "Each required gate on the watched branch's head commit and its conclusion."
            + NO_EMITTER_ON_STAGING,
            width=12,
            instant=True,
        ),
        Panel(
            "stat",
            "Ops collector sources (1 up, 0 failing)",
            "none",
            (("max by (source) (ops_collector_source_up)", "{{source}}"),),
            "Whether the collector's last read of each source worked: failing is not the "
            "same as not configured." + NO_EMITTER_ON_STAGING,
            width=12,
            thresholds=UP_DOWN,
        ),
        Panel(
            "timeseries",
            "Host CPU busy while CI runs",
            "percentunit",
            (('1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m]))', "cpu busy"),),
            "The CI runner slots share this host with staging (docs/ci/aws-ci.md).",
            width=24,
        ),
    ]
    return dashboard(
        "ci-runner",
        "CI runner — queue, durations and gates",
        "The self-hosted CI runner on the staging host and the gates it reports.",
        panels,
    )


def ops_dashboards(slo_files: Sequence[SLOFile]) -> dict[str, dict[str, Any]]:
    """Every operations dashboard, by slug (deterministic; drift-gated)."""
    return {
        "staging-overview": _overview(),
        "slo-latency": _slo_latency(slo_files),
        "model-lanes": _model_lanes(),
        "triage-safety": _triage_safety(),
        "ci-runner": _ci_runner(),
    }

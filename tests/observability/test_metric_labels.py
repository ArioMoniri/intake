"""INT-481 — no PHI or PII can ride a metric label (CLAUDE.md invariant 6).

A metric label is the one place a free-text value could reach Prometheus, and
from there every dashboard, rule and console tile that reads it. This file
scans every label key the platform can produce or read against ONE closed
allow-list (:data:`intake_platform.observability.labels.ALLOWED_LABEL_KEYS`):

- every label of every family in ``observability/metrics_catalog.yaml``;
- every label key a committed rule file declares or reads — the generated SLO
  and cost rules, the security and safety rules, and the staging host rules;
- every label key a committed Grafana dashboard reads (selectors, grouping,
  ``label_replace``/``label_join`` and ``{{legend}}`` fields);
- the staging Prometheus: every scrape job drops, at ingestion, any label key
  that is not on the list (``labelkeep``), and the regex it keeps is exactly
  the list — so a label nobody reviewed is never stored, whatever an exporter
  or a service sends.

The list itself is held to a refusal rule: a key that names a person, a
session or a device, or that carries free text, or that is id-shaped, is
refused unless it is one of the few reviewed identifiers, each with the reason
it names no patient. Every gate has a near-miss negative control.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from intake_platform.observability.labels import (
    ALLOWED_LABEL_KEYS,
    REVIEWED_IDENTIFIER_KEYS,
    STRUCTURAL_LABEL_KEYS,
    dashboard_label_keys,
    label_key_problem,
    labelkeep_regex,
    promql_label_keys,
    rule_label_keys,
)
from intake_platform.slo import PHI_RISK_LABEL_NAMES, load_metrics_catalog

REPO = Path(__file__).resolve().parents[2]
CATALOG_PATH = REPO / "observability" / "metrics_catalog.yaml"
RULE_DIRS = (REPO / "infra" / "observability", REPO / "infra" / "staging" / "observability")
DASHBOARD_DIRS = (
    REPO / "infra" / "observability" / "grafana" / "dashboards",
    REPO / "infra" / "observability" / "grafana" / "ops-dashboards",
)
STAGING_PROMETHEUS = REPO / "infra" / "staging" / "observability" / "prometheus.yml"


def _rule_files() -> list[Path]:
    files = [path for directory in RULE_DIRS for path in sorted(directory.glob("*rules*.yaml"))]
    assert files, "no rule file found: the scan would be vacuous"
    return files


def _dashboards() -> list[Path]:
    files = [path for directory in DASHBOARD_DIRS for path in sorted(directory.glob("*.json"))]
    assert files, "no dashboard found: the scan would be vacuous"
    return files


def _staging_prometheus() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(STAGING_PROMETHEUS.read_text(encoding="utf-8"))
    return loaded


# --- the list itself ------------------------------------------------------------------


def test_every_allowed_key_passes_the_refusal_rule() -> None:
    problems = {key: label_key_problem(key) for key in sorted(ALLOWED_LABEL_KEYS)}
    assert {key: why for key, why in problems.items() if why is not None} == {}


def test_reviewed_identifiers_are_on_the_list_and_each_carries_a_reason() -> None:
    assert set(REVIEWED_IDENTIFIER_KEYS) <= ALLOWED_LABEL_KEYS
    for key, reason in REVIEWED_IDENTIFIER_KEYS.items():
        assert len(reason.split()) >= 4, f"{key}: a reviewed identifier says why it is safe"
        assert "patient" not in key


def test_no_phi_risk_name_is_allowed_or_reviewed() -> None:
    assert not PHI_RISK_LABEL_NAMES & ALLOWED_LABEL_KEYS
    assert not PHI_RISK_LABEL_NAMES & set(REVIEWED_IDENTIFIER_KEYS)


@pytest.mark.parametrize(
    "key",
    [
        "patient_id",
        "patient_name",
        "session_id",
        "user_email",
        "username",
        "device_id",
        "ip_address",
        "client_ip",
        "free_text",
        "message",
        "comment_text",
        "complaint_text",
        "request_path",
        "callback_url",
        "token",
        "user_sub",
        "transcript",
        "utterance_hash",
        "phone_number",
        "tckn",
    ],
)
def test_near_miss_person_free_text_and_id_shaped_keys_are_refused(key: str) -> None:
    assert label_key_problem(key) is not None


@pytest.mark.parametrize("key", ["message_class", "reason_class", "subject_count", "data_class"])
def test_near_miss_a_class_or_a_count_is_not_mistaken_for_its_noun(key: str) -> None:
    assert label_key_problem(key) is None


def test_a_reviewed_identifier_would_be_refused_without_its_review() -> None:
    """The exception list is load-bearing: strip it and the shape rule bites."""
    for key in ("host_id", "head_sha", "run_number", "actor"):
        assert key in REVIEWED_IDENTIFIER_KEYS
        assert label_key_problem(key, reviewed=frozenset()) is not None


def test_structural_keys_are_on_the_list() -> None:
    assert STRUCTURAL_LABEL_KEYS <= ALLOWED_LABEL_KEYS
    assert {"__name__", "job", "instance", "le"} <= STRUCTURAL_LABEL_KEYS


# --- the catalogue --------------------------------------------------------------------


def test_every_catalogued_label_is_allowed() -> None:
    catalog = load_metrics_catalog(CATALOG_PATH)
    offenders = {
        metric.name: sorted(set(metric.labels) - ALLOWED_LABEL_KEYS)
        for metric in catalog.metrics
        if set(metric.labels) - ALLOWED_LABEL_KEYS
    }
    assert offenders == {}, "a catalogued label key is not on the reviewed allow-list"


# --- PromQL ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        (
            'sum by (status) (rate(http_requests_total{service="api",status=~"5.."}[5m]))',
            {"status", "service"},
        ),
        ("max without (instance) (up)", {"instance"}),
        ('a / on (job) group_left (component) b{le="0.5"}', {"job", "component", "le"}),
        ('label_replace(up == 0, "component", "$1", "job", "(.*)")', {"component", "job"}),
        ('label_join(up, "pair", "-", "job", "instance")', {"pair", "job", "instance"}),
        ("node_load1 > 4", set()),
        ('count(x{a!="b", c!~"d"}) by (e)', {"a", "c", "e"}),
    ],
)
def test_promql_label_keys_reads_every_label_position(expr: str, expected: set[str]) -> None:
    assert promql_label_keys(expr) == frozenset(expected)


def test_a_string_literal_is_not_read_as_a_label() -> None:
    assert promql_label_keys('x{route="/by (patient_id)"}') == frozenset({"route"})


# --- rule files -----------------------------------------------------------------------


def test_every_rule_file_label_key_is_allowed() -> None:
    offenders = {
        path.name: sorted(rule_label_keys(path) - ALLOWED_LABEL_KEYS)
        for path in _rule_files()
        if rule_label_keys(path) - ALLOWED_LABEL_KEYS
    }
    assert offenders == {}


def test_near_miss_a_rule_that_labels_or_groups_by_a_session_is_caught(tmp_path: Path) -> None:
    rules = tmp_path / "bad-rules.yaml"
    rules.write_text(
        yaml.safe_dump(
            {
                "groups": [
                    {
                        "name": "bad",
                        "rules": [
                            {
                                "alert": "Bad",
                                "expr": "sum by (session_id) (x) > 0",
                                "labels": {"severity": "page", "patient_name": "x"},
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    assert {"session_id", "patient_name"} <= rule_label_keys(rules) - ALLOWED_LABEL_KEYS


# --- dashboards -----------------------------------------------------------------------


def test_every_dashboard_label_key_is_allowed() -> None:
    offenders = {
        path.name: sorted(
            dashboard_label_keys(json.loads(path.read_text("utf-8"))) - ALLOWED_LABEL_KEYS
        )
        for path in _dashboards()
        if dashboard_label_keys(json.loads(path.read_text("utf-8"))) - ALLOWED_LABEL_KEYS
    }
    assert offenders == {}


def test_near_miss_a_dashboard_legend_or_grouping_on_a_person_is_caught() -> None:
    dashboard = {
        "panels": [
            {"targets": [{"expr": "sum by (user_email) (x)", "legendFormat": "{{patient_name}}"}]}
        ],
        "annotations": {"list": [{"expr": "y", "titleFormat": "{{device_id}}"}]},
    }
    keys = dashboard_label_keys(dashboard)
    assert {"user_email", "patient_name", "device_id"} <= keys - ALLOWED_LABEL_KEYS


# --- the staging Prometheus drops what is not on the list ------------------------------


def test_every_staging_scrape_job_keeps_exactly_the_allowed_keys() -> None:
    expected = labelkeep_regex()
    jobs = _staging_prometheus()["scrape_configs"]
    assert jobs
    for job in jobs:
        keep = [
            rule
            for rule in job.get("metric_relabel_configs") or []
            if rule.get("action") == "labelkeep"
        ]
        assert len(keep) == 1, f"{job['job_name']}: one labelkeep, the last word on labels"
        assert keep[0]["regex"] == expected, f"{job['job_name']}: labelkeep is not the list"
        assert job["metric_relabel_configs"][-1] is keep[0], (
            f"{job['job_name']}: labelkeep runs last, after every rename"
        )


def test_the_labelkeep_regex_admits_exactly_the_list() -> None:
    pattern = re.compile(f"^(?:{labelkeep_regex()})$")
    for key in ALLOWED_LABEL_KEYS:
        assert pattern.match(key), key
    for key in ("patient_id", "session_id", "url", "mountpoint", "device", "fstype"):
        assert not pattern.match(key), key


def test_every_staging_target_label_is_allowed() -> None:
    for job in _staging_prometheus()["scrape_configs"]:
        for static in job.get("static_configs") or []:
            assert set(static.get("labels") or {}) <= ALLOWED_LABEL_KEYS, job["job_name"]
        for rule in job.get("relabel_configs") or []:
            target = rule.get("target_label")
            if target is not None and not target.startswith("__"):
                assert target in ALLOWED_LABEL_KEYS, (job["job_name"], target)


def test_every_staging_job_caps_labels_and_samples() -> None:
    """A cardinality explosion is how an unbounded value would get in."""
    for job in _staging_prometheus()["scrape_configs"]:
        assert 0 < int(job["sample_limit"]) <= 50_000, job["job_name"]
        assert 0 < int(job["label_limit"]) <= 16, job["job_name"]
        assert 0 < int(job["label_value_length_limit"]) <= 128, job["job_name"]

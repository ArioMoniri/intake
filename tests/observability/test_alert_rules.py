"""INT-021 — every rule Prometheus loads is runnable and actionable.

files/10 §6: "docs/runbooks/ linked from every alert". CLAUDE.md invariant 13:
every series a rule reads is catalogued. The acceptance's "runbook per alert"
was pinned for the api burn alerts only; this file holds it for EVERY alert in
EVERY rule file ``infra/observability/prometheus.yml`` loads — the generated
SLO rules, the generated cost rules and the hand-written security rules — and
holds every series those rules read to the catalogue, as ``live``: a rule
over a ``planned`` series is an alert nothing can ever fire.

Each gate is proven able to fail on a near-miss: an anchor one character off,
a link to a file that does not exist, a series name one letter off, a bare
series name (no selector — the form ``slo.metric_references`` cannot see), a
recording rule nobody defines, and a rule file Prometheus never loads.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from intake_platform.alert_rules import (
    RUNBOOK_ROOT,
    alert_names,
    github_slug,
    iter_rules,
    markdown_anchors,
    prometheus_rule_files,
    promql_series,
    rule_problems,
    runbook_problem,
    unloaded_rule_files,
)
from intake_platform.slo import MetricsCatalog, load_metrics_catalog

REPO = Path(__file__).resolve().parents[2]
OBS = REPO / "infra" / "observability"
PROMETHEUS_YML = OBS / "prometheus.yml"
OBS_COMPOSE = REPO / "infra" / "docker-compose.obs.yml"
CATALOG_PATH = REPO / "observability" / "metrics_catalog.yaml"


def _catalog() -> MetricsCatalog:
    return load_metrics_catalog(CATALOG_PATH)


def _loaded() -> list[Path]:
    return prometheus_rule_files(PROMETHEUS_YML)


# --- which files Prometheus loads ------------------------------------------------------


def test_prometheus_loads_the_four_rule_files() -> None:
    # INT-406 added safety-rules.yaml (the RED acknowledgement pages, invariant 49)
    names = sorted(path.name for path in _loaded())
    assert names == [
        "cost-rules.yaml",
        "prometheus-rules.yaml",
        "safety-rules.yaml",
        "security-rules.yaml",
    ]
    for path in _loaded():
        assert path.is_file(), f"prometheus.yml loads {path.name}, which does not exist"


def test_every_rule_file_in_the_tree_is_loaded() -> None:
    assert unloaded_rule_files(OBS, _loaded()) == []


def test_an_unloaded_rule_file_is_named(tmp_path: Path) -> None:
    (tmp_path / "loaded.yaml").write_text("groups: []\n", encoding="utf-8")
    (tmp_path / "forgotten.yaml").write_text("groups: []\n", encoding="utf-8")
    (tmp_path / "loki-config.yaml").write_text("auth_enabled: false\n", encoding="utf-8")
    assert unloaded_rule_files(tmp_path, [tmp_path / "loaded.yaml"]) == [
        tmp_path / "forgotten.yaml"
    ]


def test_every_loaded_rule_file_is_mounted_into_prometheus() -> None:
    compose = yaml.safe_load(OBS_COMPOSE.read_text(encoding="utf-8"))
    volumes = [str(v) for v in compose["services"]["prometheus"]["volumes"]]
    for path in _loaded():
        mount = f"./observability/{path.name}:/etc/prometheus/rules/{path.name}:ro"
        assert mount in volumes, f"{path.name} is loaded but not mounted: {mount}"


# --- the whole tree is clean -------------------------------------------------------------


def test_every_loaded_rule_is_runnable_and_actionable() -> None:
    assert rule_problems(_loaded(), _catalog(), REPO) == []


def test_every_alert_in_every_loaded_file_links_a_runbook() -> None:
    alerts = 0
    for path in _loaded():
        for _, rule in iter_rules(path):
            if "alert" not in rule:
                continue
            alerts += 1
            link = rule.get("annotations", {}).get("runbook")
            assert runbook_problem(link, REPO) is None, f"{path.name}:{rule['alert']}"
    # 7 SLO files' burn lanes + cost budgets + security countdowns: never zero
    assert alerts > 30


def test_every_slo_file_contributes_alerts() -> None:
    names = alert_names(_loaded())
    for slo_path in sorted((REPO / "docs" / "slo").glob("*.yaml")):
        service = yaml.safe_load(slo_path.read_text(encoding="utf-8"))["service"]
        prefix = "".join(part.capitalize() for part in service.split("-"))
        assert any(name.startswith(prefix) and name.endswith("Burn") for name in names), (
            f"{slo_path.name}: no burn alert in any loaded rule file"
        )


def test_a_failed_audit_chain_verification_pages() -> None:
    # files/08 §5 pages on "audit-chain verification failure"; the INT-016 job
    # sets sec_audit_chain_ok to 0 on a broken chain AND on a missing anchor
    # (HB-I12), and says it pages. Until the close-out nothing read the gauge.
    rules = {
        rule["alert"]: rule
        for _, rule in iter_rules(OBS / "security-rules.yaml")
        if "alert" in rule
    }
    rule = rules["AuditChainVerificationFailed"]
    assert promql_series(rule["expr"]) == frozenset({"sec_audit_chain_ok"})
    assert rule["expr"] == "sec_audit_chain_ok == 0"
    assert rule["labels"]["severity"] == "page"
    assert rule["annotations"]["runbook"].startswith("docs/runbooks/audit-chain.md#")


def test_every_cost_alert_kind_links_the_cost_runbook() -> None:
    kinds = {
        rule["alert"]: rule["annotations"]["runbook"]
        for _, rule in iter_rules(OBS / "cost-rules.yaml")
        if "alert" in rule
    }
    assert kinds
    for name, link in kinds.items():
        assert link.startswith("docs/runbooks/cost-budgets.md#"), name


# --- promql_series: what a rule reads --------------------------------------------------


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        (
            'sum(rate(http_requests_total{service="api",status=~"5.."}[5m]))',
            {"http_requests_total"},
        ),
        ("sec_secret_rotation_due_days < 0", {"sec_secret_rotation_due_days"}),
        ("min(admin_access_review_age_days) > 100", {"admin_access_review_age_days"}),
        (
            'increase(admin_offboarding_total{complete="false"}[1h]) > 0',
            {"admin_offboarding_total"},
        ),
        ("vector(1)", set()),
        (
            "slo:api_availability:error_ratio_rate1h > (14.4 * 0.001) and "
            "slo:api_availability:error_ratio_rate5m > (14.4 * 0.001)",
            {"slo:api_availability:error_ratio_rate1h", "slo:api_availability:error_ratio_rate5m"},
        ),
        (
            "histogram_quantile(0.95, sum by (le) "
            '(rate(http_request_duration_seconds_bucket{service="api"}[5m])))',
            {"http_request_duration_seconds_bucket"},
        ),
        (
            'process_open_fds{job="api"} / on (job) group_left process_max_fds{job="api"}',
            {"process_open_fds", "process_max_fds"},
        ),
        ("rate(x_total[5m] offset 1h) > 1e3", {"x_total"}),
        ('up{job="sum"} == bool 1', {"up"}),
    ],
)
def test_promql_series_reads_selectors_bare_names_and_recording_rules(
    expr: str, expected: set[str]
) -> None:
    assert promql_series(expr) == frozenset(expected)


# --- rule_problems near-misses ----------------------------------------------------------


def _write_rules(tmp_path: Path, rules: list[dict[str, Any]]) -> Path:
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump({"groups": [{"name": "g", "rules": rules}]}), encoding="utf-8")
    return path


def _runbook_repo(tmp_path: Path) -> Path:
    runbooks = tmp_path / RUNBOOK_ROOT
    runbooks.mkdir(parents=True)
    (runbooks / "demo.md").write_text(
        "# Demo\n\n## Api availability fast burn\n\n```sh\n# not a heading\n```\n",
        encoding="utf-8",
    )
    return tmp_path


def _alert(expr: str, runbook: str | None) -> dict[str, Any]:
    annotations: dict[str, str] = {"summary": "s"}
    if runbook is not None:
        annotations["runbook"] = runbook
    return {"alert": "A", "expr": expr, "labels": {"severity": "page"}, "annotations": annotations}


GOOD_LINK = "docs/runbooks/demo.md#api-availability-fast-burn"


def test_a_clean_synthetic_rule_file_has_no_problems(tmp_path: Path) -> None:
    repo = _runbook_repo(tmp_path)
    path = _write_rules(tmp_path, [_alert('rate(http_requests_total{a="b"}[5m]) > 0', GOOD_LINK)])
    assert rule_problems([path], _catalog(), repo) == []


@pytest.mark.parametrize(
    ("expr", "runbook", "fragment"),
    [
        ("rate(http_requests_totals[5m]) > 0", GOOD_LINK, "http_requests_totals"),
        ("sec_secret_rotation_due_dayz < 0", GOOD_LINK, "sec_secret_rotation_due_dayz"),
        ("slo:never_recorded:error_ratio_rate1h > 1", GOOD_LINK, "slo:never_recorded"),
        ("delivery_duplicates > 0", GOOD_LINK, "planned"),
        ("rate(http_requests_total[5m]) > 0", None, "no runbook"),
        (
            "rate(http_requests_total[5m]) > 0",
            "docs/runbooks/demo.md#api-availability-fast-bur",
            "#api-availability-fast-bur",
        ),
        ("rate(http_requests_total[5m]) > 0", "docs/runbooks/absent.md#x", "does not exist"),
        (
            "rate(http_requests_total[5m]) > 0",
            "docs/runbooks/demo.md#not-a-heading",
            "#not-a-heading",
        ),
        (
            "rate(http_requests_total[5m]) > 0",
            "docs/runbooks/../../etc/passwd.md#x",
            "not a docs/runbooks",
        ),
        (
            "rate(http_requests_total[5m]) > 0",
            "https://wiki.example/runbook#x",
            "not a docs/runbooks",
        ),
    ],
)
def test_each_near_miss_is_reported(
    tmp_path: Path, expr: str, runbook: str | None, fragment: str
) -> None:
    repo = _runbook_repo(tmp_path)
    path = _write_rules(tmp_path, [_alert(expr, runbook)])
    problems = rule_problems([path], _catalog(), repo)
    assert len(problems) == 1, problems
    assert fragment in problems[0]


def test_a_recording_rule_defined_in_another_loaded_file_resolves(tmp_path: Path) -> None:
    repo = _runbook_repo(tmp_path)
    records = tmp_path / "records.yaml"
    records.write_text(
        yaml.safe_dump(
            {
                "groups": [
                    {
                        "name": "r",
                        "rules": [
                            {"record": "slo:x:error_ratio_rate1h", "expr": "up"},
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    alerts = _write_rules(tmp_path, [_alert("slo:x:error_ratio_rate1h > 1", GOOD_LINK)])
    catalog = MetricsCatalog.model_validate(
        {
            "metrics": [
                {
                    "name": "up",
                    "type": "gauge",
                    "labels": [],
                    "owner": "platform",
                    "unit": "bool",
                    "description": "d",
                }
            ]
        }
    )
    assert rule_problems([records, alerts], catalog, repo) == []


# --- anchors ----------------------------------------------------------------------------


def test_github_slug_keeps_underscores_and_drops_punctuation() -> None:
    assert github_slug("langfuse `trace_emission` fast burn") == "langfuse-trace_emission-fast-burn"
    assert github_slug("Read-only past 100 days") == "read-only-past-100-days"
    assert github_slug("Overdue") == "overdue"


def test_fenced_lines_are_not_headings() -> None:
    anchors = markdown_anchors("# Title\n\n```\n# comment\n```\n## Real one\n")
    assert anchors == frozenset({"title", "real-one"})

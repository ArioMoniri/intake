"""INT-021 — every service, app, job and tier is covered, or says why not.

CLAUDE.md invariant 15: every service declares its SLOs in
``docs/slo/<service>.yaml`` and has a synthetic probe; files/10 §6 adds
golden-signal dashboards and a runbook on every alert. The acceptance named
three files; the repo now holds five services, three apps, six
``python -m intake_platform.<job>`` entry points and two boundary tiers.
``observability/slo_coverage.yaml`` states, for each, the SLO file, the probe
rows and the alerts it relies on — or the recorded reason it has none, and
who is being asked when the reason is a missing decision.

The subjects are DISCOVERED, not listed: a new ``services/<x>``, ``apps/<x>``
or ``intake_platform/<x>/__main__.py`` without an entry fails here. Each gate
is proven on a near-miss. Separately, an SLI written against
``http_requests_total{service="x"}`` must have an emitter: the service
directory ``x`` mounts ``mount_http_metrics(app, "x")`` — without it the SLO
is one nobody could ever breach (found: services/probes, fixed here).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from intake_platform.alert_rules import alert_names, prometheus_rule_files
from intake_platform.slo import load_slo_file
from intake_platform.slo_coverage import (
    COVERAGE_PATH,
    CoverageEntry,
    CoverageManifest,
    coverage_problems,
    discover_subjects,
    http_emitter_problems,
    load_coverage,
    mounted_http_services,
    registry_components,
    sli_http_services,
)
from intake_platform.slo_dashboards import DASHBOARD_DIR
from prometheus_client.parser import text_string_to_metric_families
from pydantic import ValidationError

REPO = Path(__file__).resolve().parents[2]
SLO_DIR = REPO / "docs" / "slo"
RULES = REPO / "infra" / "observability" / "prometheus-rules.yaml"
REGISTRY = REPO / "observability" / "registry.yaml"
PROMETHEUS_YML = REPO / "infra" / "observability" / "prometheus.yml"


def _problems(manifest: CoverageManifest, repo: Path = REPO) -> list[str]:
    return coverage_problems(
        manifest,
        repo,
        registry=registry_components(REGISTRY),
        alerts=alert_names(prometheus_rule_files(PROMETHEUS_YML)),
        rules=yaml.safe_load(RULES.read_text(encoding="utf-8")),
        dashboards=REPO / DASHBOARD_DIR,
    )


def _manifest() -> CoverageManifest:
    return load_coverage(REPO / COVERAGE_PATH)


# --- the committed manifest -----------------------------------------------------------------


def test_the_committed_manifest_covers_the_repo_without_problems() -> None:
    assert _problems(_manifest()) == []


def test_discovery_finds_every_kind() -> None:
    found = discover_subjects(REPO)
    assert {"api", "voice-runtime", "probes", "metrics", "learning"} <= {
        name for name, kind in found.items() if kind == "service"
    }
    assert found["admin-web"] == "app"
    assert found["intake_platform.key_rotation"] == "job"
    assert found["intake_platform.access_hygiene"] == "job"


def test_every_present_service_carries_an_slo_file() -> None:
    entries = {entry.subject: entry for entry in _manifest().subjects}
    for name, kind in discover_subjects(REPO).items():
        if kind == "service":
            assert entries[name].slo == f"docs/slo/{name}.yaml", name


def test_the_workers_tier_is_recorded_as_a_gap_awaiting_a_decision() -> None:
    workers = next(entry for entry in _manifest().subjects if entry.subject == "workers")
    assert not (REPO / "services" / "workers").exists()
    assert workers.slo is None
    assert "slo" in workers.gaps
    assert workers.awaiting


def test_every_job_alert_named_in_the_manifest_is_loaded() -> None:
    loaded = alert_names(prometheus_rule_files(PROMETHEUS_YML))
    for entry in _manifest().subjects:
        for alert in entry.alerts:
            assert alert in loaded, f"{entry.subject}: {alert} is not in any loaded rule file"


# --- near-misses ------------------------------------------------------------------------------


def _replace(subject: str, **changes: Any) -> CoverageManifest:
    manifest = _manifest()
    subjects = [
        entry.model_copy(update=changes) if entry.subject == subject else entry
        for entry in manifest.subjects
    ]
    return CoverageManifest(subjects=subjects)


def _without(subject: str) -> CoverageManifest:
    manifest = _manifest()
    return CoverageManifest(subjects=[e for e in manifest.subjects if e.subject != subject])


@pytest.mark.parametrize(
    "subject", ["api", "admin-web", "intake_platform.key_rotation", "langfuse"]
)
def test_dropping_any_entry_is_reported(subject: str) -> None:
    problems = _problems(_without(subject))
    assert problems, subject
    assert any(subject in p or "langfuse.yaml" in p for p in problems), problems


def test_a_probe_row_one_character_off_is_reported() -> None:
    problems = _problems(_replace("metrics", probes=["metric"]))
    assert problems == ["metrics: probe row 'metric' is not in observability/registry.yaml"]


def test_an_alert_that_is_not_loaded_is_reported() -> None:
    problems = _problems(_replace("intake_platform.key_rotation", alerts=["SecretRotationOverdu"]))
    assert problems == [
        "intake_platform.key_rotation: alert 'SecretRotationOverdu' is not in any loaded rule file"
    ]


def test_a_service_may_not_be_exempted_from_an_slo() -> None:
    problems = _problems(
        _replace("learning", slo=None, exempt={"slo": "batch job, no promise to anyone"})
    )
    assert any("learning" in p and "inv. 15" in p for p in problems), problems


def test_an_slo_file_without_generated_rules_is_reported(tmp_path: Path) -> None:
    rules = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    rules["groups"] = [g for g in rules["groups"] if not g["name"].startswith("slo-siem-")]
    problems = coverage_problems(
        _manifest(),
        REPO,
        registry=registry_components(REGISTRY),
        alerts=alert_names(prometheus_rule_files(PROMETHEUS_YML)),
        rules=rules,
        dashboards=REPO / DASHBOARD_DIR,
    )
    assert problems == [
        "intake_platform.siem: docs/slo/siem.yaml has no slo-siem-recording group in "
        "infra/observability/prometheus-rules.yaml",
        "intake_platform.siem: docs/slo/siem.yaml has no slo-siem-alerts group in "
        "infra/observability/prometheus-rules.yaml",
    ]


def test_an_slo_file_without_a_dashboard_is_reported(tmp_path: Path) -> None:
    for path in (REPO / DASHBOARD_DIR).glob("*.json"):
        if path.name != "metrics-slo-dashboard.json":
            (tmp_path / path.name).write_bytes(path.read_bytes())
    problems = coverage_problems(
        _manifest(),
        REPO,
        registry=registry_components(REGISTRY),
        alerts=alert_names(prometheus_rule_files(PROMETHEUS_YML)),
        rules=yaml.safe_load(RULES.read_text(encoding="utf-8")),
        dashboards=tmp_path,
    )
    assert problems == [
        "metrics: no dashboard infra/observability/grafana/dashboards/metrics-slo-dashboard.json"
    ]


def test_a_new_service_directory_without_an_entry_is_reported(tmp_path: Path) -> None:
    (tmp_path / "services" / "billing").mkdir(parents=True)
    (tmp_path / "services" / "billing" / "pyproject.toml").write_text("[project]\n")
    (tmp_path / "apps" / "kiosk").mkdir(parents=True)
    (tmp_path / "apps" / "kiosk" / "package.json").write_text("{}")
    job = tmp_path / "packages" / "intake_platform" / "src" / "intake_platform" / "sweeper"
    job.mkdir(parents=True)
    (job / "__main__.py").write_text("")
    assert discover_subjects(tmp_path) == {
        "billing": "service",
        "kiosk": "app",
        "intake_platform.sweeper": "job",
    }
    problems = coverage_problems(
        CoverageManifest(subjects=[]),
        tmp_path,
        registry=frozenset(),
        alerts=frozenset(),
        rules={"groups": []},
        dashboards=tmp_path,
    )
    assert problems == [
        "billing (service) has no entry in observability/slo_coverage.yaml",
        "intake_platform.sweeper (job) has no entry in observability/slo_coverage.yaml",
        "kiosk (app) has no entry in observability/slo_coverage.yaml",
    ]


# --- the entry schema ------------------------------------------------------------------------


def _entry(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "subject": "x",
        "kind": "service",
        "slo": "docs/slo/x.yaml",
        "probes": ["x"],
    }
    base.update(overrides)
    return base


def test_an_entry_states_each_facet_exactly_once() -> None:
    CoverageEntry.model_validate(_entry())
    with pytest.raises(ValidationError, match="slo"):
        CoverageEntry.model_validate(_entry(exempt={"slo": "reason"}))
    with pytest.raises(ValidationError, match="slo"):
        CoverageEntry.model_validate(_entry(slo=None))
    with pytest.raises(ValidationError, match="probe"):
        CoverageEntry.model_validate(_entry(probes=[], gaps={}))
    with pytest.raises(ValidationError, match="probe"):
        CoverageEntry.model_validate(_entry(gaps={"probe": "why"}))


def test_a_reason_may_not_be_blank_and_awaiting_needs_a_gap() -> None:
    with pytest.raises(ValidationError, match="blank"):
        CoverageEntry.model_validate(_entry(probes=[], exempt={"probe": "  "}))
    with pytest.raises(ValidationError, match="awaiting"):
        CoverageEntry.model_validate(_entry(awaiting="owner"))


def test_an_slo_path_outside_docs_slo_is_refused() -> None:
    with pytest.raises(ValidationError, match="docs/slo"):
        CoverageEntry.model_validate(_entry(slo="docs/slo/../../etc/x.yaml"))


def test_subjects_are_unique() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        CoverageManifest.model_validate({"subjects": [_entry(), _entry()]})


# --- SLI emitters ------------------------------------------------------------------------------


def test_every_http_sli_has_an_emitter_in_its_service() -> None:
    slo_files = [load_slo_file(path) for path in sorted(SLO_DIR.glob("*.yaml"))]
    assert http_emitter_problems(slo_files, REPO / "services") == []


def test_http_sli_services_are_read_from_the_selectors() -> None:
    assert sli_http_services(load_slo_file(SLO_DIR / "api.yaml")) == frozenset({"api"})
    assert sli_http_services(load_slo_file(SLO_DIR / "siem.yaml")) == frozenset()


def test_the_emitter_scan_resolves_literals_and_module_constants(tmp_path: Path) -> None:
    src = tmp_path / "svc" / "src" / "pkg"
    src.mkdir(parents=True)
    (src / "app.py").write_text(
        'SERVICE_NAME = "svc"\n'
        "def create_app(app):\n"
        "    mount_http_metrics(app, SERVICE_NAME)\n"
        '    mount_http_metrics(app, "other")\n',
        encoding="utf-8",
    )
    assert mounted_http_services(tmp_path / "svc") == frozenset({"svc", "other"})


def test_an_sli_whose_service_mounts_under_another_name_is_reported(tmp_path: Path) -> None:
    src = tmp_path / "probes" / "src" / "pkg"
    src.mkdir(parents=True)
    (src / "app.py").write_text('mount_http_metrics(app, "probe")\n', encoding="utf-8")
    problems = http_emitter_problems([load_slo_file(SLO_DIR / "probes.yaml")], tmp_path)
    assert problems == [
        'docs/slo/probes.yaml reads http_requests_total{service="probes"} but services/probes '
        'never calls mount_http_metrics(app, "probes") — an SLO nothing can breach'
    ]


def test_the_probes_service_serves_its_own_request_series() -> None:
    from intake_probes.app import create_app

    client = TestClient(create_app())
    assert client.get("/healthz").status_code == 200
    samples = [
        sample.labels
        for family in text_string_to_metric_families(client.get("/metrics").text)
        if family.name == "http_requests"
        for sample in family.samples
        if sample.name == "http_requests_total"
    ]
    assert {"service": "probes", "method": "GET", "route": "/healthz", "status": "200"} in samples

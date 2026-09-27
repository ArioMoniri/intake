"""INT-202 — backup freshness and drill recency as catalogued series, with alerts.

files/10 §7 lists "backup freshness, DR-drill status" among the signals and
files/08 §4 names the two ids, ``sec.backup_age_min`` and
``sec.restore_drill_age_days``, which were catalogued ``planned`` until
something emitted them. The probes service now computes both at scrape time
from the PHI-free status records the host scripts write
(``intake_platform.backup.status``), and two alerts read them.

An absent record is +Inf, never zero: a host where no backup has ever run must
page, not report a fresh backup.
"""

from __future__ import annotations

import json
import math
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from intake_platform.backup import metrics as backup_metrics
from intake_platform.backup.status import (
    DRILL_CHECKS,
    BackupSummary,
    backup_record,
    drill_record,
    write_record,
)
from intake_platform.slo import load_metrics_catalog
from prometheus_client.parser import text_string_to_metric_families

REPO = Path(__file__).resolve().parents[2]
CATALOG = REPO / "observability" / "metrics_catalog.yaml"
RULES = REPO / "infra" / "observability" / "security-rules.yaml"
RUNBOOK = REPO / "docs" / "runbooks" / "restore-drill.md"
NOW = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
FAMILIES = ("sec_backup_age_min", "sec_restore_drill_age_days")


def _scrape(gauge: Any) -> float:
    """What a scrape reads: the collected sample, which is where set_function lands."""
    value: float = next(iter(gauge.collect())).samples[0].value
    return value


def _rules() -> dict[str, dict[str, Any]]:
    loaded = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    return {rule["alert"]: rule for group in loaded["groups"] for rule in group["rules"]}


def _anchor(heading: str) -> str:
    return re.sub(r"[^a-z0-9 -]", "", heading.lower()).strip().replace(" ", "-")


def _backup(stopped: datetime) -> dict[str, Any]:
    summary = BackupSummary(
        label="20260927-013000F",
        type="full",
        started_at=stopped - timedelta(minutes=5),
        stopped_at=stopped,
        database_bytes=1,
        repos=(1,),
        error=False,
    )
    return backup_record(summary, recorded_at=stopped, retention_days=None)


def _drill(finished: datetime) -> dict[str, Any]:
    return drill_record(
        {
            "target": "staging",
            "run_id": "ab" * 16,
            "started_at": "2026-07-01T03:00:00Z",
            "backup": {"label": "x", "type": "full", "stopped_at": "2026-07-01T01:35:00Z"},
            "recovery_target": "2026-07-01 03:02:00+00",
            "rpo_observed_s": 60.0,
            "restore_seconds": 30,
            "checks": dict.fromkeys(DRILL_CHECKS, True),
            "row_counts": {},
            "second_location": "unconfigured",
            "retention_days": None,
        },
        finished_at=finished,
    )


class TestGauges:
    def test_the_two_families_are_the_catalogued_names(self) -> None:
        assert backup_metrics.SEC_BACKUP_AGE_MIN._name == "sec_backup_age_min"
        assert backup_metrics.SEC_RESTORE_DRILL_AGE_DAYS._name == "sec_restore_drill_age_days"

    def test_before_binding_both_read_infinitely_old(self) -> None:
        """Import-time state: a gauge that defaulted to zero would report a
        backup that never happened as a fresh one."""
        import subprocess
        import sys

        probe = (
            "from intake_platform.backup import metrics as m\n"
            "for g in (m.SEC_BACKUP_AGE_MIN, m.SEC_RESTORE_DRILL_AGE_DAYS):\n"
            "    print(next(iter(g.collect())).samples[0].value)\n"
        )
        result = subprocess.run(  # noqa: S603 — this interpreter, a fixed program
            [sys.executable, "-c", probe], capture_output=True, text=True, check=True
        )
        assert result.stdout.split() == ["inf", "inf"]

    def test_an_empty_directory_reads_infinitely_old(self, tmp_path: Path) -> None:
        backup_metrics.bind_backup_gauges(tmp_path, clock=lambda: NOW)
        assert _scrape(backup_metrics.SEC_BACKUP_AGE_MIN) == math.inf
        assert _scrape(backup_metrics.SEC_RESTORE_DRILL_AGE_DAYS) == math.inf

    def test_the_ages_are_computed_from_the_records_at_scrape_time(self, tmp_path: Path) -> None:
        clock = {"now": NOW}
        backup_metrics.bind_backup_gauges(tmp_path, clock=lambda: clock["now"])
        write_record(tmp_path, _backup(NOW - timedelta(minutes=90)))
        write_record(tmp_path, _drill(NOW - timedelta(days=30)))
        assert _scrape(backup_metrics.SEC_BACKUP_AGE_MIN) == pytest.approx(90.0)
        assert _scrape(backup_metrics.SEC_RESTORE_DRILL_AGE_DAYS) == pytest.approx(30.0)
        clock["now"] = NOW + timedelta(minutes=30)
        assert _scrape(backup_metrics.SEC_BACKUP_AGE_MIN) == pytest.approx(120.0)

    def test_binding_from_the_environment_reads_the_probe_directory(self, tmp_path: Path) -> None:
        write_record(tmp_path, _backup(datetime.now(UTC) - timedelta(minutes=10)))
        assert backup_metrics.bind_from_env({"INTAKE_BACKUP_DIR": str(tmp_path)}) == tmp_path
        assert 9.0 < _scrape(backup_metrics.SEC_BACKUP_AGE_MIN) < 11.0

    def test_the_probes_service_serves_both(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from intake_probes.app import create_app

        write_record(tmp_path, _backup(datetime.now(UTC) - timedelta(minutes=5)))
        monkeypatch.setenv("INTAKE_BACKUP_DIR", str(tmp_path))
        with TestClient(create_app()) as client:
            body = client.get("/metrics").text
        served = {family.name: family for family in text_string_to_metric_families(body)}
        for name in FAMILIES:
            assert name in served, name
        age = served["sec_backup_age_min"].samples[0].value
        assert 4.0 < age < 6.0
        assert served["sec_restore_drill_age_days"].samples[0].value == math.inf


class TestCatalogue:
    @pytest.mark.parametrize("name", FAMILIES)
    def test_both_are_live_gauges_with_no_labels(self, name: str) -> None:
        catalog = load_metrics_catalog(CATALOG)
        entry = next(metric for metric in catalog.metrics if metric.name == name)
        assert entry.status == "live"
        assert entry.type == "gauge"
        assert list(entry.labels) == []


class TestAlerts:
    def test_a_missed_daily_backup_raises_a_ticket(self) -> None:
        rule = _rules()["BackupStale"]
        assert rule["expr"] == "sec_backup_age_min > 1500"
        assert rule["labels"]["severity"] == "ticket"

    def test_a_drill_older_than_the_longest_quarter_raises_a_ticket(self) -> None:
        """Quarterly (files/10 §3). The longest calendar quarter is 92 days."""
        longest_quarter = max(
            (datetime(2026 + (m == 10), (m + 2) % 12 + 1, 1) - datetime(2026, m, 1)).days
            for m in (1, 4, 7, 10)
        )
        rule = _rules()["RestoreDrillOverdue"]
        assert rule["expr"] == f"sec_restore_drill_age_days > {longest_quarter}"
        assert rule["labels"]["severity"] == "ticket"

    @pytest.mark.parametrize("alert", ["BackupStale", "RestoreDrillOverdue"])
    def test_every_alert_links_a_runbook_section_that_exists(self, alert: str) -> None:
        runbook = _rules()[alert]["annotations"]["runbook"]
        path, _, anchor = runbook.partition("#")
        assert path == "docs/runbooks/restore-drill.md"
        headings = {
            _anchor(line.lstrip("#").strip())
            for line in RUNBOOK.read_text(encoding="utf-8").splitlines()
            if line.startswith("## ")
        }
        assert anchor in headings, (anchor, headings)

    def test_the_rules_read_only_catalogued_series(self) -> None:
        catalog = load_metrics_catalog(CATALOG)
        for alert in ("BackupStale", "RestoreDrillOverdue"):
            names = set(re.findall(r"[a-z_]+(?= [<>])", _rules()[alert]["expr"]))
            for name in names:
                assert catalog.covers(name), name

    def test_the_record_files_are_json_the_alerts_can_trust(self, tmp_path: Path) -> None:
        path = write_record(tmp_path, _backup(NOW))
        assert json.loads(path.read_text(encoding="utf-8"))["kind"] == "backup"

"""INT-202 — the backup and restore-drill status records.

``intake_platform.backup.status`` is the one module the production host runs
with nothing but the system ``python3``: the host scripts call it as a file to
turn ``pgbackrest info --output=json`` into a backup record and a drill's
measurements into a drill record. Both records are PHI-free by construction —
clocks, sizes, labels, booleans and per-table integers — and the probes
service reads them back to publish ``sec_backup_age_min`` and
``sec_restore_drill_age_days``.

Pinned here: the parser, the closed record shapes, the verdict (the two
budgets files/10 §3 states, RPO 15 min and RTO 4 h, and every check), the
retention ceiling derived from files/06 §1, the headroom rule that keeps a
drill from filling the production disk, and that the module really is
stdlib-only, because the host has no virtualenv.
"""

from __future__ import annotations

import ast
import json
import math
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from intake_platform.backup import status
from intake_platform.backup.status import (
    DRILL_CHECKS,
    FULL_BACKUP_INTERVAL_DAYS,
    RETENTION_CEILING_DAYS,
    RPO_BUDGET_S,
    RTO_BUDGET_S,
    SHORTEST_SIX_MONTHS_DAYS,
    BackupSummary,
    StatusError,
    backup_age_minutes,
    backup_record,
    drill_record,
    newest_backup,
    parse_row_counts,
    restore_drill_age_days,
    restore_headroom_ok,
    second_location_state,
    validate_retention_days,
    write_record,
)

REPO = Path(__file__).resolve().parents[2]
STATUS_PY = (
    REPO / "packages" / "intake_platform" / "src" / "intake_platform" / "backup" / "status.py"
)
NOW = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
RUN_ID = "0123456789abcdef0123456789abcdef"


def _info(*backups: dict[str, Any], repos: tuple[int, ...] = (1,)) -> str:
    """The shape ``pgbackrest info --output=json`` prints (trimmed to what we read)."""
    return json.dumps(
        [
            {
                "name": "intake",
                "cipher": "aes-256-cbc",
                "repo": [
                    {"key": key, "cipher": "aes-256-cbc", "status": {"code": 0}} for key in repos
                ],
                "status": {"code": 0, "message": "ok"},
                "backup": list(backups),
            }
        ]
    )


def _backup(
    label: str, kind: str, start: datetime, stop: datetime, size: int = 4096
) -> dict[str, Any]:
    return {
        "label": label,
        "type": kind,
        "error": False,
        "timestamp": {"start": int(start.timestamp()), "stop": int(stop.timestamp())},
        "info": {"size": size, "delta": size},
        "database": {"id": 1, "repo-key": 1},
    }


def _summary() -> BackupSummary:
    start = NOW - timedelta(hours=2)
    return BackupSummary(
        label="20260927-100000F",
        type="full",
        started_at=start,
        stopped_at=start + timedelta(minutes=3),
        database_bytes=4096,
        repos=(1,),
        error=False,
    )


def _measurements(**overrides: Any) -> dict[str, Any]:
    checks = dict.fromkeys(DRILL_CHECKS, True)
    checks.update(overrides.pop("checks", {}))
    base: dict[str, Any] = {
        "target": "ci",
        "run_id": RUN_ID,
        "started_at": "2026-09-27T11:00:00Z",
        "backup": {
            "label": "20260927-100000F",
            "type": "full",
            "stopped_at": "2026-09-27T10:03:00Z",
        },
        "recovery_target": "2026-09-27 11:02:00.123456+00",
        "rpo_observed_s": 61.5,
        "restore_seconds": 42,
        "checks": checks,
        "row_counts": {"sessions": 3, "notes": 2},
        "second_location": "unconfigured",
        "retention_days": None,
    }
    base.update(overrides)
    return base


# --- the host contract: stdlib only ------------------------------------------------------


class TestHostRunnable:
    def test_the_module_imports_only_the_standard_library(self) -> None:
        """The production host runs this file with the system python3 and no
        virtualenv (infra/staging/lib.sh requires only python3). A third-party
        import would work in CI and fail on the one machine that matters."""
        tree = ast.parse(STATUS_PY.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                assert node.level == 0, "a relative import breaks `python3 status.py`"
                imported.add(str(node.module).split(".")[0])
        assert imported <= set(sys.stdlib_module_names) | {"__future__"}, imported

    def test_it_runs_as_a_plain_script(self, tmp_path: Path) -> None:
        result = subprocess.run(  # noqa: S603 — our own file, fixed argv
            [sys.executable, "-S", str(STATUS_PY), "validate-retention", "30"],
            capture_output=True,
            text=True,
            check=False,
            cwd=tmp_path,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "30"


# --- pgbackrest info -> the newest backup ------------------------------------------------


class TestNewestBackup:
    def test_the_newest_completed_backup_is_chosen(self) -> None:
        first = _backup(
            "20260920-013000F",
            "full",
            NOW - timedelta(days=7),
            NOW - timedelta(days=7) + timedelta(minutes=5),
        )
        second = _backup(
            "20260926-013000F_20260927-013000D",
            "diff",
            NOW - timedelta(hours=10),
            NOW - timedelta(hours=10) + timedelta(minutes=1),
            size=8192,
        )
        summary = newest_backup(_info(second, first))
        assert summary.label == "20260926-013000F_20260927-013000D"
        assert summary.type == "diff"
        assert summary.database_bytes == 8192
        assert summary.stopped_at == datetime.fromtimestamp(second["timestamp"]["stop"], UTC)

    def test_no_backup_is_a_refusal_not_a_default(self) -> None:
        with pytest.raises(StatusError, match="no backup"):
            newest_backup(_info())

    def test_malformed_json_is_refused(self) -> None:
        with pytest.raises(StatusError):
            newest_backup("not json")

    def test_a_stanza_that_is_not_intake_is_refused(self) -> None:
        payload = json.loads(_info(_backup("x", "full", NOW, NOW)))
        payload[0]["name"] = "other"
        with pytest.raises(StatusError, match="intake"):
            newest_backup(json.dumps(payload))

    def test_the_repositories_are_read(self) -> None:
        summary = newest_backup(_info(_backup("x", "full", NOW, NOW), repos=(1, 2)))
        assert summary.repos == (1, 2)


class TestSecondLocation:
    def test_one_repository_is_an_unconfigured_second_location(self) -> None:
        assert second_location_state((1,)) == "unconfigured"

    def test_a_second_repository_is_configured(self) -> None:
        assert second_location_state((1, 2)) == "configured"


# --- the backup record ---------------------------------------------------------------------


class TestBackupRecord:
    def test_the_record_is_clocks_sizes_and_labels(self) -> None:
        record = backup_record(_summary(), recorded_at=NOW, retention_days=None)
        assert set(record) == {
            "kind",
            "issue",
            "label",
            "type",
            "started_at",
            "stopped_at",
            "database_bytes",
            "error",
            "repos",
            "second_location",
            "retention_days",
            "recorded_at",
        }
        assert record["kind"] == "backup"
        assert record["issue"] == "INT-202"
        assert record["second_location"] == "unconfigured"
        assert record["retention_days"] is None
        assert record["stopped_at"] == "2026-09-27T10:03:00Z"

    def test_write_record_is_atomic_json_named_by_kind(self, tmp_path: Path) -> None:
        path = write_record(tmp_path, backup_record(_summary(), recorded_at=NOW, retention_days=7))
        assert path.parent == tmp_path
        assert path.name.startswith("backup-") and path.suffix == ".json"
        assert json.loads(path.read_text(encoding="utf-8"))["retention_days"] == 7
        assert [p.name for p in tmp_path.iterdir()] == [path.name], "no temp file left behind"


# --- the drill record and its verdict ------------------------------------------------------


class TestDrillRecord:
    def test_a_clean_drill_passes(self) -> None:
        record = drill_record(_measurements(), finished_at=NOW)
        assert record["verdict"] == "pass"
        assert record["failures"] == []
        assert record["rpo_budget_s"] == RPO_BUDGET_S == 15 * 60
        assert record["rto_budget_s"] == RTO_BUDGET_S == 4 * 60 * 60

    @pytest.mark.parametrize("check", DRILL_CHECKS)
    def test_every_failed_check_fails_the_drill_and_is_named(self, check: str) -> None:
        record = drill_record(_measurements(checks={check: False}), finished_at=NOW)
        assert record["verdict"] == "fail"
        assert check in record["failures"]

    def test_an_rpo_over_budget_fails(self) -> None:
        record = drill_record(_measurements(rpo_observed_s=RPO_BUDGET_S + 1), finished_at=NOW)
        assert record["verdict"] == "fail"
        assert "rpo_exceeded" in record["failures"]

    def test_an_rto_over_budget_fails(self) -> None:
        record = drill_record(_measurements(restore_seconds=RTO_BUDGET_S + 1), finished_at=NOW)
        assert record["failures"] == ["rto_exceeded"]

    def test_the_boundaries_themselves_pass(self) -> None:
        record = drill_record(
            _measurements(rpo_observed_s=RPO_BUDGET_S, restore_seconds=RTO_BUDGET_S),
            finished_at=NOW,
        )
        assert record["verdict"] == "pass"

    def test_a_missing_check_is_a_failure_not_a_pass(self) -> None:
        measurements = _measurements()
        del measurements["checks"]["erased_unreadable"]
        record = drill_record(measurements, finished_at=NOW)
        assert "erased_unreadable" in record["failures"]

    def test_an_unconfigured_second_location_is_recorded_not_hidden(self) -> None:
        record = drill_record(_measurements(), finished_at=NOW)
        assert record["second_location"] == "unconfigured"

    def test_the_record_has_a_closed_field_set_with_no_identifier_slot(self) -> None:
        record = drill_record(_measurements(), finished_at=NOW)
        assert set(record) == {
            "kind",
            "issue",
            "target",
            "run_id",
            "started_at",
            "finished_at",
            "backup",
            "recovery_target",
            "rpo_budget_s",
            "rpo_observed_s",
            "rto_budget_s",
            "restore_seconds",
            "checks",
            "row_counts",
            "second_location",
            "retention_days",
            "verdict",
            "failures",
        }
        forbidden = ("patient", "name", "phone", "tckn", "transcript", "note_text", "email")
        flat = json.dumps(record).lower()
        for word in forbidden:
            assert f'"{word}' not in flat, word

    def test_an_unknown_measurement_is_refused(self) -> None:
        with pytest.raises(StatusError, match="unexpected"):
            drill_record(_measurements(transcript="x"), finished_at=NOW)

    def test_a_malformed_run_id_is_refused(self) -> None:
        with pytest.raises(StatusError, match="run_id"):
            drill_record(_measurements(run_id="../../etc"), finished_at=NOW)

    def test_an_unknown_target_is_refused(self) -> None:
        with pytest.raises(StatusError, match="target"):
            drill_record(_measurements(target="laptop"), finished_at=NOW)


class TestRowCounts:
    def test_counts_parse_and_anything_else_is_dropped(self) -> None:
        raw = 'sessions:3\nnotes:2\nERROR:  relation "x" does not exist\nbad line\n: 4\nx y:5\n'
        assert parse_row_counts(raw) == {"sessions": 3, "notes": 2}

    def test_a_relname_longer_than_postgres_allows_is_dropped(self) -> None:
        assert parse_row_counts("a" * 64 + ":1") == {}

    def test_a_negative_or_non_integer_count_is_dropped(self) -> None:
        assert parse_row_counts("t:-1\nu:1.5\nv:7") == {"v": 7}


# --- the retention ceiling (files/06 §1, HB-I8) ------------------------------------------


class TestRetentionCeiling:
    def test_the_ceiling_is_derived_not_chosen(self) -> None:
        """files/06 §1 (KVKK-7 + DEST-2017): periodic destruction at intervals
        ≤ 6 months. pgBackRest's time retention keeps the full backup that
        straddles the window, so the oldest copy is the window plus one
        full-backup interval — and that must fit inside the shortest six
        calendar months, or a subject erased at the start of it is still
        readable from a backup at the next destruction run."""
        assert SHORTEST_SIX_MONTHS_DAYS == min(
            (datetime(2026 + (m + 6 > 12), (m + 6 - 1) % 12 + 1, 1) - datetime(2026, m, 1)).days
            for m in range(1, 13)
        )
        assert RETENTION_CEILING_DAYS == SHORTEST_SIX_MONTHS_DAYS - FULL_BACKUP_INTERVAL_DAYS

    def test_a_window_within_the_ceiling_is_accepted(self) -> None:
        assert validate_retention_days("30") == 30
        assert validate_retention_days(str(RETENTION_CEILING_DAYS)) == RETENTION_CEILING_DAYS

    def test_a_window_past_the_ceiling_is_refused(self) -> None:
        with pytest.raises(StatusError, match="files/06"):
            validate_retention_days(str(RETENTION_CEILING_DAYS + 1))

    @pytest.mark.parametrize("raw", ["0", "-3", "", "seven", "1.5"])
    def test_a_window_that_keeps_nothing_or_is_not_a_number_is_refused(self, raw: str) -> None:
        with pytest.raises(StatusError):
            validate_retention_days(raw)


# --- the drill's disk headroom -------------------------------------------------------------


class TestHeadroom:
    def test_twice_the_database_is_enough(self) -> None:
        assert restore_headroom_ok(free_bytes=2 * 10_000, database_bytes=10_000)

    def test_less_than_twice_is_refused(self) -> None:
        """The restored copy is the database's size; the rule keeps at least
        as much free again, so a drill never leaves production with less
        headroom than its own database occupies."""
        assert not restore_headroom_ok(free_bytes=2 * 10_000 - 1, database_bytes=10_000)

    def test_an_unknown_size_is_refused(self) -> None:
        assert not restore_headroom_ok(free_bytes=10**12, database_bytes=0)


# --- ages, which the probes service publishes --------------------------------------------


class TestAges:
    def test_no_record_is_infinitely_old(self, tmp_path: Path) -> None:
        assert backup_age_minutes(tmp_path, NOW) == math.inf
        assert restore_drill_age_days(tmp_path, NOW) == math.inf
        assert backup_age_minutes(tmp_path / "absent", NOW) == math.inf

    def test_the_backup_age_is_from_the_newest_stop_time(self, tmp_path: Path) -> None:
        write_record(tmp_path, backup_record(_summary(), recorded_at=NOW, retention_days=None))
        assert backup_age_minutes(tmp_path, NOW) == pytest.approx(117.0)

    def test_the_drill_age_counts_only_passing_drills(self, tmp_path: Path) -> None:
        write_record(tmp_path, drill_record(_measurements(), finished_at=NOW - timedelta(days=10)))
        write_record(
            tmp_path,
            drill_record(
                _measurements(checks={"rows_checksum": False}), finished_at=NOW - timedelta(days=1)
            ),
        )
        assert restore_drill_age_days(tmp_path, NOW) == pytest.approx(10.0)

    def test_an_unreadable_record_is_ignored_not_trusted(self, tmp_path: Path) -> None:
        (tmp_path / "backup-garbage.json").write_text("{", encoding="utf-8")
        (tmp_path / "backup-wrong.json").write_text('{"kind": "backup"}', encoding="utf-8")
        assert backup_age_minutes(tmp_path, NOW) == math.inf


# --- the host CLI -------------------------------------------------------------------------


class TestCli:
    def test_backup_record_reads_info_from_stdin(self, tmp_path: Path) -> None:
        info = _info(
            _backup(
                "20260927-100000F", "full", NOW - timedelta(hours=1), NOW - timedelta(minutes=50)
            )
        )
        result = subprocess.run(  # noqa: S603
            [sys.executable, str(STATUS_PY), "backup-record", "--status-dir", str(tmp_path)],
            input=info,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        records = list(tmp_path.glob("backup-*.json"))
        assert len(records) == 1
        assert json.loads(records[0].read_text(encoding="utf-8"))["label"] == "20260927-100000F"

    def test_newest_backup_prints_a_summary(self) -> None:
        info = _info(
            _backup("L", "full", NOW - timedelta(hours=1), NOW - timedelta(minutes=50), size=77)
        )
        assert status.main(["newest-backup"], stdin=info) == 0

    def test_validate_retention_refuses_with_exit_2(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert status.main(["validate-retention", str(RETENTION_CEILING_DAYS + 1)]) == 2
        assert "HB-I8" in capsys.readouterr().err

    def test_headroom_exit_code(self) -> None:
        assert status.main(["headroom", "--free-bytes", "20", "--database-bytes", "10"]) == 0
        assert status.main(["headroom", "--free-bytes", "19", "--database-bytes", "10"]) == 3

    @staticmethod
    def _work_dir(tmp_path: Path, **verify_overrides: bool) -> Path:
        """The files scripts/backup/drill_lib.sh leaves behind, one per step."""
        work = tmp_path / "work"
        work.mkdir()
        summary = status.summary_json(_summary())
        (work / "backup.json").write_text(json.dumps(summary), encoding="utf-8")
        manifest = {"run_id": RUN_ID, "recovery_target": "2026-09-27 11:02:00.1+00"}
        (work / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        archive = {"archived": True, "rpo_observed_s": 58.25}
        (work / "archive.json").write_text(json.dumps(archive), encoding="utf-8")
        verify = {name: True for name in DRILL_CHECKS if name != "repository_encrypted"}
        verify.update(verify_overrides)
        (work / "verify.json").write_text(json.dumps(verify), encoding="utf-8")
        (work / "counts.txt").write_text("sessions:3\nnotes:1\n", encoding="utf-8")
        (work / "repo_check.txt").write_text("Salted__\nSalted__\n", encoding="utf-8")
        return work

    @staticmethod
    def _drill_argv(status_dir: Path, work: Path) -> list[str]:
        return [
            "drill-record",
            "--status-dir",
            str(status_dir),
            "--work-dir",
            str(work),
            "--target",
            "ci",
            "--started-at",
            "2026-09-27T11:00:00Z",
            "--restore-seconds",
            "37",
        ]

    def test_drill_record_from_the_engine_work_dir(self, tmp_path: Path) -> None:
        work = self._work_dir(tmp_path)
        out = tmp_path / "status"
        assert status.main(self._drill_argv(out, work)) == 0
        written = list(out.glob("restore-drill-*.json"))
        assert len(written) == 1
        record = json.loads(written[0].read_text(encoding="utf-8"))
        assert record["verdict"] == "pass"
        assert record["rpo_observed_s"] == 58.25
        assert record["restore_seconds"] == 37
        assert record["row_counts"] == {"sessions": 3, "notes": 1}
        assert record["second_location"] == "unconfigured"

    def test_a_failing_drill_exits_1(self, tmp_path: Path) -> None:
        work = self._work_dir(tmp_path, sentinel_absent=False)
        assert status.main(self._drill_argv(tmp_path / "status", work)) == 1

    def test_a_plaintext_repository_file_fails_the_drill(self, tmp_path: Path) -> None:
        work = self._work_dir(tmp_path)
        (work / "repo_check.txt").write_text("Salted__\nPGDMP???\n", encoding="utf-8")
        assert status.main(self._drill_argv(tmp_path / "status", work)) == 1

    def test_a_drill_that_stopped_early_is_recorded_as_a_failure(self, tmp_path: Path) -> None:
        """No archive file, no verify file, no restore time: every step that
        did not run is a named failure in the evidence, not a missing file."""
        work = tmp_path / "work"
        work.mkdir()
        (work / "manifest.json").write_text(json.dumps({"run_id": RUN_ID}), encoding="utf-8")
        argv = self._drill_argv(tmp_path / "status", work)
        argv = argv[: argv.index("--restore-seconds")]
        assert status.main(argv) == 1
        written = next((tmp_path / "status").glob("restore-drill-*.json"))
        record = json.loads(written.read_text(encoding="utf-8"))
        assert "rpo_not_measured" in record["failures"]
        assert "restore_not_run" in record["failures"]
        assert "repository_encrypted" in record["failures"]

    def test_get_prints_one_field(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        path = tmp_path / "m.json"
        path.write_text(json.dumps({"run_id": RUN_ID, "rows": {"count": 2}}), encoding="utf-8")
        assert status.main(["get", str(path), "run_id"]) == 0
        assert capsys.readouterr().out.strip() == RUN_ID
        assert status.main(["get", str(path), "absent"]) == 2

    def test_ages_prints_json(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert status.main(["ages", "--status-dir", str(tmp_path)]) == 0
        ages = json.loads(capsys.readouterr().out)
        assert ages == {"backup_age_min": None, "restore_drill_age_days": None}

    def test_an_unknown_subcommand_exits_2(self) -> None:
        with pytest.raises(SystemExit) as exc:
            status.main(["restore-now"])
        assert exc.value.code == 2

"""INT-202 — backup and restore-drill status records. Standard library only.

The production host runs this file with its system ``python3`` and no
virtualenv (``infra/staging/lib.sh`` requires only ``python3``), so it imports
nothing outside the standard library and nothing relative:
``tests/infra/test_backup_status.py`` holds it to that.

It does four things:

* turns ``pgbackrest info --output=json`` into the newest backup's summary and
  a **backup record**;
* turns a drill's measurements into a **drill record** with a verdict against
  the two budgets files/10 §3 states — RPO 15 min, RTO 4 h — and every check;
* reads the records back as ages, which the probes service publishes as
  ``sec_backup_age_min`` and ``sec_restore_drill_age_days``;
* validates a retention window against the ceiling files/06 §1 implies, for
  the day HB-I8(a) is answered.

Every record is clocks, sizes, labels, booleans and per-table integers. There
is no field a patient value could occupy (invariants 3 and 6).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

#: The two figures files/10 §3 and the INT-202 acceptance state.
RPO_BUDGET_S: Final = 15 * 60
RTO_BUDGET_S: Final = 4 * 60 * 60

#: The schedule this change installs (infra/staging/backup.sh): a full backup
#: every Sunday, a differential every other day.
FULL_BACKUP_INTERVAL_DAYS: Final = 7

#: files/06 §1, KVKK-7 + DEST-2017: periodic destruction at intervals of at
#: most six months. The shortest six-calendar-month span is 181 days (1 Jan →
#: 1 Jul, 1 Sep → 1 Mar in a common year).
SHORTEST_SIX_MONTHS_DAYS: Final = 181

#: pgBackRest's time retention keeps the full backup that straddles the
#: window, so the oldest copy on disk is the window plus one full-backup
#: interval. That copy still holds the wrapped DEKs of every subject erased
#: since it was taken, so it must be gone by the next destruction run.
RETENTION_CEILING_DAYS: Final = SHORTEST_SIX_MONTHS_DAYS - FULL_BACKUP_INTERVAL_DAYS

ISSUE: Final = "INT-202"
STANZA: Final = "intake"
BACKUP_PREFIX: Final = "backup-"
DRILL_PREFIX: Final = "restore-drill-"
DRILL_TARGETS: Final = frozenset({"staging", "ci"})

#: Every check a drill reports; a missing one is a failure, never a pass.
DRILL_CHECKS: Final = (
    "rows_count",
    "rows_checksum",
    "retained_readable",
    "erased_unreadable",
    "erased_same_row",
    "sentinel_absent",
    "repository_encrypted",
)

#: The OpenSSL salted-cipher header pgBackRest writes at the start of every
#: file in an encrypted repository.
CIPHER_MAGIC: Final = "Salted__"

_RUN_ID = re.compile(r"^[0-9a-f]{32}$")
_MAX_RELNAME: Final = 63
_MEASUREMENT_KEYS: Final = frozenset(
    {
        "target",
        "run_id",
        "started_at",
        "backup",
        "recovery_target",
        "rpo_observed_s",
        "restore_seconds",
        "checks",
        "row_counts",
        "second_location",
        "retention_days",
    }
)

EXIT_OK: Final = 0
EXIT_FAILED: Final = 1
EXIT_REFUSED: Final = 2
EXIT_NO_HEADROOM: Final = 3


class StatusError(ValueError):
    """An input is not what the backup tooling produces."""


@dataclass(frozen=True, slots=True)
class BackupSummary:
    """The newest backup in the repository, as ``pgbackrest info`` reports it."""

    label: str
    type: str
    started_at: datetime
    stopped_at: datetime
    database_bytes: int
    repos: tuple[int, ...]
    error: bool


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(raw: object) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


# --- pgbackrest info ---------------------------------------------------------------------


def newest_backup(info_json: str) -> BackupSummary:
    """The newest completed backup of the ``intake`` stanza."""
    try:
        stanzas = json.loads(info_json)
    except json.JSONDecodeError as err:
        raise StatusError(f"pgbackrest info is not JSON: {err.msg}") from err
    if not isinstance(stanzas, list) or not stanzas:
        raise StatusError("pgbackrest info lists no stanza")
    stanza = next((s for s in stanzas if isinstance(s, dict) and s.get("name") == STANZA), None)
    if stanza is None:
        raise StatusError(f"pgbackrest info has no {STANZA!r} stanza")
    backups = [b for b in stanza.get("backup") or [] if isinstance(b, dict)]
    if not backups:
        raise StatusError("no backup exists in the repository yet: run a full backup first")
    newest = max(backups, key=lambda b: int(b["timestamp"]["stop"]))
    repos = tuple(sorted(int(r["key"]) for r in stanza.get("repo") or [] if isinstance(r, dict)))
    return BackupSummary(
        label=str(newest["label"]),
        type=str(newest["type"]),
        started_at=datetime.fromtimestamp(int(newest["timestamp"]["start"]), UTC),
        stopped_at=datetime.fromtimestamp(int(newest["timestamp"]["stop"]), UTC),
        database_bytes=int(newest.get("info", {}).get("size", 0)),
        repos=repos or (1,),
        error=bool(newest.get("error", False)),
    )


def second_location_state(repos: Sequence[int]) -> str:
    """``repo1`` is the host's own; a second location is a second repository
    (pgBackRest repo2), added once HB-I8(b) names the site."""
    return "configured" if any(key > 1 for key in repos) else "unconfigured"


def summary_json(summary: BackupSummary) -> dict[str, Any]:
    return {
        "label": summary.label,
        "type": summary.type,
        "started_at": _iso(summary.started_at),
        "stopped_at": _iso(summary.stopped_at),
        "database_bytes": summary.database_bytes,
        "repos": list(summary.repos),
        "error": summary.error,
    }


def backup_record(
    summary: BackupSummary, *, recorded_at: datetime, retention_days: int | None
) -> dict[str, Any]:
    """The record ``backup.sh backup`` writes after every backup."""
    return {
        "kind": "backup",
        "issue": ISSUE,
        **summary_json(summary),
        "second_location": second_location_state(summary.repos),
        "retention_days": retention_days,
        "recorded_at": _iso(recorded_at),
    }


# --- the drill record --------------------------------------------------------------------


def parse_row_counts(raw: str) -> dict[str, int]:
    """psql ``-At -F:`` output → ``{table: count}``.

    Only a bare identifier and a non-negative integer pass. A psql error
    carrying a fragment of a row is exactly what arrives where a count was
    expected when something goes wrong, and it is dropped here.
    """
    counts: dict[str, int] = {}
    for line in raw.splitlines():
        name, separator, value = line.strip().partition(":")
        name = name.strip()
        if not separator or not name.isidentifier() or len(name) > _MAX_RELNAME:
            continue
        value = value.strip()
        if not value.isdigit():
            continue
        counts[name] = int(value)
    return counts


def repository_encrypted(header_lines: str) -> bool:
    """Every sampled repository file begins with the salted-cipher header."""
    lines = [line for line in header_lines.splitlines() if line]
    return bool(lines) and all(line == CIPHER_MAGIC for line in lines)


def _number(raw: object) -> float | None:
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        return None
    return float(raw)


def drill_record(measurements: Mapping[str, Any], *, finished_at: datetime) -> dict[str, Any]:
    """The drill's evidence: the measurements, the budgets and a verdict."""
    unexpected = set(measurements) - _MEASUREMENT_KEYS
    if unexpected:
        raise StatusError(f"unexpected drill measurement(s): {sorted(unexpected)}")
    run_id = str(measurements.get("run_id", ""))
    if not _RUN_ID.match(run_id):
        raise StatusError("run_id is not 32 lowercase hex characters")
    target = measurements.get("target")
    if target not in DRILL_TARGETS:
        raise StatusError(f"target must be one of {sorted(DRILL_TARGETS)}")

    raw_checks = measurements.get("checks") or {}
    checks = {name: raw_checks.get(name) is True for name in DRILL_CHECKS}
    failures = [name for name, ok in checks.items() if not ok]

    rpo = _number(measurements.get("rpo_observed_s"))
    rto = _number(measurements.get("restore_seconds"))
    if rpo is None:
        failures.append("rpo_not_measured")
    elif rpo > RPO_BUDGET_S:
        failures.append("rpo_exceeded")
    if rto is None:
        failures.append("restore_not_run")
    elif rto > RTO_BUDGET_S:
        failures.append("rto_exceeded")

    backup = measurements.get("backup") or {}
    return {
        "kind": "restore_drill",
        "issue": ISSUE,
        "target": target,
        "run_id": run_id,
        "started_at": measurements.get("started_at"),
        "finished_at": _iso(finished_at),
        "backup": {key: backup.get(key) for key in ("label", "type", "stopped_at")},
        "recovery_target": measurements.get("recovery_target"),
        "rpo_budget_s": RPO_BUDGET_S,
        "rpo_observed_s": rpo,
        "rto_budget_s": RTO_BUDGET_S,
        "restore_seconds": None if rto is None else int(rto),
        "checks": checks,
        "row_counts": dict(measurements.get("row_counts") or {}),
        "second_location": measurements.get("second_location"),
        "retention_days": measurements.get("retention_days"),
        "verdict": "fail" if failures else "pass",
        "failures": failures,
    }


def _load_json(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def measurements_from_work_dir(
    work: Path,
    *,
    target: str,
    started_at: str,
    restore_seconds: int | None,
    retention_days: int | None,
) -> dict[str, Any]:
    """Assemble a drill's measurements from the files the engine left in *work*.

    A file that is missing (a step that never ran) leaves its checks unset,
    which :func:`drill_record` reports as failures.
    """
    backup = _load_json(work / "backup.json")
    manifest = _load_json(work / "manifest.json")
    archive = _load_json(work / "archive.json")
    verify = _load_json(work / "verify.json")
    checks: dict[str, bool] = {
        key: bool(value) for key, value in verify.items() if key in DRILL_CHECKS
    }
    header_path = work / "repo_check.txt"
    if header_path.is_file():
        checks["repository_encrypted"] = repository_encrypted(
            header_path.read_text(encoding="utf-8")
        )
    counts_path = work / "counts.txt"
    counts = (
        parse_row_counts(counts_path.read_text(encoding="utf-8")) if counts_path.is_file() else {}
    )
    repos = backup.get("repos") or [1]
    return {
        "target": target,
        "run_id": manifest.get("run_id", ""),
        "started_at": started_at,
        "backup": {key: backup.get(key) for key in ("label", "type", "stopped_at")},
        "recovery_target": manifest.get("recovery_target"),
        "rpo_observed_s": archive.get("rpo_observed_s") if archive.get("archived") else None,
        "restore_seconds": restore_seconds,
        "checks": checks,
        "row_counts": counts,
        "second_location": second_location_state([int(r) for r in repos]),
        "retention_days": retention_days,
    }


# --- records on disk ---------------------------------------------------------------------


def write_record(directory: Path, record: Mapping[str, Any]) -> Path:
    """Write *record* atomically as ``<kind>-<timestamp>.json`` in *directory*."""
    prefix = BACKUP_PREFIX if record.get("kind") == "backup" else DRILL_PREFIX
    stamp = str(record.get("recorded_at") or record.get("finished_at") or _iso(datetime.now(UTC)))
    directory.mkdir(parents=True, exist_ok=True)
    name = f"{prefix}{stamp.replace(':', '').replace('-', '')}"
    if record.get("run_id"):
        name += f"-{str(record['run_id'])[:8]}"
    target = directory / f"{name}.json"
    handle, temp = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".json")
    with os.fdopen(handle, "w", encoding="utf-8") as out:
        json.dump(record, out, indent=2, sort_keys=True)
        out.write("\n")
    os.replace(temp, target)
    return target


def _records(directory: Path, prefix: str) -> list[dict[str, Any]]:
    if not directory.is_dir():
        return []
    return [_load_json(path) for path in sorted(directory.glob(f"{prefix}*.json"))]


def backup_age_minutes(directory: Path, now: datetime) -> float:
    """Minutes since the newest backup finished; +Inf when there is none."""
    stops = [
        stop
        for record in _records(directory, BACKUP_PREFIX)
        if record.get("kind") == "backup" and (stop := _parse_iso(record.get("stopped_at")))
    ]
    if not stops:
        return math.inf
    return (now - max(stops)).total_seconds() / 60


def restore_drill_age_days(directory: Path, now: datetime) -> float:
    """Days since the newest PASSING drill; +Inf when there is none."""
    finishes = [
        finished
        for record in _records(directory, DRILL_PREFIX)
        if record.get("kind") == "restore_drill"
        and record.get("verdict") == "pass"
        and (finished := _parse_iso(record.get("finished_at")))
    ]
    if not finishes:
        return math.inf
    return (now - max(finishes)).total_seconds() / 86400


# --- retention and headroom --------------------------------------------------------------


def validate_retention_days(raw: str) -> int:
    """A retention window in days, or a refusal that says why."""
    if not raw.strip().isdigit():
        raise StatusError(f"retention must be a whole number of days, not {raw!r}")
    days = int(raw)
    if days < 1:
        raise StatusError("a retention of 0 days keeps no backup")
    if days > RETENTION_CEILING_DAYS:
        raise StatusError(
            f"a {days}-day window keeps a full backup up to {days + FULL_BACKUP_INTERVAL_DAYS} "
            f"days, past the shortest six-month span ({SHORTEST_SIX_MONTHS_DAYS} days): "
            "files/06 §1 (KVKK-7 + DEST-2017) destroys at least every six months, and an older "
            "backup still "
            f"opens subjects erased since it was taken. The ceiling is {RETENTION_CEILING_DAYS} "
            "days (files/HUMAN_BLOCKERS.md HB-I8)."
        )
    return days


def restore_headroom_ok(*, free_bytes: int, database_bytes: int) -> bool:
    """The drill restores a full copy of the database onto the same host. It
    runs only when the host keeps at least as much free again afterwards, so a
    drill never leaves production with less headroom than its own database."""
    return database_bytes > 0 and free_bytes >= 2 * database_bytes


# --- CLI -----------------------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="backup-status", description="INT-202 backup status records"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("newest-backup", help="stdin: pgbackrest info JSON → the newest backup")
    rec = sub.add_parser("backup-record", help="stdin: pgbackrest info JSON → a backup record")
    rec.add_argument("--status-dir", type=Path, required=True)
    rec.add_argument("--retention-days", type=int, default=None)
    drill = sub.add_parser("drill-record", help="the engine's work dir → a drill record")
    drill.add_argument("--status-dir", type=Path, required=True)
    drill.add_argument("--work-dir", type=Path, required=True)
    drill.add_argument("--target", default="")
    drill.add_argument("--started-at", default="")
    drill.add_argument("--restore-seconds", type=int, default=None)
    drill.add_argument("--retention-days", type=int, default=None)
    ret = sub.add_parser("validate-retention")
    ret.add_argument("days")
    room = sub.add_parser("headroom")
    room.add_argument("--free-bytes", type=int, required=True)
    room.add_argument("--database-bytes", type=int, required=True)
    ages = sub.add_parser("ages")
    ages.add_argument("--status-dir", type=Path, required=True)
    get = sub.add_parser("get", help="print one top-level field of a JSON file")
    get.add_argument("file", type=Path)
    get.add_argument("key")
    return parser


def _finite(value: float) -> float | None:
    return None if math.isinf(value) else round(value, 3)


def main(argv: Sequence[str] | None = None, stdin: str | None = None) -> int:
    args = _parser().parse_args(argv)
    now = datetime.now(UTC)
    try:
        if args.command == "newest-backup":
            summary = newest_backup(sys.stdin.read() if stdin is None else stdin)
            print(json.dumps(summary_json(summary), sort_keys=True))
            return EXIT_OK
        if args.command == "backup-record":
            summary = newest_backup(sys.stdin.read() if stdin is None else stdin)
            path = write_record(
                args.status_dir,
                backup_record(summary, recorded_at=now, retention_days=args.retention_days),
            )
            print(f"backup record: {path}")
            return EXIT_OK
        if args.command == "drill-record":
            measurements = measurements_from_work_dir(
                args.work_dir,
                target=args.target,
                started_at=args.started_at,
                restore_seconds=args.restore_seconds,
                retention_days=args.retention_days,
            )
            record = drill_record(measurements, finished_at=now)
            path = write_record(args.status_dir, record)
            print(f"restore drill evidence: {path} — verdict {record['verdict']}")
            for failure in record["failures"]:
                print(f"  failed: {failure}")
            return EXIT_OK if record["verdict"] == "pass" else EXIT_FAILED
        if args.command == "validate-retention":
            print(validate_retention_days(args.days))
            return EXIT_OK
        if args.command == "headroom":
            ok = restore_headroom_ok(free_bytes=args.free_bytes, database_bytes=args.database_bytes)
            return EXIT_OK if ok else EXIT_NO_HEADROOM
        if args.command == "ages":
            print(
                json.dumps(
                    {
                        "backup_age_min": _finite(backup_age_minutes(args.status_dir, now)),
                        "restore_drill_age_days": _finite(
                            restore_drill_age_days(args.status_dir, now)
                        ),
                    },
                    sort_keys=True,
                )
            )
            return EXIT_OK
        value = _load_json(args.file).get(args.key)
        if value is None:
            raise StatusError(f"{args.file.name} has no {args.key!r}")
        print(value if isinstance(value, str) else json.dumps(value))
        return EXIT_OK
    except StatusError as err:
        print(f"backup status: refused — {err}", file=sys.stderr)
        return EXIT_REFUSED


if __name__ == "__main__":
    raise SystemExit(main())

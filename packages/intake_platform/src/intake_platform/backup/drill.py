"""INT-202 — the restore drill: its ordered plan and its PHI boundary.

The drill proves the one property a backup cannot assert about itself: that
a restore works. files/10 §9 row ``backups`` names the threat directly —
*"[Nc] restores never exercised, discovered during the incident"*.

``scripts/backup/drill_lib.sh`` executes the plan, on the production host
(``infra/staging/backup.sh drill``, quarterly) and in CI
(``scripts/backup/ci_drill.sh``). This module states the plan once, so the
dry run an operator reads is the list the engine runs, and holds the two
PHI rules the engine relies on:

* the restored cluster never lands where the workspace can reach it
  (:func:`assert_restore_target_outside_workspace`, INT-315) — it lives in a
  container volume, and the scratch cluster runs with no network;
* verification reads counts and the synthetic canary, never a column of
  record content (:data:`ROW_COUNT_SQL`).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .config import BackupConfigError, PgBackRestConfig
from .status import RPO_BUDGET_S, RTO_BUDGET_S

__all__ = [
    "RESTORE_PGDATA",
    "RESTORE_TARGET",
    "ROW_COUNT_SQL",
    "RPO_BUDGET_S",
    "RTO_BUDGET_S",
    "SCRATCH_ARGS",
    "DrillStep",
    "RestoreTargetInsideWorkspaceError",
    "assert_restore_target_outside_workspace",
    "plan_restore_drill",
]

#: The scratch volume's mount point, and the data directory inside it. A
#: named volume inside the container runtime, never a host path.
RESTORE_TARGET: Final = "/restore"
RESTORE_PGDATA: Final = f"{RESTORE_TARGET}/pgdata"

#: The scratch cluster: archiving off (a restored cluster that archived would
#: push a second timeline into the production stanza) and no TCP listener.
SCRATCH_ARGS: Final = ("-D", RESTORE_PGDATA, "-c", "archive_mode=off", "-c", "listen_addresses=")

#: Exact per-table row counts, with no column ever projected. ``query_to_xml``
#: runs the count server-side and returns only the integer.
ROW_COUNT_SQL: Final = (
    "SELECT c.relname, "
    "(xpath('/row/cnt/text()', query_to_xml("
    "format('SELECT count(*) AS cnt FROM %I.%I', n.nspname, c.relname), "
    "false, true, '')))[1]::text::bigint AS rows "
    "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
    "WHERE c.relkind = 'r' AND n.nspname = 'public' ORDER BY 1"
)


class RestoreTargetInsideWorkspaceError(RuntimeError):
    """A restored cluster would land somewhere the workspace can read."""


@dataclass(frozen=True, slots=True)
class DrillStep:
    """One ordered step of the drill: where it runs, what it runs, and why."""

    name: str
    where: str
    argv: tuple[str, ...]
    description: str


def _contains(root: Path, candidate: Path) -> bool:
    return candidate == root or root in candidate.parents


def _readings(path: Path) -> tuple[Path, ...]:
    """The two places one spelling can mean, deduplicated.

    ``abspath`` is the reading ``git status`` uses; ``resolve`` is where the
    bytes land. They disagree exactly when a link is involved (INT-315).
    """
    absolute = Path(os.path.abspath(path))
    real = Path(path).resolve()
    return (absolute,) if absolute == real else (absolute, real)


def assert_restore_target_outside_workspace(target: Path, repo_root: Path) -> None:
    """Refuse a restore target the workspace can reach (invariants 3 and 6).

    Accepting requires every reading of both paths to agree the target is
    outside, so an ambiguous spelling fails closed (INT-315).
    """
    for root in _readings(Path(repo_root)):
        for candidate in _readings(Path(target)):
            if _contains(root, candidate):
                raise RestoreTargetInsideWorkspaceError(
                    f"restore target {target} is inside the workspace {repo_root} "
                    f"(read as {candidate} under {root}); restore into a container "
                    "volume or a path outside the repository"
                )


def plan_restore_drill(config: PgBackRestConfig) -> list[DrillStep]:
    """The ordered drill, as ``scripts/backup/drill_lib.sh`` runs it."""
    if not config.pitr_capable:
        raise BackupConfigError(
            f"stanza {config.stanza!r} is not PITR-capable: asynchronous WAL archiving and "
            "repository encryption must both be configured (files/10 §3)"
        )
    stanza = f"--stanza={config.stanza}"
    primary = "primary postgres container, as the postgres user"
    python = "API image (host) or the workspace venv (CI)"
    return [
        DrillStep(
            "newest_backup",
            primary,
            ("pgbackrest", stanza, "info", "--output=json"),
            "the newest backup to restore from; none is a refusal",
        ),
        DrillStep(
            "headroom",
            "host",
            ("status.py", "headroom", "--free-bytes", "$FREE", "--database-bytes", "$SIZE"),
            "twice the database size free, so production keeps its own headroom",
        ),
        DrillStep(
            "prepare_canary",
            python,
            ("python", "-m", "intake_platform.backup.canary", "prepare"),
            "synthetic rows and two sealed subjects after the backup; erase one; a sentinel",
        ),
        DrillStep(
            "wait_archived",
            python,
            (
                "python",
                "-m",
                "intake_platform.backup.canary",
                "wait-archived",
                f"--timeout={RPO_BUDGET_S}",
            ),
            f"the sentinel's WAL segment reaches the repository within RPO {RPO_BUDGET_S}s",
        ),
        DrillStep(
            "repository_encrypted",
            "scratch container, --network none, repository read-only",
            ("head", "-c", "8", "<every repository file>"),
            "every repository file begins with the salted-cipher header",
        ),
        DrillStep(
            "restore",
            "scratch container, --network none, repository read-only",
            (
                "pgbackrest",
                stanza,
                "--repo=1",
                f"--pg1-path={RESTORE_PGDATA}",
                "--type=time",
                "--target=$RECOVERY_TARGET",
                "--target-action=promote",
                "restore",
            ),
            "point-in-time restore into a scratch volume, never a host path",
        ),
        DrillStep(
            "start_scratch",
            "scratch container, --network none, repository read-only",
            ("postgres", *SCRATCH_ARGS),
            "replay WAL to the target and promote, with archiving off and no listener",
        ),
        DrillStep(
            "wait_promoted",
            "scratch container",
            ("psql", "--command", "SELECT pg_is_in_recovery()"),
            f"promoted within RTO {RTO_BUDGET_S}s",
        ),
        DrillStep(
            "row_counts",
            "scratch container",
            ("psql", "--no-psqlrc", "--tuples-only", "--command", ROW_COUNT_SQL),
            "per-table row counts of the restored application database; no column",
        ),
        DrillStep(
            "verify_canary",
            python,
            ("python", "-m", "intake_platform.backup.canary", "verify"),
            "rows and checksum, the kept subject opens, the erased one stays erased, no sentinel",
        ),
        DrillStep(
            "teardown",
            "host",
            ("docker", "rm", "-f", "<scratch>", "&&", "docker", "volume", "rm", "<scratch>"),
            "the restored cluster does not outlive the drill",
        ),
        DrillStep(
            "evidence",
            "host",
            ("status.py", "drill-record"),
            "clocks, budgets, checks and counts; a verdict; nothing an identifier could occupy",
        ),
    ]

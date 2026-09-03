"""INT-202 — the restore drill: the plan, the refusals and the evidence shape.

The drill proves the one property a backup strategy cannot assert about
itself: that a restore works. files/10 §9 row ``backups`` names the threat
directly — *"[Nc] restores never exercised, discovered during the incident"*.

This module holds the decidable half. It builds the ordered step list, it
refuses the two ways the drill could go wrong quietly, and it defines the
evidence record. It runs nothing: ``scripts/backup/restore_drill.sh`` executes
the steps against a container runtime, and that half needs more disk and more
Docker memory than the recorded host has (HB-I1, HB-I2).

The refusals, both fail-closed:

* **no invented retention.** files/10 §3 states RPO 15 min and RTO 4 h and
  states no retention window; ``06 §3``'s matrix has no row for backup copies.
  The drill will not expire or plan without one, and says which blocker row
  (HB-I8) unblocks it.
* **no PHI on the workspace floor.** A restored cluster is patient data on
  disk. The restore target must resolve outside the repository, the
  verification reads counts and never a column, and the evidence record has
  no field an identifier could sit in (invariants 3 and 6).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from .config import PgBackRestConfig, ReplicationPlan

#: The two figures files/10 §3 and the INT-202 acceptance actually state.
#: Nothing else in this module is a number a human did not write down.
RPO_BUDGET_S: Final = 15 * 60
RTO_BUDGET_S: Final = 4 * 60 * 60

#: Recorded in files/HUMAN_BLOCKERS.md §4. HB-I1 is disk — "Free 80–100 GB";
#: the lower bound of the owner's own figure is the gate. HB-I2 is Docker
#: memory — "the security + observability tiers alone need 22 GB"; the drill
#: stands up a second Postgres, a second object store and a restore target,
#: so it is gated at the same declared figure rather than a guess.
MIN_FREE_DISK_BYTES: Final = 80 * 1024**3
MIN_DOCKER_MEMORY_BYTES: Final = 22 * 1024**3

#: Where the restored cluster lives. A named volume inside the container
#: runtime, never a host path — see :func:`assert_restore_target_outside_workspace`.
RESTORE_TARGET: Final = "/restore"

#: Exact per-table row counts from the restored cluster, with no column ever
#: projected. ``query_to_xml`` runs the count server-side and returns only the
#: integer, so no patient value crosses the wire, reaches a log, or lands in
#: the evidence file.
ROW_COUNT_SQL: Final = (
    "SELECT c.relname, "
    "(xpath('/row/cnt/text()', query_to_xml("
    "format('SELECT count(*) AS cnt FROM %I.%I', n.nspname, c.relname), "
    "false, true, '')))[1]::text::bigint AS rows "
    "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
    "WHERE c.relkind = 'r' AND n.nspname = 'public' ORDER BY 1"
)


class RetentionNotConfiguredError(RuntimeError):
    """No human has stated how many full backups to keep."""


class RestoreTargetInsideWorkspaceError(RuntimeError):
    """A restored cluster would land somewhere the workspace can read."""


@dataclass(frozen=True, slots=True)
class DrillStep:
    """One ordered step of the drill."""

    name: str
    argv: tuple[str, ...]
    description: str


@dataclass(frozen=True, slots=True)
class DrillBlocked:
    """The host cannot run the drill, and this is why."""

    reason: str


def host_preflight(free_disk_bytes: int, docker_memory_bytes: int) -> DrillBlocked | None:
    """Return why this host cannot run the drill, or ``None`` if it can.

    Deliberately not a skip and deliberately not a smaller drill: the answer
    to "the machine is too small" is a typed refusal naming the row that
    changes the machine.
    """
    short: list[str] = []
    if free_disk_bytes < MIN_FREE_DISK_BYTES:
        short.append(
            f"HB-I1 (disk): {free_disk_bytes / 1024**3:.0f} GiB free, "
            f"the drill needs {MIN_FREE_DISK_BYTES // 1024**3} GiB"
        )
    if docker_memory_bytes < MIN_DOCKER_MEMORY_BYTES:
        short.append(
            f"HB-I2 (container memory): {docker_memory_bytes / 1024**3:.0f} GiB allocated, "
            f"the drill needs {MIN_DOCKER_MEMORY_BYTES // 1024**3} GiB"
        )
    if not short:
        return None
    return DrillBlocked(reason="; ".join(short))


def _contains(root: Path, candidate: Path) -> bool:
    return candidate == root or root in candidate.parents


def _readings(path: Path) -> tuple[Path, ...]:
    """The two places one spelling can mean, deduplicated.

    ``abspath`` is the reading ``git status`` uses: it collapses ``..``
    textually and follows no link, so a symlinked child of the checkout stays
    *under* the checkout. ``resolve`` is where the bytes actually land. The
    two disagree exactly when a link is involved, and a guard that consults
    only one of them can be walked past from the other side (INT-315).
    """
    absolute = Path(os.path.abspath(path))
    real = Path(path).resolve()
    return (absolute,) if absolute == real else (absolute, real)


def assert_restore_target_outside_workspace(target: Path, repo_root: Path) -> None:
    """Refuse a restore target the workspace can reach (invariants 3 and 6).

    A restored cluster is patient data on disk. Inside the repository it is
    one ``git add -A`` from being committed and one ``make check`` from being
    scanned, so a target is refused when it is inside the workspace under
    *any* reading of *either* path. Both sides are read both ways, because
    either side can be the symbolic half:

    * ``infra/../.cache`` is inside however it is spelled — the original case;
    * a target reached through a link that leaves the checkout is still inside
      it, because ``git status`` reports the path and not the link's
      destination. That is the shape this repository's own fresh-worktree
      de-identification-model workflow creates, and resolving the target alone
      answered "outside" (INT-315);
    * a link pointing *into* the checkout is inside it however it is reached;
    * and a checkout named through a link — ``/tmp`` for ``/private/tmp`` —
      judges its own children the same in either spelling.

    Accepting therefore requires every reading to agree the target is outside,
    so an ambiguous spelling fails closed. That costs an operator one rewrite;
    the other way round costs a patient's data on the workspace floor.
    """
    roots = _readings(Path(repo_root))
    candidates = _readings(Path(target))
    for root in roots:
        for candidate in candidates:
            if _contains(root, candidate):
                raise RestoreTargetInsideWorkspaceError(
                    f"restore target {target} is inside the workspace {repo_root} "
                    f"(read as {candidate} under {root}); restore into a container "
                    "volume or a path outside the repository"
                )


def _require_retention(retention_full: int | None) -> int:
    if retention_full is None:
        raise RetentionNotConfiguredError(
            "no backup retention window is configured. files/10 §3 states RPO 15 min and "
            "RTO 4 h and states no retention; 06 §3's matrix has no row for backup copies. "
            "Set PGBACKREST_REPO1_RETENTION_FULL once the owner answers "
            "files/HUMAN_BLOCKERS.md HB-I8 — a guessed window is not a default."
        )
    if retention_full < 1:
        raise RetentionNotConfiguredError(
            f"retention window {retention_full} keeps no full backup (HB-I8)"
        )
    return retention_full


def plan_restore_drill(
    config: PgBackRestConfig,
    replication: ReplicationPlan,
    retention_full: int | None,
    recovery_target_time: str = "$RECOVERY_TARGET_TIME",
) -> list[DrillStep]:
    """The ordered drill: check, back up, expire, restore to a time, verify.

    ``recovery_target_time`` stays a shell reference by default — the drill
    computes it at run time as "now minus the RPO budget", which is what makes
    the restore a *point-in-time* restore rather than a restore of the newest
    full backup.
    """
    keep = _require_retention(retention_full)
    stanza = config.stanza
    if not config.pitr_capable:
        raise ValueError(
            f"stanza {stanza!r} is not PITR-capable: archive-async and repository "
            "encryption must both be configured (files/10 §3)"
        )
    return [
        DrillStep(
            name="stanza_check",
            argv=("pgbackrest", f"--stanza={stanza}", "check"),
            description="the repository is reachable and WAL is arriving",
        ),
        DrillStep(
            name="backup_full",
            argv=("pgbackrest", f"--stanza={stanza}", "--type=full", "backup"),
            description="a full encrypted backup, so the drill restores something it made",
        ),
        DrillStep(
            name="retention_expire",
            argv=(
                "pgbackrest",
                f"--stanza={stanza}",
                f"--repo1-retention-full={keep}",
                "expire",
            ),
            description=f"apply the operator-supplied retention window ({keep} full backups)",
        ),
        DrillStep(
            name="restore",
            argv=(
                "pgbackrest",
                f"--stanza={stanza}",
                "--delta",
                "--type=time",
                f"--target={recovery_target_time}",
                "--target-action=promote",
                f"--pg1-path={RESTORE_TARGET}",
                "restore",
            ),
            description="point-in-time restore into a container volume outside the workspace",
        ),
        DrillStep(
            name="verify_counts",
            argv=("psql", "--no-psqlrc", "--tuples-only", "--command", ROW_COUNT_SQL),
            description="per-table row counts only; no column is ever projected",
        ),
        DrillStep(
            name="verify_replica",
            argv=(
                "mc",
                "ls",
                "--recursive",
                "--summarize",
                f"{replication.target_alias}/{replication.repository_bucket}",
            ),
            description="the second location holds the archive it is supposed to hold",
        ),
        DrillStep(
            name="teardown",
            argv=("rm", "-rf", RESTORE_TARGET),
            description="the restored cluster does not outlive the drill",
        ),
    ]


def drill_evidence_skeleton(config: PgBackRestConfig, retention_full: int | None) -> dict[str, Any]:
    """The evidence record's shape — counts and clocks, never content.

    Every field is either an identifier of the drill itself, a duration, or a
    per-table count. There is no field a patient value could occupy, which is
    how invariant 6 is satisfied by construction rather than by redaction.
    """
    return {
        "issue": "INT-202",
        "stanza": config.stanza,
        "started_at": None,
        "finished_at": None,
        "rto_budget_s": RTO_BUDGET_S,
        "rpo_budget_s": RPO_BUDGET_S,
        "retention_full": retention_full,
        "recovery_target_time": None,
        "restore_seconds": None,
        "row_counts": {},
        "verdict": None,
        "host_preflight": None,
    }

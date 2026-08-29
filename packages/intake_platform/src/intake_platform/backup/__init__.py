"""INT-202 — backups and disaster recovery (files/10 §3, §9 row ``backups``).

Two artefacts under ``infra/backup/`` are the source of truth — the pgBackRest
repository configuration and the object-store replication plan — and this
package is the only thing that reads them. :mod:`.config` loads and refuses;
:mod:`.drill` plans the restore drill, gates it on the host, and defines the
PHI-free evidence record.

Nothing here executes a backup or a restore. ``scripts/backup/restore_drill.sh``
does that, on a host that passes :func:`host_preflight`.
"""

from __future__ import annotations

from .config import (
    CIPHER_PASS_ENV,
    REQUIRED_CIPHER,
    RETENTION_FULL_ENV,
    BackupConfigError,
    PgBackRestConfig,
    ReplicationPlan,
    ReplicationRule,
    load_pgbackrest_config,
    load_replication_plan,
    replication_commands,
)
from .drill import (
    MIN_DOCKER_MEMORY_BYTES,
    MIN_FREE_DISK_BYTES,
    RESTORE_TARGET,
    ROW_COUNT_SQL,
    RPO_BUDGET_S,
    RTO_BUDGET_S,
    DrillBlocked,
    DrillStep,
    RestoreTargetInsideWorkspaceError,
    RetentionNotConfiguredError,
    assert_restore_target_outside_workspace,
    drill_evidence_skeleton,
    host_preflight,
    plan_restore_drill,
)

__all__ = [
    "CIPHER_PASS_ENV",
    "MIN_DOCKER_MEMORY_BYTES",
    "MIN_FREE_DISK_BYTES",
    "REQUIRED_CIPHER",
    "RESTORE_TARGET",
    "RETENTION_FULL_ENV",
    "ROW_COUNT_SQL",
    "RPO_BUDGET_S",
    "RTO_BUDGET_S",
    "BackupConfigError",
    "DrillBlocked",
    "DrillStep",
    "PgBackRestConfig",
    "ReplicationPlan",
    "ReplicationRule",
    "RestoreTargetInsideWorkspaceError",
    "RetentionNotConfiguredError",
    "assert_restore_target_outside_workspace",
    "drill_evidence_skeleton",
    "host_preflight",
    "load_pgbackrest_config",
    "load_replication_plan",
    "plan_restore_drill",
    "replication_commands",
]

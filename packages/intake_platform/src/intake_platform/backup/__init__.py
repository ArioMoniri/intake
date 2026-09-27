"""INT-202 — backups and disaster recovery (files/10 §3, §9 row ``backups``).

Two artefacts under ``infra/backup/`` are the source of truth — the pgBackRest
repository configuration and the object-store replication plan — and
:mod:`.config` is the only thing that reads them. :mod:`.drill` states the
restore drill's plan and its PHI boundary; :mod:`.canary` writes and verifies
the drill's synthetic data; :mod:`.status` turns pgBackRest's report and the
drill's measurements into PHI-free records (standard library only, because
the production host runs it with the system ``python3``); :mod:`.metrics`
publishes their ages.

Nothing here executes a backup or a restore: ``scripts/backup/drill_lib.sh``
does, driven by ``infra/staging/backup.sh`` on the host and
``scripts/backup/ci_drill.sh`` in CI.
"""

from __future__ import annotations

from .config import (
    CIPHER_PASS_ENV,
    REQUIRED_CIPHER,
    BackupConfigError,
    PgBackRestConfig,
    ReplicationPlan,
    ReplicationRule,
    load_pgbackrest_config,
    load_replication_plan,
    replication_commands,
    withheld_rules,
)
from .drill import (
    RESTORE_PGDATA,
    RESTORE_TARGET,
    ROW_COUNT_SQL,
    RPO_BUDGET_S,
    RTO_BUDGET_S,
    DrillStep,
    RestoreTargetInsideWorkspaceError,
    assert_restore_target_outside_workspace,
    plan_restore_drill,
)

__all__ = [
    "CIPHER_PASS_ENV",
    "REQUIRED_CIPHER",
    "RESTORE_PGDATA",
    "RESTORE_TARGET",
    "ROW_COUNT_SQL",
    "RPO_BUDGET_S",
    "RTO_BUDGET_S",
    "BackupConfigError",
    "DrillStep",
    "PgBackRestConfig",
    "ReplicationPlan",
    "ReplicationRule",
    "RestoreTargetInsideWorkspaceError",
    "assert_restore_target_outside_workspace",
    "load_pgbackrest_config",
    "load_replication_plan",
    "plan_restore_drill",
    "replication_commands",
    "withheld_rules",
]

"""INT-202 — ``sec.backup_age_min`` and ``sec.restore_drill_age_days`` (files/08 §4).

Both are computed at scrape time from the status records the host writes
(:mod:`intake_platform.backup.status`), so a scrape always reports the age
now rather than the age when a background loop last looked. Until
:func:`bind_backup_gauges` runs, and whenever no record exists, both read
+Inf: a host where no backup or no passing drill has ever run must alert
(``infra/observability/security-rules.yaml``), never report a fresh one.

The probes service binds them to ``INTAKE_BACKUP_DIR``, the same directory
its ``backup_freshness`` probe watches.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from prometheus_client import Gauge

from .status import backup_age_minutes, restore_drill_age_days

__all__ = [
    "ENV_BACKUP_DIR",
    "SEC_BACKUP_AGE_MIN",
    "SEC_RESTORE_DRILL_AGE_DAYS",
    "bind_backup_gauges",
    "bind_from_env",
]

ENV_BACKUP_DIR: Final = "INTAKE_BACKUP_DIR"
_DEFAULT_BACKUP_DIR: Final = ".cache/backups"

#: Catalogued in observability/metrics_catalog.yaml (inv. 13); files/08 §4 group M.
SEC_BACKUP_AGE_MIN = Gauge(
    "sec_backup_age_min",
    "Minutes since the newest pgBackRest backup finished (+Inf when none exists).",
)
SEC_RESTORE_DRILL_AGE_DAYS = Gauge(
    "sec_restore_drill_age_days",
    "Days since the newest passing restore drill (+Inf when none exists).",
)
SEC_BACKUP_AGE_MIN.set(math.inf)
SEC_RESTORE_DRILL_AGE_DAYS.set(math.inf)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def bind_backup_gauges(status_dir: Path, clock: Callable[[], datetime] = _utc_now) -> None:
    """Compute both gauges from *status_dir* on every scrape."""
    SEC_BACKUP_AGE_MIN.set_function(lambda: backup_age_minutes(status_dir, clock()))
    SEC_RESTORE_DRILL_AGE_DAYS.set_function(lambda: restore_drill_age_days(status_dir, clock()))


def bind_from_env(env: Mapping[str, str]) -> Path:
    status_dir = Path(env.get(ENV_BACKUP_DIR, _DEFAULT_BACKUP_DIR))
    bind_backup_gauges(status_dir)
    return status_dir

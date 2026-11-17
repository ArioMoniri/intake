"""The deploy freeze and the release verdict (INT-187; files/08 §3, §8.2).

Shared by the two sides of the CI/CD module: ``services/api/admin`` writes the
freeze (one key to freeze, four eyes to lift) and renders the verdict, and
``intake_api.admin.release_gate`` — run by ``infra/staging/deploy.sh`` before
it touches the host — reads the same record and the same rule and refuses. See
:mod:`.model` for the record, :mod:`.store` for where it lives and how it fails
closed, and :mod:`.verdict` for the rule.
"""

from __future__ import annotations

from intake_platform.release_freeze.model import DeployFreeze, DeployFreezeChange
from intake_platform.release_freeze.store import (
    ENV_RELEASE_FREEZE_REDIS_URL,
    FREEZE_KEY,
    RedisReleaseFreezeStore,
    ReleaseFreezeConflict,
    ReleaseFreezeStore,
    ReleaseFreezeUnavailable,
    release_freeze_store_from_env,
)
from intake_platform.release_freeze.verdict import ErrorBudget, ReleaseVerdict, release_verdict

__all__ = [
    "ENV_RELEASE_FREEZE_REDIS_URL",
    "FREEZE_KEY",
    "DeployFreeze",
    "DeployFreezeChange",
    "ErrorBudget",
    "RedisReleaseFreezeStore",
    "ReleaseFreezeConflict",
    "ReleaseFreezeStore",
    "ReleaseFreezeUnavailable",
    "ReleaseVerdict",
    "release_freeze_store_from_env",
    "release_verdict",
]

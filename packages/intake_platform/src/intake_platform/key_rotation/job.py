"""One tick of the scheduled KEK rotation (INT-367; files/10 §3, §7; inv. 6, 13, 14).

**What a tick does.** For every tenant KEK in Transit it reads when the latest
version was created, and when that is a quarter or more ago
(:mod:`~intake_platform.key_rotation.schedule`) it calls the existing
:meth:`~intake_platform.envelope.TransitKekProvider.rotate`, then reads the key
back to confirm Transit recorded a new version. It sets
``sec_secret_rotation_due_days{key}`` for each key from what Transit says
after the tick. Ticks are idempotent: run the job as often as you like (the
runbook runs it daily) and each key rotates once a quarter.

**Re-wrap only — why a failure cannot orphan data.** ``rotate`` adds a key
version and nothing else. The job holds no other write: it never sets
``min_decryption_version``, never enables deletion, never deletes or trims a
key, so every wrapped DEK written under any earlier version still unwraps
(files/10 §3; the INT-014 envelope design). New wraps take the newest version;
an existing field moves forward only through
:meth:`~intake_platform.envelope.EnvelopeCipher.rewrap_field`, which re-wraps
the DEK and never touches the data bytes. A rotate that fails leaves the key
exactly as it was.

**Failure is loud.** A key whose rotate failed keeps its negative countdown —
the value ``SecretRotationOverdue`` fires on
(``infra/observability/security-rules.yaml``). A key whose metadata cannot be
read gets no series at all rather than a guessed one, and the report says so.

**No PHI** (invariant 6): the only label is the Transit key name,
``tenant-<tenant_id>``, an identifier.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import httpx
from prometheus_client import Gauge

from intake_platform.envelope import CryptoShredError, TamperError
from intake_platform.key_rotation.schedule import rotation_due_days
from intake_platform.key_rotation.transit import KekState, KeyMetadataError

__all__ = [
    "SEC_SECRET_ROTATION_DUE_DAYS",
    "KekInventory",
    "KeyOutcome",
    "KeyRotator",
    "RotationAction",
    "RotationReport",
    "run_rotation",
]

#: Catalogued in observability/metrics_catalog.yaml (inv. 13) as
#: ``sec.secret_rotation_due_days``; files/08 §4 group M.
SEC_SECRET_ROTATION_DUE_DAYS = Gauge(
    "sec_secret_rotation_due_days",
    "Days until each tenant KEK's next quarterly rotation is due (files/10 §3); "
    "negative means overdue.",
    ["key"],
)

#: What a Transit read or rotate can raise. Anything else is a defect and propagates.
_TRANSIT_ERRORS = (httpx.HTTPError, CryptoShredError, TamperError, KeyMetadataError)


class KekInventory(Protocol):
    def key_ids(self) -> list[str]: ...
    def read(self, key_id: str) -> KekState: ...


class KeyRotator(Protocol):
    """The job's only write. :class:`~intake_platform.envelope.TransitKekProvider`
    satisfies it; nothing destructive is reachable through this type."""

    def rotate(self, tenant_id: str) -> None: ...


class RotationAction(enum.StrEnum):
    CURRENT = "current"
    ROTATED = "rotated"
    FAILED = "failed"
    UNREADABLE = "unreadable"


@dataclass(frozen=True)
class KeyOutcome:
    key_id: str
    action: RotationAction
    due_days: float | None
    key_version: int | None


@dataclass(frozen=True)
class RotationReport:
    outcomes: tuple[KeyOutcome, ...]

    @property
    def ok(self) -> bool:
        """True when every key is current or was rotated in this tick."""
        return all(
            outcome.action in (RotationAction.CURRENT, RotationAction.ROTATED)
            for outcome in self.outcomes
        )

    def count(self, action: RotationAction) -> int:
        return sum(1 for outcome in self.outcomes if outcome.action is action)


def _reported(state: KekState, action: RotationAction, now: datetime) -> KeyOutcome:
    days = rotation_due_days(state.last_rotated_at, now)
    SEC_SECRET_ROTATION_DUE_DAYS.labels(key=state.key_id).set(days)
    return KeyOutcome(state.key_id, action, days, state.latest_version)


def _tick_one(
    inventory: KekInventory, rotator: KeyRotator, key_id: str, now: datetime
) -> KeyOutcome:
    try:
        state = inventory.read(key_id)
    except _TRANSIT_ERRORS:
        return KeyOutcome(key_id, RotationAction.UNREADABLE, None, None)
    if rotation_due_days(state.last_rotated_at, now) > 0:
        return _reported(state, RotationAction.CURRENT, now)
    try:
        rotator.rotate(state.tenant_id)
        after = inventory.read(key_id)
    except _TRANSIT_ERRORS:
        return _reported(state, RotationAction.FAILED, now)
    if after.latest_version <= state.latest_version:
        return _reported(state, RotationAction.FAILED, now)
    return _reported(after, RotationAction.ROTATED, now)


def run_rotation(inventory: KekInventory, rotator: KeyRotator, *, now: datetime) -> RotationReport:
    """Rotate every tenant KEK that is due at ``now``; report and emit per key.

    The key list is read first and a failure to read it propagates: a tick that
    cannot see the keys has checked nothing and must not look like a clean run.
    Series for keys that no longer exist (a crypto-shredded tenant) are dropped.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be tz-aware; a naive instant is not an instant")
    key_ids = inventory.key_ids()
    SEC_SECRET_ROTATION_DUE_DAYS.clear()
    return RotationReport(tuple(_tick_one(inventory, rotator, key, now) for key in key_ids))

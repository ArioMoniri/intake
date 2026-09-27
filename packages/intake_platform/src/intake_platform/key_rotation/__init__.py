"""INT-367 — the scheduled quarterly rotation of the tenant KEKs (files/10 §3).

files/10 §3 keeps each tenant's key-encryption key in OpenBao Transit and
rotates it quarterly; INT-014 built the rotation (Transit ``rotate`` plus
``rewrap_field``) and nothing scheduled it. This package is the job:

- :mod:`.schedule` — the cadence, three calendar months, and the countdown;
- :mod:`.transit` — each KEK's last rotation, read from Transit's own metadata;
- :mod:`.job` — one idempotent tick: rotate what is due, emit
  ``sec_secret_rotation_due_days{key}``, never destroy anything;
- :mod:`.cli` — ``python -m intake_platform.key_rotation`` (``make
  key-rotation``), the entry point the scheduler calls. What calls it, and the
  OpenBao capabilities it needs, are in docs/runbooks/key-rotation.md.
"""

from intake_platform.key_rotation.job import (
    SEC_SECRET_ROTATION_DUE_DAYS,
    KekInventory,
    KeyOutcome,
    KeyRotator,
    RotationAction,
    RotationReport,
    run_rotation,
)
from intake_platform.key_rotation.schedule import (
    ROTATION_PERIOD_MONTHS,
    next_rotation_due,
    rotation_due_days,
)
from intake_platform.key_rotation.transit import KekState, KeyMetadataError, TransitKekInventory

__all__ = [
    "ROTATION_PERIOD_MONTHS",
    "SEC_SECRET_ROTATION_DUE_DAYS",
    "KekInventory",
    "KekState",
    "KeyMetadataError",
    "KeyOutcome",
    "KeyRotator",
    "RotationAction",
    "RotationReport",
    "TransitKekInventory",
    "next_rotation_due",
    "rotation_due_days",
    "run_rotation",
]

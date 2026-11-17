"""The visit lifecycle (INT-407; files/02 §2b) — a RED visit cannot silently move.

files/02 §2b: *"As the product stands, a RED-flagged patient whose appointment
moves two weeks out is invisible to everyone — to the clinic (whose queue no
longer lists them), to the clinician (whose inbox entry was for a visit that is
not happening), and to us (who have no state to act on) … That is a safety gap
wearing a UX costume, and it is fixed by state, not by copy."*

Pure, shared by the API (which is authoritative: the device reflects the
server's record) and any runtime that needs the location axis:

- :mod:`.machine` — the seven states, the table, the guards, the check-in
  evidence and the location it yields, the staleness rule.
- :mod:`.confirm` — the T-24h confirm: queued, transactional, unsent.
- :mod:`.resurface` — the re-show of a RED when its visit moves: a pointer at
  the pre-positioned script, in the register the RED was told in.
"""

from __future__ import annotations

from typing import Final

from intake_platform.visit_lifecycle.confirm import (
    CONFIRM_LEAD,
    ConfirmDispatch,
    ConfirmRequest,
    ConfirmStatus,
    attempt_confirm_dispatch,
    queue_confirm,
)
from intake_platform.visit_lifecycle.machine import (
    ALLOWED_TRANSITIONS,
    DELTA_SESSION_OFFER_FLAG,
    NOTE_STALE_AFTER,
    RESTING_STATES,
    TERMINAL_STATES,
    CheckInEvidence,
    CheckInMethod,
    IntakeMode,
    TransitionRefused,
    VisitLifecycle,
    VisitState,
    derive_location,
    landing,
)
from intake_platform.visit_lifecycle.resurface import (
    PATIENT_FACING_REGISTERS,
    RedResurface,
    red_resurface,
)

#: The visit slot the record lives in (INT-134/INT-306 precedent: a visit fact
#: is a plain ``visit.*`` slot on its session row — no new table or column).
LIFECYCLE_SLOT: Final = "visit.lifecycle"

__all__ = [
    "ALLOWED_TRANSITIONS",
    "CONFIRM_LEAD",
    "DELTA_SESSION_OFFER_FLAG",
    "LIFECYCLE_SLOT",
    "NOTE_STALE_AFTER",
    "PATIENT_FACING_REGISTERS",
    "RESTING_STATES",
    "TERMINAL_STATES",
    "CheckInEvidence",
    "CheckInMethod",
    "ConfirmDispatch",
    "ConfirmRequest",
    "ConfirmStatus",
    "IntakeMode",
    "RedResurface",
    "TransitionRefused",
    "VisitLifecycle",
    "VisitState",
    "attempt_confirm_dispatch",
    "derive_location",
    "landing",
    "queue_confirm",
    "red_resurface",
]

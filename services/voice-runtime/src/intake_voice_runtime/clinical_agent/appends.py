"""The engine's append vocabulary for the council verifier (INT-430; ADR-036).

The verifier may *append* one of two scripted steps to an answered slot and
do nothing else; :meth:`~intake_voice_runtime.clinical_agent.fsm.IntakeEngine.
append_verification` reports what it did as an :class:`AppendOutcome`. Both
enumerations are closed and PHI-free, so they can label a metric and an event.
"""

from __future__ import annotations

import enum

__all__ = ["AppendOutcome", "VerificationKind"]


class VerificationKind(enum.StrEnum):
    """The two scripted steps the council verifier may append."""

    REASK = "reask"
    CONFIRM_BACK = "confirm_back"


class AppendOutcome(enum.StrEnum):
    """What ``append_verification`` did with one action."""

    APPENDED = "appended"
    STALE_REVISION = "stale_revision"
    NOT_ANSWERED = "not_answered"
    ALREADY_QUEUED = "already_queued"
    NO_SCRIPT = "no_script"
    EXHAUSTED = "exhausted"

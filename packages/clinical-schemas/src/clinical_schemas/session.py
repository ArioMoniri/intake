"""SessionState (INT-031).

files/13 §9.2: the state is a pure fold — ``S = fold(init(protocol_hash,
reference_time), events)`` with no wall clock; files/13 §9.3 names the seven
answer states; files/03 §4.3 serialises every write to it behind the FIFO
Work queue. Lifecycle values mirror ``intake_platform.db.models.SessionStatus``
(INT-030) so the schema and the row can never disagree.

The ``triage`` slot is typed ``RulesTriageResult | None`` on purpose: the
state that drives patient-facing routing structurally cannot hold an LLM
candidate (invariant 1).
"""

from __future__ import annotations

import enum
from typing import Literal

from pydantic import AwareDatetime, Field

from clinical_schemas.common import FrozenModel, JsonValue, Ref, Sha256
from clinical_schemas.triage import RulesTriageResult


class AnswerState(enum.StrEnum):
    """The seven answer states of files/13 §9.3. ASKED_ABSENT is the only
    state that may enter ``ros_pertinent``; CONTESTED keeps both answers."""

    NOT_ASKED = "NOT_ASKED"
    ASKED_PENDING = "ASKED_PENDING"
    ASKED_PRESENT = "ASKED_PRESENT"
    ASKED_ABSENT = "ASKED_ABSENT"
    UNCLEAR = "UNCLEAR"
    DECLINED = "DECLINED"
    CONTESTED = "CONTESTED"


class SessionStatus(enum.StrEnum):
    """Session lifecycle, mirroring INT-030 ``SessionStatus``."""

    CREATED = "created"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class SessionBudget(FrozenModel):
    """Turn budget (files/13 §9.4 budget governor; ``turns_used`` /
    ``turns_remaining`` are GuardExpr whitelist functions, files/13 §9.5)."""

    turns_used: int = Field(ge=0, description="Turns consumed so far (files/13 §9.5).")
    turns_remaining: int = Field(
        ge=0,
        description="Turns left before the governor filters classes 6-8 "
        "(files/13 §9.4-9.5); the budget yields to the safety set, never the reverse.",
    )


class SessionState(FrozenModel):
    """One intake session's engine state snapshot (files/03 §4.3; files/13 §9)."""

    session_id: Ref = Field(
        description="Session id (files/03 §4.3: one Backend context per session, "
        "intake:<session_id>:backend)."
    )
    protocol_id: str = Field(
        min_length=1,
        description="Which protocol pack ran (INT-030 sessions.protocol_id).",
    )
    protocol_version: str = Field(
        min_length=1,
        description="Exact pack version for reproducibility and re-triage sweeps "
        "(INT-030 sessions.protocol_version).",
    )
    protocol_hash: Sha256 = Field(
        description="Resolved pack hash the fold was initialised with (files/13 §9.2; "
        "files/04 §7 — pinned per session)."
    )
    mode: Literal["fast", "detailed"] = Field(
        description="Intake mode (files/04 §5 meta.mode; GuardExpr ``mode``, files/13 §9.5)."
    )
    status: SessionStatus = Field(
        description="Lifecycle state (INT-030 sessions.status: created|active|completed|cancelled)."
    )
    reference_time: AwareDatetime = Field(
        description="The session's 'now', stamped at SessionStarted — no wall clock, so "
        "replay is exact (files/13 §9.2 purity)."
    )
    step_states: dict[str, AnswerState] = Field(
        default_factory=dict,
        description="Answer state per protocol step id (files/13 §9.3 seven states).",
    )
    slots: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="Slot values keyed by slot id; every write serialised through the "
        "FIFO Work queue (files/03 §4.3; persisted per INT-030 slots with envelope "
        "encryption for sensitive classes).",
    )
    budget: SessionBudget = Field(description="Turn budget (files/13 §9.4).")
    triage: RulesTriageResult | None = Field(
        default=None,
        description="Latest rules-engine determination (files/03 §4.3 evaluate_triage). "
        "Typed to exclude LLM candidates — no LLM path into routing state "
        "(invariant 1).",
    )

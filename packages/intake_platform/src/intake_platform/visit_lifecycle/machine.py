"""The visit lifecycle state machine (INT-407; files/02 §2b).

files/02 §2b: *"The entire timing model of this product hangs off an
appointment datetime acquired by OCR from an SMS screenshot and then never
re-verified … A visit therefore needs an explicit state machine, and it needs
one for a safety reason before a UX one."*

```
planned ──T-24h confirm──► confirmed ──QR/geofence──► checked_in ──► attended
   │                           │                          │
   ├──────────► cancelled ◄────┤                          └──► attended (no check-in)
   ├──────────► rescheduled ───┘ (new datetime → back to planned)
   └──────────► missed (no check-in, datetime + grace elapsed)
```

**The table** (:data:`ALLOWED_TRANSITIONS`). The diagram draws the happy path;
the rules under it make the T-24h confirm *"the only cheap correction we get on
the OCR value"* — a correction channel, not a gate on arriving. So everything a
``confirmed`` visit may do a ``planned`` one may do too: a patient who never
answered a message (and at P1 none can be sent — INT-358) still arrives, is
still seen, still misses. ``checked_in`` leads only to ``attended``;
``attended``, ``cancelled`` and ``missed`` are terminal; ``rescheduled`` is a
transition and never a resting state — it lands back in ``planned`` with the
new datetime (:func:`landing`). Anything else is refused with
``transition_not_allowed`` and changes nothing.

**The guards**, each a refusal code and never a default:

- ``rescheduled`` carries the new schedule (``schedule_required``) and queues
  a fresh T-24h confirm for it; no other move carries a schedule.
- ``missed`` needs the visit's datetime plus a grace to have elapsed with no
  check-in. files/02 names no grace, so none is invented here: the caller
  passes one or the transition is refused (``missed_grace_unset``) — the INT-141
  quiet-hours posture, where an unset window refuses rather than guesses.
- ``checked_in`` carries its :class:`CheckInEvidence`, because §2b makes the
  check-in *"a safety input, not only a UX state"*.

**Location** (:func:`derive_location`) is files/02 §5.3 Axis 3, derived from
this state plus the session mode: ``REMOTE`` for a fast-mode session before
the visit, ``ON_SITE`` only for a detailed-mode session at a check-in whose
evidence is certain, and ``UNKNOWN`` for everything else — *"never assumed when
it cannot be known"*. *"A geofence that fires in the car park, or a QR scanned
by a relative who arrived first, must yield UNKNOWN and not ON_SITE"*: an
evidence signal that is absent or negative is doubt, and doubt is UNKNOWN.

**Staleness.** *"On rescheduled: the note is marked stale after 7 days from
the session that produced it."* :meth:`VisitLifecycle.note_stale` is that
sentence: a visit that was rescheduled, a note, and seven days from the
note's session anchor.

The record is ids, enums and instants — it is persisted as a plain slot on the
visit (INT-134/INT-306's precedent) and every transition it records is also an
audit entry named by its id.
"""

from __future__ import annotations

import enum
import re
from collections.abc import Mapping
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Final, Literal, Self

from clinical_schemas.triage import RedLocation
from clinical_schemas.visit_time import VisitSchedule
from pydantic import BaseModel, ConfigDict, Field, model_validator

from intake_platform.doctor_link import visit_instant
from intake_platform.visit_lifecycle.confirm import ConfirmRequest, ConfirmStatus, queue_confirm
from intake_platform.visit_lifecycle.resurface import RedResurface

__all__ = [
    "ALLOWED_TRANSITIONS",
    "DELTA_SESSION_OFFER_FLAG",
    "NOTE_STALE_AFTER",
    "RESTING_STATES",
    "TERMINAL_STATES",
    "CheckInEvidence",
    "CheckInMethod",
    "IntakeMode",
    "TransitionRefused",
    "VisitLifecycle",
    "VisitState",
    "derive_location",
    "landing",
]

#: files/02 §2b: "the note is marked stale after 7 days from the session".
NOTE_STALE_AFTER: Final = timedelta(days=7)

#: The delta-session offer is gated: files/02 §2b quotes an offer sentence, but
#: no reviewed ``tr`` resource for it exists, and patient copy is not written by
#: an engineer. A safety flag, so no call-site default can open it.
DELTA_SESSION_OFFER_FLAG: Final = "delta_session_offer"

type IntakeMode = Literal["fast", "detailed"]

_ID: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class VisitState(enum.StrEnum):
    PLANNED = "planned"
    CONFIRMED = "confirmed"
    CHECKED_IN = "checked_in"
    ATTENDED = "attended"
    CANCELLED = "cancelled"
    RESCHEDULED = "rescheduled"
    MISSED = "missed"


_S = VisitState
#: What a visit that has not yet arrived may do next.
_BEFORE_ARRIVAL: Final = frozenset(
    {_S.CHECKED_IN, _S.ATTENDED, _S.CANCELLED, _S.RESCHEDULED, _S.MISSED}
)

ALLOWED_TRANSITIONS: Final[Mapping[VisitState, frozenset[VisitState]]] = MappingProxyType(
    {
        _S.PLANNED: _BEFORE_ARRIVAL | {_S.CONFIRMED},
        _S.CONFIRMED: _BEFORE_ARRIVAL,
        _S.CHECKED_IN: frozenset({_S.ATTENDED}),
        _S.ATTENDED: frozenset(),
        _S.CANCELLED: frozenset(),
        _S.MISSED: frozenset(),
    }
)

#: Every state a visit can rest in — all but ``rescheduled``.
RESTING_STATES: Final = frozenset(ALLOWED_TRANSITIONS)
TERMINAL_STATES: Final = frozenset(
    state for state, targets in ALLOWED_TRANSITIONS.items() if not targets
)


def landing(to: VisitState) -> VisitState:
    """Where a transition leaves the visit: ``rescheduled`` → ``planned``."""
    return VisitState.PLANNED if to is VisitState.RESCHEDULED else to


class TransitionRefused(Exception):
    """A transition the machine will not make. ``code`` is machine-shaped and
    never echoes a submitted value (invariant 6)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class CheckInMethod(enum.StrEnum):
    QR = "qr"
    GEOFENCE = "geofence"


class CheckInEvidence(BaseModel):
    """What the device knew when it checked the visit in.

    Each method has one signal, and only an affirmative one is certainty:
    a QR is certain when the patient's own device scanned it
    (``scanned_by_patient``), a geofence when the fix is inside the building
    rather than the car park (``inside_building``). Absent is doubt — a device
    that did not say is a device that did not know.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    method: CheckInMethod
    scanned_by_patient: bool | None = None
    inside_building: bool | None = None

    @model_validator(mode="after")
    def _own_signal_only(self) -> Self:
        if self.method is CheckInMethod.QR and self.inside_building is not None:
            raise ValueError("a QR check-in carries no geofence signal")
        if self.method is CheckInMethod.GEOFENCE and self.scanned_by_patient is not None:
            raise ValueError("a geofence check-in carries no QR signal")
        return self

    @property
    def certain(self) -> bool:
        if self.method is CheckInMethod.QR:
            return self.scanned_by_patient is True
        return self.inside_building is True


def derive_location(
    state: VisitState, *, mode: IntakeMode | None, check_in: CheckInEvidence | None
) -> RedLocation:
    """files/02 §5.3 Axis 3. ``mode=None`` is "no intake session is running"
    (a patient acting in the app), where nothing says where they stand."""
    if mode == "fast" and state in (VisitState.PLANNED, VisitState.CONFIRMED):
        return RedLocation.REMOTE
    if (
        mode == "detailed"
        and state is VisitState.CHECKED_IN
        and check_in is not None
        and check_in.certain
    ):
        return RedLocation.ON_SITE
    return RedLocation.UNKNOWN


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise TransitionRefused("naive_timestamp")
    return value


class VisitLifecycle(BaseModel):
    """One visit's lifecycle: where it rests, and what the last move was.

    Immutable; :meth:`apply` returns the next record or raises
    :class:`TransitionRefused`. An absent record is a ``planned`` visit
    (:meth:`from_slot`), which is what every visit written before INT-407 is.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    schema_version: Literal[1] = 1
    state: VisitState = VisitState.PLANNED
    seq: int = Field(default=0, ge=0)
    last_transition: VisitState | None = None
    transition_id: str | None = None
    transition_at: datetime | None = None
    check_in: CheckInEvidence | None = None
    rescheduled_at: datetime | None = None
    confirm: ConfirmRequest | None = None
    red_resurface: tuple[RedResurface, ...] = ()

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.state not in RESTING_STATES:
            raise ValueError("rescheduled is a transition, never a resting state")
        if self.state is VisitState.CHECKED_IN and self.check_in is None:
            raise ValueError("a checked-in visit records how it was checked in")
        if self.check_in is not None and self.state not in (
            VisitState.CHECKED_IN,
            VisitState.ATTENDED,
        ):
            raise ValueError("only a visit that was checked in carries check-in evidence")
        for instant in (self.transition_at, self.rescheduled_at):
            if instant is not None and (instant.tzinfo is None or instant.utcoffset() is None):
                raise ValueError("lifecycle instants are timezone-aware")
        return self

    # --- construction -------------------------------------------------------------------

    @classmethod
    def initial(
        cls, schedule: VisitSchedule | None = None, *, confirm_message_id: str | None = None
    ) -> VisitLifecycle:
        """A new ``planned`` visit; with a schedule, its T-24h confirm queued."""
        if schedule is None:
            return cls()
        if confirm_message_id is None:
            raise ValueError("a dated visit queues its confirm under a message id")
        return cls(confirm=queue_confirm(schedule, message_id=confirm_message_id))

    @classmethod
    def from_slot(cls, value: Mapping[str, object] | None) -> VisitLifecycle:
        return cls() if value is None else cls.model_validate(dict(value))

    def to_slot(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude_none=True)

    # --- the machine --------------------------------------------------------------------

    def apply(
        self,
        to: VisitState,
        *,
        transition_id: str,
        at: datetime,
        schedule: VisitSchedule | None = None,
        check_in: CheckInEvidence | None = None,
        missed_grace: timedelta | None = None,
        confirm_message_id: str | None = None,
    ) -> VisitLifecycle:
        if not isinstance(transition_id, str) or not _ID.fullmatch(transition_id):
            raise TransitionRefused("transition_id_invalid")
        _aware(at)
        if to not in ALLOWED_TRANSITIONS[self.state]:
            raise TransitionRefused("transition_not_allowed")
        self._guard(to, at=at, schedule=schedule, check_in=check_in, grace=missed_grace)

        confirm = self.confirm
        if to is VisitState.RESCHEDULED:
            # _guard refused a reschedule without a schedule already
            assert schedule is not None  # noqa: S101 - narrowed by _guard above
            if confirm_message_id is None:
                raise TransitionRefused("confirm_message_id_required")
            confirm = queue_confirm(schedule, message_id=confirm_message_id)
        elif confirm is not None and confirm.status is ConfirmStatus.QUEUED:
            # every other allowed move leaves ``planned`` for good (or never
            # rested there): nothing is left to confirm
            confirm = confirm.withdrawn()
        return VisitLifecycle(
            state=landing(to),
            seq=self.seq + 1,
            last_transition=to,
            transition_id=transition_id,
            transition_at=at,
            check_in=check_in if to is VisitState.CHECKED_IN else self.check_in,
            rescheduled_at=at if to is VisitState.RESCHEDULED else self.rescheduled_at,
            confirm=confirm,
            red_resurface=self.red_resurface,
        )

    @staticmethod
    def _guard(
        to: VisitState,
        *,
        at: datetime,
        schedule: VisitSchedule | None,
        check_in: CheckInEvidence | None,
        grace: timedelta | None,
    ) -> None:
        if to is VisitState.CHECKED_IN and check_in is None:
            raise TransitionRefused("check_in_evidence_required")
        if to is not VisitState.CHECKED_IN and check_in is not None:
            raise TransitionRefused("check_in_evidence_not_allowed")
        if to is VisitState.RESCHEDULED:
            if schedule is None:
                raise TransitionRefused("schedule_required")
            return
        if to is VisitState.MISSED:
            if grace is None or grace < timedelta(0):
                raise TransitionRefused("missed_grace_unset")
            if schedule is None:
                raise TransitionRefused("missed_schedule_unknown")
            if at < visit_instant(schedule) + grace:
                raise TransitionRefused("missed_not_due")
            return
        if schedule is not None:
            raise TransitionRefused("schedule_not_allowed")

    def with_resurface(self, items: tuple[RedResurface, ...]) -> VisitLifecycle:
        """The same record, now carrying the §2b re-show of this move."""
        return VisitLifecycle.model_validate({**self.model_dump(), "red_resurface": items})

    # --- what the state means -----------------------------------------------------------

    def location(self, *, mode: IntakeMode | None) -> RedLocation:
        return derive_location(self.state, mode=mode, check_in=self.check_in)

    def note_stale_at(self, anchor: datetime | None) -> datetime | None:
        """When the note goes stale: seven days after its session, on a visit
        that was rescheduled. ``None`` when it never does."""
        if self.rescheduled_at is None or anchor is None:
            return None
        return anchor + NOTE_STALE_AFTER

    def note_stale(self, anchor: datetime | None, *, now: datetime) -> bool:
        stale_at = self.note_stale_at(anchor)
        return stale_at is not None and now >= stale_at

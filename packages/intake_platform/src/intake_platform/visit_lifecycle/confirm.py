"""The T-24h confirm (INT-407; files/02 §2b).

files/02 §2b, verbatim: *"T-24h confirm. A single transactional message —
'Salı 14:30 Kardiyoloji randevunuz duruyor mu?' — with 'Evet · Ertelendi ·
İptal ettim'. This is the only cheap correction we get on the OCR value, and it
is a permitted service communication about a booked appointment, not
marketing."*

What exists, and what deliberately does not:

- **The request is queued.** A visit in ``planned`` with a known date carries
  one :class:`ConfirmRequest`: a message id, the transactional class, the SMS
  channel and the instant it falls due — ``visit_instant − 24 h``, which for a
  date with no recorded hour is a day before the START of that date, so it is
  never later than a day before the real appointment. Leaving ``planned``
  withdraws it; a reschedule queues a fresh one for the new datetime.
- **Nothing sends it.** Two gates are shut, and :func:`attempt_confirm_dispatch`
  names both rather than pretending either is open. **No SMS vendor is
  contracted** (INT-358, awaiting-human), and INT-141's ports module is
  explicit that no fake adapter stands in for one. **No reviewed body
  exists** either: the spec's example interpolates the day, the hour and the
  department, which INT-141's catalogue forbids by construction (*"an
  appointment reminder that names the department is a disclosure to whoever is
  standing behind the patient when the lock screen lights up"*). Writing that
  copy is a clinical and legal review, not an engineering choice — so the
  catalogue has no confirm template, the dispatch seam refuses before any
  transport is touched, and :class:`ConfirmStatus` has no member a send could
  be recorded in. When both gates open, the send goes through
  :class:`~intake_platform.notifications.ReminderDispatcher` (opt-out, quiet
  hours, content-freedom) like every other transactional message.

The record carries ids, enums and an instant — never a body, a department or a
phone number (invariant 6).
"""

from __future__ import annotations

import enum
import re
from datetime import datetime, timedelta
from typing import Final, Self

from clinical_schemas.visit_time import VisitSchedule
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from intake_platform.doctor_link import visit_instant
from intake_platform.notifications.catalogue import Channel, MessageClass
from intake_platform.notifications.ports import NotificationTransport, UnconfiguredTransport

__all__ = [
    "CONFIRM_LEAD",
    "ConfirmDispatch",
    "ConfirmRequest",
    "ConfirmStatus",
    "attempt_confirm_dispatch",
    "queue_confirm",
]

#: files/02 §2b: "T-24h confirm".
CONFIRM_LEAD: Final = timedelta(hours=24)

_ID: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class ConfirmStatus(enum.StrEnum):
    """Two members, and no ``sent``: until a vendor and a reviewed body exist
    there is no send to record, so there is nowhere to record one."""

    QUEUED = "queued"
    WITHDRAWN = "withdrawn"


class ConfirmDispatch(enum.StrEnum):
    NOT_DUE = "not_due"
    WITHDRAWN = "withdrawn"
    BLOCKED_TRANSPORT_UNCONFIGURED = "blocked_transport_unconfigured"
    BLOCKED_COPY_UNREVIEWED = "blocked_copy_unreviewed"


class ConfirmRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    message_id: str
    message_class: MessageClass = MessageClass.TRANSACTIONAL
    channel: Channel = Channel.SMS
    due_at: datetime
    status: ConfirmStatus = ConfirmStatus.QUEUED

    @field_validator("message_id")
    @classmethod
    def _id_shaped(cls, value: str) -> str:
        if not _ID.fullmatch(value):
            raise ValueError("a message id is id-shaped; the value is not echoed")
        return value

    @model_validator(mode="after")
    def _transactional(self) -> Self:
        # files/06 §1 row 6563-İYS: a service message about a booked
        # appointment. A commercial confirm would need an İYS record.
        if self.message_class is not MessageClass.TRANSACTIONAL:
            raise ValueError("the visit confirm is a transactional message, never commercial")
        if self.due_at.tzinfo is None or self.due_at.utcoffset() is None:
            raise ValueError("due_at must be timezone-aware")
        return self

    def withdrawn(self) -> ConfirmRequest:
        return ConfirmRequest.model_validate(
            {**self.model_dump(), "status": ConfirmStatus.WITHDRAWN}
        )


def queue_confirm(schedule: VisitSchedule, *, message_id: str) -> ConfirmRequest:
    """The confirm for this schedule, due a day before the visit instant."""
    return ConfirmRequest(message_id=message_id, due_at=visit_instant(schedule) - CONFIRM_LEAD)


def attempt_confirm_dispatch(
    confirm: ConfirmRequest, *, transport: NotificationTransport | None, now: datetime
) -> ConfirmDispatch:
    """Why the confirm is not sent right now — the only answers there are.

    The transport is checked before the copy because it is the gate the
    world has to open first (INT-358); a transport that could deliver is still
    never handed a message, because there is no reviewed body to hand it. The
    confirm is not changed: it stays queued until one of those gates moves.
    """
    if confirm.status is ConfirmStatus.WITHDRAWN:
        return ConfirmDispatch.WITHDRAWN
    if now < confirm.due_at:
        return ConfirmDispatch.NOT_DUE
    if (
        transport is None
        or isinstance(transport, UnconfiguredTransport)
        or transport.channel is not confirm.channel
    ):
        return ConfirmDispatch.BLOCKED_TRANSPORT_UNCONFIGURED
    return ConfirmDispatch.BLOCKED_COPY_UNREVIEWED

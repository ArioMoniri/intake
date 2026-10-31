"""INT-589 — how long a note's share lives (files/02 §2b, files/06 §3).

The share was minted with ``send + 72 h``. That broke the visit it exists for:
issuing a Doctor Link needs a live share, so a note sent more than 72 h before
its appointment could not be linked at the visit. files/02 §2b names this
defect for the link itself: *"A note prepared five days early currently
expires before the clinician opens it."* review.consent.untilValue and
share.tr.md ("Bağlantı, en geç randevunuzdan yetmiş iki saat sonra
kendiliğinden kapanır") both say the window runs from the appointment.

The rule, one function so the note route and the reschedule cannot disagree:

- a dated visit: the share lives until ``visit_instant + 72 h``. That is the
  Doctor Link's own anchor (``intake_platform.doctor_link.visit_instant``):
  the appointment's hour where known, else the start of the visit date in
  Türkiye, never later than the appointment;
- never less than 72 h from the send. Every send lives at least as long as it
  did before, and a note sent after its appointment keeps the old window
  instead of being born expired;
- an undated visit: ``send + 72 h``, as before. No date is no anchor, and the
  Doctor Link refuses such a visit anyway (``visit_date_unknown``).
"""

from __future__ import annotations

import datetime as dt

from clinical_schemas.visit_time import VisitSchedule, VisitTime
from intake_platform.doctor_link import DOCTOR_LINK_TTL, visit_instant

__all__ = ["SHARE_TTL", "share_expires_at", "visit_schedule"]

#: The same 72 h the Doctor Link uses (06 §3): one window, not two.
SHARE_TTL: dt.timedelta = DOCTOR_LINK_TTL


def visit_schedule(date: str | None, time: VisitTime | None) -> VisitSchedule | None:
    """A visit record's schedule, or None where it records no date."""
    if date is None:
        return None
    return VisitSchedule(date=dt.date.fromisoformat(date), time=time)


def share_expires_at(schedule: VisitSchedule | None, sent_at: dt.datetime) -> dt.datetime:
    """When a share sent at ``sent_at`` for a visit on ``schedule`` closes."""
    if sent_at.tzinfo is None:
        raise ValueError("the send instant must be timezone-aware")
    floor = sent_at + SHARE_TTL
    if schedule is None:
        return floor
    return max(visit_instant(schedule) + SHARE_TTL, floor)

"""The KVKK m.13 clock and the files/06 §3 erasure grace (INT-037).

Both windows are read off files/, never chosen here:

- :data:`KVKK_RESPONSE_WINDOW` — files/06 §1, row KVKK-11/13: "DSAR:
  access/rectify/delete/port; respond **≤ 30 days**, free of charge (first
  copy)". The statute is 6698 s. KVKK m.13.
- :data:`SHRED_GRACE` — files/06 §3: transcript-derived structured data and
  notes are "patient-deletable (30-day grace, then crypto-shred)".

They are equal today and still separate constants, because they answer
different questions to different regulators: one is when we must have
answered, the other is when the bytes stop being recoverable. Collapsing them
into one number would make a future divergence a silent behaviour change.

The console queue over these rows is INT-189's surface; what lives here is
the clock and the query it needs.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Final

from intake_platform.db.models import DsarRequest, DsarStatus
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "KVKK_RESPONSE_WINDOW",
    "OPEN_STATUSES",
    "SHRED_GRACE",
    "due_at",
    "grace_ends_at",
    "is_overdue",
    "overdue_requests",
]

#: files/06 §1 KVKK-11/13 — respond within 30 days.
KVKK_RESPONSE_WINDOW: Final = timedelta(days=30)

#: files/06 §3 — 30-day deletion grace, then crypto-shred.
SHRED_GRACE: Final = timedelta(days=30)

#: The statuses whose clock is still running.
OPEN_STATUSES: Final = (DsarStatus.RECEIVED, DsarStatus.SCHEDULED)


def _aware(value: datetime) -> datetime:
    """SQLite returns naive UTC instants; postgres returns aware ones."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def due_at(received_at: datetime) -> datetime:
    return received_at + KVKK_RESPONSE_WINDOW


def grace_ends_at(received_at: datetime) -> datetime:
    return received_at + SHRED_GRACE


def is_overdue(request: DsarRequest, *, now: datetime) -> bool:
    """A request is overdue only while it is still open: answering late is a
    breach that ends when the answer lands, and a completed row that stayed
    'overdue' for ever would drown the queue it exists to prioritise."""
    if request.status not in OPEN_STATUSES:
        return False
    return _aware(request.due_at) < now


async def overdue_requests(
    session: AsyncSession, *, tenant_id: uuid.UUID, now: datetime
) -> list[DsarRequest]:
    """Open requests past their m.13 deadline, oldest first — the tracker the
    compliance console (INT-189) will render."""
    rows = (
        await session.scalars(
            select(DsarRequest)
            .where(
                DsarRequest.tenant_id == tenant_id,
                DsarRequest.status.in_(OPEN_STATUSES),
            )
            .order_by(DsarRequest.due_at, DsarRequest.id)
        )
    ).all()
    return [row for row in rows if is_overdue(row, now=now)]

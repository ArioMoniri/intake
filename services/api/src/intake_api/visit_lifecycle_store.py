"""ORM access for the INT-407 visit lifecycle, split from ``store`` so the
visit/note/share module does not grow further past the 500-line ceiling.

Everything here runs inside the transition's one tenant-scoped transaction:

- :func:`lock_visit` takes the visit's session row ``FOR UPDATE``, so two
  transitions on one visit are serialised by postgres and the second reads the
  first's result (the unit lane's SQLite ignores the clause and is serial
  anyway). A lost update here would be a cancelled visit silently re-planned.
- :func:`write_lifecycle` and :func:`write_schedule` rewrite the plain
  ``visit.*`` slots in place — the INT-134/INT-306 precedent: a visit fact is a
  slot on its session row, so no table and no column is added (invariant 18);
  the record of every transition is the hash-chained audit, which names each
  one by id.
- :func:`live_grants` and :func:`repin_links` are the share side of the two
  moves: what a cancel revokes, and the Doctor Link expiry a reschedule moves.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from clinical_schemas.visit_time import VisitSchedule
from intake_platform.db.models import DoctorLink, IntakeSession, Share, Slot, SlotSensitivity
from intake_platform.doctor_link import link_expires_at
from intake_platform.visit_lifecycle import LIFECYCLE_SLOT, VisitLifecycle
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from intake_api import store

__all__ = [
    "LiveGrants",
    "live_grants",
    "lock_visit",
    "repin_links",
    "write_lifecycle",
    "write_schedule",
]

_SLOT_DATE = "visit.date"
_SLOT_TIME = "visit.time"


def _aware(value: datetime) -> datetime:
    """SQLite returns naive UTC instants; postgres returns aware ones."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


async def lock_visit(
    session: AsyncSession, *, tenant_id: uuid.UUID, visit_id: uuid.UUID, patient_id: uuid.UUID
) -> store.VisitRecord | None:
    """The caller's own visit, its row locked for the rest of the transaction."""
    locked = await session.scalar(
        select(IntakeSession.id)
        .where(
            IntakeSession.tenant_id == tenant_id,
            IntakeSession.id == visit_id,
            IntakeSession.patient_id == patient_id,
            IntakeSession.protocol_id == store.VISIT_PROTOCOL_ID,
        )
        .with_for_update()
    )
    if locked is None:
        return None
    return await store.get_visit(
        session, tenant_id=tenant_id, visit_id=visit_id, patient_id=patient_id
    )


async def _slot(
    session: AsyncSession, *, tenant_id: uuid.UUID, visit_id: uuid.UUID, slot_id: str
) -> Slot | None:
    stmt = select(Slot).where(
        Slot.tenant_id == tenant_id, Slot.session_id == visit_id, Slot.slot_id == slot_id
    )
    return (await session.scalars(stmt)).first()


async def _put(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    visit_id: uuid.UUID,
    slot_id: str,
    value: dict[str, object] | None,
) -> None:
    """Write (or, with ``None``, remove) one plain ``visit.*`` slot."""
    row = await _slot(session, tenant_id=tenant_id, visit_id=visit_id, slot_id=slot_id)
    if value is None:
        if row is not None:
            await session.delete(row)
    elif row is None:
        session.add(
            Slot(
                tenant_id=tenant_id,
                session_id=visit_id,
                slot_id=slot_id,
                sensitivity=SlotSensitivity.PLAIN,
                value=value,
            )
        )
    else:
        row.value = value
    await session.flush()


async def write_lifecycle(
    session: AsyncSession, *, tenant_id: uuid.UUID, visit_id: uuid.UUID, record: VisitLifecycle
) -> None:
    await _put(
        session,
        tenant_id=tenant_id,
        visit_id=visit_id,
        slot_id=LIFECYCLE_SLOT,
        value=record.to_slot(),
    )


async def write_schedule(
    session: AsyncSession, *, tenant_id: uuid.UUID, visit_id: uuid.UUID, schedule: VisitSchedule
) -> None:
    """The reschedule's new datetime. A new schedule with no stated hour
    REMOVES the old hour rather than keeping it: an hour from the old
    appointment attached to the new date is an invented time (INT-306)."""
    await _put(
        session,
        tenant_id=tenant_id,
        visit_id=visit_id,
        slot_id=_SLOT_DATE,
        value={"date": schedule.date.isoformat()},
    )
    await _put(
        session,
        tenant_id=tenant_id,
        visit_id=visit_id,
        slot_id=_SLOT_TIME,
        value=store.time_slot_value(schedule.time) if schedule.time is not None else None,
    )


@dataclass(frozen=True)
class LiveGrants:
    """What the clinic side can reach of one note right now."""

    shares: tuple[Share, ...]
    links: tuple[DoctorLink, ...]


async def live_grants(
    session: AsyncSession, *, tenant_id: uuid.UUID, note_id: uuid.UUID
) -> LiveGrants:
    """The note's unrevoked shares, and every unrevoked link hanging off
    them — read BEFORE the revocation, so each can be audited by id."""
    shares = tuple(
        (
            await session.scalars(
                select(Share).where(
                    Share.tenant_id == tenant_id,
                    Share.note_id == note_id,
                    Share.revoked_at.is_(None),
                )
            )
        ).all()
    )
    if not shares:
        return LiveGrants(shares=(), links=())
    links = tuple(
        (
            await session.scalars(
                select(DoctorLink).where(
                    DoctorLink.tenant_id == tenant_id,
                    DoctorLink.share_id.in_([share.id for share in shares]),
                    DoctorLink.revoked_at.is_(None),
                )
            )
        ).all()
    )
    return LiveGrants(shares=shares, links=links)


async def repin_links(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    note_id: uuid.UUID,
    schedule: VisitSchedule,
    now: datetime,
) -> tuple[DoctorLink, ...]:
    """files/02 §2b: *"Doctor Link expiry is pinned to visit_datetime + 72 h,
    never issue_time + 72 h"* — so when the visit datetime moves, the expiry
    moves with it. Only links that are still live are re-pinned: a revoked
    link stays revoked, and an expired one stays expired rather than being
    revived without the patient issuing it again."""
    grants = await live_grants(session, tenant_id=tenant_id, note_id=note_id)
    expires_at = link_expires_at(schedule)
    repinned = tuple(link for link in grants.links if _aware(link.expires_at) > now)
    for link in repinned:
        link.expires_at = expires_at
    await session.flush()
    return repinned

"""ORM access for the INT-150 Doctor Link grants, split from ``store`` so the
visit/note/share module stays under the 500-line ceiling (CLAUDE.md).

Two properties live here rather than in the route:

- **the view limit is enforced in one statement.** :func:`spend_one_view`
  carries the whole decision — not revoked, not expired, budget left — in the
  UPDATE's WHERE clause, so two concurrent redemptions cannot both be admitted
  at the limit. That is deliberately unlike the OTP request gate, which is
  read-decide-write and says so (INT-263); this table does not inherit that.
- **the scope is never copied.** A link is found by ``share_id`` and the
  section list stays on ``shares.scope_sections``, so a link cannot widen a
  share and a share whose scope vocabulary grows (INT-304) needs no change
  here at all.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from intake_platform.db.models import DoctorLink, Share
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "create_doctor_link",
    "doctor_link_by_id",
    "doctor_links_for_note",
    "revoke_doctor_link",
    "spend_one_view",
]


async def create_doctor_link(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    share_id: uuid.UUID,
    token_fingerprint: str,
    recipient: dict[str, object],
    expires_at: datetime,
    view_limit: int,
) -> DoctorLink:
    link = DoctorLink(
        tenant_id=tenant_id,
        share_id=share_id,
        token_fingerprint=token_fingerprint,
        recipient=recipient,
        expires_at=expires_at,
        view_limit=view_limit,
        views_used=0,
    )
    session.add(link)
    await session.flush()
    return link


async def doctor_link_by_id(
    session: AsyncSession, *, tenant_id: uuid.UUID, link_id: uuid.UUID
) -> DoctorLink | None:
    stmt = select(DoctorLink).where(DoctorLink.tenant_id == tenant_id, DoctorLink.id == link_id)
    return (await session.scalars(stmt)).first()


async def doctor_links_for_note(
    session: AsyncSession, *, tenant_id: uuid.UUID, note_id: uuid.UUID
) -> list[DoctorLink]:
    """Every link ever issued against any share of this note — live, expired
    and revoked. The patient's own view of who can reach their note has to
    include the ones that are finished, or "nobody has access" and "access
    ended yesterday" become the same screen."""
    stmt = (
        select(DoctorLink)
        .join(Share, Share.id == DoctorLink.share_id)
        .where(DoctorLink.tenant_id == tenant_id, Share.note_id == note_id)
        .order_by(DoctorLink.created_at.desc(), DoctorLink.id)
    )
    return list((await session.scalars(stmt)).all())


async def revoke_doctor_link(
    session: AsyncSession, *, tenant_id: uuid.UUID, link_id: uuid.UUID
) -> bool:
    """Revoke one link. Returns False when it was already revoked, so the
    caller can audit a real state change exactly once."""
    revoked = await session.scalars(
        update(DoctorLink)
        .where(
            DoctorLink.tenant_id == tenant_id,
            DoctorLink.id == link_id,
            DoctorLink.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
        .returning(DoctorLink.id)
    )
    return revoked.first() is not None


async def spend_one_view(
    session: AsyncSession, *, tenant_id: uuid.UUID, link_id: uuid.UUID, now: datetime
) -> int | None:
    """Admit one opening and count it, atomically.

    One UPDATE carries the whole decision — not revoked, not expired, budget
    left — so two concurrent redemptions cannot both be admitted at the limit.
    Returns the 1-based index of the view that was admitted, or ``None`` when
    the guard refused; the caller re-reads the row to say WHY.
    """
    result = await session.execute(
        update(DoctorLink)
        .where(
            DoctorLink.tenant_id == tenant_id,
            DoctorLink.id == link_id,
            DoctorLink.revoked_at.is_(None),
            DoctorLink.expires_at > now,
            DoctorLink.views_used < DoctorLink.view_limit,
        )
        .values(views_used=DoctorLink.views_used + 1)
        .returning(DoctorLink.views_used)
        # The identity of the updated row is decided by the DATABASE, in one
        # statement; asking the ORM to re-evaluate the same criteria against
        # in-session objects would both duplicate the decision and compare a
        # naive stored instant to an aware one.
        .execution_options(synchronize_session=False)
    )
    admitted = result.scalar_one_or_none()
    return int(admitted) if admitted is not None else None

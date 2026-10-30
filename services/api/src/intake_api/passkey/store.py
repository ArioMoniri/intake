"""The patient's passkey rows (INT-582) — ``patient_passkeys``, public halves only.

Every function takes the caller's :func:`intake_api.db.tenant_session`, so RLS
scopes each statement to one tenant on postgres, and every predicate also
names the tenant and the patient explicitly, which is what carries the
isolation on the SQLite unit lane. Bytes are stored as unpadded base64url.

A passkey is ACTIVE until its recovery cool-off ends: ``recovery_requested_at``
plus the cool-off. Rows past it are purged (deleted) by the next gate or list
call, and the caller audits each purged id.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from intake_platform.db.models import PatientPasskey
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from intake_api.passkey.webauthn import RegisteredCredential, b64url

__all__ = [
    "advance_sign_count",
    "aware",
    "cancel_recovery",
    "credential_exists",
    "delete_credential",
    "insert_credential",
    "patient_credentials",
    "purge_recovered",
    "recovery_ends_at",
    "request_recovery",
]


def aware(value: datetime) -> datetime:
    """SQLite hands back naive instants; every one written here is UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def recovery_ends_at(row: PatientPasskey, cooloff: timedelta) -> datetime | None:
    if row.recovery_requested_at is None:
        return None
    return aware(row.recovery_requested_at) + cooloff


async def insert_credential(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    credential: RegisteredCredential,
    user_handle: bytes,
    created_at: datetime,
) -> PatientPasskey:
    row = PatientPasskey(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        patient_id=patient_id,
        credential_id=b64url(credential.credential_id),
        public_key=b64url(credential.public_key),
        user_handle=b64url(user_handle),
        sign_count=credential.sign_count,
        backup_eligible=credential.backup_eligible,
        backup_state=credential.backup_state,
        created_at=created_at,
    )
    session.add(row)
    await session.flush()
    return row


async def credential_exists(
    session: AsyncSession, *, tenant_id: uuid.UUID, credential_id: bytes
) -> bool:
    found = await session.scalar(
        select(PatientPasskey.id).where(
            PatientPasskey.tenant_id == tenant_id,
            PatientPasskey.credential_id == b64url(credential_id),
        )
    )
    return found is not None


async def patient_credentials(
    session: AsyncSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID
) -> list[PatientPasskey]:
    rows = await session.scalars(
        select(PatientPasskey)
        .where(PatientPasskey.tenant_id == tenant_id, PatientPasskey.patient_id == patient_id)
        .order_by(PatientPasskey.created_at, PatientPasskey.id)
    )
    return list(rows.all())


async def purge_recovered(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    now: datetime,
    cooloff: timedelta,
) -> tuple[list[PatientPasskey], list[uuid.UUID]]:
    """Delete the rows whose recovery cool-off has ended; return what is left
    (the ACTIVE passkeys) and the ids that were removed."""
    rows = await patient_credentials(session, tenant_id=tenant_id, patient_id=patient_id)
    ended = [row for row in rows if (ends := recovery_ends_at(row, cooloff)) and ends <= now]
    if ended:
        await session.execute(
            delete(PatientPasskey).where(
                PatientPasskey.tenant_id == tenant_id,
                PatientPasskey.patient_id == patient_id,
                PatientPasskey.id.in_([row.id for row in ended]),
            )
        )
    gone = {row.id for row in ended}
    return [row for row in rows if row.id not in gone], [row.id for row in ended]


async def advance_sign_count(
    session: AsyncSession,
    *,
    row: PatientPasskey,
    sign_count: int,
    backup_state: bool,
    used_at: datetime,
) -> bool:
    """Compare-and-set on the counter the assertion was verified against: of
    two step-ups racing on one counter value, exactly one moves it."""
    result = await session.execute(
        update(PatientPasskey)
        .where(
            PatientPasskey.id == row.id,
            PatientPasskey.tenant_id == row.tenant_id,
            PatientPasskey.sign_count == row.sign_count,
        )
        .values(sign_count=sign_count, backup_state=backup_state, last_used_at=used_at)
        .execution_options(synchronize_session=False)
    )
    return bool(getattr(result, "rowcount", 0) == 1)


async def delete_credential(
    session: AsyncSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID, passkey_id: uuid.UUID
) -> bool:
    result = await session.execute(
        delete(PatientPasskey).where(
            PatientPasskey.tenant_id == tenant_id,
            PatientPasskey.patient_id == patient_id,
            PatientPasskey.id == passkey_id,
        )
    )
    return bool(getattr(result, "rowcount", 0) == 1)


async def request_recovery(
    session: AsyncSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID, at: datetime
) -> Sequence[PatientPasskey]:
    """Start the cool-off on every passkey that has none running; a recovery
    already running keeps its own start (asking again does not restart it,
    and does not shorten it)."""
    rows = await patient_credentials(session, tenant_id=tenant_id, patient_id=patient_id)
    for row in rows:
        if row.recovery_requested_at is None:
            row.recovery_requested_at = at
    await session.flush()
    return rows


async def cancel_recovery(
    session: AsyncSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID
) -> list[uuid.UUID]:
    rows = await patient_credentials(session, tenant_id=tenant_id, patient_id=patient_id)
    cancelled = [row.id for row in rows if row.recovery_requested_at is not None]
    for row in rows:
        row.recovery_requested_at = None
    await session.flush()
    return cancelled

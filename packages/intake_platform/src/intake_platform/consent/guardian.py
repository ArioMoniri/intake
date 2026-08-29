"""INT-223 — the guardian↔minor linkage store, behind a closed gate.

Persisting "this account is the legal representative of that minor" creates
a **new category of personal data** we do not hold today, and CLAUDE.md
makes that a stop-and-ask: the schema, the migration and this service are
built, wired and tested, and the gate stays shut until counsel answers the
``guardian_link_basis`` and ``guardian_relationship_proof`` rows of
``intake_platform.consent.minors.POLICY_TABLE``.

The gate is the INT-023 safety flag ``guardian_link``: pre-declared False in
``SAFETY_FLAG_DEFAULTS``, so a call-site default cannot open it and only an
explicit boolean from the flag backend can. Both directions are gated, not
just the write:

- :func:`record_guardian_link` raises :class:`GuardianLinkDisabledError`
  before anything is written or audited;
- :func:`active_guardian_link` answers ``None`` — a row that somehow exists
  is unreadable while the gate is shut, so no code path can come to depend
  on linkage data before the basis exists.

The rules engine (``minors.py``) is deliberately independent of this module:
age banding and actor resolution are fully testable with the gate off, which
is what lets the mechanism land while the legal question is open.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from intake_platform.consent.service import ConsentAudit
from intake_platform.db.models import GuardianLink
from intake_platform.flags import FlagProvider

__all__ = [
    "GUARDIAN_LINK_FLAG",
    "GuardianLinkDisabledError",
    "active_guardian_link",
    "guardian_link_enabled",
    "record_guardian_link",
]

#: The INT-023 safety flag guarding every guardian-linkage read and write.
GUARDIAN_LINK_FLAG = "guardian_link"

#: Id-shaped refs only (invariant 6): the guardian is named by an account
#: ref and the relationship by an evidence ref — never by a person's name.
_REF_SHAPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,127}$")


class GuardianLinkDisabledError(RuntimeError):
    """The guardian-linkage gate is shut (its lawful basis is awaiting a
    human). Carries no subject data — the caller learns only that the
    capability is closed."""

    def __init__(self) -> None:
        super().__init__(
            "guardian linkage is disabled: the guardian_link flag is off pending the "
            "guardian_link_basis policy row (awaiting-human)"
        )


def guardian_link_enabled(flags: FlagProvider) -> bool:
    """The gate, read in one place. The call-site default is False and the
    flag is pre-declared False, so both layers must be opened deliberately."""
    return flags.get_bool(GUARDIAN_LINK_FLAG, False)


def _validated_ref(field_name: str, value: str) -> str:
    if not _REF_SHAPE.match(value):
        # names the field, never echoes the value (invariant 6)
        raise ValueError(f"{field_name} must be id-shaped (invariant 6)")
    return value


async def record_guardian_link(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    minor_patient_id: uuid.UUID,
    guardian_account_ref: str,
    relationship_ref: str,
    flags: FlagProvider,
    audit: ConsentAudit,
    actor: str,
    now: datetime | None = None,
) -> GuardianLink:
    """Record one guardian↔minor link. Refuses while the gate is shut —
    before any row is added and before anything is audited, so a closed gate
    leaves no trace of a subject it was never allowed to process."""
    if not guardian_link_enabled(flags):
        raise GuardianLinkDisabledError()
    row = GuardianLink(
        tenant_id=tenant_id,
        minor_patient_id=minor_patient_id,
        guardian_account_ref=_validated_ref("guardian_account_ref", guardian_account_ref),
        relationship_ref=_validated_ref("relationship_ref", relationship_ref),
        created_at=now if now is not None else datetime.now(UTC),
    )
    session.add(row)
    await session.flush()
    await audit.record(
        actor=actor,
        action="guardian.link",
        resource_ref=f"guardian_link:{row.id}",
        consent_scope="scope:core",
    )
    return row


async def active_guardian_link(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    minor_patient_id: uuid.UUID,
    flags: FlagProvider,
) -> GuardianLink | None:
    """The live link for a minor, or ``None`` — including whenever the gate
    is shut, so no caller can grow a dependency on linkage data early."""
    if not guardian_link_enabled(flags):
        return None
    stmt = select(GuardianLink).where(
        GuardianLink.tenant_id == tenant_id,
        GuardianLink.minor_patient_id == minor_patient_id,
        GuardianLink.revoked_at.is_(None),
    )
    return (await session.scalars(stmt)).first()

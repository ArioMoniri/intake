"""INT-038 — versioned consent objects over the INT-030 model (invariant 4).

Semantics, stated once and pinned by tests/legal/:

- **grant** writes the full files/06 §2 record — {scope, version, text_hash,
  ts, channel, evidence} — with version and hash taken from the docs/legal
  catalog at the moment of grant. No text → no grant (fail closed,
  invariant 18). One call grants exactly one scope (unbundling).
- **state** answers the guard. A live grant whose hash matches the CURRENT
  canonical text is ``granted``; a live grant whose hash no longer matches —
  including the dev-tier seed rows, whose hash is NULL — is ``stale`` and
  treated as absent (re-prompt on change). A live grant for a purpose whose
  canonical text does not exist YET is ``unbound`` and honoured: nothing
  changed since it was recorded, and the fail-closed edge is the grant path
  (nothing new can be granted without a text). The instant INT-210 lands a
  text, every unbound grant goes stale — adding the text IS the version
  bump, and the system re-prompts.
- **withdraw** revokes the scope's live rows, then cascades in the SAME
  evaluation pass: dependent purposes (registry ``cascade_children``; core
  reaches everything) and live shares (core and share-family withdrawals
  drop live Doctor-Link rows — files/06 §2.3). Withdrawal of a default-on
  purpose with no rows materialises an opt-out row, because an opt-out that
  leaves no record is an opt-out nobody can prove.
- **sweep** is crash recovery for the window between the revocation mark
  and its cascade: it re-derives incomplete cascades and completes them,
  sparing anything granted after the withdrawal instant. Its schedule
  contract (sweep.py) bounds the end-to-end withdrawal cascade at ≤ 1 min.

Every change is audited (invariant 4): the audit recorder is a required
argument, so a caller cannot even express an unaudited consent change.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from intake_platform.consent.registry import (
    CHANNELS,
    CORE,
    dependents_of,
    resolve_scope,
)
from intake_platform.consent.texts import ConsentTextCatalog
from intake_platform.db.models import Consent, Note, Share

__all__ = [
    "OPT_OUT_VERSION",
    "ConsentAudit",
    "ConsentDecision",
    "Reason",
    "WithdrawalReport",
    "consent_state",
    "grant_consent",
    "is_scope_allowed",
    "sweep_withdrawals",
    "withdraw_consent",
]

# Id-shaped refs only (the audit chain's own rule, invariant 6): narrative —
# anything with spaces or non-ASCII — has no carrier here either.
_REF_SHAPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,127}$")

# The version marker on a materialised opt-out of a default-on purpose:
# no açık rıza text governs a non-consent lawful basis, so there is no
# consent-text version to record — but the opt-out itself must leave a row.
OPT_OUT_VERSION = "opt-out"

Reason = Literal["granted", "default_on", "unbound", "absent", "withdrawn", "stale"]


class ConsentAudit(Protocol):
    """The api AuditWriter's shape (INT-016 chain behind it)."""

    async def record(
        self, *, actor: str, action: str, resource_ref: str, consent_scope: str
    ) -> None: ...


@dataclass(frozen=True)
class ConsentDecision:
    scope: str
    purpose: str
    allowed: bool
    reason: Reason


@dataclass(frozen=True)
class WithdrawalReport:
    scope: str
    withdrawn_scopes: tuple[str, ...]
    revoked_share_ids: tuple[uuid.UUID, ...]


def _now(now: datetime | None) -> datetime:
    return now if now is not None else datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    """SQLite returns naive UTC instants; postgres returns aware ones."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


async def _rows_for_scope(
    session: AsyncSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID, scope: str
) -> list[Consent]:
    stmt = select(Consent).where(
        Consent.tenant_id == tenant_id,
        Consent.patient_id == patient_id,
        Consent.scope == scope,
    )
    return list((await session.scalars(stmt)).all())


async def consent_state(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    scope: str,
    catalog: ConsentTextCatalog,
) -> ConsentDecision:
    """The guard's single question: does this scope stand for this patient,
    against the CURRENT docs/legal text?"""
    purpose = resolve_scope(scope)
    rows = await _rows_for_scope(session, tenant_id=tenant_id, patient_id=patient_id, scope=scope)
    live = [row for row in rows if row.revoked_at is None]

    def decision(allowed: bool, reason: Reason) -> ConsentDecision:
        return ConsentDecision(scope=scope, purpose=purpose.id, allowed=allowed, reason=reason)

    if live:
        text = catalog.try_entry(scope)
        if text is None:
            return decision(True, "unbound")
        if any(row.text_hash == text.text_hash for row in live):
            return decision(True, "granted")
        return decision(False, "stale")
    if rows:
        return decision(False, "withdrawn")
    if purpose.default_granted:
        return decision(True, "default_on")
    return decision(False, "absent")


async def is_scope_allowed(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    scope: str,
    catalog: ConsentTextCatalog,
) -> bool:
    state = await consent_state(
        session, tenant_id=tenant_id, patient_id=patient_id, scope=scope, catalog=catalog
    )
    return state.allowed


def _validated_channel(channel: str) -> str:
    if channel not in CHANNELS:
        raise ValueError(f"channel must be one of {CHANNELS} (files/06 §1 KVKK-10)")
    return channel


def _validated_ref(field_name: str, value: str) -> str:
    if not _REF_SHAPE.match(value):
        # names the field, never echoes the value (invariant 6)
        raise ValueError(f"{field_name} must be id-shaped (invariant 6)")
    return value


async def grant_consent(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    scope: str,
    channel: str,
    evidence_ref: str,
    catalog: ConsentTextCatalog,
    audit: ConsentAudit,
    actor: str,
    now: datetime | None = None,
) -> Consent:
    """Record one grant, hash-bound to the text that was shown. Raises
    ConsentTextMissingError when docs/legal holds no text for the purpose —
    the fail-closed edge of invariant 18."""
    resolve_scope(scope)
    text = catalog.entry(scope)  # fail closed before anything is written
    row = Consent(
        tenant_id=tenant_id,
        patient_id=patient_id,
        scope=scope,
        version=text.version,
        text_hash=text.text_hash,
        granted_at=_now(now),
        channel=_validated_channel(channel),
        evidence_ref=_validated_ref("evidence_ref", evidence_ref),
    )
    session.add(row)
    await session.flush()
    await audit.record(
        actor=actor,
        action="consent.grant",
        resource_ref=f"consent:{row.id}",
        consent_scope=f"scope:{scope}",
    )
    return row


async def _revoke_rows(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    scope: str,
    instant: datetime,
    granted_no_later_than: datetime | None = None,
) -> list[Consent]:
    rows = await _rows_for_scope(session, tenant_id=tenant_id, patient_id=patient_id, scope=scope)
    revoked: list[Consent] = []
    for row in rows:
        if row.revoked_at is not None:
            continue
        if granted_no_later_than is not None and _aware(row.granted_at) > granted_no_later_than:
            continue  # granted after the withdrawal — a NEW consent, spared
        row.revoked_at = instant
        revoked.append(row)
    return revoked


async def _live_patient_scopes(
    session: AsyncSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID
) -> list[Consent]:
    stmt = select(Consent).where(
        Consent.tenant_id == tenant_id,
        Consent.patient_id == patient_id,
        Consent.revoked_at.is_(None),
    )
    return list((await session.scalars(stmt)).all())


async def _revoke_live_shares(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    instant: datetime,
    created_no_later_than: datetime | None = None,
) -> list[Share]:
    stmt = (
        select(Share)
        .join(Note, Share.note_id == Note.id)
        .where(
            Share.tenant_id == tenant_id,
            Note.patient_id == patient_id,
            Share.revoked_at.is_(None),
        )
    )
    revoked: list[Share] = []
    for share in (await session.scalars(stmt)).all():
        if created_no_later_than is not None and _aware(share.created_at) > created_no_later_than:
            continue
        share.revoked_at = instant
        revoked.append(share)
    return revoked


def _cascade_scope_ids(purpose_id: str) -> tuple[str, ...]:
    return dependents_of(purpose_id)


def _shares_fall_with(purpose_id: str) -> bool:
    # files/06 §2.3: withdrawal revokes delivered Doctor Links; a share
    # rides on the share-family consent, which rides on core.
    return purpose_id in (CORE, "share")


async def _cascade(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    purpose_id: str,
    withdrawn_at: datetime,
    revoke_at: datetime,
    audit: ConsentAudit,
    actor: str,
    spare_later_grants: bool,
) -> tuple[list[Consent], list[Share]]:
    cutoff = withdrawn_at if spare_later_grants else None
    dependents: list[Consent] = []
    if purpose_id == CORE:
        for row in await _live_patient_scopes(session, tenant_id=tenant_id, patient_id=patient_id):
            if cutoff is not None and _aware(row.granted_at) > cutoff:
                continue
            row.revoked_at = revoke_at
            dependents.append(row)
    else:
        for child in _cascade_scope_ids(purpose_id):
            dependents.extend(
                await _revoke_rows(
                    session,
                    tenant_id=tenant_id,
                    patient_id=patient_id,
                    scope=child,
                    instant=revoke_at,
                    granted_no_later_than=cutoff,
                )
            )
    shares: list[Share] = []
    if _shares_fall_with(purpose_id):
        shares = await _revoke_live_shares(
            session,
            tenant_id=tenant_id,
            patient_id=patient_id,
            instant=revoke_at,
            created_no_later_than=cutoff,
        )
    for row in dependents:
        await audit.record(
            actor=actor,
            action="consent.cascade",
            resource_ref=f"consent:{row.id}",
            consent_scope=f"scope:{row.scope}",
        )
    for share in shares:
        await audit.record(
            actor=actor,
            action="consent.cascade",
            resource_ref=f"share:{share.id}",
            consent_scope=f"scope:{purpose_id}",
        )
    return dependents, shares


async def withdraw_consent(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    scope: str,
    audit: ConsentAudit,
    actor: str,
    now: datetime | None = None,
) -> WithdrawalReport:
    """Withdraw one scope and cascade in the same evaluation pass. As easy
    as granting (files/06 §2): no text, no channel, no preconditions."""
    purpose = resolve_scope(scope)
    instant = _now(now)
    revoked = await _revoke_rows(
        session, tenant_id=tenant_id, patient_id=patient_id, scope=scope, instant=instant
    )
    if not revoked and purpose.default_granted:
        rows = await _rows_for_scope(
            session, tenant_id=tenant_id, patient_id=patient_id, scope=scope
        )
        if all(row.revoked_at is not None for row in rows):
            opt_out = Consent(
                tenant_id=tenant_id,
                patient_id=patient_id,
                scope=scope,
                version=OPT_OUT_VERSION,
                granted_at=instant,
                revoked_at=instant,
            )
            session.add(opt_out)
            await session.flush()
            revoked = [opt_out]
    for row in revoked:
        await audit.record(
            actor=actor,
            action="consent.withdraw",
            resource_ref=f"consent:{row.id}",
            consent_scope=f"scope:{scope}",
        )
    dependents, shares = await _cascade(
        session,
        tenant_id=tenant_id,
        patient_id=patient_id,
        purpose_id=purpose.id,
        withdrawn_at=instant,
        revoke_at=instant,
        audit=audit,
        actor=actor,
        spare_later_grants=False,
    )
    withdrawn = {scope, *(row.scope for row in dependents)} if (revoked or dependents) else set()
    return WithdrawalReport(
        scope=scope,
        withdrawn_scopes=tuple(sorted(withdrawn)),
        revoked_share_ids=tuple(share.id for share in shares),
    )


async def sweep_withdrawals(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    audit: ConsentAudit,
    actor: str,
    now: datetime,
) -> int:
    """Complete any cascade a crash interrupted: for every (patient, scope)
    whose rows are ALL revoked, re-apply the cascade against the latest
    withdrawal instant, sparing grants and shares that post-date it. Returns
    the number of repairs (0 on a quiet pass)."""
    stmt = select(Consent).where(Consent.tenant_id == tenant_id)
    rows = list((await session.scalars(stmt)).all())
    by_key: dict[tuple[uuid.UUID, str], list[Consent]] = {}
    for row in rows:
        by_key.setdefault((row.patient_id, row.scope), []).append(row)

    repaired = 0
    for (patient_id, scope), scope_rows in sorted(by_key.items(), key=lambda kv: str(kv[0])):
        if any(row.revoked_at is None for row in scope_rows):
            continue  # scope live (or re-granted) — nothing withdrawn to finish
        withdrawn_at = max(_aware(row.revoked_at) for row in scope_rows if row.revoked_at)
        dependents, shares = await _cascade(
            session,
            tenant_id=tenant_id,
            patient_id=patient_id,
            purpose_id=resolve_scope(scope).id,
            withdrawn_at=withdrawn_at,
            revoke_at=now,
            audit=audit,
            actor=actor,
            spare_later_grants=True,
        )
        repaired += len(dependents) + len(shares)
    return repaired

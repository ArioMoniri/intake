"""Where the Compliance module gets its facts (INT-189; files/08 §4).

The module renders four sourced feeds and an evidence bundle, and — like the
INT-183 models source — it keeps no second copy of any of them:

- the **vendor-transfer register** folds the egress ``TransferRecord`` feed
  against the sourced allow-list (``intake_platform.compliance.register``);
- **consent coverage** and the **DSAR queue** are counted straight off the
  INT-038 ``consents`` rows and the INT-037 ``dsar_requests`` rows, tenant
  scoped through :func:`intake_api.db.tenant_session`;
- the **audit search** narrows the hash chain to administrative rows, ids only
  (``intake_platform.compliance.audit_search``);
- the **evidence bundle** assembles the above through the invariant-47 export
  guard (``intake_platform.compliance.evidence``).

**Fail-closed sourcing.** The transfer feed defaults empty — a durable egress
log lives in Loki and querying it is a follow-up (a blocked external
dependency, not a value to invent), so an unwired deployment shows an empty
register rather than a fabricated one. The audit-chain status defaults to
"not verified" when no verifier result is present: an unknown chain is not a
green one.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from datetime import datetime
from os import environ
from pathlib import Path
from typing import Any

from intake_platform.compliance import (
    AuditChainStatus,
    AuditSearchQuery,
    ConsentCoverageRow,
    DsarSlaRow,
    EvidenceBundle,
    VendorRegisterRow,
    build_evidence_bundle,
    build_register,
    search_audit,
)
from intake_platform.compliance.audit_search import AuditSearchRow
from intake_platform.db.models import Consent, DsarRequest, DsarStatus
from intake_platform.egress import TransferRecord, load_allowlist
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from intake_api.audit import AuditWriter
from intake_api.db import tenant_session
from intake_api.dsar.sla import OPEN_STATUSES, is_overdue
from intake_api.state import ApiState

__all__ = [
    "ALLOWLIST_PATH_ENV",
    "AUDIT_STATUS_ENV",
    "audit_chain_status",
    "audit_search",
    "build_evidence",
    "consent_coverage",
    "dsar_queue",
    "dsar_sla_summary",
    "load_vendor_register",
]

#: Overrides the allow-list path (tests point it at a copy). Unset in prod,
#: where the repo file is the source both enforcement points already read.
ALLOWLIST_PATH_ENV = "INTAKE_EGRESS_ALLOWLIST_PATH"

#: Names the daily verifier's result file. Unset ⇒ status "not verified"
#: (fail closed): an unobserved chain is not a healthy one.
AUDIT_STATUS_ENV = "INTAKE_AUDIT_CHAIN_STATUS_PATH"


def _allowlist_path() -> Path:
    raw = environ.get(ALLOWLIST_PATH_ENV)
    if raw:
        return Path(raw)
    # services/api/src/intake_api/admin/compliance_source.py → repo root
    return Path(__file__).resolve().parents[5] / "infra" / "security" / "egress-allowlist.yaml"


def load_vendor_register(
    feed: Sequence[TransferRecord], *, now: datetime
) -> tuple[VendorRegisterRow, ...]:
    """The KVKK transfer register, auto-filled from the egress feed."""
    return build_register(feed, allowlist=load_allowlist(_allowlist_path()), now=now)


async def consent_coverage(
    session: AsyncSession, *, tenant_id: uuid.UUID
) -> tuple[ConsentCoverageRow, ...]:
    """Consent coverage by (scope, version): granted vs withdrawn counts only.

    ``case(...)`` rather than ``FILTER`` so the unit (SQLite) and live
    (postgres) lanes agree byte-for-byte.
    """
    granted = func.sum(case((Consent.revoked_at.is_(None), 1), else_=0))
    withdrawn = func.sum(case((Consent.revoked_at.is_not(None), 1), else_=0))
    result = await session.execute(
        select(Consent.scope, Consent.version, granted, withdrawn)
        .where(Consent.tenant_id == tenant_id)
        .group_by(Consent.scope, Consent.version)
        .order_by(Consent.scope, Consent.version)
    )
    return tuple(
        ConsentCoverageRow(scope=scope, version=version, granted=int(g or 0), withdrawn=int(w or 0))
        for scope, version, g, w in result.all()
    )


def _iso(value: datetime) -> str:
    return value.isoformat()


async def dsar_queue(
    session: AsyncSession, *, tenant_id: uuid.UUID, now: datetime
) -> list[dict[str, Any]]:
    """Open DSAR requests, oldest m.13 due-date first — ids and clocks only.

    The same rows :func:`intake_api.dsar.sla.overdue_requests` prioritises, but
    the whole open set with an ``overdue`` flag per row, so the console shows
    the queue rather than only its breaches.
    """
    rows = (
        await session.scalars(
            select(DsarRequest)
            .where(DsarRequest.tenant_id == tenant_id, DsarRequest.status.in_(OPEN_STATUSES))
            .order_by(DsarRequest.due_at, DsarRequest.id)
        )
    ).all()
    return [
        {
            "request_id": str(row.id),
            "kind": row.kind.value,
            "status": row.status.value,
            "received_at": _iso(row.received_at),
            "due_at": _iso(row.due_at),
            "grace_ends_at": _iso(row.grace_ends_at) if row.grace_ends_at is not None else None,
            "overdue": is_overdue(row, now=now),
        }
        for row in rows
    ]


async def dsar_sla_summary(
    session: AsyncSession, *, tenant_id: uuid.UUID
) -> tuple[DsarSlaRow, ...]:
    """DSAR queue depth by status with the oldest due-date, for the bundle."""
    result = await session.execute(
        select(DsarRequest.status, func.count(), func.min(DsarRequest.due_at))
        .where(DsarRequest.tenant_id == tenant_id)
        .group_by(DsarRequest.status)
        .order_by(DsarRequest.status)
    )
    rows: list[DsarSlaRow] = []
    for status, count, oldest in result.all():
        status_value = status.value if isinstance(status, DsarStatus) else str(status)
        rows.append(
            DsarSlaRow(
                status=status_value,
                count=int(count),
                oldest_due=_iso(oldest) if oldest is not None else None,
            )
        )
    return tuple(rows)


def audit_chain_status() -> AuditChainStatus:
    """The daily verifier's verdict, read fail-closed (see AUDIT_STATUS_ENV)."""
    raw = environ.get(AUDIT_STATUS_ENV)
    if not raw:
        return AuditChainStatus(verified=False, checked_at=None)
    path = Path(raw)
    if not path.is_file():
        return AuditChainStatus(verified=False, checked_at=None)
    data = json.loads(path.read_text(encoding="utf-8"))
    return AuditChainStatus(
        verified=bool(data.get("verified", False)),
        checked_at=data.get("checked_at"),
    )


async def audit_search(
    audit: AuditWriter, *, query: AuditSearchQuery
) -> tuple[AuditSearchRow, ...]:
    """Ids-only search over administrative audit rows (never patient content)."""
    entries = await audit.entries()
    return search_audit(entries, query=query)


async def build_evidence(
    state: ApiState,
    *,
    tenant_id: uuid.UUID | None,
    feed: Sequence[TransferRecord],
    now: datetime,
) -> EvidenceBundle:
    """The auditor's evidence bundle: register + consent + DSAR + chain status.

    The register and the audit-chain status are platform-wide; consent and
    DSAR are tenant-scoped, so with no resolved tenant those sections are empty
    (fail-safe, never another tenant's rows — see the route's ``_tenant_scope``).
    """
    register = load_vendor_register(feed, now=now)
    coverage: tuple[ConsentCoverageRow, ...] = ()
    sla: tuple[DsarSlaRow, ...] = ()
    if tenant_id is not None:
        async with tenant_session(state.engine, tenant_id) as session:
            coverage = await consent_coverage(session, tenant_id=tenant_id)
            sla = await dsar_sla_summary(session, tenant_id=tenant_id)
    return build_evidence_bundle(
        generated_at=now.isoformat(),
        register=register,
        consent_coverage=coverage,
        dsar_sla=sla,
        audit_chain=audit_chain_status(),
    )

"""INT-488 — the reviewer tenant is emptied between reviews (D39, legal review).

The reviewer patient is synthetic, but each App Review reviewer is a real
person, and what they type or upload is theirs (KVKK m.4/2, m.7). So nothing a
reviewer enters outlives their review: every window has its own reviewer
patient (``review_window.review_patient``), and closing the window, and
opening the next one, erase every reviewer subject left in the reviewer
tenant through the platform's own erasure, ``intake_api.dsar.shred``. That is
the path a patient's deletion takes, so what it destroys is exactly what an
export would show: the envelope-bearing fields are crypto-shredded, the rows
removed, the object bytes removed, each step audited by id. The patient row
and its consent evidence stay, as they do for any erased subject.

A reviewer subject has no grace period: the review is over, and nobody is
there to withdraw the request. The request is filed and its grace ended in one
step, then the executor runs. A run the executor refuses (a missing grant)
raises :class:`ReviewResetBlocked`, and the owner's ``on`` does not open a
window over a tenant that still holds a reviewer's data.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Final

from intake_platform.db.models import DsarKind, DsarRequest, DsarStatus, Patient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from intake_api.audit import AuditWriter
from intake_api.db import tenant_session
from intake_api.documents import DocumentsConfig
from intake_api.dsar.grants import PrivilegeProbe, missing_privileges
from intake_api.dsar.shred import execute_due_shreds
from intake_api.dsar.sla import OPEN_STATUSES
from intake_api.dsar.store import create_request
from intake_api.review_window import REVIEW_TENANT_ID

__all__ = [
    "REVIEW_EXPIRY_SWEEP_S",
    "ReviewResetBlocked",
    "reset_review_tenant",
    "review_expiry_forever",
    "review_reset_for",
]

logger = logging.getLogger("intake_api.review_signin")

#: How often the API looks for a review window whose time ran out. Every
#: reviewer step looks too; the sweep is for a window nobody touches.
REVIEW_EXPIRY_SWEEP_S: Final = 60.0


class ReviewResetBlocked(Exception):
    """The erasure refused to run; the message names the grants, never data."""


async def _unerased(engine: AsyncEngine) -> tuple[list[uuid.UUID], list[uuid.UUID]]:
    """Every reviewer subject not yet erased, and those of them with no
    erasure filed yet (a run the executor refused leaves its request open)."""
    async with tenant_session(engine, REVIEW_TENANT_ID) as session:
        patients = (
            await session.scalars(select(Patient.id).where(Patient.tenant_id == REVIEW_TENANT_ID))
        ).all()
        requests = (
            await session.execute(
                select(DsarRequest.patient_id, DsarRequest.status).where(
                    DsarRequest.tenant_id == REVIEW_TENANT_ID,
                    DsarRequest.kind == DsarKind.DELETE,
                )
            )
        ).all()
    erased = {patient_id for patient_id, status in requests if status == DsarStatus.COMPLETED}
    filed = {patient_id for patient_id, status in requests if status in OPEN_STATUSES}
    pending = [patient_id for patient_id in patients if patient_id not in erased]
    return pending, [patient_id for patient_id in pending if patient_id not in filed]


async def reset_review_tenant(
    engine: AsyncEngine,
    *,
    audit: AuditWriter,
    remove_object: Callable[[str], None],
    now: datetime,
    privileges: PrivilegeProbe = missing_privileges,
) -> int:
    """Erase every reviewer subject not yet erased; returns how many. Runs
    over the reviewer tenant only: every statement carries its id."""
    pending, unfiled = await _unerased(engine)
    if not pending:
        return 0
    async with tenant_session(engine, REVIEW_TENANT_ID) as session:
        for patient_id in unfiled:
            row = await create_request(
                session,
                tenant_id=REVIEW_TENANT_ID,
                patient_id=patient_id,
                kind=DsarKind.DELETE,
                status=DsarStatus.SCHEDULED,
                received_at=now,
                with_grace=True,
            )
            # no grace for a review that is over: the executor takes it now
            row.grace_ends_at = now
    for patient_id in unfiled:
        await audit.record(
            actor="operator:host",
            action="auth.review.reset",
            resource_ref=f"patient:{patient_id}",
            consent_scope="scope:auth",
        )
    report = await execute_due_shreds(
        engine,
        tenant_id=REVIEW_TENANT_ID,
        audit=audit,
        remove_object=remove_object,
        now=now,
        privileges=privileges,
    )
    if report.blocked is not None:
        missing = ", ".join(need.target for need in report.blocked.missing)
        raise ReviewResetBlocked(f"the reviewer erasure is refused: missing {missing}")
    return report.shredded_requests


def _no_object_store(object_ref: str) -> None:
    """A deployment with no object store wired cannot remove a document's
    bytes, so an erasure that needs to fails rather than leaving them."""
    del object_ref
    raise RuntimeError("no object store is wired; the reviewer's documents were not removed")


def review_reset_for(
    engine: AsyncEngine, documents: DocumentsConfig | None, audit: AuditWriter
) -> Callable[[], Awaitable[int]]:
    """The reviewer tenant's erasure as the API runs it when a window expires:
    the given engine (the deployment's owner role, the one that provisions the
    tenant), the document store's destroyer, the API's own chain."""
    from intake_platform.retention.executors import DocumentObjectDestroyer

    remove: Callable[[str], None] = (
        DocumentObjectDestroyer(
            documents.client,
            bucket_docs=documents.bucket_docs,
            bucket_audit=documents.bucket_audit,
        )
        if documents is not None
        else _no_object_store
    )

    async def reset() -> int:
        return await reset_review_tenant(
            engine, audit=audit, remove_object=remove, now=datetime.now(UTC)
        )

    return reset


async def review_expiry_forever(
    expire: Callable[[], Awaitable[bool]], interval_s: float = REVIEW_EXPIRY_SWEEP_S
) -> None:
    """The API's sweep: every ``interval_s``, close a review window whose time
    ran out. A failed pass is logged by type and the next one tries again."""
    while True:
        await asyncio.sleep(interval_s)
        try:
            await expire()
        except Exception as exc:  # noqa: BLE001 — the sweep outlives one failed pass
            logger.warning("review window expiry sweep failed (%s)", type(exc).__name__)

"""INT-488 — the reviewer tenant is emptied between reviews (D39, legal review).

The reviewer patient is synthetic, but each App Review reviewer is a real
person, and what they type or upload is theirs (KVKK m.4/2, m.7). So nothing a
reviewer enters outlives their review: every window has its own reviewer
patient (``review_window.review_patient``), and closing a window (``--off``,
the miss cap, the 14-day expiry) and opening the next erase every reviewer
subject left in the reviewer tenant through the platform's own erasure,
``intake_api.dsar.shred``. That is the path a patient's deletion takes, so what
it destroys is exactly what an export would show. The patient row and its
consent evidence stay, as they do for any erased subject.

**Which database role erases is INT-394's open decision (#650)**, and this
module does not answer it. It runs on the app role (``app_rw``) unless the
deployment names the decided role in ``INTAKE_API_ERASURE_DB_URL`` (the seam:
``ApiSettings.erasure_db_url``). Every run first asks INT-395's preflight
(``dsar.grants.missing_privileges``) whether that role holds every privilege the
erasure exercises. If it does not, the run touches nothing, appends one
``auth.review.reset_blocked`` row per missing privilege and raises
:class:`ReviewResetBlocked` naming the grants and INT-394. The owner's ``--on``
then refuses (fail closed): no reviewer data is collected before it can be
erased.

A reviewer subject has no grace period: the review is over, and nobody is
there to withdraw the request. The request is filed and its grace ended in one
step, then the executor runs.

The erasure never runs on a reviewer's request: only the owner's command and
the API's own sweep run it (:func:`review_expiry_forever`). The sweep retries
while a reviewer subject is unerased and no window is open, and a failed
attempt pages (``review_reset_failures_total``, ``ReviewResetFailing``), with
one ``auth.review.reset_failed`` row per failing episode.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Final

from intake_platform.db.models import DsarKind, DsarRequest, DsarStatus, Patient
from prometheus_client import Counter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from intake_api.audit import AuditWriter
from intake_api.db import tenant_session
from intake_api.documents import DocumentsConfig
from intake_api.dsar.grants import ERASURE_ROLE_DECISION, PrivilegeProbe, missing_privileges
from intake_api.dsar.shred import execute_due_shreds
from intake_api.dsar.sla import OPEN_STATUSES
from intake_api.dsar.store import create_request
from intake_api.review_window import REVIEW_TENANT_ID

__all__ = [
    "REVIEW_EXPIRY_SWEEP_S",
    "REVIEW_RESET_FAILURES_TOTAL",
    "ReviewReset",
    "ReviewResetBlocked",
    "reset_review_tenant",
    "review_expiry_forever",
    "review_reset_for",
    "unerased_review_subjects",
]

logger = logging.getLogger("intake_api.review_signin")

#: How often the API's sweep runs: expire a window whose time ran out, record a
#: close whose row was lost, retry an erasure still pending.
REVIEW_EXPIRY_SWEEP_S: Final = 60.0

#: Every unattended erasure attempt that failed; ReviewResetFailing pages on
#: any increase, so a pending erasure pages for as long as it stays pending.
REVIEW_RESET_FAILURES_TOTAL: Final = Counter(
    "review_reset_failures_total",
    "Unattended erasures of the App Review reviewer tenant that failed.",
)

#: The erasure as callers run it: the actor its rows name, then how many subjects.
ReviewReset = Callable[[str], Awaitable[int]]


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


async def unerased_review_subjects(engine: AsyncEngine) -> int:
    """How many reviewer subjects are not yet erased."""
    pending, _ = await _unerased(engine)
    return len(pending)


async def reset_review_tenant(
    engine: AsyncEngine,
    *,
    audit: AuditWriter,
    remove_object: Callable[[str], None],
    now: datetime,
    privileges: PrivilegeProbe = missing_privileges,
    actor: str = "operator:host",
) -> int:
    """Erase every reviewer subject not yet erased; returns how many. INT-395's
    preflight runs first, every time, so a role that cannot erase refuses even
    an empty tenant. Runs over the reviewer tenant only."""
    async with tenant_session(engine, REVIEW_TENANT_ID) as session:
        missing = await privileges(session)
    if missing:
        for need in missing:
            await audit.record(
                actor=actor,
                action="auth.review.reset_blocked",
                resource_ref=need.ref,
                consent_scope="scope:auth",
            )
        names = ", ".join(need.target for need in missing)
        raise ReviewResetBlocked(
            f"the reviewer erasure is refused: its role lacks {names} "
            f"(the erasure role is {ERASURE_ROLE_DECISION}'s open decision)"
        )
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
            actor=actor,
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
        names = ", ".join(need.target for need in report.blocked.missing)
        raise ReviewResetBlocked(
            f"the reviewer erasure is refused: its role lacks {names} "
            f"(the erasure role is {ERASURE_ROLE_DECISION}'s open decision)"
        )
    return report.shredded_requests


def _no_object_store(object_ref: str) -> None:
    """A deployment with no object store wired cannot remove a document's
    bytes, so an erasure that needs to fails rather than leaving them."""
    del object_ref
    raise RuntimeError("no object store is wired; the reviewer's documents were not removed")


def review_reset_for(
    engine: AsyncEngine,
    documents: DocumentsConfig | None,
    audit: AuditWriter,
    privileges: PrivilegeProbe = missing_privileges,
) -> ReviewReset:
    """The reviewer tenant's erasure as the API's sweep runs it: on ``engine``
    (the app role, or the role INT-394 decides), the document store's
    destroyer, the API's own chain, rows under the caller's actor."""
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

    async def reset(actor: str) -> int:
        return await reset_review_tenant(
            engine,
            audit=audit,
            remove_object=remove,
            now=datetime.now(UTC),
            privileges=privileges,
            actor=actor,
        )

    return reset


async def review_expiry_forever(
    sweep: Callable[[], Awaitable[object]], interval_s: float = REVIEW_EXPIRY_SWEEP_S
) -> None:
    """The API's sweep, every ``interval_s``. A failed pass is logged by type
    and the next one tries again."""
    while True:
        await asyncio.sleep(interval_s)
        try:
            await sweep()
        except Exception as exc:  # noqa: BLE001 — the sweep outlives one failed pass
            logger.warning("review sweep failed (%s)", type(exc).__name__)

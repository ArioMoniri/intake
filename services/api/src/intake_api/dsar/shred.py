"""Erasure execution: crypto-shred, then remove the rows (INT-037).

files/06 §3: transcript-derived structured data and notes are "patient-
deletable (30-day grace, then crypto-shred)". So erasure is two phases and
this module is the second one — the first (cancel the live shares, start the
grace) happens when the request is filed, because a share left live for
thirty more days would be exactly the orphan the patient asked us to cut.

Order inside a run, and the reason for it:

1. **Object bytes first, OUTSIDE the row transaction.** This is the INT-036
   executor's choice and its reasoning transfers exactly: if a run dies
   between the two steps, rows point at objects that are already gone — the
   failure direction that favours erasure, which is the right bias for a KVKK
   m.7/m.11 destruction. Doing it *inside* the transaction would invert that,
   because one failed ``remove_object`` would roll back the shred and the row
   deletes while the objects it had already removed stayed removed, leaving
   readable rows pointing at absent bytes.
2. **Then, in one transaction, crypto-shred and delete.** Every
   envelope-bearing field belonging to the subject has its wrapped DEK
   destroyed (``intake_platform.envelope``) before the rows go, so even a
   transaction that never commits leaves nothing readable behind. Rows are
   deleted in dependency order.
3. **Telemetry is de-linked, not deleted.** ``events.session_id`` is a FK to
   ``sessions.id`` with no ON DELETE clause, so the sessions cannot be dropped
   while events reference them. Telemetry has its own files/06 §3 clock
   (30 d hot / 1 y cold) and is PHI-free by construction, so the row survives
   under that clock with the link to the erased session cut.

Every statement carries an explicit ``tenant_id`` predicate even though
postgres enforces the same boundary with RLS — most of all the DELETEs, which
are the destructive half and which the SQLite unit lane does not police
(the ``intake_api.dsar.store`` convention).

Granularity, stated plainly because it is the design's one real limit:
``EnvelopeCipher``'s KEK is per TENANT, so destroying a KEK would erase every
patient in the tenant. Per-subject erasure therefore destroys the per-field
wrapped DEKs, which is a true crypto-shred of those fields — the DEK is the
key; the KEK only wraps it. What it does not reach is a wrapped DEK already
captured in a backup taken before the run, exactly as a tenant-KEK shred does
not reach a backed-up KEK. Closing that gap means a per-subject key in the
hierarchy, which is a key-management design change and therefore a human
decision (CLAUDE.md "when to stop and ask"); the ask is written up in
docs/evidence/INT-037.md rather than decided here.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from intake_platform.db.envelope_json import encrypted_field_from_json, encrypted_field_to_json
from intake_platform.db.models import (
    Document,
    DsarKind,
    DsarRectification,
    DsarRequest,
    DsarStatus,
    Event,
    IntakeSession,
    Note,
    OverlayFact,
    PatientOverlayHeader,
    Share,
    Slot,
    SlotSensitivity,
)
from intake_platform.envelope import shred_field
from intake_platform.records.index_store import erase_record_index
from prometheus_client import Counter
from sqlalchemy import Delete, delete, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from intake_api.audit import AuditWriter
from intake_api.db import tenant_session
from intake_api.dsar.audit import DSAR_BASIS_REF
from intake_api.dsar.sla import OPEN_STATUSES
from intake_api.dsar.store import subject_record

__all__ = ["ShredReport", "execute_due_shreds"]

#: files/08 §4 group O: "`admin.dsar_delete_total` with subject count > 1"
#: pages — a single-subject erasure is routine, a multi-subject one is an
#: incident. The label carries the count so the alert can tell them apart.
DSAR_DELETE_TOTAL = Counter(
    "admin_dsar_delete_total",
    "DSAR erasures executed, labelled by the number of subjects in the run.",
    ["subject_count"],
)


@dataclass(frozen=True)
class ShredReport:
    shredded_requests: int
    shredded_fields: int
    removed_rows: int


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _shredded(payload: dict[str, object]) -> dict[str, object]:
    return dict(encrypted_field_to_json(shred_field(encrypted_field_from_json(payload))))


async def _delete(session: AsyncSession, statement: Delete) -> int:
    result = cast("CursorResult[Any]", await session.execute(statement))
    return int(result.rowcount or 0)


async def execute_due_shreds(
    engine: AsyncEngine,
    *,
    tenant_id: uuid.UUID,
    audit: AuditWriter,
    remove_object: Callable[[str], None],
    now: datetime,
) -> ShredReport:
    """Execute every erasure whose files/06 §3 grace has elapsed.

    Idempotent by construction: a request leaves ``OPEN_STATUSES`` as soon as
    it runs, so a re-run finds nothing to do rather than shredding twice.
    """
    # Step 1: the object bytes, in their own read, before any write
    # transaction opens — see the module docstring for the failure direction.
    async with tenant_session(engine, tenant_id) as session:
        due_ids = [
            row.patient_id
            for row in (
                await session.scalars(
                    select(DsarRequest).where(
                        DsarRequest.tenant_id == tenant_id,
                        DsarRequest.kind == DsarKind.DELETE,
                        DsarRequest.status.in_(OPEN_STATUSES),
                    )
                )
            ).all()
            if (ends := _aware(row.grace_ends_at)) is not None and ends <= now
        ]
        object_refs = (
            list(
                (
                    await session.scalars(
                        select(Document.object_ref).where(
                            Document.tenant_id == tenant_id,
                            Document.patient_id.in_(due_ids),
                        )
                    )
                ).all()
            )
            if due_ids
            else []
        )
    for object_ref in object_refs:
        remove_object(object_ref)

    # Step 2: shred and delete, in one transaction.
    async with tenant_session(engine, tenant_id) as session:
        due = [
            row
            for row in (
                await session.scalars(
                    select(DsarRequest)
                    .where(
                        DsarRequest.tenant_id == tenant_id,
                        DsarRequest.kind == DsarKind.DELETE,
                        DsarRequest.status.in_(OPEN_STATUSES),
                    )
                    .order_by(DsarRequest.received_at, DsarRequest.id)
                )
            ).all()
            if (ends := _aware(row.grace_ends_at)) is not None and ends <= now
        ]
        if not due:
            return ShredReport(0, 0, 0)

        shredded_fields = 0
        removed_rows = 0
        answered: list[tuple[uuid.UUID, uuid.UUID]] = []
        for request in due:
            fields, rows = await _erase_subject(
                session, tenant_id=tenant_id, patient_id=request.patient_id
            )
            shredded_fields += fields
            removed_rows += rows
            request.status = DsarStatus.COMPLETED
            request.completed_at = now
            answered.append((request.id, request.patient_id))

    DSAR_DELETE_TOTAL.labels(
        subject_count=str(len({patient_id for _, patient_id in answered}))
    ).inc()
    for request_id, patient_id in answered:
        await audit.record(
            actor=f"patient:{patient_id}",
            action="dsar.delete.shred",
            resource_ref=f"dsar-request:{request_id}",
            consent_scope=DSAR_BASIS_REF,
        )
    return ShredReport(len(answered), shredded_fields, removed_rows)


async def _erase_subject(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
) -> tuple[int, int]:
    record = await subject_record(session, tenant_id=tenant_id, patient_id=patient_id)

    shredded = 0
    for note in record.notes:
        note.payload = _shredded(dict(note.payload))
        flag_modified(note, "payload")
        shredded += 1
    for entry in record.rectifications:
        entry.payload = _shredded(dict(entry.payload))
        flag_modified(entry, "payload")
        shredded += 1
    for slot in record.slots:
        if slot.sensitivity is not SlotSensitivity.SENSITIVE:
            continue  # a plain slot has no key to destroy; the row delete is the erasure
        slot.value = _shredded(dict(slot.value))
        flag_modified(slot, "value")
        shredded += 1
    # INT-170: the Loop 1 learning store is part of the subject's record —
    # files/09 §3 makes the overlay "patient-owned, exported/deletable", and an
    # erasure that left a learned fact standing would leave behind exactly the
    # health data the patient asked us to destroy. Queried here rather than
    # added to SubjectRecord because the export's FHIR mapping has no resource
    # for a learned fact yet (INT-037 owns that shape); erasure needs no shape.
    overlay_facts = tuple(
        (
            await session.scalars(
                select(OverlayFact).where(
                    OverlayFact.tenant_id == tenant_id, OverlayFact.patient_id == patient_id
                )
            )
        ).all()
    )
    for fact in overlay_facts:
        fact.payload = _shredded(dict(fact.payload))
        flag_modified(fact, "payload")
        shredded += 1
    await session.flush()

    session_ids = [row.id for row in record.sessions]
    note_ids = [row.id for row in record.notes]
    removed = 0
    if note_ids:
        removed += await _delete(
            session,
            delete(Share).where(Share.tenant_id == tenant_id, Share.note_id.in_(note_ids)),
        )
    removed += await _delete(
        session,
        delete(Document).where(Document.tenant_id == tenant_id, Document.patient_id == patient_id),
    )
    removed += await _delete(
        session,
        delete(DsarRectification).where(
            DsarRectification.tenant_id == tenant_id,
            DsarRectification.patient_id == patient_id,
        ),
    )
    removed += await _delete(
        session, delete(Note).where(Note.tenant_id == tenant_id, Note.patient_id == patient_id)
    )
    removed += await _delete(
        session,
        delete(OverlayFact).where(
            OverlayFact.tenant_id == tenant_id, OverlayFact.patient_id == patient_id
        ),
    )
    removed += await _delete(
        session,
        delete(PatientOverlayHeader).where(
            PatientOverlayHeader.tenant_id == tenant_id,
            PatientOverlayHeader.patient_id == patient_id,
        ),
    )
    # INT-123: the record index is derived from the subject's confirmed record,
    # so it goes with it. A vector is not an envelope — there is no DEK to
    # destroy — and the row delete is the erasure, as for a plain slot. The
    # helper sets the patient GUC first: the index's RESTRICTIVE policy would
    # otherwise make this DELETE a silent no-op under a non-owner role.
    removed += await erase_record_index(session, tenant_id=tenant_id, patient_id=patient_id)
    if session_ids:
        removed += await _delete(
            session,
            delete(Slot).where(Slot.tenant_id == tenant_id, Slot.session_id.in_(session_ids)),
        )
        # Telemetry is de-linked, never swept: events.session_id is a FK with
        # no ON DELETE clause (so the sessions cannot go while it points at
        # them), and a live pointer from a surviving row to an erased session
        # is a re-identification path the erasure exists to close. The row
        # itself keeps its own files/06 §3 clock and is PHI-free by
        # construction.
        await session.execute(
            update(Event)
            .where(Event.tenant_id == tenant_id, Event.session_id.in_(session_ids))
            .values(session_id=None)
        )
        removed += await _delete(
            session,
            delete(IntakeSession).where(
                IntakeSession.tenant_id == tenant_id, IntakeSession.id.in_(session_ids)
            ),
        )
    return shredded, removed

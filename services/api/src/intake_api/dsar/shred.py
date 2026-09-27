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
   deleted in dependency order, children first: previsit outputs, Doctor
   Links, shares, documents, rectifications, notes, learned facts and their
   header, the notification preference, the record index (INT-123), slots —
   then the telemetry de-link below, then the sessions.
3. **Telemetry is de-linked, not deleted.** ``events.session_id`` is a FK to
   ``sessions.id`` with no ON DELETE clause, so the sessions cannot be dropped
   while events reference them. Telemetry has its own files/06 §3 clock
   (30 d hot / 1 y cold) and is PHI-free by construction, so the row survives
   under that clock with the link to the erased session cut.
4. **The previsit output goes first, and by name (INT-392).** It is the
   note's frozen projection on the same files/06 §3 record clock
   (``RET_PREVISIT_OUTPUT``), so it is shredded with the note. It is removed
   before anything else because it is the one row a hospital may already have
   fetched: taking it first closes the read-back before the rest of the record
   goes. ``previsit_outputs.session_id`` deliberately keeps NO ACTION rather
   than a cascade — a cascade would drop the row without the shred and
   without the entry below, and NO ACTION makes a path that forgets it fail
   instead. Each removal is audited against ``previsit_output:<id>``, the
   same ref the hospital read-back audits a disclosure under, so the chain
   shows both what left and when it was erased (files/06 §2.3: a copy a
   hospital already holds is the hospital's as controller).
5. **Doctor Links go before their shares, and by name (INT-393).** A Doctor
   Link (INT-150) is one addressed, expiring way of reaching a share, and its
   row is annotated ``RET_SHARE``: "grant row retained with the record", so
   it follows the record and goes with it. Its recipient label is an
   envelope, so its wrapped DEK is destroyed with the note's. The filing
   already revoked every link (``revoke_live_shares``); this step removes
   them. ``doctor_links.share_id`` keeps NO ACTION for the reason point 4
   gives, and each removed link and each removed share is audited against
   ``doctor_link:<id>`` / ``share:<id>``, the refs their issue and opens
   were audited under. tests/data/test_session_delete_contract.py declares
   what an erasure does to every key reachable from ``patients`` and
   ``sessions``, and checks this executor against it.
6. **The notification preference goes with the subject (INT-395).**
   ``RET_NOTIFICATION_PREFERENCE`` puts the row on the record clock
   ("patient-deletable, 30-day grace, then crypto-shred"), and until INT-395
   no path erased it. It holds a flag and two clock times — no envelope, so
   nothing to shred — and the row delete is the erasure, audited against
   ``notification_preference:<id>``. The annotation gives the reason it may
   go: a delivery preference cannot outlive the account it configures.
   Every row this step and the ones above remove is read from
   :func:`intake_api.dsar.store.subject_record`, the sweep the export reads,
   so the erasure destroys exactly what the export showed.
7. **The grants are checked before anything is touched (INT-395).** Which
   database role runs erasure is INT-394's open decision, and ``app_rw``
   lacks three privileges this run exercises (:mod:`intake_api.dsar.grants`).
   So the run first asks postgres for every privilege in
   ``ERASURE_PRIVILEGES``. If the role lacks any, it returns
   ``ShredReport.blocked`` naming each one, audits ``dsar.delete.blocked``
   against every due request with one ``dsar.delete.blocked.missing_grant``
   per privilege, and leaves every request open for the next run. The
   alternative is worse in the direction point 1 cannot fix: a run that died
   on the first ``permission denied`` would already have removed the object
   bytes of a subject whose rows then stayed.

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
    DoctorLink,
    Document,
    DsarKind,
    DsarRectification,
    DsarRequest,
    DsarStatus,
    Event,
    IntakeSession,
    Note,
    NotificationPreference,
    OverlayFact,
    PatientOverlayHeader,
    PreVisitOutputRow,
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
from intake_api.dsar.grants import Privilege, PrivilegeProbe, missing_privileges
from intake_api.dsar.sla import OPEN_STATUSES
from intake_api.dsar.store import subject_record

__all__ = ["ErasureBlocked", "ShredReport", "execute_due_shreds"]

#: files/08 §4 group O: "`admin.dsar_delete_total` with subject count > 1"
#: pages — a single-subject erasure is routine, a multi-subject one is an
#: incident. The label carries the count so the alert can tell them apart.
DSAR_DELETE_TOTAL = Counter(
    "admin_dsar_delete_total",
    "DSAR erasures executed, labelled by the number of subjects in the run.",
    ["subject_count"],
)


@dataclass(frozen=True)
class ErasureBlocked:
    """A run refused before it touched anything (module docstring, point 7):
    the requests that were due, and every privilege the role lacks, each of
    which names the decision that owns it (``Privilege.describe``)."""

    request_ids: tuple[uuid.UUID, ...]
    missing: tuple[Privilege, ...]


@dataclass(frozen=True)
class ShredReport:
    shredded_requests: int
    shredded_fields: int
    removed_rows: int
    #: Set exactly when the run was refused for a missing grant; the three
    #: counts are then zero, because nothing was touched.
    blocked: ErasureBlocked | None = None


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _shredded(payload: dict[str, object]) -> dict[str, object]:
    return dict(encrypted_field_to_json(shred_field(encrypted_field_from_json(payload))))


async def _delete(session: AsyncSession, statement: Delete) -> int:
    result = cast("CursorResult[Any]", await session.execute(statement))
    return int(result.rowcount or 0)


async def _due_requests(
    session: AsyncSession, *, tenant_id: uuid.UUID, now: datetime
) -> list[DsarRequest]:
    """The erasures whose files/06 §3 grace has elapsed, oldest first."""
    return [
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


async def execute_due_shreds(
    engine: AsyncEngine,
    *,
    tenant_id: uuid.UUID,
    audit: AuditWriter,
    remove_object: Callable[[str], None],
    now: datetime,
    privileges: PrivilegeProbe = missing_privileges,
) -> ShredReport:
    """Execute every erasure whose files/06 §3 grace has elapsed.

    Idempotent by construction: a request leaves ``OPEN_STATUSES`` as soon as
    it runs, so a re-run finds nothing to do rather than shredding twice. A
    refused run leaves every request open, so the next run tries again.
    """
    # Step 1: the grants, then the object bytes, in their own read, before
    # any write transaction opens — see the module docstring, points 1 and 7.
    async with tenant_session(engine, tenant_id) as session:
        due = [
            (row.id, row.patient_id)
            for row in await _due_requests(session, tenant_id=tenant_id, now=now)
        ]
        if not due:
            return ShredReport(0, 0, 0)
        missing = await privileges(session)
        object_refs = (
            []
            if missing
            else list(
                (
                    await session.scalars(
                        select(Document.object_ref).where(
                            Document.tenant_id == tenant_id,
                            Document.patient_id.in_([patient_id for _, patient_id in due]),
                        )
                    )
                ).all()
            )
        )
    if missing:
        return await _refuse(audit, due=due, missing=missing)
    for object_ref in object_refs:
        remove_object(object_ref)

    # Step 2: shred and delete, in one transaction.
    async with tenant_session(engine, tenant_id) as session:
        requests = await _due_requests(session, tenant_id=tenant_id, now=now)
        if not requests:
            return ShredReport(0, 0, 0)

        shredded_fields = 0
        removed_rows = 0
        answered: list[tuple[uuid.UUID, uuid.UUID, tuple[tuple[str, str], ...]]] = []
        for request in requests:
            erased = await _erase_subject(
                session, tenant_id=tenant_id, patient_id=request.patient_id
            )
            shredded_fields += erased.shredded
            removed_rows += erased.removed
            request.status = DsarStatus.COMPLETED
            request.completed_at = now
            answered.append((request.id, request.patient_id, erased.audited))

    DSAR_DELETE_TOTAL.labels(
        subject_count=str(len({patient_id for _, patient_id, _ in answered}))
    ).inc()
    for request_id, patient_id, audited in answered:
        await audit.record(
            actor=f"patient:{patient_id}",
            action="dsar.delete.shred",
            resource_ref=f"dsar-request:{request_id}",
            consent_scope=DSAR_BASIS_REF,
        )
        for action, resource_ref in audited:
            await audit.record(
                actor=f"patient:{patient_id}",
                action=action,
                resource_ref=resource_ref,
                consent_scope=DSAR_BASIS_REF,
            )
    return ShredReport(len(answered), shredded_fields, removed_rows)


async def _refuse(
    audit: AuditWriter,
    *,
    due: list[tuple[uuid.UUID, uuid.UUID]],
    missing: tuple[Privilege, ...],
) -> ShredReport:
    """Point 7: audit the refusal against each due request, naming every
    missing grant, and touch nothing else."""
    for request_id, patient_id in due:
        await audit.record(
            actor=f"patient:{patient_id}",
            action="dsar.delete.blocked",
            resource_ref=f"dsar-request:{request_id}",
            consent_scope=DSAR_BASIS_REF,
        )
        for need in missing:
            await audit.record(
                actor=f"patient:{patient_id}",
                action="dsar.delete.blocked.missing_grant",
                resource_ref=need.ref,
                consent_scope=DSAR_BASIS_REF,
            )
    return ShredReport(
        0,
        0,
        0,
        blocked=ErasureBlocked(
            request_ids=tuple(request_id for request_id, _ in due), missing=missing
        ),
    )


@dataclass(frozen=True)
class _Erased:
    """One subject's erasure: fields shredded, rows removed, and the rows the
    audit names by id after the commit, as ``(action, resource_ref)`` in the
    order they were removed."""

    shredded: int
    removed: int
    audited: tuple[tuple[str, str], ...]


async def _erase_subject(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
) -> _Erased:
    # One sweep, the same one the export reads (``dsar.store``): what the
    # erasure destroys is exactly what the export showed, row for row.
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
    # INT-170: the Loop 1 learning store — files/09 §3 makes the overlay
    # "patient-owned, exported/deletable", and a learned fact left standing
    # would be exactly the health data the patient asked us to destroy.
    for fact in record.overlay_facts:
        fact.payload = _shredded(dict(fact.payload))
        flag_modified(fact, "payload")
        shredded += 1
    # INT-392: the frozen previsit output, the note's projection on the same
    # record clock, so its DEK goes with the note's.
    for output in record.previsit_outputs:
        output.payload = _shredded(dict(output.payload))
        flag_modified(output, "payload")
        shredded += 1
    # INT-393: the Doctor Links issued over the subject's shares (INT-150).
    # The recipient label is the envelope.
    for link in record.doctor_links:
        link.recipient = _shredded(dict(link.recipient))
        flag_modified(link, "recipient")
        shredded += 1
    await session.flush()

    session_ids = [row.id for row in record.sessions]
    share_ids = [row.id for row in record.shares]
    link_ids = [link.id for link in record.doctor_links]
    preference_ids = [row.id for row in record.notification_preferences]
    removed = 0
    # First: the one row a hospital may already have fetched (module docstring,
    # point 4). Its key to sessions is NO ACTION, so skipping this raises.
    removed += await _delete(
        session,
        delete(PreVisitOutputRow).where(
            PreVisitOutputRow.tenant_id == tenant_id,
            PreVisitOutputRow.patient_id == patient_id,
        ),
    )
    # Children first (module docstring, point 5), each by the id it is
    # audited under: a link or share that appeared after the sweep is not in
    # these lists, so its NO ACTION key stops the parent's delete and the
    # whole run rolls back rather than removing a row nobody audited.
    if link_ids:
        removed += await _delete(
            session,
            delete(DoctorLink).where(
                DoctorLink.tenant_id == tenant_id, DoctorLink.id.in_(link_ids)
            ),
        )
    if share_ids:
        removed += await _delete(
            session,
            delete(Share).where(Share.tenant_id == tenant_id, Share.id.in_(share_ids)),
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
    # Point 6: the notification preference, by the id it is audited under.
    if preference_ids:
        removed += await _delete(
            session,
            delete(NotificationPreference).where(
                NotificationPreference.tenant_id == tenant_id,
                NotificationPreference.id.in_(preference_ids),
            ),
        )
    # INT-123: the record index is derived from the subject's confirmed record,
    # so it goes with it. A vector is not an envelope — there is no DEK to
    # destroy — and the row delete is the erasure, as for a plain slot. The
    # helper sets the patient GUC first: the index's RESTRICTIVE policy would
    # otherwise make this DELETE a silent no-op under a non-owner role. The
    # sweep above listed the same namespace's rows (``record.record_index``).
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
    audited = (
        *(
            ("dsar.delete.previsit_output", f"previsit_output:{row.id}")
            for row in record.previsit_outputs
        ),
        *(("dsar.delete.doctor_link", f"doctor_link:{link_id}") for link_id in link_ids),
        *(("dsar.delete.share", f"share:{share_id}") for share_id in share_ids),
        *(
            ("dsar.delete.notification_preference", f"notification_preference:{row_id}")
            for row_id in preference_ids
        ),
    )
    return _Erased(shredded, removed, audited)

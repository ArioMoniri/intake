"""ORM access over the INT-030 models (INT-197). No new tables, no new
columns (invariant 18): a visit is one ``sessions`` row plus three plain
``visit.*`` slots; the note is one envelope-bearing ``notes`` row per visit
(updated in place — the audit chain, not row history, is the record of
access); sending is a ``shares`` row carrying only the scoped-on section ids.

Every query carries an explicit ``tenant_id`` predicate even though the
postgres tier enforces the same boundary with RLS — the unit lane (SQLite)
exercises the predicates, the integration lane proves the policies.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from intake_platform.db.models import (
    Document,
    IntakeSession,
    Note,
    Patient,
    SessionStatus,
    Share,
    Slot,
    SlotSensitivity,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

__all__ = [
    "SHARE_TTL",
    "VISIT_PROTOCOL_ID",
    "VISIT_PROTOCOL_VERSION",
    "VisitRecord",
    "create_document_row",
    "create_share",
    "create_visit",
    "get_document_row",
    "get_note_row",
    "get_patient_pseudonym",
    "get_visit",
    "list_document_rows",
    "list_visits",
    "live_share",
    "revoke_live_shares",
    "update_document_row",
    "upsert_note",
]

# The dev-tier visit container: an honest label for "manually created
# pre-visit session". Since INT-134 the row also carries the booked taxonomy
# branch and visit type as slots; live pack resolution over compiled packs
# stays with the runtime (INT-042 resolve_branch). Not a protocol pack id
# and never resolved as one.
VISIT_PROTOCOL_ID = "previsit.dev.visit"
VISIT_PROTOCOL_VERSION = "int197-dev"

_SLOT_HOSPITAL = "visit.hospital"
_SLOT_DEPARTMENT = "visit.department"
_SLOT_DATE = "visit.date"
# INT-134: written only when known — all in the already-inventoried ``slots``
# table (INT-030), so no new tables, no new columns (invariant 18); a
# pre-INT-134 row simply lacks them and reads back as None.
_SLOT_BRANCH = "visit.branch"
_SLOT_VISIT_TYPE = "visit.visit_type"

# 06 §3: share tokens expire, 72 h default ceiling.
SHARE_TTL = timedelta(hours=72)

NoteStatus = Literal["draft", "sent"]


@dataclass(frozen=True)
class VisitRecord:
    id: uuid.UUID
    patient_id: uuid.UUID
    hospital: str
    department: str
    branch_id: str | None
    visit_type: str | None
    date: str | None
    note_status: NoteStatus | None


def _aware(value: datetime) -> datetime:
    """SQLite returns naive UTC instants; postgres returns aware ones."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _is_live(share: Share, now: datetime) -> bool:
    return share.revoked_at is None and _aware(share.expires_at) > now


# Consent checks moved to intake_platform.consent (INT-038): the guard and
# the record-level route checks share ONE evaluator, so a text-staleness
# refusal cannot fork between paths. A raw existence query here would be a
# staleness-blind second opinion — deliberately removed.

# --- visits ----------------------------------------------------------------------------


async def create_visit(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    hospital: str,
    department: str,
    date: str | None,
    branch_id: str | None = None,
    visit_type: str | None = None,
) -> uuid.UUID:
    visit = IntakeSession(
        tenant_id=tenant_id,
        patient_id=patient_id,
        protocol_id=VISIT_PROTOCOL_ID,
        protocol_version=VISIT_PROTOCOL_VERSION,
        status=SessionStatus.CREATED,
    )
    session.add(visit)
    await session.flush()
    values: list[tuple[str, dict[str, object]]] = [
        (_SLOT_HOSPITAL, {"text": hospital}),
        (_SLOT_DEPARTMENT, {"text": department}),
    ]
    # optional facts are absent slots, never invented values (INT-134)
    if date is not None:
        values.append((_SLOT_DATE, {"date": date}))
    if branch_id is not None:
        values.append((_SLOT_BRANCH, {"text": branch_id}))
    if visit_type is not None:
        values.append((_SLOT_VISIT_TYPE, {"text": visit_type}))
    for slot_id, value in values:
        session.add(
            Slot(
                tenant_id=tenant_id,
                session_id=visit.id,
                slot_id=slot_id,
                sensitivity=SlotSensitivity.PLAIN,
                value=value,
            )
        )
    return visit.id


async def _visit_records(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID | None,
    visit_id: uuid.UUID | None,
) -> list[VisitRecord]:
    stmt = (
        select(IntakeSession)
        .where(
            IntakeSession.tenant_id == tenant_id,
            IntakeSession.protocol_id == VISIT_PROTOCOL_ID,
        )
        .order_by(IntakeSession.created_at.desc(), IntakeSession.id)
    )
    if patient_id is not None:
        stmt = stmt.where(IntakeSession.patient_id == patient_id)
    if visit_id is not None:
        stmt = stmt.where(IntakeSession.id == visit_id)
    visits = (await session.scalars(stmt)).all()
    if not visits:
        return []

    ids = [v.id for v in visits]
    slot_rows = (
        await session.scalars(
            select(Slot).where(Slot.tenant_id == tenant_id, Slot.session_id.in_(ids))
        )
    ).all()
    slots: dict[uuid.UUID, dict[str, dict[str, object]]] = {}
    for slot in slot_rows:
        slots.setdefault(slot.session_id, {})[slot.slot_id] = dict(slot.value)

    statuses = await _note_statuses(session, tenant_id=tenant_id, session_ids=ids)

    records: list[VisitRecord] = []
    for visit in visits:
        visit_slots = slots.get(visit.id, {})
        # a previsit.dev.visit row always carries hospital+department; a row
        # that does not is corrupt and must fail loudly, not render half a
        # visit. date/branch/visit_type are honestly optional (INT-134).
        hospital = str(visit_slots[_SLOT_HOSPITAL]["text"])
        department = str(visit_slots[_SLOT_DEPARTMENT]["text"])
        date_slot = visit_slots.get(_SLOT_DATE)
        branch_slot = visit_slots.get(_SLOT_BRANCH)
        type_slot = visit_slots.get(_SLOT_VISIT_TYPE)
        records.append(
            VisitRecord(
                id=visit.id,
                patient_id=visit.patient_id,
                hospital=hospital,
                department=department,
                branch_id=str(branch_slot["text"]) if branch_slot is not None else None,
                visit_type=str(type_slot["text"]) if type_slot is not None else None,
                date=str(date_slot["date"]) if date_slot is not None else None,
                note_status=statuses.get(visit.id),
            )
        )
    return records


async def _note_statuses(
    session: AsyncSession, *, tenant_id: uuid.UUID, session_ids: list[uuid.UUID]
) -> dict[uuid.UUID, NoteStatus]:
    note_rows = (
        await session.scalars(
            select(Note).where(Note.tenant_id == tenant_id, Note.session_id.in_(session_ids))
        )
    ).all()
    if not note_rows:
        return {}
    share_rows = (
        await session.scalars(
            select(Share).where(
                Share.tenant_id == tenant_id,
                Share.note_id.in_([n.id for n in note_rows]),
                Share.revoked_at.is_(None),
            )
        )
    ).all()
    now = datetime.now(UTC)
    sent_notes = {s.note_id for s in share_rows if _is_live(s, now)}
    return {n.session_id: "sent" if n.id in sent_notes else "draft" for n in note_rows}


async def list_visits(
    session: AsyncSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID | None
) -> list[VisitRecord]:
    return await _visit_records(session, tenant_id=tenant_id, patient_id=patient_id, visit_id=None)


async def get_visit(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    visit_id: uuid.UUID,
    patient_id: uuid.UUID | None = None,
) -> VisitRecord | None:
    records = await _visit_records(
        session, tenant_id=tenant_id, patient_id=patient_id, visit_id=visit_id
    )
    return records[0] if records else None


# --- notes ------------------------------------------------------------------------------


async def get_note_row(
    session: AsyncSession, *, tenant_id: uuid.UUID, visit_id: uuid.UUID
) -> Note | None:
    stmt = select(Note).where(Note.tenant_id == tenant_id, Note.session_id == visit_id)
    return (await session.scalars(stmt)).first()


async def upsert_note(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    visit_id: uuid.UUID,
    patient_id: uuid.UUID,
    payload: dict[str, object],
) -> Note:
    row = await get_note_row(session, tenant_id=tenant_id, visit_id=visit_id)
    if row is None:
        row = Note(
            tenant_id=tenant_id,
            session_id=visit_id,
            patient_id=patient_id,
            payload=payload,
        )
        session.add(row)
    else:
        row.payload = payload
    await session.flush()
    return row


# --- shares -----------------------------------------------------------------------------


async def revoke_live_shares(
    session: AsyncSession, *, tenant_id: uuid.UUID, note_id: uuid.UUID
) -> None:
    rows = (
        await session.scalars(
            select(Share).where(
                Share.tenant_id == tenant_id,
                Share.note_id == note_id,
                Share.revoked_at.is_(None),
            )
        )
    ).all()
    now = datetime.now(UTC)
    for row in rows:
        row.revoked_at = now


async def create_share(
    session: AsyncSession, *, tenant_id: uuid.UUID, note_id: uuid.UUID, section_ids: list[str]
) -> Share:
    share = Share(
        tenant_id=tenant_id,
        note_id=note_id,
        scope_sections={"section_ids": section_ids},
        expires_at=datetime.now(UTC) + SHARE_TTL,
    )
    session.add(share)
    await session.flush()
    return share


async def live_share(
    session: AsyncSession, *, tenant_id: uuid.UUID, note_id: uuid.UUID
) -> Share | None:
    rows = (
        await session.scalars(
            select(Share).where(
                Share.tenant_id == tenant_id,
                Share.note_id == note_id,
                Share.revoked_at.is_(None),
            )
        )
    ).all()
    now = datetime.now(UTC)
    for row in rows:
        if _is_live(row, now):
            return row
    return None


# --- documents (INT-034 refs; the bytes live in the object store) -----------------------


async def get_patient_pseudonym(
    session: AsyncSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID
) -> str | None:
    """The patients row's own Tokenizer pseudonym (``kid.hex``) — what
    addresses a patient outside this database (invariant 14). ``None`` means
    the row is absent, which callers must treat as a refusal: the row id is
    not a substitute (INT-228)."""
    stmt = select(Patient.pseudonym).where(Patient.tenant_id == tenant_id, Patient.id == patient_id)
    return (await session.scalars(stmt)).first()


async def create_document_row(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    visit_id: uuid.UUID,
    object_ref: str,
    sha256: str,
    media_type: str,
    provenance: dict[str, object],
) -> Document:
    row = Document(
        tenant_id=tenant_id,
        patient_id=patient_id,
        session_id=visit_id,
        object_ref=object_ref,
        sha256=sha256,
        media_type=media_type,
        provenance=provenance,
    )
    session.add(row)
    await session.flush()
    return row


async def list_document_rows(
    session: AsyncSession, *, tenant_id: uuid.UUID, visit_id: uuid.UUID
) -> list[Document]:
    stmt = (
        select(Document)
        .where(Document.tenant_id == tenant_id, Document.session_id == visit_id)
        .order_by(Document.created_at.desc(), Document.id)
    )
    return list((await session.scalars(stmt)).all())


async def get_document_row(
    session: AsyncSession, *, tenant_id: uuid.UUID, visit_id: uuid.UUID, doc_id: uuid.UUID
) -> Document | None:
    stmt = select(Document).where(
        Document.tenant_id == tenant_id,
        Document.session_id == visit_id,
        Document.id == doc_id,
    )
    return (await session.scalars(stmt)).first()


async def update_document_row(
    session: AsyncSession,
    row: Document,
    *,
    object_ref: str | None = None,
    sha256: str | None = None,
    provenance: dict[str, object] | None = None,
) -> None:
    if object_ref is not None:
        row.object_ref = object_ref
    if sha256 is not None:
        row.sha256 = sha256
    if provenance is not None:
        row.provenance = provenance
        flag_modified(row, "provenance")
    await session.flush()

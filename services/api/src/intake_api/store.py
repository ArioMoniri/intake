"""ORM access over the INT-030 models (INT-197). No new tables: a visit is
one ``sessions`` row plus its plain ``visit.*`` slots (hospital and department
always; date, branch, visit type and — since INT-306 — the appointment hour
where a producer stated one); the note is one envelope-bearing ``notes`` row
per visit (updated in place — the audit chain, not row history, is the record
of access); sending is a ``shares`` row
carrying only the scoped-on section ids. The INT-133 attribution columns are
the one column addition, inventoried on the model (invariant 18).

Protocol answers go through :func:`write_slot_answer` (INT-349): the slot's
data category decides the representation, so an answer in any category but
``general_health`` is an EncryptedField envelope bound to its session and slot,
and never plaintext at rest (invariant 14). An answer about another person
(``household``, ``relatives_health``, ``partner_fertility``) is written only for
a tenant whose own row makes it a hospital-controller deployment (INT-474).

Every query carries an explicit ``tenant_id`` predicate even though the
postgres tier enforces the same boundary with RLS — the unit lane (SQLite)
exercises the predicates, the integration lane proves the policies.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal

from clinical_schemas.visit_time import (
    VisitSchedule,
    VisitTime,
    VisitTimeSource,
    parse_visit_time,
)
from intake_platform.db.envelope_json import encrypted_field_from_json, encrypted_field_to_json
from intake_platform.db.models import (
    DoctorLink,
    Document,
    IntakeSession,
    Note,
    Patient,
    PreVisitOutputRow,
    SessionAttribution,
    SessionStatus,
    Share,
    Slot,
    SlotSensitivity,
)
from intake_platform.envelope import EnvelopeCipher
from intake_platform.visit_lifecycle import LIFECYCLE_SLOT, VisitLifecycle
from protocols.deployment_role import HOSPITAL_CONTROLLER_ONLY, require_admitted
from protocols.types import DataCategory
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from intake_api.deployment_role import tenant_deployment_role

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
    "read_slot_answer",
    "revoke_live_shares",
    "slot_sensitivity",
    "time_slot_value",
    "update_document_row",
    "upsert_note",
    "write_slot_answer",
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
# INT-306: the appointment's hour AND which producer stated it, in one slot
# value so the two cannot be written apart. Absent means the hour was never
# stated — never a defaulted midnight, which the expiry rule could not tell
# from a real 00:00 booking (files/02 §2b). Same argument as INT-134: a row in
# the already-inventoried ``slots`` table, so no new tables and no new columns
# (invariant 18), and a pre-INT-306 visit simply lacks it and reads back None.
_SLOT_TIME = "visit.time"

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
    # INT-306 — the appointment's hour with its provenance, or None where no
    # producer stated one. Typed rather than three strings, so a reader cannot
    # get the value without also getting where it came from.
    time: VisitTime | None
    note_status: NoteStatus | None
    # INT-133 / files/06 §6 — read off the session row, so the flag on a
    # visit, on its note and on anything else derived from that session is
    # ONE fact rather than three copies that can disagree.
    attribution: SessionAttribution = SessionAttribution.SELF_REPORT
    third_party_present: bool = False
    # INT-407 — the files/02 §2b lifecycle, read off the ``visit.lifecycle``
    # slot; a visit written before it has none and is ``planned``.
    lifecycle: VisitLifecycle = field(default_factory=VisitLifecycle)
    # INT-407 — when the note's session produced it: the latest send (the
    # completion event in this slice, the previsit output's ``completed_at``)
    # or, for a note never sent, its first save. ``None`` without a note.
    note_anchor: datetime | None = None

    def note_stale(self, now: datetime) -> bool:
        """files/02 §2b: on a rescheduled visit, the note is stale seven days
        after its session. ONE computation, projected on every surface that
        shows the note — the visit card, the note read and the Doctor Link."""
        return self.lifecycle.note_stale(self.note_anchor, now=now)

    @property
    def proxy_reported(self) -> bool:
        """files/06 §6: companion/proxy ANSWERS are flagged.
        ``assisted_self_report`` is the patient's own words on someone
        else's device, so it is not a proxy answer — that session's
        third-party fact travels on ``third_party_present`` (files/02 §3).
        """
        return self.attribution is SessionAttribution.PROXY_REPORT


def time_slot_value(time: VisitTime) -> dict[str, object]:
    """The ``visit.time`` slot value. ``source_ref`` is written only where the
    source has one, so an absent key reads as "the patient typed it" rather
    than as "we lost the ref" (INT-306)."""
    value: dict[str, object] = {"time": time.render(), "source": time.source.value}
    if time.source_ref is not None:
        value["source_ref"] = time.source_ref
    return value


def _visit_time(slot: dict[str, object] | None) -> VisitTime | None:
    """Read the INT-306 time slot back through its own validator.

    Deliberately not a bare ``VisitTime(...)`` construction: a row written by
    an older build, or edited by hand, goes through exactly the spelling and
    provenance rules the write path used, so a value that could not be created
    through the API cannot be read out of the database either. A malformed row
    raises rather than degrading to "no time recorded" — a silent degrade there
    would be indistinguishable from an honest unknown and would shorten the
    link without anything saying so.
    """
    if slot is None:
        return None
    ref = slot.get("source_ref")
    return parse_visit_time(
        str(slot["time"]),
        source=VisitTimeSource(str(slot["source"])),
        source_ref=str(ref) if ref is not None else None,
    )


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
    time: VisitTime | None = None,
    attribution: SessionAttribution = SessionAttribution.SELF_REPORT,
    third_party_present: bool = False,
    proxy_ack_at: datetime | None = None,
) -> uuid.UUID:
    visit = IntakeSession(
        tenant_id=tenant_id,
        patient_id=patient_id,
        protocol_id=VISIT_PROTOCOL_ID,
        protocol_version=VISIT_PROTOCOL_VERSION,
        status=SessionStatus.CREATED,
        # INT-133: stamped at creation, never patched afterwards — who
        # answered is a fact about the session, not a mutable label.
        attribution=attribution,
        third_party_present=third_party_present,
        proxy_ack_at=proxy_ack_at,
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
    if time is not None:
        values.append((_SLOT_TIME, time_slot_value(time)))
    # INT-407: a new visit is ``planned``; a dated one queues its T-24h confirm
    # (files/02 §2b), which stays queued while no SMS vendor exists (INT-358).
    schedule = (
        VisitSchedule(date=dt.date.fromisoformat(date), time=time) if date is not None else None
    )
    lifecycle = VisitLifecycle.initial(
        schedule, confirm_message_id=str(uuid.uuid4()) if schedule is not None else None
    )
    values.append((LIFECYCLE_SLOT, lifecycle.to_slot()))
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

    statuses, anchors = await _note_facts(session, tenant_id=tenant_id, session_ids=ids)

    records: list[VisitRecord] = []
    for visit in visits:
        visit_slots = slots.get(visit.id, {})
        # a previsit.dev.visit row always carries hospital+department; a row
        # that does not is corrupt and must fail loudly, not render half a
        # visit. date/branch/visit_type are honestly optional (INT-134).
        hospital = str(visit_slots[_SLOT_HOSPITAL]["text"])
        department = str(visit_slots[_SLOT_DEPARTMENT]["text"])
        date_slot = visit_slots.get(_SLOT_DATE)
        time_slot = visit_slots.get(_SLOT_TIME)
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
                time=_visit_time(time_slot),
                note_status=statuses.get(visit.id),
                attribution=visit.attribution,
                third_party_present=visit.third_party_present,
                # a malformed record raises, like a malformed time slot: a
                # silent "planned" would hide a cancelled or rescheduled visit
                lifecycle=VisitLifecycle.from_slot(visit_slots.get(LIFECYCLE_SLOT)),
                note_anchor=anchors.get(visit.id),
            )
        )
    return records


async def _note_facts(
    session: AsyncSession, *, tenant_id: uuid.UUID, session_ids: list[uuid.UUID]
) -> tuple[dict[uuid.UUID, NoteStatus], dict[uuid.UUID, datetime]]:
    """Per visit: the note's derived status, and the instant its session
    produced it (INT-407's staleness anchor)."""
    note_rows = (
        await session.scalars(
            select(Note).where(Note.tenant_id == tenant_id, Note.session_id.in_(session_ids))
        )
    ).all()
    if not note_rows:
        return {}, {}
    outputs = (
        await session.scalars(
            select(PreVisitOutputRow).where(
                PreVisitOutputRow.tenant_id == tenant_id,
                PreVisitOutputRow.session_id.in_(session_ids),
            )
        )
    ).all()
    sent_at = {row.session_id: _aware(row.completed_at) for row in outputs}
    anchors = {n.session_id: sent_at.get(n.session_id, _aware(n.created_at)) for n in note_rows}
    return await _note_statuses(session, tenant_id=tenant_id, note_rows=note_rows), anchors


async def _note_statuses(
    session: AsyncSession, *, tenant_id: uuid.UUID, note_rows: Sequence[Note]
) -> dict[uuid.UUID, NoteStatus]:
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


# --- protocol slot answers (INT-349) ------------------------------------------------------


def slot_sensitivity(category: DataCategory) -> SlotSensitivity:
    """``general_health`` stays the plain JSON value it always was; every other
    category is an envelope (owner decision D3: sensitive categories are stored
    encrypted before any of them is served)."""
    if category is DataCategory.GENERAL_HEALTH:
        return SlotSensitivity.PLAIN
    return SlotSensitivity.SENSITIVE


def _slot_aad(session_id: uuid.UUID, slot_id: str) -> bytes:
    """Binds the ciphertext to its row, so an envelope moved under another
    session or question fails authentication instead of reading as that
    question's answer."""
    return f"slots.value:{session_id}:{slot_id}".encode()


async def write_slot_answer(
    session: AsyncSession,
    *,
    cipher: EnvelopeCipher,
    tenant_id: uuid.UUID,
    session_id: uuid.UUID,
    slot_id: str,
    data_category: DataCategory | str,
    value: dict[str, object],
) -> Slot:
    """Write (or correct) one protocol answer in the representation its data
    category requires. The category has no default: a caller that does not
    know it cannot write. An unknown category raises before anything is
    written.

    A category about another person raises ``DeploymentRoleRefused`` before
    anything is written unless the tenant row is a hospital-controller
    deployment (INT-474). The role is the tenant's configuration; no parameter
    here can state it."""
    category = DataCategory(data_category)
    if category in HOSPITAL_CONTROLLER_ONLY:
        require_admitted(category, await tenant_deployment_role(session, tenant_id=tenant_id))
    sensitivity = slot_sensitivity(category)
    stored: dict[str, object]
    if sensitivity is SlotSensitivity.PLAIN:
        stored = dict(value)
    else:
        plaintext = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
        field = cipher.encrypt_field(str(tenant_id), plaintext, aad=_slot_aad(session_id, slot_id))
        stored = dict(encrypted_field_to_json(field))
    row = await _slot_row(session, tenant_id=tenant_id, session_id=session_id, slot_id=slot_id)
    if row is None:
        row = Slot(
            tenant_id=tenant_id,
            session_id=session_id,
            slot_id=slot_id,
            sensitivity=sensitivity,
            value=stored,
        )
        session.add(row)
    else:
        row.sensitivity = sensitivity
        row.value = stored
    await session.flush()
    return row


async def read_slot_answer(
    session: AsyncSession,
    *,
    cipher: EnvelopeCipher,
    tenant_id: uuid.UUID,
    session_id: uuid.UUID,
    slot_id: str,
) -> dict[str, object] | None:
    """The answer as written, opening the envelope where there is one. A
    tampered or moved envelope raises ``TamperError``; it never reads as
    empty."""
    row = await _slot_row(session, tenant_id=tenant_id, session_id=session_id, slot_id=slot_id)
    if row is None:
        return None
    if row.sensitivity is SlotSensitivity.PLAIN:
        return dict(row.value)
    field = encrypted_field_from_json(row.value)
    plaintext = cipher.decrypt_field(str(tenant_id), field, aad=_slot_aad(session_id, slot_id))
    loaded: dict[str, object] = json.loads(plaintext.decode("utf-8"))
    return loaded


async def _slot_row(
    session: AsyncSession, *, tenant_id: uuid.UUID, session_id: uuid.UUID, slot_id: str
) -> Slot | None:
    stmt = select(Slot).where(
        Slot.tenant_id == tenant_id,
        Slot.session_id == session_id,
        Slot.slot_id == slot_id,
    )
    return (await session.scalars(stmt)).first()


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
        # INT-150: a link is a way to reach a share, so it cannot outlive the
        # share. Every save takes the note back to draft (notes.write_note),
        # and a patient who did that must not find an old link still open.
        await _revoke_links_of_share(session, tenant_id=tenant_id, share_id=row.id, now=now)


async def _revoke_links_of_share(
    session: AsyncSession, *, tenant_id: uuid.UUID, share_id: uuid.UUID, now: datetime
) -> None:
    links = (
        await session.scalars(
            select(DoctorLink).where(
                DoctorLink.tenant_id == tenant_id,
                DoctorLink.share_id == share_id,
                DoctorLink.revoked_at.is_(None),
            )
        )
    ).all()
    for link in links:
        link.revoked_at = now


async def create_share(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    note_id: uuid.UUID,
    section_ids: list[str],
    withheld_section_ids: list[str],
) -> Share:
    # ``section_ids`` is the grant the read path and Doctor Link redemption read;
    # ``withheld_section_ids`` records the patient's scope-off choices as an
    # affirmative fact rather than an absence (INT-304, invariant 4). Readers
    # still consult ``section_ids`` only, so a section is served only when it is
    # explicitly in the grant (fail-closed).
    share = Share(
        tenant_id=tenant_id,
        note_id=note_id,
        scope_sections={
            "section_ids": section_ids,
            "withheld_section_ids": withheld_section_ids,
        },
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

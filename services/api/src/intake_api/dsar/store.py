"""ORM access for the DSAR tables and the subject-scoped record sweep.

Every query carries an explicit ``tenant_id`` predicate even though postgres
enforces the same boundary with RLS — the unit lane (SQLite) exercises the
predicates, the integration lane proves the policies (the INT-197 store
precedent).

The sweep in :func:`subject_record` is the one place that answers "everything
we hold about this subject", and both the export and the erasure read it. One
answer, not two: an export that showed less than the erasure destroyed, or an
erasure that missed what the export listed, is the defect a DSAR audit finds.

INT-395 made that true again. The erasure had grown its own queries for the
learned facts (INT-170), the previsit outputs (INT-392) and the Doctor Links
(INT-393), so it destroyed rows the export never showed. They live here now,
with the other subject tables the inventory annotations put under the
subject's rights; tests/data/test_session_delete_contract.py derives that
list from the annotations and checks the export against it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from intake_platform.db.models import (
    Consent,
    CsatText,
    DoctorLink,
    Document,
    DsarKind,
    DsarRectification,
    DsarRequest,
    DsarStatus,
    GuardianLink,
    IntakeSession,
    Note,
    NotificationPreference,
    OverlayFact,
    PatientOverlayHeader,
    PreVisitOutputRow,
    Share,
    Slot,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from intake_api.dsar.sla import due_at, grace_ends_at

__all__ = [
    "SubjectRecord",
    "create_request",
    "create_rectification",
    "get_request",
    "list_requests",
    "subject_record",
]


@dataclass(frozen=True)
class SubjectRecord:
    """Everything the controller holds for one data subject, in one place."""

    sessions: tuple[IntakeSession, ...]
    slots: tuple[Slot, ...]
    notes: tuple[Note, ...]
    shares: tuple[Share, ...]
    documents: tuple[Document, ...]
    consents: tuple[Consent, ...]
    rectifications: tuple[DsarRectification, ...]
    requests: tuple[DsarRequest, ...]
    #: INT-392: each sent note's frozen hospital-facing projection.
    previsit_outputs: tuple[PreVisitOutputRow, ...]
    #: INT-393: every grant ever issued over the subject's shares.
    doctor_links: tuple[DoctorLink, ...]
    #: INT-170: the confirmed learned facts and the overlay's version header.
    overlay_facts: tuple[OverlayFact, ...]
    overlay_headers: tuple[PatientOverlayHeader, ...]
    #: INT-240: the satisfaction comments, per session.
    csat_texts: tuple[CsatText, ...]
    #: INT-141: the opt-out and quiet window (one row per patient at most).
    notification_preferences: tuple[NotificationPreference, ...]
    #: INT-223: the links naming this subject as a minor (gate shut today).
    guardian_links: tuple[GuardianLink, ...]

    def slots_for(self, session_id: uuid.UUID) -> tuple[Slot, ...]:
        return tuple(slot for slot in self.slots if slot.session_id == session_id)

    def notes_for(self, session_id: uuid.UUID) -> tuple[Note, ...]:
        return tuple(note for note in self.notes if note.session_id == session_id)


async def subject_record(
    session: AsyncSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID
) -> SubjectRecord:
    sessions = tuple(
        (
            await session.scalars(
                select(IntakeSession)
                .where(
                    IntakeSession.tenant_id == tenant_id,
                    IntakeSession.patient_id == patient_id,
                )
                .order_by(IntakeSession.created_at, IntakeSession.id)
            )
        ).all()
    )
    session_ids = [row.id for row in sessions]
    slots = (
        tuple(
            (
                await session.scalars(
                    select(Slot)
                    .where(Slot.tenant_id == tenant_id, Slot.session_id.in_(session_ids))
                    .order_by(Slot.slot_id, Slot.id)
                )
            ).all()
        )
        if session_ids
        else ()
    )
    notes = tuple(
        (
            await session.scalars(
                select(Note)
                .where(Note.tenant_id == tenant_id, Note.patient_id == patient_id)
                .order_by(Note.created_at, Note.id)
            )
        ).all()
    )
    note_ids = [row.id for row in notes]
    shares = (
        tuple(
            (
                await session.scalars(
                    select(Share)
                    .where(Share.tenant_id == tenant_id, Share.note_id.in_(note_ids))
                    .order_by(Share.created_at, Share.id)
                )
            ).all()
        )
        if note_ids
        else ()
    )
    documents = tuple(
        (
            await session.scalars(
                select(Document)
                .where(Document.tenant_id == tenant_id, Document.patient_id == patient_id)
                .order_by(Document.created_at, Document.id)
            )
        ).all()
    )
    consents = tuple(
        (
            await session.scalars(
                select(Consent)
                .where(Consent.tenant_id == tenant_id, Consent.patient_id == patient_id)
                .order_by(Consent.granted_at, Consent.id)
            )
        ).all()
    )
    rectifications = tuple(
        (
            await session.scalars(
                select(DsarRectification)
                .where(
                    DsarRectification.tenant_id == tenant_id,
                    DsarRectification.patient_id == patient_id,
                )
                .order_by(DsarRectification.created_at, DsarRectification.id)
            )
        ).all()
    )
    requests = tuple(await list_requests(session, tenant_id=tenant_id, patient_id=patient_id))
    share_ids = [row.id for row in shares]
    return SubjectRecord(
        sessions=sessions,
        slots=slots,
        notes=notes,
        shares=shares,
        documents=documents,
        consents=consents,
        rectifications=rectifications,
        requests=requests,
        previsit_outputs=tuple(
            (
                await session.scalars(
                    select(PreVisitOutputRow)
                    .where(
                        PreVisitOutputRow.tenant_id == tenant_id,
                        PreVisitOutputRow.patient_id == patient_id,
                    )
                    .order_by(PreVisitOutputRow.created_at, PreVisitOutputRow.id)
                )
            ).all()
        ),
        doctor_links=(
            tuple(
                (
                    await session.scalars(
                        select(DoctorLink)
                        .where(
                            DoctorLink.tenant_id == tenant_id, DoctorLink.share_id.in_(share_ids)
                        )
                        .order_by(DoctorLink.created_at, DoctorLink.id)
                    )
                ).all()
            )
            if share_ids
            else ()
        ),
        overlay_facts=tuple(
            (
                await session.scalars(
                    select(OverlayFact)
                    .where(OverlayFact.tenant_id == tenant_id, OverlayFact.patient_id == patient_id)
                    .order_by(OverlayFact.fact_key, OverlayFact.id)
                )
            ).all()
        ),
        overlay_headers=tuple(
            (
                await session.scalars(
                    select(PatientOverlayHeader).where(
                        PatientOverlayHeader.tenant_id == tenant_id,
                        PatientOverlayHeader.patient_id == patient_id,
                    )
                )
            ).all()
        ),
        csat_texts=(
            tuple(
                (
                    await session.scalars(
                        select(CsatText)
                        .where(
                            CsatText.tenant_id == tenant_id, CsatText.session_id.in_(session_ids)
                        )
                        .order_by(CsatText.created_at, CsatText.id)
                    )
                ).all()
            )
            if session_ids
            else ()
        ),
        notification_preferences=tuple(
            (
                await session.scalars(
                    select(NotificationPreference).where(
                        NotificationPreference.tenant_id == tenant_id,
                        NotificationPreference.patient_id == patient_id,
                    )
                )
            ).all()
        ),
        guardian_links=tuple(
            (
                await session.scalars(
                    select(GuardianLink)
                    .where(
                        GuardianLink.tenant_id == tenant_id,
                        GuardianLink.minor_patient_id == patient_id,
                    )
                    .order_by(GuardianLink.created_at, GuardianLink.id)
                )
            ).all()
        ),
    )


async def create_request(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    kind: DsarKind,
    status: DsarStatus,
    received_at: datetime,
    with_grace: bool = False,
) -> DsarRequest:
    row = DsarRequest(
        tenant_id=tenant_id,
        patient_id=patient_id,
        kind=kind,
        status=status,
        received_at=received_at,
        due_at=due_at(received_at),
        grace_ends_at=grace_ends_at(received_at) if with_grace else None,
    )
    session.add(row)
    await session.flush()
    return row


async def get_request(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    request_id: uuid.UUID,
) -> DsarRequest | None:
    return (
        await session.scalars(
            select(DsarRequest).where(
                DsarRequest.tenant_id == tenant_id,
                DsarRequest.patient_id == patient_id,
                DsarRequest.id == request_id,
            )
        )
    ).first()


async def list_requests(
    session: AsyncSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID
) -> list[DsarRequest]:
    return list(
        (
            await session.scalars(
                select(DsarRequest)
                .where(
                    DsarRequest.tenant_id == tenant_id,
                    DsarRequest.patient_id == patient_id,
                )
                .order_by(DsarRequest.received_at, DsarRequest.id)
            )
        ).all()
    )


async def create_rectification(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    request_id: uuid.UUID,
    target_ref: str,
    payload: dict[str, object],
) -> DsarRectification:
    row = DsarRectification(
        tenant_id=tenant_id,
        patient_id=patient_id,
        request_id=request_id,
        target_ref=target_ref,
        payload=payload,
    )
    session.add(row)
    await session.flush()
    return row

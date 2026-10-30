"""Data-subject rights endpoints (INT-037): export, erasure, rectification
and the KVKK m.13 tracker.

Basis, not consent. Every route here carries the ``data_subject_right``
declaration rather than a consent scope: KVKK m.11 is exercisable regardless
of consent state, and a route that 403'd on a withdrawn ``core`` grant could
never answer the request that withdrawal itself provokes. Access control does
not weaken — the routes are patient-only, act on the requesting subject's own
rows, and every action appends to the hash-chained audit against
``basis:KVKK-11/13``.

Fail closed. The export renders its fixed strings from ``docs/legal`` with
hash binding (files/06 §7; invariant 18). Until INT-210 authors them the
export refuses with 503 — and the request is still recorded, because the
obligation exists whether or not we can yet render the answer, and an
unanswerable request that never entered the tracker is an obligation nobody
can see.
"""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from intake_platform.db.envelope_json import encrypted_field_to_json
from intake_platform.db.models import DsarKind, DsarRequest, DsarStatus, Note
from intake_platform.legal import (
    LegalStrings,
    LegalStringsChangedError,
    LegalStringsError,
    LegalStringsMissingError,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from intake_api import store as record_store
from intake_api.auth import Principal, require_patient
from intake_api.consent_guard import data_subject_right
from intake_api.db import tenant_session
from intake_api.dsar import store as dsar_store
from intake_api.dsar.audit import DSAR_BASIS_REF
from intake_api.dsar.document import render_export_document
from intake_api.dsar.export import build_export_bundle, build_view
from intake_api.dsar.schemas import (
    DsarExportOut,
    DsarPdfOut,
    DsarRectifyIn,
    DsarRectifyOut,
    DsarRequestOut,
    DsarScheduleOut,
)
from intake_api.dsar.sla import is_overdue
from intake_api.dsar.strings import DSAR_EXPORT_STRING_KEYS
from intake_api.errors import not_found
from intake_api.passkey.actions import StepUpAction
from intake_api.passkey.gate import require_step_up
from intake_api.state import ApiState, State

__all__ = ["router"]

router = APIRouter(prefix="/v1/me/dsar", tags=["dsar"], dependencies=[data_subject_right()])


def _legal_strings_missing() -> HTTPException:
    """The fixed strings are not authored yet (INT-210): no text, no lawful
    m.13 response document — refuse rather than ship a half-rendered one."""
    return HTTPException(status_code=503, detail={"error": "legal_strings_missing"})


def _legal_strings_changed() -> HTTPException:
    return HTTPException(status_code=409, detail={"error": "legal_strings_changed"})


def _grace_elapsed() -> HTTPException:
    return HTTPException(status_code=409, detail={"error": "dsar_grace_elapsed"})


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _iso(value: datetime | None) -> str | None:
    return None if value is None else _aware(value).isoformat()


def _to_out(row: DsarRequest, *, now: datetime) -> DsarRequestOut:
    return DsarRequestOut(
        request_id=row.id,
        kind=row.kind.value,
        status=row.status.value,
        received_at=_aware(row.received_at).isoformat(),
        due_at=_aware(row.due_at).isoformat(),
        grace_ends_at=_iso(row.grace_ends_at),
        completed_at=_iso(row.completed_at),
        overdue=is_overdue(row, now=now),
    )


def _bound_strings(state: ApiState, *, expected_hash: str | None = None) -> LegalStrings:
    try:
        return state.legal_strings.entry(
            required=DSAR_EXPORT_STRING_KEYS, expected_hash=expected_hash
        )
    except LegalStringsChangedError as err:
        raise _legal_strings_changed() from err
    except LegalStringsMissingError as err:
        raise _legal_strings_missing() from err
    except LegalStringsError as err:
        # an unversionable or malformed legal file is a defect in the legal
        # tree, not an absence — same refusal, so nothing renders either way
        raise _legal_strings_missing() from err


# --- access (KVKK m.11 a/b/d — export) ----------------------------------------------


@router.post("/export", response_model=DsarRequestOut, status_code=201)
async def request_export(principal: Principal, state: State) -> DsarRequestOut:
    patient, patient_id = require_patient(principal)
    now = datetime.now(UTC)
    async with tenant_session(state.engine, patient.tenant_id) as session:
        row = await dsar_store.create_request(
            session,
            tenant_id=patient.tenant_id,
            patient_id=patient_id,
            kind=DsarKind.EXPORT,
            status=DsarStatus.RECEIVED,
            received_at=now,
        )
        out = _to_out(row, now=now)
    await state.audit.record(
        actor=f"patient:{patient_id}",
        action="dsar.export.request",
        resource_ref=f"dsar-request:{out.request_id}",
        consent_scope=DSAR_BASIS_REF,
    )
    return out


@router.get(
    "/export/{request_id}",
    response_model=DsarExportOut,
    # INT-582 (D36): data export steps up where the data leaves — here, not
    # at the tracker row POST /export writes, which returns none of it
    dependencies=[require_step_up(StepUpAction.DATA_EXPORT)],
)
async def read_export(request_id: uuid.UUID, principal: Principal, state: State) -> DsarExportOut:
    """The answer itself: FHIR bundle + PDF, bound to the legal strings.

    ``generated_at`` is the request's own ``received_at``, so the document's
    instant does not drift between downloads.

    This GET does write two things, deliberately: the completion instant and
    the strings hash the answer was issued under. Both are facts about
    DELIVERY, and delivery is the only moment either is knowable — a KVKK
    m.13 request is answered when the subject receives the answer, not when a
    job decides it is ready. The write is convergent (received → completed,
    hash set once), so a retried or repeated download changes nothing further.
    """
    patient, patient_id = require_patient(principal)
    async with tenant_session(state.engine, patient.tenant_id) as session:
        row = await dsar_store.get_request(
            session,
            tenant_id=patient.tenant_id,
            patient_id=patient_id,
            request_id=request_id,
        )
        if row is None or row.kind is not DsarKind.EXPORT:
            raise not_found()
        # first issue binds; a re-issue must match the copy it was issued
        # under, or it is a different document wearing the same id
        strings = _bound_strings(state, expected_hash=row.legal_strings_hash)
        record = await dsar_store.subject_record(
            session, tenant_id=patient.tenant_id, patient_id=patient_id
        )
        view = build_view(
            record,
            tenant_id=patient.tenant_id,
            patient_id=patient_id,
            cipher=state.cipher,
            generated_at=_aware(row.received_at),
        )
        bundle = build_export_bundle(view, strings=strings)
        document = render_export_document(view, strings=strings)
        row.legal_strings_hash = document.legal_strings_hash
        if row.status is not DsarStatus.COMPLETED:
            row.status = DsarStatus.COMPLETED
            row.completed_at = datetime.now(UTC)
    await state.audit.record(
        actor=f"patient:{patient_id}",
        action="dsar.export.issue",
        resource_ref=f"dsar-request:{request_id}",
        consent_scope=DSAR_BASIS_REF,
    )
    return DsarExportOut(
        request_id=request_id,
        generated_at=_aware(row.received_at).isoformat(),
        legal_strings_version=document.legal_strings_version,
        legal_strings_hash=document.legal_strings_hash,
        fhir_bundle=bundle,
        pdf=DsarPdfOut(
            media_type="application/pdf",
            sha256=hashlib.sha256(document.pdf).hexdigest(),
            base64=base64.b64encode(document.pdf).decode("ascii"),
        ),
    )


# --- erasure (KVKK m.11 e/f — delete) -----------------------------------------------


@router.post(
    "/delete",
    response_model=DsarScheduleOut,
    status_code=201,
    # INT-582 (D36): data delete steps up to the patient's passkey
    dependencies=[require_step_up(StepUpAction.DATA_DELETE)],
)
async def request_delete(principal: Principal, state: State) -> DsarScheduleOut:
    """Schedule the erasure: cancel every live share now (files/06 §2.3 — a
    withdrawal cancels shares rather than orphaning them), start the files/06
    §3 grace, and leave the record readable to the subject until it ends."""
    patient, patient_id = require_patient(principal)
    now = datetime.now(UTC)
    async with tenant_session(state.engine, patient.tenant_id) as session:
        row = await dsar_store.create_request(
            session,
            tenant_id=patient.tenant_id,
            patient_id=patient_id,
            kind=DsarKind.DELETE,
            status=DsarStatus.SCHEDULED,
            received_at=now,
            with_grace=True,
        )
        cancelled = await _cancel_live_shares(
            session, tenant_id=patient.tenant_id, patient_id=patient_id
        )
        out = _to_out(row, now=now)
    await state.audit.record(
        actor=f"patient:{patient_id}",
        action="dsar.delete.request",
        resource_ref=f"dsar-request:{out.request_id}",
        consent_scope=DSAR_BASIS_REF,
    )
    return DsarScheduleOut(**out.model_dump(), shares_cancelled=cancelled)


async def _cancel_live_shares(
    session: AsyncSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID
) -> int:
    notes = (
        await session.scalars(
            select(Note).where(Note.tenant_id == tenant_id, Note.patient_id == patient_id)
        )
    ).all()
    cancelled = 0
    for note in notes:
        live = await record_store.live_share(session, tenant_id=tenant_id, note_id=note.id)
        if live is not None:
            cancelled += 1
        await record_store.revoke_live_shares(session, tenant_id=tenant_id, note_id=note.id)
    return cancelled


@router.delete(
    "/delete/{request_id}",
    response_model=DsarRequestOut,
    # INT-582 review: withdrawing a scheduled erasure is a data_delete step-up
    # too, or an OTP-only session (a SIM swap) could cancel the holder's
    dependencies=[require_step_up(StepUpAction.DATA_DELETE)],
)
async def cancel_delete(
    request_id: uuid.UUID, principal: Principal, state: State
) -> DsarRequestOut:
    """Withdraw a scheduled erasure inside its grace.

    The shares stay revoked: un-sharing is the patient's decision and the
    server cannot know they want it republished to a clinic. They re-send.
    """
    patient, patient_id = require_patient(principal)
    now = datetime.now(UTC)
    async with tenant_session(state.engine, patient.tenant_id) as session:
        row = await dsar_store.get_request(
            session,
            tenant_id=patient.tenant_id,
            patient_id=patient_id,
            request_id=request_id,
        )
        if row is None or row.kind is not DsarKind.DELETE:
            raise not_found()
        if row.status is not DsarStatus.SCHEDULED:
            raise _grace_elapsed()
        if row.grace_ends_at is not None and _aware(row.grace_ends_at) <= now:
            raise _grace_elapsed()
        row.status = DsarStatus.CANCELLED
        row.completed_at = now
        out = _to_out(row, now=now)
    await state.audit.record(
        actor=f"patient:{patient_id}",
        action="dsar.delete.cancel",
        resource_ref=f"dsar-request:{request_id}",
        consent_scope=DSAR_BASIS_REF,
    )
    return out


# --- rectification (KVKK m.11 d; KSVY m.13) -----------------------------------------


@router.post("/rectify", response_model=DsarRectifyOut, status_code=201)
async def request_rectify(
    payload: DsarRectifyIn, principal: Principal, state: State
) -> DsarRectifyOut:
    """Record a correction as an ADDENDUM (files/02 §3), never a rewrite."""
    patient, patient_id = require_patient(principal)
    now = datetime.now(UTC)
    kind, _, raw_id = payload.target_ref.partition(":")
    target_id = uuid.UUID(raw_id)
    async with tenant_session(state.engine, patient.tenant_id) as session:
        await _require_own_target(
            session, tenant_id=patient.tenant_id, patient_id=patient_id, kind=kind, target=target_id
        )
        request = await dsar_store.create_request(
            session,
            tenant_id=patient.tenant_id,
            patient_id=patient_id,
            kind=DsarKind.RECTIFY,
            status=DsarStatus.COMPLETED,
            received_at=now,
        )
        request.completed_at = now
        plaintext = json.dumps(
            {"correction": payload.correction}, ensure_ascii=False, sort_keys=True
        ).encode("utf-8")
        field = state.cipher.encrypt_field(str(patient.tenant_id), plaintext)
        addendum = await dsar_store.create_rectification(
            session,
            tenant_id=patient.tenant_id,
            patient_id=patient_id,
            request_id=request.id,
            target_ref=payload.target_ref,
            payload=dict(encrypted_field_to_json(field)),
        )
        out = DsarRectifyOut(
            request_id=request.id,
            rectification_id=addendum.id,
            target_ref=payload.target_ref,
            status="completed",
        )
    await state.audit.record(
        actor=f"patient:{patient_id}",
        action="dsar.rectify",
        resource_ref=f"dsar-rectification:{out.rectification_id}",
        consent_scope=DSAR_BASIS_REF,
    )
    return out


async def _require_own_target(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    kind: str,
    target: uuid.UUID,
) -> None:
    record = await dsar_store.subject_record(session, tenant_id=tenant_id, patient_id=patient_id)
    owned: set[uuid.UUID] = {
        "note": {row.id for row in record.notes},
        "visit": {row.id for row in record.sessions},
        "document": {row.id for row in record.documents},
    }[kind]
    if target not in owned:
        raise not_found()


# --- the tracker ---------------------------------------------------------------------


@router.get("/requests", response_model=list[DsarRequestOut])
async def list_own_requests(principal: Principal, state: State) -> list[DsarRequestOut]:
    """The subject's own KVKK m.13 clocks. The tenant-wide compliance queue
    over the same rows is the admin console's surface (INT-189)."""
    patient, patient_id = require_patient(principal)
    now = datetime.now(UTC)
    async with tenant_session(state.engine, patient.tenant_id) as session:
        rows = await dsar_store.list_requests(
            session, tenant_id=patient.tenant_id, patient_id=patient_id
        )
        return [_to_out(row, now=now) for row in rows]

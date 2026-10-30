"""INT-150 — the PATIENT's Doctor Link surface (files/10 §2, §3).

Issue, list, mint an opening code, revoke, and read the access log — all over
the patient's own note, all authenticated, all consent-gated at the door.

The one rule that lives here and nowhere else: **the expiry is computed on
the server**. files/02 §2b pins Doctor Link expiry to ``visit_datetime + 72 h``
and says in terms that ``issue_time + 72 h`` is the wrong clock. The client
holds a visit schedule; the server holds the rule; a visit with no recorded
date is refused rather than given an invented clock (``visit_date_unknown``).

Since INT-306 the schedule may also carry the appointment's hour, and the
expiry then uses it. A visit that records no hour keeps INT-150's start-of-day
anchor — the documented fallback, never later than the appointment — which is
why an unknown time is NOT a refusal the way an unknown date is: a date is the
whole anchor, an hour only sharpens it.
"""

from __future__ import annotations

import uuid
from datetime import date

from clinical_schemas.visit_time import VisitSchedule
from fastapi import APIRouter, Depends, Request
from intake_platform.access_log import build_access_log
from intake_platform.db.models import DoctorLink, Note
from intake_platform.doctor_link import (
    DEFAULT_VIEW_LIMIT,
    RecipientInvalidError,
    link_expires_at,
    new_token,
    normalise_recipient,
    token_fingerprint,
)
from sqlalchemy.ext.asyncio import AsyncSession

from intake_api import store
from intake_api.auth import Principal, require_patient
from intake_api.consent_guard import ensure_consent, require_scopes
from intake_api.db import tenant_session
from intake_api.doctor_link import store as links
from intake_api.doctor_link.common import (
    accessor_role,
    decrypt_recipient,
    encrypt_recipient,
    link_out,
    no_index,
    require_live,
    service_of,
)
from intake_api.doctor_link.metrics import DoctorLinkEvent, record_event
from intake_api.doctor_link.schemas import (
    AccessLogEntryOut,
    DoctorLinkCreate,
    DoctorLinkIssued,
    DoctorLinkOtpOut,
    DoctorLinkOut,
)
from intake_api.errors import not_found, note_not_shared, otp_limited, visit_invalid
from intake_api.notes import SHARE_SCOPE
from intake_api.passkey.actions import StepUpAction
from intake_api.passkey.gate import require_step_up
from intake_api.state import State
from intake_api.visits import CORE_SCOPE

__all__ = ["router"]

router = APIRouter(
    prefix="/v1/visits/{visit_id}/note/doctor-links",
    tags=["doctor-link"],
    dependencies=[Depends(no_index)],
)


async def _own_note(
    session: AsyncSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID, visit_id: uuid.UUID
) -> tuple[store.VisitRecord, Note]:
    visit = await store.get_visit(
        session, tenant_id=tenant_id, visit_id=visit_id, patient_id=patient_id
    )
    if visit is None:
        raise not_found()
    note = await store.get_note_row(session, tenant_id=tenant_id, visit_id=visit_id)
    if note is None:
        raise not_found()
    return visit, note


async def _link_of_patient(
    session: AsyncSession, *, tenant_id: uuid.UUID, note_id: uuid.UUID, link_id: uuid.UUID
) -> DoctorLink:
    """A link reachable only through the caller's OWN note: the id in the path
    is never trusted to name a row on its own."""
    for candidate in await links.doctor_links_for_note(
        session, tenant_id=tenant_id, note_id=note_id
    ):
        if candidate.id == link_id:
            return candidate
    raise not_found()


@router.post(
    "",
    response_model=DoctorLinkIssued,
    status_code=201,
    # files/06 §2.1 / KVKK m.7: a route may not ENFORCE core together with an
    # optional purpose — that is service conditioning. The share purpose is
    # declared conditional and enforced inside the endpoint, exactly as
    # notes.write_note does, so refusing it costs the share and nothing else.
    # INT-582 (D36): issuing a Doctor Link steps up to the patient's passkey,
    # after the consent check so a consent refusal never spends a grant; a
    # patient with no passkey keeps the OTP-session tier and is offered one.
    dependencies=[
        require_scopes(CORE_SCOPE, conditional=(SHARE_SCOPE,)),
        require_step_up(StepUpAction.DOCTOR_LINK_ISSUE),
    ],
)
async def issue_link(
    visit_id: uuid.UUID, payload: DoctorLinkCreate, principal: Principal, state: State
) -> DoctorLinkIssued:
    """Mint one grant over the note's live share. The token is returned once."""
    patient, patient_id = require_patient(principal)
    service = service_of(state)
    try:
        recipient = normalise_recipient(payload.recipient)
    except RecipientInvalidError:
        # the code, never the value: the label is patient-typed (invariant 6)
        raise visit_invalid("recipient_invalid") from None

    async with tenant_session(state.engine, patient.tenant_id) as session:
        visit, note = await _own_note(
            session, tenant_id=patient.tenant_id, patient_id=patient_id, visit_id=visit_id
        )
        if visit.date is None:
            raise visit_invalid("visit_date_unknown")
        share = await store.live_share(session, tenant_id=patient.tenant_id, note_id=note.id)
        if share is None:
            raise note_not_shared()
        await ensure_consent(
            session,
            state=state,
            tenant_id=patient.tenant_id,
            patient_id=patient_id,
            scope=SHARE_SCOPE,
            actor=patient.account_id,
        )
        token = new_token()
        # INT-306: files/02 §2b's own rule where the visit records an hour,
        # INT-150's start-of-day anchor as the documented fallback where it
        # does not. The schedule type is what makes that choice explicit here
        # rather than hidden inside a defaulted midnight.
        expires_at = link_expires_at(
            VisitSchedule(date=date.fromisoformat(visit.date), time=visit.time)
        )
        link = await links.create_doctor_link(
            session,
            tenant_id=patient.tenant_id,
            share_id=share.id,
            token_fingerprint=token_fingerprint(token),
            recipient=encrypt_recipient(state, patient.tenant_id, recipient),
            expires_at=expires_at,
            view_limit=payload.view_limit or DEFAULT_VIEW_LIMIT,
        )
        now = service.utcnow()
        await service.register(
            fingerprint=link.token_fingerprint,
            link_id=link.id,
            tenant_id=patient.tenant_id,
            ttl_s=int(max((expires_at - now).total_seconds(), 1)),
        )
        await state.audit.record(
            actor=patient.account_id,
            action="api.doctor_link.issued",
            resource_ref=f"doctor_link:{link.id}",
            consent_scope=f"scope:{SHARE_SCOPE}",
        )
        record_event(DoctorLinkEvent.ISSUED)
        return DoctorLinkIssued(**link_out(link, recipient, now=now).model_dump(), token=token)


@router.get("", response_model=list[DoctorLinkOut], dependencies=[require_scopes(CORE_SCOPE)])
async def list_links(
    visit_id: uuid.UUID, principal: Principal, state: State
) -> list[DoctorLinkOut]:
    """Every grant over this note — live, expired and revoked.

    Finished grants stay visible on purpose: "nobody has access" and "access
    ended yesterday" must not be the same screen for the person who shared it.
    """
    patient, patient_id = require_patient(principal)
    service = service_of(state)
    async with tenant_session(state.engine, patient.tenant_id) as session:
        _, note = await _own_note(
            session, tenant_id=patient.tenant_id, patient_id=patient_id, visit_id=visit_id
        )
        now = service.utcnow()
        return [
            link_out(row, decrypt_recipient(state, patient.tenant_id, dict(row.recipient)), now=now)
            for row in await links.doctor_links_for_note(
                session, tenant_id=patient.tenant_id, note_id=note.id
            )
        ]


@router.post(
    "/{link_id}/otp",
    response_model=DoctorLinkOtpOut,
    dependencies=[require_scopes(CORE_SCOPE, conditional=(SHARE_SCOPE,))],
)
async def mint_otp(
    visit_id: uuid.UUID, link_id: uuid.UUID, request: Request, principal: Principal, state: State
) -> DoctorLinkOtpOut:
    """Mint the opening code and hand it to the patient.

    This is the delivery channel that EXISTS. The channel files/10 §2 names —
    the phone or e-mail the patient chose — has no recorded destination in this
    repo and no contracted messaging vendor, so the public route refuses rather
    than faking one (``POST /v1/doctor-link/otp``). Both paths run the same
    INT-131 abuse gate, so the budget is one budget.
    """
    patient, patient_id = require_patient(principal)
    service = service_of(state)
    async with tenant_session(state.engine, patient.tenant_id) as session:
        _, note = await _own_note(
            session, tenant_id=patient.tenant_id, patient_id=patient_id, visit_id=visit_id
        )
        link = await _link_of_patient(
            session, tenant_id=patient.tenant_id, note_id=note.id, link_id=link_id
        )
        # minting an opening code is enabling a disclosure, so the share
        # purpose has to hold — unlike revoking, which a withdrawal must
        # never be able to lock
        await ensure_consent(
            session,
            state=state,
            tenant_id=patient.tenant_id,
            patient_id=patient_id,
            scope=SHARE_SCOPE,
            actor=patient.account_id,
        )
        require_live(link, now=service.utcnow())
    ip = request.client.host if request.client is not None else "unknown"
    retry_after = await service.gate(link_id=link_id, ip=ip, channel="patient")
    if retry_after is not None:
        record_event(DoctorLinkEvent.OTP_LIMITED)
        raise otp_limited(retry_after)
    code = await service.mint(link_id)
    record_event(DoctorLinkEvent.OTP_REQUESTED)
    return DoctorLinkOtpOut(
        code=code, expires_in_s=service.code_ttl_s, resend_after_s=service.resend_after_s
    )


@router.post(
    "/{link_id}/revoke", response_model=DoctorLinkOut, dependencies=[require_scopes(CORE_SCOPE)]
)
async def revoke_link(
    visit_id: uuid.UUID, link_id: uuid.UUID, principal: Principal, state: State
) -> DoctorLinkOut:
    """Instant revoke (files/10 §2). Idempotent: a second call changes nothing
    and writes no second audit entry, so the log says what happened once.

    Declared under ``core`` alone and NOT under the share purpose: a patient
    who withdrew consent to share must still be able to stop the sharing they
    already started. A refusal register a refusal can lock is not a refusal
    register (the INT-141 reasoning, applied here).
    """
    patient, patient_id = require_patient(principal)
    service = service_of(state)
    async with tenant_session(state.engine, patient.tenant_id) as session:
        _, note = await _own_note(
            session, tenant_id=patient.tenant_id, patient_id=patient_id, visit_id=visit_id
        )
        link = await _link_of_patient(
            session, tenant_id=patient.tenant_id, note_id=note.id, link_id=link_id
        )
        changed = await links.revoke_doctor_link(
            session, tenant_id=patient.tenant_id, link_id=link_id
        )
        # the routing hint goes too, so a revoked token stops resolving at all
        await service.forget(link.token_fingerprint)
        if changed:
            await state.audit.record(
                actor=patient.account_id,
                action="api.doctor_link.revoked",
                resource_ref=f"doctor_link:{link.id}",
                consent_scope=f"scope:{SHARE_SCOPE}",
            )
            record_event(DoctorLinkEvent.REVOKED)
        refreshed = await links.doctor_link_by_id(
            session, tenant_id=patient.tenant_id, link_id=link_id
        )
        if refreshed is None:  # pragma: no cover — read inside the same transaction
            raise not_found()
        return link_out(
            refreshed,
            decrypt_recipient(state, patient.tenant_id, dict(refreshed.recipient)),
            now=service.utcnow(),
        )


@router.get(
    "/access-log", response_model=list[AccessLogEntryOut], dependencies=[require_scopes(CORE_SCOPE)]
)
async def access_log(
    visit_id: uuid.UUID, principal: Principal, state: State
) -> list[AccessLogEntryOut]:
    """Every audited event about this note's sharing, as the patient sees it.

    The scope is built from the patient's OWN refs — the note, its shares and
    its links — and handed to the INT-016 projection, which renders a role
    rather than an identity and drops nothing it was given. This is the
    acceptance's "every open ... visible to patient".
    """
    patient, patient_id = require_patient(principal)
    async with tenant_session(state.engine, patient.tenant_id) as session:
        _, note = await _own_note(
            session, tenant_id=patient.tenant_id, patient_id=patient_id, visit_id=visit_id
        )
        rows = await links.doctor_links_for_note(
            session, tenant_id=patient.tenant_id, note_id=note.id
        )
    refs = {f"note:{note.id}"}
    refs |= {f"doctor_link:{row.id}" for row in rows}
    refs |= {f"share:{row.share_id}" for row in rows}
    return [
        AccessLogEntryOut(
            seq=row.seq,
            occurred_at_utc=row.occurred_at_utc,
            category=row.category.value,
            accessor_role=row.accessor_role.value,
            resource_ref=row.resource_ref,
            entry_hash=row.entry_hash,
        )
        for row in build_access_log(
            await state.audit.entries(), patient_refs=refs, role_of=accessor_role
        )
    ]

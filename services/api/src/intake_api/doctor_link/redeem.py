"""INT-150 — the CLINICIAN's Doctor Link surface (files/10 §2, §9).

The caller has no account. Four rules hold this surface together.

1. **The token never travels in a URL.** Both routes are POST and take the
   token in the body, so a credential cannot land in an access log, a Referer
   header, a browser history entry or a proxy trace (invariant 6). No path or
   query parameter in this package carries it, and a test asserts that over
   the live route table.
2. **The consent check does not disappear with the principal.** The token
   names a grant, the grant names a share, the share names the note and its
   patient — and ``ensure_consent`` runs against THAT patient before any
   section is read, through the same evaluator the clinic-admin path uses, so
   a withdrawal or a stale text refuses here too (invariant 4).
3. **Every open is audited before it is answered**, against
   ``doctor_link:<id>``, so the patient's access log names the grant they can
   revoke rather than an actor they cannot act on.
4. **The order of checks is the disclosure policy.** Token → OTP → state →
   consent → spend. A caller who cannot pass the OTP learns nothing about the
   grant's state, and a consent that has been withdrawn costs the patient no
   view from their budget.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from intake_platform.db.models import DoctorLink, Note, Share
from intake_platform.doctor_link import Watermark, token_fingerprint, token_matches

from intake_api import store
from intake_api.consent_guard import doctor_link_redemption, ensure_consent
from intake_api.db import tenant_session
from intake_api.doctor_link import store as links
from intake_api.doctor_link.common import (
    NOINDEX,
    aware,
    decrypt_recipient,
    no_index,
    require_live,
    service_of,
    shared_ids,
)
from intake_api.doctor_link.metrics import DoctorLinkEvent, record_event
from intake_api.doctor_link.schemas import DoctorLinkView, RedeemBody, TokenBody
from intake_api.doctor_link.service import (
    DoctorLinkService,
    RecipientChannelUnconfiguredError,
)
from intake_api.errors import (
    doctor_link_revoked,
    doctor_link_view_limit,
    not_found,
    otp_invalid,
    otp_limited,
)
from intake_api.notes import SHARE_SCOPE, decrypt_note_body
from intake_api.state import ApiState, State

__all__ = ["public_router"]

public_router = APIRouter(
    prefix="/v1/doctor-link", tags=["doctor-link"], dependencies=[Depends(no_index)]
)


def _delivery_unconfigured() -> HTTPException:
    return HTTPException(status_code=503, detail={"error": "doctor_link_delivery_unconfigured"})


async def _resolve(service: DoctorLinkService, token: str) -> tuple[uuid.UUID, uuid.UUID]:
    """Token → (tenant, link) through the Redis routing hint.

    A redemption arrives with no principal and therefore no tenant, and every
    clinical read runs inside a tenant-scoped RLS session; this is what makes
    that session openable. It is only a hint — the row's own fingerprint is
    re-checked in constant time by the caller.
    """
    ref = await service.resolve(token_fingerprint(token))
    if ref is None:
        record_event(DoctorLinkEvent.REFUSED_UNKNOWN_TOKEN)
        raise not_found()
    return ref.tenant_id, ref.link_id


@public_router.post("/otp", dependencies=[doctor_link_redemption()], status_code=202)
async def request_delivery(payload: TokenBody, request: Request, state: State) -> Response:
    """Ask for the opening code on the channel the PATIENT chose.

    The abuse gate runs BEFORE the delivery attempt, so the control is real the
    day a channel lands rather than written after it. Then the seam refuses:
    this repo records no patient-chosen destination (invariant 14 keeps contact
    identifiers out of every app table and no file records a Doctor-Link
    delivery preference) and no messaging vendor is contracted. A receipt for a
    message nobody sent would be a mock standing in for a control (CLAUDE.md
    invariant 17); the patient-side route mints the same code over the one
    channel that does exist.
    """
    service = service_of(state)
    tenant_id, link_id = await _resolve(service, payload.token)
    async with tenant_session(state.engine, tenant_id) as session:
        link = await links.doctor_link_by_id(session, tenant_id=tenant_id, link_id=link_id)
        if link is None or not token_matches(payload.token, link.token_fingerprint):
            record_event(DoctorLinkEvent.REFUSED_UNKNOWN_TOKEN)
            raise not_found()
        require_live(link, now=service.utcnow())
    ip = request.client.host if request.client is not None else "unknown"
    retry_after = await service.gate(link_id=link_id, ip=ip, channel="delivery")
    if retry_after is not None:
        record_event(DoctorLinkEvent.OTP_LIMITED)
        raise otp_limited(retry_after)
    # Deliver BEFORE remembering: a delivery that fails must not invalidate a
    # code the patient already minted and read out to the clinician in the room.
    code = service.generate_code()
    try:
        service.deliver(link_id=link_id, code=code)
    except RecipientChannelUnconfiguredError:
        raise _delivery_unconfigured() from None
    await service.remember(link_id, code)  # pragma: no cover — no channel exists yet
    record_event(DoctorLinkEvent.OTP_REQUESTED)  # pragma: no cover — no channel exists yet
    return Response(  # pragma: no cover — no channel exists yet
        status_code=202, headers={"X-Robots-Tag": NOINDEX}
    )


@public_router.post("/view", response_model=DoctorLinkView, dependencies=[doctor_link_redemption()])
async def open_link(payload: RedeemBody, state: State) -> DoctorLinkView:
    """Spend one opening; answer with the shared sections and the stamp."""
    service = service_of(state)
    tenant_id, link_id = await _resolve(service, payload.token)
    async with tenant_session(state.engine, tenant_id) as session:
        link = await links.doctor_link_by_id(session, tenant_id=tenant_id, link_id=link_id)
        if link is None or not token_matches(payload.token, link.token_fingerprint):
            record_event(DoctorLinkEvent.REFUSED_UNKNOWN_TOKEN)
            raise not_found()
        if not await service.check(link_id=link_id, code=payload.code):
            record_event(DoctorLinkEvent.OTP_FAILED)
            raise otp_invalid()
        now = service.utcnow()
        require_live(link, now=now)

        share = await session.get(Share, link.share_id)
        if share is None or share.revoked_at is not None:
            # the patient took the note back to draft, or re-sent it: the
            # grant this link hangs off no longer exists
            record_event(DoctorLinkEvent.REFUSED_REVOKED)
            raise doctor_link_revoked()
        note = await session.get(Note, share.note_id)
        visit = (
            None
            if note is None
            else await store.get_visit(session, tenant_id=tenant_id, visit_id=note.session_id)
        )
        if note is None or visit is None:  # pragma: no cover — FK-guaranteed
            raise not_found()

        await ensure_consent(
            session,
            state=state,
            tenant_id=tenant_id,
            patient_id=note.patient_id,
            scope=SHARE_SCOPE,
            actor=f"doctor_link:{link.id}",
        )
        admitted = await links.spend_one_view(
            session, tenant_id=tenant_id, link_id=link.id, now=now
        )
        if admitted is None:  # pragma: no cover — the race the guarded UPDATE closes
            refreshed = await links.doctor_link_by_id(session, tenant_id=tenant_id, link_id=link.id)
            require_live(refreshed if refreshed is not None else link, now=now)
            raise doctor_link_view_limit()

        view = _render(
            state, link=link, note=note, share=share, visit=visit, now=now, admitted=admitted
        )
        await state.audit.record(
            actor=f"doctor_link:{link.id}",
            action="api.doctor_link.opened",
            resource_ref=f"doctor_link:{link.id}",
            consent_scope=f"scope:{SHARE_SCOPE}",
        )
        record_event(DoctorLinkEvent.OPENED)
        return view


def _render(
    state: ApiState,
    *,
    link: DoctorLink,
    note: Note,
    share: Share,
    visit: store.VisitRecord,
    now: datetime,
    admitted: int,
) -> DoctorLinkView:
    """The answer: the sections the SHARE scopes on, and the stamp.

    The section filter reads ``shares.scope_sections`` and nothing else, so a
    link can never widen the share it hangs off, and the attribution flags come
    from the session that produced the note — a clinician must be able to tell
    an observed symptom from a reported one before they read a word of it
    (files/06 §6).
    """
    tenant_id = link.tenant_id
    body = decrypt_note_body(state, tenant_id, dict(note.payload))
    scope = shared_ids(dict(share.scope_sections))
    watermark = Watermark.compose(
        recipient=decrypt_recipient(state, tenant_id, dict(link.recipient)),
        viewed_at=now,
        link_id=link.id,
    )
    return DoctorLinkView(
        sections=[section for section in body.sections if section.id in scope],
        watermark_recipient=watermark.recipient,
        watermark_viewed_at_utc=watermark.viewed_at_utc,
        watermark_link_ref=watermark.link_ref,
        watermark_line=watermark.render(),
        view_index=admitted,
        views_remaining=max(link.view_limit - admitted, 0),
        expires_at=aware(link.expires_at),
        proxy_reported=visit.proxy_reported,
        third_party_present=visit.third_party_present,
        note_stale=visit.note_stale(now),
    )

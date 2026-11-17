"""Pre-visit note endpoints (INT-197): the buildNote shape over one
envelope-encrypted ``notes`` row per visit.

At rest the payload is a single EncryptedField envelope (invariant 14) over
``{"sections": [...], "scopes": {...}}``. Status is never stored in the
clear either — it is DERIVED: a live share means "sent", a note row without
one means "draft". Sending writes a ``shares`` row carrying only the
scoped-on section ids; re-saving revokes live shares first (the patient can
always take a note back to draft — sending is their call, 02 §5.1). The
clinic-admin account reads a note only through a live share, and only the
shared sections.
"""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter
from intake_platform.db.envelope_json import encrypted_field_from_json, encrypted_field_to_json
from sqlalchemy.ext.asyncio import AsyncSession

from intake_api import store
from intake_api.auth import Principal, require_patient
from intake_api.consent_guard import ensure_consent, require_scopes
from intake_api.db import tenant_session
from intake_api.dev_fixture import DevAccount
from intake_api.errors import not_found
from intake_api.previsit_output import record_previsit_output
from intake_api.schemas import NoteBody, NoteOut, NotePut
from intake_api.state import ApiState, State
from intake_api.visits import CORE_SCOPE

__all__ = ["SHARE_SCOPE", "decrypt_note_body", "router"]

router = APIRouter(prefix="/v1/visits/{visit_id}/note", tags=["notes"])

SHARE_SCOPE = "share:previsit_note"


def _encrypt_body(state: ApiState, tenant_id: uuid.UUID, body: NoteBody) -> dict[str, object]:
    plaintext = json.dumps(
        {"sections": [s.model_dump() for s in body.sections], "scopes": dict(body.scopes)},
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    field = state.cipher.encrypt_field(str(tenant_id), plaintext)
    return dict(encrypted_field_to_json(field))


def decrypt_note_body(
    state: ApiState, tenant_id: uuid.UUID, payload: dict[str, object]
) -> NoteBody:
    field = encrypted_field_from_json(payload)
    plaintext = state.cipher.decrypt_field(str(tenant_id), field)
    return NoteBody.model_validate(json.loads(plaintext.decode("utf-8")))


async def _own_visit(
    session: AsyncSession, principal: DevAccount, visit_id: uuid.UUID
) -> store.VisitRecord:
    record = await store.get_visit(
        session,
        tenant_id=principal.tenant_id,
        visit_id=visit_id,
        patient_id=principal.patient_id,
    )
    if record is None:
        raise not_found()
    return record


@router.get(
    "",
    response_model=NoteOut,
    dependencies=[require_scopes(CORE_SCOPE, conditional=(SHARE_SCOPE,))],
)
async def read_note(visit_id: uuid.UUID, principal: Principal, state: State) -> NoteOut:
    async with tenant_session(state.engine, principal.tenant_id) as session:
        record = await _own_visit(session, principal, visit_id)
        note = await store.get_note_row(session, tenant_id=principal.tenant_id, visit_id=visit_id)
        if note is None:
            raise not_found()
        share = await store.live_share(session, tenant_id=principal.tenant_id, note_id=note.id)

        if principal.role == "patient":
            # the route guard already enforced the patient's own core scope
            body = decrypt_note_body(state, principal.tenant_id, dict(note.payload))
            sections = body.sections
            scopes = body.scopes
            scope_checked = CORE_SCOPE
        else:
            # the clinic side sees a note only through a live share, and only
            # the sections the patient scoped on when sending
            if share is None:
                raise not_found()
            await ensure_consent(
                session,
                state=state,
                tenant_id=principal.tenant_id,
                patient_id=record.patient_id,
                scope=SHARE_SCOPE,
                actor=principal.account_id,
            )
            body = decrypt_note_body(state, principal.tenant_id, dict(note.payload))
            shared_ids = _shared_ids(share.scope_sections)
            sections = [s for s in body.sections if s.id in shared_ids]
            scopes = {sid: on for sid, on in body.scopes.items() if sid in shared_ids}
            scope_checked = SHARE_SCOPE

        await state.audit.record(
            actor=principal.account_id,
            action="api.note.read",
            resource_ref=f"note:{note.id}",
            consent_scope=f"scope:{scope_checked}",
        )
        return NoteOut(
            visit_id=visit_id,
            sections=list(sections),
            scopes=scopes,
            status="sent" if share is not None else "draft",
            # INT-133 / files/06 §6 — projected from the session, so the
            # clinician reading a shared note sees the same flag the visit
            # carries. Never stored a second time (it cannot drift).
            proxy_reported=record.proxy_reported,
            third_party_present=record.third_party_present,
            # INT-407 — files/02 §2b: whoever reads the note is told it is stale
            stale=record.note_stale(state.clock()),
        )


@router.put(
    "",
    response_model=NoteOut,
    dependencies=[require_scopes(CORE_SCOPE, conditional=(SHARE_SCOPE,))],
)
async def write_note(
    visit_id: uuid.UUID, payload: NotePut, principal: Principal, state: State
) -> NoteOut:
    patient, patient_id = require_patient(principal)
    async with tenant_session(state.engine, patient.tenant_id) as session:
        record = await _own_visit(session, patient, visit_id)

        note = await store.upsert_note(
            session,
            tenant_id=patient.tenant_id,
            visit_id=visit_id,
            patient_id=patient_id,
            payload=_encrypt_body(state, patient.tenant_id, payload),
        )
        await state.audit.record(
            actor=patient.account_id,
            action="api.note.write",
            resource_ref=f"note:{note.id}",
            consent_scope=f"scope:{CORE_SCOPE}",
        )

        # every save resets the share state: a draft save takes the note back
        # from the clinic side; a send publishes exactly the current scopes
        await store.revoke_live_shares(session, tenant_id=patient.tenant_id, note_id=note.id)
        sent = False
        if payload.status == "sent":
            await ensure_consent(
                session,
                state=state,
                tenant_id=patient.tenant_id,
                patient_id=patient_id,
                scope=SHARE_SCOPE,
                actor=patient.account_id,
            )
            share = await store.create_share(
                session,
                tenant_id=patient.tenant_id,
                note_id=note.id,
                section_ids=payload.shared_section_ids(),
                withheld_section_ids=payload.withheld_section_ids(),
            )
            await state.audit.record(
                actor=patient.account_id,
                action="api.note.share",
                resource_ref=f"share:{share.id}",
                consent_scope=f"scope:{SHARE_SCOPE}",
            )
            # Sending is what FINISHES a previsit here (02 §5.1: sending is the
            # patient's call), so this is where the frozen hospital-facing
            # output is produced — once, replacing any earlier one for this
            # visit. It is deliberately inside the `sent` branch: a draft is
            # not an output, and a save that takes the note back to draft
            # revokes the share above, which closes the read-back.
            await record_previsit_output(
                session,
                state=state,
                tenant_id=patient.tenant_id,
                visit=record,
                body=payload,
            )
            sent = True

        return NoteOut(
            visit_id=visit_id,
            sections=payload.sections,
            scopes=payload.scopes,
            status="sent" if sent else "draft",
            proxy_reported=record.proxy_reported,
            third_party_present=record.third_party_present,
            # INT-407: a send is a completed session, so its anchor is now and
            # the note is fresh; a draft save keeps the anchor it had
            stale=False if sent else record.note_stale(state.clock()),
        )


def _shared_ids(scope_sections: dict[str, object]) -> set[str]:
    ids = scope_sections.get("section_ids")
    if not isinstance(ids, list):
        return set()
    return {str(item) for item in ids}

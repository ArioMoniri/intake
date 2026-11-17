"""Visit endpoints (INT-197): list own / create / read, over sessions+slots.

Consent + audit (invariant 4): every route declares its ``core`` scope on
the consent_guard (INT-038), which enforces it for the requesting patient;
record-level checks (the clinic-admin reading a specific patient's rows) go
through the same ensure_consent evaluator, so text staleness refuses both
paths identically. Every disclosed read and every create appends a
hash-chained audit entry. The clinic-admin account reads only what belongs
to consented patients and can write nothing.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import cast

from fastapi import APIRouter
from intake_platform.consent import is_scope_allowed
from intake_platform.db.models import SessionAttribution
from intake_platform.profiles import Attribution
from intake_platform.visit_lifecycle import DELTA_SESSION_OFFER_FLAG
from sqlalchemy.ext.asyncio import AsyncSession

from intake_api import store
from intake_api.auth import Principal, require_patient
from intake_api.consent_guard import ensure_consent, require_scopes
from intake_api.db import tenant_session
from intake_api.dev_fixture import DevAccount
from intake_api.errors import not_found
from intake_api.schemas import (
    VisitCreate,
    VisitOut,
    VisitStateOut,
    resolved_attribution,
    validated_new_visit,
)
from intake_api.state import ApiState, State

__all__ = ["CORE_SCOPE", "router", "visit_out"]

router = APIRouter(prefix="/v1/visits", tags=["visits"])

CORE_SCOPE = "core"


def visit_out(record: store.VisitRecord, *, now: datetime, offer: bool) -> VisitOut:
    """The one projection of a visit record. ``offer`` is the
    ``delta_session_offer`` flag's value: the offer is shown only for a stale
    note AND an open flag, and the flag stays shut until the offer's copy is
    clinically reviewed (INT-407)."""
    lifecycle = record.lifecycle
    stale = record.note_stale(now)
    return VisitOut(
        id=record.id,
        hospital=record.hospital,
        department=record.department,
        branch_id=record.branch_id,
        visit_type=record.visit_type,
        date=record.date,
        # INT-306 — projected on every read, and None means "no producer stated
        # an hour" rather than "midnight" (files/02 §2b)
        time=record.time.render() if record.time is not None else None,
        time_source=record.time.source.value if record.time is not None else None,
        time_source_ref=record.time.source_ref if record.time is not None else None,
        note_status=record.note_status,
        # INT-133 / files/06 §6: on EVERY record read, not only the ones a
        # companion created — the projection is one place, so no read path
        # can forget the flag.
        proxy_reported=record.proxy_reported,
        third_party_present=record.third_party_present,
        # INT-407 — files/02 §2b, server-authoritative; the device reflects it
        state=cast(VisitStateOut, lifecycle.state.value),
        check_in_certain=lifecycle.check_in.certain if lifecycle.check_in is not None else None,
        note_stale=stale,
        delta_session_offered=stale and offer,
        red_resurface=list(lifecycle.red_resurface),
    )


def _offer(state: ApiState) -> bool:
    return state.flags.get_bool(DELTA_SESSION_OFFER_FLAG, False)


async def require_visit_consent(
    session: AsyncSession, state: ApiState, principal: DevAccount, patient_id: uuid.UUID
) -> None:
    """Record-level check for the paths the route guard cannot see (a
    non-subject principal reading a specific patient's rows) — same
    evaluator as the guard, so staleness refuses identically."""
    await ensure_consent(
        session,
        state=state,
        tenant_id=principal.tenant_id,
        patient_id=patient_id,
        scope=CORE_SCOPE,
        actor=principal.account_id,
    )


@router.get("", response_model=list[VisitOut], dependencies=[require_scopes(CORE_SCOPE)])
async def list_visits(principal: Principal, state: State) -> list[VisitOut]:
    async with tenant_session(state.engine, principal.tenant_id) as session:
        if principal.patient_id is not None:
            # the route guard already enforced the patient's own core scope
            records = await store.list_visits(
                session, tenant_id=principal.tenant_id, patient_id=principal.patient_id
            )
            resource_ref = f"patient:{principal.patient_id}"
        else:
            # clinic admin: tenant-wide, but only visits of consented patients
            all_records = await store.list_visits(
                session, tenant_id=principal.tenant_id, patient_id=None
            )
            consented: dict[uuid.UUID, bool] = {}
            for record in all_records:
                if record.patient_id not in consented:
                    consented[record.patient_id] = await is_scope_allowed(
                        session,
                        tenant_id=principal.tenant_id,
                        patient_id=record.patient_id,
                        scope=CORE_SCOPE,
                        catalog=state.consent_catalog,
                    )
            records = [r for r in all_records if consented[r.patient_id]]
            resource_ref = f"tenant:{principal.tenant_id}"
        await state.audit.record(
            actor=principal.account_id,
            action="api.visit.list",
            resource_ref=resource_ref,
            consent_scope=f"scope:{CORE_SCOPE}",
        )
        now = state.clock()
        offer = _offer(state)
        return [visit_out(r, now=now, offer=offer) for r in records]


@router.post(
    "", response_model=VisitOut, status_code=201, dependencies=[require_scopes(CORE_SCOPE)]
)
async def create_visit(payload: VisitCreate, principal: Principal, state: State) -> VisitOut:
    patient, patient_id = require_patient(principal)
    loaded = state.taxonomy()
    visit = validated_new_visit(payload, loaded.taxonomy if loaded is not None else None)
    # INT-133: derived by the platform rules engine, refused (422) when a
    # companion has not acknowledged the role. Never asserted by the client.
    attribution = resolved_attribution(payload.attribution)
    async with tenant_session(state.engine, patient.tenant_id) as session:
        visit_id = await store.create_visit(
            session,
            tenant_id=patient.tenant_id,
            patient_id=patient_id,
            hospital=visit.hospital,
            department=visit.department,
            date=visit.date,
            time=visit.time,
            branch_id=visit.branch_id,
            visit_type=visit.visit_type,
            attribution=SessionAttribution(attribution.attribution.value),
            third_party_present=attribution.third_party_present,
            # both companion attributions passed the acknowledgement gate to
            # get here; a self-report session never took it, so it records no
            # instant rather than a misleading one
            proxy_ack_at=(
                datetime.now(UTC)
                if attribution.attribution is not Attribution.SELF_REPORT
                else None
            ),
        )
        await state.audit.record(
            actor=patient.account_id,
            action="api.visit.create",
            resource_ref=f"visit:{visit_id}",
            consent_scope=f"scope:{CORE_SCOPE}",
        )
    return VisitOut(
        id=visit_id,
        hospital=visit.hospital,
        department=visit.department,
        branch_id=visit.branch_id,
        visit_type=visit.visit_type,
        date=visit.date,
        time=visit.time.render() if visit.time is not None else None,
        time_source=visit.time.source.value if visit.time is not None else None,
        time_source_ref=visit.time.source_ref if visit.time is not None else None,
        note_status=None,
        proxy_reported=attribution.proxy_reported,
        third_party_present=attribution.third_party_present,
    )


@router.get("/{visit_id}", response_model=VisitOut, dependencies=[require_scopes(CORE_SCOPE)])
async def read_visit(visit_id: uuid.UUID, principal: Principal, state: State) -> VisitOut:
    async with tenant_session(state.engine, principal.tenant_id) as session:
        record = await store.get_visit(
            session,
            tenant_id=principal.tenant_id,
            visit_id=visit_id,
            patient_id=principal.patient_id,
        )
        if record is None:
            raise not_found()
        await require_visit_consent(session, state, principal, record.patient_id)
        await state.audit.record(
            actor=principal.account_id,
            action="api.visit.read",
            resource_ref=f"visit:{record.id}",
            consent_scope=f"scope:{CORE_SCOPE}",
        )
        return visit_out(record, now=state.clock(), offer=_offer(state))

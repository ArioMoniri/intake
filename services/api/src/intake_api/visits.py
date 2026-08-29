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

from fastapi import APIRouter
from intake_platform.consent import is_scope_allowed
from sqlalchemy.ext.asyncio import AsyncSession

from intake_api import store
from intake_api.auth import Principal, require_patient
from intake_api.consent_guard import ensure_consent, require_scopes
from intake_api.db import tenant_session
from intake_api.dev_fixture import DevAccount
from intake_api.errors import not_found
from intake_api.schemas import VisitCreate, VisitOut, validated_new_visit
from intake_api.state import ApiState, State

__all__ = ["router"]

router = APIRouter(prefix="/v1/visits", tags=["visits"])

CORE_SCOPE = "core"


def _to_out(record: store.VisitRecord) -> VisitOut:
    return VisitOut(
        id=record.id,
        hospital=record.hospital,
        department=record.department,
        branch_id=record.branch_id,
        visit_type=record.visit_type,
        date=record.date,
        note_status=record.note_status,
    )


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
        return [_to_out(r) for r in records]


@router.post(
    "", response_model=VisitOut, status_code=201, dependencies=[require_scopes(CORE_SCOPE)]
)
async def create_visit(payload: VisitCreate, principal: Principal, state: State) -> VisitOut:
    patient, patient_id = require_patient(principal)
    loaded = state.taxonomy()
    visit = validated_new_visit(payload, loaded.taxonomy if loaded is not None else None)
    async with tenant_session(state.engine, patient.tenant_id) as session:
        visit_id = await store.create_visit(
            session,
            tenant_id=patient.tenant_id,
            patient_id=patient_id,
            hospital=visit.hospital,
            department=visit.department,
            date=visit.date,
            branch_id=visit.branch_id,
            visit_type=visit.visit_type,
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
        note_status=None,
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
        return _to_out(record)

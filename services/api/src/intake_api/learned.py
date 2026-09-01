"""INT-170 — ``/v1/me/learned``: *Me → Hakkımda öğrendikleri* (files/09 §3).

The patient's own view of what the system has learned about them, and the
surface through which they confirm it, re-confirm it, re-scope it and delete
it. files/09 §3 requires all four: *"every learned fact shows 'where from' and
can be corrected or deleted by the patient in Me → Hakkımda öğrendikleri; per-
field share scope; a fact older than 12 months is re-confirmed before use."*

**Consent (invariant 4).** A learned fact is clinical data about the patient,
so every route here declares ``core`` and is enforced by the ONE
``ensure_consent`` path — no marker, no exemption. A withdrawn ``core`` closes
the surface exactly as it closes ``/v1/visits``; a refused read is not a read
and is not audited. Every read and every change that *does* happen appends a
hash-chained audit entry naming ids and nothing else (invariant 6).

**Confirmation (invariant 12).** The request body carries **no ``source``
field**. A patient principal establishes a patient provenance, and the two
provenances a patient can establish are the whole ``FactOrigin`` vocabulary —
so ``clinician_accepted_note`` is unspellable over this route rather than
filtered out of it. That provenance is established by note acceptance on the
clinician surface, against the same store.

**The twelve-month window** is
:func:`~clinical_schemas.overlay.fact_needs_reconfirmation` and is not
re-derived here: the route calls it to tell the patient which facts need
re-confirming, which is the only place a duration appears in this feature at
all.

sec_row: `learning-loops`.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime

from clinical_schemas.common import JsonValue, Ref
from clinical_schemas.overlay import (
    CONFIRMING_ACTOR,
    Confirmation,
    FactCandidate,
    LearnedFact,
    LearnedFactSource,
    fact_needs_reconfirmation,
)
from fastapi import APIRouter, Response
from intake_platform.overlay import OverlayStore
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from intake_api.auth import Principal, require_patient
from intake_api.consent_guard import require_scopes
from intake_api.db import tenant_session
from intake_api.errors import not_found
from intake_api.state import ApiState, State
from intake_api.visits import CORE_SCOPE

__all__ = ["FactOrigin", "LearnedFactOut", "LearnedOut", "router"]

router = APIRouter(prefix="/v1/me/learned", tags=["learned"])


class FactOrigin(enum.StrEnum):
    """What a PATIENT may confirm, and therefore the whole vocabulary this
    route accepts (files/09 §3: the in-app confirmation card and the confirmed
    import). The clinician provenance is established by note acceptance, so it
    has no member here — a body asking for it is a 422 from the schema, not a
    rejection from a guard (invariant 12)."""

    INTAKE_EXTRACTION = "intake_extraction"
    IMPORTED_RECORD = "imported_record"


#: Total over :class:`FactOrigin` by construction, and every value maps to a
#: source whose confirming actor is the patient.
_SOURCE_OF: dict[FactOrigin, LearnedFactSource] = {
    FactOrigin.INTAKE_EXTRACTION: LearnedFactSource.CONFIRMED_INTAKE_EXTRACTION,
    FactOrigin.IMPORTED_RECORD: LearnedFactSource.CONFIRMED_IMPORTED_RECORD,
}


class ConfirmIn(BaseModel):
    """One in-app confirmation card, answered.

    ``extra="forbid"`` is load-bearing here rather than habitual: it is what
    makes a smuggled ``source`` a 422 instead of an ignored field.
    """

    model_config = ConfigDict(extra="forbid")

    key: Ref
    value: JsonValue
    origin: FactOrigin
    origin_ref: Ref
    source_ref: Ref
    observed_at: AwareDatetime
    confidence: float = Field(ge=0, le=1)

    def candidate(self) -> FactCandidate:
        return FactCandidate(
            key=self.key,
            value=self.value,
            origin_ref=self.origin_ref,
            observed_at=self.observed_at,
            confidence=self.confidence,
        )

    def confirmation(self, *, confirmed_at: datetime) -> Confirmation:
        return Confirmation(
            source=_SOURCE_OF[self.origin],
            source_ref=self.source_ref,
            confirmed_at=confirmed_at,
        )


class ShareIn(BaseModel):
    """Per-field share scope (files/09 §3 guardrails)."""

    model_config = ConfigDict(extra="forbid")

    shared: bool


class LearnedFactOut(BaseModel):
    """One fact with its provenance — the "where from" files/09 §3 promises."""

    model_config = ConfigDict(extra="forbid")

    key: str
    value: JsonValue
    source: LearnedFactSource
    source_ref: str
    confirmed_by: str
    confirmed_at: AwareDatetime
    confidence: float
    shared: bool
    needs_reconfirmation: bool


class LearnedOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    facts: list[LearnedFactOut]


def _to_out(fact: LearnedFact, *, now: datetime) -> LearnedFactOut:
    return LearnedFactOut(
        key=fact.key,
        value=fact.value,
        source=fact.source,
        source_ref=fact.source_ref,
        confirmed_by=CONFIRMING_ACTOR[fact.source].value,
        confirmed_at=fact.confirmed_at,
        confidence=fact.confidence,
        shared=fact.shared,
        # the ONE window (files/09 §3), shared with decide_delta and
        # activate_overlays — shown so the patient can act on it
        needs_reconfirmation=fact_needs_reconfirmation(fact, now),
    )


def _store(state: ApiState) -> OverlayStore:
    return OverlayStore(state.cipher)


async def _render(
    session: AsyncSession, state: ApiState, *, tenant_id: uuid.UUID, patient_id: uuid.UUID
) -> LearnedOut:
    store = _store(state)
    now = datetime.now(UTC)
    facts = await store.list_facts(session, tenant_id=tenant_id, patient_id=patient_id)
    return LearnedOut(
        version=await store.version(session, tenant_id=tenant_id, patient_id=patient_id),
        facts=[_to_out(fact, now=now) for fact in facts],
    )


@router.get("", response_model=LearnedOut, dependencies=[require_scopes(CORE_SCOPE)])
async def read_learned(principal: Principal, state: State) -> LearnedOut:
    """The overlay as the patient sees it. Patient-only: the overlay is
    patient-owned (files/09 §3), and the clinic side sees a shared NOTE, never
    the learning object behind it."""
    patient, patient_id = require_patient(principal)
    async with tenant_session(state.engine, patient.tenant_id) as session:
        payload = await _render(session, state, tenant_id=patient.tenant_id, patient_id=patient_id)
        await state.audit.record(
            actor=patient.account_id,
            action="api.learned.read",
            resource_ref=f"patient:{patient_id}",
            consent_scope=f"scope:{CORE_SCOPE}",
        )
        return payload


@router.post(
    "", response_model=LearnedOut, status_code=201, dependencies=[require_scopes(CORE_SCOPE)]
)
async def confirm_learned(body: ConfirmIn, principal: Principal, state: State) -> LearnedOut:
    """Answer a confirmation card: the candidate becomes a fact, or an
    existing fact is re-confirmed and its twelve-month clock restarts."""
    patient, patient_id = require_patient(principal)
    async with tenant_session(state.engine, patient.tenant_id) as session:
        await _store(state).confirm_fact(
            session,
            tenant_id=patient.tenant_id,
            patient_id=patient_id,
            candidate=body.candidate(),
            confirmation=body.confirmation(confirmed_at=datetime.now(UTC)),
        )
        await state.audit.record(
            actor=patient.account_id,
            action="api.learned.confirm",
            resource_ref=f"patient:{patient_id}",
            consent_scope=f"scope:{CORE_SCOPE}",
        )
        return await _render(session, state, tenant_id=patient.tenant_id, patient_id=patient_id)


@router.patch("/{key}", response_model=LearnedFactOut, dependencies=[require_scopes(CORE_SCOPE)])
async def rescope_learned(
    key: str, body: ShareIn, principal: Principal, state: State
) -> LearnedFactOut:
    """Turn one fact's share scope on or off (files/09 §3: per-field)."""
    patient, patient_id = require_patient(principal)
    store = _store(state)
    async with tenant_session(state.engine, patient.tenant_id) as session:
        if not await store.set_shared(
            session,
            tenant_id=patient.tenant_id,
            patient_id=patient_id,
            key=key,
            shared=body.shared,
        ):
            raise not_found()
        await state.audit.record(
            actor=patient.account_id,
            action="api.learned.rescope",
            resource_ref=f"patient:{patient_id}",
            consent_scope=f"scope:{CORE_SCOPE}",
        )
        facts = await store.list_facts(session, tenant_id=patient.tenant_id, patient_id=patient_id)
    now = datetime.now(UTC)
    return next(_to_out(fact, now=now) for fact in facts if fact.key == key)


@router.delete("/{key}", status_code=204, dependencies=[require_scopes(CORE_SCOPE)])
async def forget_learned(key: str, principal: Principal, state: State) -> Response:
    """Delete one fact. files/09 §3: the patient can correct or delete
    anything the system learned about them."""
    patient, patient_id = require_patient(principal)
    async with tenant_session(state.engine, patient.tenant_id) as session:
        if not await _store(state).forget_fact(
            session, tenant_id=patient.tenant_id, patient_id=patient_id, key=key
        ):
            raise not_found()
        await state.audit.record(
            actor=patient.account_id,
            action="api.learned.forget",
            resource_ref=f"patient:{patient_id}",
            consent_scope=f"scope:{CORE_SCOPE}",
        )
    return Response(status_code=204)

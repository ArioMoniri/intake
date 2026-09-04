"""Demo route: a logged-in patient's upcoming visits, pulled from the Acibadem
appointments feed after OTP verification.

This is the read side of the connector INT-160/INT-161 framework wired to the
auth tier. The OTP is the authentication; this runs after it, on a phone the
OTP tier has already verified, and re-checks that the submitted phone tokenizes
to the *caller's own* pseudonym before anything leaves the process — so a
patient can never learn another patient's visits by submitting their number
(invariant 14: the raw phone is used transiently, never stored). The feed read
is a clinical-data read and clears a consent scope first (invariant 4).
"""

from __future__ import annotations

import datetime as dt
import os

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from intake_connectors.acibadem import ADAPTER_ID, AcibademAppointmentsClient
from intake_connectors.credentials import EnvCredentialResolver
from intake_connectors.identity import normalise_tr_msisdn
from intake_connectors.sources import ClinicalSource
from intake_platform.db.models import Consent, Patient

from intake_api.auth import Principal, require_patient
from intake_api.db import tenant_session
from intake_api.otp import normalise_tr_phone
from intake_api.state import State

router = APIRouter(prefix="/v1/visits", tags=["visits"])

#: The read clears this scope before the feed is touched (invariant 4). It is a
#: closed-registry purpose that a docs/legal text binds.
READ_SCOPE = "core"


class SyncBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phone: str


class VisitOut(BaseModel):
    id: str
    hospital: str
    department: str
    branchId: str | None = None
    visitType: str | None = None
    date: str | None
    time: str | None = None
    noteStatus: str | None = None


class VisitsOut(BaseModel):
    outcome: str
    patient_name: str | None = None
    visits: list[VisitOut]


def _source(tenant_id: str) -> ClinicalSource:
    base = os.environ["ACIBADEM_BASE_URL"]
    hostport = base.split("://", 1)[1]
    host, port = hostport.split(":")
    return ClinicalSource(
        source_id="acibadem-demo",
        tenant_id=tenant_id,
        adapter_id=ADAPTER_ID,
        address=host,
        port=int(port),
        protocol="http",
        base_path="",
        consent_scope=READ_SCOPE,
        credential_ref="connectors/acibadem",
        dpa_ref="demo-dpa",
        approval_ref="demo-approval",
        plaintext_approval="demo-lan-plaintext",
    )


def _client(tenant_id: str) -> AcibademAppointmentsClient:
    return AcibademAppointmentsClient(
        source=_source(tenant_id),
        credentials=EnvCredentialResolver({"connectors/acibadem": {"api_key": "ACIBADEM_API_KEY"}}),
    )


@router.post("/sync", response_model=VisitsOut)
async def sync(payload: SyncBody, principal: Principal, state: State) -> VisitsOut:
    patient, patient_id = require_patient(principal)
    if state.auth is None:
        return VisitsOut(outcome="unavailable", visits=[])

    normalised = normalise_tr_phone(payload.phone)
    if normalised is None:
        return VisitsOut(outcome="phone_invalid", visits=[])

    # Ownership: the phone must belong to THIS caller. Tokenise it the same way
    # the OTP tier does and require the row it names to be the caller's own.
    pseudonym = state.auth._tokenizer.pseudonym(normalised)
    async with tenant_session(state.engine, patient.tenant_id) as session:
        owner = (
            await session.scalars(
                select(Patient).where(
                    Patient.tenant_id == patient.tenant_id,
                    Patient.pseudonym == pseudonym,
                )
            )
        ).first()
        if owner is None or owner.id != patient_id:
            return VisitsOut(outcome="not_your_number", visits=[])
        granted = (
            await session.scalars(
                select(Consent.scope).where(
                    Consent.tenant_id == patient.tenant_id,
                    Consent.patient_id == patient_id,
                    Consent.scope == READ_SCOPE,
                    Consent.revoked_at.is_(None),
                )
            )
        ).first()
        if granted is None:
            return VisitsOut(outcome="consent_required", visits=[])

    feed_phone = normalise_tr_msisdn(payload.phone)
    client = _client(str(patient.tenant_id))
    match = next((u for u in client.upcoming() if u.msisdn == feed_phone), None)
    if match is None:
        return VisitsOut(outcome="no_appointment", visits=[])

    display_name = " ".join(
        part.strip() for part in (match.patient_name, match.patient_surname) if part and part.strip()
    ).title() or None

    today = dt.date.today()
    visits: list[VisitOut] = []
    for a in client.appointments_for(match.patient_number):
        if a.app_date < today:
            continue
        visits.append(
            VisitOut(
                id=f"acb-{a.patient_number}-{a.app_date.isoformat()}-{a.randevu_saati.strftime('%H%M')}",
                hospital=a.facility_name,
                department=a.specialty_name,
                date=a.app_date.isoformat(),
                time=a.randevu_saati.strftime("%H:%M"),
                noteStatus=None,
            )
        )
    visits.sort(key=lambda v: (v.date or "", v.time or ""))
    return VisitsOut(
        outcome="matched" if visits else "no_upcoming",
        patient_name=display_name,
        visits=visits,
    )

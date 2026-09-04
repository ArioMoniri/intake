"""INT-318 — a logged-in patient's upcoming visits, read from the Acıbadem
appointments feed right after OTP verification.

This is the read side of the INT-160/INT-161 connector framework wired to the
auth tier, and it is the one missing piece between a working OTP login and the
"Bugün" screen showing a real visit. The OTP is the authentication; this runs
after it, on a phone the OTP tier has already verified.

Three properties this route is responsible for, each an invariant:

* **Ownership (invariant 14).** The submitted phone must tokenize to *this*
  caller's own pseudonym — the same normalisation + tokenisation the OTP tier
  keyed the account by — before anything leaves the process. A patient can
  therefore never learn another patient's visits by submitting their number,
  and the raw phone is used transiently and never written to an app table.
* **Consent (invariant 4).** The feed read is a clinical-data read, so the
  ``core`` scope is declared and enforced at the door via ``require_scopes``
  (INT-038: staleness and the INT-223 age/guardian gate are handled by the one
  evaluator), and every disclosure is written to the hash-chained audit. NOTE:
  ``core`` is a **dev-tier stand-in** — "reading a patient's hospital record"
  is arguably a distinct INT-038 purpose that ``docs/legal/`` does not yet bind
  (HB-L27). The mechanism gates and audits correctly; the canonical
  purpose is awaiting-human.
* **No first-match guess.** Identity resolution is delegated to the connector's
  :func:`resolve_identity`, which returns a *terminal* ``refused_ambiguous``
  when a phone maps to more than one patient and no TC settles it. A shared
  handset therefore surfaces as a clean "couldn't identify you", never one
  patient's visits shown to the other.

The client is injected (``state.acibadem``) so the unit lane drives it over an
``httpx.MockTransport`` and never touches the network; production builds it from
``ACIBADEM_BASE_URL`` + ``ACIBADEM_API_KEY`` (no in-code default), and the read
still passes the LanSourcePolicy runtime gate (``INTAKE_ALLOW_LAN_SOURCE``).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os
from collections.abc import Iterable
from typing import Literal
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter
from intake_connectors.acibadem import (
    ADAPTER_ID,
    AcibademAppointmentsClient,
    AcibademUpstreamError,
    Appointment,
    UpcomingPatient,
)
from intake_connectors.credentials import EnvCredentialResolver
from intake_connectors.identity import IdentityOutcome, normalise_tr_msisdn, resolve_identity
from intake_connectors.sources import ClinicalSource
from intake_platform.db.models import Patient
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from intake_api.auth import Principal, require_patient
from intake_api.consent_guard import require_scopes
from intake_api.db import tenant_session
from intake_api.state import State

__all__ = ["acibadem_client_from_env", "router"]

router = APIRouter(prefix="/v1/visits", tags=["visits"])

#: The scope the read clears before the feed is touched (invariant 4). A
#: dev-tier stand-in on the seed grants — see the module docstring and HB-L27.
READ_SCOPE = "core"

#: The demo-tier credential reference. Its material is delivered as an
#: environment variable through EnvCredentialResolver (invariant 14: no value
#: in code, and an unset/empty var is a missing credential, never a default).
_CREDENTIAL_REF = "connectors/acibadem-demo/api-key"


#: A stable, non-PHI id for one appointment row: a hash-free composite of the
#: hospital-side identifier, the date and the clock time, so the two same-day
#: visits (13:00 and 13:05) stay distinct and a re-login does not churn ids.
def _visit_id(row: Appointment) -> str:
    clock = row.randevu_saati.strftime("%H%M")
    return f"acb-{row.patient_number}-{row.app_date.isoformat()}-{clock}"


def _today() -> dt.date:
    """Seam so a test can pin the upcoming/past boundary (the connector passes
    ``today`` for the same reason); production reads the clock."""
    return dt.date.today()


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
    #: A closed vocabulary, safe to log: matched | no_upcoming | no_appointment
    #: | ambiguous | not_your_number | phone_invalid | unavailable.
    outcome: str
    #: The matched patient's display name, read explicitly off the redacted
    #: feed row (invariant 6: it is never logged from here).
    patient_name: str | None = None
    visits: list[VisitOut]


def acibadem_client_from_env() -> AcibademAppointmentsClient | None:
    """Build the demo-tier client from the environment, or ``None`` when it is
    not configured (the route then answers ``unavailable`` — fail closed).

    ``None`` rather than a raise on an unset ``ACIBADEM_BASE_URL`` mirrors every
    other optional tier (auth, documents, admin): an unconfigured connector is a
    deployment state, not a crash.
    """
    base = os.environ.get("ACIBADEM_BASE_URL")
    if not base:
        return None
    parts = urlsplit(base)
    if parts.scheme not in ("http", "https") or parts.hostname is None or parts.port is None:
        return None
    protocol: Literal["http", "https"] = "http" if parts.scheme == "http" else "https"
    source = ClinicalSource(
        source_id="acibadem-demo",
        tenant_id="acibadem-demo",
        adapter_id=ADAPTER_ID,
        address=parts.hostname,
        port=parts.port,
        protocol=protocol,
        base_path=parts.path.rstrip("/"),
        consent_scope=READ_SCOPE,
        credential_ref=_CREDENTIAL_REF,
        # Dev-tier binding refs: the production sources.yaml row needs a signed
        # DPA and recorded tier-3 approvals no agent may mint (HB-L27), so this
        # is the runtime stand-in, not a committed registration.
        dpa_ref="dev-acibadem-dpa",
        approval_ref="dev-acibadem-approval",
        plaintext_approval="dev-acibadem-plaintext" if protocol == "http" else None,
    )
    return AcibademAppointmentsClient(
        source=source,
        credentials=EnvCredentialResolver({_CREDENTIAL_REF: {"api_key": "ACIBADEM_API_KEY"}}),
    )


def _display_name(rows: Iterable[UpcomingPatient], patient_number: str) -> str | None:
    for row in rows:
        if row.patient_number == patient_number:
            name = " ".join(
                part.strip()
                for part in (row.patient_name, row.patient_surname)
                if part and part.strip()
            ).title()
            return name or None
    return None


@router.post("/sync", response_model=VisitsOut, dependencies=[require_scopes(READ_SCOPE)])
async def sync(payload: SyncBody, principal: Principal, state: State) -> VisitsOut:
    patient, patient_id = require_patient(principal)
    client = state.acibadem
    if state.auth is None or client is None:
        # Without the OTP tokenizer the ownership check cannot run, and without
        # a client there is nothing to read: fail closed, gracefully empty.
        return VisitsOut(outcome="unavailable", visits=[])

    pseudonym = state.auth.pseudonym_for(payload.phone)
    if pseudonym is None:
        return VisitsOut(outcome="phone_invalid", visits=[])

    # Ownership (invariant 14): the phone must tokenize to the caller's own
    # pseudonym. Anyone else's number resolves to a different pseudonym (or
    # none), so this returns before a single byte reaches the feed.
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

    # Consent (invariant 4) was enforced at the door by require_scopes(core):
    # a stale or absent grant, or an age/guardian refusal, is a 403 before here.

    feed_phone = normalise_tr_msisdn(payload.phone)
    if feed_phone is None:  # pragma: no cover - pseudonym check already proved it
        return VisitsOut(outcome="phone_invalid", visits=[])

    # One directory read, then the connector's terminal-on-ambiguous matcher —
    # never a first-match guess (that is the shared-handset leak this avoids).
    try:
        rows = tuple(await asyncio.to_thread(client.upcoming))
    except (httpx.HTTPError, AcibademUpstreamError):
        # A blip on the hospital feed degrades to an honest empty result,
        # never a 500 that breaks the whole login / home flow.
        return VisitsOut(outcome="upstream_unavailable", visits=[])
    resolution = resolve_identity((row.as_candidate() for row in rows), phone=feed_phone, tckn=None)

    # Invariant 4: the disclosure is audited with ids only — the resolved
    # hospital-side patient_number when matched, the app patient id otherwise.
    await state.audit.record(
        actor=f"patient:{patient_id}",
        action="api.visit.acibadem.sync",
        resource_ref=(
            f"acibadem:{resolution.patient_number}"
            if resolution.patient_number is not None
            else f"patient:{patient_id}"
        ),
        consent_scope=f"scope:{READ_SCOPE}",
    )

    if resolution.outcome is not IdentityOutcome.MATCHED or resolution.patient_number is None:
        # NO_MATCH → this number has no record; NEEDS_TCKN / REFUSED_AMBIGUOUS →
        # a shared handset the feed cannot disambiguate → a clean refusal that
        # shows neither patient's visits.
        outcome = (
            "no_appointment" if resolution.outcome is IdentityOutcome.NO_MATCH else "ambiguous"
        )
        return VisitsOut(outcome=outcome, visits=[])

    patient_number = resolution.patient_number
    display_name = _display_name(rows, patient_number)
    try:
        appointments = await asyncio.to_thread(client.appointments_for, patient_number)
    except (httpx.HTTPError, AcibademUpstreamError):
        return VisitsOut(outcome="upstream_unavailable", visits=[])
    today = _today()
    visits = [
        VisitOut(
            id=_visit_id(a),
            hospital=a.facility_name,
            department=a.specialty_name,
            date=a.app_date.isoformat(),
            time=a.randevu_saati.strftime("%H:%M"),
            noteStatus=None,
        )
        for a in appointments
        if a.app_date >= today
    ]
    visits.sort(key=lambda v: (v.date or "", v.time or ""))
    return VisitsOut(
        outcome="matched" if visits else "no_upcoming",
        patient_name=display_name,
        visits=visits,
    )

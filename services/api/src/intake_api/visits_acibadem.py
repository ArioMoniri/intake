"""INT-318 — a logged-in patient's upcoming visits, read from the Acıbadem
appointments feed right after OTP verification.

This is the read side of the INT-160/INT-161 connector framework wired to the
auth tier. The OTP is the authentication; this route runs after it, on a phone
the OTP tier has already verified.

**The source row comes from ``infra/connectors/sources.yaml`` and from nowhere
else** (audit 2026-09-26 F06, §6 item 8). The file ships with zero rows, so the
shipped state wires no client and the route answers ``unavailable`` without a
byte leaving the process. This module holds no binding reference, no
credential reference, no address and no purpose of its own: the signed
agreement, the tier-3 approval, the plaintext decision and the consent purpose
are facts a named human records in that row (HUMAN_BLOCKERS HB-A15, HB-A5,
HB-L27), and the schema in :mod:`intake_connectors.sources` refuses a row that
lacks one. The credential the row names is read from OpenBao (invariant 14).

What the route is responsible for, each an invariant:

* **Consent (invariant 4).** ``core`` is declared and enforced at the door by
  ``require_scopes``, as on every other ``/v1/visits`` route. The read itself
  then clears the purpose the registered row names, through the same one
  ``ensure_consent`` evaluator (staleness and the INT-223 age gate included),
  so a service consent alone never unlocks a hospital record. Every disclosure
  is written to the hash-chained audit under that purpose, with ids only.
* **Tenant.** A row serves the patients of the tenant it is registered for and
  no other; a caller in any other tenant gets ``unavailable``.
* **Ownership (invariant 14).** The submitted phone must tokenize to *this*
  caller's own pseudonym — the normalisation and tokenisation the OTP tier
  keyed the account by — before anything leaves the process, so a patient can
  never learn another patient's visits by submitting their number, and the
  raw phone is used transiently and never written to an app table.
* **No first-match guess.** Identity goes through the connector's
  :func:`resolve_identity`, whose ``refused_ambiguous`` is terminal: a shared
  handset surfaces as a clean "couldn't identify you", never one patient's
  visits shown to the other.
* **Fail closed, never a 500.** No row, a row for another tenant, the
  ``INTAKE_ALLOW_LAN_SOURCE`` runtime gate off, or a credential OpenBao does
  not hold → ``unavailable``. A dropped link, a timeout or a non-200 from the
  hospital → ``upstream_unavailable``. Both are 200 with no visits, which the
  mobile client renders as an empty home screen rather than a broken login.

The client is injected (``state.acibadem``), so the unit lane drives it over an
``httpx.MockTransport`` and never dials the network.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from collections.abc import Callable, Iterable
from pathlib import Path

import httpx
import yaml
from fastapi import APIRouter
from intake_connectors.acibadem import (
    ADAPTER_ID,
    AcibademAppointmentsClient,
    AcibademUpstreamError,
    Appointment,
    UpcomingPatient,
)
from intake_connectors.credentials import CredentialMissing, OpenBaoCredentialResolver
from intake_connectors.identity import IdentityOutcome, normalise_tr_msisdn, resolve_identity
from intake_connectors.sources import (
    ClinicalSource,
    SourceRegistry,
    SourceRegistryError,
    load_sources,
)
from intake_platform.consent.registry import CORE
from intake_platform.db.models import Patient
from intake_platform.egress import EgressDenied
from intake_platform.secrets import SecretsBootError, SecretsProvider
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from intake_api.auth import Principal, require_patient
from intake_api.consent_guard import ensure_consent, require_scopes
from intake_api.db import tenant_session
from intake_api.state import State

__all__ = ["acibadem_client_from_registry", "registered_source", "router"]

logger = logging.getLogger("intake_api")

router = APIRouter(prefix="/v1/visits", tags=["visits"])


def _visit_id(row: Appointment) -> str:
    """A stable, non-PHI id for one appointment row: the hospital-side
    identifier, the date and the clock time, so the two same-day visits
    (13:00 and 13:05) stay distinct and a re-login does not churn ids."""
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
    #: | ambiguous | not_your_number | phone_invalid | unavailable
    #: | upstream_unavailable.
    outcome: str
    #: The matched patient's display name, read explicitly off the redacted
    #: feed row (invariant 6: it is never logged from here).
    patient_name: str | None = None
    visits: list[VisitOut]


# --- the registry is the only way in ------------------------------------------------------


def registered_source(registry: SourceRegistry) -> ClinicalSource | None:
    """The one row registered for the Acıbadem adapter, or ``None``.

    Zero rows is the shipped state. More than one is refused rather than
    chosen between: which hospital a patient's phone is sent to must not
    depend on file order, and a client serves exactly one row.
    """
    rows = [row for row in registry.rows if row.adapter_id == ADAPTER_ID]
    if len(rows) > 1:
        logger.warning(
            "clinical read source refused: %d rows name adapter %s and exactly one may",
            len(rows),
            ADAPTER_ID,
        )
        return None
    return rows[0] if rows else None


def acibadem_client_from_registry(path: Path) -> AcibademAppointmentsClient | None:
    """Build the client from the registry file, or ``None`` (fail closed).

    ``None`` — and ``/v1/visits/sync`` answering ``unavailable`` — when the
    file holds no Acıbadem row (as shipped), holds more than one, cannot be
    read, or holds a row its own schema refuses (a plaintext transport without
    a recorded decision, a purpose outside the closed registry, a hostname in
    place of a private literal). OpenBao is consulted only once a row exists,
    and an unconfigured OpenBao wires nothing rather than a client whose every
    call would fail at the credential. Log lines carry no path content and no
    value (invariant 6).
    """
    try:
        registry = load_sources(path)
    except (OSError, ValueError, SourceRegistryError, yaml.YAMLError):
        logger.warning("clinical read sources unconfigured: the registry is absent or invalid")
        return None
    source = registered_source(registry)
    if source is None:
        return None
    try:
        provider = SecretsProvider.from_env()
    except SecretsBootError:
        logger.warning(
            "clinical read source %s unconfigured: OpenBao is not configured", source.source_id
        )
        return None
    return AcibademAppointmentsClient(
        source=source, credentials=OpenBaoCredentialResolver(provider)
    )


# --- the route ----------------------------------------------------------------------------


class _FeedClosed(Exception):
    """A feed read that ended without data; ``outcome`` is the closed code."""

    def __init__(self, outcome: str) -> None:
        super().__init__(outcome)
        self.outcome = outcome


async def _read[T](call: Callable[..., T], *args: str) -> T:
    """One upstream read off the event loop, with every non-answer typed.

    A refusal by this deployment — the operator's runtime gate is off, or the
    credential the row names is not in OpenBao — is ``unavailable``: the
    hospital was never asked. A failure at the hospital's end is
    ``upstream_unavailable``. Neither is a 500.
    """
    try:
        return await asyncio.to_thread(call, *args)
    except (EgressDenied, CredentialMissing):
        logger.warning("clinical read refused before sending: runtime gate or credential absent")
        raise _FeedClosed("unavailable") from None
    except (httpx.HTTPError, AcibademUpstreamError):
        raise _FeedClosed("upstream_unavailable") from None


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


@router.post("/sync", response_model=VisitsOut, dependencies=[require_scopes(CORE)])
async def sync(payload: SyncBody, principal: Principal, state: State) -> VisitsOut:
    patient, patient_id = require_patient(principal)
    client = state.acibadem
    if state.auth is None or client is None:
        # Without the OTP tokenizer the ownership check cannot run, and without
        # a registered row there is nothing to read: fail closed, empty.
        return VisitsOut(outcome="unavailable", visits=[])
    source = client.source
    if source.tenant_id != str(patient.tenant_id):
        # The row serves the tenant it is registered for and no other.
        return VisitsOut(outcome="unavailable", visits=[])

    pseudonym = state.auth.pseudonym_for(payload.phone)
    if pseudonym is None:
        return VisitsOut(outcome="phone_invalid", visits=[])

    async with tenant_session(state.engine, patient.tenant_id) as session:
        # Ownership (invariant 14): the phone must tokenize to the caller's own
        # pseudonym. Anyone else's number resolves to a different pseudonym (or
        # none), so this returns before a single byte reaches the feed.
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
        # Consent (invariant 4): the read clears the purpose the registered row
        # names, on top of the core scope the door already enforced.
        await ensure_consent(
            session,
            state=state,
            tenant_id=patient.tenant_id,
            patient_id=patient_id,
            scope=source.consent_scope,
            actor=principal.account_id,
        )

    feed_phone = normalise_tr_msisdn(payload.phone)
    if feed_phone is None:  # pragma: no cover - the pseudonym check already proved it
        return VisitsOut(outcome="phone_invalid", visits=[])

    # One directory read, then the connector's terminal-on-ambiguous matcher —
    # never a first-match guess (that is the shared-handset leak this avoids).
    try:
        rows = await _read(client.upcoming)
    except _FeedClosed as closed:
        return VisitsOut(outcome=closed.outcome, visits=[])
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
        consent_scope=f"scope:{source.consent_scope}",
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
        appointments = await _read(client.appointments_for, patient_number)
    except _FeedClosed as closed:
        return VisitsOut(outcome=closed.outcome, visits=[])
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

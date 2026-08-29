"""INT-240 — satisfaction ingestion: CSAT per session, NPS per account.

Acceptance: *"csat.v1 (1-5 + reason enum + optional text), nps.v1,
clinician_pulse.v1; POST /sessions/{id}/csat, /feedback/nps; rollups in
services/metrics"*. The event schemas already exist (INT-031,
``clinical_schemas.events``); this module is the write path for two of them and
nothing here redefines a shape.

**The split, and why it is the whole design.** A satisfaction comment is
patient-authored free text about a hospital visit, so it will carry symptoms
and names — the `experience` threat row calls this out as threat [I], "patient
typed free text carrying identifiers into analytics". ``events.payload`` is
declared id-shaped and PHI-free because the rollups and the admin console read
it. So a response is written as two rows: the score and the reason into
``events`` (analysable, PHI-free, unchanged declaration), the sentence into
``csat_texts`` behind field-level envelope encryption (invariant 14). The
rollup path never joins the second table and the projection it reads through
has no text field at all, so a fragment cannot reach an aggregate even if a
future payload acquired one.

Before the envelope closes, the files/10 §3 redaction baseline runs over the
text — the threat row's own control line, *"redaction baseline (§3) applied to
free-text ingestion"*. It removes the structured identifiers that have no
business in a satisfaction comment (TCKN, TR mobile, IBAN). Names are NER
territory and stay, which is exactly why the column is encrypted rather than
merely filtered.

**Consent** is ``satisfaction`` (files/06 §2, açık rıza, default OFF) on both
routes, declared on the route so ``unguarded_data_routes`` stays empty and
enforced through the single ``ensure_consent`` path — no second evaluator.

**What this module deliberately does not do.** No survey cadence, no sampling
rate and no prompt schedule: the acceptance names two POST routes and the
blueprint states no cadence, so nothing is invented here (INT-242 owns
"NPS scheduling + clinician pulse survey cadence"). ``clinician_pulse.v1`` has
a schema and a rollup but no ingest route for the same reason — the acceptance
enumerates exactly two.
"""

from __future__ import annotations

import uuid

from clinical_schemas.events import ClinicianPulseV1, CsatReason, CsatV1, NpsV1
from fastapi import APIRouter
from intake_platform.db.envelope_json import encrypted_field_to_json
from intake_platform.db.models import CsatText, Event, IntakeSession
from intake_platform.redaction import redact_text
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from intake_api.auth import Principal, require_patient
from intake_api.consent_guard import require_scopes
from intake_api.db import tenant_session
from intake_api.errors import not_found
from intake_api.state import ApiState, State

__all__ = ["SATISFACTION_SCOPE", "CsatIn", "CsatOut", "NpsIn", "NpsOut", "router"]

router = APIRouter(prefix="/v1", tags=["satisfaction"])

SATISFACTION_SCOPE = "satisfaction"

#: The longest comment the csat.v1 schema accepts. Mirrored here so the
#: boundary refuses before anything is decrypted, hashed or stored.
MAX_TEXT_LEN = 500


class CsatIn(BaseModel):
    """The wire body. Tenant and session come from the principal and the path,
    never from the client, so the event this builds cannot be aimed elsewhere."""

    model_config = ConfigDict(extra="forbid")

    score: int = Field(ge=1, le=5)
    reason: CsatReason
    text: str | None = Field(default=None, max_length=MAX_TEXT_LEN)


class CsatOut(BaseModel):
    """Acknowledgement only. Echoing the comment back would put it into every
    client log and crash report on the way home (invariant 6)."""

    session_id: uuid.UUID
    recorded: bool


class NpsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: int = Field(ge=0, le=10)


class NpsOut(BaseModel):
    recorded: bool


def _event_payload(event: CsatV1 | NpsV1 | ClinicianPulseV1) -> dict[str, object]:
    """The row body: the validated event MINUS anything free-text.

    ``exclude`` rather than a hand-built dict, so a future field on the schema
    has to be considered here instead of silently flowing into a column that
    promises to be PHI-free.
    """
    payload = event.model_dump(mode="json", exclude={"text"})
    return dict(payload)


async def _own_session(
    session: AsyncSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID, session_id: uuid.UUID
) -> None:
    """404 unless the session is this patient's own. Not 403: whether a session
    id exists at all is not something an unrelated caller may learn."""
    found = await session.scalar(
        select(IntakeSession.id).where(
            IntakeSession.id == session_id,
            IntakeSession.tenant_id == tenant_id,
            IntakeSession.patient_id == patient_id,
        )
    )
    if found is None:
        raise not_found()


def _sealed_comment(state: ApiState, tenant_id: uuid.UUID, text: str) -> dict[str, object]:
    """Redaction baseline, then the envelope. In that order: a wrapped
    identifier is still an identifier the moment the field is opened."""
    redacted = redact_text(text)
    field = state.cipher.encrypt_field(str(tenant_id), redacted.encode("utf-8"))
    return dict(encrypted_field_to_json(field))


@router.post(
    "/sessions/{session_id}/csat",
    response_model=CsatOut,
    status_code=201,
    dependencies=[require_scopes(SATISFACTION_SCOPE)],
)
async def record_csat(
    session_id: uuid.UUID, payload: CsatIn, principal: Principal, state: State
) -> CsatOut:
    patient, patient_id = require_patient(principal)
    event = CsatV1(
        tenant_id=patient.tenant_id,
        session_id=session_id,
        score=payload.score,
        reason=payload.reason,
        text=payload.text,
    )
    comment = (event.text or "").strip()
    async with tenant_session(state.engine, patient.tenant_id) as session:
        await _own_session(
            session,
            tenant_id=patient.tenant_id,
            patient_id=patient_id,
            session_id=session_id,
        )
        row = Event(
            tenant_id=patient.tenant_id,
            session_id=session_id,
            event_type="csat.v1",
            payload=_event_payload(event),
        )
        session.add(row)
        if comment:
            # flush so the text row can carry the event's key: the cascade that
            # makes the 06 §3 satisfaction clock reach the comment needs it
            await session.flush()
            session.add(
                CsatText(
                    tenant_id=patient.tenant_id,
                    session_id=session_id,
                    event_id=row.id,
                    payload=_sealed_comment(state, patient.tenant_id, comment),
                )
            )
        await state.audit.record(
            actor=patient.account_id,
            action="api.csat.record",
            resource_ref=f"session:{session_id}",
            consent_scope=f"scope:{SATISFACTION_SCOPE}",
        )
    return CsatOut(session_id=session_id, recorded=True)


@router.post(
    "/feedback/nps",
    response_model=NpsOut,
    status_code=201,
    dependencies=[require_scopes(SATISFACTION_SCOPE)],
)
async def record_nps(payload: NpsIn, principal: Principal, state: State) -> NpsOut:
    """NPS is account-level, not visit-level (files/08 §4 group F
    ``nps.monthly``), so the row carries no session link — nothing to join a
    score to a particular consultation with. nps.v1 has no text field, and
    ``extra="forbid"`` on the body means one cannot be smuggled in."""
    patient, _ = require_patient(principal)
    event = NpsV1(tenant_id=patient.tenant_id, score=payload.score)
    async with tenant_session(state.engine, patient.tenant_id) as session:
        session.add(
            Event(
                tenant_id=patient.tenant_id,
                session_id=None,
                event_type="nps.v1",
                payload=_event_payload(event),
            )
        )
        await state.audit.record(
            actor=patient.account_id,
            action="api.nps.record",
            resource_ref=f"tenant:{patient.tenant_id}",
            consent_scope=f"scope:{SATISFACTION_SCOPE}",
        )
    return NpsOut(recorded=True)

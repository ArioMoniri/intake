"""GET /v1/me/access-log — the patient's own access log (INT-016; KVKK-12,
KSVY-7).

The view model, the classification rules and the ownership/suppression
predicates live in :mod:`intake_platform.access_log`; this module is the API
shape over them — the route, its consent gate, and the one query that turns a
patient id into the closed set of resource refs the log is allowed to cover.

**Why this route enforces a consent scope while the DSAR routes do not.** The
DSAR surface is the exercise of a statutory right whose basis is legal
obligation, so gating it on explicit consent would let a withdrawal lock the
very request the withdrawal provokes. This is a different thing: a standing
product surface reading clinical METADATA — which records exist, when they were
touched, by whom — and invariant 4 says every read of clinical data checks a
consent scope. So it declares ``core``, the purpose the record itself is kept
under (files/06 §2). A patient who has withdrawn ``core`` and still wants the
log has the m.11 route, which is where that request belongs.

**Ownership is enforced in the query.** :func:`owned_resource_refs` builds the
ref set from the subject's own rows inside the tenant session; the source is
asked for that set and returns nothing outside it. A caller cannot widen the
view because there is no parameter through which to widen it — the route takes
no patient id at all, only the principal's.

**The read audits itself, write-ahead.** files/10 §2 orders the break-glass
audit BEFORE the read, and an access log is where that ordering matters most:
an enumeration that fails midway must still have left its trace. The entry it
writes is suppressed from the subject's own view in the query
(``intake_platform.access_log.SELF_READ_ACTION``), so the log does not grow by
being looked at while the chain still records every look.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Query
from intake_platform.access_log import (
    SELF_READ_ACTION,
    AccessKind,
    AccessLogQuery,
    ActorKind,
    RecordKind,
    project,
)
from intake_platform.db.models import (
    Consent,
    Document,
    DsarRectification,
    DsarRequest,
    IntakeSession,
    Note,
    Share,
)
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from intake_api.auth import Principal, require_patient
from intake_api.consent_guard import require_scopes
from intake_api.db import tenant_session
from intake_api.errors import service_unconfigured
from intake_api.state import State

__all__ = ["AccessLogEntryOut", "AccessLogOut", "owned_resource_refs", "router"]

CORE_SCOPE = "core"

#: Newest-first page size. Bounded because the response is rendered on a phone
#: and because an unbounded ``IN`` list is a denial of service shaped like a
#: feature.
DEFAULT_LIMIT = 50
MAX_LIMIT = 200

router = APIRouter(prefix="/v1/me/access-log", tags=["access-log"])


class AccessLogEntryOut(BaseModel):
    """One line of the patient's log. Closed vocabularies, id-shaped refs and
    ``tr`` keys — the client renders the Turkish (invariant 5); nothing here is
    copy and nothing here is free text (invariant 6)."""

    seq: int
    occurred_at: str
    actor_kind: ActorKind
    actor_role: str | None
    access_kind: AccessKind
    record_kind: RecordKind
    record_ref: str
    basis_ref: str
    actor_tr_key: str
    access_tr_key: str
    record_tr_key: str


class AccessLogOut(BaseModel):
    entries: list[AccessLogEntryOut]
    limit: int
    truncated: bool


async def owned_resource_refs(
    session: AsyncSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID
) -> tuple[str, ...]:
    """Every ``<kind>:<id>`` the chain may name that belongs to this subject.

    One SELECT per owning table, each predicated on ``patient_id`` AND
    ``tenant_id`` (belt and braces beside RLS — and the only isolation the
    SQLite unit lane has, which is the INT-197 store layer's rule), plus the
    subject's own ``patient:<id>``, the ref every account-level action is
    recorded against. Shares hang off the note rather than the patient, so
    they join through it. ``visit:`` and ``session:`` are two ref spellings of
    the same ``sessions`` row and both are emitted, because both appear in the
    chain today.

    Completeness, stated rather than assumed: a ref shape not listed here is
    invisible to the patient, which NARROWS the view and can never widen it.
    Adding a patient-owned table means adding it here — the alternative, a
    prefix-and-hope match on the ref string, would let one malformed ref hand
    a patient somebody else's row.
    """
    refs = {f"patient:{patient_id}"}
    session_ids = (
        await session.scalars(
            select(IntakeSession.id).where(
                IntakeSession.tenant_id == tenant_id, IntakeSession.patient_id == patient_id
            )
        )
    ).all()
    refs.update(f"visit:{value}" for value in session_ids)
    refs.update(f"session:{value}" for value in session_ids)

    refs.update(
        f"note:{value}"
        for value in await session.scalars(
            select(Note.id).where(Note.tenant_id == tenant_id, Note.patient_id == patient_id)
        )
    )
    refs.update(
        f"doc:{value}"
        for value in await session.scalars(
            select(Document.id).where(
                Document.tenant_id == tenant_id, Document.patient_id == patient_id
            )
        )
    )
    refs.update(
        f"consent:{value}"
        for value in await session.scalars(
            select(Consent.id).where(
                Consent.tenant_id == tenant_id, Consent.patient_id == patient_id
            )
        )
    )
    refs.update(
        f"dsar-request:{value}"
        for value in await session.scalars(
            select(DsarRequest.id).where(
                DsarRequest.tenant_id == tenant_id, DsarRequest.patient_id == patient_id
            )
        )
    )
    refs.update(
        f"dsar-rectification:{value}"
        for value in await session.scalars(
            select(DsarRectification.id).where(
                DsarRectification.tenant_id == tenant_id,
                DsarRectification.patient_id == patient_id,
            )
        )
    )
    refs.update(
        f"share:{value}"
        for value in await session.scalars(
            select(Share.id)
            .join(Note, Share.note_id == Note.id)
            .where(Share.tenant_id == tenant_id, Note.patient_id == patient_id)
        )
    )
    return tuple(sorted(refs))


@router.get("", response_model=AccessLogOut, dependencies=[require_scopes(CORE_SCOPE)])
async def read_access_log(
    principal: Principal,
    state: State,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> AccessLogOut:
    patient, patient_id = require_patient(principal)
    source = state.access_log
    if source is None:
        # no reader wired: refuse rather than answer "nothing happened", which
        # is the one wrong answer a transparency surface can give
        raise service_unconfigured("access_log_unconfigured")

    # write-ahead (files/10 §2): the read is recorded before it happens
    await state.audit.record(
        actor=patient.account_id,
        action=SELF_READ_ACTION,
        resource_ref=f"patient:{patient_id}",
        consent_scope=f"scope:{CORE_SCOPE}",
    )

    async with tenant_session(state.engine, patient.tenant_id) as session:
        refs = await owned_resource_refs(
            session, tenant_id=patient.tenant_id, patient_id=patient_id
        )

    # one over the page size, so truncation is observed rather than assumed
    query = AccessLogQuery(resource_refs=refs, subject_actor=patient.account_id, limit=limit + 1)
    entries = await asyncio.to_thread(source.fetch, query)
    truncated = len(entries) > limit
    rows = project(entries[:limit], subject_actor=patient.account_id, roles=state.actor_roles)
    return AccessLogOut(
        entries=[AccessLogEntryOut(**asdict(row)) for row in rows],
        limit=limit,
        truncated=truncated,
    )

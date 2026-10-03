"""The previsit OUTPUT store and the hospital read-back (owner directive).

*"after the previsit is done write output version of json which is worked on
in a sql in the data folder under intake and the acibadem side will then send
a request there to get the previsit details of json for that patient with the
same structure"* — two halves, and the second one is the hard one.

**Half one, the write.** Sending the note is what finishes a previsit in this
slice (files/02 §5.1: sending is the patient's call), so that is where the
output is produced: one ``previsit_outputs`` row per completed previsit,
holding a frozen :class:`~clinical_schemas.previsit_output.PreVisitOutput`
inside an EncryptedField envelope (invariant 14). A draft save produces
nothing — a document the patient has not sent is not an output — and a resend
replaces the row rather than appending, so "the finished previsit" stays
singular.

**Half two, the read.** A hospital fetching a previsit is a **share of
clinical data to another organisation**, not a read, so invariant 4 applies in
full: a consent scope is checked per patient per fetch, and the disclosure is
written to the hash-chained audit log before it is answered. Five gates stand
between a caller and a document, and the ORDER of them is the disclosure
policy:

1. **an approved reader** — ``intake_platform.previsit_output``, whose
   committed registry has zero rows. No DPA is executed and no reader is
   approved, so today this refuses everybody (503);
2. **a tokenization key** — without one a hospital patient number cannot be
   turned into the pseudonym that addresses a patient, and guessing is not an
   option (invariant 14). 503, never a scan;
3. **a patient** — the number is tokenized and matched against
   ``patients.pseudonym``; no match is a 404;
4. **consent** — ``share:previsit_output`` for THAT patient, through the one
   evaluator ``intake_api.consent_guard.ensure_consent``, so a withdrawal or a
   stale text refuses here exactly as it does on every other path. This runs
   BEFORE the output row is looked up, so an unconsented caller cannot learn
   whether a previsit exists;
5. **a live share** — the patient's own send. Scope lives on
   ``shares.scope_sections`` and is read from there, so a fetch can never widen
   what was sent, and taking the note back to draft closes the read-back.

**Why ``share:previsit_output`` and not ``share:previsit_note``.** files/06 §2
makes ``share`` a parameterised family precisely so that a share consent names
its recipient; a bare ``share`` is not grantable. ``share:previsit_note`` is
the patient handing one note to one clinician through a link they can revoke.
Handing the whole finished previsit to a hospital information system that will
keep it under its own retention is a materially different disclosure, and
answering the second with a grant given for the first is the bundled consent
files/06 §2 forbids. So it is a second parameter of the same family — which
needs no new text file (a ``share:<qualifier>`` scope binds to the ``share``
family text) and no registry change.

**Nothing can actually be served today, and that is deliberate.** The
``share`` açık rıza text does not exist (HB-L27 — docs/legal is empty, so
``grant_consent`` refuses every new grant), no dev seed grants this scope, and
the recipient registry is empty. The mechanism is wired and fails closed at
three independent points.

**Authentication is the honest gap.** The caller is authenticated as the
clinic side through :func:`~intake_api.auth.require_admin` — the same door
``notes.read_note``'s clinic-admin branch uses, and the same rule that the
tenant a caller may read is the tenant on their own principal, never one they
name. That door is real but it is a *human* door: it resolves through the
INT-197 dev bearer today and through INT-180's OIDC console tomorrow, and
neither is a machine-to-machine credential a hospital integration engine can
present. This module does not invent one. See the branch report.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from typing import Annotated

from clinical_schemas.previsit_output import (
    PREVISIT_OUTPUT_SCHEMA_ID,
    NotEvaluatedReason,
    OutputSection,
    PreVisitOutput,
    TriageNotEvaluated,
)
from fastapi import APIRouter
from intake_platform.db.envelope_json import encrypted_field_from_json, encrypted_field_to_json
from intake_platform.db.models import IntakeSession, Patient, PreVisitOutputRow
from intake_platform.previsit_output import (
    HospitalRecipient,
    RecipientNotRegistered,
    RecipientRegistryError,
)
from intake_platform.tokenization import Tokenizer
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from intake_api import store
from intake_api.auth import Principal, require_admin
from intake_api.consent_guard import ensure_consent, require_scopes
from intake_api.db import tenant_session
from intake_api.errors import (
    not_found,
    previsit_output_recipient_unregistered,
    previsit_output_unconfigured,
)
from intake_api.schemas import NoteBody
from intake_api.state import ApiState, State

__all__ = [
    "PREVISIT_OUTPUT_SCOPE",
    "FetchBody",
    "PreVisitOutputFetched",
    "record_previsit_output",
    "router",
]

#: files/06 §2's parameterised share family, with the hospital-system
#: recipient as the parameter. Distinct from ``share:previsit_note``.
PREVISIT_OUTPUT_SCOPE = "share:previsit_output"

router = APIRouter(prefix="/v1/previsit-output", tags=["previsit-output"])

# A hospital patient number is short and alphanumeric (Acıbadem's is eight
# characters). The grammar is here so a malformed one is refused at the
# boundary; the VALUE is never echoed, because the app-wide validation handler
# strips ``input``/``ctx`` from every 422 (invariant 6).
PatientNumber = Annotated[
    str, StringConstraints(min_length=4, max_length=32, pattern=r"^[A-Za-z0-9]+$")
]


class FetchBody(BaseModel):
    """The number travels in the BODY, never in a path or a query.

    This is the Doctor Link rule applied to the other credential-shaped value
    on this surface: a direct identifier in a URL lands in every access log,
    Referer header, browser history entry and proxy trace (invariant 6). A
    test over the live route table asserts no path parameter exists here.
    """

    model_config = ConfigDict(extra="forbid")

    patient_number: PatientNumber = Field(
        description="The hospital's own key for this patient — echoed back so the "
        "receiver can join without guessing, and stored nowhere."
    )


class PreVisitOutputFetched(BaseModel):
    """What the hospital gets: its own key, a stable ref, and the document."""

    patient_number: str = Field(description="Echoed from the request; this row holds no copy.")
    output_ref: str = Field(
        description="Stable id of the disclosed previsit — the same ref the audit entry "
        "names, so a patient's access log and the receiver's record agree."
    )
    output: PreVisitOutput = Field(description="The finished previsit, shared sections only.")


# --- half one: producing the output ------------------------------------------------------


def _canonical(document: PreVisitOutput) -> bytes:
    """The bytes the digest covers: sorted keys, no incidental whitespace.

    Field order is a serialiser's choice; a content identity that changed when
    a field moved would tell a receiver a previsit had changed when it had
    not.
    """
    return json.dumps(
        json.loads(document.model_dump_json()),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _document(
    *,
    visit: store.VisitRecord,
    session_row: IntakeSession,
    body: NoteBody,
    completed_at: datetime,
) -> PreVisitOutput:
    """Build the finished document from what this slice actually has.

    ``triage`` is the one field that could be filled in by guessing, and is
    not. The note path runs no rules engine, so the document says
    ``not_evaluated`` in as many words rather than omitting the field (which
    reads as GREEN) or deriving a level from anything an LLM produced
    (invariant 1). ``measurements`` is empty for the same reason: the note
    sections are prose here, and a magnitude parsed out of a line would be a
    number this system invented (invariant 22).
    """
    return PreVisitOutput(
        schema_version=PREVISIT_OUTPUT_SCHEMA_ID,
        visit_ref=str(visit.id),
        completed_at=completed_at,
        locale=session_row.locale,
        protocol_id=session_row.protocol_id,
        protocol_version=session_row.protocol_version,
        proxy_reported=visit.proxy_reported,
        third_party_present=visit.third_party_present,
        sections=tuple(
            OutputSection(id=section.id, title_tr=section.title, lines=tuple(section.lines))
            for section in body.sections
        ),
        triage=TriageNotEvaluated(reason=NotEvaluatedReason.RULES_ENGINE_NOT_ON_THIS_PATH),
    )


async def record_previsit_output(
    session: AsyncSession,
    *,
    state: ApiState,
    tenant_id: uuid.UUID,
    visit: store.VisitRecord,
    body: NoteBody,
) -> PreVisitOutputRow:
    """Write (or replace) the finished previsit for this visit.

    Called from ``notes.write_note`` on a SEND and nowhere else: this is the
    completion event in this slice. The full document is stored and the
    section scope is NOT copied here — it stays on ``shares.scope_sections``,
    so a later re-scope changes what is served without a second row having to
    be kept in step.
    """
    session_row = await session.get(IntakeSession, visit.id)
    if session_row is None:  # pragma: no cover — the visit was just resolved
        raise not_found()
    document = _document(
        visit=visit,
        session_row=session_row,
        body=body,
        # the API's one clock (INT-407): this instant is also the note's
        # staleness anchor, so it must be the clock staleness is read against
        completed_at=state.clock(),
    )
    plaintext = _canonical(document)
    envelope = dict(encrypted_field_to_json(state.cipher.encrypt_field(str(tenant_id), plaintext)))
    digest = hashlib.sha256(plaintext).hexdigest()

    row = (
        await session.scalars(
            select(PreVisitOutputRow).where(
                PreVisitOutputRow.tenant_id == tenant_id,
                PreVisitOutputRow.session_id == visit.id,
            )
        )
    ).first()
    if row is None:
        row = PreVisitOutputRow(
            tenant_id=tenant_id,
            session_id=visit.id,
            patient_id=visit.patient_id,
            schema_version=PREVISIT_OUTPUT_SCHEMA_ID,
            payload=envelope,
            payload_sha256=digest,
            completed_at=document.completed_at,
        )
        session.add(row)
    else:
        row.schema_version = PREVISIT_OUTPUT_SCHEMA_ID
        row.payload = envelope
        row.payload_sha256 = digest
        row.completed_at = document.completed_at
    await session.flush()
    return row


# --- half two: serving it ----------------------------------------------------------------


def _recipient(state: ApiState, tenant_id: uuid.UUID) -> HospitalRecipient:
    """The approved reader for this tenant, or a fail-closed 503.

    A registry that cannot be read is the same answer as a registry with no
    matching row: this surface does not serve on an assumption.
    """
    try:
        registry = state.previsit_output_recipients()
        return registry.for_tenant(tenant_id)
    except (RecipientRegistryError, RecipientNotRegistered):
        raise previsit_output_recipient_unregistered() from None


async def _patient_by_number(
    session: AsyncSession, *, tenant_id: uuid.UUID, tokenizer: Tokenizer, number: str
) -> uuid.UUID | None:
    """The hospital's key → the pseudonymised patient row (invariant 14).

    Every configured key id is tried, not only the active one: a pseudonym
    carries the generation it was signed under, so after a key rotation the
    rows written before it still resolve rather than silently reading as an
    unknown patient.

    This is the interface the inbound match path has to satisfy: a patient row
    for an Acıbadem-tenant patient must carry
    ``Tokenizer.pseudonym(patient_number)`` as its pseudonym.
    """
    candidates = [tokenizer.pseudonym(number, key_id) for key_id in tokenizer.key_ids]
    stmt = select(Patient.id).where(
        Patient.tenant_id == tenant_id, Patient.pseudonym.in_(candidates)
    )
    return (await session.scalars(stmt)).first()


def _decrypt(state: ApiState, tenant_id: uuid.UUID, row: PreVisitOutputRow) -> PreVisitOutput:
    field = encrypted_field_from_json(dict(row.payload))
    plaintext = state.cipher.decrypt_field(str(tenant_id), field)
    return PreVisitOutput.model_validate_json(plaintext.decode("utf-8"))


def _shared_ids(scope_sections: dict[str, object]) -> set[str]:
    ids = scope_sections.get("section_ids")
    if not isinstance(ids, list):
        return set()
    return {str(item) for item in ids}


@router.post(
    "/fetch",
    response_model=PreVisitOutputFetched,
    dependencies=[require_scopes(conditional=(PREVISIT_OUTPUT_SCOPE,))],
)
async def fetch_previsit_output(
    payload: FetchBody, principal: Principal, state: State
) -> PreVisitOutputFetched:
    """Answer one hospital's request for one patient's finished previsit.

    The scope is declared ``conditional`` because the caller is not a data
    subject: the route guard has no patient to resolve at the door, so the
    check moves inside, against the patient the number resolves to. That is
    the same record-level shape ``notes.read_note`` and the Doctor Link
    redemption already use, and it goes through the same one evaluator.
    """
    caller = require_admin(principal)
    recipient = _recipient(state, caller.tenant_id)
    tokenizer = state.tokenizer
    if tokenizer is None:
        raise previsit_output_unconfigured()

    actor = f"recipient:{recipient.recipient_id}"
    async with tenant_session(state.engine, caller.tenant_id) as session:
        patient_id = await _patient_by_number(
            session,
            tenant_id=caller.tenant_id,
            tokenizer=tokenizer,
            number=payload.patient_number,
        )
        if patient_id is None:
            raise not_found()

        # Invariant 4, before anything about this patient's previsit is read —
        # including whether one exists.
        await ensure_consent(
            session,
            state=state,
            tenant_id=caller.tenant_id,
            patient_id=patient_id,
            scope=PREVISIT_OUTPUT_SCOPE,
            actor=actor,
        )

        row = (
            await session.scalars(
                select(PreVisitOutputRow)
                .where(
                    PreVisitOutputRow.tenant_id == caller.tenant_id,
                    PreVisitOutputRow.patient_id == patient_id,
                )
                .order_by(PreVisitOutputRow.completed_at.desc())
            )
        ).first()
        if row is None:
            # No stored previsit is a 404, never an empty document: a shell
            # with no sections reads as "the patient told us nothing".
            raise not_found()

        note = await store.get_note_row(
            session, tenant_id=caller.tenant_id, visit_id=row.session_id
        )
        share = (
            None
            if note is None
            else await store.live_share(session, tenant_id=caller.tenant_id, note_id=note.id)
        )
        if share is None:
            # The patient never sent it, took it back to draft, or the share
            # expired. Same 404 as "no previsit": the distinction is not the
            # hospital's to learn.
            raise not_found()

        document = _decrypt(state, caller.tenant_id, row)
        shared = _shared_ids(dict(share.scope_sections))
        sections = tuple(section for section in document.sections if section.id in shared)
        if not sections:
            raise not_found()
        served = document.model_copy(update={"sections": sections})

        resource_ref = f"previsit_output:{row.id}"
        await state.audit.record(
            actor=actor,
            action="api.previsit_output.shared",
            resource_ref=resource_ref,
            consent_scope=f"scope:{PREVISIT_OUTPUT_SCOPE}",
        )
        return PreVisitOutputFetched(
            patient_number=payload.patient_number,
            output_ref=resource_ref,
            output=served,
        )

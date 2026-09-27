"""A document's extracted items, published to its patient, and their verdicts (INT-138).

Two routes under the document they belong to:

- ``GET …/documents/{doc_id}/extraction`` — what has been read out of the
  document: a closed ``state`` and, when read, one confirm card per item —
  an id, the kind, the ``summary`` line, the ``unit_conflict`` flag, the
  printed date and the source box (page + normalised bbox).
- ``POST …/documents/{doc_id}/extraction/decisions`` — ``{card_id,
  decision}``, where a decision is ``confirmed`` or ``declined``. A confirmed
  item goes through ``confirm_record_item`` into INT-121's
  ``ConfirmedRecordStore.admit``; a declined one is recorded and admitted
  nowhere. The answer echoes the recorded decision, so the app shows a card
  as settled only when this route said so (the no-optimistic-write rule).

**Consent and audit (invariant 4).** Both routes declare the patient's
``documents`` scope — the same scope the document itself is read under — and
append a hash-chained entry naming the account and ``doc:<id>`` and nothing
else (invariant 6). A refused read is not a read and is not audited.

**The body names no actor (invariant 12).** ``confirm_record_item`` takes no
``by=``: the actor is read off INT-170's closed vocabulary. The request model
forbids every field but the two, so a caller cannot assert who confirmed, and
it carries no magnitude or unit either: confirming is agreeing with what was
extracted, never restating it.

**The number crosses unrendered twice (invariant 22).** ``summary`` is
carried byte for byte. It was written once by ``summarise_item`` at
``SUMMARY_LOCALE`` through INT-385's ``quantity_atom`` (decimal comma, no
grouping, U+00A0 between number and unit), and the ``unit_conflict`` flag
rides beside it. Nothing here parses, converts or re-renders a value — a
transport that tidied a flagged magnitude would defeat the guard.

**The document is data, never instructions (invariant 14).** Nothing on this
path reaches a model. The one check it makes on the text is the one fence's
own: an item carrying the data-boundary control token refuses the extraction
whole, exactly as the fence refuses such a region, and the refusal names no
content. So does an item whose box points into a different document.

**A document may not triage (invariant 1).** The response model has no field
a level could occupy, and ``UnconfirmedRecordItem`` has none to copy from.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Literal

from clinical_schemas.record_extraction import UnconfirmedRecordItem, confirm_record_item
from clinical_schemas.records import RecordItemKind
from fastapi import APIRouter, HTTPException
from intake_platform.data_boundary import carries_control_token
from intake_platform.records import DocumentExtraction
from pydantic import BaseModel, ConfigDict, Field

from intake_api import store
from intake_api.auth import Principal, require_patient
from intake_api.consent_guard import require_scopes
from intake_api.db import tenant_session
from intake_api.errors import not_found
from intake_api.record_feed import Decision, ExtractionPhase, document_ref_for
from intake_api.state import State

__all__ = ["DecisionIn", "DecisionOut", "ExtractionOut", "item_id_of", "router"]

router = APIRouter(prefix="/v1/visits/{visit_id}/documents/{doc_id}/extraction", tags=["records"])

DOCUMENTS_SCOPE = "documents"
_SCOPE_REF = f"scope:{DOCUMENTS_SCOPE}"

FeedState = Literal["read", "reading", "unread", "refused"]


# --- bodies ----------------------------------------------------------------------------------


class SourceBoxOut(BaseModel):
    """Where on which page the line is: page is 1-based, bbox is normalised."""

    document_ref: str
    page: int
    bbox: tuple[float, float, float, float]


class ExtractedItemOut(BaseModel):
    """One confirm card. No field a level, a confidence or a value could occupy."""

    id: str
    kind: RecordItemKind
    summary: str
    unit_conflict: bool
    date: str | None
    provenance: SourceBoxOut
    decision: Decision | None


class ExtractionOut(BaseModel):
    state: FeedState
    items: list[ExtractedItemOut]


class DecisionIn(BaseModel):
    """Which card, and the verdict. Nothing else is accepted."""

    model_config = ConfigDict(extra="forbid")

    card_id: str = Field(min_length=1, max_length=64)
    decision: Decision


class DecisionOut(BaseModel):
    card_id: str
    decision: Decision


# --- the items a document may serve ----------------------------------------------------------


def item_id_of(index: int, item: UnconfirmedRecordItem) -> str:
    """A stable id from the item's position and box, never from its text.

    The box and the character interval are coordinates, not content, so the
    id can travel and be logged. An extraction that is re-read differently
    yields different ids, which makes a verdict on the old one miss rather
    than land on a different line.
    """
    box = item.box
    material = f"{index}|{item.kind.value}|{box.page}|{box.bbox}|{box.start}|{box.end}"
    return "item-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def _servable(
    extraction: DocumentExtraction, document_id: uuid.UUID
) -> Mapping[str, UnconfirmedRecordItem] | None:
    """The items keyed by id, or ``None`` when the extraction is refused whole.

    Refused whole rather than trimmed, like every other refusal on this path:
    dropping the offending item and serving the rest is how the remainder of
    a bad answer gets through.
    """
    expected_ref = document_ref_for(document_id)
    served: dict[str, UnconfirmedRecordItem] = {}
    for index, item in enumerate(extraction.items):
        if item.box.document_ref != expected_ref:
            return None
        if carries_control_token(item.summary):
            return None
        served[item_id_of(index, item)] = item
    return served


# --- helpers ---------------------------------------------------------------------------------


async def _patient_document(
    state: State, principal: Principal, visit_id: uuid.UUID, doc_id: uuid.UUID
) -> tuple[str, uuid.UUID, uuid.UUID, bool]:
    """(account id, tenant id, patient id, scanned clean) for the caller's own document."""
    patient, patient_id = require_patient(principal)
    async with tenant_session(state.engine, patient.tenant_id) as session:
        visit = await store.get_visit(
            session, tenant_id=patient.tenant_id, visit_id=visit_id, patient_id=patient_id
        )
        if visit is None:
            raise not_found()
        row = await store.get_document_row(
            session, tenant_id=patient.tenant_id, visit_id=visit_id, doc_id=doc_id
        )
        if row is None:
            raise not_found()
        clean = dict(row.provenance).get("state") == "clean"
    return patient.account_id, patient.tenant_id, patient_id, clean


def _not_ready() -> HTTPException:
    return HTTPException(status_code=409, detail={"error": "extraction_not_read"})


# --- endpoints -------------------------------------------------------------------------------


@router.get("", response_model=ExtractionOut, dependencies=[require_scopes(DOCUMENTS_SCOPE)])
async def read_extraction(
    visit_id: uuid.UUID, doc_id: uuid.UUID, principal: Principal, state: State
) -> ExtractionOut:
    account_id, tenant_id, _, clean = await _patient_document(state, principal, visit_id, doc_id)
    out = ExtractionOut(state="unread", items=[])
    # Only a scanned-clean document is ever read: quarantined or rejected
    # bytes have no business reaching an extractor, so the source is not
    # even asked about one.
    if clean:
        reading = await state.extractions.read(tenant_id=tenant_id, document_id=doc_id)
        if reading.phase is ExtractionPhase.READING:
            out = ExtractionOut(state="reading", items=[])
        elif reading.extraction is not None:
            served = _servable(reading.extraction, doc_id)
            if served is None:
                out = ExtractionOut(state="refused", items=[])
            else:
                out = ExtractionOut(
                    state="read",
                    items=[
                        ExtractedItemOut(
                            id=item_id,
                            kind=item.kind,
                            summary=item.summary,
                            unit_conflict=item.unit_conflict,
                            date=item.date.isoformat() if item.date is not None else None,
                            provenance=SourceBoxOut(
                                document_ref=item.box.document_ref,
                                page=item.box.page,
                                bbox=item.box.bbox,
                            ),
                            decision=state.record_decisions.decision(
                                tenant_id=tenant_id, document_id=doc_id, item_id=item_id
                            ),
                        )
                        for item_id, item in served.items()
                    ],
                )
    await state.audit.record(
        actor=account_id,
        action="api.document.extraction.read",
        resource_ref=document_ref_for(doc_id),
        consent_scope=_SCOPE_REF,
    )
    return out


@router.post(
    "/decisions", response_model=DecisionOut, dependencies=[require_scopes(DOCUMENTS_SCOPE)]
)
async def record_decision(
    visit_id: uuid.UUID, doc_id: uuid.UUID, payload: DecisionIn, principal: Principal, state: State
) -> DecisionOut:
    account_id, tenant_id, patient_id, clean = await _patient_document(
        state, principal, visit_id, doc_id
    )
    if not clean:
        raise _not_ready()
    reading = await state.extractions.read(tenant_id=tenant_id, document_id=doc_id)
    if reading.extraction is None:
        raise _not_ready()
    served = _servable(reading.extraction, doc_id)
    if served is None:
        raise HTTPException(status_code=409, detail={"error": "extraction_refused"})
    item = served.get(payload.card_id)
    if item is None:
        raise not_found()

    ledger = state.record_decisions
    async with ledger.lock:
        prior = ledger.decision(tenant_id=tenant_id, document_id=doc_id, item_id=payload.card_id)
        if prior is not None:
            if prior is payload.decision:
                # The same tap twice is the same verdict: acknowledged again,
                # recorded once, admitted once.
                return DecisionOut(card_id=payload.card_id, decision=prior)
            raise HTTPException(status_code=409, detail={"error": "already_decided"})
        # Audit before effect: if the chain cannot take the entry, nothing is
        # recorded and the app is told nothing was saved.
        await state.audit.record(
            actor=account_id,
            action=(
                "api.document.extraction.confirm"
                if payload.decision is Decision.CONFIRMED
                else "api.document.extraction.decline"
            ),
            resource_ref=document_ref_for(doc_id),
            consent_scope=_SCOPE_REF,
        )
        if payload.decision is Decision.CONFIRMED:
            ledger.record_confirmed(
                tenant_id=tenant_id,
                patient_id=patient_id,
                document_id=doc_id,
                item_id=payload.card_id,
                item=confirm_record_item(item, at=datetime.now(UTC)),
            )
        else:
            ledger.record_declined(tenant_id=tenant_id, document_id=doc_id, item_id=payload.card_id)
    return DecisionOut(card_id=payload.card_id, decision=payload.decision)

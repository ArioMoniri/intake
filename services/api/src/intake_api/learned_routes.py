"""INT-170 — ``/v1/me/learned``: the transparency ledger, and the way out of it.

files/09 §3 requires every ``PatientOverlay`` fact to be inspectable in *Me →
Hakkımda öğrendikleri*, showing where it came from, and to be correctable or
deletable by the patient. INT-247 already built that screen against a
``CarriedFact`` shape; this module is the server side of the same contract —
one fact per row, each carrying its provenance and its status, in ids and
closed vocabularies so the client renders the Turkish (invariant 5).

**Two routes, two different consent stories, and the difference is the point.**

- ``GET`` is a read of clinical data, so invariant 4 applies literally: it
  declares ``learning:personal``, the files/06 §2 purpose the fact is held
  under, and the store audits the read before it answers.
- ``DELETE`` is the patient saying a fact about them is not so — KVKK m.11. It
  declares ``core`` and **not** ``learning:personal``, for the reason
  ``DataSubjectRightDeclaration`` and ``NotificationPreferenceDeclaration``
  both give in ``intake_api.consent_guard``: a purpose whose withdrawal locks
  the correction of the facts it produced is not a purpose, it is a cage. The
  request a withdrawal provokes is exactly the request a
  ``learning:personal``-gated route would refuse. The audit names
  ``basis:KVKK-11`` rather than a scope.

**Fail closed when unwired.** The store is resolved through
:func:`get_overlay_store`, which answers 503 when nothing is mounted rather
than an empty ledger. INT-016 states the reason and it is the same one here: an
empty ledger and an unreadable one look identical to a patient, and only one of
them is true.

The value of a learned fact travels in this response body because that is the
whole purpose of the surface — it is the data subject reading their own record
over an authenticated channel. It travels nowhere else: invariant 6 governs
logs, traces and errors, and every refusal below is a code with no narrative.

sec_row: `learning-loops`.
"""

from __future__ import annotations

from typing import Annotated

from clinical_schemas.common import JsonValue
from clinical_schemas.overlay import RECONFIRM_AFTER, Confirmer, LearnedFactSource
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from intake_api.auth import Principal, require_patient
from intake_api.consent_guard import require_scopes
from intake_api.errors import not_found, service_unconfigured
from intake_api.overlay_store import (
    LEARNING_SCOPE,
    FactStatus,
    LedgerEntry,
    OverlayFactNotFound,
    PatientOverlayStore,
)

__all__ = [
    "CORE_SCOPE",
    "LEARNED_STORE_ATTR",
    "LearnedFactOut",
    "LearnedOut",
    "OverlayStore",
    "get_overlay_store",
    "router",
]

#: The base service purpose. The correction right must not be lockable by the
#: purpose it corrects, so the delete route declares this instead.
CORE_SCOPE = "core"

#: Where ``app.py`` mounts the store. Read through :func:`get_overlay_store` so
#: an unmounted store is a 503 at the route rather than an AttributeError.
LEARNED_STORE_ATTR = "overlay_facts"

router = APIRouter(prefix="/v1/me/learned", tags=["learned"])


class LearnedFactOut(BaseModel):
    """One ledger row. Every provenance axis is required except the withdrawal
    stamp — "not withdrawn" is a state; a missing provenance is not."""

    fact_id: str
    key: str
    value: JsonValue
    status: FactStatus
    confirmed_by: Confirmer
    confirmed_by_ref: str
    confirmed_at: str
    source: LearnedFactSource
    source_ref: str
    reconfirm_due_at: str
    withdrawn_at: str | None


class LearnedOut(BaseModel):
    facts: list[LearnedFactOut]
    #: The window, sent rather than hard-coded in the app, so the client's copy
    #: and the server's rule cannot drift (files/09 §3).
    reconfirm_after_days: int


def get_overlay_store(request: Request) -> PatientOverlayStore:
    """The store, or a fail-closed 503 (INT-016's posture)."""
    store = getattr(request.app.state, LEARNED_STORE_ATTR, None)
    if store is None:
        raise service_unconfigured("overlay_store_unconfigured")
    if not isinstance(store, PatientOverlayStore):  # pragma: no cover - wiring guard
        raise service_unconfigured("overlay_store_unconfigured")
    return store


#: The seam, as a dependency: tests inject an in-process store, ``app.py``
#: mounts the wired one, and an unmounted store is a 503 rather than a crash.
OverlayStore = Annotated[PatientOverlayStore, Depends(get_overlay_store)]


def _to_out(entry: LedgerEntry) -> LearnedFactOut:
    return LearnedFactOut(
        fact_id=entry.fact_id,
        key=entry.key,
        value=entry.value,
        status=entry.status,
        confirmed_by=entry.confirmed_by,
        confirmed_by_ref=entry.confirmed_by_ref,
        confirmed_at=entry.confirmed_at.isoformat(),
        source=entry.source,
        source_ref=entry.source_ref,
        reconfirm_due_at=entry.reconfirm_due_at.isoformat(),
        withdrawn_at=None if entry.withdrawn_at is None else entry.withdrawn_at.isoformat(),
    )


@router.get("", response_model=LearnedOut, dependencies=[require_scopes(LEARNING_SCOPE)])
async def read_learned(principal: Principal, store: OverlayStore) -> LearnedOut:
    """Everything the system holds about this patient, with where it came from."""
    account, patient_id = require_patient(principal)
    entries = await store.ledger(
        tenant_ref=str(account.tenant_id),
        patient_ref=str(patient_id),
        actor=account.account_id,
    )
    return LearnedOut(
        facts=[_to_out(entry) for entry in entries],
        reconfirm_after_days=RECONFIRM_AFTER.days,
    )


@router.delete(
    "/{fact_id}", response_model=LearnedFactOut, dependencies=[require_scopes(CORE_SCOPE)]
)
async def withdraw_learned(
    fact_id: str, principal: Principal, store: OverlayStore
) -> LearnedFactOut:
    """KVKK m.11 — withdraw a fact about oneself. Tombstoned, never deleted."""
    account, patient_id = require_patient(principal)
    try:
        entry = await store.withdraw(
            tenant_ref=str(account.tenant_id),
            patient_ref=str(patient_id),
            fact_id=fact_id,
            actor=account.account_id,
        )
    except OverlayFactNotFound as err:
        raise not_found() from err
    return _to_out(entry)

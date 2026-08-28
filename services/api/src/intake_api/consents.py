"""Patient-facing consent routes (INT-232) — the INT-132 client seam served.

Three routes under /v1/consents, all patient-only (the ledger is the
subject's own; the clinic admin gets 403) and all declared to the INT-038
route-table scan with the consent_management() marker — they are ABOUT
consent, so requiring a consent scope would be circular (consent_guard.py
explains the taxonomy).

- ``GET  /v1/consents`` — the snapshot the mobile loader parses verbatim:
  one ``scopes`` row per non-parameterised files/06 §2 purpose (reason from
  the pinned INT-038 ``consent_state`` semantics, plus the bound
  {version, text_hash} of the live grant when one exists) and the ``texts``
  the docs/legal catalog can load ({purpose, version, text_hash, body}).
  An absent legal tree serves an EMPTY texts list — fail closed, never
  invented copy (invariant 18).
- ``POST /v1/consents/grant`` — records one hash-bound grant, ONLY when the
  submitted {version, text_hash} still match the served text (the client
  grants against the text it showed): a moved text is 409
  ``consent_text_changed``, a missing one 409 ``text_missing``. Granting a
  purpose grants nothing else (unbundling, files/06 §2) and every grant is
  audited inside the service (invariant 4).
- ``POST /v1/consents/withdraw`` — instant; rides the INT-038 service so the
  cascade (dependents + live Doctor-Link shares) happens in the same
  evaluation pass, audited. The client-declared ``at`` is accepted for seam
  compatibility but the revocation instant is the server's — a device clock
  must not be able to time a consent change.

Refusals carry ids only (invariant 6): a scope off the closed registry list
— ``lane:acoustic``, the bare ``share`` family, anything unknown — answers
422 with the submitted purpose id and nothing else.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter
from intake_platform.consent import (
    PURPOSES,
    ConsentText,
    ConsentTextMissingError,
    PurposeDef,
    Reason,
    UnknownPurposeError,
    consent_state,
    grant_consent,
    resolve_scope,
    withdraw_consent,
)
from intake_platform.db.models import Consent
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import select

from intake_api.auth import Principal, require_patient
from intake_api.consent_guard import consent_management
from intake_api.db import tenant_session
from intake_api.errors import consent_text_changed, consent_text_missing, purpose_unknown
from intake_api.state import State

__all__ = ["router"]

router = APIRouter(prefix="/v1/consents", tags=["consents"])

#: All grants through this surface come from the app channel (files/06 §1).
GRANT_CHANNEL = "app"

#: The snapshot rows: every non-parameterised registry purpose, in files/06
#: §2 order — exactly the closed list the mobile purposes.ts mirrors. The
#: parameterised share family has no standing row (a bare share toggle would
#: be the bundled consent files/06 §2 forbids); its per-visit grants live on
#: the Review & send flow.
SNAPSHOT_PURPOSES: tuple[PurposeDef, ...] = tuple(p for p in PURPOSES if not p.parameterised)

# Boundary shapes: ids and version tokens only, so nothing narrative can even
# arrive (invariant 6). The scope shape admits the whole closed list plus
# share:<qualifier>; membership is the registry's call, not the regex's.
ScopeField = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_.:-]{0,63}$")]
VersionField = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")]
TextHashField = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class ScopeStateOut(BaseModel):
    scope: str
    reason: Reason
    version: str | None
    text_hash: str | None


class ConsentTextOut(BaseModel):
    purpose: str
    version: str
    text_hash: str
    body: str


class ConsentSnapshotOut(BaseModel):
    scopes: list[ScopeStateOut]
    texts: list[ConsentTextOut]


class GrantBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: ScopeField
    version: VersionField
    text_hash: TextHashField
    # The device's own instant (the offline queue replays carry it). It is
    # provenance on the grant row's evidence_ref, never the grant time —
    # granted_at is stamped by the server.
    at: datetime | None = None


class WithdrawBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: ScopeField
    # Seam compatibility only (the merged client always sends it): the
    # revocation instant is the server's, so a device clock cannot time a
    # consent change.
    at: datetime | None = None


class GrantOut(BaseModel):
    scope: str
    version: str
    text_hash: str


class WithdrawOut(BaseModel):
    scope: str
    withdrawn_scopes: list[str]
    revoked_share_ids: list[uuid.UUID]


def _resolved(scope: str) -> PurposeDef:
    """The registry decides membership; refusal echoes the id only."""
    try:
        return resolve_scope(scope)
    except UnknownPurposeError as exc:
        raise purpose_unknown(scope) from exc


#: Lookup key for a parameterised family's text: the catalog binds any
#: ``share:<qualifier>`` to the one family file, so the qualifier below is a
#: lookup key only — never a grantable scope, never stored anywhere.
_FAMILY_TEXT_QUALIFIER = "text"


def _text_lookup_scope(purpose: PurposeDef) -> str:
    if purpose.parameterised:
        return f"{purpose.id}:{_FAMILY_TEXT_QUALIFIER}"
    return purpose.id


def _ref_instant(value: datetime) -> str:
    """UTC instant in the audit/service ref shape (no '+', no spaces)."""
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _evidence_ref(at: datetime | None) -> str:
    if at is None:
        return "server-at:" + _ref_instant(datetime.now(UTC))
    return "client-at:" + _ref_instant(at)


def _granted_key(row: Consent) -> datetime:
    value = row.granted_at
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _bound_binding(
    rows: list[Consent], reason: Reason, current: ConsentText | None
) -> tuple[str | None, str | None]:
    """The {version, text_hash} the standing grant is bound to — what tells
    the client WHICH text the patient actually agreed to (and, for a stale
    row, which superseded one). Reasons without a live row carry nulls."""
    live = [row for row in rows if row.revoked_at is None]
    if not live or reason not in ("granted", "unbound", "stale"):
        return None, None
    if reason == "granted" and current is not None:
        matching = [row for row in live if row.text_hash == current.text_hash]
        if matching:
            live = matching
    latest = max(live, key=_granted_key)
    return latest.version, latest.text_hash


@router.get("", response_model=ConsentSnapshotOut, dependencies=[consent_management()])
async def read_snapshot(principal: Principal, state: State) -> ConsentSnapshotOut:
    patient, patient_id = require_patient(principal)
    scopes: list[ScopeStateOut] = []
    async with tenant_session(state.engine, patient.tenant_id) as session:
        all_rows = (
            await session.scalars(
                select(Consent).where(
                    Consent.tenant_id == patient.tenant_id,
                    Consent.patient_id == patient_id,
                )
            )
        ).all()
        by_scope: dict[str, list[Consent]] = {}
        for row in all_rows:
            by_scope.setdefault(row.scope, []).append(row)
        for purpose in SNAPSHOT_PURPOSES:
            decision = await consent_state(
                session,
                tenant_id=patient.tenant_id,
                patient_id=patient_id,
                scope=purpose.id,
                catalog=state.consent_catalog,
            )
            version, text_hash = _bound_binding(
                by_scope.get(purpose.id, []),
                decision.reason,
                state.consent_catalog.try_entry(purpose.id),
            )
            scopes.append(
                ScopeStateOut(
                    scope=purpose.id,
                    reason=decision.reason,
                    version=version,
                    text_hash=text_hash,
                )
            )
    texts: list[ConsentTextOut] = []
    for purpose in PURPOSES:
        entry = state.consent_catalog.try_entry(_text_lookup_scope(purpose))
        if entry is not None:
            texts.append(
                ConsentTextOut(
                    purpose=purpose.id,
                    version=entry.version,
                    text_hash=entry.text_hash,
                    body=entry.body,
                )
            )
    await state.audit.record(
        actor=patient.account_id,
        action="api.consent.read",
        resource_ref=f"patient:{patient_id}",
        consent_scope="scope:consent",
    )
    return ConsentSnapshotOut(scopes=scopes, texts=texts)


@router.post(
    "/grant", response_model=GrantOut, status_code=201, dependencies=[consent_management()]
)
async def grant(payload: GrantBody, principal: Principal, state: State) -> GrantOut:
    patient, patient_id = require_patient(principal)
    _resolved(payload.scope)
    entry = state.consent_catalog.try_entry(payload.scope)
    if entry is None:
        raise consent_text_missing(payload.scope)  # no text, no grant (invariant 18)
    if payload.version != entry.version or payload.text_hash != entry.text_hash:
        raise consent_text_changed(payload.scope)
    async with tenant_session(state.engine, patient.tenant_id) as session:
        try:
            row = await grant_consent(
                session,
                tenant_id=patient.tenant_id,
                patient_id=patient_id,
                scope=payload.scope,
                channel=GRANT_CHANNEL,
                evidence_ref=_evidence_ref(payload.at),
                catalog=state.consent_catalog,
                audit=state.audit,
                actor=patient.account_id,
            )
        except ConsentTextMissingError as exc:
            # the file vanished between the check above and the bind
            raise consent_text_missing(payload.scope) from exc
        if row.version != payload.version or row.text_hash != payload.text_hash:
            # the text moved between the check and the bind: the patient
            # never saw what got bound — raising rolls the row back
            raise consent_text_changed(payload.scope)
    return GrantOut(scope=payload.scope, version=payload.version, text_hash=payload.text_hash)


@router.post("/withdraw", response_model=WithdrawOut, dependencies=[consent_management()])
async def withdraw(payload: WithdrawBody, principal: Principal, state: State) -> WithdrawOut:
    patient, patient_id = require_patient(principal)
    _resolved(payload.scope)
    async with tenant_session(state.engine, patient.tenant_id) as session:
        report = await withdraw_consent(
            session,
            tenant_id=patient.tenant_id,
            patient_id=patient_id,
            scope=payload.scope,
            audit=state.audit,
            actor=patient.account_id,
        )
    return WithdrawOut(
        scope=report.scope,
        withdrawn_scopes=list(report.withdrawn_scopes),
        revoked_share_ids=list(report.revoked_share_ids),
    )

"""INT-407 — ``POST /v1/visits/{visit_id}/transitions``: the files/02 §2b visit
lifecycle, server-authoritative.

files/02 §2b: *"a RED-flagged patient whose appointment moves two weeks out is
invisible to everyone … The alert fired, the patient rescheduled, and the
system forgot. That is a safety gap wearing a UX costume, and it is fixed by
state, not by copy."* The machine is :mod:`intake_platform.visit_lifecycle`;
this route is where a move happens, and every hook §2b binds to a move runs
inside the same transaction as the move itself:

- **every transition** is refused unless the table allows it, and is audited
  by its id (``api.visit.transition.<state>``, ``visit:<id>/transition:<id>``);
- **``rescheduled`` or ``cancelled`` on a RED visit** raises a clinic Safety
  inbox entry (INT-406) — no connector is consulted, so none is needed — and
  re-shows each patient-facing RED as a pointer in the register it was told in
  (:mod:`intake_platform.visit_lifecycle.resurface`). The inbox is read before
  anything is written and written before the transaction commits: an inbox
  that is unwired or unreachable refuses the move (503) rather than letting a
  RED visit move silently, and a move whose entry cannot be written is rolled
  back. A transition that does not move the visit needs no inbox;
- **``cancelled``** revokes every live share and Doctor Link of the note and
  withdraws what the clinic side could read — *"A patient who cancelled has
  withdrawn the context in which they consented to share"*;
- **``rescheduled``** writes the new datetime, re-pins every live Doctor Link
  to the new ``visit_datetime + 72 h`` (row and routing hint), and re-queues the
  T-24h confirm; the note's staleness and the delta-session offer are derived
  on read (:meth:`~intake_api.store.VisitRecord.note_stale`).

``attended`` and ``missed`` are not the patient's to declare and are not
offered here: ``attended`` belongs to the clinic, ``missed`` to a scheduler
holding an owner-set grace (files/02 names none, so none is invented).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Literal

import redis
from clinical_schemas.visit_time import VisitSchedule
from fastapi import APIRouter, HTTPException
from intake_platform.safety_inbox import (
    InboxEntry,
    SafetyInbox,
    SafetyInboxUnavailable,
    VisitTransition,
)
from intake_platform.visit_lifecycle import (
    DELTA_SESSION_OFFER_FLAG,
    CheckInEvidence,
    CheckInMethod,
    RedResurface,
    TransitionRefused,
    VisitState,
    derive_location,
    red_resurface,
)
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from intake_api import store
from intake_api import visit_lifecycle_store as lifecycle_store
from intake_api.auth import Principal, require_patient
from intake_api.consent_guard import require_scopes
from intake_api.db import tenant_session
from intake_api.dev_fixture import DevAccount
from intake_api.errors import not_found, safety_inbox_refused, visit_invalid
from intake_api.notes import SHARE_SCOPE
from intake_api.schemas import VisitOut, validated_date, validated_visit_time
from intake_api.state import ApiState, State
from intake_api.visits import CORE_SCOPE, visit_out

__all__ = [
    "CheckInIn",
    "VisitTransitionIn",
    "VisitTransitionOut",
    "router",
    "validated_reschedule",
]

logger = logging.getLogger("intake_api.visit_lifecycle")

router = APIRouter(prefix="/v1/visits", tags=["visits"])

#: The two §2b moves: the ones a RED visit may not make silently.
_MOVES = {
    VisitState.RESCHEDULED: VisitTransition.RESCHEDULED,
    VisitState.CANCELLED: VisitTransition.CANCELLED,
}


class CheckInIn(BaseModel):
    """What the device knew when it checked in. Each method has one signal; an
    absent signal is doubt, and doubt is UNKNOWN, never ON_SITE."""

    model_config = ConfigDict(extra="forbid")

    method: Literal["qr", "geofence"]
    scanned_by_patient: bool | None = None
    inside_building: bool | None = None


class VisitTransitionIn(BaseModel):
    """A patient-initiated move. ``planned`` is where a reschedule lands, not
    a move anyone makes."""

    model_config = ConfigDict(extra="forbid")

    to: Literal["confirmed", "checked_in", "cancelled", "rescheduled"]
    # the new datetime, on a reschedule only — INT-306's rules, as on create
    date: str | None = Field(default=None, max_length=40)
    time: str | None = Field(default=None, max_length=40)
    time_source: str | None = Field(default=None, max_length=40)
    time_source_ref: str | None = Field(default=None, max_length=200)
    check_in: CheckInIn | None = None


class VisitTransitionOut(BaseModel):
    transition_id: str
    visit: VisitOut
    red_resurface: list[RedResurface]


def validated_reschedule(payload: VisitTransitionIn) -> VisitSchedule | None:
    """The new datetime a reschedule carries, validated with a create's reason
    codes; ``None`` for every other move.

    A reschedule to no date is ``schedule_required`` — §2b's ``rescheduled``
    is *"new datetime → back to planned"*, and every clock keyed off the visit
    (the Doctor Link expiry, the T-24h confirm) needs one. Date or time fields
    on any other move are ``schedule_not_allowed``: the datetime changes only
    by a reschedule, so it can never change silently.
    """
    fields = (payload.date, payload.time, payload.time_source, payload.time_source_ref)
    if payload.to != VisitState.RESCHEDULED.value:
        if any(value is not None for value in fields):
            raise visit_invalid("schedule_not_allowed")
        return None
    date = validated_date(payload.date)
    if date is None:
        raise visit_invalid("schedule_required")
    time = validated_visit_time(payload, date=date)
    return VisitSchedule(date=datetime.fromisoformat(date).date(), time=time)


def _evidence(payload: VisitTransitionIn) -> CheckInEvidence | None:
    if payload.check_in is None:
        return None
    try:
        return CheckInEvidence(
            method=CheckInMethod(payload.check_in.method),
            scanned_by_patient=payload.check_in.scanned_by_patient,
            inside_building=payload.check_in.inside_building,
        )
    except ValueError:
        raise visit_invalid("check_in_evidence_invalid") from None


def _refusal(code: str) -> HTTPException:
    """The table's refusal is a conflict with the visit's state (409); every
    other refusal is about the request (422). Codes only (invariant 6)."""
    if code == "transition_not_allowed":
        return HTTPException(status_code=409, detail={"error": code})
    return visit_invalid(code)


async def _reds(inbox: SafetyInbox, *, tenant_id: str, visit_id: str) -> tuple[InboxEntry, ...]:
    try:
        return await asyncio.to_thread(inbox.store.red_entries_for_visit, tenant_id, visit_id)
    except SafetyInboxUnavailable as refusal:
        raise safety_inbox_refused(503, refusal.code) from None


async def _raise_entry(
    inbox: SafetyInbox,
    *,
    tenant_id: str,
    visit_id: str,
    move: VisitTransition,
    transition_id: str,
    at: datetime,
) -> InboxEntry | None:
    try:
        return await asyncio.to_thread(
            lambda: inbox.visit_transition(
                tenant_id=tenant_id,
                visit_id=visit_id,
                transition=move,
                transition_id=transition_id,
                at=at,
            )
        )
    except SafetyInboxUnavailable as refusal:
        raise safety_inbox_refused(503, refusal.code) from None


async def _withdraw(
    session: AsyncSession, state: ApiState, patient: DevAccount, visit: store.VisitRecord
) -> None:
    """``cancelled``: revoke every live share and link, and say so by id."""
    note = await store.get_note_row(session, tenant_id=patient.tenant_id, visit_id=visit.id)
    if note is None:
        return
    grants = await lifecycle_store.live_grants(
        session, tenant_id=patient.tenant_id, note_id=note.id
    )
    if not grants.shares:
        return
    await store.revoke_live_shares(session, tenant_id=patient.tenant_id, note_id=note.id)
    for share in grants.shares:
        await state.audit.record(
            actor=patient.account_id,
            action="api.note.share_revoked",
            resource_ref=f"share:{share.id}",
            consent_scope=f"scope:{SHARE_SCOPE}",
        )
    for link in grants.links:
        await state.audit.record(
            actor=patient.account_id,
            action="api.doctor_link.revoked",
            resource_ref=f"doctor_link:{link.id}",
            consent_scope=f"scope:{SHARE_SCOPE}",
        )
        if state.doctor_link is not None:
            # the routing hint goes too, so a revoked token stops resolving
            await state.doctor_link.forget(link.token_fingerprint)
    # the clinic side read this note through those shares; it reads nothing now
    await state.audit.record(
        actor=patient.account_id,
        action="api.visit.clinician_entry_withdrawn",
        resource_ref=f"note:{note.id}",
        consent_scope=f"scope:{SHARE_SCOPE}",
    )


async def _repin(
    session: AsyncSession,
    state: ApiState,
    patient: DevAccount,
    visit: store.VisitRecord,
    schedule: VisitSchedule,
    now: datetime,
) -> None:
    """``rescheduled``: the Doctor Link expiry follows the visit (§2b), and so
    does the share the link hangs off (INT-589)."""
    note = await store.get_note_row(session, tenant_id=patient.tenant_id, visit_id=visit.id)
    if note is None:
        return
    shares = await lifecycle_store.repin_shares(
        session, tenant_id=patient.tenant_id, note_id=note.id, schedule=schedule, now=now
    )
    for share in shares:
        await state.audit.record(
            actor=patient.account_id,
            action="api.note.share_expiry_repinned",
            resource_ref=f"share:{share.id}",
            consent_scope=f"scope:{SHARE_SCOPE}",
        )
    links = await lifecycle_store.repin_links(
        session, tenant_id=patient.tenant_id, note_id=note.id, schedule=schedule, now=now
    )
    for link in links:
        await state.audit.record(
            actor=patient.account_id,
            action="api.doctor_link.expiry_repinned",
            resource_ref=f"doctor_link:{link.id}",
            consent_scope=f"scope:{SHARE_SCOPE}",
        )
        if state.doctor_link is not None:
            service = state.doctor_link
            ttl_s = int(max((link.expires_at - service.utcnow()).total_seconds(), 1))
            try:
                await service.register(
                    fingerprint=link.token_fingerprint,
                    link_id=link.id,
                    tenant_id=patient.tenant_id,
                    ttl_s=ttl_s,
                )
            except redis.RedisError:
                # the hint is not the authority (INT-150): a stale TTL makes the
                # link stop resolving early — fail closed — and the row, which
                # every redemption re-checks, already carries the new expiry
                logger.warning("doctor link routing hint not re-pinned")


@router.post(
    "/{visit_id}/transitions",
    response_model=VisitTransitionOut,
    dependencies=[require_scopes(CORE_SCOPE)],
)
async def transition_visit(
    visit_id: uuid.UUID, payload: VisitTransitionIn, principal: Principal, state: State
) -> VisitTransitionOut:
    patient, patient_id = require_patient(principal)
    to = VisitState(payload.to)
    schedule = validated_reschedule(payload)
    evidence = _evidence(payload)
    move = _MOVES.get(to)
    inbox = state.safety_inbox
    if move is not None and inbox is None:
        # nothing could say whether this visit carries a RED, so it does not move
        raise safety_inbox_refused(503, "safety_inbox_unconfigured")
    now = state.clock()
    transition_id = str(uuid.uuid4())
    tenant_ref, visit_ref = str(patient.tenant_id), str(visit_id)

    async with tenant_session(state.engine, patient.tenant_id) as session:
        visit = await lifecycle_store.lock_visit(
            session, tenant_id=patient.tenant_id, visit_id=visit_id, patient_id=patient_id
        )
        if visit is None:
            raise not_found()
        try:
            moved = visit.lifecycle.apply(
                to,
                transition_id=transition_id,
                at=now,
                schedule=schedule,
                check_in=evidence,
                confirm_message_id=str(uuid.uuid4()) if schedule is not None else None,
            )
        except TransitionRefused as refused:
            raise _refusal(refused.code) from None

        resurface: tuple[RedResurface, ...] = ()
        if move is not None and inbox is not None:
            reds = await _reds(inbox, tenant_id=tenant_ref, visit_id=visit_ref)
            # outside a session nobody knows where the patient stands (mode None)
            location = derive_location(moved.state, mode=None, check_in=moved.check_in)
            resurface = red_resurface(reds, location=location)
            moved = moved.with_resurface(resurface)

        await lifecycle_store.write_lifecycle(
            session, tenant_id=patient.tenant_id, visit_id=visit_id, record=moved
        )
        if move is not None and inbox is not None:
            # written before any audit row and before the commit: an entry that
            # cannot be written rolls the move back with nothing claimed; one
            # written for a move that then fails is an extra alert, never a
            # missing one
            await _raise_entry(
                inbox,
                tenant_id=tenant_ref,
                visit_id=visit_ref,
                move=move,
                transition_id=transition_id,
                at=now,
            )
        if to is VisitState.CANCELLED:
            await _withdraw(session, state, patient, visit)
        if schedule is not None:
            await lifecycle_store.write_schedule(
                session, tenant_id=patient.tenant_id, visit_id=visit_id, schedule=schedule
            )
            await _repin(session, state, patient, visit, schedule, now)
        await state.audit.record(
            actor=patient.account_id,
            action=f"api.visit.transition.{to.value}",
            resource_ref=f"visit:{visit_id}/transition:{transition_id}",
            consent_scope=f"scope:{CORE_SCOPE}",
        )
        refreshed = await store.get_visit(
            session, tenant_id=patient.tenant_id, visit_id=visit_id, patient_id=patient_id
        )
        if refreshed is None:  # pragma: no cover — read inside the same transaction
            raise not_found()
        out = visit_out(
            refreshed, now=now, offer=state.flags.get_bool(DELTA_SESSION_OFFER_FLAG, False)
        )
    return VisitTransitionOut(transition_id=transition_id, visit=out, red_resurface=list(resurface))

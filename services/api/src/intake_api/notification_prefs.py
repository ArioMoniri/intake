"""INT-141 — /v1/me/notifications: the patient's opt-out and quiet window.

Persisted, because a quiet-hours setting that lives in a process stops
working at the next deploy — at 03:00, for everybody at once — and an opt-out
that evaporates is a promise the product breaks silently.

Declared to the route scan with the ``notification_preference`` marker rather
than a consent scope, for the reason spelled out on
:class:`intake_api.consent_guard.NotificationPreferenceDeclaration`: a refusal
register that a withdrawal can lock is not a refusal register. Access control
is unchanged — patient-only, own row, audited.

Nothing clinical crosses this boundary in either direction: the request body
is a flag and two clock times, the response is the same, and the audit entry
carries a patient ref and a basis ref (invariant 6).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter
from intake_platform.db.models import NotificationPreference
from intake_platform.notifications import (
    NOTIFICATION_PREFERENCE_CHANGED_TOTAL,
    NotificationPreferences,
    QuietWindow,
)
from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from intake_api.auth import Principal, require_patient
from intake_api.consent_guard import notification_preference
from intake_api.db import tenant_session
from intake_api.state import State

__all__ = ["NOTIFICATION_BASIS_REF", "NotificationPrefsIn", "NotificationPrefsOut", "router"]

router = APIRouter(prefix="/v1/me/notifications", tags=["notifications"])

#: files/06 §1, row 6563-İYS. Service messages are non-commercial; the
#: register that turns them off is part of the same row's obligation, so the
#: audit cites the row rather than a consent scope that does not apply.
NOTIFICATION_BASIS_REF = "basis:6563-IYS"


class NotificationPrefsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    opted_out: bool
    quiet_start: str | None
    quiet_end: str | None


class NotificationPrefsIn(BaseModel):
    """Both ends of the window or neither. Half a window is refused rather
    than half-defaulted: filling in the other end would be choosing an hour
    for the patient, which is the whole thing this issue must not do."""

    model_config = ConfigDict(extra="forbid")

    opted_out: bool
    quiet_start: str | None = None
    quiet_end: str | None = None

    @model_validator(mode="after")
    def _window_is_whole_and_well_formed(self) -> NotificationPrefsIn:
        if (self.quiet_start is None) != (self.quiet_end is None):
            raise ValueError("quiet hours need both ends or neither")
        if self.quiet_start is not None and self.quiet_end is not None:
            # QuietWindow carries the format and zero-width rules; reusing it
            # keeps the API and the dispatcher from drifting apart.
            QuietWindow.parse(self.quiet_start, self.quiet_end)
        return self

    def window(self) -> QuietWindow | None:
        if self.quiet_start is None or self.quiet_end is None:
            return None
        return QuietWindow.parse(self.quiet_start, self.quiet_end)


def _to_out(preferences: NotificationPreferences) -> NotificationPrefsOut:
    if preferences.quiet is None:
        return NotificationPrefsOut(
            opted_out=preferences.opted_out, quiet_start=None, quiet_end=None
        )
    start, end = preferences.quiet.as_text()
    return NotificationPrefsOut(opted_out=preferences.opted_out, quiet_start=start, quiet_end=end)


def _from_row(row: NotificationPreference | None) -> NotificationPreferences:
    """An absent row is "the patient has said nothing" — not an error, and
    not an invented window."""
    if row is None:
        return NotificationPreferences(opted_out=False, quiet=None)
    quiet = (
        QuietWindow(start_minute=row.quiet_start_minute, end_minute=row.quiet_end_minute)
        if row.quiet_start_minute is not None and row.quiet_end_minute is not None
        else None
    )
    return NotificationPreferences(opted_out=row.opted_out, quiet=quiet)


async def _load_row(
    session: AsyncSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID
) -> NotificationPreference | None:
    row: NotificationPreference | None = await session.scalar(
        select(NotificationPreference).where(
            NotificationPreference.tenant_id == tenant_id,
            NotificationPreference.patient_id == patient_id,
        )
    )
    return row


async def load_preferences(
    session: AsyncSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID
) -> NotificationPreferences:
    """What the dispatcher asks for before sending anything."""
    return _from_row(await _load_row(session, tenant_id=tenant_id, patient_id=patient_id))


def _change_label(before: NotificationPreferences, after: NotificationPreferences) -> str | None:
    """The metric's closed label set (files/10 §9: opt-out rates). Opt-out
    outranks the window because it is the change that matters."""
    if before.opted_out != after.opted_out:
        return "opt_out" if after.opted_out else "opt_in"
    if before.quiet != after.quiet:
        return "quiet_window_cleared" if after.quiet is None else "quiet_window_set"
    return None


@router.get("", response_model=NotificationPrefsOut, dependencies=[notification_preference()])
async def read_notification_prefs(principal: Principal, state: State) -> NotificationPrefsOut:
    patient, patient_id = require_patient(principal)
    async with tenant_session(state.engine, patient.tenant_id) as session:
        preferences = await load_preferences(
            session, tenant_id=patient.tenant_id, patient_id=patient_id
        )
    await state.audit.record(
        actor=patient.account_id,
        action="api.notification_prefs.read",
        resource_ref=f"patient:{patient_id}",
        consent_scope=NOTIFICATION_BASIS_REF,
    )
    return _to_out(preferences)


@router.put("", response_model=NotificationPrefsOut, dependencies=[notification_preference()])
async def write_notification_prefs(
    payload: NotificationPrefsIn, principal: Principal, state: State
) -> NotificationPrefsOut:
    patient, patient_id = require_patient(principal)
    window = payload.window()
    after = NotificationPreferences(opted_out=payload.opted_out, quiet=window)
    # tenant_session already owns the transaction (and the RLS GUC); it
    # commits on clean exit, so the write needs no second begin().
    async with tenant_session(state.engine, patient.tenant_id) as session:
        row = await _load_row(session, tenant_id=patient.tenant_id, patient_id=patient_id)
        before = _from_row(row)
        if row is None:
            row = NotificationPreference(
                tenant_id=patient.tenant_id,
                patient_id=patient_id,
                opted_out=after.opted_out,
                quiet_start_minute=None if window is None else window.start_minute,
                quiet_end_minute=None if window is None else window.end_minute,
                updated_at=datetime.now(UTC),
            )
            session.add(row)
        else:
            row.opted_out = after.opted_out
            row.quiet_start_minute = None if window is None else window.start_minute
            row.quiet_end_minute = None if window is None else window.end_minute
            row.updated_at = datetime.now(UTC)
    change = _change_label(before, after)
    if change is not None:
        NOTIFICATION_PREFERENCE_CHANGED_TOTAL.labels(change=change).inc()
    await state.audit.record(
        actor=patient.account_id,
        action="api.notification_prefs.update",
        resource_ref=f"patient:{patient_id}",
        consent_scope=NOTIFICATION_BASIS_REF,
    )
    return _to_out(after)

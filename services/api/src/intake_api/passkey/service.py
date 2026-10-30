"""The passkey ceremonies (INT-582, D36): enrol, step up, remove, recover.

Every registration, step-up, refusal, removal and recovery is appended to the
hash-chained audit with ids only — ``patient:<id>`` as the actor,
``passkey:<id>`` or ``step-up:<action>`` as the resource, and
:data:`PASSKEY_BASIS_REF` as the ground (invariant 4, invariant 6) — and
counted in ``passkey_events_total`` with closed labels. Nothing is logged.

Registration happens only from an already authenticated OTP session (the
DPoP-bound tier, INT-131): the dev-bearer tier cannot enrol. Each challenge
is spent before any verifier runs, so a refused response still burns it
(the App Attest order, INT-344).

Recovery from a lost phone is the OTP tier plus a cool-off
(:data:`RECOVERY_COOLOFF_S`): the passkey keeps guarding D36's actions until
the cool-off ends — its holder can cancel the recovery by stepping up — and
then stops counting, so the patient is back on the OTP tier with enrolment
offered. A SIM-swap attacker must therefore hold the number for the whole
cool-off, unnoticed, while D35's push notice goes to the patient's signed-in
devices (INT-583). The 72 h figure is an engineering default recorded in
docs/evidence/INT-582.md for the owner to confirm, not a clinical value.
"""

from __future__ import annotations

import asyncio
import secrets
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, NoReturn

import redis
from fastapi import HTTPException, Request
from intake_platform.db.models import PatientPasskey
from sqlalchemy.ext.asyncio import AsyncEngine

from intake_api.audit import AuditWriter
from intake_api.auth import AUTH_TIER_OTP, require_patient
from intake_api.db import tenant_session
from intake_api.dev_fixture import DevAccount
from intake_api.passkey import store
from intake_api.passkey.actions import StepUpAction
from intake_api.passkey.challenges import CHALLENGE_TTL_S, Binding, Ceremony, ChallengeStore, Spent
from intake_api.passkey.metrics import PasskeyEvent, record_event
from intake_api.passkey.webauthn import (
    COSE_ES256,
    PasskeyConfig,
    PasskeyRefused,
    StoredCredential,
    b64url,
    b64url_decode,
    client_data_challenge,
    verify_assertion,
    verify_registration,
)

__all__ = [
    "MANUAL_PATH",
    "PASSKEY_BASIS_REF",
    "RECOVERY_COOLOFF_S",
    "Caller",
    "PasskeyService",
    "PasskeyWiring",
    "active_passkeys",
    "audit_event",
    "caller_of",
    "passkey_not_configured",
    "step_up_refused",
]

#: The audit ground: the KVKK m.12 security obligation (inventory.BASIS_ACCOUNT_SECURITY).
PASSKEY_BASIS_REF = "basis:KVKK-12"
#: Where a refusal made on the step-up signal alone sends the patient: an
#: application to the controller under KVKK m.13, reviewed by a person — the
#: KVKK m.11(1)(g) objection to a result reached solely by automated means.
#: The app renders it from its own tr key; the channel itself is the legal
#: lane's text.
MANUAL_PATH = "kvkk_m13_application"
#: Engineering default, owner to confirm (docs/evidence/INT-582.md).
RECOVERY_COOLOFF_S = 72 * 3600
#: The relying-party and account label the phone's passkey manager shows.
#: The brand, deliberately: never the phone number, never a name.
RP_NAME = "Önvizit"
_HANDLE_BYTES = 32


@dataclass(frozen=True)
class PasskeyWiring:
    """Everything the passkey tier needs, injectable for tests. It rides the
    OTP tier's Redis for challenges and grants; without an RP configuration
    the tier is absent and every enrolment route answers 503."""

    config: PasskeyConfig
    redis_client: redis.Redis
    now_fn: Callable[[], float] | None = None
    recovery_cooloff_s: int = RECOVERY_COOLOFF_S


@dataclass(frozen=True)
class Caller:
    tenant_id: uuid.UUID
    patient_id: uuid.UUID
    actor: str
    session_ref: str
    otp_tier: bool

    def binding(self, ceremony: Ceremony, action: StepUpAction | None) -> Binding:
        return Binding(
            tenant_id=self.tenant_id,
            patient_id=self.patient_id,
            session_ref=self.session_ref,
            ceremony=ceremony,
            action=None if action is None else action.value,
        )


def caller_of(request: Request, principal: DevAccount) -> Caller:
    """The patient asking, and the device session they ask from: the DPoP key
    thumbprint on the OTP tier, the bearer account on the dev tier."""
    patient, patient_id = require_patient(principal)
    jkt = getattr(request.state, "dpop_jkt", None)
    otp = getattr(request.state, "auth_tier", None) == AUTH_TIER_OTP and isinstance(jkt, str)
    return Caller(
        tenant_id=patient.tenant_id,
        patient_id=patient_id,
        actor=patient.account_id,
        session_ref=f"dpop:{jkt}" if otp else f"bearer:{patient.account_id}",
        otp_tier=otp,
    )


# --- refusals -----------------------------------------------------------------------------


def passkey_not_configured(*, manual_path: bool = False) -> HTTPException:
    detail: dict[str, str] = {"error": "passkey_not_configured"}
    if manual_path:
        detail["manual_path"] = MANUAL_PATH
    return HTTPException(status_code=503, detail=detail)


def otp_session_required() -> HTTPException:
    return HTTPException(status_code=403, detail={"error": "passkey_otp_session_required"})


def step_up_refused(action: StepUpAction, reason: str) -> HTTPException:
    return HTTPException(
        status_code=403,
        detail={
            "error": "step_up_refused",
            "action": action.value,
            "reason": reason,
            "manual_path": MANUAL_PATH,
        },
    )


async def audit_event(audit: AuditWriter, caller: Caller, action: str, resource_ref: str) -> None:
    await audit.record(
        actor=caller.actor,
        action=action,
        resource_ref=resource_ref,
        consent_scope=PASSKEY_BASIS_REF,
    )


async def active_passkeys(
    *,
    engine: AsyncEngine,
    audit: AuditWriter,
    caller: Caller,
    now: datetime,
    cooloff: timedelta,
) -> list[PatientPasskey]:
    """The caller's passkeys that still count; a recovery whose cool-off has
    ended removes its passkey here, audited, before anyone asks it anything."""
    async with tenant_session(engine, caller.tenant_id) as session:
        rows, purged = await store.purge_recovered(
            session,
            tenant_id=caller.tenant_id,
            patient_id=caller.patient_id,
            now=now,
            cooloff=cooloff,
        )
    for passkey_id in purged:
        await audit_event(audit, caller, "passkey.recovery.complete", f"passkey:{passkey_id}")
        record_event(PasskeyEvent.RECOVERY_COMPLETED)
    return rows


class PasskeyService:
    def __init__(self, wiring: PasskeyWiring, *, engine: AsyncEngine, audit: AuditWriter) -> None:
        self._config = wiring.config
        self._challenges = ChallengeStore(wiring.redis_client, now_fn=wiring.now_fn)
        self._now_fn = wiring.now_fn
        self._cooloff = timedelta(seconds=wiring.recovery_cooloff_s)
        self._engine = engine
        self._audit = audit

    @property
    def cooloff(self) -> timedelta:
        return self._cooloff

    def now(self) -> datetime:
        return datetime.fromtimestamp(
            self._now_fn() if self._now_fn is not None else time.time(), tz=UTC
        )

    async def active(self, caller: Caller) -> list[PatientPasskey]:
        return await active_passkeys(
            engine=self._engine,
            audit=self._audit,
            caller=caller,
            now=self.now(),
            cooloff=self._cooloff,
        )

    def spend_grant(self, grant: str, caller: Caller, action: StepUpAction) -> Spent:
        return self._challenges.consume_grant(grant, caller.binding(Ceremony.STEP_UP, action))

    # --- registration ----------------------------------------------------------------------

    async def registration_options(self, caller: Caller) -> dict[str, Any]:
        if not caller.otp_tier:
            raise otp_session_required()
        rows = await self.active(caller)
        handle = b64url_decode(rows[0].user_handle) if rows else secrets.token_bytes(_HANDLE_BYTES)
        challenge = await asyncio.to_thread(
            self._challenges.issue, caller.binding(Ceremony.REGISTER, None), note=b64url(handle)
        )
        return {
            "publicKey": {
                "rp": {"id": self._config.rp_id, "name": RP_NAME},
                "user": {"id": b64url(handle), "name": RP_NAME, "displayName": RP_NAME},
                "challenge": b64url(challenge),
                "pubKeyCredParams": [{"type": "public-key", "alg": COSE_ES256}],
                "timeout": CHALLENGE_TTL_S * 1000,
                "excludeCredentials": [
                    {"type": "public-key", "id": row.credential_id} for row in rows
                ],
                "authenticatorSelection": {
                    "authenticatorAttachment": "platform",
                    "residentKey": "required",
                    "userVerification": "required",
                },
                "attestation": "none",
            }
        }

    async def _refuse_registration(
        self, caller: Caller, reason: str, status: int = 400
    ) -> NoReturn:
        await audit_event(self._audit, caller, "passkey.register.refused", "ceremony:register")
        record_event(PasskeyEvent.REGISTRATION_REFUSED, reason)
        if status == 409:
            raise HTTPException(status_code=409, detail={"error": "passkey_exists"})
        raise HTTPException(
            status_code=400, detail={"error": "passkey_registration_refused", "reason": reason}
        )

    async def register(
        self,
        caller: Caller,
        *,
        credential_id: str,
        claimed_id: str,
        client_data: str,
        attestation: str,
    ) -> PatientPasskey:
        """``credential_id`` is the response's ``rawId``; ``claimed_id`` its
        ``id``, which WebAuthn makes the same value — a response that names two
        credentials is refused, audited, before anything is spent."""
        if not caller.otp_tier:
            raise otp_session_required()
        if claimed_id != credential_id:
            await self._refuse_registration(caller, "passkey_malformed")
        try:
            client_data_raw = b64url_decode(client_data)
            attestation_raw = b64url_decode(attestation)
            challenge = client_data_challenge(client_data_raw)
        except PasskeyRefused as refused:
            await self._refuse_registration(caller, refused.reason.value)
        spent, note = await asyncio.to_thread(
            self._challenges.consume_noted, challenge, caller.binding(Ceremony.REGISTER, None)
        )
        if spent is not Spent.OK or note is None:
            await self._refuse_registration(caller, f"challenge_{spent.value}")
        try:
            registered = verify_registration(
                config=self._config,
                expected_challenge=challenge,
                credential_id=credential_id,
                client_data_json=client_data_raw,
                attestation_object=attestation_raw,
            )
        except PasskeyRefused as refused:
            await self._refuse_registration(caller, refused.reason.value)
        row: PatientPasskey | None = None
        async with tenant_session(self._engine, caller.tenant_id) as session:
            if not await store.credential_exists(
                session, tenant_id=caller.tenant_id, credential_id=registered.credential_id
            ):
                row = await store.insert_credential(
                    session,
                    tenant_id=caller.tenant_id,
                    patient_id=caller.patient_id,
                    credential=registered,
                    user_handle=b64url_decode(note),
                    created_at=self.now(),
                )
        if row is None:
            await self._refuse_registration(caller, "passkey_exists", status=409)
        await audit_event(self._audit, caller, "passkey.register", f"passkey:{row.id}")
        record_event(PasskeyEvent.REGISTERED)
        return row

    # --- step-up ---------------------------------------------------------------------------

    async def step_up_options(self, caller: Caller, action: StepUpAction) -> dict[str, Any]:
        rows = await self.active(caller)
        if not rows:
            return {
                "enrolled": False,
                "tier": "otp_session",
                "enrolment": "offered" if caller.otp_tier else "unavailable",
            }
        challenge = await asyncio.to_thread(
            self._challenges.issue, caller.binding(Ceremony.STEP_UP, action)
        )
        return {
            "enrolled": True,
            "publicKey": {
                "challenge": b64url(challenge),
                "rpId": self._config.rp_id,
                "allowCredentials": [
                    {"type": "public-key", "id": row.credential_id} for row in rows
                ],
                "userVerification": "required",
                "timeout": CHALLENGE_TTL_S * 1000,
            },
        }

    async def _refuse_step_up(self, caller: Caller, action: StepUpAction, reason: str) -> NoReturn:
        await audit_event(self._audit, caller, "passkey.step_up.refused", f"step-up:{action.value}")
        record_event(PasskeyEvent.STEP_UP_REFUSED, reason)
        raise step_up_refused(action, reason)

    async def step_up(
        self,
        caller: Caller,
        action: StepUpAction,
        *,
        credential_id: str,
        claimed_id: str,
        client_data: str,
        authenticator_data: str,
        signature: str,
        user_handle: str | None,
    ) -> str:
        """Verify one assertion for ``action``; return the single-use grant."""
        if claimed_id != credential_id:
            await self._refuse_step_up(caller, action, "passkey_malformed")
        try:
            client_data_raw = b64url_decode(client_data)
            auth_data_raw = b64url_decode(authenticator_data)
            signature_raw = b64url_decode(signature)
            handle_raw = None if user_handle is None else b64url_decode(user_handle)
            presented_id = b64url(b64url_decode(credential_id))
            challenge = client_data_challenge(client_data_raw)
        except PasskeyRefused as refused:
            await self._refuse_step_up(caller, action, refused.reason.value)
        binding = caller.binding(Ceremony.STEP_UP, action)
        spent = await asyncio.to_thread(self._challenges.consume, challenge, binding)
        if spent is not Spent.OK:
            await self._refuse_step_up(caller, action, f"challenge_{spent.value}")
        row = next(
            (row for row in await self.active(caller) if row.credential_id == presented_id), None
        )
        if row is None:
            await self._refuse_step_up(caller, action, "credential_unknown")
        try:
            outcome = verify_assertion(
                config=self._config,
                expected_challenge=challenge,
                credential=StoredCredential(
                    credential_id=b64url_decode(row.credential_id),
                    public_key=b64url_decode(row.public_key),
                    sign_count=row.sign_count,
                    user_handle=b64url_decode(row.user_handle),
                ),
                client_data_json=client_data_raw,
                authenticator_data=auth_data_raw,
                signature=signature_raw,
                user_handle=handle_raw,
            )
        except PasskeyRefused as refused:
            await self._refuse_step_up(caller, action, refused.reason.value)
        async with tenant_session(self._engine, caller.tenant_id) as session:
            moved = await store.advance_sign_count(
                session,
                row=row,
                sign_count=outcome.sign_count,
                backup_state=outcome.backup_state,
                used_at=self.now(),
            )
        if not moved:
            await self._refuse_step_up(caller, action, "passkey_sign_count")
        grant = await asyncio.to_thread(self._challenges.issue_grant, binding)
        await audit_event(self._audit, caller, "passkey.step_up", f"passkey:{row.id}")
        record_event(PasskeyEvent.STEP_UP_PASSED)
        return grant

    # --- removal and recovery ----------------------------------------------------------------

    async def remove(self, caller: Caller, passkey_id: uuid.UUID) -> bool:
        async with tenant_session(self._engine, caller.tenant_id) as session:
            removed = await store.delete_credential(
                session,
                tenant_id=caller.tenant_id,
                patient_id=caller.patient_id,
                passkey_id=passkey_id,
            )
        if removed:
            await audit_event(self._audit, caller, "passkey.remove", f"passkey:{passkey_id}")
            record_event(PasskeyEvent.REMOVED)
        return removed

    async def start_recovery(self, caller: Caller) -> datetime | None:
        """Start (or report) the cool-off; None when there is nothing to recover."""
        if not caller.otp_tier:
            raise otp_session_required()
        if not await self.active(caller):
            return None
        async with tenant_session(self._engine, caller.tenant_id) as session:
            rows = await store.request_recovery(
                session, tenant_id=caller.tenant_id, patient_id=caller.patient_id, at=self.now()
            )
            ends = [end for row in rows if (end := store.recovery_ends_at(row, self._cooloff))]
        for row in rows:
            await audit_event(self._audit, caller, "passkey.recovery.request", f"passkey:{row.id}")
        record_event(PasskeyEvent.RECOVERY_REQUESTED)
        return min(ends)

    async def cancel_recovery(self, caller: Caller) -> int:
        async with tenant_session(self._engine, caller.tenant_id) as session:
            cancelled = await store.cancel_recovery(
                session, tenant_id=caller.tenant_id, patient_id=caller.patient_id
            )
        for passkey_id in cancelled:
            await audit_event(
                self._audit, caller, "passkey.recovery.cancel", f"passkey:{passkey_id}"
            )
        if cancelled:
            record_event(PasskeyEvent.RECOVERY_CANCELLED)
        return len(cancelled)

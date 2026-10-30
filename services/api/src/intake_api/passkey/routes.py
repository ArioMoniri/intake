"""``/v1/me/passkeys`` — the patient's passkeys (INT-582, D36).

The bodies are WebAuthn's own JSON (``RegistrationResponseJSON`` /
``AuthenticationResponseJSON``, as react-native-passkeys returns them), each
field bounded. They are data, never instructions (invariant 14): only the
members the verifier reads are taken, every byte string is strict base64url,
and the verifier refuses anything off the documented shape.

Every route declares itself to the consent scan as the patient's own
sign-in factor (``consent_guard.sign_in_factor``), caged to this prefix.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from intake_api.auth import Principal
from intake_api.consent_guard import sign_in_factor
from intake_api.errors import not_found
from intake_api.passkey.actions import StepUpAction
from intake_api.passkey.challenges import GRANT_TTL_S
from intake_api.passkey.gate import require_step_up
from intake_api.passkey.service import (
    RECOVERY_COOLOFF_S,
    PasskeyService,
    active_passkeys,
    caller_of,
    passkey_not_configured,
)
from intake_api.passkey.store import aware, recovery_ends_at
from intake_api.state import ApiState, State

__all__ = ["router"]

router = APIRouter(prefix="/v1/me/passkeys", tags=["passkeys"], dependencies=[sign_in_factor()])

# WebAuthn §5.1: a credential id is at most 1023 bytes, 1364 base64url chars
_ID_CHARS = 1366


class _WebAuthnModel(BaseModel):
    # the platform adds members (transports, clientExtensionResults, ...);
    # they are not read, so they are not kept
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class AttestationResponseIn(_WebAuthnModel):
    client_data_json: str = Field(alias="clientDataJSON", min_length=1, max_length=4096)
    attestation_object: str = Field(alias="attestationObject", min_length=1, max_length=8192)


class RegistrationCredentialIn(_WebAuthnModel):
    id: str = Field(min_length=1, max_length=_ID_CHARS)
    raw_id: str = Field(alias="rawId", min_length=1, max_length=_ID_CHARS)
    type: Literal["public-key"]
    response: AttestationResponseIn


class RegistrationIn(BaseModel):
    credential: RegistrationCredentialIn


class AssertionResponseIn(_WebAuthnModel):
    client_data_json: str = Field(alias="clientDataJSON", min_length=1, max_length=4096)
    authenticator_data: str = Field(alias="authenticatorData", min_length=1, max_length=2048)
    signature: str = Field(min_length=1, max_length=256)
    user_handle: str | None = Field(default=None, alias="userHandle", max_length=128)


class AssertionCredentialIn(_WebAuthnModel):
    id: str = Field(min_length=1, max_length=_ID_CHARS)
    raw_id: str = Field(alias="rawId", min_length=1, max_length=_ID_CHARS)
    type: Literal["public-key"]
    response: AssertionResponseIn


class StepUpOptionsIn(BaseModel):
    action: StepUpAction


class StepUpIn(BaseModel):
    action: StepUpAction
    credential: AssertionCredentialIn


class PasskeyOut(BaseModel):
    passkey_id: uuid.UUID
    created_at: str
    last_used_at: str | None
    backup_eligible: bool
    recovery_ends_at: str | None


class PasskeyListOut(BaseModel):
    enrolment: Literal["enrolled", "offered", "unavailable"]
    passkeys: list[PasskeyOut]


class GrantOut(BaseModel):
    grant: str
    action: StepUpAction
    expires_in: int


class RecoveryOut(BaseModel):
    recovery_ends_at: str


class RecoveryCancelOut(BaseModel):
    cancelled: int


def _service(state: ApiState) -> PasskeyService:
    if state.passkey is None:
        raise passkey_not_configured()
    return state.passkey


def _iso(value: datetime | None) -> str | None:
    return None if value is None else aware(value).isoformat()


# Enrolment while a passkey is active is a step-up of its own (passkey_add):
# without it a SIM-swapper enrols their own passkey beside the patient's and
# walks through D36. A patient with no active passkey enrols on the OTP tier,
# which is also where a completed recovery leaves them. The options read the
# grant (they name the existing passkeys, so an un-stepped caller gets none of
# it); the registration spends it.


@router.post(
    "/registration/options",
    dependencies=[require_step_up(StepUpAction.PASSKEY_ADD, spend=False)],
)
async def registration_options(
    request: Request, principal: Principal, state: State
) -> dict[str, Any]:
    service = _service(state)
    return await service.registration_options(caller_of(request, principal))


@router.post(
    "/registration",
    status_code=201,
    response_model=PasskeyOut,
    dependencies=[require_step_up(StepUpAction.PASSKEY_ADD)],
)
async def register(
    payload: RegistrationIn, request: Request, principal: Principal, state: State
) -> PasskeyOut:
    service = _service(state)
    credential = payload.credential
    row = await service.register(
        caller_of(request, principal),
        credential_id=credential.raw_id,
        claimed_id=credential.id,
        client_data=credential.response.client_data_json,
        attestation=credential.response.attestation_object,
    )
    return PasskeyOut(
        passkey_id=row.id,
        created_at=aware(row.created_at).isoformat(),
        last_used_at=None,
        backup_eligible=row.backup_eligible,
        recovery_ends_at=None,
    )


@router.get("", response_model=PasskeyListOut)
async def list_passkeys(request: Request, principal: Principal, state: State) -> PasskeyListOut:
    service = _service(state)
    caller = caller_of(request, principal)
    rows = await service.active(caller)
    enrolment: Literal["enrolled", "offered", "unavailable"] = (
        "enrolled" if rows else ("offered" if caller.otp_tier else "unavailable")
    )
    return PasskeyListOut(
        enrolment=enrolment,
        passkeys=[
            PasskeyOut(
                passkey_id=row.id,
                created_at=aware(row.created_at).isoformat(),
                last_used_at=_iso(row.last_used_at),
                backup_eligible=row.backup_eligible,
                recovery_ends_at=_iso(recovery_ends_at(row, service.cooloff)),
            )
            for row in rows
        ],
    )


@router.post("/step-up/options")
async def step_up_options(
    payload: StepUpOptionsIn, request: Request, principal: Principal, state: State
) -> dict[str, Any]:
    caller = caller_of(request, principal)
    if state.passkey is None:
        # no passkey tier: a patient without a passkey keeps the OTP tier; a
        # patient WITH one cannot be asked for it, and is told so with the
        # manual path, as the gate refuses their action
        rows = await active_passkeys(
            engine=state.engine,
            audit=state.audit,
            caller=caller,
            now=state.clock(),
            cooloff=timedelta(seconds=RECOVERY_COOLOFF_S),
        )
        if rows:
            raise passkey_not_configured(manual_path=True)
        return {"enrolled": False, "tier": "otp_session", "enrolment": "unavailable"}
    return await state.passkey.step_up_options(caller, payload.action)


@router.post("/step-up", response_model=GrantOut)
async def step_up(
    payload: StepUpIn, request: Request, principal: Principal, state: State
) -> GrantOut:
    service = _service(state)
    credential = payload.credential
    grant = await service.step_up(
        caller_of(request, principal),
        payload.action,
        credential_id=credential.raw_id,
        claimed_id=credential.id,
        client_data=credential.response.client_data_json,
        authenticator_data=credential.response.authenticator_data,
        signature=credential.response.signature,
        user_handle=credential.response.user_handle,
    )
    return GrantOut(grant=grant, action=payload.action, expires_in=GRANT_TTL_S)


# /recovery is declared before /{passkey_id}: a path segment matches the
# parameter route first, and "recovery" is not a passkey id


@router.post("/recovery", status_code=202, response_model=RecoveryOut)
async def start_recovery(request: Request, principal: Principal, state: State) -> RecoveryOut:
    ends = await _service(state).start_recovery(caller_of(request, principal))
    if ends is None:
        raise not_found()
    return RecoveryOut(recovery_ends_at=ends.isoformat())


@router.delete(
    "/recovery",
    response_model=RecoveryCancelOut,
    dependencies=[require_step_up(StepUpAction.RECOVERY_CANCEL)],
)
async def cancel_recovery(
    request: Request, principal: Principal, state: State
) -> RecoveryCancelOut:
    cancelled = await _service(state).cancel_recovery(caller_of(request, principal))
    if not cancelled:
        raise not_found()
    return RecoveryCancelOut(cancelled=cancelled)


@router.delete(
    "/{passkey_id}",
    status_code=204,
    dependencies=[require_step_up(StepUpAction.PASSKEY_REMOVE)],
)
async def remove_passkey(
    passkey_id: uuid.UUID, request: Request, principal: Principal, state: State
) -> Response:
    if not await _service(state).remove(caller_of(request, principal), passkey_id):
        raise not_found()
    return Response(status_code=204)

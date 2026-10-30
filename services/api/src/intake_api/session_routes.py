"""INT-583 — the patient's own sessions and push token: /v1/auth/sessions, /v1/auth/push-token.

The app's "Cihazlarınız" screen (Profilim) lists the devices the account is
signed in on, signs one or all of the others out, and takes "Bu girişi ben
yapmadım" — the report that a sign-in was not the patient's. The same signed-in
session registers the device's APNs token, which the new-device notice
(D35, ``intake_api.sign_in_notice``) is sent to.

**Only the OTP tier's DPoP session reaches these routes.** The caller's device
is the one its session signed in from (``OtpAuthService.resolve_session``): a
push token is always kept for THAT device, and a client cannot name another.
A session from before devices were bound has no device and is answered
``session_unbound``; the next sign-in binds one.

**Declared pre-auth to the consent scan** (the ``/v1/auth`` router's marker).
These routes carry no clinical data in either direction: device ids, sign-in
times, a push token. Account security must not hang on a consent scope, or a
withdrawal would lock the patient out of signing an intruder out.

**The hold.** A session younger than
:data:`~intake_api.device_sessions.SIGN_OUT_OTHERS_HOLD_S` may sign itself out
but not the other devices: whoever just signed in with an intercepted code or a
swapped SIM must not be able to sign the real patient out before the notice is
read. "Bu girişi ben yapmadım" is recorded even then.

**The breach hook.** A ``not_me`` report writes ``auth.session.disowned`` to
the hash chain, counts ``sec_sign_in_disowned_total`` and pages through
``SignInDisowned``: a patient saying a sign-in was not theirs is a presumed
account takeover, and the KVKK 72-hour clock starts when we learn of it
(docs/runbooks/sms-abuse.md, docs/security/incident-runbook.md).

Every change is audited under the patient with ids only (``auth.*`` reads as
ACCOUNT_SECURITY in the patient's own access log).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from functools import partial
from typing import Final, Literal

from fastapi import APIRouter, HTTPException, Request, Response
from prometheus_client import Counter
from pydantic import BaseModel, ConfigDict, Field

from intake_api.consent_guard import pre_auth
from intake_api.device_sessions import (
    APNS_TOKEN_SHAPE,
    SESSION_ID_SHAPE,
    SIGN_OUT_OTHERS_HOLD_S,
    DeviceSession,
)
from intake_api.errors import not_found, otp_auth_unconfigured, unauthorized
from intake_api.otp import CurrentSession, OtpAuthService
from intake_api.state import ApiState, State

__all__ = [
    "SEC_SESSIONS_SIGNED_OUT_TOTAL",
    "SEC_SIGN_IN_DISOWNED_TOTAL",
    "router",
]

router = APIRouter(prefix="/v1/auth", tags=["auth"], dependencies=[pre_auth()])

AUTH_TIER_OTP: Final = "otp"

SEC_SESSIONS_SIGNED_OUT_TOTAL: Final = Counter(
    "sec_sessions_signed_out_total",
    "Devices signed out from the sessions screen, by what was asked for.",
    ("scope",),
)
SEC_SIGN_IN_DISOWNED_TOTAL: Final = Counter(
    "sec_sign_in_disowned_total",
    "Patients reporting that a sign-in to their account was not theirs.",
)


class SessionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    current: bool
    signed_in_at: str
    push: bool


class SessionsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sessions: list[SessionOut]
    #: None when this session may sign the others out now; otherwise when it may
    sign_out_others_after: str | None
    #: whether a push channel is wired: without one no device is told
    notices_on: bool


class SignOutOthersIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    not_me: bool = False


class SignedOutOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signed_out: int


class PushTokenIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform: Literal["ios"]
    #: anchored: pydantic searches a pattern, and an unanchored one admits a
    #: token with anything around it
    token: str = Field(min_length=64, max_length=200, pattern=f"^{APNS_TOKEN_SHAPE.pattern}$")


def _service(request: Request, state: ApiState) -> OtpAuthService:
    request.state.auth_tier = AUTH_TIER_OTP
    if state.auth is None:
        raise otp_auth_unconfigured()
    return state.auth


async def _current(request: Request, service: OtpAuthService) -> CurrentSession:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    token = token.strip()
    if scheme.lower() != "dpop" or not token:
        raise unauthorized()
    return await service.resolve_session(request, token)


def _bound(current: CurrentSession) -> DeviceSession:
    if current.device is None:
        raise HTTPException(status_code=409, detail={"error": "session_unbound"})
    return current.device


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(int(epoch), tz=UTC).isoformat().replace("+00:00", "Z")


def _hold_left(device: DeviceSession, now: float) -> float:
    return max(0.0, device.signed_in_at + SIGN_OUT_OTHERS_HOLD_S - now)


def _too_new(left: float) -> HTTPException:
    return HTTPException(
        status_code=403,
        detail={"error": "session_too_new", "retry_after_s": round(left, 1)},
        headers={"Retry-After": str(int(left) + 1)},
    )


@router.get("/sessions", response_model=SessionsOut)
async def list_sessions(request: Request, state: State) -> SessionsOut:
    service = _service(request, state)
    current = await _current(request, service)
    device = _bound(current)
    store = service.device_sessions
    sessions = await asyncio.to_thread(store.sessions, current.patient_id)
    pushed = await asyncio.to_thread(store.registered_devices, current.patient_id)
    ordered = sorted(sessions, key=lambda s: s.device_ref != device.device_ref)
    left = _hold_left(device, service.now())
    return SessionsOut(
        sessions=[
            SessionOut(
                session_id=s.session_id,
                current=s.device_ref == device.device_ref,
                signed_in_at=_iso(s.signed_in_at),
                push=s.device_ref in pushed,
            )
            for s in ordered
        ],
        sign_out_others_after=_iso(device.signed_in_at + SIGN_OUT_OTHERS_HOLD_S)
        if left > 0
        else None,
        notices_on=service.notices_on,
    )


@router.delete("/sessions/{session_id}", status_code=204)
async def sign_out_session(session_id: str, request: Request, state: State) -> Response:
    service = _service(request, state)
    current = await _current(request, service)
    device = _bound(current)
    if not SESSION_ID_SHAPE.fullmatch(session_id):
        raise not_found()
    store = service.device_sessions
    sessions = await asyncio.to_thread(store.sessions, current.patient_id)
    target = next((s for s in sessions if s.session_id == session_id), None)
    if target is None:
        raise not_found()
    own = target.device_ref == device.device_ref
    if not own and (left := _hold_left(device, service.now())) > 0:
        raise _too_new(left)
    # every sign-out forgets the device, its own included: an intruder's
    # phone that signs itself out must not come back silently (round three)
    await asyncio.to_thread(
        partial(store.sign_out, current.patient_id, target.device_ref, forget=True)
    )
    SEC_SESSIONS_SIGNED_OUT_TOTAL.labels(scope="self" if own else "one").inc()
    await service.audit_account(
        current.patient_id, "auth.session.signed_out_self" if own else "auth.session.signed_out"
    )
    return Response(status_code=204)


@router.post("/sessions/sign-out-others", response_model=SignedOutOut)
async def sign_out_others(payload: SignOutOthersIn, request: Request, state: State) -> SignedOutOut:
    service = _service(request, state)
    current = await _current(request, service)
    store = service.device_sessions
    if payload.not_me:
        # the report is the breach hook, recorded before anything can refuse,
        # the missing device binding included. Each reporting device's first
        # report in a day pages and writes the row; a repeat leaves a
        # non-paging trace (legal B6)
        reporter = current.device.device_ref if current.device is not None else None
        first = await asyncio.to_thread(store.first_disowned_report, current.patient_id, reporter)
        if first:
            SEC_SIGN_IN_DISOWNED_TOTAL.inc()
            await service.audit_account(current.patient_id, "auth.session.disowned")
        else:
            await service.audit_account(current.patient_id, "auth.session.disowned_repeat")
    device = _bound(current)
    if (left := _hold_left(device, service.now())) > 0:
        raise _too_new(left)
    sessions = await asyncio.to_thread(store.sessions, current.patient_id)
    others = [s for s in sessions if s.device_ref != device.device_ref]
    for other in others:
        await asyncio.to_thread(
            partial(store.sign_out, current.patient_id, other.device_ref, forget=True)
        )
    SEC_SESSIONS_SIGNED_OUT_TOTAL.labels(scope="others").inc(len(others))
    await service.audit_account(current.patient_id, "auth.session.signed_out_others")
    return SignedOutOut(signed_out=len(others))


@router.put("/push-token", status_code=204)
async def register_push_token(payload: PushTokenIn, request: Request, state: State) -> Response:
    service = _service(request, state)
    current = await _current(request, service)
    device = _bound(current)
    if not service.notices_on:
        # no channel is wired, so a token would be kept and never used
        raise HTTPException(status_code=503, detail={"error": "push_unavailable"})
    await asyncio.to_thread(
        service.device_sessions.register_push,
        current.patient_id,
        device.device_ref,
        payload.token,
    )
    await service.audit_account(current.patient_id, "auth.push.registered")
    return Response(status_code=204)


@router.delete("/push-token", status_code=204)
async def unregister_push_token(request: Request, state: State) -> Response:
    service = _service(request, state)
    current = await _current(request, service)
    if current.device is not None:
        await asyncio.to_thread(
            service.device_sessions.unregister_push, current.patient_id, current.device.device_ref
        )
        await service.audit_account(current.patient_id, "auth.push.unregistered")
    return Response(status_code=204)

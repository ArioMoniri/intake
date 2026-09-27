"""OTP auth endpoints (INT-131) — the /v1/auth surface over OtpAuthService.

Every route here is the OTP tier: responses are tagged
``X-Intake-Auth-Tier: otp`` (auth.py's middleware reads request.state), and
when the tier is unconfigured (no Redis / no tokenization key) every route
answers 503 fail-closed while the dev-bearer tier keeps carrying the demo.
The dev peek route exists only under INTAKE_DEV_OTP_PEEK=explicit-yes and
is a plain 404 otherwise — indistinguishable from a route that was never
registered."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from intake_api.consent_guard import pre_auth
from intake_api.errors import not_found, otp_auth_unconfigured
from intake_api.otp import OtpAuthService, TokenBundle
from intake_api.state import ApiState, State

__all__ = ["router"]

# Every route here is pre-authentication by nature (no principal exists
# yet) and must SAY so - the INT-038 route scan refuses silent routes,
# and the pre_auth marker is only accepted under this prefix.
router = APIRouter(prefix="/v1/auth", tags=["auth"], dependencies=[pre_auth()])

AUTH_TIER_OTP = "otp"


class AttestKeyIn(BaseModel):
    """An App Attest attestation for one key (INT-344). The attestation object
    runs to several kilobytes, which is why it travels in a body once rather
    than in a header on every call."""

    platform: Literal["ios"]
    key_id: str = Field(max_length=64)
    attestation: str = Field(max_length=16384)
    challenge: str = Field(max_length=64)


class OtpRequestIn(BaseModel):
    phone: str = Field(max_length=32)


class OtpVerifyIn(BaseModel):
    phone: str = Field(max_length=32)
    code: str = Field(max_length=12)


class RefreshIn(BaseModel):
    refresh_token: str = Field(max_length=256)


class TokenBundleOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    patient_id: str
    tenant_id: str


def _service(request: Request, state: ApiState) -> OtpAuthService:
    request.state.auth_tier = AUTH_TIER_OTP
    if state.auth is None:
        raise otp_auth_unconfigured()
    return state.auth


def _bundle_out(bundle: TokenBundle) -> TokenBundleOut:
    return TokenBundleOut(
        access_token=bundle.access_token,
        refresh_token=bundle.refresh_token,
        token_type=bundle.token_type,
        expires_in=bundle.expires_in,
        patient_id=bundle.patient_id,
        tenant_id=bundle.tenant_id,
    )


@router.post("/attest/challenge", status_code=201)
async def attest_challenge(request: Request, state: State) -> dict[str, object]:
    """Single-use attestation nonce (files/10 §2: attestation on OTP request
    and session start binds to a server challenge, not a client value)."""
    return await _service(request, state).issue_challenge()


@router.post("/attest/key", status_code=201)
async def attest_key(payload: AttestKeyIn, request: Request, state: State) -> dict[str, str]:
    """Register an App Attest key (INT-344): the attestation spends one
    challenge; every later OTP call carries an assertion from this key."""
    return await _service(request, state).register_attested_key(
        payload.key_id, payload.attestation, payload.challenge
    )


@router.post("/otp/request", status_code=202)
async def otp_request(payload: OtpRequestIn, request: Request, state: State) -> dict[str, object]:
    return await _service(request, state).request_code(request, payload.phone)


@router.post("/otp/verify", response_model=TokenBundleOut)
async def otp_verify(payload: OtpVerifyIn, request: Request, state: State) -> TokenBundleOut:
    bundle = await _service(request, state).verify_code(request, payload.phone, payload.code)
    return _bundle_out(bundle)


@router.post("/token/refresh", response_model=TokenBundleOut)
async def token_refresh(payload: RefreshIn, request: Request, state: State) -> TokenBundleOut:
    bundle = await _service(request, state).refresh_tokens(request, payload.refresh_token)
    return _bundle_out(bundle)


@router.get("/dev/otp-peek")
async def dev_otp_peek(phone: str, request: Request, state: State) -> dict[str, str]:
    """Dev tier ONLY: INTAKE_DEV_OTP_PEEK=explicit-yes exposes the pending
    code so the flow is walkable without an SMS vendor; otherwise 404."""
    request.state.auth_tier = AUTH_TIER_OTP
    if state.auth is None:
        raise not_found()
    return await state.auth.peek_code(phone)

"""Request authentication: OTP/DPoP accounts (INT-131) + the dev-bearer tier.

Two schemes resolve a principal:

- ``Authorization: DPoP <access_token>`` + a ``DPoP`` proof header — the
  real OTP tier (INT-131). The token is opaque, short-lived (15 min,
  files/10 §2) and bound to the client key's RFC 7638 thumbprint; the proof
  must match method, URL, token hash (``ath``) and be replay-fresh. These
  requests are tagged ``X-Intake-Auth-Tier: otp``.

- ``Authorization: Bearer <token>`` — the INT-197 dev tier: exactly two
  synthetic accounts (:mod:`intake_api.dev_fixture`) behind env tokens
  (`INTAKE_DEV_TOKEN_PATIENT` / `INTAKE_DEV_TOKEN_ADMIN`). No default
  exists in code: with either token unset, every bearer /v1 request
  answers 503 (fail closed). Comparison is constant-time; tokens are never
  logged and never echoed (invariant 6). This tier stays load-bearing for
  the demo and keeps its ``dev`` tag so nobody mistakes it for real auth.

Every request resolves account → tenant → the RLS session context
(``app.tenant_id``); routes downstream see one Principal shape."""

from __future__ import annotations

import hmac
import uuid
from typing import Annotated, cast

from fastapi import Depends, Request

from intake_api.dev_fixture import ADMIN_ACCOUNT, PATIENT_ACCOUNT, DevAccount
from intake_api.errors import dev_auth_unconfigured, forbidden, otp_auth_unconfigured, unauthorized
from intake_api.settings import ApiSettings
from intake_api.state import get_state

__all__ = [
    "AUTH_TIER_HEADER",
    "AUTH_TIER_OTP",
    "Principal",
    "get_settings",
    "require_admin",
    "require_patient",
    "require_principal",
]

AUTH_TIER_HEADER = ("X-Intake-Auth-Tier", "dev")
AUTH_TIER_OTP = "otp"


def get_settings(request: Request) -> ApiSettings:
    return cast(ApiSettings, request.app.state.settings)


def _matches(candidate: str, expected: str | None) -> bool:
    # candidate is never empty here (checked below); an unset/empty expected
    # token therefore never matches — the same fail-closed posture as the
    # 503 guard, kept total instead of branching
    return hmac.compare_digest(candidate.encode("utf-8"), (expected or "").encode("utf-8"))


async def require_principal(request: Request) -> DevAccount:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    token = token.strip()
    if scheme.lower() == "dpop" and token:
        # INT-131 tier: opaque access token + per-request DPoP proof
        state = get_state(request)
        if state.auth is None:
            raise otp_auth_unconfigured()
        account = await state.auth.resolve_access(request, token)
        request.state.auth_tier = AUTH_TIER_OTP
        return account
    settings = get_settings(request)
    if not settings.dev_auth_configured:
        raise dev_auth_unconfigured()
    if scheme.lower() != "bearer" or not token:
        raise unauthorized()
    if _matches(token, settings.token_patient):
        return PATIENT_ACCOUNT
    if _matches(token, settings.token_admin):
        return ADMIN_ACCOUNT
    raise unauthorized()


Principal = Annotated[DevAccount, Depends(require_principal)]


def require_patient(principal: DevAccount) -> tuple[DevAccount, uuid.UUID]:
    """Writes are the patient's alone in this slice (02 §5.1: sending and
    creating are the patient's call; the clinic side only reads shares).
    Returns the account together with its non-null patient row id."""
    if principal.role != "patient" or principal.patient_id is None:
        raise forbidden()
    return principal, principal.patient_id


def require_admin(principal: DevAccount) -> DevAccount:
    """The console side of the same door (INT-241 admin aggregates).

    Symmetric with :func:`require_patient` and, like it, the dev-tier stand-in
    for the files/08 §2.1 role set — the console roles arrive with OIDC
    (INT-131/INT-180). What matters already: the tenant a caller may read is
    the tenant on their own principal, never one they name (files/08 §8), and
    a patient token cannot reach a tenant-wide aggregate at all.
    """
    if principal.role != "clinic_admin":
        raise forbidden()
    return principal

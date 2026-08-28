"""Dev-bearer auth (INT-197) — EXPLICITLY the dev tier; real OIDC is INT-131.

Exactly two synthetic accounts (:mod:`intake_api.dev_fixture`), each behind
one bearer token read from the environment (`INTAKE_DEV_TOKEN_PATIENT` /
`INTAKE_DEV_TOKEN_ADMIN`). No default exists in code: with either token
unset, every /v1 request answers 503 (fail closed) and readiness reports
``dev_auth: error``. Comparison is constant-time; tokens are never logged
and never echoed (invariant 6).

Every request resolves account → tenant → the RLS session context
(``app.tenant_id``), which is the same resolution shape INT-131 will feed
from OIDC claims.
"""

from __future__ import annotations

import hmac
import uuid
from typing import Annotated, cast

from fastapi import Depends, Request

from intake_api.dev_fixture import ADMIN_ACCOUNT, PATIENT_ACCOUNT, DevAccount
from intake_api.errors import dev_auth_unconfigured, forbidden, unauthorized
from intake_api.settings import ApiSettings

__all__ = ["AUTH_TIER_HEADER", "Principal", "get_settings", "require_patient", "require_principal"]

AUTH_TIER_HEADER = ("X-Intake-Auth-Tier", "dev")


def get_settings(request: Request) -> ApiSettings:
    return cast(ApiSettings, request.app.state.settings)


def _matches(candidate: str, expected: str | None) -> bool:
    # candidate is never empty here (checked below); an unset/empty expected
    # token therefore never matches — the same fail-closed posture as the
    # 503 guard, kept total instead of branching
    return hmac.compare_digest(candidate.encode("utf-8"), (expected or "").encode("utf-8"))


async def require_principal(request: Request) -> DevAccount:
    settings = get_settings(request)
    if not settings.dev_auth_configured:
        raise dev_auth_unconfigured()
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    token = token.strip()
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

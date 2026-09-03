"""Console request guards (INT-180; files/08 §2.3, §8 rule a).

Every ``/admin`` request passes three gates before a handler sees it, in this
order and for this reason:

1. **Is the console wired at all?** No claims verifier means 503 — the console
   authenticates nobody rather than falling back to a weaker tier.
2. **Did the request come from an admitted address?** files/08 §2.3's
   allow-list, checked against the transport peer only. It is checked BEFORE
   the token so a stolen token presented from anywhere is refused without the
   verifier ever being asked, and so the refusal reveals nothing about whether
   the token was good.
3. **Who is the caller, and may they reach this route?** Roles are intersected
   with the files/08 §2.1 set, tenant scope comes from the claim, and
   ``?tenant=`` is refused below ``platform_owner``.

The audit wrapper sits outside all three in :mod:`intake_api.admin.routes`, so
a refusal at any gate is still an audited action — a refused admin request is
exactly the request an investigator wants to see.
"""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Request
from intake_platform.admin import (
    AdminPrincipal,
    AdminWiring,
    ClaimsRejected,
    PrincipalRefused,
    effective_tenant,
    principal_from_claims,
)

from intake_api.errors import (
    admin_console_unconfigured,
    admin_refused,
    source_ip_refused,
    unauthorized,
)

__all__ = ["AdminCaller", "Wiring", "get_admin_wiring", "resolve_caller"]


def get_admin_wiring(request: Request) -> AdminWiring:
    wiring = cast(AdminWiring | None, getattr(request.app.state, "admin", None))
    if wiring is None:
        raise admin_console_unconfigured()
    return wiring


Wiring = Annotated[AdminWiring, Depends(get_admin_wiring)]


def _client_host(request: Request) -> str:
    """The transport peer, and only that.

    ``X-Forwarded-For`` is attacker-controlled unless a trusted-proxy hop
    count is configured; none is, so the header is not read. An allow-list
    that trusts a spoofable header is not an allow-list.
    """
    client = request.client
    return client.host if client is not None else ""


class AdminCaller:
    """The resolved caller plus the tenant their request is scoped to."""

    __slots__ = ("principal", "tenant")

    def __init__(self, principal: AdminPrincipal, tenant: str | None) -> None:
        self.principal = principal
        self.tenant = tenant


def resolve_caller(request: Request, wiring: AdminWiring) -> AdminCaller:
    if not wiring.ip_allowlist.permits(_client_host(request)):
        raise source_ip_refused()
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise unauthorized()
    try:
        claims = wiring.claims.verify(token.strip())
    except ClaimsRejected:
        raise unauthorized() from None
    try:
        principal = principal_from_claims(claims, source_ip=_client_host(request))
        tenant = effective_tenant(principal, request.query_params.get("tenant"))
    except PrincipalRefused as refusal:
        raise admin_refused(refusal.code) from None
    return AdminCaller(principal, tenant)

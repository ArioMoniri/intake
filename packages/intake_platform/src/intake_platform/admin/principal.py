"""The console principal, resolved from an OIDC claim set (INT-180).

**Keycloak is behind a seam.** :class:`AdminClaimsVerifier` is the whole
contract: bytes in, a verified claim set out. No implementation ships in this
package — validating a Keycloak signature needs a JWKS client and a JWT
library, neither of which is a dependency of this repository, and hand-rolling
JWS verification inside the highest-privilege surface in the system is not a
trade this issue is willing to make. With no verifier wired the console
answers 503 and authenticates nobody, which is the fail-closed direction;
tests drive a recorded claim set through the same seam.

**Tenant scope comes from the claim, never from the query string** (files/08
§8 rule a). ``?tenant=`` is refused for every role except ``platform_owner``,
whose own claim carries no tenant precisely because its scope is all of them.

**Roles are intersected, not trusted.** A Keycloak realm carries roles that
are not console roles (`clinician`, `patient`); those are dropped, and a token
left with none is refused rather than admitted as an empty-privilege session.

**The second factor is checked here, once, for every verifier** (INT-365).
Every claim set reaches the console through this function, whichever
verifier produced it, so this is the one place a token issued without the
factors files/08 §2.3 demands can be refused. The check runs as soon as the
console roles are known, because the roles decide what counts as enough.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from intake_platform.admin.four_eyes import ActorBlock
from intake_platform.admin.roles import ADMIN_ROLES, AdminRole
from intake_platform.admin.second_factor import require_second_factor

__all__ = [
    "AdminClaimsVerifier",
    "AdminPrincipal",
    "ClaimsRejected",
    "MalformedClaims",
    "NoConsoleRole",
    "PrincipalRefused",
    "RoleNotPermitted",
    "TenantScopeRefused",
    "effective_tenant",
    "principal_from_claims",
]

#: The same id shape the audit chain accepts, checked here so a broken IdP
#: mapper is refused at the door rather than raising deep inside an append.
#: Free text in a claim is how narrative reaches a log (invariant 6).
_ID_SHAPE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@-]{0,127}")

_ROLE_VALUES = {role.value: role for role in ADMIN_ROLES}


class ClaimsRejected(Exception):
    """The verifier would not vouch for the token — 401, not 403."""


class PrincipalRefused(Exception):
    """A verified caller the console will not serve. ``code`` reaches the
    response body; it is a code and never narrative (invariant 6)."""

    code = "forbidden"


class NoConsoleRole(PrincipalRefused):
    """Verified, but holds no files/08 §2.1 role."""


class MalformedClaims(PrincipalRefused):
    """Verified, but a claim the audit row depends on is missing or shaped
    like prose rather than an identifier."""


class RoleNotPermitted(PrincipalRefused):
    """Holds a console role, but not one this route admits."""


class TenantScopeRefused(PrincipalRefused):
    code = "tenant_scope_refused"


class AdminClaimsVerifier(Protocol):
    def verify(self, token: str) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class AdminPrincipal:
    subject: str
    roles: frozenset[AdminRole]
    org: str
    tenant: str | None
    session_id: str
    authenticator_aaguid: str
    credential_id: str
    source_ip: str

    def actor_block(self, role: AdminRole) -> ActorBlock:
        """The files/08 §8.1 actor block for one of the caller's roles."""
        return ActorBlock(
            subject=self.subject,
            role=role,
            org=self.org,
            authenticator_aaguid=self.authenticator_aaguid,
            credential_id=self.credential_id,
            session_id=self.session_id,
        )

    def first_permitted(self, permitted: frozenset[AdminRole]) -> AdminRole | None:
        """The role under which this caller reaches a route, or ``None``.

        Deterministic — registry order — so the audited role does not depend
        on the order Keycloak happened to list the claims in. Total rather
        than raising, because the caller must audit the refusal before
        turning it into a response.
        """
        for role in ADMIN_ROLES:
            if role in self.roles and role in permitted:
                return role
        return None


def _required_id(claims: Mapping[str, Any], key: str) -> str:
    value = claims.get(key)
    if not isinstance(value, str) or not _ID_SHAPE.fullmatch(value):
        raise MalformedClaims(f"claim {key!r} is absent or not id-shaped")
    return value


def _id_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and _ID_SHAPE.fullmatch(value) else None


def principal_from_claims(claims: Mapping[str, Any], *, source_ip: str) -> AdminPrincipal:
    realm_access = claims.get("realm_access")
    raw_roles = realm_access.get("roles", ()) if isinstance(realm_access, Mapping) else ()
    roles = frozenset(
        _ROLE_VALUES[name] for name in raw_roles if isinstance(name, str) and name in _ROLE_VALUES
    )
    if not roles:
        raise NoConsoleRole("the token carries no files/08 §2.1 console role")
    require_second_factor(claims.get("amr"), roles, subject=_id_or_none(claims.get("sub")))
    tenant = claims.get("tenant")
    if tenant is not None and (not isinstance(tenant, str) or not _ID_SHAPE.fullmatch(tenant)):
        raise MalformedClaims("claim 'tenant' is not id-shaped")
    return AdminPrincipal(
        subject=_required_id(claims, "sub"),
        roles=roles,
        org=_required_id(claims, "org"),
        tenant=tenant,
        session_id=_required_id(claims, "sid"),
        authenticator_aaguid=_required_id(claims, "aaguid"),
        credential_id=_required_id(claims, "credential_id"),
        source_ip=source_ip,
    )


def effective_tenant(principal: AdminPrincipal, requested: str | None) -> str | None:
    """files/08 §8 rule (a). ``platform_owner`` is the only role that may name
    a tenant; for everyone else the claim decides and naming one is refused
    outright rather than ignored — an ignored parameter reads as honoured."""
    if requested is None:
        return principal.tenant
    if AdminRole.PLATFORM_OWNER not in principal.roles:
        raise TenantScopeRefused("tenant scope comes from the OIDC claim, not the query string")
    if not _ID_SHAPE.fullmatch(requested):
        raise MalformedClaims("requested tenant is not id-shaped")
    return requested

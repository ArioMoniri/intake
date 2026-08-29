"""INT-038 — consent_guard: declarative per-route consent scopes.

A route DECLARES the consent scopes it operates under; the guard ENFORCES
the subject-level ones and the route-table scan (tests/legal) fails on any
data route that declares nothing — the acceptance's "every data route
declares scopes". Two declaration slots, because two enforcement shapes
exist in this API:

- ``enforced``: checked here, before the endpoint body, against the
  REQUESTING patient's live consents in a fresh RLS tenant session. A
  clinic-admin principal has no patient row, and the record it touches is
  resolved inside the endpoint — so for non-patient principals the guard
  defers to the route's record-level checks (which call ensure_consent
  below and are therefore staleness-aware too).
- ``conditional``: declared for the scan, enforced inside the endpoint
  where the condition lives (role, record ownership, send-vs-draft). The
  scan sees the full contract either way.

Refusals are a typed 403 naming the missing purpose id and NOTHING else
(invariant 6). A stale grant — the docs/legal text moved since it was
given — is treated as absent and audited as ``consent.stale`` (re-prompt on
change); a plain absence is not audited, because a refused read is not a
read (tests/api/test_visits.py pins that).

**INT-223 — the age/guardian gate runs here too**, not beside it. Before the
ledger is consulted, ``ensure_consent`` resolves the subject's age context
(``intake_api.age_context``) and asks the rules engine
(``intake_platform.consent.minors``) which actor must hold the consent. A
minor's own grant therefore cannot unlock a scope the guardian has to hold,
and there is no second refusal path to keep in step with this one
(invariant 4). The refusal is the engine's own code in a 403 carrying
``{error, scope}`` and nothing derived from the date of birth (invariant 6).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import Depends, FastAPI, params
from fastapi.routing import APIRoute
from intake_platform.consent import consent_state, resolve_scope
from intake_platform.consent.minors import resolve_consent_actor
from sqlalchemy.ext.asyncio import AsyncSession

from intake_api.auth import Principal
from intake_api.db import tenant_session
from intake_api.errors import age_gate_refused, consent_required
from intake_api.state import State

if TYPE_CHECKING:
    from intake_api.state import ApiState

__all__ = [
    "CONSENT_MANAGEMENT_PREFIX",
    "META_ROUTES",
    "PRE_AUTH_PREFIX",
    "REFERENCE_DATA_PREFIX",
    "ConsentGuard",
    "ConsentPolicy",
    "consent_management",
    "consent_management_routes",
    "ensure_age_actor",
    "ensure_consent",
    "pre_auth",
    "pre_auth_routes",
    "reference_data",
    "reference_data_routes",
    "require_scopes",
    "route_policies",
    "unguarded_data_routes",
]

# The invariant-15 service-meta surface plus FastAPI's own schema routes —
# the ONLY paths allowed to carry no consent declaration.
META_ROUTES = frozenset(
    {
        "/healthz",
        "/readyz",
        "/metrics",
        "/version",
        "/openapi.json",
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
    }
)


@dataclass(frozen=True)
class ConsentPolicy:
    """One route's declared consent contract."""

    enforced: tuple[str, ...]
    conditional: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.enforced and not self.conditional:
            raise ValueError("a consent policy must declare at least one scope")
        for scope in self.enforced + self.conditional:
            resolve_scope(scope)  # typos and de-listed purposes fail at import


async def ensure_age_actor(
    session: AsyncSession,
    *,
    state: ApiState,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    scope: str,
) -> None:
    """INT-223 — the age axis of the same enforcement point.

    Refuses when the rules engine says this subject may not be served on the
    age axis at all: an under-18 whose guardian must hold the consent, a date
    of birth that is not verified, a jurisdiction we do not encode. Runs
    BEFORE the ledger so a minor's own grant cannot answer for the guardian's.
    """
    context = await state.age_context.resolve(session, tenant_id=tenant_id, patient_id=patient_id)
    decision = resolve_consent_actor(context, scope=scope, on=datetime.now(UTC).date())
    if decision.permitted:
        return
    # refusal_code is always present on a refusal (the engine sets both
    # together); the fallback keeps the refusal total rather than optional.
    raise age_gate_refused(decision.refusal_code or "guardian_consent_required", scope)


async def ensure_consent(
    session: AsyncSession,
    *,
    state: ApiState,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    scope: str,
    actor: str,
) -> None:
    """The one enforcement point (invariant 4): route code and the guard
    both come through here, so staleness handling — and, since INT-223, the
    age/guardian gate — cannot fork."""
    await ensure_age_actor(
        session, state=state, tenant_id=tenant_id, patient_id=patient_id, scope=scope
    )
    decision = await consent_state(
        session,
        tenant_id=tenant_id,
        patient_id=patient_id,
        scope=scope,
        catalog=state.consent_catalog,
    )
    if decision.allowed:
        return
    if decision.reason == "stale":
        # the grant exists but binds a superseded text: audit the fact —
        # it is the re-prompt trigger — then refuse exactly like an absence
        await state.audit.record(
            actor=actor,
            action="consent.stale",
            resource_ref=f"patient:{patient_id}",
            consent_scope=f"scope:{scope}",
        )
    raise consent_required(scope)


class ConsentGuard:
    """The dependency a route mounts via require_scopes(...)."""

    def __init__(self, policy: ConsentPolicy) -> None:
        self.policy = policy

    async def __call__(self, principal: Principal, state: State) -> None:
        if principal.patient_id is None:
            return  # record-level checks inside the endpoint cover non-subjects
        async with tenant_session(state.engine, principal.tenant_id) as session:
            for scope in self.policy.enforced:
                await ensure_consent(
                    session,
                    state=state,
                    tenant_id=principal.tenant_id,
                    patient_id=principal.patient_id,
                    scope=scope,
                    actor=principal.account_id,
                )


def require_scopes(*enforced: str, conditional: tuple[str, ...] = ()) -> params.Depends:
    """Declare (and enforce) a route's consent scopes:
    ``dependencies=[require_scopes("core")]`` on the route decorator."""
    dependency: params.Depends = Depends(
        ConsentGuard(ConsentPolicy(tuple(enforced), tuple(conditional)))
    )
    return dependency


class PreAuthDeclaration:
    """Explicit declaration that a route runs BEFORE any principal exists
    (INT-131 onboarding: OTP, attestation, refresh). Consent scopes attach
    to an authenticated subject, so these routes cannot enforce one — but
    they may not stay silent either: the scan accepts this marker ONLY under
    PRE_AUTH_PREFIX, so a data route elsewhere cannot borrow it."""

    async def __call__(self) -> None:
        return


#: The only prefix where a pre-auth declaration is accepted by the scan.
PRE_AUTH_PREFIX = "/v1/auth"


def pre_auth() -> params.Depends:
    """Declare a route as pre-authentication (see PreAuthDeclaration)."""
    dependency: params.Depends = Depends(PreAuthDeclaration())
    return dependency


class ConsentManagementDeclaration:
    """Explicit declaration that a route IS the consent-management surface
    (INT-232): its subject matter is the consent ledger itself, so requiring
    a consent scope would be circular — nobody can need a consent to grant
    their first consent, and a snapshot that 403s on the very staleness it
    exists to report could never trigger a re-prompt. Same class as
    pre_auth: the route cannot enforce a scope, but it may not stay silent
    either — the scan accepts this marker ONLY under
    CONSENT_MANAGEMENT_PREFIX (as a path segment, not a substring), so a
    data route elsewhere cannot borrow it."""

    async def __call__(self) -> None:
        return


#: The only prefix where a consent-management declaration is accepted.
CONSENT_MANAGEMENT_PREFIX = "/v1/consents"


def consent_management() -> params.Depends:
    """Declare a route as consent management (see
    ConsentManagementDeclaration)."""
    dependency: params.Depends = Depends(ConsentManagementDeclaration())
    return dependency


class ReferenceDataDeclaration:
    """Explicit declaration that a route serves REFERENCE DATA only
    (INT-134): a versioned projection of a committed artefact — the branch
    taxonomy — that contains no patient data at all. Consent scopes attach
    to a data subject's clinical data; demanding one here would over-claim
    (and would block the picker before the patient has granted anything).
    Same class as pre_auth and consent_management: the route cannot enforce
    a scope, but it may not stay silent either — the scan accepts this
    marker ONLY under REFERENCE_DATA_PREFIX (as a path segment, not a
    substring), so a data route elsewhere cannot borrow it. Authentication
    is unchanged: the route still requires a principal."""

    async def __call__(self) -> None:
        return


#: The only prefix where a reference-data declaration is accepted.
REFERENCE_DATA_PREFIX = "/v1/taxonomy"


def reference_data() -> params.Depends:
    """Declare a route as reference data (see ReferenceDataDeclaration)."""
    dependency: params.Depends = Depends(ReferenceDataDeclaration())
    return dependency


def _policy_of(route: APIRoute) -> ConsentPolicy | None:
    for dependency in route.dependencies:
        call = dependency.dependency
        if isinstance(call, ConsentGuard):
            return call.policy
    return None


def _iter_api_routes(routes: Iterable[object], prefix: str = "") -> Iterator[tuple[str, APIRoute]]:
    """Walk the route table INCLUDING nested routers: FastAPI keeps
    include_router() results as lazy wrapper entries (each holding the
    original router and its include prefix), so a flat scan would miss
    every /v1 route — exactly the routes the scan exists for."""
    for route in routes:
        if isinstance(route, APIRoute):
            yield prefix + route.path, route
            continue
        inner = getattr(route, "original_router", None)
        context = getattr(route, "include_context", None)
        if inner is None and hasattr(route, "routes"):
            inner = route
        if inner is not None:
            child_prefix = prefix + str(getattr(context, "prefix", "") or "")
            inner_routes = getattr(inner, "routes", [])
            yield from _iter_api_routes(list(inner_routes), child_prefix)


def route_policies(app: FastAPI) -> dict[tuple[str, str], ConsentPolicy]:
    """(method, path) → declared policy, for the scan and for review."""
    policies: dict[tuple[str, str], ConsentPolicy] = {}
    for path, route in _iter_api_routes(list(app.routes)):
        policy = _policy_of(route)
        if policy is None:
            continue
        for method in sorted(route.methods or ()):
            policies[(method, path)] = policy
    return policies


def _is_pre_auth(route: APIRoute) -> bool:
    return any(
        isinstance(dependency.dependency, PreAuthDeclaration) for dependency in route.dependencies
    )


def _is_consent_management(route: APIRoute) -> bool:
    return any(
        isinstance(dependency.dependency, ConsentManagementDeclaration)
        for dependency in route.dependencies
    )


def _is_reference_data(route: APIRoute) -> bool:
    return any(
        isinstance(dependency.dependency, ReferenceDataDeclaration)
        for dependency in route.dependencies
    )


def _under_consent_management_prefix(path: str) -> bool:
    """Segment-boundary match: ``/v1/consents`` and ``/v1/consents/...``
    qualify; a lookalike like ``/v1/consentsish`` does not."""
    return path == CONSENT_MANAGEMENT_PREFIX or path.startswith(CONSENT_MANAGEMENT_PREFIX + "/")


def _under_reference_data_prefix(path: str) -> bool:
    """Segment-boundary match, same rule as the consent-management cage."""
    return path == REFERENCE_DATA_PREFIX or path.startswith(REFERENCE_DATA_PREFIX + "/")


def pre_auth_routes(app: FastAPI) -> list[str]:
    """Every route carrying the pre-auth declaration, for the pin test."""
    marked: list[str] = []
    for path, route in _iter_api_routes(list(app.routes)):
        if _is_pre_auth(route):
            for method in sorted(route.methods or ()):
                marked.append(f"{method} {path}")
    return sorted(marked)


def consent_management_routes(app: FastAPI) -> list[str]:
    """Every route carrying the consent-management declaration, for the pin
    test (INT-232) — reported wherever it appears; whether the scan ACCEPTS
    it is unguarded_data_routes' prefix rule."""
    marked: list[str] = []
    for path, route in _iter_api_routes(list(app.routes)):
        if _is_consent_management(route):
            for method in sorted(route.methods or ()):
                marked.append(f"{method} {path}")
    return sorted(marked)


def reference_data_routes(app: FastAPI) -> list[str]:
    """Every route carrying the reference-data declaration, for the pin
    test (INT-134) — reported wherever it appears; whether the scan ACCEPTS
    it is unguarded_data_routes' prefix rule."""
    marked: list[str] = []
    for path, route in _iter_api_routes(list(app.routes)):
        if _is_reference_data(route):
            for method in sorted(route.methods or ()):
                marked.append(f"{method} {path}")
    return sorted(marked)


def unguarded_data_routes(app: FastAPI) -> list[str]:
    """Every data route that declares neither consent scopes nor a valid
    marker — the scan test asserts this list is empty, so a new route cannot
    land undeclared (silence always fails). Three markers exist, each caged
    to its prefix: pre_auth under PRE_AUTH_PREFIX (INT-131 bootstrap, no
    principal yet), consent_management under CONSENT_MANAGEMENT_PREFIX
    (INT-232, the routes ABOUT consent) and reference_data under
    REFERENCE_DATA_PREFIX (INT-134, versioned artefact projections holding
    no patient data). Any marker outside its prefix does NOT count as a
    declaration (the route is reported here instead)."""
    missing: list[str] = []
    for path, route in _iter_api_routes(list(app.routes)):
        if path in META_ROUTES:
            continue
        if _is_pre_auth(route) and path.startswith(PRE_AUTH_PREFIX):
            continue
        if _is_consent_management(route) and _under_consent_management_prefix(path):
            continue
        if _is_reference_data(route) and _under_reference_data_prefix(path):
            continue
        if _policy_of(route) is None:
            for method in sorted(route.methods or ()):
                missing.append(f"{method} {path}")
    return missing

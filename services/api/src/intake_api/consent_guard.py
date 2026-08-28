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
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import Depends, FastAPI, params
from fastapi.routing import APIRoute
from intake_platform.consent import consent_state, resolve_scope
from sqlalchemy.ext.asyncio import AsyncSession

from intake_api.auth import Principal
from intake_api.db import tenant_session
from intake_api.errors import consent_required
from intake_api.state import State

if TYPE_CHECKING:
    from intake_api.state import ApiState

__all__ = [
    "META_ROUTES",
    "ConsentGuard",
    "ConsentPolicy",
    "ensure_consent",
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
    both come through here, so staleness handling cannot fork."""
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


def unguarded_data_routes(app: FastAPI) -> list[str]:
    """Every data route that declares no consent scopes — the scan test
    asserts this list is empty, so a new route cannot land undeclared."""
    missing: list[str] = []
    for path, route in _iter_api_routes(list(app.routes)):
        if path in META_ROUTES:
            continue
        if _policy_of(route) is None:
            for method in sorted(route.methods or ()):
                missing.append(f"{method} {path}")
    return missing

"""The ``/admin`` router, BUILT from the descriptor table (INT-180).

No route is declared here with a decorator. :data:`ADMIN_ROUTES` is walked and
each descriptor is registered through one wrapper, which means three things
hold structurally rather than by review:

- **Every route is audited.** The wrapper opens
  :class:`~intake_platform.admin.audit.AdminActionRecord` before the guards
  run and closes it after the handler returns or raises, so a refusal is
  audited exactly like a success. A route cannot exist without an audit
  action, because the descriptor that creates it carries one.
- **Every mutating route is a registered DangerousAction.** The descriptor
  carries the id and ``tests/admin/test_admin_audit.py`` derives the check
  from FastAPI's served route table.
- **The audited-route list is derived, never maintained.** The test reads
  ``app.routes``; if a handler were added by any other means it would appear
  there, match no descriptor, and fail the suite.

Bodies are parsed inside the audited block on purpose. FastAPI's own request
validation runs before dependencies resolve, so a malformed body would answer
422 with nothing on the chain — an unaudited admin request, which is the hole
this issue exists to close.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from intake_platform.admin import (
    ADMIN_ROUTES,
    BREAK_GLASS_GRANT_TTL,
    AdminActionRecord,
    AdminRole,
    AdminRoute,
    AdminWiring,
    BreakGlassReason,
    BreakGlassRefused,
    FourEyesRefused,
    RoleNotPermitted,
    build_break_glass_justification,
    dangerous_action,
)
from intake_platform.admin.four_eyes import SelfApproval
from intake_platform.admin.metrics import (
    ADMIN_BREAK_GLASS_OPENED_TOTAL,
    ADMIN_FOUR_EYES_SELF_APPROVAL_ATTEMPT_TOTAL,
    ADMIN_MODEL_BENCHMARK_REQUESTED_TOTAL,
    ADMIN_PENDING_ACTION_EXPIRED_TOTAL,
    SEC_BREAK_GLASS_TOTAL,
)
from intake_platform.compliance import AuditSearchQuery
from intake_platform.compliance.audit_search import AuditSearchContentRefused
from intake_probes.console import BenchmarkKind, BenchmarkRefused

from intake_api.admin import compliance_source, views
from intake_api.admin.deps import AdminCaller, get_admin_wiring, resolve_caller
from intake_api.admin.models_source import (
    load_models_module,
    resolve_benchmark,
    run_benchmark,
)
from intake_api.admin.ops_console import load_ops_console
from intake_api.admin.reliability_console import load_reliability_console
from intake_api.consent_guard import administrative_action
from intake_api.db import tenant_session
from intake_api.errors import (
    admin_refused,
    benchmark_refused,
    break_glass_refused,
    compliance_query_refused,
    four_eyes_refused,
    not_found,
)
from intake_api.state import get_state

__all__ = ["router"]

router = APIRouter(tags=["admin"])

Handler = Callable[[Request, AdminCaller, AdminWiring, AdminRole], Awaitable[dict[str, Any]]]

#: The audit actor when the caller could not be resolved. The chain's field
#: set is id-shaped, so an unresolved caller is recorded as an unresolved
#: caller rather than by echoing whatever the token claimed to be.
_UNRESOLVED_ACTOR = "admin:unresolved"


async def _json_body(request: Request) -> Mapping[str, Any]:
    try:
        payload = json.loads(await request.body())
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise break_glass_refused("body_not_json") from None
    if not isinstance(payload, dict):
        raise break_glass_refused("body_not_an_object")
    return payload


def _text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise break_glass_refused(f"{key}_required")
    return value


def _sweep_expired(wiring: AdminWiring) -> None:
    expired = wiring.four_eyes.expire_due()
    if expired:
        ADMIN_PENDING_ACTION_EXPIRED_TOTAL.inc(expired)


async def _whoami(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    return views.whoami(caller.principal, caller.tenant)


async def _roles(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    return views.role_registry_view()


async def _actions(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    return views.action_registry_view()


async def _break_glass_open(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    _sweep_expired(wiring)
    action = dangerous_action("admin.break_glass.open")
    payload = await _json_body(request)
    if caller.tenant is None:
        # platform_owner's claim carries no tenant, so it must name one; the
        # deployment question (files/08 §2.6) is answered per tenant or not
        # at all
        raise break_glass_refused("tenant_required")
    deployment = wiring.deployments.get(caller.tenant)
    if deployment is None:
        raise break_glass_refused("tenant_deployment_unknown")
    try:
        reason = BreakGlassReason(_text(payload, "reason_class"))
    except ValueError:
        raise break_glass_refused("reason_class_unknown") from None
    controller_ref = payload.get("controller_instruction_ref")
    try:
        justification = build_break_glass_justification(
            reason_class=reason,
            free_text=_text(payload, "justification"),
            controller_instruction_ref=controller_ref if isinstance(controller_ref, str) else None,
            deployment=deployment,
        )
        pending = wiring.four_eyes.open(
            action=action,
            actor=caller.principal.actor_block(role),
            target_ref=_text(payload, "session_ref"),
            justification=justification,
            evidence={"tenant": caller.tenant, "deployment": deployment.value},
            ttl=BREAK_GLASS_GRANT_TTL,
        )
    except BreakGlassRefused as refusal:
        raise break_glass_refused(refusal.code) from None
    except FourEyesRefused as refusal:
        raise four_eyes_refused(refusal.code) from None
    SEC_BREAK_GLASS_TOTAL.inc()
    ADMIN_BREAK_GLASS_OPENED_TOTAL.labels(
        actor=caller.principal.subject, reason_class=reason.value
    ).inc()
    return views.pending_view(pending)


async def _break_glass_brief(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    _sweep_expired(wiring)
    try:
        brief = wiring.four_eyes.brief(request.path_params["action_id"])
    except FourEyesRefused:
        raise not_found() from None
    return views.brief_view(brief)


async def _break_glass_approve(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    _sweep_expired(wiring)
    payload = await _json_body(request)
    try:
        approved = wiring.four_eyes.approve(
            request.path_params["action_id"],
            approver=caller.principal.actor_block(role),
            assertion_id=_text(payload, "assertion_id"),
        )
    except SelfApproval as refusal:
        # files/08 §5: an intrusion signal, not a hygiene metric.
        ADMIN_FOUR_EYES_SELF_APPROVAL_ATTEMPT_TOTAL.inc()
        raise four_eyes_refused(refusal.code) from None
    except FourEyesRefused as refusal:
        if refusal.code == "four_eyes_unknown":
            raise not_found() from None
        raise four_eyes_refused(refusal.code) from None
    return views.pending_view(approved)


async def _models(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    return views.models_module_view(load_models_module())


async def _ops(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    # INT-351. Prometheus and the registry, server-side; the query table is the
    # API's own and nothing in the request reaches it (files/08 §0b F1). The
    # composite is synchronous httpx, so it runs off the event loop.
    return await run_in_threadpool(load_ops_console, datetime.now(UTC))


async def _reliability(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    # INT-181. The SLO files, Prometheus, the registry and the probe sweep,
    # server-side; every query derives from committed files and nothing in the
    # request reaches one (files/08 §0b F1). Synchronous httpx, off the loop.
    return await run_in_threadpool(load_reliability_console, datetime.now(UTC))


#: The closed body shape of a benchmark trigger. Anything else is refused
#: rather than ignored: invariant 6 says no patient data reaches this surface,
#: and a field the server silently drops is a field nobody notices carrying
#: one. Two keys, both operator vocabulary, neither free text.
_BENCHMARK_FIELDS = frozenset({"kind", "corpus_id"})


async def _models_benchmark(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    component = request.path_params["component"]
    payload = await _json_body(request)
    unexpected = sorted(set(payload) - _BENCHMARK_FIELDS)
    if unexpected:
        # the refusal names the KEYS, never their values — echoing a rejected
        # value is how a rejected value reaches a log (invariant 6)
        raise benchmark_refused(
            "unexpected_field",
            f"the benchmark trigger takes {sorted(_BENCHMARK_FIELDS)} and nothing else; "
            f"refused: {unexpected}",
        )
    try:
        kind = BenchmarkKind(_text(payload, "kind"))
    except ValueError:
        raise benchmark_refused(
            "unknown_kind",
            f"kind must be one of {[k.value for k in BenchmarkKind]}",
        ) from None
    corpus_id = payload.get("corpus_id")
    try:
        plan = resolve_benchmark(component, kind, corpus_id if isinstance(corpus_id, str) else None)
    except BenchmarkRefused as refusal:
        ADMIN_MODEL_BENCHMARK_REQUESTED_TOTAL.labels(
            actor=caller.principal.subject, kind=kind.value, outcome="refused"
        ).inc()
        raise benchmark_refused(refusal.code, refusal.detail) from None
    ADMIN_MODEL_BENCHMARK_REQUESTED_TOTAL.labels(
        actor=caller.principal.subject, kind=kind.value, outcome="planned"
    ).inc()
    executed = run_benchmark(plan)
    if executed is None:
        return views.benchmark_plan_view(plan)
    return views.benchmark_result_view(executed)


# --------------------------------------------------------------------------
# INT-189 — the compliance module (files/08 §4). All reads; the tenant-scoped
# ones (consents, DSAR, evidence) take the tenant from the resolved caller,
# never from a query string (files/08 §8 rule a; effective_tenant already
# refused ?tenant= below platform_owner).
# --------------------------------------------------------------------------


def _tenant_scope(caller: AdminCaller) -> uuid.UUID | None:
    """The DB tenant a scoped read runs against, or ``None`` for no scope.

    Production hands a tenant claim that is the tenant's UUID; a claim that is
    absent (``platform_owner`` names one via ``?tenant=`` or sees nothing) or
    does not resolve to a UUID scopes the read to **no rows** rather than being
    refused. That is fail-safe for a read: the wrong direction is returning
    another tenant's rows, never returning none of your own. Tenant isolation
    is unchanged — a caller only ever reaches rows under its own claim tenant.
    """
    if caller.tenant is None:
        return None
    try:
        return uuid.UUID(caller.tenant)
    except ValueError:
        return None


async def _compliance_vendor_register(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    state = get_state(request)
    rows = compliance_source.load_vendor_register(state.transfer_feed, now=datetime.now(UTC))
    return views.vendor_register_view(rows)


async def _compliance_consents(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    state = get_state(request)
    tenant_id = _tenant_scope(caller)
    if tenant_id is None:
        return views.consent_coverage_view(())
    async with tenant_session(state.engine, tenant_id) as session:
        rows = await compliance_source.consent_coverage(session, tenant_id=tenant_id)
    return views.consent_coverage_view(rows)


async def _compliance_audit_search(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    state = get_state(request)
    params = request.query_params
    try:
        query = AuditSearchQuery(
            action_prefix=params.get("action_prefix"),
            actor=params.get("actor"),
            since=params.get("since"),
            until=params.get("until"),
        )
        rows = await compliance_source.audit_search(state.audit, query=query)
    except AuditSearchContentRefused as refusal:
        # a search that would reach content is refused, never emptied (HB-L6)
        raise compliance_query_refused(refusal.code) from None
    return views.audit_search_view(rows)


async def _compliance_dsar(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    state = get_state(request)
    tenant_id = _tenant_scope(caller)
    if tenant_id is None:
        return views.dsar_queue_view(())
    async with tenant_session(state.engine, tenant_id) as session:
        rows = await compliance_source.dsar_queue(
            session, tenant_id=tenant_id, now=datetime.now(UTC)
        )
    return views.dsar_queue_view(rows)


async def _compliance_evidence(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    state = get_state(request)
    bundle = await compliance_source.build_evidence(
        state,
        tenant_id=_tenant_scope(caller),
        feed=state.transfer_feed,
        now=datetime.now(UTC),
    )
    return views.evidence_bundle_view(bundle)


_HANDLERS: dict[str, Handler] = {
    "admin.whoami.read": _whoami,
    "admin.access.roles.read": _roles,
    "admin.actions.read": _actions,
    "admin.models.read": _models,
    "admin.ops.read": _ops,
    "admin.reliability.read": _reliability,
    "admin.models.benchmark": _models_benchmark,
    "admin.break_glass.open": _break_glass_open,
    "admin.break_glass.brief.read": _break_glass_brief,
    "admin.break_glass.approve": _break_glass_approve,
    "admin.compliance.vendor_register.read": _compliance_vendor_register,
    "admin.compliance.consents.read": _compliance_consents,
    "admin.compliance.audit_search.read": _compliance_audit_search,
    "admin.compliance.dsar.read": _compliance_dsar,
    "admin.compliance.evidence.export": _compliance_evidence,
}


def _endpoint(route: AdminRoute) -> Callable[[Request], Awaitable[Response]]:
    handler = _HANDLERS[route.audit_action]

    async def endpoint(request: Request) -> Response:
        wiring = get_admin_wiring(request)
        sink = get_state(request).audit
        # files/08 §8 rule (b): a mutating route that resolves to no
        # registry entry raises here rather than executing — an unregistered
        # admin write cannot be logged, so it cannot happen
        tier = (
            int(dangerous_action(route.dangerous_action_id).tier)
            if route.dangerous_action_id is not None
            else 0
        )
        base = {
            "route": f"{route.method} {route.path}",
            "action": route.audit_action,
            "tier": str(tier),
        }
        try:
            caller = resolve_caller(request, wiring)
        except HTTPException as refusal:
            # a request refused before the caller is known is still an admin
            # action, and is exactly the one an investigator wants to see
            async with AdminActionRecord(
                sink, actor=_UNRESOLVED_ACTOR, action=route.audit_action, detail=base
            ) as record:
                record.mark_failed()
            raise refusal
        role = caller.principal.first_permitted(route.permitted_roles)
        detail = {
            **base,
            "role": role.value if role is not None else "none",
            "tenant": caller.tenant or "-",
        }
        async with AdminActionRecord(
            sink, actor=caller.principal.subject, action=route.audit_action, detail=detail
        ):
            if role is None:
                raise admin_refused(RoleNotPermitted.code)
            return JSONResponse(await handler(request, caller, wiring, role))

    return endpoint


for _route in ADMIN_ROUTES:
    router.add_api_route(
        _route.path,
        _endpoint(_route),
        methods=[_route.method],
        name=_route.audit_action.replace(".", "_"),
        # INT-038's route-table scan: a console action has no data subject at
        # the door, so it declares WHY rather than naming a scope it could not
        # honestly claim. Attached here, once, for every descriptor — the same
        # choke point that attaches the audit action, so a route cannot be
        # added that is undeclared to either.
        dependencies=[administrative_action()],
    )

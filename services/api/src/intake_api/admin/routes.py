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
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
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
    ADMIN_PENDING_ACTION_EXPIRED_TOTAL,
    SEC_BREAK_GLASS_TOTAL,
)

from intake_api.admin import views
from intake_api.admin.deps import AdminCaller, get_admin_wiring, resolve_caller
from intake_api.errors import admin_refused, break_glass_refused, four_eyes_refused, not_found
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


_HANDLERS: dict[str, Handler] = {
    "admin.whoami.read": _whoami,
    "admin.access.roles.read": _roles,
    "admin.actions.read": _actions,
    "admin.break_glass.open": _break_glass_open,
    "admin.break_glass.brief.read": _break_glass_brief,
    "admin.break_glass.approve": _break_glass_approve,
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
    )

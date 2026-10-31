"""The CI/CD & releases module's handlers (INT-187; files/08 §3, §8, §8.2).

Registered through :mod:`intake_api.admin.routes` like every console route, so
each one is write-ahead audited, role-guarded from the descriptor table and a
registered ``DangerousAction`` — nothing here opens its own audit record.

- ``GET /admin/cicd`` — the composite (:mod:`.cicd_console`).
- ``POST /admin/cicd/freeze`` — tier 1, one key: freeze deploys.
- ``POST /admin/cicd/freeze/lift`` — tier 2: opens a four-eyes ceremony and
  changes nothing yet.
- ``POST /admin/cicd/freeze/lift/{action_id}/approve`` — the second key.
- ``GET /admin/cicd/pending/{action_id}`` — the brief the approver reads.

**Bodies are closed.** A field outside the action's set is refused by name,
never ignored: a field the server drops silently is a field nobody notices
carrying patient text (invariant 6). Refusals are codes; no submitted value
is echoed.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from intake_platform.admin import AdminRole, AdminWiring, FourEyesRefused
from intake_platform.admin.actions import CICD_CEREMONIES
from intake_platform.admin.flag_governance import (
    FlagChangeReason,
    FlagGovernanceRefused,
    build_flag_change_justification,
)
from intake_platform.admin.four_eyes import Justification, SelfApproval
from intake_platform.admin.freeze_governance import (
    DeployFreezeGovernor,
    FreezeGovernanceRefused,
    FreezeRoleIneligible,
)
from intake_platform.admin.metrics import (
    ADMIN_DEPLOY_FREEZE_CHANGES_TOTAL,
    ADMIN_FOUR_EYES_SELF_APPROVAL_ATTEMPT_TOTAL,
    ADMIN_PENDING_ACTION_EXPIRED_TOTAL,
)
from intake_platform.release_freeze import DeployFreezeChange, ReleaseFreezeUnavailable

from intake_api.admin import views
from intake_api.admin.cicd_console import freeze_view, load_cicd_console
from intake_api.admin.deps import AdminCaller
from intake_api.admin.step_up_routes import GRANT_FIELD, stepped_up_approver
from intake_api.errors import four_eyes_refused, not_found, release_freeze_refused

__all__ = ["CICD_HANDLERS"]

Handler = Callable[[Request, AdminCaller, AdminWiring, AdminRole], Awaitable[dict[str, Any]]]

_REASON_BODY = frozenset({"reason_class", "justification"})
_APPROVE_BODY = frozenset({GRANT_FIELD})


def _count(control: DeployFreezeChange, outcome: str) -> None:
    ADMIN_DEPLOY_FREEZE_CHANGES_TOTAL.labels(control=control.value, outcome=outcome).inc()


def _sweep(wiring: AdminWiring) -> None:
    expired = wiring.four_eyes.expire_due()
    if expired:
        ADMIN_PENDING_ACTION_EXPIRED_TOTAL.inc(expired)


def _governor(wiring: AdminWiring) -> DeployFreezeGovernor:
    if wiring.release_freeze is None:
        raise release_freeze_refused(503, "release_freeze_unconfigured")
    return DeployFreezeGovernor(wiring.four_eyes, wiring.release_freeze)


async def _body(request: Request, allowed: frozenset[str]) -> Mapping[str, Any]:
    try:
        payload = json.loads(await request.body())
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise release_freeze_refused(422, "release_freeze_body_not_json") from None
    if not isinstance(payload, dict):
        raise release_freeze_refused(422, "release_freeze_body_not_an_object")
    if set(payload) - allowed:
        raise release_freeze_refused(422, "release_freeze_unexpected_field")
    return payload


def _justification(payload: Mapping[str, Any]) -> Justification:
    raw = payload.get("reason_class")
    try:
        reason = FlagChangeReason(raw if isinstance(raw, str) else "")
    except ValueError:
        raise release_freeze_refused(422, "release_freeze_reason_class_unknown") from None
    text = payload.get("justification")
    try:
        return build_flag_change_justification(
            reason_class=reason, free_text=text if isinstance(text, str) else ""
        )
    except FlagGovernanceRefused as refusal:
        raise release_freeze_refused(422, refusal.code) from None


def _refusal(error: Exception) -> HTTPException:
    """One mapping from a typed refusal to a status and a code."""
    if isinstance(error, ReleaseFreezeUnavailable):
        return release_freeze_refused(503, error.code)
    if isinstance(error, FlagGovernanceRefused):
        return release_freeze_refused(422, error.code)
    if isinstance(error, FreezeRoleIneligible):
        return release_freeze_refused(403, error.code)
    if isinstance(error, FreezeGovernanceRefused):
        return release_freeze_refused(409, error.code)
    if isinstance(error, SelfApproval):
        # files/08 §5: an intrusion signal, not a hygiene metric
        ADMIN_FOUR_EYES_SELF_APPROVAL_ATTEMPT_TOTAL.inc()
        return four_eyes_refused(error.code)
    if isinstance(error, FourEyesRefused):
        if error.code == "four_eyes_unknown":
            return not_found()
        return four_eyes_refused(error.code)
    raise error


_REFUSALS = (
    ReleaseFreezeUnavailable,
    FlagGovernanceRefused,
    FreezeGovernanceRefused,
    FourEyesRefused,
)


async def _read(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    _sweep(wiring)
    pending = wiring.four_eyes.pending()
    # Redis and Prometheus are both synchronous clients: off the event loop.
    return await run_in_threadpool(
        lambda: load_cicd_console(
            datetime.now(UTC), freeze_store=wiring.release_freeze, pending=pending
        )
    )


async def _engage(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    governor = _governor(wiring)
    change = DeployFreezeChange.ENGAGE
    try:
        payload = await _body(request, _REASON_BODY)
        justification = _justification(payload)
        result = await run_in_threadpool(
            lambda: governor.engage(
                actor=caller.principal.actor_block(role), justification=justification
            )
        )
    except HTTPException:
        _count(change, "refused")
        raise
    except _REFUSALS as refusal:
        _count(change, "refused")
        raise _refusal(refusal) from None
    _count(change, "applied" if result.changed else "unchanged")
    return {"changed": result.changed, "freeze": freeze_view(result.freeze)}


async def _open_lift(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    _sweep(wiring)
    governor = _governor(wiring)
    change = DeployFreezeChange.LIFT
    try:
        payload = await _body(request, _REASON_BODY)
        justification = _justification(payload)
        pending = await run_in_threadpool(
            lambda: governor.open_lift(
                actor=caller.principal.actor_block(role), justification=justification
            )
        )
    except HTTPException:
        _count(change, "refused")
        raise
    except _REFUSALS as refusal:
        _count(change, "refused")
        raise _refusal(refusal) from None
    _count(change, "requested")
    return views.pending_view(pending)


async def _approve_lift(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    _sweep(wiring)
    governor = _governor(wiring)
    change = DeployFreezeChange.LIFT
    action_id = request.path_params["action_id"]
    try:
        payload = await _body(request, _APPROVE_BODY)
        approver, assertion = await stepped_up_approver(
            request, caller, wiring, role, action_id=action_id, payload=payload
        )
        freeze = await run_in_threadpool(
            lambda: governor.approve_lift(action_id, approver=approver, assertion_id=assertion)
        )
    except HTTPException:
        _count(change, "refused")
        raise
    except _REFUSALS as refusal:
        _count(change, "refused")
        raise _refusal(refusal) from None
    _count(change, "applied")
    return {
        "pending": views.pending_view(wiring.four_eyes.get(action_id)),
        "freeze": freeze_view(freeze),
    }


async def _brief(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    _sweep(wiring)
    action_id = request.path_params["action_id"]
    try:
        pending = wiring.four_eyes.get(action_id)
    except FourEyesRefused:
        raise not_found() from None
    if pending.action not in CICD_CEREMONIES:
        # another module's ceremony is that module's to show
        raise not_found()
    return views.brief_view(wiring.four_eyes.brief(action_id))


CICD_HANDLERS: dict[str, Handler] = {
    "admin.cicd.read": _read,
    "admin.cicd.freeze.engage": _engage,
    "admin.cicd.freeze.lift": _open_lift,
    "admin.cicd.freeze.lift.approve": _approve_lift,
    "admin.cicd.pending.brief.read": _brief,
}

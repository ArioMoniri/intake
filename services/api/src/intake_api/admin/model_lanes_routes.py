"""The Model lanes module's handlers (INT-428, ADR-035; files/08 §3, §8.2).

Registered through :mod:`intake_api.admin.routes` like every console route, so
each one is write-ahead audited (the hash-chained audit sink), role-guarded
from the descriptor table and a registered ``DangerousAction``.

- ``GET /admin/model-lanes`` — the composite (:mod:`.model_lanes_console`).
- ``POST /admin/model-lanes/hosted/disable`` — tier 1: every hosted lane off.
- ``POST /admin/model-lanes/self-hosted`` — tier 1: the one-click switch to GPU.
- ``POST /admin/model-lanes/hosted/release`` (+ ``/{id}/approve``) — tier 2.
- ``PUT /admin/model-lanes/route/{lane}`` (+ ``/route/pending/{id}/approve``) — tier 2.
- ``PUT /admin/model-lanes/keys/{provider}`` (+ ``/keys/pending/{id}/approve``) — tier 2.
- ``GET /admin/model-lanes/pending/{action_id}`` — the brief the approver reads.

**Bodies are closed and refusals are codes.** A field outside the action's set
is refused by name; no submitted value is ever echoed — and the one field
that is a secret, ``api_key``, is read once into a
:class:`~intake_platform.model_lanes.ProviderApiKey` and never reaches a
response, a log line, an exception message or the audit detail.
"""

from __future__ import annotations

import json
import os
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from intake_platform.admin import AdminRole, AdminWiring, FourEyesRefused
from intake_platform.admin.actions import MODEL_LANES_CEREMONIES
from intake_platform.admin.flag_governance import (
    FlagChangeReason,
    FlagGovernanceRefused,
    build_flag_change_justification,
)
from intake_platform.admin.four_eyes import ActorBlock, Justification, SelfApproval
from intake_platform.admin.metrics import (
    ADMIN_FOUR_EYES_SELF_APPROVAL_ATTEMPT_TOTAL,
    ADMIN_MODEL_LANE_CHANGES_TOTAL,
    ADMIN_PENDING_ACTION_EXPIRED_TOTAL,
)
from intake_platform.admin.model_lanes_governance import (
    ModelLanesGovernanceRefused,
    ModelLanesGovernor,
    ModelLanesRoleIneligible,
    SelfHostedNotHealthy,
)
from intake_platform.model_lanes import (
    KeyVaultUnavailable,
    ModelLanesChange,
    ModelLanesRefused,
    ModelLanesUnavailable,
    ProviderApiKey,
    ProviderKeyMalformed,
    parse_lane,
    parse_model_key,
    parse_provider,
    parse_role,
    parse_route,
)
from intake_platform.model_lanes.store import ModelLanesConflict
from intake_platform.model_lanes.wiring import ModelLanesWiring

from intake_api.admin import views
from intake_api.admin.deps import AdminCaller
from intake_api.admin.model_lanes_console import load_model_lanes_console
from intake_api.admin.ops_prom import prom_client_from_env
from intake_api.admin.step_up_routes import GRANT_FIELD, stepped_up_approver
from intake_api.errors import four_eyes_refused, model_lanes_refused, not_found

__all__ = ["MODEL_LANES_HANDLERS"]

Handler = Callable[[Request, AdminCaller, AdminWiring, AdminRole], Awaitable[dict[str, Any]]]

_REASON_FIELDS = frozenset({"reason_class", "justification"})
_ENGAGE_BODY = _REASON_FIELDS | {"lanes"}
_SWITCH_BODY = _REASON_FIELDS | {"route", "model", "fallback", "fallback_model"}
_KEY_BODY = _REASON_FIELDS | {"api_key"}
_APPROVE_BODY = frozenset({GRANT_FIELD})


def _count(control: ModelLanesChange, outcome: str) -> None:
    ADMIN_MODEL_LANE_CHANGES_TOTAL.labels(control=control.value, outcome=outcome).inc()


def _lanes(wiring: AdminWiring) -> ModelLanesWiring:
    if wiring.model_lanes is None:
        raise model_lanes_refused(503, "model_lanes_unconfigured")
    return wiring.model_lanes


def _governor(wiring: AdminWiring) -> ModelLanesGovernor:
    lanes = _lanes(wiring)
    return ModelLanesGovernor(wiring.four_eyes, lanes.store, lanes.router)


def _sweep(wiring: AdminWiring) -> None:
    expired = wiring.four_eyes.expire_due()
    if expired:
        ADMIN_PENDING_ACTION_EXPIRED_TOTAL.inc(expired)
    if wiring.model_lanes is None or wiring.model_lanes.router.keys is None:
        return  # no key store in this deployment: nothing can have been staged
    governor = _governor(wiring)
    try:
        # a staged key whose ceremony expired is destroyed, not left in OpenBao
        governor.reap_staged_keys(governor.live_staging_refs())
    except KeyVaultUnavailable:
        return


async def _body(request: Request, allowed: frozenset[str]) -> Mapping[str, Any]:
    try:
        payload = json.loads(await request.body())
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise model_lanes_refused(422, "model_lanes_body_not_json") from None
    if not isinstance(payload, dict):
        raise model_lanes_refused(422, "model_lanes_body_not_an_object")
    if set(payload) - allowed:
        raise model_lanes_refused(422, "model_lanes_unexpected_field")
    return payload


def _justification(payload: Mapping[str, Any]) -> Justification:
    raw = payload.get("reason_class")
    try:
        reason = FlagChangeReason(raw if isinstance(raw, str) else "")
    except ValueError:
        raise model_lanes_refused(422, "model_lanes_reason_class_unknown") from None
    text = payload.get("justification")
    try:
        return build_flag_change_justification(
            reason_class=reason, free_text=text if isinstance(text, str) else ""
        )
    except FlagGovernanceRefused as refusal:
        raise model_lanes_refused(422, refusal.code) from None


def _refusal(error: Exception) -> HTTPException:
    """One mapping from a typed refusal to a status and a code."""
    if isinstance(error, ModelLanesUnavailable | KeyVaultUnavailable):
        return model_lanes_refused(503, error.code)
    if isinstance(error, ModelLanesRefused | ProviderKeyMalformed | FlagGovernanceRefused):
        return model_lanes_refused(422, error.code)
    if isinstance(error, ModelLanesRoleIneligible):
        return model_lanes_refused(403, error.code)
    if isinstance(error, SelfHostedNotHealthy | ModelLanesGovernanceRefused):
        return model_lanes_refused(409, error.code)
    if isinstance(error, ModelLanesConflict):
        return model_lanes_refused(409, error.code)
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
    ModelLanesUnavailable,
    KeyVaultUnavailable,
    ModelLanesRefused,
    ProviderKeyMalformed,
    FlagGovernanceRefused,
    ModelLanesGovernanceRefused,
    ModelLanesConflict,
    FourEyesRefused,
)


async def _run(
    change: ModelLanesChange, success: str, work: Callable[[], Awaitable[dict[str, Any]]]
) -> dict[str, Any]:
    try:
        result = await work()
    except HTTPException:
        _count(change, "refused")
        raise
    except _REFUSALS as refusal:
        _count(change, "refused")
        raise _refusal(refusal) from None
    _count(change, result.pop("_outcome", success))
    return result


async def _stepped_up(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole, action_id: str
) -> tuple[ActorBlock, str]:
    """The approver block and assertion id, from the caller's step-up grant
    for this action and from nothing else (INT-563; ADR-043)."""
    payload = await _body(request, _APPROVE_BODY)
    return await stepped_up_approver(
        request, caller, wiring, role, action_id=action_id, payload=payload
    )


def _control(control: Any) -> dict[str, Any]:
    return {
        "revision": control.revision,
        "hosted_disabled": control.hosted_disabled,
        "lanes": {
            lane.value: setting.model_dump(mode="json") for lane, setting in control.lanes.items()
        },
        "last_change": control.last_change.value if control.last_change else None,
    }


# -- reads ---------------------------------------------------------------------------


async def _read(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    _sweep(wiring)
    pending = tuple(p for p in wiring.four_eyes.pending() if p.action in MODEL_LANES_CEREMONIES)
    prom = prom_client_from_env(os.environ)
    return await run_in_threadpool(
        lambda: load_model_lanes_console(
            datetime.now(UTC), wiring=wiring.model_lanes, pending=pending, prom=prom
        )
    )


async def _brief(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    _sweep(wiring)
    action_id = request.path_params["action_id"]
    try:
        pending = wiring.four_eyes.get(action_id)
    except FourEyesRefused:
        raise not_found() from None
    if pending.action not in MODEL_LANES_CEREMONIES:
        # another module's ceremony is that module's to show
        raise not_found()
    return views.brief_view(wiring.four_eyes.brief(action_id))


# -- tier 1 --------------------------------------------------------------------------


async def _disable(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    async def work() -> dict[str, Any]:
        governor = _governor(wiring)
        justification = _justification(await _body(request, _REASON_FIELDS))
        result = await run_in_threadpool(
            lambda: governor.disable_hosted(
                actor=caller.principal.actor_block(role), justification=justification
            )
        )
        return {
            "changed": result.changed,
            "control": _control(result.control),
            "_outcome": "applied" if result.changed else "unchanged",
        }

    return await _run(ModelLanesChange.HOSTED_DISABLE, "applied", work)


async def _engage(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    async def work() -> dict[str, Any]:
        governor = _governor(wiring)
        payload = await _body(request, _ENGAGE_BODY)
        justification = _justification(payload)
        raw = payload.get("lanes")
        if not isinstance(raw, list) or not raw:
            raise model_lanes_refused(422, "model_lanes_lane_unknown")
        lanes = tuple(dict.fromkeys(parse_lane(value) for value in raw))
        result = await run_in_threadpool(
            lambda: governor.engage_self_hosted(
                actor=caller.principal.actor_block(role),
                justification=justification,
                lanes=lanes,
            )
        )
        return {
            "changed": result.changed,
            "control": _control(result.control),
            "_outcome": "applied" if result.changed else "unchanged",
        }

    return await _run(ModelLanesChange.SELF_HOSTED_ENGAGE, "applied", work)


# -- tier 2 --------------------------------------------------------------------------


async def _open_release(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    async def work() -> dict[str, Any]:
        _sweep(wiring)
        governor = _governor(wiring)
        justification = _justification(await _body(request, _REASON_FIELDS))
        pending = await run_in_threadpool(
            lambda: governor.open_release(
                actor=caller.principal.actor_block(role), justification=justification
            )
        )
        return views.pending_view(pending)

    return await _run(ModelLanesChange.HOSTED_RELEASE, "requested", work)


async def _approve_release(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    action_id = request.path_params["action_id"]

    async def work() -> dict[str, Any]:
        _sweep(wiring)
        governor = _governor(wiring)
        approver, assertion = await _stepped_up(request, caller, wiring, role, action_id)
        control = await run_in_threadpool(
            lambda: governor.approve_release(action_id, approver=approver, assertion_id=assertion)
        )
        return {
            "pending": views.pending_view(wiring.four_eyes.get(action_id)),
            "control": _control(control),
        }

    return await _run(ModelLanesChange.HOSTED_RELEASE, "applied", work)


async def _open_switch(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    async def work() -> dict[str, Any]:
        _sweep(wiring)
        governor = _governor(wiring)
        model_role = parse_role(request.path_params["role"])
        payload = await _body(request, _SWITCH_BODY)
        justification = _justification(payload)
        route = parse_route(payload.get("route"))
        model = parse_model_key(payload.get("model"))
        raw_fallback = payload.get("fallback")
        fallback = None if raw_fallback is None else parse_provider(raw_fallback)
        fallback_model = parse_model_key(payload.get("fallback_model"))
        pending = await run_in_threadpool(
            lambda: governor.open_switch(
                actor=caller.principal.actor_block(role),
                justification=justification,
                role=model_role,
                route=route,
                model=model,
                fallback=fallback,
                fallback_model=fallback_model,
            )
        )
        return views.pending_view(pending)

    return await _run(ModelLanesChange.ROUTE_SWITCH, "requested", work)


async def _approve_switch(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    action_id = request.path_params["action_id"]

    async def work() -> dict[str, Any]:
        _sweep(wiring)
        governor = _governor(wiring)
        approver, assertion = await _stepped_up(request, caller, wiring, role, action_id)
        control = await run_in_threadpool(
            lambda: governor.approve_switch(action_id, approver=approver, assertion_id=assertion)
        )
        return {
            "pending": views.pending_view(wiring.four_eyes.get(action_id)),
            "control": _control(control),
        }

    return await _run(ModelLanesChange.ROUTE_SWITCH, "applied", work)


async def _open_key_set(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    async def work() -> dict[str, Any]:
        _sweep(wiring)
        governor = _governor(wiring)
        provider = parse_provider(request.path_params["provider"])
        payload = await _body(request, _KEY_BODY)
        justification = _justification(payload)
        raw = payload.get("api_key")
        key = ProviderApiKey(raw if isinstance(raw, str) else "")
        del raw, payload  # the raw value goes no further than the key object
        pending = await run_in_threadpool(
            lambda: governor.open_key_set(
                actor=caller.principal.actor_block(role),
                justification=justification,
                provider=provider,
                key=key,
            )
        )
        return {**views.pending_view(pending), "key": {"state": "staged", "last4": key.last4}}

    return await _run(ModelLanesChange.KEY_SET, "requested", work)


async def _approve_key_set(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    action_id = request.path_params["action_id"]

    async def work() -> dict[str, Any]:
        _sweep(wiring)
        governor = _governor(wiring)
        approver, assertion = await _stepped_up(request, caller, wiring, role, action_id)
        status = await run_in_threadpool(
            lambda: governor.approve_key_set(action_id, approver=approver, assertion_id=assertion)
        )
        return {
            "pending": views.pending_view(wiring.four_eyes.get(action_id)),
            "key": {"state": status.state, "last4": status.last4, "set_at": status.set_at},
        }

    return await _run(ModelLanesChange.KEY_SET, "applied", work)


MODEL_LANES_HANDLERS: dict[str, Handler] = {
    "admin.model_lanes.read": _read,
    "admin.model_lanes.hosted.disable": _disable,
    "admin.model_lanes.self_hosted.engage": _engage,
    "admin.model_lanes.hosted.release": _open_release,
    "admin.model_lanes.hosted.release.approve": _approve_release,
    "admin.model_lanes.route.switch": _open_switch,
    "admin.model_lanes.route.switch.approve": _approve_switch,
    "admin.model_lanes.key.set": _open_key_set,
    "admin.model_lanes.key.set.approve": _approve_key_set,
    "admin.model_lanes.pending.brief.read": _brief,
}

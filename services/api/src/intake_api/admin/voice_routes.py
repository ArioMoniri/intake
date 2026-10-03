"""The Voice module's handlers (INT-182; files/08 §3 "Voice runtime", §8, §8.2).

Registered through :mod:`intake_api.admin.routes` like every console route, so
each one is write-ahead audited, role-guarded from the descriptor table and a
registered ``DangerousAction`` — nothing here opens its own audit record.

- ``POST /admin/voice/kill-switch`` — tier 1, one key, toward ``typed``.
- ``POST /admin/voice/kill-switch/release``, ``PUT /admin/voice/profile/{tenant}``,
  ``PUT /admin/voice/canary/{tenant}`` — tier 2: each opens a four-eyes
  ceremony and changes nothing yet.
- ``POST …/{action_id}/approve`` — the second key, one route per action.
- ``GET /admin/voice`` and ``GET /admin/voice/pending/{action_id}`` — reads.

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
from intake_platform.admin.actions import (
    VOICE_CANARY_SET,
    VOICE_CEREMONIES,
    VOICE_KILL_SWITCH_RELEASE,
    VOICE_PROFILE_SWITCH,
    DangerousAction,
)
from intake_platform.admin.flag_governance import (
    FlagChangeReason,
    FlagGovernanceRefused,
    build_flag_change_justification,
)
from intake_platform.admin.four_eyes import Justification, SelfApproval
from intake_platform.admin.metrics import (
    ADMIN_FOUR_EYES_SELF_APPROVAL_ATTEMPT_TOTAL,
    ADMIN_PENDING_ACTION_EXPIRED_TOTAL,
    ADMIN_VOICE_CONTROL_CHANGES_TOTAL,
)
from intake_platform.admin.voice_governance import (
    VoiceControlGovernor,
    VoiceGovernanceRefused,
    VoiceRoleIneligible,
)
from intake_platform.voice_control import (
    VoiceControlChange,
    VoiceControlRefused,
    VoiceControlUnavailable,
    require_tenant_id,
)

from intake_api.admin import views
from intake_api.admin.deps import AdminCaller
from intake_api.admin.voice_console import control_view, load_voice_console
from intake_api.errors import four_eyes_refused, not_found, voice_control_refused

__all__ = ["VOICE_HANDLERS"]

Handler = Callable[[Request, AdminCaller, AdminWiring, AdminRole], Awaitable[dict[str, Any]]]

_REASON_FIELDS = frozenset({"reason_class", "justification"})
_TENANT_BODY = _REASON_FIELDS | {"tenant"}
_PROFILE_BODY = _REASON_FIELDS | {"profile"}
_CANARY_BODY = _REASON_FIELDS | {"profile", "weight"}
_APPROVE_BODY = frozenset({"assertion_id"})


def _count(control: VoiceControlChange, outcome: str) -> None:
    ADMIN_VOICE_CONTROL_CHANGES_TOTAL.labels(control=control.value, outcome=outcome).inc()


def _sweep(wiring: AdminWiring) -> None:
    expired = wiring.four_eyes.expire_due()
    if expired:
        ADMIN_PENDING_ACTION_EXPIRED_TOTAL.inc(expired)


def _governor(wiring: AdminWiring) -> VoiceControlGovernor:
    if wiring.voice_controls is None:
        raise voice_control_refused(503, "voice_control_unconfigured")
    return VoiceControlGovernor(wiring.four_eyes, wiring.voice_controls)


async def _body(request: Request, allowed: frozenset[str]) -> Mapping[str, Any]:
    try:
        payload = json.loads(await request.body())
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise voice_control_refused(422, "voice_body_not_json") from None
    if not isinstance(payload, dict):
        raise voice_control_refused(422, "voice_body_not_an_object")
    if set(payload) - allowed:
        raise voice_control_refused(422, "voice_unexpected_field")
    return payload


def _justification(payload: Mapping[str, Any]) -> Justification:
    raw = payload.get("reason_class")
    try:
        reason = FlagChangeReason(raw if isinstance(raw, str) else "")
    except ValueError:
        raise voice_control_refused(422, "voice_reason_class_unknown") from None
    text = payload.get("justification")
    try:
        return build_flag_change_justification(
            reason_class=reason, free_text=text if isinstance(text, str) else ""
        )
    except FlagGovernanceRefused as refusal:
        raise voice_control_refused(422, refusal.code) from None


def _refusal(error: Exception) -> HTTPException:
    """One mapping from a typed refusal to a status and a code."""
    if isinstance(error, VoiceControlUnavailable):
        return voice_control_refused(503, error.code)
    if isinstance(error, VoiceControlRefused | FlagGovernanceRefused):
        return voice_control_refused(422, error.code)
    if isinstance(error, VoiceRoleIneligible):
        return voice_control_refused(403, error.code)
    if isinstance(error, VoiceGovernanceRefused):
        return voice_control_refused(409, error.code)
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
    VoiceControlUnavailable,
    VoiceControlRefused,
    FlagGovernanceRefused,
    VoiceGovernanceRefused,
    FourEyesRefused,
)


async def _read(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    _sweep(wiring)
    pending = wiring.four_eyes.pending()
    # Redis and Prometheus are both synchronous clients: off the event loop.
    return await run_in_threadpool(
        lambda: load_voice_console(
            datetime.now(UTC), controls=wiring.voice_controls, pending=pending
        )
    )


async def _engage(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    governor = _governor(wiring)
    payload = await _body(request, _TENANT_BODY)
    change = VoiceControlChange.KILL_SWITCH_ENGAGE
    try:
        tenant = require_tenant_id(payload.get("tenant"))
        justification = _justification(payload)
        result = await run_in_threadpool(
            lambda: governor.engage_kill_switch(
                tenant_id=tenant,
                actor=caller.principal.actor_block(role),
                justification=justification,
            )
        )
    except HTTPException:
        _count(change, "refused")
        raise
    except _REFUSALS as refusal:
        _count(change, "refused")
        raise _refusal(refusal) from None
    _count(change, "applied" if result.changed else "unchanged")
    return {
        "tenant": result.control.tenant_id,
        "changed": result.changed,
        "control": control_view(result.control),
    }


def _opener(change: VoiceControlChange, fields: frozenset[str], *, tenant_in_path: bool) -> Handler:
    async def handler(
        request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
    ) -> dict[str, Any]:
        _sweep(wiring)
        governor = _governor(wiring)
        payload = await _body(request, fields)
        raw_tenant = request.path_params["tenant"] if tenant_in_path else payload.get("tenant")
        actor = caller.principal.actor_block(role)
        try:
            tenant = require_tenant_id(raw_tenant)
            justification = _justification(payload)
            if change is VoiceControlChange.KILL_SWITCH_RELEASE:
                pending = await run_in_threadpool(
                    lambda: governor.open_kill_switch_release(
                        tenant_id=tenant, actor=actor, justification=justification
                    )
                )
            elif change is VoiceControlChange.DEFAULT_PROFILE:
                pending = await run_in_threadpool(
                    lambda: governor.open_profile_switch(
                        tenant_id=tenant,
                        profile=payload.get("profile"),
                        actor=actor,
                        justification=justification,
                    )
                )
            else:
                pending = await run_in_threadpool(
                    lambda: governor.open_canary(
                        tenant_id=tenant,
                        profile=payload.get("profile"),
                        weight=payload.get("weight"),
                        actor=actor,
                        justification=justification,
                    )
                )
        except HTTPException:
            _count(change, "refused")
            raise
        except _REFUSALS as refusal:
            _count(change, "refused")
            raise _refusal(refusal) from None
        _count(change, "requested")
        return {**views.pending_view(pending), "tenant": pending.evidence["tenant"]}

    return handler


def _approver(action: DangerousAction, change: VoiceControlChange) -> Handler:
    async def handler(
        request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
    ) -> dict[str, Any]:
        _sweep(wiring)
        governor = _governor(wiring)
        payload = await _body(request, _APPROVE_BODY)
        assertion = payload.get("assertion_id")
        action_id = request.path_params["action_id"]
        try:
            control = await run_in_threadpool(
                lambda: governor.approve(
                    action_id,
                    action=action,
                    approver=caller.principal.actor_block(role),
                    assertion_id=assertion if isinstance(assertion, str) else "",
                )
            )
        except _REFUSALS as refusal:
            _count(change, "refused")
            raise _refusal(refusal) from None
        _count(change, "applied")
        return {
            "pending": views.pending_view(wiring.four_eyes.get(action_id)),
            "control": control_view(control),
        }

    return handler


async def _brief(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    _sweep(wiring)
    action_id = request.path_params["action_id"]
    try:
        pending = wiring.four_eyes.get(action_id)
    except FourEyesRefused:
        raise not_found() from None
    if pending.action not in VOICE_CEREMONIES:
        # another module's ceremony is that module's to show
        raise not_found()
    return views.brief_view(wiring.four_eyes.brief(action_id))


VOICE_HANDLERS: dict[str, Handler] = {
    "admin.voice.read": _read,
    "admin.voice.kill_switch.engage": _engage,
    "admin.voice.kill_switch.release": _opener(
        VoiceControlChange.KILL_SWITCH_RELEASE, _TENANT_BODY, tenant_in_path=False
    ),
    "admin.voice.kill_switch.release.approve": _approver(
        VOICE_KILL_SWITCH_RELEASE, VoiceControlChange.KILL_SWITCH_RELEASE
    ),
    "admin.voice.profile.switch": _opener(
        VoiceControlChange.DEFAULT_PROFILE, _PROFILE_BODY, tenant_in_path=True
    ),
    "admin.voice.profile.switch.approve": _approver(
        VOICE_PROFILE_SWITCH, VoiceControlChange.DEFAULT_PROFILE
    ),
    "admin.voice.canary.set": _opener(VoiceControlChange.CANARY, _CANARY_BODY, tenant_in_path=True),
    "admin.voice.canary.set.approve": _approver(VOICE_CANARY_SET, VoiceControlChange.CANARY),
    "admin.voice.pending.brief.read": _brief,
}

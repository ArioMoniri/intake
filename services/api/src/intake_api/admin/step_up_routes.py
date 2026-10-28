"""The four-eyes step-up's two routes and the one redemption every approval
runs (INT-563; ADR-043; files/08 §2.3).

Registered through :mod:`intake_api.admin.routes` like every console route, so
both are write-ahead audited, role-guarded from the descriptor table and the
registered tier-1 action ``admin.four_eyes.step_up``.

- ``POST /admin/step-up`` ``{"action_id"}`` — refuses an approval that could
  never pass (unknown, decided or expired action; an ineligible role; the
  requester themselves, counted as the intrusion signal it is), then opens a
  ceremony bound to the caller's subject and Keycloak session and to that one
  action, and answers the authorization URL the console redirects to.
- ``POST /admin/step-up/complete`` ``{"state", "code"}`` — what Keycloak sent
  back to the console's callback. The API redeems the code with the PKCE
  verifier it never let out, verifies the ID token and answers a one-time
  grant for that action. The grant is on the chain as
  ``admin.four_eyes.step_up.granted``, by ids only.

:func:`stepped_up_approver` is the only way any approve or countersign route
obtains an approver block and an assertion id: it spends the grant named by
``step_up_grant`` (write-ahead ``admin.four_eyes.step_up.redeemed``) and
returns the caller's block carrying the credential just asserted. There is no
other path — the old ``assertion_id`` the API never checked is gone, and a
body that still carries it is refused as an unexpected field.

Every refusal is a code; nothing submitted is echoed and no credential id
reaches the chain (invariant 6).
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Final

from fastapi import Request
from fastapi.concurrency import run_in_threadpool
from intake_platform.admin import ADMIN_BASIS_REF, AdminRole, AdminWiring, FourEyesRefused
from intake_platform.admin.four_eyes import ActorBlock, SelfApproval
from intake_platform.admin.metrics import (
    ADMIN_FOUR_EYES_SELF_APPROVAL_ATTEMPT_TOTAL,
    ADMIN_PENDING_ACTION_EXPIRED_TOTAL,
    ADMIN_STEP_UP_TOTAL,
)
from intake_platform.admin.step_up import (
    CEREMONY_TTL,
    StepUpExchangeFailed,
    StepUpGrant,
    StepUpRefused,
    StepUpService,
)

from intake_api.admin.deps import AdminCaller
from intake_api.errors import four_eyes_refused, not_found, step_up_refused
from intake_api.state import get_state

__all__ = ["GRANT_FIELD", "STEP_UP_HANDLERS", "stepped_up_approver"]

Handler = Callable[[Request, AdminCaller, AdminWiring, AdminRole], Awaitable[dict[str, Any]]]

#: The one body field an approve or countersign route takes.
GRANT_FIELD: Final = "step_up_grant"
GRANTED: Final = "admin.four_eyes.step_up.granted"
REDEEMED: Final = "admin.four_eyes.step_up.redeemed"
#: The id :class:`~intake_platform.admin.four_eyes.FourEyesService` mints.
_ACTION_ID: Final = re.compile(r"[0-9a-f]{32}")
_BEGIN_BODY: Final = frozenset({"action_id"})
_COMPLETE_BODY: Final = frozenset({"state", "code"})


def _count(stage: str, outcome: str) -> None:
    ADMIN_STEP_UP_TOTAL.labels(stage=stage, outcome=outcome).inc()


def _service(wiring: AdminWiring, stage: str) -> StepUpService:
    if wiring.step_up is None:
        _count(stage, "step_up_unconfigured")
        raise step_up_refused(503, "step_up_unconfigured")
    return wiring.step_up


async def _body(request: Request, fields: frozenset[str], stage: str) -> Mapping[str, str]:
    """Exactly ``fields``, every one a string — or a refusal naming neither."""
    try:
        payload = json.loads(await request.body())
    except (json.JSONDecodeError, UnicodeDecodeError):
        payload = None
    if (
        not isinstance(payload, dict)
        or set(payload) != fields
        or not all(isinstance(value, str) for value in payload.values())
    ):
        _count(stage, "step_up_body_refused")
        raise step_up_refused(422, "step_up_body_refused")
    return payload


def _refused(stage: str, refusal: StepUpRefused) -> Exception:
    _count(stage, refusal.code)
    status = 502 if isinstance(refusal, StepUpExchangeFailed) else 403
    return step_up_refused(status, refusal.code)


def _ref(grant: StepUpGrant) -> str:
    """The chain's name for one step-up: the action and the hashed token id.
    Neither the grant id (a bearer value) nor the credential id is written."""
    return f"four_eyes:{grant.action_id}:{grant.assertion_ref}"


async def _begin(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    service = _service(wiring, "begin")
    action_id = (await _body(request, _BEGIN_BODY, "begin"))["action_id"]
    expired = wiring.four_eyes.expire_due()
    if expired:
        ADMIN_PENDING_ACTION_EXPIRED_TOTAL.inc(expired)
    if _ACTION_ID.fullmatch(action_id) is None:
        _count("begin", "four_eyes_unknown")
        raise not_found()
    try:
        pending = wiring.four_eyes.get(action_id)
    except FourEyesRefused:
        _count("begin", "four_eyes_unknown")
        raise not_found() from None
    approver_role = caller.principal.first_permitted(pending.action.approver_roles)
    if approver_role is None:
        _count("begin", "four_eyes_approver_role")
        raise four_eyes_refused("four_eyes_approver_role")
    try:
        wiring.four_eyes.check_approvable(
            action_id, approver=caller.principal.actor_block(approver_role)
        )
    except SelfApproval as refusal:
        # files/08 §5: an intrusion signal, counted where it is refused
        ADMIN_FOUR_EYES_SELF_APPROVAL_ATTEMPT_TOTAL.inc()
        _count("begin", refusal.code)
        raise four_eyes_refused(refusal.code) from None
    except FourEyesRefused as refusal:
        _count("begin", refusal.code)
        raise four_eyes_refused(refusal.code) from None
    ceremony, url = service.begin(
        subject=caller.principal.subject,
        session_id=caller.principal.session_id,
        action_id=action_id,
    )
    _count("begin", "ok")
    return {
        "authorize_url": url,
        "action_id": action_id,
        "expires_at": (ceremony.started_at + CEREMONY_TTL).isoformat(),
    }


async def _complete(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    service = _service(wiring, "complete")
    payload = await _body(request, _COMPLETE_BODY, "complete")
    subject = caller.principal.subject
    try:
        grant = await run_in_threadpool(
            lambda: service.complete(
                subject=subject,
                session_id=caller.principal.session_id,
                state=payload["state"],
                code=payload["code"],
            )
        )
    except StepUpRefused as refusal:
        raise _refused("complete", refusal) from None
    await get_state(request).audit.record(
        actor=subject, action=GRANTED, resource_ref=_ref(grant), consent_scope=ADMIN_BASIS_REF
    )
    try:
        pending = wiring.four_eyes.get(grant.action_id)
    except FourEyesRefused as refusal:
        _count("complete", refusal.code)
        raise four_eyes_refused(refusal.code) from None
    _count("complete", "ok")
    return {
        "grant": grant.grant_id,
        "action_id": grant.action_id,
        "action": pending.action.id,
        "expires_at": grant.expires_at.isoformat(),
    }


async def stepped_up_approver(
    request: Request,
    caller: AdminCaller,
    wiring: AdminWiring,
    role: AdminRole,
    *,
    action_id: str,
    payload: Mapping[str, Any],
) -> tuple[ActorBlock, str]:
    """Spend the caller's grant for ``action_id``; return the approver block
    with the credential just asserted, and the assertion id four-eyes spends.

    Every approve and countersign route calls this and nothing else to obtain
    either value. A missing, unknown, expired, spent, foreign or mis-bound
    grant is refused 403 — never answered with the old session credential."""
    service = _service(wiring, "redeem")
    grant_id = payload.get(GRANT_FIELD)
    try:
        grant = service.redeem(
            grant_id if isinstance(grant_id, str) else "",
            subject=caller.principal.subject,
            session_id=caller.principal.session_id,
            action_id=action_id,
        )
    except StepUpRefused as refusal:
        raise _refused("redeem", refusal) from None
    # write-ahead: the use is on the chain before the approval it enables
    await get_state(request).audit.record(
        actor=caller.principal.subject,
        action=REDEEMED,
        resource_ref=_ref(grant),
        consent_scope=ADMIN_BASIS_REF,
    )
    _count("redeem", "ok")
    return grant.approver(caller.principal.actor_block(role)), grant.assertion_ref


STEP_UP_HANDLERS: dict[str, Handler] = {
    "admin.four_eyes.step_up.begin": _begin,
    "admin.four_eyes.step_up.complete": _complete,
}

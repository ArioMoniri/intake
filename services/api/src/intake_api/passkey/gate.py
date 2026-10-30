"""The step-up gate on D36's sensitive actions (INT-582).

``require_step_up(action)`` sits in a sensitive route's ``dependencies`` and
decides, for the patient asking:

1. **No active passkey** — the patient is NOT locked out. Today's tier still
   applies (the OTP-verified, DPoP-bound session; the dev-bearer tier in dev),
   exactly as the route behaved before this gate existed, and the response
   says so: ``X-Intake-Step-Up: otp_session`` and
   ``X-Intake-Passkey-Enrolment: offered`` (``unavailable`` when the passkey
   tier is unconfigured or the session cannot enrol).
2. **An active passkey** — the request must carry a grant
   (``X-Intake-Step-Up-Grant``) minted by a passkey assertion for THIS action
   on THIS device session in the last :data:`~.challenges.GRANT_TTL_S`
   seconds, unused. Spending it is atomic; a wrong grant is burnt.
3. **An active passkey and no passkey tier** (unconfigured) — refused 503,
   never downgraded to the OTP tier, because the downgrade is exactly what a
   SIM swap wants.

Every refusal made on the step-up signal alone names the manual path
(:data:`~.service.MANUAL_PATH`): an application a person reviews, which is
what KVKK m.11(1)(g) requires of a result reached solely by automated means.
Every decision is audited (``step_up.*``, resource ``step-up:<action>``) and
counted.

:data:`STEP_UP_ROUTES` is the map the tests hold the served app to: each D36
action, the routes that carry its gate. ``phone_change`` names none because
no route changes the phone number today; the test that reads this map fails
the day one is served without the gate.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import timedelta
from types import MappingProxyType

from fastapi import Depends, FastAPI, HTTPException, Request, Response, params

from intake_api.auth import Principal
from intake_api.consent_guard import _iter_api_routes
from intake_api.passkey.actions import D36_ACTIONS, StepUpAction
from intake_api.passkey.challenges import Spent
from intake_api.passkey.metrics import MetricReason, PasskeyEvent, record_event
from intake_api.passkey.service import (
    MANUAL_PATH,
    RECOVERY_COOLOFF_S,
    Caller,
    active_passkeys,
    audit_event,
    caller_of,
    passkey_not_configured,
    step_up_refused,
)
from intake_api.state import ApiState, State

__all__ = [
    "D36_ACTIONS",
    "ENROLMENT_HEADER",
    "GRANT_HEADER",
    "MANUAL_PATH",
    "STEP_UP_ROUTES",
    "TIER_HEADER",
    "StepUpAction",
    "StepUpGate",
    "require_step_up",
    "step_up_actions_of",
]

GRANT_HEADER = "X-Intake-Step-Up-Grant"
TIER_HEADER = "X-Intake-Step-Up"
ENROLMENT_HEADER = "X-Intake-Passkey-Enrolment"

STEP_UP_ROUTES: Mapping[StepUpAction, tuple[str, ...]] = MappingProxyType(
    {
        StepUpAction.DOCTOR_LINK_ISSUE: ("POST /v1/visits/{visit_id}/note/doctor-links",),
        StepUpAction.PHONE_CHANGE: (),
        # where the data leaves: the answer itself, not the tracker row that
        # records the request (which returns no personal data)
        StepUpAction.DATA_EXPORT: ("GET /v1/me/dsar/export/{request_id}",),
        # scheduling the erasure, and withdrawing one somebody scheduled: a
        # SIM-swapper must not cancel the holder's erasure either
        StepUpAction.DATA_DELETE: (
            "POST /v1/me/dsar/delete",
            "DELETE /v1/me/dsar/delete/{request_id}",
        ),
        # both halves of an enrolment: the options (which name the existing
        # passkeys) and the registration (which spends the grant)
        StepUpAction.PASSKEY_ADD: (
            "POST /v1/me/passkeys/registration/options",
            "POST /v1/me/passkeys/registration",
        ),
        StepUpAction.PASSKEY_REMOVE: ("DELETE /v1/me/passkeys/{passkey_id}",),
        StepUpAction.RECOVERY_CANCEL: ("DELETE /v1/me/passkeys/recovery",),
    }
)


def step_up_required(action: StepUpAction) -> HTTPException:
    return HTTPException(
        status_code=403,
        detail={"error": "step_up_required", "action": action.value, "manual_path": MANUAL_PATH},
    )


class StepUpGate:
    """One gate per action; the instance is what the route scan reads.

    ``spend=False`` reads the grant without spending it: only for the
    registration options, whose act the registration completes and spends.
    Every other gate spends."""

    def __init__(self, action: StepUpAction, *, spend: bool = True) -> None:
        self.action = action
        self.spend = spend

    async def _refuse(
        self, state: ApiState, caller: Caller, reason: str, error: HTTPException
    ) -> HTTPException:
        await audit_event(state.audit, caller, "step_up.refused", f"step-up:{self.action.value}")
        record_event(PasskeyEvent.GATE_REFUSED, MetricReason(reason))
        return error

    async def __call__(
        self, request: Request, response: Response, principal: Principal, state: State
    ) -> None:
        caller = caller_of(request, principal)
        service = state.passkey
        rows = await active_passkeys(
            engine=state.engine,
            audit=state.audit,
            caller=caller,
            now=service.now() if service is not None else state.clock(),
            cooloff=service.cooloff
            if service is not None
            else timedelta(seconds=RECOVERY_COOLOFF_S),
        )
        ref = f"step-up:{self.action.value}"
        if not rows:
            response.headers[TIER_HEADER] = "otp_session"
            response.headers[ENROLMENT_HEADER] = (
                "offered" if service is not None and caller.otp_tier else "unavailable"
            )
            await audit_event(state.audit, caller, "step_up.otp_tier", ref)
            record_event(PasskeyEvent.GATE_OTP_TIER)
            return
        if service is None:
            raise await self._refuse(
                state, caller, "passkey_not_configured", passkey_not_configured(manual_path=True)
            )
        grant = request.headers.get(GRANT_HEADER)
        if not grant:
            raise await self._refuse(state, caller, "grant_absent", step_up_required(self.action))
        check = service.spend_grant if self.spend else service.check_grant
        spent = await asyncio.to_thread(check, grant, caller, self.action)
        if spent is not Spent.OK:
            reason = f"grant_{spent.value}"
            raise await self._refuse(state, caller, reason, step_up_refused(self.action, reason))
        response.headers[TIER_HEADER] = "passkey"
        await audit_event(state.audit, caller, "step_up.passkey", ref)
        record_event(PasskeyEvent.GATE_PASSKEY)


def require_step_up(action: StepUpAction, *, spend: bool = True) -> params.Depends:
    """Put the step-up for ``action`` in front of a route."""
    dependency: params.Depends = Depends(StepUpGate(action, spend=spend))
    return dependency


def step_up_actions_of(app: FastAPI) -> dict[str, StepUpAction]:
    """``"METHOD /path"`` -> the action its gate steps up to, for every route
    that carries one."""
    gated: dict[str, StepUpAction] = {}
    for path, route in _iter_api_routes(list(app.routes)):
        for dependency in route.dependencies:
            if isinstance(dependency.dependency, StepUpGate):
                for method in sorted(route.methods or ()):
                    gated[f"{method} {path}"] = dependency.dependency.action
    return gated

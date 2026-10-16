"""Session start reads the tenant's voice control; live sessions follow the kill switch.

files/02 §375: *"the admin console can switch a tenant to typed mode (kill
switch) without a deploy"* (INT-182). This module is the runtime half of that
sentence, and it has two jobs:

**1 · Route every new session.** :meth:`VoiceSessionRouter.start` reads the
tenant's :class:`~intake_platform.voice_control.TenantVoiceControl` — once per
session start, never cached — decides a profile with :func:`decide_route` and
calls the shipped composition root for it
(``build_residency_tr_session`` / ``build_typed_session``, handed in as
builders by the worker). The decision, in order:

- the kill switch engaged → ``typed`` (it dominates everything);
- the session's canary bucket below the canary weight → the canary profile;
- otherwise → the tenant's default profile, which for a tenant nobody has
  configured is ``typed``.

A control that cannot be read starts the session ``typed`` and is counted:
the safer transport, never a guessed default (CLAUDE.md invariant 17).

**2 · Move live sessions.** :meth:`VoiceSessionRouter.poll` reads the control
of every tenant with a live voice session and, where the kill switch is
engaged, moves each of those sessions to the keyboard through INT-096's own
path — :meth:`~intake_voice_runtime.talker.session.TalkerSession.fall_back_to_typed`
with ``OPERATOR_KILL_SWITCH`` — the same swap INT-100's failover ladder uses:
one field (the egress), every slot kept. :meth:`VoiceSessionRouter.watch`
runs the poll every :data:`KILL_SWITCH_POLL_MS`, which is held below INT-100's
2 s typed-fallback budget, so a live session is on the keyboard within one
poll of the write. A session with no screen is not a switch target
(``KillSwitchNotArmed``): it stays in voice rather than going silent, and is
counted once. A poll that cannot read the control moves nothing — a live
session keeps the state it was routed under, and the failure is counted.

**The canary is deterministic.** :func:`canary_bucket` hashes the tenant and
session ids into 0..99, so a replay routes the same session the same way
(files/08 §0c F7 wants replay byte-exact) and a weight of *w* takes *w* of
every hundred buckets.

Nothing here awaits Backend Work or touches the Talker's tool set
(invariant 9): the poll is an ordinary function, and the watch loop sleeps on
the injected clock between polls.
"""

from __future__ import annotations

import enum
import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final

from clinical_schemas.common import FrozenModel
from intake_platform.voice_control import (
    CANARY_WEIGHT_MAX,
    TenantVoiceControl,
    VoiceControlReader,
    VoiceControlUnavailable,
    require_tenant_id,
)
from pydantic import Field

from intake_voice_runtime.composition import SessionStack
from intake_voice_runtime.metrics import (
    VOICE_CONTROL_READ_FAILURES_TOTAL,
    VOICE_KILL_SWITCH_FLIPS_TOTAL,
    VOICE_SESSION_ROUTES_TOTAL,
)
from intake_voice_runtime.ports import Clock
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.resilience.failover import TYPED_FALLBACK_DEADLINE_MS
from intake_voice_runtime.typed.switch import KillSwitchNotArmed, LaneSwitchReason

__all__ = [
    "KILL_SWITCH_POLL_MS",
    "FlipOutcome",
    "KillSwitchFlip",
    "RouteDecision",
    "RouteMismatch",
    "RouteReason",
    "RoutedSession",
    "VoiceSessionRouter",
    "canary_bucket",
    "decide_route",
]

#: How often live sessions re-read their tenant's control. Half of INT-100's
#: 2 s typed-fallback budget: the flip lands within one poll of the write.
KILL_SWITCH_POLL_MS: Final[float] = 1_000.0

_BUCKETS: Final = CANARY_WEIGHT_MAX


class RouteReason(enum.StrEnum):
    """Why a session started on the profile it did — the ``reason`` label."""

    DEFAULT = "default"
    CANARY = "canary"
    KILL_SWITCH = "kill_switch"
    CONTROL_UNREADABLE = "control_unreadable"


class FlipOutcome(enum.StrEnum):
    SWITCHED = "switched"
    NOT_ARMED = "not_armed"


class RouteMismatch(RuntimeError):
    """A builder returned a session on a profile other than the one routed."""


class RouteDecision(FrozenModel):
    tenant_id: str
    profile: VoiceProfile
    reason: RouteReason
    #: The control's revision the decision was taken on; ``None`` when the
    #: control could not be read.
    control_revision: int | None
    bucket: int = Field(ge=0, lt=_BUCKETS)


class KillSwitchFlip(FrozenModel):
    """One live session the poll acted on. Ids and a closed outcome only."""

    tenant_id: str
    session_id: str
    outcome: FlipOutcome
    at_ms: float = Field(ge=0.0)


@dataclass
class RoutedSession:
    tenant_id: str
    session_id: str
    decision: RouteDecision
    stack: SessionStack
    #: Set once a kill switch found no screen to move this session onto, so it
    #: is counted once rather than on every poll.
    not_armed: bool = False


def canary_bucket(tenant_id: str, session_id: str) -> int:
    """The session's canary bucket, 0..99 — a hash, so a replay agrees."""
    digest = hashlib.sha256(f"{tenant_id}\x00{session_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % _BUCKETS


def decide_route(control: TenantVoiceControl, *, bucket: int) -> tuple[VoiceProfile, RouteReason]:
    """The routing rule, pure. See the module docstring for the order."""
    if not 0 <= bucket < _BUCKETS:
        raise ValueError(f"a canary bucket is 0..{_BUCKETS - 1}")
    if control.kill_switch:
        return VoiceProfile.TYPED, RouteReason.KILL_SWITCH
    if control.canary_profile is not None and bucket < control.canary_weight:
        return VoiceProfile(control.canary_profile.value), RouteReason.CANARY
    return VoiceProfile(control.default_profile.value), RouteReason.DEFAULT


class VoiceSessionRouter:
    """Session starts and live-session moves for one runtime process."""

    def __init__(
        self,
        *,
        controls: VoiceControlReader,
        clock: Clock,
        poll_ms: float = KILL_SWITCH_POLL_MS,
    ) -> None:
        if not 0 < poll_ms < TYPED_FALLBACK_DEADLINE_MS:
            raise ValueError(
                f"the kill-switch poll must sit inside the {TYPED_FALLBACK_DEADLINE_MS:g} ms "
                f"typed-fallback budget (INT-100); got {poll_ms:g} ms"
            )
        self._controls = controls
        self._clock = clock
        self._poll_ms = poll_ms
        self._live: dict[str, RoutedSession] = {}

    def decide(self, *, tenant_id: str, session_id: str) -> RouteDecision:
        """Read the control now and route one session. Counted either way."""
        tenant = require_tenant_id(tenant_id)
        bucket = canary_bucket(tenant, session_id)
        try:
            control = self._controls.read(tenant)
        except VoiceControlUnavailable as failure:
            VOICE_CONTROL_READ_FAILURES_TOTAL.labels(phase="start", code=failure.code).inc()
            decision = RouteDecision(
                tenant_id=tenant,
                profile=VoiceProfile.TYPED,
                reason=RouteReason.CONTROL_UNREADABLE,
                control_revision=None,
                bucket=bucket,
            )
        else:
            profile, reason = decide_route(control, bucket=bucket)
            decision = RouteDecision(
                tenant_id=tenant,
                profile=profile,
                reason=reason,
                control_revision=control.revision,
                bucket=bucket,
            )
        VOICE_SESSION_ROUTES_TOTAL.labels(
            tenant=tenant, profile=decision.profile.value, reason=decision.reason.value
        ).inc()
        return decision

    def start(
        self,
        *,
        tenant_id: str,
        session_id: str,
        builders: Mapping[VoiceProfile, Callable[[], SessionStack]],
    ) -> RoutedSession:
        """Route and compose one session. Both builders are required: the kill
        switch's target has to be buildable for every session, not only for
        the ones it happens to fire on."""
        missing = sorted(profile.value for profile in VoiceProfile if profile not in builders)
        if missing:
            raise ValueError(
                f"a session start needs a builder for every profile; missing {missing}"
            )
        if session_id in self._live:
            raise ValueError("that session id has already been started on this router")
        decision = self.decide(tenant_id=tenant_id, session_id=session_id)
        stack = builders[decision.profile]()
        if stack.profile is not decision.profile:
            raise RouteMismatch(
                f"routed to {decision.profile.value} but the builder composed {stack.profile.value}"
            )
        routed = RoutedSession(
            tenant_id=decision.tenant_id, session_id=session_id, decision=decision, stack=stack
        )
        self._live[session_id] = routed
        return routed

    def end(self, session_id: str) -> None:
        """Close a finished session, then forget it; the poll no longer considers it.

        The close (INT-540) is queued behind the session's last answers and
        returns at once: a tense anchor still asked and unanswered is resolved
        and evaluated by the Backend pump, so it cannot outlive the session.
        Then the Talker stops watching for a RED between turns (INT-531).
        """
        routed = self._live.pop(session_id, None)
        if routed is not None:
            routed.stack.close()
            routed.stack.session.stop_red_watch()

    def live(self) -> tuple[RoutedSession, ...]:
        return tuple(self._live.values())

    def poll(self) -> tuple[KillSwitchFlip, ...]:
        """One pass over live voice sessions; one control read per tenant."""
        by_tenant: dict[str, list[RoutedSession]] = {}
        for routed in self._live.values():
            if routed.stack.profile is VoiceProfile.RESIDENCY_TR and not routed.not_armed:
                by_tenant.setdefault(routed.tenant_id, []).append(routed)
        flips: list[KillSwitchFlip] = []
        for tenant, sessions in sorted(by_tenant.items()):
            try:
                control = self._controls.read(tenant)
            except VoiceControlUnavailable as failure:
                VOICE_CONTROL_READ_FAILURES_TOTAL.labels(phase="poll", code=failure.code).inc()
                continue
            if not control.kill_switch:
                continue
            for routed in sessions:
                flips.append(self._flip(routed))
        return tuple(flips)

    async def watch(self) -> None:
        """Poll forever on the injected clock. Cancel the task to stop it."""
        while True:
            await self._clock.sleep(self._poll_ms / 1000.0)
            self.poll()

    def _flip(self, routed: RoutedSession) -> KillSwitchFlip:
        try:
            routed.stack.session.fall_back_to_typed(LaneSwitchReason.OPERATOR_KILL_SWITCH)
        except KillSwitchNotArmed:
            routed.not_armed = True
            outcome = FlipOutcome.NOT_ARMED
        else:
            outcome = FlipOutcome.SWITCHED
        VOICE_KILL_SWITCH_FLIPS_TOTAL.labels(tenant=routed.tenant_id, outcome=outcome.value).inc()
        return KillSwitchFlip(
            tenant_id=routed.tenant_id,
            session_id=routed.session_id,
            outcome=outcome,
            at_ms=self._clock.now_ms(),
        )

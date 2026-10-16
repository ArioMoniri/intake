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

**3 · Hold an ended session's RED watch until its close has run** (INT-545).
:meth:`VoiceSessionRouter.end` queues the session's close (INT-540) behind its
last answers, and the close — or an answer still queued ahead of it — can
raise a RED. An ended session takes no next turn, so the Talker's between-turn
watch (INT-531) is then the only route that RED has to the patient's device.
``end`` therefore keeps the watch running and records the close; every
:meth:`~VoiceSessionRouter.poll` first releases the ended sessions whose close
has settled (completed, failed or cancelled) on two consecutive polls while
the watch is idle and the Backend is not inside a Work. The second poll is a
grace for a Backend pump on a worker thread, which marks a Work settled a
moment before it posts the RED that Work raised. Only a session whose queue a
RED had already sealed, with that RED already taken and the Backend idle, is
released at ``end`` itself. Releasing tells the clinician of any RED the
device was never reached with
(:meth:`~intake_voice_runtime.talker.session.TalkerSession.end_red_watch`).

**The contract for the worker that composes sessions** (INT-542 item 1): it
runs :meth:`VoiceSessionRouter.watch` on the sessions' event loop — or calls
:meth:`~VoiceSessionRouter.poll` itself on that loop — for as long as the
router holds a session, live or closing. A worker that ends sessions through
``end`` and never polls leaves every ended session in :meth:`closing`, its
watch parked, for the life of the process. ``end`` called off the loop cannot
start a watch the session never started; the next poll on the loop does.

**The canary is deterministic.** :func:`canary_bucket` hashes the tenant and
session ids into 0..99, so a replay routes the same session the same way
(files/08 §0c F7 wants replay byte-exact) and a weight of *w* takes *w* of
every hundred buckets.

Nothing here awaits Backend Work or touches the Talker's tool set
(invariant 9): the poll is an ordinary function, and the watch loop sleeps on
the injected clock between polls.
"""

from __future__ import annotations

import asyncio
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
from intake_voice_runtime.ports import Clock, WorkState
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.resilience.failover import TYPED_FALLBACK_DEADLINE_MS
from intake_voice_runtime.talker.session import TalkerSession
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

#: A Work in one of these has finished; whatever it raised has been posted.
_SETTLED: Final = frozenset({WorkState.COMPLETED, WorkState.FAILED, WorkState.CANCELLED})


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


@dataclass
class _Closing:
    """An ended session whose RED watch the router still holds (INT-545)."""

    stack: SessionStack
    #: The close ``end`` queued, or ``None`` where a RED had already sealed the
    #: queue and there was nothing to queue.
    work_id: str | None
    #: The close was found settled on the previous poll.
    settled_seen: bool = False

    def settled(self) -> bool:
        if self.work_id is None:
            return True
        return self.stack.agent.record(self.work_id).state in _SETTLED

    def quiescent(self) -> bool:
        """Nothing more can reach the watch, and the watch has nothing left to do.

        A RED is determined, settled, sealed behind and posted inside one
        state-lane Work, under the engine lock (``BackendAgent._execute_state``).
        While that lock is held a RED may be on its way to the mailbox; once it
        is free and the watch is idle, every RED raised so far has been taken
        and delivered or recorded as failed.
        """
        if self.stack.agent.engine_lock.locked():
            return False
        return self.stack.session.red_watch_idle


def _keep_watching(session: TalkerSession) -> None:
    """Start the session's RED watch if none is running, where a loop runs.

    ``ensure_red_watch`` is idempotent and needs the running loop; off the
    loop there is nothing to start it on, and the next poll does it.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return
    session.ensure_red_watch()


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
        #: INT-545: ended sessions whose RED watch outlives their close.
        self._closing: dict[str, _Closing] = {}

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
        if session_id in self._live or session_id in self._closing:
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
        """Close a finished session; the kill-switch poll no longer considers it.

        The close (INT-540) is queued behind the session's last answers and
        returns at once: a tense anchor still asked and unanswered is resolved
        and evaluated by the Backend pump, so it cannot outlive the session.
        The Talker's between-turn watch (INT-531) keeps running until the
        close has settled and the watch is idle, so a RED the close raises
        still reaches the device (INT-545); :meth:`poll` releases it. Only a
        session already sealed by a RED that has been taken is released here.
        Awaits nothing.
        """
        routed = self._live.pop(session_id, None)
        if routed is None:
            return
        ticket = routed.stack.close()
        closing = _Closing(stack=routed.stack, work_id=None if ticket is None else ticket.work_id)
        if ticket is None and closing.quiescent():
            routed.stack.session.end_red_watch()
            return
        self._closing[session_id] = closing
        _keep_watching(routed.stack.session)

    def live(self) -> tuple[RoutedSession, ...]:
        return tuple(self._live.values())

    def closing(self) -> tuple[str, ...]:
        """Ended sessions whose RED watch the router still holds (INT-545)."""
        return tuple(self._closing)

    def poll(self) -> tuple[KillSwitchFlip, ...]:
        """Release the ended sessions that are done, then one pass over live
        voice sessions; one control read per tenant."""
        self._release_closed()
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

    def _release_closed(self) -> None:
        """Let an ended session's watch go once its close is done (INT-545).

        Released when the close was settled on this poll and the one before,
        and the session is quiescent; until then the watch is kept running,
        and started if it never was.
        """
        for session_id, closing in tuple(self._closing.items()):
            if closing.settled():
                if closing.settled_seen and closing.quiescent():
                    del self._closing[session_id]
                    closing.stack.session.end_red_watch()
                    continue
                closing.settled_seen = True
            _keep_watching(closing.stack.session)

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

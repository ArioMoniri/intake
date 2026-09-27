"""One circuit breaker per vendor component (INT-100; files/10 §5 LLM10).

files/10 §5 lists *"circuit breakers per vendor"* among the LLM10 controls and
files/03 §4.9.4 says what a failing speech lane costs the patient: every turn
spent dialling a dead TTS is a question nobody hears. The breaker is what
turns the first few of those failures into a fact the *next* session can act
on before it dials anything.

It is the textbook three-state machine and deliberately nothing more:

- **closed** — calls go through; ``failure_threshold`` *consecutive* failures
  open it, and any success resets the count.
- **open** — calls are refused without touching the vendor until ``open_ms``
  has passed on the injected clock.
- **half open** — exactly one trial call at a time is let through; a failure
  re-opens it (and restarts the cooldown from *now*), ``close_after`` clean
  trials close it.

**Where the defaults come from.** Neither number is invented for this module:

- ``open_ms = 30 000`` is files/03 §4.5b's anti-flap rule — *"never change
  state more than once per 30 s"* — applied to the one state machine here
  that could otherwise flap between a dying vendor and a recovering one.
- ``failure_threshold = 2`` is §4.5b T3's own count for the same situation
  seen from the patient's side — *"two consecutive
  ``request_repeat_or_clarify`` on the same step"* — before the session gives
  up on the channel.

Both are policy, not code: :class:`BreakerPolicy` is a value, and
:class:`BreakerBoard` takes a default plus per-vendor overrides.

**The board is shared; the breaker is per vendor.** One
:class:`BreakerBoard` per process, one :class:`CircuitBreaker` per registry
component, and every session's failover ladder consults the same object — so
the vendor that failed session A is skipped by session B. Which lane a
*session* is on is not the breaker's business: that is sticky per session
(:mod:`~intake_voice_runtime.resilience.failover`).

State and transitions are exported as the catalogued families
``vendor_breaker_state`` (one-hot) and ``vendor_breaker_transitions_total``
(CLAUDE.md invariant 13). Every method is an ordinary function — no awaitable,
no socket, no sleep — so a breaker costs a Talker turn nothing (invariant 9).
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from typing import Protocol

from clinical_schemas.common import FrozenModel
from pydantic import Field

from intake_voice_runtime.metrics import VENDOR_BREAKER_STATE, VENDOR_BREAKER_TRANSITIONS_TOTAL

__all__ = [
    "BreakerBoard",
    "BreakerPolicy",
    "BreakerState",
    "CircuitBreaker",
    "NowMs",
]


class BreakerState(enum.StrEnum):
    """The three states. A closed set, and the ``state`` label's whole domain."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class BreakerPolicy(FrozenModel):
    """When a breaker opens, how long it stays open, and what closes it."""

    failure_threshold: int = Field(
        default=2,
        ge=1,
        description="Consecutive failures that open a closed breaker (files/03 §4.5b T3).",
    )
    open_ms: float = Field(
        default=30_000.0,
        gt=0.0,
        description="How long an open breaker refuses before one trial (files/03 §4.5b "
        "anti-flap: never change state more than once per 30 s).",
    )
    close_after: int = Field(
        default=1,
        ge=1,
        description="Clean half-open trials that close the breaker again.",
    )


class NowMs(Protocol):
    """The one clock member a breaker reads. ``ports.Clock`` satisfies it."""

    def now_ms(self) -> float: ...


class CircuitBreaker:
    """One vendor component's breaker. See the module docstring."""

    def __init__(self, component: str, *, policy: BreakerPolicy, clock: NowMs) -> None:
        self._component = component
        self._policy = policy
        self._clock = clock
        self._state = BreakerState.CLOSED
        self._failures = 0
        self._successes = 0
        self._opened_at_ms = 0.0
        self._trial_in_flight = False
        self._publish()

    @property
    def component(self) -> str:
        return self._component

    @property
    def policy(self) -> BreakerPolicy:
        return self._policy

    @property
    def state(self) -> BreakerState:
        """The stored state. Reading it never moves the machine."""
        return self._state

    def admits(self) -> bool:
        """Whether :meth:`allow` would let a call through right now — a peek.

        The failover ladder uses this to count how many lanes will share the
        remaining budget, which must not itself start a half-open trial.
        """
        if self._state is BreakerState.CLOSED:
            return True
        if self._state is BreakerState.OPEN:
            return self._cooled_down()
        return not self._trial_in_flight

    def allow(self) -> bool:
        """Admit one call, or refuse it. The only method that starts a trial."""
        if self._state is BreakerState.CLOSED:
            return True
        if self._state is BreakerState.OPEN:
            if not self._cooled_down():
                return False
            self._move(BreakerState.HALF_OPEN)
            self._successes = 0
        if self._trial_in_flight:
            return False
        self._trial_in_flight = True
        return True

    def record_success(self) -> None:
        """An admitted call answered."""
        if self._state is BreakerState.CLOSED:
            self._failures = 0
        elif self._state is BreakerState.HALF_OPEN:
            self._trial_in_flight = False
            self._successes += 1
            if self._successes >= self._policy.close_after:
                self._failures = 0
                self._move(BreakerState.CLOSED)
        # OPEN: no call was admitted, so there is no outcome to report.

    def record_failure(self) -> None:
        """An admitted call failed."""
        if self._state is BreakerState.CLOSED:
            self._failures += 1
            if self._failures >= self._policy.failure_threshold:
                self._open()
        elif self._state is BreakerState.HALF_OPEN:
            self._trial_in_flight = False
            self._open()
        # OPEN: as above — nothing was admitted.

    # --- internals -------------------------------------------------------------------

    def _cooled_down(self) -> bool:
        return self._clock.now_ms() - self._opened_at_ms >= self._policy.open_ms

    def _open(self) -> None:
        self._opened_at_ms = self._clock.now_ms()
        self._move(BreakerState.OPEN)

    def _move(self, target: BreakerState) -> None:
        VENDOR_BREAKER_TRANSITIONS_TOTAL.labels(
            component=self._component, from_state=self._state.value, to_state=target.value
        ).inc()
        self._state = target
        self._publish()

    def _publish(self) -> None:
        for state in BreakerState:
            VENDOR_BREAKER_STATE.labels(component=self._component, state=state.value).set(
                1.0 if state is self._state else 0.0
            )


class BreakerBoard:
    """Every vendor's breaker, one per component, shared across sessions."""

    def __init__(
        self,
        *,
        clock: NowMs,
        policy: BreakerPolicy | None = None,
        overrides: Mapping[str, BreakerPolicy] | None = None,
    ) -> None:
        self._clock = clock
        self._policy = policy or BreakerPolicy()
        self._overrides = dict(overrides or {})
        self._breakers: dict[str, CircuitBreaker] = {}

    def breaker(self, component: str) -> CircuitBreaker:
        """The breaker for ``component`` — created on first use, then the same one."""
        found = self._breakers.get(component)
        if found is None:
            found = CircuitBreaker(
                component,
                policy=self._overrides.get(component, self._policy),
                clock=self._clock,
            )
            self._breakers[component] = found
        return found

    def states(self) -> dict[str, BreakerState]:
        """A snapshot, for the console and for evidence."""
        return {component: breaker.state for component, breaker in self._breakers.items()}

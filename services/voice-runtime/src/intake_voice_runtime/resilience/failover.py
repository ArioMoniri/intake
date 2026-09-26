"""Speech-lane failover under one 2 s budget (INT-100; files/03 §4.9.4 row 11).

files/03 §4.9.4 row 11 writes the whole policy in one sentence: *"On failure:
fall to a cached bridge clip, then to row 12 for the rest of the session, then
to ``typed``."* :class:`FailoverSynthesizer` is the middle and last clauses —
the cached bridge is copy no human has signed off yet (``safe_bridge_clip_id``
stays ``None``, docs/evidence/INT-091.md), so this ladder begins at the lanes.

It **is** a :class:`~intake_voice_runtime.ports.SpeechSynthesizer`. That is
the whole integration: ``SpeechRouter`` already speaks to that port, the
metering decorator already wraps it, and the composition root already takes
one. Nothing above the port learns that there is more than one lane.

**The order** is a :class:`~intake_voice_runtime.resilience.order.FailoverOrder`
read from the registry, and the lanes bound to it must be exactly its
components — a missing lane is a deployment that silently lost one, and an
extra lane is a lane the registry never sanctioned, which is how a cloud
adapter handed in by a deployment is refused (CLAUDE.md invariant 19).

**The budget.** One deadline per synthesis, :data:`TYPED_FALLBACK_DEADLINE_MS`
= 2 000 ms — INT-024's acceptance bound, restated in milliseconds and pinned
equal to it by a test. Each attempt is handed its share **as the wire
timeout**: the time left, divided by the lanes still able to take a call.
Dividing is what keeps a hung primary from spending the fallback's time — two
hung lanes are abandoned at 1 000 ms each and the patient is reading the
question at 2 000 — while a primary that dies fast leaves nearly the whole
budget to the next lane. A lane whose breaker is open costs nothing and is not
counted in the division. The lanes are synchronous, like every speech port in
this service, so the bound rests on each adapter honouring the timeout it is
handed on the wire; ``HttpSpeechSynthesizer`` puts it on the request, and the
chaos test holds the far side of that wire to it.

**Sticky, per session.** Once a session has failed over it never returns to
an earlier lane — *"for the rest of the session"*, and §4.9.1 row 11's
*"two voices mid-session breaks voice identity"* makes swapping back a worse
defect than the slower voice. The breaker is per vendor and shared
(:class:`~intake_voice_runtime.resilience.breaker.BreakerBoard`), so a *new*
session skips a vendor that is known dead without dialling it; this object
only remembers where *this* session is.

**Exhaustion** raises :class:`SpeechLanesExhausted`, and the Talker session
turns it into the typed profile inside the same turn
(:meth:`~intake_voice_runtime.talker.session.TalkerSession.fall_back_to_typed`
with ``SPEECH_LANES_EXHAUSTED``). The exception names components and
outcomes only — never the sentence (CLAUDE.md invariant 6).

Two things are deliberately **not** lane failures: a numeral in the text
(invariant 22 is refused before any lane or breaker is touched — it is the
caller's defect, not a vendor's), and an attempt the budget left no time for
(``OUT_OF_TIME`` blames nobody's breaker).
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from typing import Final, Protocol, runtime_checkable

from clinical_schemas.common import FrozenModel
from pydantic import Field

from intake_voice_runtime.metrics import VENDOR_FAILOVERS_TOTAL
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.resilience.breaker import BreakerBoard, NowMs
from intake_voice_runtime.resilience.order import FailoverOrder
from intake_voice_runtime.talker.speech import assert_no_numeral

__all__ = [
    "TYPED_FALLBACK_DEADLINE_MS",
    "TYPED_LANE",
    "AttemptOutcome",
    "BoundedSynthesizer",
    "FailoverSynthesizer",
    "LaneAttempt",
    "LaneBindingMismatch",
    "LaneFailover",
    "SpeechLanesExhausted",
]

#: INT-024 / INT-100 acceptance: the patient holds the question — spoken by the
#: next lane or drawn on the screen — no later than this after the turn's
#: synthesis began. Measured at the Talker's egress, server side, the same
#: place INT-091 and INT-093 measure their budgets.
TYPED_FALLBACK_DEADLINE_MS: Final[float] = 2_000.0

#: The ``to_component`` label value when no speech lane is left. It is a
#: profile, not a registry component — the registry's own ``voice-runtime``
#: row records that ``typed`` "is a mode of this same service".
TYPED_LANE: Final[str] = VoiceProfile.TYPED.value


@runtime_checkable
class BoundedSynthesizer(Protocol):
    """A speech lane that accepts a per-call wire timeout.

    The ``SpeechSynthesizer`` port plus one keyword. Both adapters in
    :mod:`intake_voice_runtime.adapters.speech` satisfy it; ``None`` means the
    adapter's own configured timeout.
    """

    def synthesize(
        self, text_tr: str, voice_id: str, *, timeout_s: float | None = None
    ) -> bytes: ...


class AttemptOutcome(enum.StrEnum):
    """What happened to one lane in one synthesis."""

    SERVED = "served"
    FAILED = "failed"
    SKIPPED_OPEN = "skipped_open"
    OUT_OF_TIME = "out_of_time"


class LaneAttempt(FrozenModel):
    """One lane's part in one synthesis: an id, an outcome, a duration."""

    component: str
    outcome: AttemptOutcome
    elapsed_ms: float = Field(ge=0.0)


class LaneFailover(FrozenModel):
    """A session moved off a lane. ``to_component`` is ``typed`` at the end."""

    from_component: str
    to_component: str
    at_ms: float = Field(ge=0.0, description="Session-clock milliseconds.")


class LaneBindingMismatch(RuntimeError):
    """The lanes handed in are not exactly the lanes the registry orders."""


class SpeechLanesExhausted(RuntimeError):
    """No speech lane is left for this session. The session goes typed."""

    def __init__(self, attempts: tuple[LaneAttempt, ...]) -> None:
        self.attempts = attempts
        summary = ", ".join(f"{a.component}={a.outcome.value}" for a in attempts) or "none left"
        super().__init__(
            f"every speech lane is exhausted ({summary}); the session continues on the "
            "text lane (files/03 §4.9.4 row 11: then to typed)"
        )


class FailoverSynthesizer:
    """The session's speech lanes, tried in registry order under their breakers."""

    def __init__(
        self,
        order: FailoverOrder,
        lanes: Mapping[str, BoundedSynthesizer],
        *,
        board: BreakerBoard,
        clock: NowMs,
        voice_ids: Mapping[str, str] | None = None,
        deadline_ms: float = TYPED_FALLBACK_DEADLINE_MS,
    ) -> None:
        if deadline_ms <= 0:
            raise ValueError(f"the failover deadline must leave time to speak (got {deadline_ms})")
        ordered = set(order.components)
        missing = sorted(ordered - set(lanes))
        unordered = sorted(set(lanes) - ordered)
        if missing or unordered:
            raise LaneBindingMismatch(
                f"the registry orders {list(order.components)}; missing {missing}, "
                f"not in the order {unordered}. A lane the registry does not name as a "
                "fallback cannot be failed over to — including any cloud adapter "
                "(CLAUDE.md invariant 19)"
            )
        overrides = dict(voice_ids or {})
        stray = sorted(set(overrides) - ordered)
        if stray:
            raise LaneBindingMismatch(f"voices bound to lanes not in the order: {stray}")
        self._order = order
        self._lanes = tuple((component, lanes[component]) for component in order.components)
        self._voice_ids = overrides
        self._board = board
        self._clock = clock
        self._deadline_ms = deadline_ms
        self._position = 0
        self._failovers: list[LaneFailover] = []
        self._last_attempts: tuple[LaneAttempt, ...] = ()
        for component in order.components:
            board.breaker(component)  # every bound lane's state is visible from the start

    @property
    def order(self) -> FailoverOrder:
        return self._order

    @property
    def current_component(self) -> str | None:
        """The lane this session speaks through next; ``None`` once exhausted."""
        if self._position < len(self._lanes):
            return self._lanes[self._position][0]
        return None

    @property
    def failovers(self) -> tuple[LaneFailover, ...]:
        return tuple(self._failovers)

    @property
    def last_attempts(self) -> tuple[LaneAttempt, ...]:
        return self._last_attempts

    def synthesize(self, text_tr: str, voice_id: str) -> bytes:
        """Speak through the first lane that answers inside the budget."""
        assert_no_numeral(text_tr)
        started_ms = self._clock.now_ms()
        attempts: list[LaneAttempt] = []
        while self._position < len(self._lanes):
            component, lane = self._lanes[self._position]
            remaining_ms = self._deadline_ms - (self._clock.now_ms() - started_ms)
            if remaining_ms <= 0:
                attempts.append(
                    LaneAttempt(
                        component=component, outcome=AttemptOutcome.OUT_OF_TIME, elapsed_ms=0.0
                    )
                )
                self._leave(component, exhausted=True)
                break
            sharing = self._lanes_admitting()
            breaker = self._board.breaker(component)
            if not breaker.allow():
                attempts.append(
                    LaneAttempt(
                        component=component, outcome=AttemptOutcome.SKIPPED_OPEN, elapsed_ms=0.0
                    )
                )
                self._leave(component)
                continue
            attempt_started = self._clock.now_ms()
            try:
                frames = lane.synthesize(
                    text_tr,
                    self._voice_ids.get(component, voice_id),
                    timeout_s=remaining_ms / sharing / 1000.0,
                )
            except Exception:
                breaker.record_failure()
                attempts.append(
                    LaneAttempt(
                        component=component,
                        outcome=AttemptOutcome.FAILED,
                        elapsed_ms=self._clock.now_ms() - attempt_started,
                    )
                )
                self._leave(component)
                continue
            breaker.record_success()
            attempts.append(
                LaneAttempt(
                    component=component,
                    outcome=AttemptOutcome.SERVED,
                    elapsed_ms=self._clock.now_ms() - attempt_started,
                )
            )
            self._last_attempts = tuple(attempts)
            return frames
        self._last_attempts = tuple(attempts)
        raise SpeechLanesExhausted(self._last_attempts)

    def _lanes_admitting(self) -> int:
        """Lanes from here on whose breaker would take a call — the budget's divisor."""
        return sum(
            1
            for component, _ in self._lanes[self._position :]
            if self._board.breaker(component).admits()
        )

    def _leave(self, component: str, *, exhausted: bool = False) -> None:
        """Move this session off ``component`` for good, and say where to."""
        self._position = len(self._lanes) if exhausted else self._position + 1
        target = self.current_component or TYPED_LANE
        VENDOR_FAILOVERS_TOTAL.labels(from_component=component, to_component=target).inc()
        self._failovers.append(
            LaneFailover(from_component=component, to_component=target, at_ms=self._clock.now_ms())
        )

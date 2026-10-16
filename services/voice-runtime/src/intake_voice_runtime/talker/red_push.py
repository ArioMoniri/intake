"""Layer B → Layer A, between turns: the push that carries a RED (INT-531).

Before this module the Talker drained Layer B only when it took a turn
(:meth:`~intake_voice_runtime.talker.session.TalkerSession.take_turn`). A
rules-engine RED that Layer B evaluated while no turn was running — the
patient silent, the patient still talking, the agent's own question still
playing — waited for the next turn, so files/02 §8.2's *"RED preemption
≤ 300 ms from rule evaluation"* held only when a turn happened to follow the
evaluation promptly.

The push closes that gap with two halves and nothing in between:

- **Layer B holds :class:`RedPush`.** One member, and it is not awaitable —
  the same structural trick ADR-009 plays on ``WorkSubmitter``, run the other
  way. Layer B can *post* a RED; it cannot call into the Talker, hand it a
  coroutine, or wait on it. The queue posts only a result it has already
  derived ``preempt`` for, put through the preempt gate, settled and (where
  the register stops the intake) sealed behind.
- **The Talker holds the other end of :class:`RedMailbox`** and parks on it
  in its own between-turn loop
  (:meth:`~intake_voice_runtime.talker.session.TalkerSession.watch_reds`),
  which hands each RED to the preemption path the moment it lands.

**Only a rules-engine RED can be posted** (CLAUDE.md invariant 9). The mailbox
refuses anything that is not ``priority: preempt`` over a
:class:`~clinical_schemas.triage.RulesTriageResult` at ``RED`` — re-checked
here, not trusted, because a result built around its validator would
otherwise ride the one route that interrupts the patient. The Talker then
re-runs its own provenance gate before the path.

**The post is thread-safe and never blocks.** Layer B's pump may run on a
worker thread (the queue's double guard is two ``threading`` locks). The post
appends under a lock and asks the Talker's loop, via
``call_soon_threadsafe``, to wake; it never touches anything that loop owns. A
loop that has gone away keeps the RED in the mailbox, and the session's next
turn drains the same settled RED from the queue in any case: the push is the
fast route, never the only one.

**An ended session has no next turn** (INT-545). There the push is the only
route, so the session router keeps the watch running past the session's end
until the close it queued has settled and :attr:`RedMailbox.empty` holds.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
from collections import deque
from typing import Protocol, runtime_checkable

from clinical_schemas.triage import RulesTriageResult, TriageLevel

from intake_voice_runtime.talker.preemption import BackendResult, PreemptRefused, Priority

__all__ = ["RedMailbox", "RedPush"]


@runtime_checkable
class RedPush(Protocol):
    """Layer B's half of the push. **One member, and it is not awaitable.**"""

    def push(self, result: BackendResult) -> None: ...


class RedMailbox:
    """One session's mailbox: Layer B posts a RED, the Talker's loop takes it.

    The wake is an :class:`asyncio.Event` bound to whichever loop last took
    from the mailbox, so a session driven by a fresh loop per call — as the
    fake-clock tests drive it — rebinds rather than waking a loop that has
    closed.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._posted: deque[BackendResult] = deque()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._wake: asyncio.Event | None = None

    def push(self, result: BackendResult) -> None:
        """Post one rules-engine RED and wake the Talker's loop. Returns at once."""
        triage = result.presentation.triage_update
        if (
            result.priority is not Priority.PREEMPT
            or not isinstance(triage, RulesTriageResult)
            or triage.level is not TriageLevel.RED
        ):
            raise PreemptRefused(
                "only a rules-engine RED at priority=preempt may be pushed between "
                "turns (CLAUDE.md invariants 1 and 9); everything else waits for the "
                "turn's drain and a safe insertion window"
            )
        with self._lock:
            self._posted.append(result)
            loop, wake = self._loop, self._wake
        if loop is not None and wake is not None:
            # A closed loop raises here. The RED stays posted for the next loop
            # that takes, and the queue still holds it for the next turn's drain.
            with contextlib.suppress(RuntimeError):
                loop.call_soon_threadsafe(wake.set)

    @property
    def empty(self) -> bool:
        """True when nothing posted is waiting to be taken (INT-545).

        Read under the post's lock, so it is true from any thread only once
        every RED posted so far has been taken by the watch. The router reads
        it before it lets an ended session's watch go.
        """
        with self._lock:
            return not self._posted

    async def take(self) -> tuple[BackendResult, ...]:
        """Park until a RED is posted, then take every RED posted so far."""
        running = asyncio.get_running_loop()
        with self._lock:
            if self._loop is not running or self._wake is None:
                self._loop, self._wake = running, asyncio.Event()
            wake = self._wake
        while True:
            with self._lock:
                if self._posted:
                    taken = tuple(self._posted)
                    self._posted.clear()
                    return taken
                # Cleared only while nothing is posted, under the lock a post
                # takes: a wake-up for a RED already taken cannot spin the loop,
                # and one for a RED posted after this line cannot be lost.
                wake.clear()
            await wake.wait()

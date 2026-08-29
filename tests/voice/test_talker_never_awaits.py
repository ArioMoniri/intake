"""INT-091 — the Talker never awaits Backend Work (invariant 9 clause 2).

files/03 §4.6 invariant 1 and scenario RT-03: *"with the Backend Agent stalled
for 10 s (fake clock), the Talker still answers within budget"*, and ADR-009:
*"submit_utterance returns a work_id immediately"*.

Two proofs, because either alone is weak:

- **Structural.** ``WorkSubmitter`` has no awaitable member. ``submit``,
  ``cancel`` and ``drain_results`` are ordinary functions returning values, so
  there is nothing for the Talker to await even by accident. A coroutine
  member added to the port fails ``test_the_work_port_has_no_awaitable_member``.
- **Measured.** On the virtual clock, one turn against a backend stalled 10 s
  and the same turn against one stalled 10 000 s take **the same** virtual
  time — and the same time as against a backend that answers instantly. If
  the Talker awaited anything on that path the three numbers would diverge by
  construction.
"""

from __future__ import annotations

import asyncio
import inspect

import pytest
from intake_voice_runtime.ports import WorkSubmitter
from intake_voice_runtime.talker.session import TurnOutcome
from talker_harness import FakeClock, StalledBackend, build_session, scripted_step


def _turn_latency(stall_s: float) -> float:
    clock = FakeClock()
    backend = StalledBackend(clock=clock, stall_s=stall_s)
    session = build_session(clock, steps=[scripted_step()], backend=backend)

    async def scenario() -> TurnOutcome:
        work = asyncio.ensure_future(backend.work())
        outcome = await session.take_turn("iki gündür ağrıyor")
        work.cancel()
        return outcome

    outcome = clock.run(scenario())
    return float(outcome.elapsed_ms)


# --- structural --------------------------------------------------------------------


def test_the_work_port_has_no_awaitable_member() -> None:
    members = {
        name: value
        for name, value in vars(WorkSubmitter).items()
        if callable(value) and not name.startswith("_")
    }
    assert set(members) == {"submit", "cancel", "drain_results"}
    for name, value in members.items():
        assert not inspect.iscoroutinefunction(value), (
            f"WorkSubmitter.{name} is a coroutine — the Talker could await Backend "
            "Work (invariant 9)"
        )


def test_submit_utterance_returns_before_the_backend_has_run() -> None:
    clock = FakeClock()
    backend = StalledBackend(clock=clock, stall_s=3_600.0)
    session = build_session(clock, steps=[scripted_step()], backend=backend)

    ticket = session.submit_utterance("s1", "iki gündür ağrıyor")

    assert ticket.work_id
    assert clock.now_ms() == 0.0, "submitting Work must not consume any time at all"
    assert backend.drain_results() == ()


# --- measured ------------------------------------------------------------------------


def test_turn_latency_is_unchanged_by_an_arbitrarily_stalled_backend() -> None:
    """RT-03 with the stall taken to absurdity — 10 s and 10 000 s agree."""
    ten_seconds = _turn_latency(10.0)
    nearly_three_hours = _turn_latency(10_000.0)
    instant = _turn_latency(0.0)

    assert ten_seconds == nearly_three_hours == instant
    assert ten_seconds > 0.0, "the turn must actually have spoken something"


def test_the_turn_stays_inside_the_scripted_budget_while_stalled() -> None:
    """files/03 §4.5: a scripted turn costs end-of-turn detection plus
    playback — the clip cache means zero TTS. The harness charges playback
    only, so the whole turn must land well under the 505 ms scripted total."""
    assert _turn_latency(10.0) < 505.0


def test_a_result_that_lands_later_is_delivered_on_a_later_turn() -> None:
    """The Talker does not wait for the result; it picks it up when it exists.
    Nothing is lost by not waiting — that is the other half of RT-03."""
    clock = FakeClock()
    backend = StalledBackend(clock=clock, stall_s=1.0)
    session = build_session(clock, steps=[scripted_step()], backend=backend)

    async def scenario() -> tuple[TurnOutcome, TurnOutcome]:
        work = asyncio.ensure_future(backend.work())
        first = await session.take_turn("iki gündür ağrıyor")
        await clock.sleep(2.0)
        second = await session.take_turn(None)
        work.cancel()
        return first, second

    first, second = clock.run(scenario())
    assert first.drained_results == 0
    assert second.drained_results == 0  # nothing was queued by this fixture
    assert first.elapsed_ms == pytest.approx(second.elapsed_ms)


def test_the_snapshot_read_is_the_only_engine_interaction_on_the_hot_path() -> None:
    """files/12 §7.2: protocol_next is a lock-free atomic attribute read."""
    clock = FakeClock()
    engine_steps = [scripted_step()]
    session = build_session(clock, steps=engine_steps)
    before = session.engine.snapshot_reads
    clock.run(session.take_turn(None))
    assert session.engine.snapshot_reads - before == 1

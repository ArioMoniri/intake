"""INT-100 — chaos: kill a speech lane mid-turn; the patient hears or reads within 2 s.

Acceptance (docs/backlog/issues.yaml INT-100, verbatim):
  "breaker per vendor; failover order from probes registry; chaos kill proves <=2s"

INT-024 proved the bound against a mock adapter and a degradation *decision*.
This file proves it against the thing a patient meets: a real
:class:`~intake_voice_runtime.talker.session.TalkerSession` turn, the real
:class:`~intake_voice_runtime.adapters.speech.HttpSpeechSynthesizer`, and the
real ``observability/registry.yaml``. Only the far side of the wire is a
double — :class:`ChaosEndpoint`, served through ``httpx.MockTransport``, so no
socket is opened and no model is dialled (CLAUDE.md: never call live APIs in
tests). Time is the harness's virtual clock; nothing sleeps.

What is killed, and how, is the chaos catalogue a self-hosted TTS process
actually has:

- **killed** — the process is gone; the connect is refused.
- **dies in flight** — the process accepted this turn's call and died inside
  it, 200 ms in. This is the "mid-turn" kill.
- **hung** — the process accepted the call and never answers; only the wire
  timeout ends it, and the ladder decides that timeout from the budget left.

The two latencies the healthy endpoints charge are files/03 §4.9.1's own
figures, not tuned ones: row 11's measured 0.14 s TTFT for the primary and
row 12's 0.52 s architectural floor for the fallback.

The 2 s is measured from the start of the turn to the moment the patient's
device is handed the first frame (audio) or the sentence (screen), server
side — the same place INT-091/INT-093 measure their budgets.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import _chaos_voice_suite  # noqa: F401  (puts tests/voice on sys.path first)
import httpx
import pytest
import yaml
from intake_voice_runtime.adapters.pins import COMPONENT_OF, ModelStackRow
from intake_voice_runtime.adapters.speech import HttpSpeechSynthesizer
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.resilience import (
    TYPED_FALLBACK_DEADLINE_MS,
    TYPED_LANE,
    AttemptOutcome,
    BreakerBoard,
    BreakerPolicy,
    BreakerState,
    CloudFailoverRefused,
    FailoverSynthesizer,
    LaneBindingMismatch,
    failover_order,
)
from intake_voice_runtime.talker.session import TalkerSession, TurnOutcome
from intake_voice_runtime.typed.switch import LaneSwitchReason
from prometheus_client import REGISTRY
from talker_harness import FakeClock, StalledBackend, build_session, scripted_step

#: files/03 §4.9.1 row 11 — "TTFT 0.14 s (RTX 4090, third-party)".
PRIMARY_ANSWER_S = 0.14
#: files/03 §4.9.1 row 12 — "0.52 s TTFT is a hard architectural floor".
FALLBACK_ANSWER_S = 0.52
#: How far into this turn's call the primary dies in the mid-turn kill.
DIES_AFTER_S = 0.2
#: Row 12 speaks in its own single voice; the lane is bound to it, never guessed.
FALLBACK_VOICE = "yedek-ses"

QUESTIONS = (
    scripted_step("s1", "Nereniz ağrıyor?"),
    scripted_step("s2", "Ağrı ne zaman başladı?"),
    scripted_step("s3", "Ateşiniz var mı?"),
)


def _sample(name: str, **labels: str) -> float:
    value = REGISTRY.get_sample_value(name, labels)
    return 0.0 if value is None else value


# --- the far side of the wire ------------------------------------------------------------


@dataclass
class ChaosEndpoint:
    """One self-hosted TTS process as its HTTP client sees it.

    Every failure mode honours the timeout the client put on the request, the
    way a socket does: a hung process costs exactly the read timeout, never a
    second more. That is the contract ``HttpSpeechSynthesizer`` relies on, and
    it is the one the ladder's budget arithmetic is built on.
    """

    clock: FakeClock
    component: str
    answer_s: float
    port: int
    mode: str = "healthy"
    timeouts_seen: list[float] = field(default_factory=list)
    served: int = 0

    def kill(self) -> None:
        self.mode = "killed"

    def handle(self, request: httpx.Request) -> httpx.Response:
        timeout_s = float(request.extensions["timeout"]["read"])
        self.timeouts_seen.append(timeout_s)
        if self.mode == "killed":
            raise httpx.ConnectError("connection refused", request=request)
        if self.mode == "hung":
            self.clock.advance(timeout_s)
            raise httpx.ReadTimeout("no answer", request=request)
        if self.mode == "dies_in_flight":
            self.clock.advance(min(DIES_AFTER_S, timeout_s))
            raise httpx.RemoteProtocolError("peer closed the connection", request=request)
        if self.answer_s > timeout_s:
            self.clock.advance(timeout_s)
            raise httpx.ReadTimeout("slower than the budget", request=request)
        self.clock.advance(self.answer_s)
        self.served += 1
        voice_id = json.loads(request.content)["voice_id"]
        return httpx.Response(200, content=f"{self.component}|{voice_id}".encode())

    def lane(self) -> HttpSpeechSynthesizer:
        return HttpSpeechSynthesizer(
            endpoint=f"http://127.0.0.1:{self.port}",
            transport=httpx.MockTransport(self.handle),
        )


# --- the near side: where the patient's device is handed something -----------------------


@dataclass
class StampedSink:
    """The media egress, recording when each utterance was handed on."""

    clock: FakeClock
    plays: list[tuple[str, float, bytes]] = field(default_factory=list)

    async def play(self, frames: bytes, *, label: str = "") -> None:
        self.plays.append((label, self.clock.now_ms(), frames))
        await self.clock.sleep(len(frames) / 1000.0)

    async def cancel(self) -> None:
        return None


@dataclass
class StampedScreen:
    """The data channel, recording when each sentence was drawn."""

    clock: FakeClock
    rendered: list[tuple[str, str, float]] = field(default_factory=list)

    async def render(self, text_tr: str, *, label: str = "") -> None:
        self.rendered.append((label, text_tr, self.clock.now_ms()))


@dataclass
class Chaos:
    clock: FakeClock
    primary: ChaosEndpoint
    fallback: ChaosEndpoint
    board: BreakerBoard
    synth: FailoverSynthesizer
    backend: StalledBackend
    sink: StampedSink
    screen: StampedScreen
    session: TalkerSession


def chaos_stack(
    *,
    clock: FakeClock | None = None,
    board: BreakerBoard | None = None,
    stall_s: float = 10.0,
) -> Chaos:
    """A composed ``residency_tr`` session whose speech lanes come from the registry."""
    clock = clock or FakeClock()
    entry = COMPONENT_OF[ModelStackRow.TTS_DYNAMIC]
    assert entry is not None
    order = failover_order(entry, profile=VoiceProfile.RESIDENCY_TR)
    primary_name, fallback_name = order.components
    primary = ChaosEndpoint(clock, primary_name, PRIMARY_ANSWER_S, port=8805)
    fallback = ChaosEndpoint(clock, fallback_name, FALLBACK_ANSWER_S, port=8803)
    board = board or BreakerBoard(clock=clock)
    synth = FailoverSynthesizer(
        order,
        {primary_name: primary.lane(), fallback_name: fallback.lane()},
        board=board,
        clock=clock,
        voice_ids={fallback_name: FALLBACK_VOICE},
    )
    backend = StalledBackend(clock=clock, stall_s=stall_s)
    sink = StampedSink(clock)
    screen = StampedScreen(clock)
    session = build_session(
        clock,
        steps=list(QUESTIONS),
        backend=backend,
        synthesizer=synth,
        sink=sink,
        screen=screen,
    )
    return Chaos(clock, primary, fallback, board, synth, backend, sink, screen, session)


@dataclass(frozen=True)
class Turn:
    outcome: TurnOutcome
    started_ms: float


def drive(
    stack: Chaos, script: Sequence[tuple[str | None, Callable[[], None] | None]]
) -> list[Turn]:
    """Run turns back to back on one virtual clock, with the Backend stalled
    underneath all of them. ``before`` throws the chaos switch for that turn."""

    async def scenario() -> list[Turn]:
        work = asyncio.ensure_future(stack.backend.work())
        turns: list[Turn] = []
        for transcript, before in script:
            if before is not None:
                before()
            started = stack.clock.now_ms()
            turns.append(Turn(await stack.session.take_turn(transcript), started))
        work.cancel()
        return turns

    result: list[Turn] = stack.clock.run(scenario())
    return result


def _dies_in_flight(endpoint: ChaosEndpoint) -> Callable[[], None]:
    def throw() -> None:
        endpoint.mode = "dies_in_flight"

    return throw


def _all(*switches: Callable[[], None]) -> Callable[[], None]:
    def throw() -> None:
        for switch in switches:
            switch()

    return throw


def _hang(endpoint: ChaosEndpoint) -> Callable[[], None]:
    def throw() -> None:
        endpoint.mode = "hung"

    return throw


# =====================================================================================
# The order the chaos walks is the registry's
# =====================================================================================


def test_the_failover_order_is_read_from_the_probes_registry() -> None:
    stack = chaos_stack()
    assert stack.synth.order.components == ("voxcpm2-tts", "freya-tts")
    assert stack.synth.current_component == "voxcpm2-tts"


# =====================================================================================
# Kill the primary mid-turn → the next lane answers within 2 s
# =====================================================================================


def test_the_primary_dying_mid_turn_hands_the_turn_to_the_next_lane_within_two_seconds() -> None:
    stack = chaos_stack()
    failovers_before = _sample(
        "vendor_failovers_total", from_component="voxcpm2-tts", to_component="freya-tts"
    )

    healthy, killed = drive(
        stack, [(None, None), ("iki gündür ağrıyor", _dies_in_flight(stack.primary))]
    )

    # baseline: the primary spoke the first question
    assert stack.sink.plays[0][0] == "s1"
    assert stack.sink.plays[0][2].startswith(b"voxcpm2-tts|")
    assert healthy.outcome.spoken_text == QUESTIONS[0].text_tr

    # the kill: the primary accepted turn 2's call and died inside it
    label, handed_on_ms, frames = stack.sink.plays[1]
    assert label == "s2"
    assert frames == f"freya-tts|{FALLBACK_VOICE}".encode()
    visible_ms = handed_on_ms - killed.started_ms
    assert visible_ms == pytest.approx((DIES_AFTER_S + FALLBACK_ANSWER_S) * 1000.0)
    assert visible_ms <= TYPED_FALLBACK_DEADLINE_MS
    assert killed.outcome.spoken_text == QUESTIONS[1].text_tr

    assert [a.outcome for a in stack.synth.last_attempts] == [
        AttemptOutcome.FAILED,
        AttemptOutcome.SERVED,
    ]
    assert stack.session.config.profile is VoiceProfile.RESIDENCY_TR
    assert (
        _sample("vendor_failovers_total", from_component="voxcpm2-tts", to_component="freya-tts")
        == failovers_before + 1
    )


def test_a_hung_primary_cannot_spend_the_fallbacks_time() -> None:
    """The budget split is what keeps this patient on voice: the hung primary
    is abandoned at its half, and the fallback answers inside the rest."""
    stack = chaos_stack()

    _, hung = drive(stack, [(None, None), ("iki gündür ağrıyor", _hang(stack.primary))])

    _, handed_on_ms, frames = stack.sink.plays[1]
    assert frames.startswith(b"freya-tts|")
    assert stack.primary.timeouts_seen[-1] == pytest.approx(TYPED_FALLBACK_DEADLINE_MS / 2000.0)
    visible_ms = handed_on_ms - hung.started_ms
    assert visible_ms == pytest.approx(TYPED_FALLBACK_DEADLINE_MS / 2 + FALLBACK_ANSWER_S * 1000.0)
    assert visible_ms <= TYPED_FALLBACK_DEADLINE_MS
    assert stack.session.config.profile is VoiceProfile.RESIDENCY_TR


def test_after_the_kill_the_session_stays_on_the_fallback_voice() -> None:
    """files/03 §4.9.4 row 11 — "then to row 12 for the rest of the session"."""
    stack = chaos_stack()

    def revive() -> None:
        stack.primary.mode = "healthy"

    drive(
        stack,
        [
            (None, None),
            ("iki gündür ağrıyor", _dies_in_flight(stack.primary)),
            ("dün başladı", revive),
        ],
    )
    assert [frames.split(b"|")[0] for _, _, frames in stack.sink.plays] == [
        b"voxcpm2-tts",
        b"freya-tts",
        b"freya-tts",
    ]


# =====================================================================================
# Kill every lane → the question is on the screen within 2 s
# =====================================================================================


def test_every_lane_killed_puts_the_question_on_the_screen_within_two_seconds() -> None:
    stack = chaos_stack()

    _, degraded = drive(
        stack,
        [(None, None), ("iki gündür ağrıyor", _all(stack.primary.kill, stack.fallback.kill))],
    )

    assert len(stack.sink.plays) == 1, "nothing after the kill reached the audio path"
    label, text, drawn_ms = stack.screen.rendered[0]
    assert (label, text) == ("s2", QUESTIONS[1].text_tr)  # verbatim (invariant 10)
    assert drawn_ms - degraded.started_ms <= TYPED_FALLBACK_DEADLINE_MS
    assert degraded.outcome.spoken_text == QUESTIONS[1].text_tr

    session = stack.session
    assert session.config.profile is VoiceProfile.TYPED
    assert session.modality_switch is not None
    assert session.modality_switch.reason is LaneSwitchReason.SPEECH_LANES_EXHAUSTED
    assert session.modality_degraded is True


def test_hung_lanes_still_reach_the_screen_within_two_seconds() -> None:
    """The worst case: both processes accept the call and never answer."""
    stack = chaos_stack()
    typed_before = _sample(
        "vendor_failovers_total", from_component="freya-tts", to_component=TYPED_LANE
    )

    _, degraded = drive(
        stack,
        [(None, None), ("iki gündür ağrıyor", _all(_hang(stack.primary), _hang(stack.fallback)))],
    )

    _, _, drawn_ms = stack.screen.rendered[0]
    assert drawn_ms - degraded.started_ms <= TYPED_FALLBACK_DEADLINE_MS
    # each process was held for exactly its share of the budget, on the wire
    assert stack.primary.timeouts_seen[-1] == pytest.approx(1.0)
    assert stack.fallback.timeouts_seen[-1] == pytest.approx(1.0)
    assert (
        _sample("vendor_failovers_total", from_component="freya-tts", to_component=TYPED_LANE)
        == typed_before + 1
    )


def test_the_session_finishes_typed_after_the_fallback() -> None:
    stack = chaos_stack()
    drive(
        stack,
        [
            (None, None),
            ("iki gündür ağrıyor", _all(stack.primary.kill, stack.fallback.kill)),
            ("dün başladı", None),
        ],
    )
    assert [text for _, text, _ in stack.screen.rendered] == [
        QUESTIONS[1].text_tr,
        QUESTIONS[2].text_tr,
    ]


# =====================================================================================
# Invariant 9 — the chaos turn never waits on Backend Work
# =====================================================================================


def _chaos_turn_latencies(stall_s: float) -> tuple[float, float]:
    stack = chaos_stack(stall_s=stall_s)
    _, killed = drive(stack, [(None, None), ("iki gündür ağrıyor", _dies_in_flight(stack.primary))])
    audible_ms = stack.sink.plays[1][1] - killed.started_ms
    assert stack.backend.submitted, "the transcript was handed to Layer B"
    return audible_ms, float(killed.outcome.elapsed_ms)


def test_the_failover_turn_is_unchanged_by_an_arbitrarily_stalled_backend() -> None:
    """RT-03 under chaos: 10 s and 10 000 s of Backend stall cost the turn nothing."""
    ten_seconds = _chaos_turn_latencies(10.0)
    nearly_three_hours = _chaos_turn_latencies(10_000.0)
    instant = _chaos_turn_latencies(0.0)
    assert ten_seconds == nearly_three_hours == instant
    assert ten_seconds[0] <= TYPED_FALLBACK_DEADLINE_MS


# =====================================================================================
# Breaker per vendor — the next session pays nothing for a known-dead primary
# =====================================================================================


def test_the_kill_opens_the_primary_breaker_and_the_next_session_starts_on_the_fallback() -> None:
    clock = FakeClock()
    board = BreakerBoard(clock=clock, policy=BreakerPolicy(failure_threshold=1))
    opened_before = _sample(
        "vendor_breaker_transitions_total",
        component="voxcpm2-tts",
        from_state=BreakerState.CLOSED.value,
        to_state=BreakerState.OPEN.value,
    )

    first = chaos_stack(clock=clock, board=board)
    first.primary.kill()
    drive(first, [(None, None)])
    assert board.breaker("voxcpm2-tts").state is BreakerState.OPEN
    assert (
        _sample(
            "vendor_breaker_transitions_total",
            component="voxcpm2-tts",
            from_state=BreakerState.CLOSED.value,
            to_state=BreakerState.OPEN.value,
        )
        == opened_before + 1
    )
    assert _sample("vendor_breaker_state", component="voxcpm2-tts", state="open") == 1.0

    second = chaos_stack(clock=clock, board=board)
    second.primary.kill()
    (turn,) = drive(second, [(None, None)])
    assert second.primary.timeouts_seen == [], "an open breaker dials nothing"
    assert [a.outcome for a in second.synth.last_attempts] == [
        AttemptOutcome.SKIPPED_OPEN,
        AttemptOutcome.SERVED,
    ]
    assert second.sink.plays[0][1] - turn.started_ms == pytest.approx(FALLBACK_ANSWER_S * 1000.0)


# =====================================================================================
# Invariant 19 — residency_tr never fails over to a cloud vendor
# =====================================================================================


def test_a_registry_that_names_a_cloud_fallback_cannot_build_a_residency_order(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "registry.yaml"
    registry.write_text(
        yaml.safe_dump(
            {
                "components": [
                    {
                        "component": "voxcpm2-tts",
                        "self_hostable": True,
                        "self_hosted_now": True,
                        "phi_path": True,
                        "fallback": "component:hosted-tts",
                    },
                    {
                        "component": "hosted-tts",
                        "self_hostable": False,
                        "self_hosted_now": True,
                        "phi_path": False,
                        "fallback": "none",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(CloudFailoverRefused, match="hosted-tts"):
        failover_order("voxcpm2-tts", profile=VoiceProfile.RESIDENCY_TR, registry_path=registry)


def test_a_cloud_lane_handed_to_the_ladder_is_refused_at_composition() -> None:
    clock = FakeClock()
    order = failover_order("voxcpm2-tts", profile=VoiceProfile.RESIDENCY_TR)
    endpoint = ChaosEndpoint(clock, "hosted-tts", PRIMARY_ANSWER_S, port=9999)
    lanes = {component: endpoint.lane() for component in (*order.components, "hosted-tts")}
    with pytest.raises(LaneBindingMismatch, match="hosted-tts"):
        FailoverSynthesizer(order, lanes, board=BreakerBoard(clock=clock), clock=clock)

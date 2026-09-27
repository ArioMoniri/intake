"""INT-100 — per-vendor circuit breakers, registry-ordered failover, typed fallback.

Acceptance (docs/backlog/issues.yaml INT-100, verbatim):
  "breaker per vendor; failover order from probes registry; chaos kill proves <=2s"

This file pins the mechanism unit by unit; ``tests/chaos/test_vendor_failover.py``
drives the same pieces through a real Talker turn. Every clock here is the
virtual one from ``talker_harness`` — no test sleeps, and a lane's latency is
charged with :meth:`FakeClock.advance` exactly where a synchronous adapter
would spend it.

- **The breaker** is the textbook three-state machine with an injectable clock:
  closed → open after ``failure_threshold`` consecutive failures, open → half
  open once ``open_ms`` has passed, one trial at a time while half open.
- **The order** is read from ``observability/registry.yaml`` by following each
  row's ``fallback: component:<x>`` link. On the PHI path every lane in it must
  be self-hostable and cleared for PHI (CLAUDE.md invariant 19) — a cloud row
  is refused, never skipped, and a dev order puts self-hosted lanes first.
- **The ladder** spends one 2 s budget across the lanes in that order, gives
  each attempt its share as the wire timeout, sticks to a lane once it has
  failed over (files/03 §4.9.4 row 11: *"then to row 12 for the rest of the
  session"*), and raises :class:`SpeechLanesExhausted` when nothing is left.
- **The session** turns that exhaustion into the typed profile *inside the same
  turn*, so the question the patient could not hear is on their screen.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import pytest
import yaml
from intake_platform.slo import load_metrics_catalog
from intake_probes.registry import load_registry
from intake_voice_runtime.adapters.pins import COMPONENT_OF, REGISTRY_PATH, ModelStackRow
from intake_voice_runtime.adapters.speech import (
    HttpSpeechSynthesizer,
    RecordedSpeechSynthesizer,
    SpeechUnavailable,
)
from intake_voice_runtime.ports import SpeechSynthesizer
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.resilience import (
    TYPED_FALLBACK_DEADLINE_MS,
    TYPED_LANE,
    AttemptOutcome,
    BoundedSynthesizer,
    BreakerBoard,
    BreakerPolicy,
    BreakerState,
    CircuitBreaker,
    CloudFailoverRefused,
    FailoverChainBroken,
    FailoverOrder,
    FailoverRefused,
    FailoverSynthesizer,
    LaneBindingMismatch,
    LaneOffPhiPath,
    LaneRow,
    NoServingLane,
    ProfileHasNoSpeechLanes,
    SelfHostedNotFirst,
    SpeechLanesExhausted,
    build_failover_order,
    failover_order,
    load_lane_rows,
)
from intake_voice_runtime.talker.speech import NumeralOnTtsPathError
from intake_voice_runtime.typed.egress import TypedEgress
from intake_voice_runtime.typed.switch import KillSwitchNotArmed, LaneSwitchReason
from prometheus_client import REGISTRY
from pydantic import ValidationError
from talker_harness import FakeClock, RecordingScreen, build_session, scripted_step

REPO = Path(__file__).resolve().parents[2]
CATALOG = REPO / "observability" / "metrics_catalog.yaml"

#: The three families this issue emits — every one must be catalogued (inv. 13).
RESILIENCE_FAMILIES = (
    "vendor_breaker_state",
    "vendor_breaker_transitions_total",
    "vendor_failovers_total",
)


def _sample(name: str, **labels: str) -> float:
    value = REGISTRY.get_sample_value(name, labels)
    return 0.0 if value is None else value


def _state(component: str, state: BreakerState) -> float:
    return _sample("vendor_breaker_state", component=component, state=state.value)


def _transitions(component: str, before: BreakerState, after: BreakerState) -> float:
    return _sample(
        "vendor_breaker_transitions_total",
        component=component,
        from_state=before.value,
        to_state=after.value,
    )


def _failovers(source: str, target: str) -> float:
    return _sample("vendor_failovers_total", from_component=source, to_component=target)


# --- doubles ---------------------------------------------------------------------------


@dataclass
class ScriptedLane:
    """A :class:`BoundedSynthesizer` double that serves, refuses or hangs.

    ``hang`` holds the socket until the wire timeout it was handed, which is
    what an HTTP client does against a process that accepted the connection
    and never answered. ``refuse`` is a dead process: the connect fails.
    """

    clock: FakeClock
    mode: str = "serve"
    latency_s: float = 0.0
    calls: list[tuple[str, str, float | None]] = field(default_factory=list)

    def synthesize(self, text_tr: str, voice_id: str, *, timeout_s: float | None = None) -> bytes:
        self.calls.append((text_tr, voice_id, timeout_s))
        if self.mode == "hang":
            assert timeout_s is not None, "a hung lane is only bounded by its wire timeout"
            self.clock.advance(timeout_s)
            raise SpeechUnavailable("the TTS endpoint did not answer (ReadTimeout)")
        self.clock.advance(self.latency_s)
        if self.mode == "refuse":
            raise SpeechUnavailable("the TTS endpoint did not answer (ConnectError)")
        return f"{voice_id}:{text_tr}".encode()[:32]


def row(
    component: str,
    *,
    fallback: str = "none",
    self_hostable: bool = True,
    self_hosted_now: bool = True,
    phi_path: bool = True,
) -> LaneRow:
    return LaneRow(
        component=component,
        self_hostable=self_hostable,
        self_hosted_now=self_hosted_now,
        phi_path=phi_path,
        fallback=fallback,
    )


def rows(*items: LaneRow) -> dict[str, LaneRow]:
    return {item.component: item for item in items}


def two_lane_order(primary: str, secondary: str) -> FailoverOrder:
    return build_failover_order(
        primary,
        rows(row(primary, fallback=f"component:{secondary}"), row(secondary)),
        phi_path=True,
    )


def ladder(
    clock: FakeClock,
    lanes: Mapping[str, BoundedSynthesizer],
    *,
    order: FailoverOrder,
    board: BreakerBoard | None = None,
    voice_ids: Mapping[str, str] | None = None,
) -> FailoverSynthesizer:
    return FailoverSynthesizer(
        order,
        lanes,
        board=board or BreakerBoard(clock=clock),
        clock=clock,
        voice_ids=voice_ids,
    )


# =====================================================================================
# 1 · The breaker — closed / open / half-open, on an injected clock
# =====================================================================================


class TestCircuitBreaker:
    def test_a_new_breaker_is_closed_and_publishes_that_state(self) -> None:
        breaker = CircuitBreaker("unit-fresh", policy=BreakerPolicy(), clock=FakeClock())
        assert breaker.component == "unit-fresh"
        assert breaker.state is BreakerState.CLOSED
        assert breaker.allow() is True
        assert _state("unit-fresh", BreakerState.CLOSED) == 1.0
        assert _state("unit-fresh", BreakerState.OPEN) == 0.0
        assert _state("unit-fresh", BreakerState.HALF_OPEN) == 0.0

    def test_failures_below_the_threshold_keep_it_closed_and_a_success_resets_them(
        self,
    ) -> None:
        breaker = CircuitBreaker(
            "unit-reset", policy=BreakerPolicy(failure_threshold=3), clock=FakeClock()
        )
        breaker.record_failure()
        breaker.record_failure()
        breaker.record_success()
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state is BreakerState.CLOSED

    def test_consecutive_failures_at_the_threshold_open_it(self) -> None:
        before = _transitions("unit-open", BreakerState.CLOSED, BreakerState.OPEN)
        breaker = CircuitBreaker(
            "unit-open", policy=BreakerPolicy(failure_threshold=2), clock=FakeClock()
        )
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state is BreakerState.OPEN
        assert breaker.allow() is False
        assert _transitions("unit-open", BreakerState.CLOSED, BreakerState.OPEN) == before + 1
        assert _state("unit-open", BreakerState.OPEN) == 1.0
        assert _state("unit-open", BreakerState.CLOSED) == 0.0

    def test_it_stays_open_until_the_cooldown_has_passed_on_the_injected_clock(self) -> None:
        clock = FakeClock()
        breaker = CircuitBreaker(
            "unit-cool", policy=BreakerPolicy(failure_threshold=1, open_ms=5_000.0), clock=clock
        )
        breaker.record_failure()
        clock.advance(4.999)
        assert breaker.admits() is False
        assert breaker.allow() is False
        clock.advance(0.001)
        assert breaker.admits() is True
        # admits() is a peek: it never moves the state machine
        assert breaker.state is BreakerState.OPEN

    def test_after_the_cooldown_exactly_one_trial_is_let_through(self) -> None:
        clock = FakeClock()
        before = _transitions("unit-trial", BreakerState.OPEN, BreakerState.HALF_OPEN)
        breaker = CircuitBreaker(
            "unit-trial", policy=BreakerPolicy(failure_threshold=1, open_ms=1_000.0), clock=clock
        )
        breaker.record_failure()
        clock.advance(1.0)
        assert breaker.allow() is True
        assert breaker.state is BreakerState.HALF_OPEN
        assert breaker.admits() is False
        assert breaker.allow() is False, "a second caller must not ride the same trial"
        assert _transitions("unit-trial", BreakerState.OPEN, BreakerState.HALF_OPEN) == before + 1
        assert _state("unit-trial", BreakerState.HALF_OPEN) == 1.0

    def test_a_successful_trial_closes_it(self) -> None:
        clock = FakeClock()
        breaker = CircuitBreaker(
            "unit-close", policy=BreakerPolicy(failure_threshold=1, open_ms=1_000.0), clock=clock
        )
        breaker.record_failure()
        clock.advance(1.0)
        assert breaker.allow()
        breaker.record_success()
        assert breaker.state is BreakerState.CLOSED
        assert breaker.allow() is True

    def test_close_after_asks_for_that_many_clean_trials(self) -> None:
        clock = FakeClock()
        breaker = CircuitBreaker(
            "unit-two-trials",
            policy=BreakerPolicy(failure_threshold=1, open_ms=1_000.0, close_after=2),
            clock=clock,
        )
        breaker.record_failure()
        clock.advance(1.0)
        assert breaker.allow()
        breaker.record_success()
        assert breaker.state is BreakerState.HALF_OPEN
        assert breaker.allow()
        breaker.record_success()
        assert breaker.state is BreakerState.CLOSED

    def test_a_failed_trial_reopens_it_and_restarts_the_cooldown_from_now(self) -> None:
        clock = FakeClock()
        breaker = CircuitBreaker(
            "unit-reopen", policy=BreakerPolicy(failure_threshold=1, open_ms=1_000.0), clock=clock
        )
        breaker.record_failure()
        clock.advance(1.0)
        assert breaker.allow()
        before = _transitions("unit-reopen", BreakerState.HALF_OPEN, BreakerState.OPEN)
        breaker.record_failure()
        assert breaker.state is BreakerState.OPEN
        assert _transitions("unit-reopen", BreakerState.HALF_OPEN, BreakerState.OPEN) == before + 1
        clock.advance(0.5)
        assert breaker.allow() is False
        clock.advance(0.5)
        assert breaker.allow() is True

    def test_outcomes_reported_while_open_do_not_move_it(self) -> None:
        """Only an admitted call may report; a stray report changes nothing."""
        breaker = CircuitBreaker(
            "unit-stray", policy=BreakerPolicy(failure_threshold=1), clock=FakeClock()
        )
        breaker.record_failure()
        breaker.record_success()
        breaker.record_failure()
        assert breaker.state is BreakerState.OPEN

    @pytest.mark.parametrize(
        "overrides",
        [{"failure_threshold": 0}, {"open_ms": 0.0}, {"close_after": 0}],
    )
    def test_the_policy_refuses_a_threshold_that_could_never_trip_or_recover(
        self, overrides: dict[str, float]
    ) -> None:
        with pytest.raises(ValidationError):
            BreakerPolicy.model_validate(overrides)


class TestBreakerBoard:
    def test_there_is_one_breaker_per_vendor_and_it_is_shared(self) -> None:
        board = BreakerBoard(clock=FakeClock())
        first = board.breaker("board-a")
        assert board.breaker("board-a") is first
        assert board.breaker("board-b") is not first

    def test_a_per_vendor_override_replaces_the_default_policy(self) -> None:
        board = BreakerBoard(
            clock=FakeClock(),
            policy=BreakerPolicy(failure_threshold=5),
            overrides={"board-strict": BreakerPolicy(failure_threshold=1)},
        )
        assert board.breaker("board-strict").policy.failure_threshold == 1
        assert board.breaker("board-lenient").policy.failure_threshold == 5

    def test_states_is_a_snapshot_of_every_breaker(self) -> None:
        board = BreakerBoard(clock=FakeClock(), policy=BreakerPolicy(failure_threshold=1))
        board.breaker("board-x").record_failure()
        board.breaker("board-y")
        assert board.states() == {"board-x": BreakerState.OPEN, "board-y": BreakerState.CLOSED}


# =====================================================================================
# 2 · The order — the registry's fallback chain, self-hosted only on the PHI path
# =====================================================================================


class TestFailoverOrderFromTheRegistry:
    def test_the_tts_order_is_the_registry_chain_from_the_dynamic_path_row(self) -> None:
        """files/03 §4.9.1 row 11 → row 12, read from the registry — not restated."""
        entry = COMPONENT_OF[ModelStackRow.TTS_DYNAMIC]
        assert entry is not None
        order = failover_order(entry, profile=VoiceProfile.RESIDENCY_TR)
        assert order.components == ("voxcpm2-tts", "freya-tts")
        registry = load_registry(REGISTRY_PATH)
        assert registry.get(entry).fallback_target == order.components[1]
        assert registry.get(order.components[1]).fallback == "none"

    def test_every_lane_in_the_residency_order_is_self_hosted_and_on_the_phi_path(self) -> None:
        order = failover_order("voxcpm2-tts", profile=VoiceProfile.RESIDENCY_TR)
        registry = load_registry(REGISTRY_PATH)
        assert order.phi_path is True
        for component in order.components:
            entry = registry.get(component)
            assert entry.self_hostable and entry.phi_path and entry.self_hosted_now

    def test_the_lane_reader_agrees_with_the_authoritative_validator_row_for_row(self) -> None:
        """One file, one meaning: this module reads it permissively and must
        never disagree with ``intake_probes.registry`` about a lane."""
        lane_rows = load_lane_rows()
        for entry in load_registry(REGISTRY_PATH):
            lane = lane_rows[entry.component]
            assert (
                lane.self_hostable,
                lane.self_hosted_now,
                lane.phi_path,
                lane.fallback,
            ) == (entry.self_hostable, entry.self_hosted_now, entry.phi_path, entry.fallback)

    def test_a_registry_file_on_disk_is_read_the_same_way(self, tmp_path: Path) -> None:
        path = tmp_path / "registry.yaml"
        path.write_text(
            yaml.safe_dump(
                {
                    "components": [
                        {
                            "component": "disk-a",
                            "self_hostable": True,
                            "self_hosted_now": True,
                            "phi_path": True,
                            "fallback": "component:disk-b",
                            "host": "loopback",
                        },
                        {
                            "component": "disk-b",
                            "self_hostable": True,
                            "self_hosted_now": True,
                            "phi_path": True,
                            "fallback": "none",
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )
        order = failover_order("disk-a", profile=VoiceProfile.RESIDENCY_TR, registry_path=path)
        assert order.components == ("disk-a", "disk-b")

    def test_the_typed_profile_has_no_speech_lanes_to_order(self) -> None:
        with pytest.raises(ProfileHasNoSpeechLanes):
            failover_order("voxcpm2-tts", profile=VoiceProfile.TYPED)


class TestFailoverOrderInvariant19:
    """CLAUDE.md invariant 19 — ``residency_tr`` never fails over to a cloud vendor."""

    def test_a_cloud_row_behind_a_phi_lane_is_refused_not_skipped(self) -> None:
        registry = rows(
            row("tts-self", fallback="component:tts-cloud"),
            row("tts-cloud", self_hostable=False, phi_path=False),
        )
        with pytest.raises(CloudFailoverRefused, match="tts-cloud"):
            build_failover_order("tts-self", registry, phi_path=True)

    def test_a_self_hostable_row_not_cleared_for_phi_is_refused_too(self) -> None:
        registry = rows(
            row("tts-self", fallback="component:tts-dev"),
            row("tts-dev", phi_path=False),
        )
        with pytest.raises(LaneOffPhiPath, match="tts-dev"):
            build_failover_order("tts-self", registry, phi_path=True)

    def test_every_refusal_is_one_family(self) -> None:
        for refusal in (
            CloudFailoverRefused,
            LaneOffPhiPath,
            SelfHostedNotFirst,
            FailoverChainBroken,
            NoServingLane,
            ProfileHasNoSpeechLanes,
        ):
            assert issubclass(refusal, FailoverRefused)

    def test_off_the_phi_path_self_hosted_lanes_still_come_first(self) -> None:
        """A dev/synthetic bridge may reach a non-self-hostable lane — last."""
        registry = rows(
            row("dev-cloud", self_hostable=False, phi_path=False, fallback="component:dev-self"),
            row("dev-self", phi_path=False),
        )
        order = build_failover_order("dev-cloud", registry, phi_path=False)
        assert order.components == ("dev-self", "dev-cloud")

    def test_an_order_object_holds_the_invariant_however_it_was_built(self) -> None:
        with pytest.raises(CloudFailoverRefused):
            FailoverOrder(
                entry="x",
                lanes=(row("x"), row("y", self_hostable=False, phi_path=False)),
                phi_path=True,
            )
        with pytest.raises(SelfHostedNotFirst):
            FailoverOrder(
                entry="x",
                lanes=(row("y", self_hostable=False, phi_path=False), row("x")),
                phi_path=False,
            )

    def test_the_real_registry_carries_no_cloud_row_on_any_speech_chain(self) -> None:
        """Every TTS row in §4.9.1 that the registry carries orders cleanly."""
        for stack_row in (ModelStackRow.TTS_CLIP, ModelStackRow.TTS_DYNAMIC):
            entry = COMPONENT_OF[stack_row]
            assert entry is not None
            failover_order(entry, profile=VoiceProfile.RESIDENCY_TR)


class TestFailoverChainShape:
    def test_a_planned_row_is_skipped_and_the_chain_continues(self) -> None:
        registry = rows(
            row("chain-a", fallback="component:chain-b"),
            row("chain-b", self_hosted_now=False, fallback="component:chain-c"),
            row("chain-c"),
        )
        order = build_failover_order("chain-a", registry, phi_path=True)
        assert order.components == ("chain-a", "chain-c")

    def test_an_in_process_fallback_ends_the_chain(self) -> None:
        registry = rows(row("chain-in", fallback="in-process:intake_platform.redaction"))
        order = build_failover_order("chain-in", registry, phi_path=True)
        assert order.components == ("chain-in",)

    def test_a_cycle_is_refused(self) -> None:
        registry = rows(
            row("loop-a", fallback="component:loop-b"),
            row("loop-b", fallback="component:loop-a"),
        )
        with pytest.raises(FailoverChainBroken, match="loop-a"):
            build_failover_order("loop-a", registry, phi_path=True)

    def test_an_unknown_entry_or_link_is_refused(self) -> None:
        with pytest.raises(FailoverChainBroken, match="nowhere"):
            build_failover_order("nowhere", rows(row("somewhere")), phi_path=True)
        with pytest.raises(FailoverChainBroken, match="missing"):
            build_failover_order(
                "link-a", rows(row("link-a", fallback="component:missing")), phi_path=True
            )

    def test_a_chain_with_nothing_running_is_refused(self) -> None:
        registry = rows(row("idle-a", self_hosted_now=False))
        with pytest.raises(NoServingLane):
            build_failover_order("idle-a", registry, phi_path=True)


# =====================================================================================
# 3 · The ladder — one 2 s budget, spent in registry order, sticky per session
# =====================================================================================


class TestFailoverSynthesizerBinding:
    def test_it_is_a_speech_synthesizer_the_router_already_speaks_to(self) -> None:
        clock = FakeClock()
        order = two_lane_order("bind-a", "bind-b")
        synth = ladder(
            clock, {"bind-a": ScriptedLane(clock), "bind-b": ScriptedLane(clock)}, order=order
        )
        assert isinstance(synth, SpeechSynthesizer)
        assert synth.order is order
        assert synth.current_component == "bind-a"

    def test_a_lane_the_order_names_must_be_bound(self) -> None:
        clock = FakeClock()
        with pytest.raises(LaneBindingMismatch, match="bind-b"):
            ladder(clock, {"bind-a": ScriptedLane(clock)}, order=two_lane_order("bind-a", "bind-b"))

    def test_a_lane_the_registry_does_not_order_is_refused(self) -> None:
        """How a cloud adapter handed in by a deployment is kept off the path."""
        clock = FakeClock()
        lanes = {
            "bind-a": ScriptedLane(clock),
            "bind-b": ScriptedLane(clock),
            "some-cloud-tts": ScriptedLane(clock),
        }
        with pytest.raises(LaneBindingMismatch, match="some-cloud-tts"):
            ladder(clock, lanes, order=two_lane_order("bind-a", "bind-b"))

    def test_a_voice_for_an_unordered_lane_is_refused(self) -> None:
        clock = FakeClock()
        lanes = {"bind-a": ScriptedLane(clock), "bind-b": ScriptedLane(clock)}
        with pytest.raises(LaneBindingMismatch, match="bind-z"):
            ladder(
                clock, lanes, order=two_lane_order("bind-a", "bind-b"), voice_ids={"bind-z": "v"}
            )

    def test_a_deadline_that_leaves_no_time_is_refused(self) -> None:
        clock = FakeClock()
        with pytest.raises(ValueError, match="deadline"):
            FailoverSynthesizer(
                two_lane_order("bind-a", "bind-b"),
                {"bind-a": ScriptedLane(clock), "bind-b": ScriptedLane(clock)},
                board=BreakerBoard(clock=clock),
                clock=clock,
                deadline_ms=0.0,
            )

    def test_the_deadline_is_the_acceptance_bound(self) -> None:
        """INT-024's bound, restated in ms: one number, two spellings, pinned."""
        from intake_platform.chaos import FALLBACK_DEADLINE_S

        assert TYPED_FALLBACK_DEADLINE_MS == FALLBACK_DEADLINE_S * 1000.0
        assert TYPED_LANE == VoiceProfile.TYPED.value


class TestFailoverSynthesizerLadder:
    def test_a_healthy_primary_serves_and_nothing_fails_over(self) -> None:
        clock = FakeClock()
        primary, secondary = ScriptedLane(clock, latency_s=0.14), ScriptedLane(clock)
        synth = ladder(
            clock, {"lad-a": primary, "lad-b": secondary}, order=two_lane_order("lad-a", "lad-b")
        )
        frames = synth.synthesize("Nereniz ağrıyor?", "ses-1")
        assert frames == b"ses-1:Nereniz a\xc4\x9fr\xc4\xb1yor?"[:32]
        assert secondary.calls == []
        assert synth.failovers == ()
        assert [a.outcome for a in synth.last_attempts] == [AttemptOutcome.SERVED]
        assert synth.last_attempts[0].elapsed_ms == pytest.approx(140.0)

    def test_a_dead_primary_hands_the_call_to_the_next_lane_and_the_session_stays_there(
        self,
    ) -> None:
        clock = FakeClock()
        primary = ScriptedLane(clock, mode="refuse")
        secondary = ScriptedLane(clock)
        before = _failovers("lad-dead", "lad-next")
        synth = ladder(
            clock,
            {"lad-dead": primary, "lad-next": secondary},
            order=two_lane_order("lad-dead", "lad-next"),
        )

        synth.synthesize("Ateşiniz var mı?", "ses-1")
        assert synth.current_component == "lad-next"
        assert [a.outcome for a in synth.last_attempts] == [
            AttemptOutcome.FAILED,
            AttemptOutcome.SERVED,
        ]
        assert _failovers("lad-dead", "lad-next") == before + 1
        assert synth.failovers[0].from_component == "lad-dead"
        assert synth.failovers[0].to_component == "lad-next"

        # files/03 §4.9.4 row 11: "then to row 12 for the rest of the session" —
        # the primary coming back does not pull this session back to it.
        primary.mode = "serve"
        synth.synthesize("Ne zamandan beri?", "ses-1")
        assert len(primary.calls) == 1
        assert len(secondary.calls) == 2

    def test_an_open_breaker_is_skipped_at_session_start_without_a_call(self) -> None:
        clock = FakeClock()
        board = BreakerBoard(clock=clock, policy=BreakerPolicy(failure_threshold=1))
        board.breaker("lad-open").record_failure()
        primary, secondary = ScriptedLane(clock), ScriptedLane(clock)
        synth = ladder(
            clock,
            {"lad-open": primary, "lad-fresh": secondary},
            order=two_lane_order("lad-open", "lad-fresh"),
            board=board,
        )
        synth.synthesize("Ateşiniz var mı?", "ses-1")
        assert primary.calls == []
        assert [a.outcome for a in synth.last_attempts] == [
            AttemptOutcome.SKIPPED_OPEN,
            AttemptOutcome.SERVED,
        ]
        # the open lane does not get a share of the budget it will not use
        assert secondary.calls[0][2] == pytest.approx(TYPED_FALLBACK_DEADLINE_MS / 1000.0)

    def test_the_budget_is_shared_and_a_fast_failure_leaves_the_rest_to_the_next_lane(
        self,
    ) -> None:
        clock = FakeClock()
        primary = ScriptedLane(clock, mode="refuse", latency_s=0.05)
        secondary = ScriptedLane(clock)
        synth = ladder(
            clock,
            {"lad-fast": primary, "lad-rest": secondary},
            order=two_lane_order("lad-fast", "lad-rest"),
        )
        synth.synthesize("Ateşiniz var mı?", "ses-1")
        assert primary.calls[0][2] == pytest.approx(1.0)  # 2 000 ms over two lanes
        assert secondary.calls[0][2] == pytest.approx(1.95)  # everything that is left

    def test_hung_lanes_exhaust_the_ladder_exactly_at_the_deadline(self) -> None:
        clock = FakeClock()
        synth = ladder(
            clock,
            {
                "lad-h1": ScriptedLane(clock, mode="hang"),
                "lad-h2": ScriptedLane(clock, mode="hang"),
            },
            order=two_lane_order("lad-h1", "lad-h2"),
        )
        with pytest.raises(SpeechLanesExhausted) as raised:
            synth.synthesize("Ateşiniz var mı?", "ses-1")
        assert clock.now_ms() == pytest.approx(TYPED_FALLBACK_DEADLINE_MS)
        assert [a.outcome for a in raised.value.attempts] == [
            AttemptOutcome.FAILED,
            AttemptOutcome.FAILED,
        ]

    def test_every_lane_down_raises_exhaustion_and_moves_the_session_to_the_text_lane(
        self,
    ) -> None:
        clock = FakeClock()
        before = _failovers("lad-x2", TYPED_LANE)
        synth = ladder(
            clock,
            {
                "lad-x1": ScriptedLane(clock, mode="refuse"),
                "lad-x2": ScriptedLane(clock, mode="refuse"),
            },
            order=two_lane_order("lad-x1", "lad-x2"),
        )
        with pytest.raises(SpeechLanesExhausted) as raised:
            synth.synthesize("Ateşiniz var mı?", "ses-1")
        assert synth.current_component is None
        assert _failovers("lad-x2", TYPED_LANE) == before + 1
        # invariant 6: component ids and outcomes, never the sentence
        assert "Ateşiniz" not in str(raised.value)
        assert "lad-x1" in str(raised.value)
        # latched: nothing is dialled again
        with pytest.raises(SpeechLanesExhausted) as again:
            synth.synthesize("Ateşiniz var mı?", "ses-1")
        assert again.value.attempts == ()

    def test_a_spent_budget_stops_the_ladder_without_blaming_the_untried_lane(self) -> None:
        clock = FakeClock()
        board = BreakerBoard(clock=clock, policy=BreakerPolicy(failure_threshold=1))
        slow = ScriptedLane(clock, mode="refuse", latency_s=2.5)  # ignores its timeout
        untried = ScriptedLane(clock)
        before = _failovers("lad-late", TYPED_LANE)
        synth = ladder(
            clock,
            {"lad-slow": slow, "lad-late": untried},
            order=two_lane_order("lad-slow", "lad-late"),
            board=board,
        )
        with pytest.raises(SpeechLanesExhausted) as raised:
            synth.synthesize("Ateşiniz var mı?", "ses-1")
        assert [a.outcome for a in raised.value.attempts] == [
            AttemptOutcome.FAILED,
            AttemptOutcome.OUT_OF_TIME,
        ]
        assert untried.calls == []
        assert board.breaker("lad-late").state is BreakerState.CLOSED
        assert _failovers("lad-late", TYPED_LANE) == before + 1

    def test_a_numeral_is_refused_before_any_lane_or_breaker_is_touched(self) -> None:
        """Invariant 22 is the caller's defect, not a vendor outage."""
        clock = FakeClock()
        board = BreakerBoard(clock=clock, policy=BreakerPolicy(failure_threshold=1))
        primary = ScriptedLane(clock)
        synth = ladder(
            clock,
            {"lad-num": primary, "lad-num2": ScriptedLane(clock)},
            order=two_lane_order("lad-num", "lad-num2"),
            board=board,
        )
        with pytest.raises(NumeralOnTtsPathError):
            synth.synthesize("2 gündür", "ses-1")
        assert primary.calls == []
        assert board.breaker("lad-num").state is BreakerState.CLOSED
        assert synth.current_component == "lad-num"

    def test_a_fallback_lane_speaks_in_its_own_voice(self) -> None:
        """Row 12 has one voice of its own; it is bound, never guessed."""
        clock = FakeClock()
        secondary = ScriptedLane(clock)
        synth = ladder(
            clock,
            {"lad-v1": ScriptedLane(clock, mode="refuse"), "lad-v2": secondary},
            order=two_lane_order("lad-v1", "lad-v2"),
            voice_ids={"lad-v2": "yedek-ses"},
        )
        synth.synthesize("Ateşiniz var mı?", "ses-1")
        assert secondary.calls[0][1] == "yedek-ses"

    def test_a_failing_lane_trips_its_breaker_for_every_later_session(self) -> None:
        clock = FakeClock()
        board = BreakerBoard(clock=clock, policy=BreakerPolicy(failure_threshold=2))
        dead = ScriptedLane(clock, mode="refuse")
        order = two_lane_order("lad-trip", "lad-safe")
        for _ in range(2):
            ladder(
                clock, {"lad-trip": dead, "lad-safe": ScriptedLane(clock)}, order=order, board=board
            ).synthesize("Ateşiniz var mı?", "ses-1")
        assert board.breaker("lad-trip").state is BreakerState.OPEN
        third = ladder(
            clock, {"lad-trip": dead, "lad-safe": ScriptedLane(clock)}, order=order, board=board
        )
        third.synthesize("Ateşiniz var mı?", "ses-1")
        assert len(dead.calls) == 2
        assert third.last_attempts[0].outcome is AttemptOutcome.SKIPPED_OPEN


# =====================================================================================
# 4 · The adapters honour the per-attempt timeout on the wire
# =====================================================================================


class TestAdaptersTakeTheAttemptTimeout:
    def test_the_http_lane_puts_the_share_on_the_request(self) -> None:
        seen: list[dict[str, float]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(dict(request.extensions["timeout"]))
            return httpx.Response(200, content=b"sentetik")

        synth = HttpSpeechSynthesizer(
            endpoint="http://127.0.0.1:8805", transport=httpx.MockTransport(handler)
        )
        assert isinstance(synth, BoundedSynthesizer)
        synth.synthesize("Ateşiniz var mı?", "ses-1", timeout_s=0.75)
        synth.synthesize("Ateşiniz var mı?", "ses-1")
        assert seen[0]["read"] == 0.75
        assert seen[0]["connect"] == 0.75
        assert seen[1]["read"] == synth.timeout_s

    def test_the_recorded_lane_accepts_it_and_reads_a_local_file(self, tmp_path: Path) -> None:
        synth = RecordedSpeechSynthesizer(root=tmp_path)
        assert isinstance(synth, BoundedSynthesizer)
        with pytest.raises(LookupError):
            synth.synthesize("Ateşiniz var mı?", "ses-1", timeout_s=0.5)


# =====================================================================================
# 5 · The session — exhaustion becomes the typed profile inside the same turn
# =====================================================================================


def _dead_ladder(clock: FakeClock, prefix: str) -> FailoverSynthesizer:
    return ladder(
        clock,
        {
            f"{prefix}-1": ScriptedLane(clock, mode="refuse"),
            f"{prefix}-2": ScriptedLane(clock, mode="refuse"),
        },
        order=two_lane_order(f"{prefix}-1", f"{prefix}-2"),
    )


class TestSessionTypedFallback:
    def test_the_question_nobody_could_speak_is_on_the_screen_in_the_same_turn(self) -> None:
        clock = FakeClock()
        screen = RecordingScreen()
        step = scripted_step()
        session = build_session(
            clock, steps=[step], synthesizer=_dead_ladder(clock, "sess-a"), screen=screen
        )
        outcome = clock.run(session.take_turn(None))

        assert screen.texts == [step.text_tr]
        assert outcome.spoken_text == step.text_tr
        assert outcome.from_clip is False
        assert session.config.profile is VoiceProfile.TYPED
        assert isinstance(session.router, TypedEgress)
        assert session.modality_switch is not None
        assert session.modality_switch.reason is LaneSwitchReason.SPEECH_LANES_EXHAUSTED
        assert session.modality_degraded is True
        assert session.synthesizer is None and session.sink is None

    def test_the_turn_after_the_fallback_is_an_ordinary_typed_turn(self) -> None:
        clock = FakeClock()
        screen = RecordingScreen()
        steps = [scripted_step(), scripted_step("s2", "Başka bir şikâyetiniz var mı?")]
        session = build_session(
            clock, steps=steps, synthesizer=_dead_ladder(clock, "sess-b"), screen=screen
        )
        clock.run(session.take_turn(None))
        clock.run(session.take_turn("iki gündür"))
        assert screen.texts == [steps[0].text_tr, steps[1].text_tr]

    def test_a_session_with_no_screen_refuses_loudly_rather_than_going_silent(self) -> None:
        clock = FakeClock()
        session = build_session(
            clock, steps=[scripted_step()], synthesizer=_dead_ladder(clock, "sess-c")
        )
        session.screen = None
        with pytest.raises(KillSwitchNotArmed) as raised:
            clock.run(session.take_turn(None))
        assert isinstance(raised.value.__context__, SpeechLanesExhausted)
        assert session.config.profile is VoiceProfile.RESIDENCY_TR

    def test_a_healthy_ladder_leaves_the_session_on_voice(self) -> None:
        clock = FakeClock()
        screen = RecordingScreen()
        synth = ladder(
            clock,
            {"sess-ok-1": ScriptedLane(clock), "sess-ok-2": ScriptedLane(clock)},
            order=two_lane_order("sess-ok-1", "sess-ok-2"),
        )
        session = build_session(clock, steps=[scripted_step()], synthesizer=synth, screen=screen)
        clock.run(session.take_turn(None))
        assert session.config.profile is VoiceProfile.RESIDENCY_TR
        assert screen.texts == []


# =====================================================================================
# 6 · Inv. 13 — every family this issue emits is catalogued and live
# =====================================================================================


def test_every_resilience_family_is_catalogued_live_and_owned_by_the_runtime() -> None:
    catalog = load_metrics_catalog(CATALOG)
    by_name = {metric.name: metric for metric in catalog.metrics}
    for family in RESILIENCE_FAMILIES:
        assert catalog.covers(family), f"{family} missing from metrics_catalog.yaml"
        assert by_name[family].status == "live"
        assert by_name[family].owner == "voice-runtime"
    assert by_name["vendor_breaker_state"].labels == ["component", "state"]
    assert by_name["vendor_breaker_transitions_total"].labels == [
        "component",
        "from_state",
        "to_state",
    ]
    assert by_name["vendor_failovers_total"].labels == ["from_component", "to_component"]

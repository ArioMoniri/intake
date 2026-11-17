"""INT-182 — the runtime reads the tenant's voice control at every session start.

files/02 §375: *"the admin console can switch a tenant to typed mode (kill
switch) without a deploy"*. That sentence is only true if the runtime asks
at session start rather than at process start, so the router below is held to
four properties, each with its near-miss:

- **One read per session start, no cache.** A control changed between two
  starts is honoured by the second, on the same router instance.
- **The kill switch dominates.** Engaged, every new session is ``typed``
  whatever the default profile or the canary weight says; and a live voice
  session is moved to the keyboard by the poll, inside INT-100's 2 s budget.
- **Fail closed.** An unreadable control starts the session ``typed`` — the
  safer state — and is counted; it never falls back to a guessed default.
- **Only profiles that exist.** The platform's profile set *is* the runtime's
  (CLAUDE.md invariant 19); a builder that returns a different profile from
  the one routed is refused.

The canary is a deterministic hash of the session id, so a replay routes the
same session the same way.
"""

from __future__ import annotations

import asyncio

import fakeredis
import pytest
from intake_platform.voice_control import (
    RedisVoiceControlStore,
    TenantVoiceControl,
    VoiceControlProfile,
    VoiceControlUnavailable,
)
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.resilience import TYPED_FALLBACK_DEADLINE_MS
from intake_voice_runtime.session_router import (
    KILL_SWITCH_POLL_MS,
    FlipOutcome,
    RouteMismatch,
    RouteReason,
    VoiceSessionRouter,
    canary_bucket,
    decide_route,
)
from intake_voice_runtime.typed import LaneSwitchReason
from prometheus_client import REGISTRY
from session_harness import builders, turn
from talker_harness import FakeClock, RecordingScreen

TENANT = "00000000-0000-4000-8000-0000000000a1"
OTHER = "00000000-0000-4000-8000-0000000000b2"


def _sample(name: str, labels: dict[str, str]) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


def _store() -> RedisVoiceControlStore:
    return RedisVoiceControlStore(fakeredis.FakeRedis())


def _set(store: RedisVoiceControlStore, tenant: str, **fields: object) -> TenantVoiceControl:
    current = store.read(tenant)
    updated = current.model_copy(update={**fields, "revision": current.revision + 1})
    validated = TenantVoiceControl.model_validate(updated.model_dump())
    return store.write(validated, expected_revision=current.revision)


class UnreadableControls:
    """A control store that cannot answer — the fail-closed direction."""

    def __init__(self) -> None:
        self.reads = 0

    def read(self, tenant_id: str) -> TenantVoiceControl:
        self.reads += 1
        raise VoiceControlUnavailable("voice_control_unreachable")


class CountingControls:
    def __init__(self, inner: RedisVoiceControlStore) -> None:
        self.inner = inner
        self.reads = 0

    def read(self, tenant_id: str) -> TenantVoiceControl:
        self.reads += 1
        return self.inner.read(tenant_id)


# =====================================================================================
# 1 · The pure decision
# =====================================================================================


class TestDecideRoute:
    def control(self, **fields: object) -> TenantVoiceControl:
        return TenantVoiceControl.model_validate({"tenant_id": TENANT, "revision": 1, **fields})

    def test_an_unconfigured_tenant_is_typed(self) -> None:
        """Voice is opt-in per tenant: a tenant nobody has configured, or a
        store that lost its keys, starts on the safer transport."""
        control = TenantVoiceControl.unconfigured(TENANT)
        assert control.default_profile is VoiceControlProfile.TYPED
        assert control.canary_weight == 0
        assert decide_route(control, bucket=0) == (VoiceProfile.TYPED, RouteReason.DEFAULT)

    def test_the_default_profile_routes_when_nothing_else_applies(self) -> None:
        control = self.control(default_profile="residency_tr")
        assert decide_route(control, bucket=42) == (VoiceProfile.RESIDENCY_TR, RouteReason.DEFAULT)

    def test_the_kill_switch_dominates_the_default_and_the_canary(self) -> None:
        control = self.control(
            default_profile="residency_tr",
            canary_profile="typed",
            canary_weight=100,
            kill_switch=True,
        )
        for bucket in (0, 50, 99):
            assert decide_route(control, bucket=bucket) == (
                VoiceProfile.TYPED,
                RouteReason.KILL_SWITCH,
            )

    def test_the_canary_takes_buckets_below_its_weight_and_no_others(self) -> None:
        control = self.control(canary_profile="residency_tr", canary_weight=25)
        assert decide_route(control, bucket=24) == (VoiceProfile.RESIDENCY_TR, RouteReason.CANARY)
        # the near miss: the first bucket at the weight is the default's
        assert decide_route(control, bucket=25) == (VoiceProfile.TYPED, RouteReason.DEFAULT)

    def test_weight_zero_routes_nothing_to_the_canary(self) -> None:
        control = self.control(default_profile="residency_tr")
        assert all(decide_route(control, bucket=b)[1] is RouteReason.DEFAULT for b in range(100))

    def test_weight_one_hundred_routes_everything_to_the_canary(self) -> None:
        control = self.control(canary_profile="residency_tr", canary_weight=100)
        assert all(decide_route(control, bucket=b)[1] is RouteReason.CANARY for b in range(100))

    def test_a_bucket_outside_the_hundred_is_refused(self) -> None:
        with pytest.raises(ValueError, match="bucket"):
            decide_route(self.control(), bucket=100)


class TestCanaryBucket:
    def test_it_is_deterministic_so_a_replay_routes_the_same_way(self) -> None:
        assert canary_bucket(TENANT, "s-1") == canary_bucket(TENANT, "s-1")

    def test_it_stays_inside_zero_to_ninety_nine_and_reaches_every_bucket(self) -> None:
        seen = {canary_bucket(TENANT, f"session-{index}") for index in range(4000)}
        assert seen == set(range(100))

    def test_a_weight_takes_roughly_its_share(self) -> None:
        control = TenantVoiceControl.model_validate(
            {
                "tenant_id": TENANT,
                "revision": 1,
                "canary_profile": "residency_tr",
                "canary_weight": 25,
            }
        )
        routed = [
            decide_route(control, bucket=canary_bucket(TENANT, f"s-{index}"))[1]
            for index in range(4000)
        ]
        share = routed.count(RouteReason.CANARY) / len(routed)
        assert 0.21 < share < 0.29

    def test_the_tenant_is_part_of_the_hash(self) -> None:
        differing = sum(
            canary_bucket(TENANT, f"s-{i}") != canary_bucket(OTHER, f"s-{i}") for i in range(200)
        )
        assert differing > 150


# =====================================================================================
# 2 · Session start reads the control, every time
# =====================================================================================


class TestSessionStart:
    def test_the_decided_profile_is_the_profile_that_was_built(self) -> None:
        store = _store()
        _set(store, TENANT, default_profile="residency_tr")
        clock = FakeClock()
        router = VoiceSessionRouter(controls=store, clock=clock)
        routed = router.start(
            tenant_id=TENANT,
            session_id="s-voice",
            builders=builders(tenant_id=TENANT, session_id="s-voice", clock=clock),
        )
        assert routed.decision.profile is VoiceProfile.RESIDENCY_TR
        assert routed.stack.profile is VoiceProfile.RESIDENCY_TR
        assert routed.decision.control_revision == 1

    def test_a_change_between_two_starts_is_honoured_without_a_new_router(self) -> None:
        store = _store()
        _set(store, TENANT, default_profile="residency_tr")
        clock = FakeClock()
        counting = CountingControls(store)
        router = VoiceSessionRouter(controls=counting, clock=clock)
        first = router.start(
            tenant_id=TENANT,
            session_id="s-1",
            builders=builders(tenant_id=TENANT, session_id="s-1", clock=clock),
        )
        _set(store, TENANT, kill_switch=True)
        second = router.start(
            tenant_id=TENANT,
            session_id="s-2",
            builders=builders(tenant_id=TENANT, session_id="s-2", clock=clock),
        )
        assert first.stack.profile is VoiceProfile.RESIDENCY_TR
        assert second.stack.profile is VoiceProfile.TYPED
        assert second.decision.reason is RouteReason.KILL_SWITCH
        assert counting.reads == 2  # one read per start; nothing cached

    def test_an_unreadable_control_starts_typed_and_is_counted(self) -> None:
        clock = FakeClock()
        before = _sample(
            "voice_control_read_failures_total",
            {"phase": "start", "code": "voice_control_unreachable"},
        )
        routes_before = _sample(
            "voice_session_routes_total",
            {"tenant": TENANT, "profile": "typed", "reason": "control_unreadable"},
        )
        router = VoiceSessionRouter(controls=UnreadableControls(), clock=clock)
        routed = router.start(
            tenant_id=TENANT,
            session_id="s-dark",
            builders=builders(tenant_id=TENANT, session_id="s-dark", clock=clock),
        )
        assert routed.stack.profile is VoiceProfile.TYPED
        assert routed.decision.reason is RouteReason.CONTROL_UNREADABLE
        assert routed.decision.control_revision is None
        assert (
            _sample(
                "voice_control_read_failures_total",
                {"phase": "start", "code": "voice_control_unreachable"},
            )
            == before + 1
        )
        assert (
            _sample(
                "voice_session_routes_total",
                {"tenant": TENANT, "profile": "typed", "reason": "control_unreadable"},
            )
            == routes_before + 1
        )

    def test_a_malformed_stored_record_is_unreadable_not_a_default(self) -> None:
        client = fakeredis.FakeRedis()
        store = RedisVoiceControlStore(client)
        client.set(store.key(TENANT), b'{"tenant_id": "' + TENANT.encode() + b'", "revision": -4}')
        with pytest.raises(VoiceControlUnavailable) as raised:
            store.read(TENANT)
        assert raised.value.code == "voice_control_malformed"

    def test_both_builders_are_required_because_typed_must_always_be_reachable(self) -> None:
        clock = FakeClock()
        router = VoiceSessionRouter(controls=_store(), clock=clock)
        only_voice = builders(tenant_id=TENANT, session_id="s-x", clock=clock)
        del only_voice[VoiceProfile.TYPED]
        with pytest.raises(ValueError, match="typed"):
            router.start(tenant_id=TENANT, session_id="s-x", builders=only_voice)

    def test_a_builder_that_returns_another_profile_is_refused(self) -> None:
        clock = FakeClock()
        router = VoiceSessionRouter(controls=_store(), clock=clock)
        crossed = builders(tenant_id=TENANT, session_id="s-y", clock=clock)
        crossed[VoiceProfile.TYPED] = crossed[VoiceProfile.RESIDENCY_TR]
        with pytest.raises(RouteMismatch):
            router.start(tenant_id=TENANT, session_id="s-y", builders=crossed)

    def test_a_session_id_cannot_be_started_twice(self) -> None:
        clock = FakeClock()
        router = VoiceSessionRouter(controls=_store(), clock=clock)
        router.start(
            tenant_id=TENANT,
            session_id="s-z",
            builders=builders(tenant_id=TENANT, session_id="s-z", clock=clock),
        )
        with pytest.raises(ValueError, match="already"):
            router.start(
                tenant_id=TENANT,
                session_id="s-z",
                builders=builders(tenant_id=TENANT, session_id="s-z", clock=clock),
            )

    def test_a_tenant_that_is_not_id_shaped_is_refused_before_any_read(self) -> None:
        unreadable = UnreadableControls()
        router = VoiceSessionRouter(controls=unreadable, clock=FakeClock())
        with pytest.raises(ValueError, match="id-shaped"):
            router.decide(tenant_id="Hastane A", session_id="s-1")
        assert unreadable.reads == 0

    def test_the_platform_profile_set_is_the_runtime_profile_set(self) -> None:
        """Invariant 19: two profiles, the same two on both sides of the store."""
        assert {p.value for p in VoiceControlProfile} == {p.value for p in VoiceProfile}


# =====================================================================================
# 3 · In-flight sessions: the poll
# =====================================================================================


def _engaged_router(
    *, voice_screen: bool = True
) -> tuple[RedisVoiceControlStore, VoiceSessionRouter, FakeClock, list[object]]:
    store = _store()
    _set(store, TENANT, default_profile="residency_tr")
    _set(store, OTHER, default_profile="residency_tr")
    clock = FakeClock()
    router = VoiceSessionRouter(controls=store, clock=clock)
    started = [
        router.start(
            tenant_id=tenant,
            session_id=sid,
            builders=builders(
                tenant_id=tenant, session_id=sid, clock=clock, voice_screen=voice_screen
            ),
        )
        for tenant, sid in ((TENANT, "live-1"), (TENANT, "live-2"), (OTHER, "live-3"))
    ]
    return store, router, clock, list(started)


class TestPoll:
    def test_nothing_moves_while_the_switch_is_off(self) -> None:
        _, router, _, _ = _engaged_router()
        assert router.poll() == ()

    def test_an_engaged_switch_moves_that_tenants_live_voice_sessions_only(self) -> None:
        store, router, _, started = _engaged_router()
        _set(store, TENANT, kill_switch=True)
        before = _sample("voice_kill_switch_flips_total", {"tenant": TENANT, "outcome": "switched"})
        flips = router.poll()
        assert {flip.session_id for flip in flips} == {"live-1", "live-2"}
        assert all(flip.outcome is FlipOutcome.SWITCHED for flip in flips)
        by_id = {routed.session_id: routed for routed in router.live()}
        for sid in ("live-1", "live-2"):
            session = by_id[sid].stack.session
            assert by_id[sid].stack.profile is VoiceProfile.TYPED
            assert session.modality_switch is not None
            assert session.modality_switch.reason is LaneSwitchReason.OPERATOR_KILL_SWITCH
            assert session.modality_degraded is True
        assert by_id["live-3"].stack.profile is VoiceProfile.RESIDENCY_TR
        assert (
            _sample("voice_kill_switch_flips_total", {"tenant": TENANT, "outcome": "switched"})
            == before + 2
        )
        # a second poll finds nothing left to move
        assert router.poll() == ()

    def test_a_session_with_no_screen_stays_in_voice_and_is_counted_once(self) -> None:
        store, router, _, _ = _engaged_router(voice_screen=False)
        _set(store, TENANT, kill_switch=True)
        before = _sample(
            "voice_kill_switch_flips_total", {"tenant": TENANT, "outcome": "not_armed"}
        )
        flips = router.poll()
        assert {flip.outcome for flip in flips} == {FlipOutcome.NOT_ARMED}
        assert router.poll() == ()  # counted once, not every second
        assert (
            _sample("voice_kill_switch_flips_total", {"tenant": TENANT, "outcome": "not_armed"})
            == before + 2
        )
        assert all(
            routed.stack.profile is VoiceProfile.RESIDENCY_TR
            for routed in router.live()
            if routed.tenant_id == TENANT
        )

    def test_an_unreadable_poll_moves_nothing_and_is_counted(self) -> None:
        store, router, _, _ = _engaged_router()
        _set(store, TENANT, kill_switch=True)
        router._controls = UnreadableControls()  # the store went dark after start
        before = _sample(
            "voice_control_read_failures_total",
            {"phase": "poll", "code": "voice_control_unreachable"},
        )
        assert router.poll() == ()
        assert (
            _sample(
                "voice_control_read_failures_total",
                {"phase": "poll", "code": "voice_control_unreachable"},
            )
            == before + 2  # one read per tenant with live voice sessions
        )

    def test_an_ended_session_is_not_moved(self) -> None:
        store, router, _, _ = _engaged_router()
        router.end("live-1")
        _set(store, TENANT, kill_switch=True)
        assert {flip.session_id for flip in router.poll()} == {"live-2"}

    def test_the_watch_loop_moves_a_live_session_inside_the_typed_budget(self) -> None:
        store, router, clock, _ = _engaged_router()
        engaged_at: list[float] = []

        async def main() -> None:
            watcher = asyncio.ensure_future(router.watch())
            await clock.sleep(0.25)
            _set(store, TENANT, kill_switch=True)
            engaged_at.append(clock.now_ms())
            await clock.sleep(TYPED_FALLBACK_DEADLINE_MS / 1000.0)
            watcher.cancel()

        clock.run(main())
        session = next(r for r in router.live() if r.session_id == "live-1").stack.session
        assert session.modality_switch is not None
        assert session.modality_switch.at_ms - engaged_at[0] <= TYPED_FALLBACK_DEADLINE_MS

    def test_a_live_session_keeps_its_turns_after_the_switch(self) -> None:
        """INT-096: the switch swaps the egress and nothing else — the next
        question arrives on the screen of the same session."""
        store = _store()
        _set(store, TENANT, default_profile="residency_tr")
        clock = FakeClock()
        screen = RecordingScreen()
        router = VoiceSessionRouter(controls=store, clock=clock)
        routed = router.start(
            tenant_id=TENANT,
            session_id="s-keep",
            builders=builders(tenant_id=TENANT, session_id="s-keep", clock=clock, screen=screen),
        )

        async def main() -> None:
            await turn(routed.stack, None)
            _set(store, TENANT, kill_switch=True)
            router.poll()
            await turn(routed.stack, "bir tane")

        clock.run(main())
        assert screen.texts == ["Sentetik ikinci soru."]


class TestPollInterval:
    def test_the_default_poll_sits_inside_the_typed_fallback_budget(self) -> None:
        assert 0 < KILL_SWITCH_POLL_MS < TYPED_FALLBACK_DEADLINE_MS

    @pytest.mark.parametrize("poll_ms", [0.0, -1.0, TYPED_FALLBACK_DEADLINE_MS, 5_000.0])
    def test_a_poll_that_could_miss_the_budget_is_refused(self, poll_ms: float) -> None:
        with pytest.raises(ValueError, match="poll"):
            VoiceSessionRouter(controls=_store(), clock=FakeClock(), poll_ms=poll_ms)

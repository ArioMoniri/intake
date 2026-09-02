"""INT-110 — the observer-lane framework, and CLAUDE.md invariant 11 clause by clause.

The invariant is the acceptance, so the file is organised by its clauses:

1. **Read-only, structurally.** A lane cannot write a slot or a triage level —
   not because a reviewer would catch it, but because there is no expression
   that says it. Three locks stack: the context a lane is handed has no engine
   and no submitter to write *through*; :class:`LaneObservation` has no field a
   slot value or a level could occupy and refuses one at construction; and its
   ``triage_update``/``slot_updates`` are read-only properties over
   ``ClassVar`` constants, so the assignment is a ``mypy`` error and an
   ``AttributeError`` — the shape INT-172's ``CandidateRedFlag`` already uses.
   A fourth, static, lock closes the import graph.
2. **Never on the speech critical path.** The ingress has no awaitable member
   (the ``WorkSubmitter`` proof of invariant 9, reused), and on the virtual
   clock one turn against lanes stalled 30 s costs exactly what it costs
   against no lanes at all. No test sleeps.
3. **Frames drop under load, speech never waits**, and the drop is counted on
   ``lane.dropped_frames``.
4. **Per-lane consent**, through the one evaluator's verdicts. A refused lane
   is *absent*: no ring, no task, no aggregate, not even a metric child.
5. **`acoustic` fails closed** on the INT-230 study registry, and closes again
   on a protocol amendment (TCKAY m.11).

Everything Turkish here is synthetic (files/04 §7). No clinical content is
authored: INT-043 is `awaiting-human` (HB-C1), and there is no Turkish vocal
biomarker model to wire (files/00 §2, HB-L1/HB-C11).
"""

from __future__ import annotations

import ast
import asyncio
import dataclasses
import inspect
import logging
from datetime import date, timedelta
from pathlib import Path

import pytest
from clinical_schemas.observers import InteractionState, Lane, ObserverState
from intake_platform.consent import UnknownPurposeError, resolve_scope
from intake_platform.research import (
    StudyApprovalLapsedError,
    StudyRecord,
    StudyRegistry,
    UnknownStudyError,
    load_default_registry,
)
from intake_voice_runtime.observers import (
    INTENDED_PURPOSE,
    LANE_CONSENT_SCOPE,
    LANE_SPECS,
    MAX_WINDOW_SECONDS,
    AcousticAdmission,
    AcousticAssertion,
    ApprovalDateMismatchError,
    IcfVersionUnrecordedError,
    LaneBudget,
    LaneConsentUndeclared,
    LaneContext,
    LaneObservation,
    LaneRuntime,
    LaneWindow,
    ObserverField,
    ObserverStore,
    ProtocolAmendedError,
    SealedDestinationRefused,
    StudyAssertionRefused,
    admit_acoustic,
)
from intake_voice_runtime.observers.runtime import LANE_DROPPED_FRAMES
from lane_harness import (
    SYNTHETIC_TURKISH,
    FakeClock,
    RecordingSealedStore,
    build_session,
    frame,
    granted,
    lane_double,
    refused,
    scripted_step,
)
from prometheus_client import REGISTRY
from pydantic import ValidationError

SESSION_ID = "11111111-2222-4333-8444-555555555555"

#: The session's starting interaction state is a property of the profile, not
#: something the lane framework may invent (files/03 §4.7.1 gives the record's
#: shape and no defaults).
NEUTRAL = InteractionState(
    pace="normal",
    modality="voice",
    break_offer=False,
    confirm_by_card=False,
    repeat_request=False,
    third_party_present=False,
)

OBSERVERS_SRC = (
    Path(__file__).resolve().parents[2]
    / "services"
    / "voice-runtime"
    / "src"
    / "intake_voice_runtime"
    / "observers"
)


def _observation(lane: Lane = Lane.LINGUISTIC, **overrides: object) -> LaneObservation:
    payload: dict[str, object] = {
        "lane": lane,
        "window_id": "w-1",
        "seq": 1,
        "markers": {"pause_ratio": 0.25},
        "confidence": 0.5,
        "sampling_rate_hz": 50.0,
        "dropped_frames_in_window": 0,
    }
    payload.update(overrides)
    return LaneObservation(**payload)  # type: ignore[arg-type]


def _runtime(
    clock: FakeClock,
    *,
    lanes: list[Lane],
    consent_scopes: tuple[str, ...],
    stall_s: float = 0.0,
    budget: LaneBudget | None = None,
    study: AcousticAdmission | None = None,
) -> LaneRuntime:
    return LaneRuntime.admit(
        session_id=SESSION_ID,
        implementations=[lane_double(lane, clock, stall_s=stall_s) for lane in lanes],
        consent=granted(*consent_scopes),
        interaction=NEUTRAL,
        study=study,
        budget=budget,
    )


# --- clause 1: read-only, structurally --------------------------------------------


class TestALaneCannotWriteASlotOrATriageLevel:
    def test_the_observation_type_has_no_field_a_slot_or_a_level_could_occupy(self) -> None:
        fields = set(LaneObservation.model_fields)
        assert fields == {
            "lane",
            "window_id",
            "seq",
            "markers",
            "confidence",
            "sampling_rate_hz",
            "dropped_frames_in_window",
        }
        for forbidden in ("level", "triage_update", "slot_updates", "slot_id", "value"):
            assert forbidden not in fields

    @pytest.mark.parametrize(
        "forbidden",
        [
            {"triage_update": "RED"},
            {"slot_updates": {"chest_pain": True}},
            {"level": "RED"},
            {"candidate_flags": ("rf.x",)},
        ],
    )
    def test_constructing_an_observation_that_names_a_slot_or_a_level_is_refused(
        self, forbidden: dict[str, object]
    ) -> None:
        with pytest.raises(ValidationError, match="extra"):
            _observation(**forbidden)

    def test_triage_update_and_slot_updates_are_read_only_constants(self) -> None:
        """INT-172's shape: the cap is a ``ClassVar`` behind a property, so the
        forbidden assignment raises instead of being silently clamped.

        Two locks, and both are load-bearing. The properties have **no
        setter**, which is what ``mypy --strict`` sees — the assignment does
        not compile. At runtime the frozen model refuses it one step earlier,
        so a caller that got past the type checker still cannot land the write.
        """
        observation = _observation()
        assert observation.triage_update is None
        assert observation.slot_updates == ()
        # ClassVars are not fields, so neither is a constructor argument
        assert "_TRIAGE_UPDATE" not in LaneObservation.model_fields
        assert "_SLOT_UPDATES" not in LaneObservation.model_fields
        assert LaneObservation.triage_update.fset is None
        assert LaneObservation.slot_updates.fset is None
        with pytest.raises(ValidationError, match="frozen"):
            observation.triage_update = "RED"  # type: ignore[misc]
        with pytest.raises(ValidationError, match="frozen"):
            observation.slot_updates = ("chest_pain",)  # type: ignore[misc]
        assert observation.triage_update is None
        assert observation.slot_updates == ()

    def test_a_marker_cannot_carry_a_string_so_it_cannot_carry_a_level_or_a_slot_value(
        self,
    ) -> None:
        """Markers are numeric. A slot value and a triage level are both
        strings, so neither has a carrier here even inside the open map."""
        with pytest.raises(ValidationError):
            _observation(markers={"triage": "RED"})
        with pytest.raises(ValidationError):
            _observation(markers={"chest_pain": "evet"})
        assert _observation(markers={"hopelessness": 1.0}).markers == {"hopelessness": 1.0}

    def test_the_context_a_lane_is_handed_carries_no_engine_and_no_submitter(self) -> None:
        names = {f.name for f in dataclasses.fields(LaneContext)}
        assert names == {"lane", "session_id", "window", "is_cancelled"}
        window_names = {f.name for f in dataclasses.fields(LaneWindow)}
        assert window_names == {
            "window_id",
            "frames",
            "sampling_rate_hz",
            "dropped_frames",
            "duration_s",
        }

    def test_no_observer_module_imports_the_engine_the_queue_or_a_triage_type(self) -> None:
        """The static half: there is no path, not merely no call."""
        forbidden_modules = (
            "intake_voice_runtime.clinical_agent",
            "intake_voice_runtime.talker",
            "clinical_schemas.triage",
            "protocols",
        )
        forbidden_names = {
            "IntakeEngine",
            "BackendAgent",
            "RulesTriageResult",
            "TriageLevel",
            "StateContext",
            "StateEffect",
        }
        offenders: list[str] = []
        sources = sorted(OBSERVERS_SRC.rglob("*.py"))
        assert sources, "the observers package must exist for this gate to mean anything"
        for path in sources:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                module = ""
                if isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    for alias in node.names:
                        if alias.name in forbidden_names:
                            offenders.append(f"{path.name}: {alias.name}")
                elif isinstance(node, ast.Import):
                    module = node.names[0].name
                else:
                    continue
                if module.startswith(forbidden_modules):
                    offenders.append(f"{path.name}: {module}")
        assert offenders == []

    def test_no_observer_module_can_open_an_audio_transport(self) -> None:
        """files/10 §9.1 invariant 13 (`lane_shared_stream_guard`), static half:
        a lane consumes the frames the session already decoded (files/03
        §4.7.2's one stream) and has no network capability to open a second."""
        forbidden = (
            "aiohttp",
            "httpx",
            "livekit",
            "requests",
            "socket",
            "ssl",
            "urllib",
            "websockets",
        )
        offenders: list[str] = []
        for path in sorted(OBSERVERS_SRC.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                elif isinstance(node, ast.Import):
                    module = node.names[0].name
                else:
                    continue
                if module.split(".")[0] in forbidden:
                    offenders.append(f"{path.name}: {module}")
        assert offenders == []

    def test_the_store_has_no_method_that_could_write_a_slot_or_a_triage_level(self) -> None:
        public = {
            name
            for name, value in vars(ObserverStore).items()
            if not name.startswith("_") and (callable(value) or isinstance(value, property))
        }
        assert public == {"state", "apply", "drop"}

    def test_the_store_refuses_an_observation_that_claims_another_lane(self) -> None:
        store = ObserverStore(session_id=SESSION_ID, interaction=NEUTRAL)
        with pytest.raises(ValueError, match="lane"):
            store.apply(LANE_SPECS[Lane.LINGUISTIC], _observation(lane=Lane.ENGAGEMENT))

    def test_what_a_lane_writes_is_an_observer_state_and_only_an_observer_state(self) -> None:
        store = ObserverStore(session_id=SESSION_ID, interaction=NEUTRAL)
        store.apply(LANE_SPECS[Lane.LINGUISTIC], _observation(markers={"pause_ratio": 0.25}))
        state = store.state
        assert isinstance(state, ObserverState)
        assert state.linguistic_markers == {"pause_ratio": 0.25}
        assert state.asr_quality == {} and state.engagement == {}
        assert state.interaction == NEUTRAL

    def test_an_affect_observation_writes_nothing_because_m1_output_dies_in_m1(self) -> None:
        """Invariant 22: nothing but the closed ``InteractionState`` crosses the
        M1 boundary, so there is no ``affect`` field on ``ObserverState`` and
        the store deliberately stores nothing."""
        assert LANE_SPECS[Lane.AFFECT].field is ObserverField.M1_INTERNAL
        assert "affect" not in ObserverState.model_fields
        store = ObserverStore(session_id=SESSION_ID, interaction=NEUTRAL)
        before = store.state
        store.apply(LANE_SPECS[Lane.AFFECT], _observation(lane=Lane.AFFECT))
        assert store.state == before

    def test_an_acoustic_observation_can_never_reach_observer_state(self) -> None:
        """files/03 §4.7.4: sealed research store only — never the note, never
        an ``Observation``, and never here."""
        assert LANE_SPECS[Lane.ACOUSTIC].field is ObserverField.SEALED_RESEARCH
        store = ObserverStore(session_id=SESSION_ID, interaction=NEUTRAL)
        with pytest.raises(SealedDestinationRefused):
            store.apply(LANE_SPECS[Lane.ACOUSTIC], _observation(lane=Lane.ACOUSTIC))

    def test_every_lane_declares_a_reviewed_intended_purpose(self) -> None:
        """Invariant 29 (`lane_intended_purpose_manifest`), one statement per
        module exactly as MDCG 2019-11 §3.4 requires (files/03 §4.7.1)."""
        for lane, spec in LANE_SPECS.items():
            purpose = INTENDED_PURPOSE[spec.module]
            assert purpose.strip(), f"{lane}: empty intended purpose"
        acoustic_purpose = INTENDED_PURPOSE[LANE_SPECS[Lane.ACOUSTIC].module]
        assert "registered clinical investigation" in acoustic_purpose


# --- clause 2: never on the speech critical path -----------------------------------


class TestLanesNeverSitOnTheSpeechCriticalPath:
    def test_the_lane_ingress_has_no_awaitable_member(self) -> None:
        """The invariant-9 proof reused: what the audio path calls cannot be
        awaited even by accident."""
        for name in ("offer", "withdraw", "close", "depth", "dropped"):
            member = getattr(LaneRuntime, name)
            assert not inspect.iscoroutinefunction(member), f"LaneRuntime.{name} is awaitable"

    def test_offering_a_frame_consumes_no_time_at_all(self) -> None:
        clock = FakeClock()
        runtime = _runtime(clock, lanes=[Lane.LINGUISTIC], consent_scopes=("lane:linguistic",))
        for index in range(50):
            runtime.offer(frame(index))
        assert clock.now_ms() == 0.0
        runtime.close()

    def _turn_latency(self, stall_s: float | None) -> float:
        clock = FakeClock()
        session = build_session(clock, steps=[scripted_step()])
        runtime = (
            None
            if stall_s is None
            else _runtime(
                clock,
                lanes=[Lane.AFFECT, Lane.LINGUISTIC],
                consent_scopes=("lane:affect", "lane:linguistic"),
                stall_s=stall_s,
            )
        )

        async def scenario() -> float:
            pump = None
            if runtime is not None:
                for index in range(8):
                    runtime.offer(frame(index))
                pump = asyncio.ensure_future(runtime.pump())
            outcome = await session.take_turn("iki gündür ağrıyor")
            if pump is not None:
                pump.cancel()
            return float(outcome.elapsed_ms)

        elapsed = float(clock.run(scenario()))
        if runtime is not None:
            runtime.close()
        return elapsed

    def test_turn_latency_is_unchanged_by_lanes_stalled_thirty_seconds(self) -> None:
        """The fake-clock test invariant 11 names, taken past its own number."""
        without = self._turn_latency(None)
        instant = self._turn_latency(0.0)
        thirty = self._turn_latency(30.0)
        an_hour = self._turn_latency(3_600.0)

        assert without == instant == thirty == an_hour
        assert without > 0.0, "the turn must actually have spoken something"

    def test_the_measurement_is_not_vacuous_an_awaited_lane_would_cost_the_stall(self) -> None:
        """The positive control the equality above needs.

        The same 30 s stall, awaited on the turn's own path, costs the full
        30 s of virtual time. So ``test_turn_latency_is_unchanged_…`` measures
        where the lanes sit, not a property of the fake clock.
        """
        clock = FakeClock()
        session = build_session(clock, steps=[scripted_step()])
        runtime = _runtime(
            clock,
            lanes=[Lane.LINGUISTIC],
            consent_scopes=("lane:linguistic",),
            stall_s=30.0,
        )

        async def scenario() -> float:
            runtime.offer(frame(0))
            started = clock.now_ms()
            await runtime.pump()  # the regression, made deliberately
            await session.take_turn("iki gündür ağrıyor")
            return clock.now_ms() - started

        elapsed = float(clock.run(scenario()))
        runtime.close()
        assert elapsed >= 30_000.0

    def test_a_stalled_lane_never_blocks_the_next_frame(self) -> None:
        clock = FakeClock()
        runtime = _runtime(
            clock,
            lanes=[Lane.LINGUISTIC],
            consent_scopes=("lane:linguistic",),
            stall_s=30.0,
            budget=LaneBudget(window_s=1.0, frame_ms=100.0),
        )

        async def scenario() -> None:
            runtime.offer(frame(0))
            pump = asyncio.ensure_future(runtime.pump())
            await asyncio.sleep(0)
            for index in range(1, 40):
                runtime.offer(frame(index))
            assert clock.now_ms() == 0.0
            pump.cancel()

        clock.run(scenario())
        assert runtime.dropped(Lane.LINGUISTIC) > 0
        runtime.close()


# --- clause 3: budgets and backpressure ---------------------------------------------


class TestBudgetsAndBackpressure:
    def test_a_budget_wider_than_the_sixty_second_ceiling_is_refused(self) -> None:
        assert MAX_WINDOW_SECONDS == 60.0
        LaneBudget(window_s=60.0, frame_ms=20.0)
        with pytest.raises(ValueError, match="60"):
            LaneBudget(window_s=60.1, frame_ms=20.0)

    def test_a_budget_with_a_non_positive_frame_is_refused(self) -> None:
        with pytest.raises(ValueError, match="frame_ms"):
            LaneBudget(window_s=1.0, frame_ms=0.0)

    def test_every_shipped_lane_budget_is_inside_the_ceiling(self) -> None:
        for lane, spec in LANE_SPECS.items():
            assert spec.budget.window_s <= MAX_WINDOW_SECONDS, lane

    def test_frames_beyond_the_budget_are_dropped_and_the_newest_window_survives(self) -> None:
        clock = FakeClock()
        budget = LaneBudget(window_s=1.0, frame_ms=100.0)  # ten frames
        runtime = _runtime(
            clock,
            lanes=[Lane.LINGUISTIC],
            consent_scopes=("lane:linguistic",),
            budget=budget,
        )
        for index in range(25):
            runtime.offer(frame(index))

        assert runtime.depth(Lane.LINGUISTIC) == 10
        assert runtime.dropped(Lane.LINGUISTIC) == 15
        window = runtime.take_window(Lane.LINGUISTIC)
        assert window is not None
        assert bytes(window.frames[-1]) == frame(24)
        assert window.dropped_frames == 15
        runtime.close()

    def test_the_dropped_frame_metric_counts_by_lane_and_nothing_else(self) -> None:
        clock = FakeClock()
        before = REGISTRY.get_sample_value(
            "lane_dropped_frames_total", {"lane": Lane.ENGAGEMENT.value}
        )
        runtime = _runtime(
            clock,
            lanes=[Lane.LINGUISTIC],
            consent_scopes=("lane:linguistic",),
            budget=LaneBudget(window_s=0.2, frame_ms=100.0),
        )
        for index in range(7):
            runtime.offer(frame(index))
        after = REGISTRY.get_sample_value(
            "lane_dropped_frames_total", {"lane": Lane.LINGUISTIC.value}
        )
        assert after is not None and after >= 5.0
        assert LANE_DROPPED_FRAMES._labelnames == ("lane",)
        # an unadmitted lane has no child at all — absence, not a zero
        assert (
            REGISTRY.get_sample_value("lane_dropped_frames_total", {"lane": Lane.ENGAGEMENT.value})
            == before
        )
        runtime.close()

    def test_the_window_is_zeroed_after_the_lane_has_looked_at_it(self) -> None:
        """Invariant 3: no artefact derived from raw audio outlives the buffer."""
        clock = FakeClock()
        runtime = _runtime(clock, lanes=[Lane.LINGUISTIC], consent_scopes=("lane:linguistic",))
        runtime.offer(frame(0))
        window = runtime.take_window(Lane.LINGUISTIC)
        assert window is not None and bytes(window.frames[0]) == frame(0)
        window.zeroize()
        assert set(bytes(window.frames[0])) == {0}

    def test_pumping_leaves_no_frame_bytes_behind(self) -> None:
        clock = FakeClock()
        lane = lane_double(Lane.LINGUISTIC, clock)
        runtime = LaneRuntime.admit(
            session_id=SESSION_ID,
            implementations=[lane],
            consent=granted("lane:linguistic"),
            interaction=NEUTRAL,
        )
        runtime.offer(frame(0))
        assert clock.run(runtime.pump()) == 1
        assert runtime.depth(Lane.LINGUISTIC) == 0
        assert runtime.store.state.linguistic_markers == {"frames_seen": 1.0}
        runtime.close()

    def test_pumping_with_no_frames_runs_nothing(self) -> None:
        clock = FakeClock()
        runtime = _runtime(clock, lanes=[Lane.LINGUISTIC], consent_scopes=("lane:linguistic",))
        assert clock.run(runtime.pump()) == 0
        runtime.close()

    def test_a_lane_that_faults_loses_its_window_and_never_stops_the_session(self) -> None:
        """A lane fault is a dropped window, not a crashed pump — and the log
        carries the exception class, never its message (invariant 6)."""
        clock = FakeClock()
        lane = lane_double(Lane.LINGUISTIC, clock, raises=True)
        runtime = LaneRuntime.admit(
            session_id=SESSION_ID,
            implementations=[lane],
            consent=granted("lane:linguistic"),
            interaction=NEUTRAL,
        )
        runtime.offer(frame(0))
        held = runtime.buffered_frames(Lane.LINGUISTIC)
        assert clock.run(runtime.pump()) == 0
        assert runtime.store.state.linguistic_markers == {}
        assert set(bytes(held[0])) == {0}
        # the session survives: the next window is still observed
        runtime.offer(frame(1))
        assert clock.run(runtime.pump()) == 0

    def test_a_lane_that_declines_a_window_writes_nothing(self) -> None:
        clock = FakeClock()
        runtime = LaneRuntime.admit(
            session_id=SESSION_ID,
            implementations=[lane_double(Lane.LINGUISTIC, clock, silent=True)],
            consent=granted("lane:linguistic"),
            interaction=NEUTRAL,
        )
        runtime.offer(frame(0))
        assert clock.run(runtime.pump()) == 0
        assert runtime.store.state.linguistic_markers == {}

    def test_close_zeroes_every_buffered_frame(self) -> None:
        clock = FakeClock()
        runtime = _runtime(clock, lanes=[Lane.LINGUISTIC], consent_scopes=("lane:linguistic",))
        runtime.offer(frame(0))
        held = runtime.buffered_frames(Lane.LINGUISTIC)
        assert bytes(held[0]) == frame(0)
        runtime.close()
        assert set(bytes(held[0])) == {0}
        assert runtime.depth(Lane.LINGUISTIC) == 0


# --- clause 4: per-lane consent ------------------------------------------------------


class TestPerLaneConsent:
    def test_every_declared_lane_scope_resolves_in_the_closed_registry(self) -> None:
        for lane, scope in LANE_CONSENT_SCOPE.items():
            assert resolve_scope(scope).id == scope, lane

    def test_acoustic_has_no_consent_scope_because_it_is_an_icf_not_a_toggle(self) -> None:
        """files/06 §2.4 — a device you may not place on the market is not made
        lawful by a toggle, so ``lane:acoustic`` is refused by the registry."""
        assert Lane.ACOUSTIC not in LANE_CONSENT_SCOPE
        with pytest.raises(UnknownPurposeError):
            resolve_scope("lane:acoustic")

    def test_a_lane_whose_consent_purpose_files_06_does_not_name_cannot_be_admitted(self) -> None:
        """files/03 §4.7 says every lane is its own consent purpose; files/06 §2
        lists exactly two. Neither ``asr_quality`` nor ``engagement`` has one,
        so they are refused rather than attached to a basis nobody chose."""
        clock = FakeClock()
        for lane in (Lane.ASR_QUALITY, Lane.ENGAGEMENT):
            assert lane not in LANE_CONSENT_SCOPE
            with pytest.raises(LaneConsentUndeclared):
                LaneRuntime.admit(
                    session_id=SESSION_ID,
                    implementations=[lane_double(lane, clock)],
                    consent=granted("voice", "core"),
                    interaction=NEUTRAL,
                )

    def test_a_refused_lane_is_absent_not_idle(self) -> None:
        clock = FakeClock()
        runtime = LaneRuntime.admit(
            session_id=SESSION_ID,
            implementations=[
                lane_double(Lane.AFFECT, clock),
                lane_double(Lane.LINGUISTIC, clock),
            ],
            consent=granted("lane:linguistic") + refused("lane:affect"),
            interaction=NEUTRAL,
        )
        assert runtime.lanes == frozenset({Lane.LINGUISTIC})
        runtime.offer(frame(0))
        # no ring, so nothing to ask about — an idle lane would answer 0
        with pytest.raises(LookupError):
            runtime.depth(Lane.AFFECT)
        with pytest.raises(LookupError):
            runtime.dropped(Lane.AFFECT)
        assert clock.run(runtime.pump()) == 1
        runtime.close()

    def test_a_lane_with_no_decision_at_all_is_absent(self) -> None:
        """Silence is not consent: the framework never falls back to a default,
        because the default belongs to the one evaluator."""
        clock = FakeClock()
        runtime = LaneRuntime.admit(
            session_id=SESSION_ID,
            implementations=[lane_double(Lane.AFFECT, clock)],
            consent=(),
            interaction=NEUTRAL,
        )
        assert runtime.lanes == frozenset()

    def test_withdrawal_removes_the_lane_zeroes_its_frames_and_drops_its_aggregate(self) -> None:
        clock = FakeClock()
        runtime = _runtime(clock, lanes=[Lane.LINGUISTIC], consent_scopes=("lane:linguistic",))
        runtime.offer(frame(0))
        assert clock.run(runtime.pump()) == 1
        assert runtime.store.state.linguistic_markers != {}

        runtime.offer(frame(1))
        held = runtime.buffered_frames(Lane.LINGUISTIC)
        runtime.withdraw(Lane.LINGUISTIC)

        assert runtime.lanes == frozenset()
        assert set(bytes(held[0])) == {0}
        assert runtime.store.state.linguistic_markers == {}
        assert clock.run(runtime.pump()) == 0

    def test_withdrawing_the_affect_lane_drops_nothing_because_it_stored_nothing(self) -> None:
        """Invariant 22 again, from the withdrawal side: there is no affect
        aggregate to drop, because M1's inference never left M1."""
        clock = FakeClock()
        runtime = _runtime(clock, lanes=[Lane.AFFECT], consent_scopes=("lane:affect",))
        runtime.offer(frame(0))
        assert clock.run(runtime.pump()) == 1
        before = runtime.store.state
        runtime.withdraw(Lane.AFFECT)
        assert runtime.lanes == frozenset()
        assert runtime.store.state == before

    def test_withdrawing_a_lane_that_was_never_admitted_is_a_lookup_error(self) -> None:
        clock = FakeClock()
        runtime = _runtime(clock, lanes=[Lane.LINGUISTIC], consent_scopes=("lane:linguistic",))
        with pytest.raises(LookupError):
            runtime.withdraw(Lane.AFFECT)


# --- clause 5: acoustic fails closed --------------------------------------------------


def _study(**overrides: object) -> StudyRecord:
    payload: dict[str, object] = {
        "study_id": "sentetik-calisma",
        "site": "sentetik-merkez",
        "ethics_committee": "sentetik-kaek",
        "ethics_approval_id": "sentetik-karar-1",
        "approval_date": date(2026, 1, 1),
        "approval_valid_until": date(2027, 1, 1),
        "protocol_version": "v1",
        "recipients": ("sentetik-arastirmaci",),
    }
    payload.update(overrides)
    return StudyRecord.model_validate(payload)


class _StudyWithIcf(StudyRecord):
    """What the registry record will look like once files/08 §3's
    ``ICF_version`` field lands on it. Test-only, so the gate's ICF check can
    be shown to be a real comparison rather than a permanent refusal."""

    icf_version: str


class _StudyWithNumericIcf(StudyRecord):
    """The near-miss: a record that has the field under the wrong type. An ICF
    version is the string an assertion carries, so a number next to it vouches
    for nothing."""

    icf_version: int


def _assertion(**overrides: object) -> AcousticAssertion:
    payload: dict[str, object] = {
        "study_id": "sentetik-calisma",
        "protocol_version": "v1",
        "icf_version": "icf-1",
        "approval_date": date(2026, 1, 1),
    }
    payload.update(overrides)
    return AcousticAssertion(**payload)  # type: ignore[arg-type]


class TestAcousticFailsClosed:
    def test_all_four_assertions_are_required_and_none_has_a_default(self) -> None:
        fields = {f.name: f for f in dataclasses.fields(AcousticAssertion)}
        assert set(fields) == {"study_id", "protocol_version", "icf_version", "approval_date"}
        for name, field_def in fields.items():
            assert field_def.default is dataclasses.MISSING, name
            assert field_def.default_factory is dataclasses.MISSING, name

    def test_the_shipped_registry_registers_no_study_so_acoustic_is_unreachable(self) -> None:
        """HB-L1 and HB-R1: no site, no ethics decision, no study — so today
        the gate refuses before it looks at anything else."""
        assert load_default_registry().studies == ()
        with pytest.raises(UnknownStudyError):
            admit_acoustic(_assertion(), registry=load_default_registry(), on=date(2026, 6, 1))

    def test_a_protocol_amendment_closes_the_gate(self) -> None:
        """TCKAY m.11 makes an amendment a fresh submission, so the assertion
        that was valid against v1 is refused the moment the record says v2."""
        amended = StudyRegistry(studies=(_study(protocol_version="v2"),))
        with pytest.raises(ProtocolAmendedError):
            admit_acoustic(_assertion(), registry=amended, on=date(2026, 6, 1))

    def test_an_approval_date_that_is_not_the_registered_one_is_refused(self) -> None:
        registry = StudyRegistry(studies=(_study(),))
        with pytest.raises(ApprovalDateMismatchError):
            admit_acoustic(
                _assertion(approval_date=date(2026, 2, 1)),
                registry=registry,
                on=date(2026, 6, 1),
            )

    def test_a_lapsed_approval_refuses_the_day_after_with_no_grace(self) -> None:
        registry = StudyRegistry(studies=(_study(),))
        last_day = date(2027, 1, 1)
        with pytest.raises(StudyApprovalLapsedError):
            admit_acoustic(_assertion(), registry=registry, on=last_day + timedelta(days=1))

    def test_an_icf_version_the_registry_does_not_record_is_refused(self) -> None:
        """The registry is the single source of ethics ids; a version it cannot
        vouch for is not asserted, it is merely claimed."""
        registry = StudyRegistry(studies=(_study(),))
        with pytest.raises(IcfVersionUnrecordedError):
            admit_acoustic(_assertion(), registry=registry, on=date(2026, 6, 1))

    def test_the_gate_opens_only_when_the_registry_vouches_for_all_four(self) -> None:
        record = _StudyWithIcf.model_validate(
            {
                "study_id": "sentetik-calisma",
                "site": "sentetik-merkez",
                "ethics_committee": "sentetik-kaek",
                "ethics_approval_id": "sentetik-karar-1",
                "approval_date": date(2026, 1, 1),
                "approval_valid_until": date(2027, 1, 1),
                "protocol_version": "v1",
                "recipients": ("sentetik-arastirmaci",),
                "icf_version": "icf-1",
            }
        )
        registry = StudyRegistry(studies=(record,))
        admission = admit_acoustic(_assertion(), registry=registry, on=date(2026, 6, 1))
        assert isinstance(admission, AcousticAdmission)
        assert admission.study_id == "sentetik-calisma"

        with pytest.raises(IcfVersionUnrecordedError):
            admit_acoustic(_assertion(icf_version="icf-2"), registry=registry, on=date(2026, 6, 1))

    def test_a_record_carrying_the_icf_field_under_another_type_vouches_for_nothing(self) -> None:
        payload = {
            "study_id": "sentetik-calisma",
            "site": "sentetik-merkez",
            "ethics_committee": "sentetik-kaek",
            "ethics_approval_id": "sentetik-karar-1",
            "approval_date": date(2026, 1, 1),
            "approval_valid_until": date(2027, 1, 1),
            "protocol_version": "v1",
            "recipients": ("sentetik-arastirmaci",),
            "icf_version": 1,
        }
        registry = StudyRegistry(studies=(_StudyWithNumericIcf.model_validate(payload),))
        with pytest.raises(IcfVersionUnrecordedError):
            admit_acoustic(_assertion(), registry=registry, on=date(2026, 6, 1))

    def test_an_assertion_field_that_is_not_id_shaped_is_refused(self) -> None:
        """Ids only, and the refused value is never echoed (invariant 6)."""
        with pytest.raises(StudyAssertionRefused) as refusal:
            _assertion(icf_version="onam formu sürüm bir")
        assert "onam" not in str(refusal.value)

    def test_an_admitted_acoustic_lane_writes_to_the_sealed_store_and_nowhere_else(self) -> None:
        """files/03 §4.7.4's one destination, wired as a seam INT-115 fills.
        Even admitted, the band never reaches ``ObserverState``."""
        clock = FakeClock()
        sealed = RecordingSealedStore()
        admission = AcousticAdmission(
            study_id="sentetik-calisma",
            protocol_version="v1",
            icf_version="icf-1",
            approval_date=date(2026, 1, 1),
        )
        runtime = LaneRuntime.admit(
            session_id=SESSION_ID,
            implementations=[lane_double(Lane.ACOUSTIC, clock)],
            consent=(),
            interaction=NEUTRAL,
            study=admission,
            sealed_store=sealed,
        )
        assert runtime.lanes == frozenset({Lane.ACOUSTIC})
        runtime.offer(frame(0))
        assert clock.run(runtime.pump()) == 1
        assert [study_id for study_id, _ in sealed.recorded] == ["sentetik-calisma"]
        state = runtime.store.state
        assert state.linguistic_markers == {}
        assert state.asr_quality == {}
        assert state.engagement == {}
        runtime.close()

    def test_the_acoustic_lane_is_absent_without_an_admission(self) -> None:
        clock = FakeClock()
        runtime = LaneRuntime.admit(
            session_id=SESSION_ID,
            implementations=[lane_double(Lane.ACOUSTIC, clock)],
            consent=granted("lane:linguistic"),
            interaction=NEUTRAL,
        )
        assert runtime.lanes == frozenset()

    def test_the_acoustic_lane_is_absent_without_a_sealed_store_to_write_to(self) -> None:
        """files/03 §4.7.4 gives that output one destination. The sealed store
        is INT-115's, so on this branch there is nowhere for a band to go and
        the lane is not built — unreachable, not merely unrendered."""
        clock = FakeClock()
        admission = AcousticAdmission(
            study_id="sentetik-calisma",
            protocol_version="v1",
            icf_version="icf-1",
            approval_date=date(2026, 1, 1),
        )
        runtime = LaneRuntime.admit(
            session_id=SESSION_ID,
            implementations=[lane_double(Lane.ACOUSTIC, clock)],
            consent=granted("lane:linguistic"),
            interaction=NEUTRAL,
            study=admission,
        )
        assert runtime.lanes == frozenset()
        with pytest.raises(LookupError):
            runtime.depth(Lane.ACOUSTIC)
        runtime.offer(frame(0))
        assert clock.run(runtime.pump()) == 0


# --- invariant 6: nothing a lane reads reaches a log ---------------------------------


def _sweep(text: str) -> str:
    """Decode escapes before searching: ``ensure_ascii`` JSON hides a Turkish
    sentence behind ``\\u00f6`` and a raw substring search would miss it."""
    return text.encode("ascii", "backslashreplace").decode("unicode_escape")


class TestNoPhiReachesALogOrAMetric:
    def test_no_lane_log_record_carries_the_frame_it_read(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        clock = FakeClock()
        with caplog.at_level(logging.DEBUG):
            runtime = _runtime(
                clock,
                lanes=[Lane.LINGUISTIC],
                consent_scopes=("lane:linguistic",),
                budget=LaneBudget(window_s=0.2, frame_ms=100.0),
            )
            for index in range(9):
                runtime.offer(frame(index))
            clock.run(runtime.pump())
            runtime.withdraw(Lane.LINGUISTIC)
            runtime.close()

        rendered = _sweep("\n".join(record.getMessage() for record in caplog.records))
        extras = _sweep(
            "\n".join(
                f"{key}={value!r}"
                for record in caplog.records
                for key, value in vars(record).items()
            )
        )
        assert SYNTHETIC_TURKISH not in rendered
        assert SYNTHETIC_TURKISH not in extras
        assert SESSION_ID not in rendered

    def test_the_only_metric_label_is_the_closed_lane_enumeration(self) -> None:
        assert LANE_DROPPED_FRAMES._labelnames == ("lane",)
        for lane in Lane:
            assert lane.value.isidentifier()

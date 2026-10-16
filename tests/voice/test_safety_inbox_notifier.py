"""INT-406 — the runtime half of invariant 49: every RED reaches the Safety inbox.

files/10 §9.1 invariant 49: *"every RED produces a clinic inbox entry ≤ 60 s
regardless of connector presence"*. The runtime's part is three joints, each
held here:

1. **Layer B tells the clinic at the determination.** ``BackendAgent`` hands a
   rules-engine RED to its clinician route the moment it settles, before Layer
   A has drained it — so a patient who hangs up on the answer that fired the
   RED still produces an entry. The RED path's order is unchanged: the
   route's port has no awaitable member, so it cannot delay anything.
2. **The adapter is in-process.** :class:`SafetyInboxNotifier` turns the
   notification into an entry in the process's outbox; no connector, no
   network call and no await sits between the RED and the entry.
3. **A session cannot be composed without it, and a worker cannot be ready
   without the inbox store.** ``clinic`` is a required argument of both
   composition roots (parity), and ``/readyz`` names ``safety_inbox`` on both
   profiles — a typed session fires REDs too.

Every id is synthetic (files/04 §7).
"""

from __future__ import annotations

import inspect
import logging
from datetime import UTC, datetime

import fakeredis
import pytest
from clinical_schemas.triage import (
    RedLocation,
    RedRegister,
    RuleFire,
    RulesTriageResult,
    TriageLevel,
)
from fastapi.testclient import TestClient
from intake_platform.safety_inbox import EntryKind, RedisSafetyInboxStore, SafetyInboxOutbox
from intake_voice_runtime.app import VoiceRuntimeWiring, create_app
from intake_voice_runtime.clinical_agent import IntakeEngine
from intake_voice_runtime.clinical_agent.work_queue import BackendAgent, StateContext, StateEffect
from intake_voice_runtime.composition import build_residency_tr_session, build_typed_session
from intake_voice_runtime.ports import WorkRequest, WorkState, WorkType
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.safety_inbox import SafetyInboxNotifier
from intake_voice_runtime.talker.delivery import DeliveryClass
from intake_voice_runtime.talker.preemption import BackendResult, Presentation, Priority
from intake_voice_runtime.talker.red_path import ClinicNotifier, RedNotification
from prometheus_client import REGISTRY
from red_harness import RecordingClinicNotifier
from session_harness import HASH, NOW, builders, protocol
from talker_harness import FakeClock

T0 = datetime(2026, 9, 27, 9, 0, tzinfo=UTC)
TENANT = "tenant-a"
SESSION = "11111111-2222-4333-8444-555555555555"
PINNED_RULE = "rf.sentetik_kirmizi"


def _engine() -> IntakeEngine:
    return IntakeEngine(protocol=protocol(), reference_time=NOW)


def _triage(level: TriageLevel) -> RulesTriageResult:
    if level is TriageLevel.RED:
        return RulesTriageResult(
            level=level,
            rules=(RuleFire(id=PINNED_RULE, evidence="sentetik kanıt"),),
            register=RedRegister.DEFERRED_CLINICIAN,
            location=RedLocation.UNKNOWN,
        )
    return RulesTriageResult(
        level=level, rules=(RuleFire(id=PINNED_RULE, evidence="sentetik kanıt"),)
    )


def _agent(clinic: ClinicNotifier | None, level: TriageLevel) -> BackendAgent:
    agent = BackendAgent(
        session_id=SESSION,
        engine=_engine(),
        rule_ids=frozenset({PINNED_RULE}),
        clock=FakeClock(),
        clinic=clinic,
    )

    def handler(context: StateContext) -> StateEffect:
        return StateEffect(triage_update=_triage(level))

    agent.register_state(WorkType.EXTRACT_SLOTS, handler)
    return agent


def _run(agent: BackendAgent) -> WorkState:
    ticket = agent.submit(
        WorkRequest(
            session_id=SESSION,
            work_type=WorkType.EXTRACT_SLOTS,
            step_id="oyku.birinci",
            input_hash="a" * 64,
            protocol_hash=HASH,
            engine_version=0,
        )
    )
    agent.run_pending()
    return agent.record(ticket.work_id).state


class TestLayerBTellsTheClinicAtTheDetermination:
    def test_a_red_is_notified_once_before_anything_drains_it(self) -> None:
        clinic = RecordingClinicNotifier()
        agent = _agent(clinic, TriageLevel.RED)
        assert _run(agent) is WorkState.COMPLETED
        (notification,) = clinic.notifications
        assert notification.rule_ids == (PINNED_RULE,)
        assert notification.register is RedRegister.DEFERRED_CLINICIAN
        assert notification.location is RedLocation.UNKNOWN
        # DEFERRED_CLINICIAN: the patient surface does not change, the clinic hears
        assert notification.patient_facing is False
        (result,) = agent.drain_results()
        assert notification.work_id == result.work_id

    @pytest.mark.parametrize("level", [TriageLevel.YELLOW, TriageLevel.GREEN])
    def test_nothing_but_a_red_is_notified(self, level: TriageLevel) -> None:
        clinic = RecordingClinicNotifier()
        assert _run(_agent(clinic, level)) is WorkState.COMPLETED
        assert clinic.notifications == []

    def test_a_route_that_raises_never_costs_the_red(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        class Broken:
            def notify(self, notification: RedNotification) -> None:
                raise RuntimeError("sentetik arıza")

        agent = _agent(Broken(), TriageLevel.RED)
        before = REGISTRY.get_sample_value("clinic_red_inbox_route_failures_total") or 0.0
        with caplog.at_level(logging.ERROR):
            assert _run(agent) is WorkState.COMPLETED
        assert agent.sealed
        assert len(agent.drain_results()) == 1
        assert "sentetik arıza" not in caplog.text
        assert "red clinic route failed" in caplog.text
        # no entry means no clock: the counter is the page instead
        assert REGISTRY.get_sample_value("clinic_red_inbox_route_failures_total") == before + 1

    def test_no_clinic_route_leaves_the_queue_as_it_was(self) -> None:
        """The unit-level default. The composition roots never take it."""
        assert _run(_agent(None, TriageLevel.RED)) is WorkState.COMPLETED

    def test_a_forged_result_is_counted_not_raised(self) -> None:
        """Unreachable past ``authorise_preempt``; if a forged shape ever got
        this far, the route counts it rather than raising inside Layer B."""
        clinic = RecordingClinicNotifier()
        agent = _agent(clinic, TriageLevel.RED)
        forged = BackendResult.model_construct(
            work_id="w_forged",
            state=WorkState.COMPLETED,
            delivery_class=DeliveryClass.RED,
            presentation=Presentation(),
            priority=Priority.PREEMPT,
        )
        before = REGISTRY.get_sample_value("clinic_red_inbox_route_failures_total") or 0.0
        agent._notify_clinic(forged)
        assert clinic.notifications == []
        assert REGISTRY.get_sample_value("clinic_red_inbox_route_failures_total") == before + 1


class TestTheAdapterIsInProcess:
    def test_notify_puts_one_entry_and_awaits_nothing(self) -> None:
        outbox = SafetyInboxOutbox(clock=lambda: T0)
        notifier = SafetyInboxNotifier(
            outbox=outbox,
            tenant_id=TENANT,
            session_id=SESSION,
            visit_id=SESSION,
            wall_clock=lambda: T0,
        )
        assert isinstance(notifier, ClinicNotifier)
        assert not inspect.iscoroutinefunction(notifier.notify)
        notifier.notify(
            RedNotification(
                work_id="w_red",
                rule_ids=(PINNED_RULE,),
                register=RedRegister.ALERT,
                location=RedLocation.REMOTE,
                evaluated_at_ms=0.0,
                patient_facing=True,
            )
        )
        (entry,) = outbox.pending()
        assert entry.kind is EntryKind.RED
        assert entry.tenant_id == TENANT
        assert entry.source_ref == "w_red"
        assert entry.created_at == T0

    @pytest.mark.parametrize("register", list(RedRegister))
    def test_an_on_site_red_also_notifies_staff_in_the_same_put(
        self, register: RedRegister
    ) -> None:
        """INT-475: files/04 §8.1 rule 7 — under ON_SITE the staff notification
        fires automatically with the RED, and every KIRMIZI rule's ON_SITE action
        carries notify_staff_immediate (protocols.dsl), whatever its register."""
        outbox = SafetyInboxOutbox(clock=lambda: T0)
        _bound_notifier(outbox).notify(
            _notification(location=RedLocation.ON_SITE, register=register)
        )
        red, on_site = outbox.pending()
        assert red.kind is EntryKind.RED
        assert on_site.kind is EntryKind.RED_ON_SITE
        assert on_site.source_ref == red.source_ref == "w_red"
        assert on_site.rule_ids == (PINNED_RULE,)
        assert on_site.register is None
        assert (on_site.session_id, on_site.visit_id) == (SESSION, SESSION)

    @pytest.mark.parametrize("location", [RedLocation.REMOTE, RedLocation.UNKNOWN])
    def test_near_miss_a_red_off_site_notifies_no_staff(self, location: RedLocation) -> None:
        outbox = SafetyInboxOutbox(clock=lambda: T0)
        _bound_notifier(outbox).notify(_notification(location=location))
        assert [entry.kind for entry in outbox.pending()] == [EntryKind.RED]

    def test_a_mis_wired_notifier_fails_at_composition_not_at_the_red(self) -> None:
        with pytest.raises(ValueError):
            SafetyInboxNotifier(
                outbox=SafetyInboxOutbox(),
                tenant_id="Not A Tenant",
                session_id=SESSION,
                visit_id=SESSION,
            )
        with pytest.raises(ValueError):
            SafetyInboxNotifier(
                outbox=SafetyInboxOutbox(),
                tenant_id=TENANT,
                session_id="hasta adı",
                visit_id=SESSION,
            )


class TestNoSessionWithoutTheRoute:
    @pytest.mark.parametrize("builder", [build_residency_tr_session, build_typed_session])
    def test_both_composition_roots_require_the_clinic_route(self, builder: object) -> None:
        parameter = inspect.signature(builder).parameters["clinic"]  # type: ignore[arg-type]
        assert parameter.default is inspect.Parameter.empty
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY

    def test_the_composed_agent_carries_the_route(self) -> None:
        clock = FakeClock()
        for profile, build in builders(tenant_id=TENANT, session_id=SESSION, clock=clock).items():
            assert build().agent.clinic is not None, profile


class TestNoWorkerWithoutTheInbox:
    @pytest.mark.parametrize("profile", [VoiceProfile.TYPED, VoiceProfile.RESIDENCY_TR])
    def test_readyz_names_the_safety_inbox_on_both_profiles(self, profile: VoiceProfile) -> None:
        client = TestClient(create_app(VoiceRuntimeWiring(profile=profile)))
        response = client.get("/readyz")
        assert response.status_code == 503
        assert response.json()["checks"]["safety_inbox"] == "error"

    def test_a_typed_worker_with_the_inbox_is_ready(self) -> None:
        wiring = VoiceRuntimeWiring(
            profile=VoiceProfile.TYPED,
            safety_inbox=RedisSafetyInboxStore(fakeredis.FakeStrictRedis()),
        )
        response = TestClient(create_app(wiring)).get("/readyz")
        assert response.status_code == 200
        assert response.json()["checks"]["safety_inbox"] == "ok"

    def test_the_app_pumps_the_process_outbox_into_the_store(self) -> None:
        store = RedisSafetyInboxStore(fakeredis.FakeStrictRedis())
        wiring = VoiceRuntimeWiring(profile=VoiceProfile.TYPED, safety_inbox=store)
        with TestClient(create_app(wiring)):
            _bound_notifier(wiring.outbox).notify(_notification())
            assert wiring.outbox.wait_until_empty(timeout=5.0)
        assert len(store.open_entries()) == 1

    def test_entries_the_store_refused_at_stop_are_counted_never_named(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        server = fakeredis.FakeServer()
        server.connected = False
        store = RedisSafetyInboxStore(fakeredis.FakeStrictRedis(server=server))
        wiring = VoiceRuntimeWiring(profile=VoiceProfile.TYPED, safety_inbox=store)
        with caplog.at_level(logging.ERROR), TestClient(create_app(wiring)):
            _bound_notifier(wiring.outbox).notify(_notification())
        assert len(wiring.outbox.pending()) == 1
        assert "safety inbox entries unwritten at stop" in caplog.text
        assert SESSION not in caplog.text


def _bound_notifier(outbox: SafetyInboxOutbox) -> SafetyInboxNotifier:
    return SafetyInboxNotifier(
        outbox=outbox, tenant_id=TENANT, session_id=SESSION, visit_id=SESSION, wall_clock=lambda: T0
    )


def _notification(
    *,
    location: RedLocation = RedLocation.REMOTE,
    register: RedRegister = RedRegister.ALERT,
) -> RedNotification:
    return RedNotification(
        work_id="w_red",
        rule_ids=(PINNED_RULE,),
        register=register,
        location=location,
        evaluated_at_ms=0.0,
        patient_facing=register is not RedRegister.DEFERRED_CLINICIAN,
    )

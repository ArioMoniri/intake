"""INT-406 — invariant 49 ``red_acknowledgement_sla_guard`` (files/10 §9.1).

files/10 §9.1, verbatim: *"every RED produces a clinic inbox entry ≤ 60 s
regardless of connector presence; the ack clock starts; unacknowledged past
SLA pages; ``02 §2b`` visit-state transitions on a RED visit raise an entry"*,
enforced by *"simulator + runtime"*. The numbers come from files/02 §8.2:
*"RED → clinic inbox ≤ 60 s. RED → human acknowledgement within a tenant SLA,
default 4 business hours"*.

This suite is the runtime half. The RED here is produced by the real rules
engine (``protocols.triage.evaluate_triage``) over a synthetic rule, settled
by the real Layer B queue (``BackendAgent``) and routed through the shipped
clinician-route adapter into the shipped Safety inbox, whose store is the
production Redis implementation over ``fakeredis``. Two clocks are faked and
nothing sleeps: the session's monotonic clock (what the queue stamps) and the
wall clock (what the inbox stamps and the SLA is measured on).

Near-miss controls sit beside every positive: a YELLOW, a GREEN that names a
rule, an LLM candidate flag and a RED naming a rule outside the pinned pack
never create an entry; a visit that carried only a YELLOW moves without one;
the SLA boundary itself does not page, one second past it does.

Everything is SYNTHETIC (files/04 §7): rule ids, slot names and ids carry no
clinical meaning, and no triage rule, level or RED semantic is defined here —
the suite consumes the rules engine, it does not configure it.
"""

from __future__ import annotations

import ast
import math
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

import fakeredis
import pytest
import yaml
from clinical_schemas.triage import CandidateFlag, RedLocation, RedRegister
from intake_platform.safety_inbox import (
    DEFAULT_ACK_SLA,
    INBOX_ENTRY_BUDGET,
    PUMP_INTERVAL,
    UNREADABLE_TENANT,
    AckSlaPolicy,
    AgeBand,
    EntryKind,
    RedisSafetyInboxStore,
    SafetyInbox,
    SafetyInboxOutbox,
    VisitTransition,
)
from intake_platform.safety_inbox.metrics import (
    CLINIC_RED_ACK_LATENCY_MIN,
    CLINIC_RED_INBOX_PENDING_AGE_S,
    CLINIC_RED_UNACKNOWLEDGED_TOTAL,
)
from intake_voice_runtime.clinical_agent import IntakeEngine
from intake_voice_runtime.clinical_agent.work_queue import (
    BackendAgent,
    BackgroundEffect,
    ReadOnlyContext,
    StateContext,
    StateEffect,
)
from intake_voice_runtime.ports import WorkRequest, WorkState, WorkType
from intake_voice_runtime.safety_inbox import SafetyInboxNotifier
from prometheus_client import REGISTRY
from protocols import EK4Level
from protocols.compile.resolve import ResolvedProtocol, ResolvedSection, ResolvedSlot
from protocols.dsl import Slot
from protocols.locale_text import DEFAULT_LOCALE as TR
from protocols.triage import evaluate_triage
from protocols.types import Delivery, SlotType
from synthetic_triage import ctx, make_rule, present

REPO = Path(__file__).resolve().parents[2]
RULES_FILE = REPO / "infra" / "observability" / "safety-rules.yaml"
PROMETHEUS_CONFIG = REPO / "infra" / "observability" / "prometheus.yml"
OBS_COMPOSE = REPO / "infra" / "docker-compose.obs.yml"
CATALOG = REPO / "observability" / "metrics_catalog.yaml"
RUNBOOK = REPO / "docs" / "runbooks" / "red-acknowledgement.md"

#: The RED path's modules, from the rules engine's result to the store. None
#: may import a hospital connector: "regardless of connector presence" is a
#: property of the import graph before it is a property of a run.
RED_PATH_SOURCES: Final[tuple[Path, ...]] = (
    REPO / "services/voice-runtime/src/intake_voice_runtime/clinical_agent/work_queue.py",
    REPO / "services/voice-runtime/src/intake_voice_runtime/safety_inbox.py",
    *sorted((REPO / "packages/intake_platform/src/intake_platform/safety_inbox").glob("*.py")),
)

T0: Final = datetime(2026, 9, 27, 9, 0, tzinfo=UTC)
TENANT: Final = "tenant-a"
SESSION: Final = "11111111-2222-4333-8444-555555555555"
#: INT-197: a visit is a session row, so the visit id is the session's.
VISIT: Final = SESSION
OTHER_VISIT: Final = "99999999-2222-4333-8444-555555555555"
HASH: Final = "0" * 64
ACKER: Final = "kc-sub-tenant-clinical-responsible"

RED_RULE = make_rule(
    "rf.sentetik_kirmizi", EK4Level.KIRMIZI_K2, "kirmizi_isaret == true", register=RedRegister.CALM
)
YELLOW_RULE = make_rule("rf.sentetik_sari", EK4Level.SARI_K1, "sari_isaret == true")
GREEN_RULE = make_rule("rf.sentetik_yesil", EK4Level.YESIL, "yesil_isaret == true")
RULES = (RED_RULE, YELLOW_RULE, GREEN_RULE)
PINNED: Final = frozenset(rule.id for rule in RULES)


# --- the two fake clocks ------------------------------------------------------------------


class WallClock:
    """The inbox's clock: aware UTC, advanced by hand."""

    def __init__(self, at: datetime) -> None:
        self.at = at

    def __call__(self) -> datetime:
        return self.at

    def advance(self, delta: timedelta) -> None:
        self.at += delta


class SessionClock:
    """The queue's monotonic clock (``intake_voice_runtime.ports.Clock``),
    read off the same wall so the two can be compared."""

    def __init__(self, wall: WallClock) -> None:
        self._wall = wall

    def now_ms(self) -> float:
        return (self._wall() - T0).total_seconds() * 1000.0

    async def sleep(self, seconds: float) -> None:
        raise AssertionError("nothing on the RED → inbox path may sleep")


# --- the synthetic protocol ---------------------------------------------------------------


def _protocol() -> ResolvedProtocol:
    slot = Slot.model_validate(
        {"type": SlotType.BOOLEAN, "ask_tr": {TR: "Sentetik soru."}, "follow_up_tr": {TR: "Takip."}}
    )
    section = ResolvedSection(
        id="oyku",
        delivery=Delivery.VOICE,
        allow_paraphrase=False,
        slots=(
            ResolvedSlot(
                section_id="oyku",
                key="isaret",
                fhir_link_id="oyku.isaret",
                slot=slot,
                delivery=Delivery.VOICE,
            ),
        ),
    )
    return ResolvedProtocol(
        pack_id="base.sentetik_kirmizi",
        version="1.0.0",
        chain=("base.sentetik_kirmizi",),
        sections=(section,),
        resolved_protocol_hash=HASH,
    )


class Rig:
    """One session's Layer B, wired to the Safety inbox the way production is."""

    def __init__(self, *, store: Any = None) -> None:
        self.wall = WallClock(T0)
        self.redis = fakeredis.FakeStrictRedis()
        self.store = store if store is not None else RedisSafetyInboxStore(self.redis)
        self.outbox = SafetyInboxOutbox(clock=self.wall)
        self.inbox = SafetyInbox(store=self.store)
        self.notifier = SafetyInboxNotifier(
            outbox=self.outbox,
            tenant_id=TENANT,
            session_id=SESSION,
            visit_id=VISIT,
            wall_clock=self.wall,
        )
        self.agent = BackendAgent(
            session_id=SESSION,
            engine=IntakeEngine(protocol=_protocol(), reference_time=T0),
            rule_ids=PINNED,
            clock=SessionClock(self.wall),
            clinic=self.notifier,
        )
        self._slots: dict[str, bool] = {}
        self._pinned_override: frozenset[str] | None = None
        self.agent.register_state(WorkType.EXTRACT_SLOTS, self._evaluate)
        self._submitted = 0

    def _evaluate(self, context: StateContext) -> StateEffect:
        # The rules engine, over the typed answer state (files/12 §1.1). The
        # handler passes its determination through verbatim: the queue
        # derives the priority, the handler cannot ask for one (INT-092).
        answers = {name: present(value) for name, value in self._slots.items()}
        evaluation = evaluate_triage(RULES, ctx(**answers), RedLocation.REMOTE)
        return StateEffect(triage_update=evaluation.result)

    def answer(self, **slots: bool) -> WorkState:
        """Submit one answer and run the Backend until it settles."""
        self._slots = dict(slots)
        self._submitted += 1
        ticket = self.agent.submit(
            WorkRequest(
                session_id=SESSION,
                work_type=WorkType.EXTRACT_SLOTS,
                step_id="oyku.isaret",
                input_hash=f"{self._submitted:064x}",
                protocol_hash=HASH,
                engine_version=0,
            )
        )
        self.agent.run_pending()
        return self.agent.record(ticket.work_id).state

    def flush(self) -> None:
        self.outbox.flush(self.store)


def _gauge(tenant: str, band: AgeBand) -> float | None:
    return REGISTRY.get_sample_value(
        "clinic_red_unacknowledged_total", {"tenant": tenant, "age_band": band.value}
    )


def _latency_count() -> float:
    return REGISTRY.get_sample_value("clinic_red_ack_latency_min_count") or 0.0


@pytest.fixture(autouse=True)
def _fresh_gauges() -> None:
    CLINIC_RED_UNACKNOWLEDGED_TOTAL.clear()
    CLINIC_RED_INBOX_PENDING_AGE_S.set(0.0)


# --- clause 1: every RED produces an entry within 60 s, whatever connector is present -------


class TestEveryRedProducesAnEntryWithinSixtySeconds:
    def test_a_rules_engine_red_is_in_the_inbox_within_the_budget(self) -> None:
        rig = Rig()
        assert rig.answer(kirmizi_isaret=True) is WorkState.COMPLETED
        # in-process on the RED path: the entry exists the instant the RED settles
        (pending,) = rig.outbox.pending()
        assert pending.kind is EntryKind.RED
        assert pending.created_at == T0
        # the pump flushes within one interval, which sits inside the budget
        assert PUMP_INTERVAL <= INBOX_ENTRY_BUDGET
        rig.wall.advance(PUMP_INTERVAL)
        rig.flush()
        (entry,) = rig.store.open_entries()
        assert entry.tenant_id == TENANT
        assert entry.session_id == SESSION
        assert entry.visit_id == VISIT
        assert entry.rule_ids == (RED_RULE.id,)
        assert entry.created_at == T0
        assert rig.wall() - entry.created_at <= INBOX_ENTRY_BUDGET
        assert entry.acknowledged_at is None

    def test_the_entry_carries_ids_and_nothing_else(self) -> None:
        """Invariant 6: ``RuleFire.evidence`` — which slot values satisfied
        the rule — is patient material and has no carrier on the entry."""
        rig = Rig()
        rig.answer(kirmizi_isaret=True)
        rig.flush()
        (entry,) = rig.store.open_entries()
        dumped = entry.model_dump_json()
        assert "kirmizi_isaret" not in dumped
        assert set(entry.model_dump()) == {
            "schema_version",
            "entry_id",
            "tenant_id",
            "session_id",
            "visit_id",
            "kind",
            "rule_ids",
            "source_ref",
            "created_at",
            "acknowledged_at",
            "acknowledged_by",
        }

    def test_the_red_settles_even_when_the_inbox_write_cannot_happen_yet(self) -> None:
        """The shared store is down: the RED still settles and seals, the
        entry waits in-process, and its age is exported for the page. The
        clock is not reset by the late write — it started at the RED."""
        server = fakeredis.FakeServer()
        server.connected = False
        rig = Rig(store=RedisSafetyInboxStore(fakeredis.FakeStrictRedis(server=server)))
        assert rig.answer(kirmizi_isaret=True) is WorkState.COMPLETED
        assert rig.agent.sealed
        rig.wall.advance(INBOX_ENTRY_BUDGET + timedelta(seconds=1))
        report = rig.outbox.flush(rig.store)
        assert report.written == ()
        assert report.pending == 1
        assert report.oldest_pending_age_s > INBOX_ENTRY_BUDGET.total_seconds()
        pending_age = REGISTRY.get_sample_value("clinic_red_inbox_pending_age_s")
        assert pending_age is not None
        assert pending_age > INBOX_ENTRY_BUDGET.total_seconds()
        # the store comes back: the entry lands with the RED's own timestamp
        server.connected = True
        report = rig.outbox.flush(rig.store)
        assert report.pending == 0
        assert REGISTRY.get_sample_value("clinic_red_inbox_pending_age_s") == 0.0
        (entry,) = rig.store.open_entries()
        assert entry.created_at == T0

    def test_a_replayed_red_is_one_entry(self) -> None:
        """files/03 §4.6 invariant 6: a re-derived RED carries the same
        content-addressed work id, so the inbox sees one RED, not two."""
        rig = Rig()
        rig.answer(kirmizi_isaret=True)
        (pending,) = rig.outbox.pending()
        rig.outbox.put(pending)
        rig.flush()
        assert len(rig.store.open_entries()) == 1

    def test_the_pump_writes_what_the_red_path_put(self) -> None:
        """The worker thread the runtime runs beside its sessions: woken by
        the put, it writes, and on shutdown it drains before it returns."""
        rig = Rig()
        rig.answer(kirmizi_isaret=True)
        worker = threading.Thread(target=rig.outbox.pump, args=(rig.store,))
        worker.start()
        try:
            assert rig.outbox.wait_until_empty(timeout=5.0)
        finally:
            rig.outbox.stop()
            worker.join(timeout=5)
        assert not worker.is_alive()
        assert len(rig.store.open_entries()) == 1

    def test_no_module_on_the_red_path_imports_a_connector(self) -> None:
        for source in RED_PATH_SOURCES:
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
            imported = {
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names
            } | {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
            assert not any(name.startswith("intake_connectors") for name in imported), source


class TestOnlyARulesEngineRedCreatesAnEntry:
    """Near-miss controls: invariant 1 says only the rules engine produces
    RED, and only a RED may enter this inbox."""

    def test_yellow_never_creates_an_entry(self) -> None:
        rig = Rig()
        assert rig.answer(sari_isaret=True) is WorkState.COMPLETED
        rig.flush()
        assert rig.outbox.pending() == ()
        assert rig.store.open_entries() == ()
        assert not rig.agent.sealed

    def test_a_green_that_names_a_rule_never_creates_an_entry(self) -> None:
        rig = Rig()
        assert rig.answer(yesil_isaret=True) is WorkState.COMPLETED
        rig.flush()
        assert rig.store.open_entries() == ()

    def test_nothing_firing_never_creates_an_entry(self) -> None:
        rig = Rig()
        assert rig.answer(kirmizi_isaret=False) is WorkState.COMPLETED
        rig.flush()
        assert rig.store.open_entries() == ()

    def test_an_llm_candidate_flag_never_creates_an_entry(self) -> None:
        rig = Rig()

        def candidate(context: ReadOnlyContext) -> BackgroundEffect:
            return BackgroundEffect(
                candidate_flags=(CandidateFlag(text="sentetik aday", evidence="ifade"),)
            )

        rig.agent.register_background(WorkType.PARSE_DOCUMENT, candidate)
        ticket = rig.agent.submit(
            WorkRequest(
                session_id=SESSION,
                work_type=WorkType.PARSE_DOCUMENT,
                step_id="oyku.isaret",
                input_hash="c" * 64,
                protocol_hash=HASH,
                engine_version=0,
            )
        )
        rig.agent.run_pending()
        assert rig.agent.record(ticket.work_id).state is WorkState.COMPLETED
        rig.flush()
        assert rig.store.open_entries() == ()

    def test_a_red_naming_a_rule_outside_the_pinned_pack_never_creates_an_entry(self) -> None:
        rig = Rig()
        rig.agent.rule_ids = frozenset({YELLOW_RULE.id})
        assert rig.answer(kirmizi_isaret=True) is WorkState.FAILED
        rig.flush()
        assert rig.outbox.pending() == ()
        assert rig.store.open_entries() == ()


# --- clause 2: the clock starts at the entry; unacknowledged past the SLA pages ------------


class TestTheClockPagesAtTheSla:
    def _entry_at_t0(self) -> Rig:
        rig = Rig()
        rig.answer(kirmizi_isaret=True)
        rig.flush()
        return rig

    def test_the_default_sla_is_the_02_default(self) -> None:
        assert DEFAULT_ACK_SLA == timedelta(hours=4)
        assert AckSlaPolicy().sla_for(TENANT) == DEFAULT_ACK_SLA

    def test_at_the_sla_it_does_not_page_and_one_second_past_it_does(self) -> None:
        rig = self._entry_at_t0()
        at_sla = rig.inbox.sweep(T0 + DEFAULT_ACK_SLA)
        assert at_sla.readable
        assert at_sla.breaches == ()
        assert _gauge(TENANT, AgeBand.WITHIN_SLA) == 1.0
        assert _gauge(TENANT, AgeBand.PAST_SLA) is None

        past = rig.inbox.sweep(T0 + DEFAULT_ACK_SLA + timedelta(seconds=1))
        (breach,) = past.breaches
        assert breach.tenant_id == TENANT
        assert breach.kind is EntryKind.RED
        assert breach.overdue_by == timedelta(seconds=1)
        assert _gauge(TENANT, AgeBand.PAST_SLA) == 1.0
        assert _gauge(TENANT, AgeBand.WITHIN_SLA) is None

    def test_a_tenant_sla_moves_the_page(self) -> None:
        rig = self._entry_at_t0()
        rig.inbox.policy = AckSlaPolicy(per_tenant={TENANT: timedelta(hours=1)})
        assert rig.inbox.sweep(T0 + timedelta(hours=1)).breaches == ()
        assert len(rig.inbox.sweep(T0 + timedelta(hours=1, seconds=1)).breaches) == 1

    def test_an_sla_that_is_not_a_duration_is_refused(self) -> None:
        with pytest.raises(ValueError, match="SLA"):
            AckSlaPolicy(per_tenant={TENANT: timedelta(0)})
        with pytest.raises(ValueError, match="SLA"):
            AckSlaPolicy(default=timedelta(seconds=-1))

    def test_an_acknowledgement_stops_the_clock(self) -> None:
        rig = self._entry_at_t0()
        (entry,) = rig.store.open_entries()
        before = _latency_count()
        acked = rig.inbox.acknowledge(
            tenant_id=TENANT,
            entry_id=entry.entry_id,
            by=ACKER,
            at=T0 + DEFAULT_ACK_SLA - timedelta(minutes=1),
        )
        assert acked.acknowledged_by == ACKER
        assert _latency_count() == before + 1
        report = rig.inbox.sweep(T0 + DEFAULT_ACK_SLA + timedelta(hours=1))
        assert report.breaches == ()
        assert report.open_count == 0
        assert _gauge(TENANT, AgeBand.PAST_SLA) is None

    def test_an_inbox_that_cannot_be_read_pages(self) -> None:
        """Fail closed: a sweep that cannot see the inbox cannot say nobody
        is waiting, so it reports the unreadable inbox past the SLA."""
        server = fakeredis.FakeServer()
        server.connected = False
        inbox = SafetyInbox(store=RedisSafetyInboxStore(fakeredis.FakeStrictRedis(server=server)))
        report = inbox.sweep(T0)
        assert not report.readable
        value = _gauge(UNREADABLE_TENANT, AgeBand.PAST_SLA)
        assert value is not None
        assert math.isinf(value)
        assert CLINIC_RED_ACK_LATENCY_MIN is not None


# --- clause 3: a 02 §2b transition on a RED visit raises an entry ---------------------------


class TestAVisitThatCarriesARedCannotSilentlyMove:
    @pytest.mark.parametrize(
        ("transition", "kind"),
        [
            (VisitTransition.RESCHEDULED, EntryKind.VISIT_RESCHEDULED),
            (VisitTransition.CANCELLED, EntryKind.VISIT_CANCELLED),
        ],
    )
    def test_a_transition_on_a_red_visit_raises_an_entry(
        self, transition: VisitTransition, kind: EntryKind
    ) -> None:
        rig = Rig()
        rig.answer(kirmizi_isaret=True)
        rig.flush()
        rig.wall.advance(timedelta(days=2))
        raised = rig.inbox.visit_transition(
            tenant_id=TENANT,
            visit_id=VISIT,
            transition=transition,
            transition_id=f"tr-{transition.value}-1",
            at=rig.wall(),
        )
        assert raised is not None
        assert raised.kind is kind
        assert raised.rule_ids == (RED_RULE.id,)
        assert raised.session_id == SESSION
        # the transition entry has its own clock, from the transition
        assert raised.created_at == rig.wall()
        kinds = sorted(entry.kind.value for entry in rig.store.open_entries())
        assert kinds == sorted({EntryKind.RED.value, kind.value})

    def test_the_transition_raises_an_entry_even_after_the_red_was_acknowledged(self) -> None:
        """files/02 §2b: *"A visit carrying an unresolved RED cannot silently
        move."* An acknowledgement is not a resolution — nothing in the tree
        records one — so an acknowledged RED still moves loudly."""
        rig = Rig()
        rig.answer(kirmizi_isaret=True)
        rig.flush()
        (red,) = rig.store.open_entries()
        rig.inbox.acknowledge(tenant_id=TENANT, entry_id=red.entry_id, by=ACKER, at=T0)
        raised = rig.inbox.visit_transition(
            tenant_id=TENANT,
            visit_id=VISIT,
            transition=VisitTransition.CANCELLED,
            transition_id="tr-cancel-1",
            at=T0 + timedelta(days=1),
        )
        assert raised is not None
        assert raised.is_open

    def test_a_replayed_transition_is_one_entry(self) -> None:
        rig = Rig()
        rig.answer(kirmizi_isaret=True)
        rig.flush()
        for _ in range(2):
            rig.inbox.visit_transition(
                tenant_id=TENANT,
                visit_id=VISIT,
                transition=VisitTransition.RESCHEDULED,
                transition_id="tr-once",
                at=T0,
            )
        assert len(rig.store.open_entries()) == 2  # the RED and one transition

    def test_a_visit_that_carried_only_a_yellow_moves_without_an_entry(self) -> None:
        rig = Rig()
        rig.answer(sari_isaret=True)
        rig.flush()
        raised = rig.inbox.visit_transition(
            tenant_id=TENANT,
            visit_id=VISIT,
            transition=VisitTransition.CANCELLED,
            transition_id="tr-yellow-1",
            at=T0,
        )
        assert raised is None
        assert rig.store.open_entries() == ()

    def test_another_visit_of_the_same_tenant_moves_without_an_entry(self) -> None:
        rig = Rig()
        rig.answer(kirmizi_isaret=True)
        rig.flush()
        raised = rig.inbox.visit_transition(
            tenant_id=TENANT,
            visit_id=OTHER_VISIT,
            transition=VisitTransition.RESCHEDULED,
            transition_id="tr-other-1",
            at=T0,
        )
        assert raised is None

    def test_the_same_visit_id_in_another_tenant_moves_without_an_entry(self) -> None:
        rig = Rig()
        rig.answer(kirmizi_isaret=True)
        rig.flush()
        raised = rig.inbox.visit_transition(
            tenant_id="tenant-b",
            visit_id=VISIT,
            transition=VisitTransition.CANCELLED,
            transition_id="tr-tenant-b-1",
            at=T0,
        )
        assert raised is None

    def test_a_transition_entry_pages_on_its_own_clock(self) -> None:
        rig = Rig()
        rig.answer(kirmizi_isaret=True)
        rig.flush()
        (red,) = rig.store.open_entries()
        rig.inbox.acknowledge(tenant_id=TENANT, entry_id=red.entry_id, by=ACKER, at=T0)
        moved_at = T0 + timedelta(days=3)
        rig.inbox.visit_transition(
            tenant_id=TENANT,
            visit_id=VISIT,
            transition=VisitTransition.RESCHEDULED,
            transition_id="tr-late-1",
            at=moved_at,
        )
        assert rig.inbox.sweep(moved_at + DEFAULT_ACK_SLA).breaches == ()
        (breach,) = rig.inbox.sweep(moved_at + DEFAULT_ACK_SLA + timedelta(seconds=1)).breaches
        assert breach.kind is EntryKind.VISIT_RESCHEDULED


# --- clause 4: the two metrics are catalogued, alerted and runbooked -----------------------


def _alerts() -> dict[str, dict[str, Any]]:
    payload = yaml.safe_load(RULES_FILE.read_text(encoding="utf-8"))
    return {
        rule["alert"]: rule
        for group in payload["groups"]
        for rule in group["rules"]
        if "alert" in rule
    }


class TestTheSignalsArePaged:
    def test_both_spec_metrics_and_the_pending_age_are_live_in_the_catalogue(self) -> None:
        catalog = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
        entries = {metric["name"]: metric for metric in catalog["metrics"]}
        for name in (
            "clinic_red_ack_latency_min",
            "clinic_red_unacknowledged_total",
            "clinic_red_inbox_pending_age_s",
        ):
            assert entries[name].get("status", "live") == "live", name
        assert entries["clinic_red_unacknowledged_total"]["labels"] == ["tenant", "age_band"]

    def test_unacknowledged_past_the_sla_pages(self) -> None:
        rule = _alerts()["RedAcknowledgementOverdue"]
        assert rule["labels"]["severity"] == "page"
        assert "clinic_red_unacknowledged_total" in rule["expr"]
        assert f'age_band="{AgeBand.PAST_SLA.value}"' in rule["expr"]
        assert "for" not in rule, "the SLA already is the grace period"

    def test_an_entry_that_missed_the_sixty_seconds_pages(self) -> None:
        rule = _alerts()["RedInboxEntryLate"]
        assert rule["labels"]["severity"] == "page"
        assert "clinic_red_inbox_pending_age_s" in rule["expr"]
        assert f"> {int(INBOX_ENTRY_BUDGET.total_seconds())}" in rule["expr"]

    def test_every_alert_links_an_anchor_that_exists(self) -> None:
        text = RUNBOOK.read_text(encoding="utf-8")
        anchors = {
            line.lstrip("#").strip().lower().replace(" ", "-")
            for line in text.splitlines()
            if line.startswith("#")
        }
        for rule in _alerts().values():
            path, _, anchor = rule["annotations"]["runbook"].partition("#")
            assert path == "docs/runbooks/red-acknowledgement.md"
            assert anchor in anchors, anchor

    def test_prometheus_loads_the_rules(self) -> None:
        config = yaml.safe_load(PROMETHEUS_CONFIG.read_text(encoding="utf-8"))
        assert "/etc/prometheus/rules/safety-rules.yaml" in config["rule_files"]
        compose = OBS_COMPOSE.read_text(encoding="utf-8")
        assert (
            "./observability/safety-rules.yaml:/etc/prometheus/rules/safety-rules.yaml:ro"
            in compose
        )

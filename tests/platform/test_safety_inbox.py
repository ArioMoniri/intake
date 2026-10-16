"""INT-406 — the Safety inbox's parts: the entry, the store, the outbox, the sweep.

tests/safety/test_red_acknowledgement_sla.py holds invariant 49 end to end;
this suite holds each part to its own contract, so a regression names the part
rather than the invariant. The store is the production Redis implementation
over ``fakeredis``. Every id is synthetic.
"""

from __future__ import annotations

import asyncio
import logging
import math
import threading
from datetime import UTC, datetime, timedelta

import fakeredis
import pytest
from intake_platform.safety_inbox import (
    DEFAULT_ACK_SLA,
    ENV_SAFETY_INBOX_REDIS_URL,
    SWEEP_INTERVAL,
    UNREADABLE_TENANT,
    AckSlaPolicy,
    AgeBand,
    AlreadyAcknowledged,
    EntryKind,
    EntryNotFound,
    InboxEntry,
    RedisSafetyInboxStore,
    SafetyInbox,
    SafetyInboxOutbox,
    SafetyInboxUnavailable,
    VisitTransition,
    entry_id_for,
    mark_inbox_unreadable,
    safety_inbox_store_from_env,
    sweep_forever,
)
from intake_platform.safety_inbox.metrics import CLINIC_RED_UNACKNOWLEDGED_TOTAL
from intake_platform.safety_inbox.store import KEY_PREFIX
from prometheus_client import REGISTRY
from pydantic import ValidationError

T0 = datetime(2026, 9, 27, 9, 0, tzinfo=UTC)
TENANT = "tenant-a"
SESSION = "11111111-2222-4333-8444-555555555555"
RULE = "rf.sentetik_kirmizi"
ACKER = "kc-sub-tenant-clinical-responsible"


def _red(
    *,
    tenant_id: str = TENANT,
    work_id: str = "w_red",
    visit_id: str = SESSION,
    at: datetime = T0,
) -> InboxEntry:
    return InboxEntry.for_red(
        tenant_id=tenant_id,
        session_id=SESSION,
        visit_id=visit_id,
        work_id=work_id,
        rule_ids=(RULE,),
        at=at,
    )


def _store() -> RedisSafetyInboxStore:
    return RedisSafetyInboxStore(fakeredis.FakeStrictRedis())


def _down_store() -> RedisSafetyInboxStore:
    server = fakeredis.FakeServer()
    server.connected = False
    return RedisSafetyInboxStore(fakeredis.FakeStrictRedis(server=server))


@pytest.fixture(autouse=True)
def _fresh_gauge() -> None:
    CLINIC_RED_UNACKNOWLEDGED_TOTAL.clear()


class TestTheEntry:
    def test_the_entry_id_is_derived_from_tenant_kind_and_source(self) -> None:
        entry = _red()
        assert entry.entry_id == entry_id_for(TENANT, EntryKind.RED, "w_red")
        assert entry.entry_id != _red(tenant_id="tenant-b").entry_id
        assert entry.entry_id != _red(work_id="w_other").entry_id
        assert entry.entry_id.startswith("sx_")

    @pytest.mark.parametrize(
        "field",
        ["tenant_id", "session_id", "visit_id", "work_id"],
    )
    def test_ids_are_ids_never_prose(self, field: str) -> None:
        arguments: dict[str, object] = {
            "tenant_id": TENANT,
            "session_id": SESSION,
            "visit_id": SESSION,
            "work_id": "w_red",
            "rule_ids": (RULE,),
            "at": T0,
        }
        arguments[field] = "göğüs ağrısı var"
        with pytest.raises((ValidationError, ValueError)):
            InboxEntry.for_red(**arguments)  # type: ignore[arg-type]

    def test_a_rule_id_that_is_not_an_id_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            InboxEntry.for_red(
                tenant_id=TENANT,
                session_id=SESSION,
                visit_id=SESSION,
                work_id="w_red",
                rule_ids=("Hasta nefes alamıyor",),
                at=T0,
            )

    def test_an_entry_names_at_least_one_rule(self) -> None:
        with pytest.raises(ValidationError):
            InboxEntry.for_red(
                tenant_id=TENANT,
                session_id=SESSION,
                visit_id=SESSION,
                work_id="w_red",
                rule_ids=(),
                at=T0,
            )

    def test_a_naive_timestamp_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="aware"):
            _red(at=datetime(2026, 9, 27, 9, 0))  # noqa: DTZ001 - the refusal under test

    def test_an_entry_is_forged_neither_by_id_nor_by_half_an_acknowledgement(self) -> None:
        payload = _red().model_dump()
        with pytest.raises(ValidationError, match="entry_id"):
            InboxEntry.model_validate({**payload, "entry_id": "sx_" + "0" * 32})
        with pytest.raises(ValidationError, match="acknowledg"):
            InboxEntry.model_validate({**payload, "acknowledged_by": ACKER})

    def test_acknowledging_twice_or_before_the_entry_is_refused(self) -> None:
        entry = _red()
        acked = entry.acknowledge(by=ACKER, at=T0 + timedelta(minutes=5))
        assert not acked.is_open
        with pytest.raises(AlreadyAcknowledged):
            acked.acknowledge(by=ACKER, at=T0 + timedelta(minutes=6))
        with pytest.raises(ValueError, match="before"):
            entry.acknowledge(by=ACKER, at=T0 - timedelta(seconds=1))

    def test_a_visit_transition_maps_to_its_kind(self) -> None:
        assert VisitTransition.RESCHEDULED.kind is EntryKind.VISIT_RESCHEDULED
        assert VisitTransition.CANCELLED.kind is EntryKind.VISIT_CANCELLED


def _on_site(*, work_id: str = "w_red", at: datetime = T0) -> InboxEntry:
    return InboxEntry.for_on_site(
        tenant_id=TENANT,
        session_id=SESSION,
        visit_id=SESSION,
        work_id=work_id,
        rule_ids=(RULE,),
        at=at,
    )


class TestTheOnSiteStaffNotification:
    """INT-475: files/02 §5.3 Axis 3 and files/04 §8.1 rule 7 — under ON_SITE the
    clinic notification is the primary channel and fires automatically. It is its
    own entry kind with its own clock, one per RED, carrying ids only."""

    def test_one_per_red_and_never_the_red_entry_itself(self) -> None:
        entry = _on_site()
        assert entry.kind is EntryKind.RED_ON_SITE
        assert entry.source_ref == "w_red"
        assert entry.entry_id == entry_id_for(TENANT, EntryKind.RED_ON_SITE, "w_red")
        # Near miss: the RED entry of the same RED is a different entry.
        assert entry.entry_id != _red().entry_id
        assert entry.entry_id != _on_site(work_id="w_other").entry_id

    def test_it_records_no_register_and_no_prose(self) -> None:
        with pytest.raises(ValidationError, match="register"):
            InboxEntry.model_validate({**_on_site().model_dump(), "register": "ALERT"})
        with pytest.raises((ValidationError, ValueError)):
            InboxEntry.for_on_site(
                tenant_id=TENANT,
                session_id=SESSION,
                visit_id="hastanın adı",
                work_id="w_red",
                rule_ids=(RULE,),
                at=T0,
            )

    def test_the_store_keeps_one_and_it_does_not_index_the_visit(self) -> None:
        store = _store()
        red = store.add(_red())
        first = store.add(_on_site(at=T0))
        assert store.add(_on_site(at=T0 + timedelta(minutes=1))) == first
        assert {entry.kind for entry in store.open_entries()} == {
            EntryKind.RED,
            EntryKind.RED_ON_SITE,
        }
        # files/02 §2b reads the visit's REDs; the staff notification is not one
        assert store.red_entries_for_visit(TENANT, SESSION) == (red,)


class TestThePolicy:
    def test_band_and_deadline(self) -> None:
        policy = AckSlaPolicy()
        entry = _red()
        assert policy.deadline(entry) == T0 + DEFAULT_ACK_SLA
        assert policy.band(entry, T0 + DEFAULT_ACK_SLA) is AgeBand.WITHIN_SLA
        assert policy.band(entry, T0 + DEFAULT_ACK_SLA + timedelta(microseconds=1)) is (
            AgeBand.PAST_SLA
        )

    def test_a_tenant_override_needs_an_id_shaped_tenant(self) -> None:
        with pytest.raises(ValueError):
            AckSlaPolicy(per_tenant={"Not A Tenant": timedelta(hours=1)})


class TestTheRedisStore:
    def test_add_is_idempotent_and_first_write_wins(self) -> None:
        store = _store()
        first = store.add(_red(at=T0))
        replay = store.add(_red(at=T0 + timedelta(minutes=1)))
        assert replay == first
        assert store.open_entries() == (first,)
        assert store.tenant_entries(TENANT) == (first,)

    def test_get_is_scoped_to_the_tenant(self) -> None:
        store = _store()
        entry = store.add(_red())
        assert store.get(TENANT, entry.entry_id) == entry
        assert store.get("tenant-b", entry.entry_id) is None

    def test_acknowledge_closes_the_entry_once(self) -> None:
        store = _store()
        entry = store.add(_red())
        acked = store.acknowledge(TENANT, entry.entry_id, by=ACKER, at=T0 + timedelta(minutes=3))
        assert acked.acknowledged_by == ACKER
        assert store.open_entries() == ()
        assert store.tenant_entries(TENANT) == (acked,)
        with pytest.raises(AlreadyAcknowledged):
            store.acknowledge(TENANT, entry.entry_id, by=ACKER, at=T0 + timedelta(minutes=4))

    def test_acknowledging_another_tenants_entry_is_not_found(self) -> None:
        store = _store()
        entry = store.add(_red())
        with pytest.raises(EntryNotFound):
            store.acknowledge("tenant-b", entry.entry_id, by=ACKER, at=T0)
        assert store.open_entries() == (entry,)

    def test_open_entries_are_oldest_first_across_tenants(self) -> None:
        store = _store()
        late = store.add(_red(work_id="w_late", at=T0 + timedelta(minutes=2)))
        early = store.add(_red(tenant_id="tenant-b", work_id="w_early", at=T0))
        assert store.open_entries() == (early, late)

    def test_only_red_entries_index_the_visit(self) -> None:
        store = _store()
        red = store.add(_red())
        store.add(
            InboxEntry.for_visit_transition(
                tenant_id=TENANT,
                session_id=SESSION,
                visit_id=SESSION,
                transition=VisitTransition.CANCELLED,
                transition_id="tr-1",
                rule_ids=(RULE,),
                at=T0,
            )
        )
        assert store.red_entries_for_visit(TENANT, SESSION) == (red,)
        assert store.red_entries_for_visit("tenant-b", SESSION) == ()

    def test_a_record_that_is_not_an_entry_is_unavailable_never_skipped(self) -> None:
        client = fakeredis.FakeStrictRedis()
        store = RedisSafetyInboxStore(client)
        entry = store.add(_red())
        client.set(f"{KEY_PREFIX}entry:{TENANT}:{entry.entry_id}", b"not json")
        with pytest.raises(SafetyInboxUnavailable) as raised:
            store.open_entries()
        assert raised.value.code == "safety_inbox_malformed"

    def test_a_record_filed_under_the_wrong_key_is_malformed(self) -> None:
        client = fakeredis.FakeStrictRedis()
        store = RedisSafetyInboxStore(client)
        entry = store.add(_red())
        other = _red(work_id="w_other")
        client.set(f"{KEY_PREFIX}entry:{TENANT}:{entry.entry_id}", other.model_dump_json())
        with pytest.raises(SafetyInboxUnavailable):
            store.get(TENANT, entry.entry_id)

    def test_an_unreachable_server_is_unavailable(self) -> None:
        store = _down_store()
        for call in (
            lambda: store.add(_red()),
            lambda: store.get(TENANT, "sx_" + "0" * 32),
            lambda: store.open_entries(),
            lambda: store.tenant_entries(TENANT),
            lambda: store.red_entries_for_visit(TENANT, SESSION),
            lambda: store.acknowledge(TENANT, "sx_" + "0" * 32, by=ACKER, at=T0),
        ):
            with pytest.raises(SafetyInboxUnavailable) as raised:
                call()
            assert raised.value.code == "safety_inbox_unreachable"

    def test_the_store_comes_from_the_environment_or_not_at_all(self) -> None:
        assert safety_inbox_store_from_env({}) is None
        assert safety_inbox_store_from_env({ENV_SAFETY_INBOX_REDIS_URL: "  "}) is None
        with pytest.raises(ValueError, match="redis"):
            safety_inbox_store_from_env({ENV_SAFETY_INBOX_REDIS_URL: "http://example.invalid"})
        store = safety_inbox_store_from_env(
            {ENV_SAFETY_INBOX_REDIS_URL: "redis://localhost:6379/0"}
        )
        assert isinstance(store, RedisSafetyInboxStore)


class TestTheOutbox:
    def test_flush_keeps_order_and_what_it_could_not_write(self) -> None:
        clock_at = [T0]
        outbox = SafetyInboxOutbox(clock=lambda: clock_at[0])
        first, second = _red(work_id="w_1"), _red(work_id="w_2", at=T0 + timedelta(seconds=1))
        outbox.put(first)
        outbox.put(second)
        report = outbox.flush(_down_store())
        assert report.pending == 2
        assert outbox.pending() == (first, second)
        clock_at[0] = T0 + timedelta(seconds=30)
        assert outbox.oldest_pending_age_s() == 30.0
        store = _store()
        report = outbox.flush(store)
        assert report.written == (first.entry_id, second.entry_id)
        assert outbox.pending() == ()
        assert outbox.oldest_pending_age_s() == 0.0

    def test_waiting_for_an_empty_outbox_times_out_honestly(self) -> None:
        outbox = SafetyInboxOutbox(clock=lambda: T0)
        assert outbox.wait_until_empty(timeout=0.0)
        outbox.put(_red())
        assert not outbox.wait_until_empty(timeout=0.0)

    def test_an_entry_being_written_is_still_waiting(self) -> None:
        """INT-475: a flush takes the batch out before it writes; until the write
        lands the entry is still waiting — it counts in ``pending``, in the age that
        pages, and ``wait_until_empty`` does not return early (a drain on shutdown
        would otherwise stop with the write half done)."""
        entered, release = threading.Event(), threading.Event()

        class SlowStore:
            def __init__(self) -> None:
                self.inner = _store()

            def add(self, entry: InboxEntry) -> InboxEntry:
                entered.set()
                assert release.wait(timeout=5.0)
                return self.inner.add(entry)

        clock_at = [T0]
        outbox = SafetyInboxOutbox(clock=lambda: clock_at[0])
        entry = _red()
        outbox.put(entry)
        slow = SlowStore()
        writer = threading.Thread(target=outbox.flush, args=(slow,))
        writer.start()
        assert entered.wait(timeout=5.0)
        clock_at[0] = T0 + timedelta(seconds=7)
        assert outbox.pending() == (entry,)
        assert outbox.oldest_pending_age_s() == 7.0
        assert not outbox.wait_until_empty(timeout=0.05)
        release.set()
        assert outbox.wait_until_empty(timeout=5.0)
        writer.join(timeout=5.0)
        assert slow.inner.open_entries() == (entry,)
        assert outbox.pending() == ()

    def test_an_unexpected_store_fault_keeps_the_entry_and_the_pump_alive(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """INT-475: only ``SafetyInboxUnavailable`` was kept before; any other fault
        killed the pump and dropped the batch it had taken, with nothing paging."""

        class FaultyStore:
            def add(self, entry: InboxEntry) -> InboxEntry:
                raise RuntimeError("sentetik store arızası")

        outbox = SafetyInboxOutbox(clock=lambda: T0)
        entry = _red()
        outbox.put(entry)
        with caplog.at_level(logging.ERROR):
            report = outbox.flush(FaultyStore())  # type: ignore[arg-type]
        assert report.written == ()
        assert outbox.pending() == (entry,)
        assert "safety inbox write failed" in caplog.text
        assert "sentetik store arızası" not in caplog.text
        # Near miss: the next pass with a working store writes it.
        store = _store()
        assert outbox.flush(store).written == (entry.entry_id,)
        assert store.open_entries() == (entry,)


class TestTheInbox:
    def test_the_queue_puts_the_unanswered_first(self) -> None:
        store = _store()
        inbox = SafetyInbox(store=store)
        answered = store.add(_red(work_id="w_answered", at=T0))
        inbox.acknowledge(tenant_id=TENANT, entry_id=answered.entry_id, by=ACKER, at=T0)
        waiting = store.add(_red(work_id="w_waiting", at=T0 + timedelta(minutes=1)))
        rows = inbox.queue(TENANT, now=T0 + DEFAULT_ACK_SLA + timedelta(minutes=2))
        assert [row.entry.entry_id for row in rows] == [waiting.entry_id, answered.entry_id]
        assert rows[0].band is AgeBand.PAST_SLA
        assert rows[0].sla == DEFAULT_ACK_SLA
        assert rows[1].band is None

    def test_the_queue_across_all_tenants(self) -> None:
        store = _store()
        inbox = SafetyInbox(store=store)
        store.add(_red())
        store.add(_red(tenant_id="tenant-b", work_id="w_b"))
        assert len(inbox.queue(None, now=T0)) == 2

    def test_mark_unreadable_pages(self) -> None:
        mark_inbox_unreadable()
        value = REGISTRY.get_sample_value(
            "clinic_red_unacknowledged_total",
            {"tenant": UNREADABLE_TENANT, "age_band": AgeBand.PAST_SLA.value},
        )
        assert value is not None and math.isinf(value)

    def test_the_sweep_loop_survives_a_fault_and_pages_it(self) -> None:
        inbox = SafetyInbox(store=_store())
        calls = {"n": 0}

        class _Stop(BaseException):
            """Ends the loop from inside, the way a task cancellation would."""

        def sweep(now: datetime) -> object:
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("synthetic fault")
            raise _Stop

        inbox.sweep = sweep  # type: ignore[method-assign]
        slept: list[float] = []

        async def sleep(seconds: float) -> None:
            slept.append(seconds)

        with pytest.raises(_Stop):
            asyncio.run(sweep_forever(inbox, clock=lambda: T0, sleep=sleep))
        # the fault paged and the loop went round again rather than ending
        assert calls["n"] == 2
        assert slept == [SWEEP_INTERVAL.total_seconds()]
        value = REGISTRY.get_sample_value(
            "clinic_red_unacknowledged_total",
            {"tenant": UNREADABLE_TENANT, "age_band": AgeBand.PAST_SLA.value},
        )
        assert value is not None and math.isinf(value)

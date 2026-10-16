"""INT-547 and INT-525 — CD-08's chest-pain items in the clinic inbox, and no SLA invented.

CD-04 and CD-01 raise clinician-only items that CD-08 routes to the booked
clinic's inbox: ``chest_pain_arms_unresolved`` and (INT-525)
``proxy_chest_pain_screen_unasked``. They travel the clinic Safety inbox the
RED route already writes (INT-406, INT-475) — the same entry shape, the same
store, the same console queue — and they are not REDs:

1. Each item is its own entry kind, its id derived from tenant, kind and the
   item's own reference, so raising it twice is one entry (once per session).
   Ids only (invariant 6), no register, never a RED and never on a visit's RED
   index (files/02 §2b reads REDs only).
2. CD-08 leaves the acknowledgement SLA ``draft_needs_source``. The inbox
   states none for these kinds: no deadline, no age band, no breach and no
   ``clinic_red_unacknowledged_total`` series; the console row shows no SLA.
   Near miss: a RED entry of the same age still breaches the RED SLA.
3. Acknowledging one records who and when, like any entry, and is not a RED
   acknowledgement, so the RED latency histogram is not fed.

The store is the production Redis implementation over ``fakeredis``. Every id
is synthetic.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import fakeredis
import pytest
from intake_platform.safety_inbox import (
    CLINIC_ITEM_KINDS,
    DEFAULT_ACK_SLA,
    AckSlaPolicy,
    AgeBand,
    EntryKind,
    InboxEntry,
    RedisSafetyInboxStore,
    SafetyInbox,
    VisitTransition,
    entry_id_for,
)
from intake_platform.safety_inbox.metrics import CLINIC_RED_UNACKNOWLEDGED_TOTAL
from prometheus_client import REGISTRY
from protocols.clinic_items import ClinicItemKind
from pydantic import ValidationError

T0 = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)
TENANT = "tenant-a"
SESSION = "11111111-2222-4333-8444-555555555555"
ITEM_REF = "ci_" + "a" * 32
RULES = ("rf.chest_pain_cardiac_features", "rf.chest_pain_no_cardiac_history")
ACKER = "kc-sub-tenant-clinical-responsible"
#: INT-553 F9: the slot the item is about and the decisions that raise it.
SLOTS = ("chest_pain.character",)
DECISIONS = ("CD-04", "CD-08")
WELL_PAST = DEFAULT_ACK_SLA * 3


def _item(
    kind: EntryKind = EntryKind.CHEST_PAIN_ARMS_UNRESOLVED,
    *,
    item_ref: str = ITEM_REF,
    at: datetime = T0,
) -> InboxEntry:
    return InboxEntry.for_clinic_item(
        tenant_id=TENANT,
        session_id=SESSION,
        visit_id=SESSION,
        kind=kind,
        item_ref=item_ref,
        rule_ids=RULES,
        slot_refs=SLOTS,
        decision_ids=DECISIONS,
        at=at,
    )


def _red(at: datetime = T0) -> InboxEntry:
    return InboxEntry.for_red(
        tenant_id=TENANT,
        session_id=SESSION,
        visit_id=SESSION,
        work_id="w_red",
        rule_ids=(RULES[0],),
        at=at,
    )


def _inbox() -> SafetyInbox:
    return SafetyInbox(store=RedisSafetyInboxStore(fakeredis.FakeStrictRedis()))


def _past_sla_series() -> float:
    value = REGISTRY.get_sample_value(
        "clinic_red_unacknowledged_total",
        {"tenant": TENANT, "age_band": AgeBand.PAST_SLA.value},
    )
    return value or 0.0


@pytest.fixture(autouse=True)
def _fresh_gauge() -> None:
    CLINIC_RED_UNACKNOWLEDGED_TOTAL.clear()


# --- 1 · CD-08's own names, never a RED -------------------------------------------------------


def test_the_item_kinds_are_cd08s_names_and_only_they_are_clinic_items() -> None:
    assert {kind.value for kind in CLINIC_ITEM_KINDS} == {kind.value for kind in ClinicItemKind}
    assert CLINIC_ITEM_KINDS == {
        EntryKind.CHEST_PAIN_ARMS_UNRESOLVED,
        EntryKind.PROXY_CHEST_PAIN_SCREEN_UNASKED,  # INT-525
    }
    for kind in EntryKind:
        assert kind.is_clinic_item is (kind in CLINIC_ITEM_KINDS)
    assert not EntryKind.RED.is_clinic_item and not EntryKind.RED_ON_SITE.is_clinic_item


@pytest.mark.parametrize("kind", sorted(CLINIC_ITEM_KINDS))
def test_an_item_entry_is_derived_from_tenant_kind_and_its_own_reference(kind: EntryKind) -> None:
    entry = _item(kind)
    assert entry.kind is kind
    assert entry.source_ref == ITEM_REF
    assert entry.entry_id == entry_id_for(TENANT, kind, ITEM_REF)
    assert entry.rule_ids == RULES
    assert entry.register is None
    assert entry.created_at == T0 and entry.is_open


def test_another_reference_is_another_entry() -> None:
    assert _item().entry_id != _item(item_ref="ci_" + "c" * 32).entry_id


def test_the_two_kinds_for_one_reference_are_two_entries() -> None:
    """INT-525: the proxy item is its own entry, beside the arms item."""
    assert (
        _item(EntryKind.CHEST_PAIN_ARMS_UNRESOLVED).entry_id
        != _item(EntryKind.PROXY_CHEST_PAIN_SCREEN_UNASKED).entry_id
    )


@pytest.mark.parametrize(
    "kind",
    [EntryKind.RED, EntryKind.RED_ON_SITE, EntryKind.VISIT_RESCHEDULED, EntryKind.VISIT_CANCELLED],
)
def test_a_red_family_kind_is_never_raised_as_a_clinic_item(kind: EntryKind) -> None:
    with pytest.raises(ValueError, match="clinic item"):
        _item(kind)


def test_an_item_records_no_register() -> None:
    entry = _item()
    with pytest.raises(ValidationError):
        InboxEntry.model_validate({**entry.model_dump(), "register": "ALERT"})


@pytest.mark.parametrize(
    ("field", "prose"),
    [
        ("item_ref", "göğüs ağrısı belirsiz"),
        ("session_id", "Ayşe Yılmaz"),
        ("slot_refs", "göğsümde baskı var"),
        ("decision_ids", "Kardiyoloji kararı"),
    ],
)
def test_ids_are_ids_never_prose(field: str, prose: str) -> None:
    with pytest.raises((ValueError, ValidationError)) as raised:
        InboxEntry.for_clinic_item(
            tenant_id=TENANT,
            session_id=prose if field == "session_id" else SESSION,
            visit_id=SESSION,
            kind=EntryKind.CHEST_PAIN_ARMS_UNRESOLVED,
            item_ref=prose if field == "item_ref" else ITEM_REF,
            rule_ids=RULES,
            slot_refs=(prose,) if field == "slot_refs" else SLOTS,
            decision_ids=(prose,) if field == "decision_ids" else DECISIONS,
            at=T0,
        )
    assert prose not in str(raised.value)


# --- 1b · the entry keeps the item's slots and decisions (INT-553 F9) ----------------------


@pytest.mark.parametrize("kind", sorted(CLINIC_ITEM_KINDS))
def test_an_item_entry_keeps_which_slot_and_which_decisions(kind: EntryKind) -> None:
    """The clinician reading the queue sees which chest-pain slot was left
    unresolved or unasked and which decisions raised it — protocol ids only."""
    entry = _item(kind)
    assert (entry.slot_refs, entry.decision_ids) == (SLOTS, DECISIONS)
    again = _inbox().store.add(entry)
    assert (again.slot_refs, again.decision_ids) == (SLOTS, DECISIONS)


@pytest.mark.parametrize("field", ["slot_refs", "decision_ids"])
def test_an_item_entry_without_its_slots_or_decisions_is_refused(field: str) -> None:
    with pytest.raises(ValidationError, match=field):
        InboxEntry.model_validate({**_item().model_dump(), field: ()})


@pytest.mark.parametrize("field", ["slot_refs", "decision_ids"])
def test_near_miss_a_red_entry_carries_no_slots_and_no_decisions(field: str) -> None:
    red = _red()
    assert (red.slot_refs, red.decision_ids) == ((), ())
    with pytest.raises(ValidationError, match="clinic item"):
        InboxEntry.model_validate({**red.model_dump(), field: _item().model_dump()[field]})


def test_the_store_keeps_one_entry_per_item_and_never_indexes_the_visit() -> None:
    inbox = _inbox()
    first = inbox.store.add(_item())
    again = inbox.store.add(_item(at=T0 + timedelta(minutes=5)))
    assert again == first  # first write wins: the clock started at the first raise
    assert inbox.store.red_entries_for_visit(TENANT, SESSION) == ()


def test_a_visit_carrying_only_a_clinic_item_raises_no_transition_entry() -> None:
    """files/02 §2b is a RED rule. Near miss of INT-406's own transition test."""
    inbox = _inbox()
    inbox.store.add(_item())
    raised = inbox.visit_transition(
        tenant_id=TENANT,
        visit_id=SESSION,
        transition=VisitTransition.RESCHEDULED,
        transition_id="tr_1",
        at=T0 + timedelta(hours=1),
    )
    assert raised is None


# --- 2 · no SLA invented: CD-08 leaves it draft ------------------------------------------------


@pytest.mark.parametrize("kind", sorted(CLINIC_ITEM_KINDS))
def test_an_item_has_no_sla_no_deadline_and_no_age_band(kind: EntryKind) -> None:
    policy = AckSlaPolicy()
    entry = _item(kind)
    assert policy.sla_for_entry(entry) is None
    assert policy.deadline(entry) is None
    assert policy.band(entry, T0 + WELL_PAST) is None


def test_near_miss_a_red_keeps_the_red_sla() -> None:
    policy = AckSlaPolicy()
    red = _red()
    assert policy.sla_for_entry(red) == DEFAULT_ACK_SLA
    assert policy.deadline(red) == T0 + DEFAULT_ACK_SLA
    assert policy.band(red, T0 + WELL_PAST) is AgeBand.PAST_SLA


def test_an_open_item_well_past_four_hours_neither_breaches_nor_counts_as_a_red() -> None:
    inbox = _inbox()
    inbox.store.add(_item())
    report = inbox.sweep(T0 + WELL_PAST)
    assert report.readable and report.breaches == ()
    assert _past_sla_series() == 0.0


def test_near_miss_a_red_of_the_same_age_beside_it_breaches() -> None:
    inbox = _inbox()
    inbox.store.add(_item())
    inbox.store.add(_red())
    report = inbox.sweep(T0 + WELL_PAST)
    assert [breach.kind for breach in report.breaches] == [EntryKind.RED]
    assert _past_sla_series() == 1.0


def test_the_console_row_shows_the_item_with_no_sla_and_no_band() -> None:
    inbox = _inbox()
    inbox.store.add(_item())
    inbox.store.add(_red())
    rows = {row.entry.kind: row for row in inbox.queue(TENANT, T0 + timedelta(hours=1))}
    item_row = rows[EntryKind.CHEST_PAIN_ARMS_UNRESOLVED]
    assert item_row.sla is None and item_row.band is None
    assert item_row.elapsed == timedelta(hours=1)
    assert rows[EntryKind.RED].sla == DEFAULT_ACK_SLA  # near miss
    assert rows[EntryKind.RED].band is AgeBand.WITHIN_SLA


# --- 2b · unacknowledged REDs first (files/08 §3; INT-553 F3) ---------------------------------


def _on_site(at: datetime) -> InboxEntry:
    return InboxEntry.for_on_site(
        tenant_id=TENANT,
        session_id=SESSION,
        visit_id=SESSION,
        work_id="w_on_site",
        rule_ids=(RULES[0],),
        at=at,
    )


def test_an_open_red_is_shown_above_an_older_open_item() -> None:
    """Items never auto-clear and have no SLA, so oldest-first would pile them
    above every newer RED. files/08 §3: "unacknowledged REDs first"."""
    inbox = _inbox()
    item = inbox.store.add(_item(at=T0))
    red = inbox.store.add(_red(at=T0 + timedelta(hours=2)))
    on_site = inbox.store.add(_on_site(at=T0 + timedelta(hours=3)))
    rows = inbox.queue(TENANT, T0 + timedelta(hours=4))
    assert [row.entry.entry_id for row in rows] == [red.entry_id, on_site.entry_id, item.entry_id]


def test_near_miss_open_items_beside_no_red_stay_oldest_first() -> None:
    inbox = _inbox()
    newer = inbox.store.add(_item(EntryKind.PROXY_CHEST_PAIN_SCREEN_UNASKED, at=T0))
    older = inbox.store.add(_item(item_ref="ci_" + "c" * 32, at=T0 - timedelta(hours=1)))
    rows = inbox.queue(TENANT, T0 + timedelta(hours=1))
    assert [row.entry.entry_id for row in rows] == [older.entry_id, newer.entry_id]


def test_near_miss_an_answered_red_goes_below_an_open_item() -> None:
    inbox = _inbox()
    red = inbox.store.add(_red(at=T0 + timedelta(hours=1)))
    inbox.acknowledge(tenant_id=TENANT, entry_id=red.entry_id, by=ACKER, at=T0 + timedelta(hours=2))
    item = inbox.store.add(_item(at=T0))
    rows = inbox.queue(TENANT, T0 + timedelta(hours=3))
    assert [row.entry.entry_id for row in rows] == [item.entry_id, red.entry_id]


# --- 3 · acknowledged like any entry, not as a RED ---------------------------------------------


def _latency_count() -> float:
    return REGISTRY.get_sample_value("clinic_red_ack_latency_min_count") or 0.0


def test_acknowledging_an_item_records_who_and_when_and_is_not_a_red_latency() -> None:
    inbox = _inbox()
    entry = inbox.store.add(_item())
    before = _latency_count()
    acked = inbox.acknowledge(
        tenant_id=TENANT, entry_id=entry.entry_id, by=ACKER, at=T0 + timedelta(minutes=30)
    )
    assert (acked.acknowledged_by, acked.acknowledged_at) == (ACKER, T0 + timedelta(minutes=30))
    assert _latency_count() == before


def test_near_miss_acknowledging_a_red_still_feeds_the_red_latency() -> None:
    inbox = _inbox()
    entry = inbox.store.add(_red())
    before = _latency_count()
    inbox.acknowledge(
        tenant_id=TENANT, entry_id=entry.entry_id, by=ACKER, at=T0 + timedelta(minutes=30)
    )
    assert _latency_count() == before + 1

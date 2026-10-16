"""INT-553 — a CD-08 clinic item can never delay or skip a triage evaluation.

GitHub #937, from the clinical review of #931 (INT-547) and #932 (INT-525).
The CD-08 chest-pain items are clinician-only notices raised from the live
session. Before this issue the watch that raised them ran *inside* the state
handler, so:

- **F1.** A fault in the watch (an item it could not build, an engine read
  that raised) was a handler fault: the Work failed, the rules engine never
  ran over the answer it had bound, and no evaluation was owed — a K2-firing
  answer in that Work went unevaluated.
- **F2.** The item's audit row — a database INSERT in production — was
  written on the state lane before the same Work's determination, so a slow
  audit store delayed a K2 RED by exactly as long as it was slow, and the
  ``evaluated_at_ms`` budgets, measured from the determination, could not see
  the delay. ``AuditChain`` itself had no lock.

What this suite holds, on both profiles, over the committed ``base.intake`` and
``base.life_threat``:

1. The watch is not the handler: the queue looks before the handler and again
   only once the Work has settled — after the determination, the clinician
   route and the RED push. A watch that raises is counted
   (``work_watch_faults_total{step}``) and logged by ids, the Work completes,
   its evaluation runs, and K2 reaches the device inside the 300 ms budget.
2. A session id the item could not carry is refused at composition.
3. The audit row is queued, never written on the state lane: a five-second
   audit write leaves the K2 determination where it was, and the row lands
   when the audit worker runs. The audit outbox is bounded and never waits;
   a row it cannot take, or the chain refuses, is counted as unaudited.
4. ``AnswerState`` is pinned and sorted whole into unasked and asked, so
   ADR-040's ``NOT_ASKED_PROXY`` cannot arrive unsorted (F4); the screen's
   ``skip_if`` must compare CD-01's own reading to CD-01's own literal (F8).

The gateway is a table keyed by what the patient said; nothing dials a model.
The transcripts are synthetic (files/04 §7).
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any

import pytest
import test_clinic_items as int547
import test_extraction_valuesets as int518
import test_live_triage as int521
import test_onset_anchor as int522
import test_red_between_turns as int531
from clinic_item_harness import RecordingClinicItems
from clinical_schemas.session import AnswerState
from clinical_schemas.triage import RedLocation, TriageLevel
from intake_platform.audit import GENESIS_PREV_HASH, AuditChain, AuditEntry, InMemoryAuditStore
from intake_platform.safety_inbox import EntryKind, SafetyInboxOutbox
from intake_voice_runtime import safety_inbox as inbox_module
from intake_voice_runtime.clinical_agent import clinic_items as watch_module
from intake_voice_runtime.clinical_agent.clinic_items import (
    ClinicItem,
    ClinicItemWatch,
    ClinicItemWiringError,
    clinic_item_id,
)
from intake_voice_runtime.ports import WorkState, WorkType
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.safety_inbox import ClinicItemNotifier
from intake_voice_runtime.talker.preemption import Priority
from prometheus_client import REGISTRY
from protocols.triage import evaluate_triage
from talker_harness import FakeClock

K2 = int522.K2
ONSET = int522.ONSET
SESSION = int518.SESSION
ARMS = int547.ARMS
HEDGE = int547.HEDGE
STILL_HEDGED = int547.STILL_HEDGED
SLOW_AUDIT_S = 5.0


def _watch_faults(step: str) -> float:
    value = REGISTRY.get_sample_value("work_watch_faults_total", {"step": step})
    return value or 0.0


def _unaudited() -> float:
    return int547._unaudited(ARMS)


def _onset_hedged(rig: int522.Rig) -> str:
    """The lead answers, then 'bilmiyorum' to the onset: its follow-up is next.
    Returns the follow-up's step id. The Work that answers it with another
    hedge records the onset UNCLEAR after its follow-up — CD-04's item — and
    CD-05 resolves the anchor to the most acute band, so K2 fires on the same
    Work (INT-540)."""
    int522._lead(rig)
    int522._say(rig, ONSET, HEDGE)
    return int547._reentry(rig, ONSET)


def _k2_result(rig: int522.Rig, work_id: str) -> Any:
    [result] = [r for r in rig.stack.agent.drain_results() if r.work_id == work_id]
    expected = evaluate_triage(
        int521._served_rules(), rig.triage.context(rig.stack.engine), RedLocation.REMOTE
    ).result
    assert expected.level is TriageLevel.RED and [fire.id for fire in expected.rules] == [K2]
    assert result.presentation.triage_update == expected
    assert result.priority is Priority.PREEMPT
    return result


# --- 1 · the watch is not the handler -----------------------------------------------------


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_the_handlers_registered_are_the_bare_handlers_and_the_queue_holds_the_watch(
    profile: VoiceProfile,
) -> None:
    """Nothing wraps a handler: the watch cannot reach a Work's effect at all."""
    rig = int522._rig(profile, int547._model())
    agent = rig.stack.agent
    assert agent.state_handlers[WorkType.EXTRACT_SLOTS] is rig.stack.handler
    assert agent.watch is rig.stack.clinic_items is not None
    assert not hasattr(ClinicItemWatch, "wrap")


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_an_item_that_cannot_be_built_beside_k2_never_costs_the_evaluation(
    profile: VoiceProfile, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """F1: the item due on the K2 Work cannot be built. The Work completes, the
    rules engine's K2 is the Work's determination, settled at the instant the
    Work ran and handed to the clinician route; the fault is counted and
    logged by ids, and nothing is owed."""
    rig = int522._rig(profile, int547._model())
    follow_up = _onset_hedged(rig)

    def refuse(**_: object) -> ClinicItem:
        raise ValueError("synthetic item fault")

    monkeypatch.setattr(watch_module, "ClinicItem", refuse)
    before = _watch_faults("after")
    with caplog.at_level(logging.ERROR, logger="intake_voice_runtime.clinical_agent.work_queue"):
        last = int522._say(rig, follow_up, STILL_HEDGED)
    record = rig.stack.agent.record(last)
    assert record.state is WorkState.COMPLETED and record.error is None
    result = _k2_result(rig, last)
    assert result.evaluated_at_ms == record.started_ms
    assert [n.rule_ids for n in rig.clinic.notifications] == [(K2,)]
    assert rig.stack.agent._evaluation_owed is False  # noqa: SLF001 - evaluated, nothing owed
    assert _watch_faults("after") - before == 1
    [line] = [r for r in caplog.records if r.getMessage() == "state work watch failed"]
    assert (line.session_id, line.work_id, line.step, line.error) == (  # type: ignore[attr-defined]
        SESSION,
        last,
        "after",
        "ValueError",
    )
    assert int547._route(rig).items == []
    said = (HEDGE, STILL_HEDGED, *int522.SAID.values())
    shown = " ".join(r.getMessage() + str(r.__dict__) for r in caplog.records)
    assert not any(text in shown for text in said)


@dataclass
class _OrderRoute(RecordingClinicItems):
    """Records, for each item, how many REDs the clinic had been told of and
    which Works were still in flight at the moment the item was raised."""

    rig: Any = None
    seen: list[tuple[int, tuple[str, ...]]] = field(default_factory=list)

    def raise_item(self, item: ClinicItem) -> None:
        self.seen.append((len(self.rig.clinic.notifications), self.rig.stack.agent.in_flight))
        super().raise_item(item)


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_near_miss_the_item_beside_k2_is_raised_once_the_red_has_settled(
    profile: VoiceProfile,
) -> None:
    """The same Work with nothing faulting: the item is raised after the Work
    settled and the RED reached the clinician route, never before."""
    rig = int522._rig(profile, int547._model())
    watch = rig.stack.clinic_items
    assert watch is not None
    route = _OrderRoute(rig=rig)
    watch.route = route
    last = int522._say(rig, _onset_hedged(rig), STILL_HEDGED)
    assert [item.kind for item in route.items] == [ARMS]
    assert route.seen == [(1, ())]
    assert _k2_result(rig, last).evaluated_at_ms == rig.stack.agent.record(last).started_ms


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_a_watch_that_faults_before_the_handler_costs_the_work_nothing(
    profile: VoiceProfile, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both looks fault — an engine read that raises — and the K2 Work still
    binds, is evaluated and is delivered."""
    rig = int522._rig(profile, int547._model())
    follow_up = _onset_hedged(rig)

    def unreadable(self: ClinicItemWatch, engine: object) -> None:
        raise RuntimeError("synthetic engine read fault")

    monkeypatch.setattr(ClinicItemWatch, "_observe", unreadable)
    before, after = _watch_faults("before"), _watch_faults("after")
    last = int522._say(rig, follow_up, STILL_HEDGED)
    assert rig.stack.agent.record(last).state is WorkState.COMPLETED
    _k2_result(rig, last)
    assert (_watch_faults("before") - before, _watch_faults("after") - after) == (1, 1)


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_a_watch_that_faults_on_the_k2_work_never_holds_the_red_past_its_budget(
    profile: VoiceProfile, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INT-531's between-turns scenario with the watch's raise faulting on
    every Work: K2 reaches the device inside 150/300 ms of its evaluation,
    once, exactly as with no watch at all."""

    def broken(self: ClinicItemWatch, engine: object) -> None:
        raise RuntimeError("synthetic watch fault")

    monkeypatch.setattr(ClinicItemWatch, "_raise_due", broken)
    rig = int531._rig(profile)
    before = _watch_faults("after")
    between = int531._answer_onset_then(rig)
    assert rig.stack.agent.record(between.answering.work_id).state is WorkState.COMPLETED
    int531._assert_reached_within_budget(rig, between)
    int531._assert_nothing_after(rig, between)
    assert _watch_faults("after") - before >= 1


# --- 2 · ids the item could not carry are refused at composition --------------------------


@pytest.mark.parametrize("session_id", ["Ayşe Yılmaz", "", " leading-space"])
def test_a_session_id_an_item_could_not_carry_is_refused_at_composition(session_id: str) -> None:
    with pytest.raises(ValueError) as raised:
        ClinicItemWatch.for_protocol(
            int521._served_protocol(), route=RecordingClinicItems(), session_id=session_id
        )
    if session_id.strip():
        assert session_id.strip() not in str(raised.value)


def test_near_miss_a_session_with_no_watch_is_not_asked_for_an_id_shape() -> None:
    """A protocol serving no rule has no item to raise and composes no watch."""
    protocol = int521._served_protocol(())
    assert ClinicItemWatch.for_protocol(protocol, route=None, session_id="Ayşe Yılmaz") is None


# --- 3 · the audit row is never written on the state lane ---------------------------------


class _SlowAuditStore(InMemoryAuditStore):
    """An audit store whose INSERT costs virtual time, charged to the caller."""

    def __init__(self) -> None:
        super().__init__()
        self.clock: FakeClock | None = None

    def append(self, entry: AuditEntry) -> None:
        assert self.clock is not None
        self.clock.advance(SLOW_AUDIT_S)
        super().append(entry)


def _notifier(
    rows: inbox_module.ClinicItemAuditOutbox, outbox: SafetyInboxOutbox
) -> ClinicItemNotifier:
    return ClinicItemNotifier(
        outbox=outbox,
        audit=rows,
        tenant_id=int518.TENANT,
        session_id=SESSION,
        visit_id=SESSION,
    )


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_a_slow_audit_write_never_holds_the_k2_determination(profile: VoiceProfile) -> None:
    """F2: the item beside K2, through the production route, over an audit
    store that takes five seconds. The Work settles at the instant it ran — K2
    determined and delivered with nothing charged to it — and the five seconds
    are spent by the audit worker, after."""
    store = _SlowAuditStore()
    chain = AuditChain(store)
    rows = inbox_module.ClinicItemAuditOutbox(chain)
    outbox = SafetyInboxOutbox()
    rig = int522._rig(profile, int547._model(), clinic_items=_notifier(rows, outbox))
    store.clock = rig.clock
    last = int522._say(rig, _onset_hedged(rig), STILL_HEDGED)
    record = rig.stack.agent.record(last)
    assert record.finished_ms == record.started_ms
    assert _k2_result(rig, last).evaluated_at_ms == record.started_ms
    assert [e.kind for e in outbox.pending()] == [EntryKind.CHEST_PAIN_ARMS_UNRESOLVED]
    assert chain.head == GENESIS_PREV_HASH and rows.pending() == 1
    assert rows.flush() == 1
    assert rig.clock.now_ms() == record.finished_ms + SLOW_AUDIT_S * 1000.0
    assert chain.verify().ok and rows.pending() == 0


def _row_outbox(capacity: int = 2) -> tuple[inbox_module.ClinicItemAuditOutbox, AuditChain]:
    chain = AuditChain(InMemoryAuditStore())
    return inbox_module.ClinicItemAuditOutbox(chain, capacity=capacity), chain


def _raise(rows: inbox_module.ClinicItemAuditOutbox, outbox: SafetyInboxOutbox, *, n: int) -> None:
    """``n`` sessions each raise one item through the production route."""
    for index in range(n):
        session = f"{index:08d}-2222-4333-8444-555555555555"
        notifier = ClinicItemNotifier(
            outbox=outbox,
            audit=rows,
            tenant_id=int518.TENANT,
            session_id=session,
            visit_id=session,
        )
        notifier.raise_item(int547._item(session_id=session, item_id=clinic_item_id(session, ARMS)))


def test_a_full_audit_outbox_refuses_never_waits_and_counts_the_row(
    caplog: pytest.LogCaptureFixture,
) -> None:
    rows, chain = _row_outbox(capacity=2)
    outbox = SafetyInboxOutbox()
    before = _unaudited()
    with caplog.at_level(logging.ERROR, logger="intake_voice_runtime.safety_inbox"):
        _raise(rows, outbox, n=3)
    assert len(outbox.pending()) == 3  # the clinic first: every item is put
    assert rows.pending() == 2 and _unaudited() - before == 1
    [line] = [r for r in caplog.records if r.getMessage() == "clinic item unaudited"]
    assert line.error == "audit_outbox_full"  # type: ignore[attr-defined]
    assert rows.flush() == 2 and chain.verify().ok


def test_near_miss_an_outbox_with_room_counts_nothing() -> None:
    rows, chain = _row_outbox(capacity=2)
    before = _unaudited()
    _raise(rows, SafetyInboxOutbox(), n=2)
    assert rows.flush() == 2 and _unaudited() == before
    assert len(chain.export_worm().decode().splitlines()) == 3


class _RefusingStore(InMemoryAuditStore):
    def __init__(self, refuse: int) -> None:
        super().__init__()
        self.refuse = refuse

    def append(self, entry: AuditEntry) -> None:
        if self.refuse > 0:
            self.refuse -= 1
            raise RuntimeError("synthetic audit store fault")
        super().append(entry)


def test_a_row_the_chain_refuses_is_counted_and_never_blocks_the_next() -> None:
    chain = AuditChain(_RefusingStore(refuse=1))
    rows = inbox_module.ClinicItemAuditOutbox(chain)
    before = _unaudited()
    _raise(rows, SafetyInboxOutbox(), n=2)
    assert rows.flush() == 1
    assert _unaudited() - before == 1 and chain.verify().ok


def test_the_audit_pump_appends_on_the_put_and_drains_on_stop() -> None:
    rows, chain = _row_outbox(capacity=8)
    worker = threading.Thread(target=rows.pump, daemon=True)
    worker.start()
    try:
        _raise(rows, SafetyInboxOutbox(), n=3)
        assert rows.wait_until_empty(timeout=5.0)
    finally:
        rows.stop()
        worker.join(timeout=5.0)
    assert not worker.is_alive()
    assert len(chain.export_worm().decode().splitlines()) == 4 and chain.verify().ok


def test_near_miss_an_empty_outbox_is_empty_at_once() -> None:
    rows, _ = _row_outbox()
    assert rows.wait_until_empty(timeout=0.0) and rows.flush() == 0


def test_an_outbox_with_no_room_at_all_is_refused() -> None:
    with pytest.raises(ValueError, match="capacity"):
        inbox_module.ClinicItemAuditOutbox(AuditChain(InMemoryAuditStore()), capacity=0)


# --- 4 · what the watch reads is pinned -----------------------------------------------------


def test_answer_state_is_pinned_and_sorted_whole_into_unasked_and_asked() -> None:
    """F4: ADR-040 (#833) adds NOT_ASKED_PROXY. When it lands this fails until
    the new state is sorted — into unasked, where the proxy item needs it."""
    assert {state.value for state in AnswerState} == {
        "NOT_ASKED",
        "ASKED_PENDING",
        "ASKED_PRESENT",
        "ASKED_ABSENT",
        "UNCLEAR",
        "DECLINED",
        "CONTESTED",
    }
    unasked, asked = watch_module._UNASKED, watch_module._ASKED
    assert unasked | asked == frozenset(AnswerState) and not unasked & asked
    assert unasked == {AnswerState.NOT_ASKED}


def test_a_state_sorted_neither_way_is_refused_at_composition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(watch_module, "_ASKED", watch_module._ASKED - {AnswerState.UNCLEAR})
    with pytest.raises(ClinicItemWiringError, match="UNCLEAR"):
        ClinicItemWatch.for_protocol(
            int521._served_protocol(), route=RecordingClinicItems(), session_id=SESSION
        )


@pytest.mark.parametrize(
    "skip_if",
    [
        pytest.param("identity_check.subject_role == 'kendim için'", id="another-literal"),
        pytest.param("identity_check.subject_role != 'yakınım adına'", id="inverted"),
        pytest.param(
            "identity_check.subject_role == 'yakınım adına' || hpi.trajectory == 'daha kötü'",
            id="and-another-reading",
        ),
        pytest.param("!(identity_check.subject_role == 'yakınım adına')", id="negated"),
        pytest.param("identity_check.subject_role == hpi.trajectory", id="slot-to-slot"),
        pytest.param("identity_check.subject_rol == 'yakınım adına'", id="unresolved-slot"),
    ],
)
def test_a_screen_skipped_on_anything_but_cd01s_own_reading_is_refused(skip_if: str) -> None:
    """F8: naming CD-01's slot is not enough. A screen skipped when the
    subject role is anything but CD-01's literal would raise a proxy item for
    a self session — or skip the screen for one. The refusal names what the
    ``skip_if`` reads."""
    with pytest.raises(ClinicItemWiringError, match=r"skip_if reads .*identity_check\.subject_rol"):
        ClinicItemWatch.for_protocol(
            int547._with_screen_skip(skip_if), route=RecordingClinicItems(), session_id=SESSION
        )


def test_near_miss_cd01s_own_reading_either_way_round_is_watched() -> None:
    for skip_if in (
        "identity_check.subject_role == 'yakınım adına'",
        "'yakınım adına' == identity_check.subject_role",
    ):
        watch = ClinicItemWatch.for_protocol(
            int547._with_screen_skip(skip_if), route=RecordingClinicItems(), session_id=SESSION
        )
        assert watch is not None and watch.screen_skip is not None

"""INT-407 — the visit lifecycle state machine itself (files/02 §2b), pure.

files/02 §2b, verbatim: *"The entire timing model of this product hangs off an
appointment datetime acquired by OCR from an SMS screenshot and then never
re-verified … A visit therefore needs an explicit state machine, and it needs
one for a safety reason before a UX one."*

What this file pins (the API is ``tests/api/test_visit_lifecycle.py``; the RED
half is ``tests/safety/test_red_visit_transition.py``):

1. **The table.** Every (from, to) pair over the seven states is either
   allowed or refused, and the expected table below is restated from 02 §2b by
   hand rather than imported, so the code's table is checked against the
   spec's reading and not against itself.
2. **The guards.** A reschedule carries a new datetime and lands back in
   ``planned``; ``missed`` needs the datetime plus a grace to have elapsed with
   no check-in, and the grace is the caller's (no default is invented); a
   check-in carries its evidence.
3. **Check-in doubt is UNKNOWN**, never ``ON_SITE`` (invariant 21).
4. **The T-24h confirm is queued, transactional, and unsent** while no SMS
   vendor is configured (INT-358) — and nothing, fake or real, is handed it
   without reviewed copy.
5. **Staleness**: only a rescheduled visit's note goes stale, seven days after
   its session.
"""

from __future__ import annotations

import datetime as dt
import itertools
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from clinical_schemas.triage import RedLocation
from clinical_schemas.visit_time import VisitSchedule, VisitTime, VisitTimeSource
from intake_platform.notifications import Channel, DeliveryReceipt, MessageClass, SealedMessage
from intake_platform.notifications.ports import UnconfiguredTransport
from intake_platform.visit_lifecycle import (
    ALLOWED_TRANSITIONS,
    CONFIRM_LEAD,
    NOTE_STALE_AFTER,
    RESTING_STATES,
    CheckInEvidence,
    CheckInMethod,
    ConfirmDispatch,
    ConfirmStatus,
    TransitionRefused,
    VisitLifecycle,
    VisitState,
    attempt_confirm_dispatch,
    derive_location,
    landing,
    queue_confirm,
)

TR = ZoneInfo("Europe/Istanbul")
T0 = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
TID = "7b0f3c2e-1d4a-4b8e-9c6f-0a1b2c3d4e5f"

#: files/02 §2b, restated by hand. The diagram draws the happy path; its rules
#: make the T-24h confirm a CORRECTION channel on the OCR'd datetime, not a gate
#: on arriving — so everything a confirmed visit may do, a planned one may do
#: too (and at P1 no confirm can even be sent: INT-358). ``checked_in`` leads
#: only to ``attended``; ``attended``, ``cancelled`` and ``missed`` are
#: terminal; ``rescheduled`` is a transition, never a resting state — it lands
#: back in ``planned`` with the new datetime.
EXPECTED: dict[str, set[str]] = {
    "planned": {"confirmed", "checked_in", "attended", "cancelled", "rescheduled", "missed"},
    "confirmed": {"checked_in", "attended", "cancelled", "rescheduled", "missed"},
    "checked_in": {"attended"},
    "attended": set(),
    "cancelled": set(),
    "missed": set(),
}

SCHEDULE = VisitSchedule(
    date=dt.date(2026, 9, 20),
    time=VisitTime(at=dt.time(14, 30), source=VisitTimeSource.PATIENT_ENTRY),
)
CERTAIN_QR = CheckInEvidence(method=CheckInMethod.QR, scanned_by_patient=True)


def _instant(schedule: VisitSchedule) -> datetime:
    at = schedule.time.at if schedule.time is not None else dt.time.min
    return datetime.combine(schedule.date, at, tzinfo=TR).astimezone(UTC)


def _record(state: str) -> VisitLifecycle:
    if state == "checked_in":
        return VisitLifecycle(state=VisitState.CHECKED_IN, seq=2, check_in=CERTAIN_QR)
    return VisitLifecycle(state=VisitState(state), seq=2)


def _apply(record: VisitLifecycle, to: VisitState, *, at: datetime = T0) -> VisitLifecycle:
    """Every transition with the payload its own guard asks for, so a refusal
    below can only be the table's."""
    kwargs: dict[str, Any] = {"transition_id": TID, "at": at}
    if to is VisitState.RESCHEDULED:
        kwargs["schedule"] = SCHEDULE
        kwargs["confirm_message_id"] = "c-1"
    elif to is VisitState.CHECKED_IN:
        kwargs["check_in"] = CERTAIN_QR
    elif to is VisitState.MISSED:
        kwargs["schedule"] = SCHEDULE
        kwargs["missed_grace"] = timedelta(hours=1)
        kwargs["at"] = _instant(SCHEDULE) + timedelta(hours=2)
    return record.apply(to, **kwargs)


# ======================================================================================
# 1. the table
# ======================================================================================


class TestTheTable:
    def test_the_code_table_is_the_spec_table(self) -> None:
        coded = {
            state.value: {target.value for target in ALLOWED_TRANSITIONS[state]}
            for state in RESTING_STATES
        }
        assert coded == EXPECTED

    def test_rescheduled_is_a_transition_never_a_resting_state(self) -> None:
        assert VisitState.RESCHEDULED not in RESTING_STATES
        assert landing(VisitState.RESCHEDULED) is VisitState.PLANNED
        with pytest.raises(ValueError):
            VisitLifecycle(state=VisitState.RESCHEDULED, seq=1)

    @pytest.mark.parametrize(
        ("source", "target"),
        list(itertools.product(sorted(EXPECTED), [state.value for state in VisitState])),
    )
    def test_every_pair_is_allowed_or_refused_exactly_as_the_table_says(
        self, source: str, target: str
    ) -> None:
        record = _record(source)
        to = VisitState(target)
        if target in EXPECTED[source]:
            moved = _apply(record, to)
            assert moved.state is landing(to)
            assert moved.seq == record.seq + 1
            assert moved.transition_id == TID
            assert moved.last_transition is to
        else:
            with pytest.raises(TransitionRefused) as refused:
                _apply(record, to)
            assert refused.value.code == "transition_not_allowed"

    def test_a_refusal_leaves_the_record_as_it_was(self) -> None:
        record = _record("cancelled")
        before = record.model_dump()
        with pytest.raises(TransitionRefused):
            _apply(record, VisitState.RESCHEDULED)
        assert record.model_dump() == before


# ======================================================================================
# 2. the guards
# ======================================================================================


class TestTheGuards:
    def test_a_reschedule_carries_a_new_datetime(self) -> None:
        with pytest.raises(TransitionRefused) as refused:
            _record("planned").apply(VisitState.RESCHEDULED, transition_id=TID, at=T0)
        assert refused.value.code == "schedule_required"

    def test_a_schedule_is_refused_on_a_transition_that_does_not_move_the_visit(self) -> None:
        with pytest.raises(TransitionRefused) as refused:
            _record("planned").apply(
                VisitState.CONFIRMED, transition_id=TID, at=T0, schedule=SCHEDULE
            )
        assert refused.value.code == "schedule_not_allowed"

    def test_a_reschedule_lands_in_planned_and_requeues_the_confirm(self) -> None:
        confirmed = _record("confirmed")
        moved = _apply(confirmed, VisitState.RESCHEDULED)
        assert moved.state is VisitState.PLANNED
        assert moved.last_transition is VisitState.RESCHEDULED
        assert moved.rescheduled_at == T0
        assert moved.confirm is not None
        assert moved.confirm.status is ConfirmStatus.QUEUED
        assert moved.confirm.due_at == _instant(SCHEDULE) - CONFIRM_LEAD

    def test_a_check_in_carries_its_evidence(self) -> None:
        with pytest.raises(TransitionRefused) as refused:
            _record("confirmed").apply(VisitState.CHECKED_IN, transition_id=TID, at=T0)
        assert refused.value.code == "check_in_evidence_required"
        with pytest.raises(TransitionRefused) as refused:
            _record("planned").apply(
                VisitState.CONFIRMED, transition_id=TID, at=T0, check_in=CERTAIN_QR
            )
        assert refused.value.code == "check_in_evidence_not_allowed"

    def test_missed_needs_the_datetime_plus_grace_to_have_elapsed(self) -> None:
        grace = timedelta(minutes=45)
        due = _instant(SCHEDULE) + grace
        record = _record("confirmed")
        # near-miss: one second before the grace ends is not missed
        with pytest.raises(TransitionRefused) as refused:
            record.apply(
                VisitState.MISSED,
                transition_id=TID,
                at=due - timedelta(seconds=1),
                schedule=SCHEDULE,
                missed_grace=grace,
            )
        assert refused.value.code == "missed_not_due"
        moved = record.apply(
            VisitState.MISSED, transition_id=TID, at=due, schedule=SCHEDULE, missed_grace=grace
        )
        assert moved.state is VisitState.MISSED

    def test_missed_has_no_invented_grace_and_no_unknown_datetime(self) -> None:
        record = _record("planned")
        late = _instant(SCHEDULE) + timedelta(days=3)
        with pytest.raises(TransitionRefused) as refused:
            record.apply(VisitState.MISSED, transition_id=TID, at=late, schedule=SCHEDULE)
        assert refused.value.code == "missed_grace_unset"
        with pytest.raises(TransitionRefused) as refused:
            record.apply(
                VisitState.MISSED, transition_id=TID, at=late, missed_grace=timedelta(hours=1)
            )
        assert refused.value.code == "missed_schedule_unknown"
        with pytest.raises(TransitionRefused) as refused:
            record.apply(
                VisitState.MISSED,
                transition_id=TID,
                at=late,
                schedule=SCHEDULE,
                missed_grace=timedelta(hours=-1),
            )
        assert refused.value.code == "missed_grace_unset"

    def test_leaving_planned_withdraws_the_queued_confirm(self) -> None:
        queued = VisitLifecycle.initial(schedule=SCHEDULE, confirm_message_id="c-0")
        assert queued.confirm is not None
        assert queued.confirm.status is ConfirmStatus.QUEUED
        for target in (VisitState.CONFIRMED, VisitState.CANCELLED):
            moved = queued.apply(target, transition_id=TID, at=T0)
            assert moved.confirm is not None
            assert moved.confirm.status is ConfirmStatus.WITHDRAWN
            assert moved.confirm.message_id == "c-0"

    def test_timestamps_are_aware(self) -> None:
        with pytest.raises(TransitionRefused) as refused:
            _record("planned").apply(
                VisitState.CONFIRMED, transition_id=TID, at=datetime(2026, 9, 1, 9, 0)
            )
        assert refused.value.code == "naive_timestamp"

    def test_a_transition_id_is_an_id_never_prose(self) -> None:
        with pytest.raises(TransitionRefused) as refused:
            _record("planned").apply(VisitState.CONFIRMED, transition_id="hasta iptal etti", at=T0)
        assert refused.value.code == "transition_id_invalid"
        assert "hasta" not in str(refused.value)

    def test_the_slot_round_trips_and_an_absent_slot_is_planned(self) -> None:
        assert VisitLifecycle.from_slot(None) == VisitLifecycle.initial()
        assert VisitLifecycle.initial().state is VisitState.PLANNED
        record = _apply(_apply(_record("planned"), VisitState.CONFIRMED), VisitState.CHECKED_IN)
        assert VisitLifecycle.from_slot(record.to_slot()) == record


# ======================================================================================
# 3. location — check-in doubt is UNKNOWN, never ON_SITE (invariant 21)
# ======================================================================================


DOUBTFUL = (
    CheckInEvidence(method=CheckInMethod.QR, scanned_by_patient=False),  # a relative scanned
    CheckInEvidence(method=CheckInMethod.QR),  # nobody said who scanned
    CheckInEvidence(method=CheckInMethod.GEOFENCE, inside_building=False),  # the car park
    CheckInEvidence(method=CheckInMethod.GEOFENCE),  # no fix inside the building
)


class TestLocation:
    def test_the_derivation_table(self) -> None:
        certain_fence = CheckInEvidence(method=CheckInMethod.GEOFENCE, inside_building=True)
        assert derive_location(VisitState.PLANNED, mode="fast", check_in=None) is (
            RedLocation.REMOTE
        )
        assert derive_location(VisitState.CONFIRMED, mode="fast", check_in=None) is (
            RedLocation.REMOTE
        )
        for evidence in (CERTAIN_QR, certain_fence):
            assert derive_location(VisitState.CHECKED_IN, mode="detailed", check_in=evidence) is (
                RedLocation.ON_SITE
            )

    @pytest.mark.parametrize("evidence", DOUBTFUL)
    def test_check_in_doubt_yields_unknown_never_on_site(self, evidence: CheckInEvidence) -> None:
        assert evidence.certain is False
        assert derive_location(VisitState.CHECKED_IN, mode="detailed", check_in=evidence) is (
            RedLocation.UNKNOWN
        )

    def test_nothing_that_cannot_be_known_is_guessed(self) -> None:
        for state in VisitState:
            for mode in ("fast", "detailed", None):
                for evidence in (*DOUBTFUL, None):
                    location = derive_location(state, mode=mode, check_in=evidence)
                    assert location is not RedLocation.ON_SITE
        for state in (VisitState.ATTENDED, VisitState.CANCELLED, VisitState.MISSED):
            assert derive_location(state, mode="fast", check_in=None) is RedLocation.UNKNOWN
        # a fast-mode session at a checked-in visit, or a session of no known mode
        assert derive_location(VisitState.CHECKED_IN, mode="fast", check_in=CERTAIN_QR) is (
            RedLocation.UNKNOWN
        )
        assert derive_location(VisitState.PLANNED, mode=None, check_in=None) is (
            RedLocation.UNKNOWN
        )
        assert derive_location(VisitState.PLANNED, mode="detailed", check_in=None) is (
            RedLocation.UNKNOWN
        )

    def test_evidence_names_only_its_own_signal(self) -> None:
        with pytest.raises(ValueError):
            CheckInEvidence(method=CheckInMethod.QR, inside_building=True)
        with pytest.raises(ValueError):
            CheckInEvidence(method=CheckInMethod.GEOFENCE, scanned_by_patient=True)


# ======================================================================================
# 4. the T-24h confirm — queued, transactional, unsent without a vendor
# ======================================================================================


class _SpyTransport:
    """A transport that WOULD deliver — used only to prove it is never asked."""

    channel = Channel.SMS

    def __init__(self) -> None:
        self.calls = 0

    def deliver(self, message: SealedMessage) -> DeliveryReceipt:
        self.calls += 1
        return DeliveryReceipt(delivery_id="x", accepted=True, vendor_status="queued")


class TestTheConfirm:
    def test_it_is_a_transactional_sms_due_a_day_before_the_visit(self) -> None:
        confirm = queue_confirm(SCHEDULE, message_id="c-1")
        assert confirm.status is ConfirmStatus.QUEUED
        assert confirm.message_class is MessageClass.TRANSACTIONAL
        assert confirm.channel is Channel.SMS
        assert confirm.due_at == _instant(SCHEDULE) - CONFIRM_LEAD
        assert CONFIRM_LEAD == timedelta(hours=24)

    def test_a_date_only_visit_is_asked_no_later_than_a_day_before_any_hour(self) -> None:
        date_only = VisitSchedule(date=SCHEDULE.date, time=None)
        confirm = queue_confirm(date_only, message_id="c-1")
        for minute in range(0, 24 * 60, 7):
            at = dt.time(minute // 60, minute % 60)
            real = VisitSchedule(
                date=SCHEDULE.date, time=VisitTime(at=at, source=VisitTimeSource.PATIENT_ENTRY)
            )
            assert confirm.due_at <= queue_confirm(real, message_id="c-2").due_at

    def test_it_stays_queued_without_an_sms_vendor(self) -> None:
        confirm = queue_confirm(SCHEDULE, message_id="c-1")
        due = confirm.due_at
        assert attempt_confirm_dispatch(
            confirm, transport=None, now=due - timedelta(minutes=1)
        ) is (ConfirmDispatch.NOT_DUE)
        for transport in (None, UnconfiguredTransport(Channel.SMS)):
            outcome = attempt_confirm_dispatch(confirm, transport=transport, now=due)
            assert outcome is ConfirmDispatch.BLOCKED_TRANSPORT_UNCONFIGURED
        assert confirm.status is ConfirmStatus.QUEUED

    def test_a_transport_that_would_deliver_is_never_asked_without_reviewed_copy(self) -> None:
        """Near-miss control: were the vendor contracted tomorrow, the confirm
        still has no reviewed body (files/02 §2b's example interpolates the day,
        the hour and the department, which the INT-141 content-free catalogue
        forbids), so nothing — fake or real — is handed a message."""
        confirm = queue_confirm(SCHEDULE, message_id="c-1")
        spy = _SpyTransport()
        outcome = attempt_confirm_dispatch(confirm, transport=spy, now=confirm.due_at)
        assert outcome is ConfirmDispatch.BLOCKED_COPY_UNREVIEWED
        assert spy.calls == 0

    def test_a_withdrawn_confirm_is_never_due(self) -> None:
        queued = VisitLifecycle.initial(schedule=SCHEDULE, confirm_message_id="c-0")
        cancelled = queued.apply(VisitState.CANCELLED, transition_id=TID, at=T0)
        assert cancelled.confirm is not None
        outcome = attempt_confirm_dispatch(
            cancelled.confirm, transport=None, now=cancelled.confirm.due_at
        )
        assert outcome is ConfirmDispatch.WITHDRAWN


# ======================================================================================
# 5. note staleness
# ======================================================================================


class TestNoteStaleness:
    def test_only_a_rescheduled_visit_marks_its_note_stale(self) -> None:
        anchor = T0
        planned = _record("planned")
        assert planned.note_stale(anchor, now=anchor + timedelta(days=60)) is False
        moved = _apply(planned, VisitState.RESCHEDULED, at=anchor + timedelta(days=1))
        assert NOTE_STALE_AFTER == timedelta(days=7)
        assert moved.note_stale(anchor, now=anchor + NOTE_STALE_AFTER - timedelta(seconds=1)) is (
            False
        )
        assert moved.note_stale(anchor, now=anchor + NOTE_STALE_AFTER) is True
        assert moved.note_stale(None, now=anchor + timedelta(days=60)) is False

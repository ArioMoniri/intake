"""INT-407 — the visit lifecycle through the API (files/02 §2b).

``POST /v1/visits/{id}/transitions`` is where a visit moves, and the server is
authoritative: the device reflects the record, it never derives one. The pure
machine — the table, the guards, the location axis — is
``tests/platform/test_visit_lifecycle_machine.py``; the RED half (a RED visit
cannot silently move) is ``tests/safety/test_red_visit_transition.py``.

What this file pins:

1. **Every transition is audited by id**, an invalid one is refused (409) and
   changes nothing, and only the patient's own moves are offered.
2. **Cancel** revokes every share and Doctor Link and withdraws what the clinic
   side could read — *"A patient who cancelled has withdrawn the context in
   which they consented to share."*
3. **Reschedule** moves the datetime, re-pins the Doctor Link expiry to the NEW
   ``visit_datetime + 72 h`` — never issue time (near-miss control) — marks the
   note stale seven days after its session on every surface that shows it, and
   offers a delta session only behind a flag, because no reviewed copy for the
   offer exists.
4. **A doubtful check-in** is recorded and yields UNKNOWN, never ON_SITE.
5. **The T-24h confirm** is queued on every dated visit and is still queued
   past its due time: no SMS vendor exists (INT-358), and nothing fake sends it.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, get_args

import fakeredis
import pytest
from api_harness import ADMIN_TOKEN, PATIENT_TOKEN, ApiHarness, build_harness, run
from clinical_schemas.triage import RedLocation
from clinical_schemas.visit_time import VisitSchedule, VisitTime, VisitTimeSource
from intake_api.attestation import FailClosedAttestationVerifier
from intake_api.otp import AuthWiring, DevLogDeliveryAdapter
from intake_api.schemas import VisitStateOut
from intake_platform.audit import verify_entries
from intake_platform.db.models import Share
from intake_platform.doctor_link import DOCTOR_LINK_TTL
from intake_platform.flags import SAFETY_FLAG_DEFAULTS, InMemoryProvider
from intake_platform.notifications import Channel, MessageClass
from intake_platform.notifications.ports import UnconfiguredTransport
from intake_platform.safety_inbox import RedisSafetyInboxStore, SafetyInbox
from intake_platform.tokenization import Tokenizer
from intake_platform.visit_lifecycle import (
    CONFIRM_LEAD,
    DELTA_SESSION_OFFER_FLAG,
    NOTE_STALE_AFTER,
    RESTING_STATES,
    ConfirmDispatch,
    ConfirmStatus,
    VisitState,
    attempt_confirm_dispatch,
)
from lifecycle_helpers import (
    SCHEDULE,
    T0,
    Clock,
    aware,
    instant,
    issue_link,
    lifecycle,
    link_row,
    move,
    open_link,
    read,
    send_note,
    visit,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture()
def clock() -> Clock:
    return Clock(T0)


@pytest.fixture()
def link_redis() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis()


@pytest.fixture()
def api(tmp_path: Path, clock: Clock, link_redis: fakeredis.FakeRedis) -> Iterator[ApiHarness]:
    auth = AuthWiring(
        redis_client=link_redis,
        tokenizer=Tokenizer(keys={"v1": b"unit-lane-tokenization-key"}, active_key_id="v1"),
        delivery=DevLogDeliveryAdapter(),
        attestation=FailClosedAttestationVerifier(),
        dev_otp_peek=False,
        now_fn=clock.epoch,
    )
    harnesses = build_harness(
        tmp_path,
        token_patient=PATIENT_TOKEN,
        token_admin=ADMIN_TOKEN,
        auth=auth,
        # the clinic Safety inbox, empty: no visit here carries a RED (the RED
        # half is tests/safety/test_red_visit_transition.py)
        safety_inbox=SafetyInbox(store=RedisSafetyInboxStore(fakeredis.FakeStrictRedis())),
    )
    harness = next(harnesses)
    harness.client.app.state.api.clock = clock  # type: ignore[attr-defined]
    yield harness
    for _ in harnesses:
        pass


class TestTheRoute:
    def test_the_wire_states_are_the_resting_states(self) -> None:
        assert set(get_args(VisitStateOut)) == {state.value for state in RESTING_STATES}

    def test_a_new_visit_is_planned_with_its_confirm_queued(self, api: ApiHarness) -> None:
        visit_id = visit(api)
        assert read(api, visit_id)["state"] == "planned"
        record = lifecycle(api, visit_id)
        assert record.state is VisitState.PLANNED
        assert record.confirm is not None
        assert record.confirm.status is ConfirmStatus.QUEUED
        assert record.confirm.channel is Channel.SMS
        assert record.confirm.message_class is MessageClass.TRANSACTIONAL
        assert record.confirm.due_at == instant(SCHEDULE) - CONFIRM_LEAD

    def test_an_undated_visit_queues_no_confirm(self, api: ApiHarness) -> None:
        visit_id = visit(api, {"hospital": "Hastane", "department": "Bölüm"})
        assert lifecycle(api, visit_id).confirm is None

    def test_the_queued_confirm_stays_unsent_past_its_due_time(
        self, api: ApiHarness, clock: Clock
    ) -> None:
        """INT-358 is awaiting-human, so no SMS transport exists to hand it to:
        past its due time the confirm is still queued, and there is no state a
        send could even be recorded in — nothing, fake or real, sent it."""
        visit_id = visit(api)
        record = lifecycle(api, visit_id)
        assert record.confirm is not None
        clock.now = record.confirm.due_at + timedelta(hours=1)
        read(api, visit_id)
        assert lifecycle(api, visit_id).confirm == record.confirm
        assert {status.value for status in ConfirmStatus} == {"queued", "withdrawn"}
        outcome = attempt_confirm_dispatch(
            record.confirm, transport=UnconfiguredTransport(Channel.SMS), now=clock()
        )
        assert outcome is ConfirmDispatch.BLOCKED_TRANSPORT_UNCONFIGURED

    def test_every_transition_is_audited_by_its_id(self, api: ApiHarness, clock: Clock) -> None:
        visit_id = visit(api)
        confirmed = move(api, visit_id, to="confirmed")
        assert confirmed.status_code == 200, confirmed.text
        first = confirmed.json()["transition_id"]
        clock.advance(timedelta(hours=1))
        checked = move(
            api, visit_id, to="checked_in", check_in={"method": "qr", "scanned_by_patient": True}
        )
        assert checked.status_code == 200, checked.text
        second = checked.json()["transition_id"]
        assert first != second
        entries = api.audit_store.entries()
        refs = {(entry.action, entry.resource_ref) for entry in entries}
        assert ("api.visit.transition.confirmed", f"visit:{visit_id}/transition:{first}") in refs
        assert ("api.visit.transition.checked_in", f"visit:{visit_id}/transition:{second}") in refs
        assert verify_entries(entries).ok
        record = lifecycle(api, visit_id)
        assert (record.state, record.seq, record.transition_id) == (
            VisitState.CHECKED_IN,
            2,
            second,
        )

    def test_an_invalid_transition_is_refused_and_changes_nothing(self, api: ApiHarness) -> None:
        visit_id = visit(api)
        assert move(api, visit_id, to="cancelled").status_code == 200
        before = lifecycle(api, visit_id)
        audited = len(api.audit_store.entries())
        refused = move(api, visit_id, to="confirmed")
        assert refused.status_code == 409
        assert refused.json() == {"error": "transition_not_allowed"}
        assert lifecycle(api, visit_id) == before
        assert len(api.audit_store.entries()) == audited

    @pytest.mark.parametrize("target", ["attended", "missed", "rescheduledd", "planned"])
    def test_the_patient_route_takes_only_the_patient_transitions(
        self, api: ApiHarness, target: str
    ) -> None:
        visit_id = visit(api)
        assert move(api, visit_id, to=target).status_code == 422
        assert lifecycle(api, visit_id).state is VisitState.PLANNED

    def test_another_patients_visit_is_not_found(self, api: ApiHarness) -> None:
        assert move(api, str(uuid.uuid4()), to="confirmed").status_code == 404

    def test_the_clinic_side_cannot_move_avisit(self, api: ApiHarness) -> None:
        visit_id = visit(api)
        response = api.client.post(
            f"/v1/visits/{visit_id}/transitions", json={"to": "cancelled"}, headers=api.admin()
        )
        assert response.status_code == 403
        assert lifecycle(api, visit_id).state is VisitState.PLANNED


class TestCancel:
    def test_cancel_revokes_every_share_and_link_and_withdraws_the_clinic_entry(
        self, api: ApiHarness, clock: Clock
    ) -> None:
        visit_id = visit(api)
        send_note(api, visit_id)
        issued = issue_link(api, visit_id)
        # the clinic side can read the shared note before the cancel
        assert api.client.get(f"/v1/visits/{visit_id}/note", headers=api.admin()).status_code == 200

        cancelled = move(api, visit_id, to="cancelled")
        assert cancelled.status_code == 200, cancelled.text
        body = cancelled.json()
        assert body["visit"]["state"] == "cancelled"
        assert body["visit"]["note_status"] == "draft"

        async def _shares() -> list[Share]:
            async with AsyncSession(api.engine) as session:
                return list((await session.scalars(select(Share))).all())

        shares = run(_shares())
        assert shares and all(share.revoked_at is not None for share in shares)
        assert link_row(api, str(issued["link_id"])).revoked_at is not None
        # the clinician's entry is withdrawn: the clinic side reads nothing now
        assert api.client.get(f"/v1/visits/{visit_id}/note", headers=api.admin()).status_code == 404
        assert open_link(api, clock, visit_id, issued).status_code != 200
        actions = {(e.action, e.resource_ref) for e in api.audit_store.entries()}
        assert ("api.note.share_revoked", f"share:{shares[0].id}") in actions
        assert ("api.doctor_link.revoked", f"doctor_link:{issued['link_id']}") in actions
        assert any(action == "api.visit.clinician_entry_withdrawn" for action, _ in actions)
        confirm = lifecycle(api, visit_id).confirm
        assert confirm is not None
        assert confirm.status is ConfirmStatus.WITHDRAWN

    def test_cancelling_a_visit_with_nothing_shared_revokes_nothing(self, api: ApiHarness) -> None:
        visit_id = visit(api)
        assert move(api, visit_id, to="cancelled").status_code == 200
        actions = {e.action for e in api.audit_store.entries()}
        assert "api.note.share_revoked" not in actions
        assert "api.visit.clinician_entry_withdrawn" not in actions


class TestReschedule:
    NEW = {"date": "2026-10-05", "time": "10:00", "time_source": "patient_entry"}
    NEW_SCHEDULE = VisitSchedule(
        date=dt.date(2026, 10, 5),
        time=VisitTime(at=dt.time(10, 0), source=VisitTimeSource.PATIENT_ENTRY),
    )

    def test_a_reschedule_moves_the_datetime_and_lands_in_planned(self, api: ApiHarness) -> None:
        visit_id = visit(api)
        assert move(api, visit_id, to="confirmed").status_code == 200
        moved = move(api, visit_id, to="rescheduled", **self.NEW)
        assert moved.status_code == 200, moved.text
        out = moved.json()["visit"]
        assert (out["state"], out["date"], out["time"]) == ("planned", "2026-10-05", "10:00")
        assert read(api, visit_id) == out
        record = lifecycle(api, visit_id)
        assert record.last_transition is VisitState.RESCHEDULED
        assert record.confirm is not None
        assert record.confirm.status is ConfirmStatus.QUEUED
        assert record.confirm.due_at == instant(self.NEW_SCHEDULE) - CONFIRM_LEAD

    @pytest.mark.parametrize(
        ("body", "code"),
        [
            ({}, "schedule_required"),
            ({"date": "05-10-2026"}, "bad_date"),
            ({"date": "2026-10-05", "time": "10:00"}, "time_source_required"),
        ],
    )
    def test_a_reschedule_without_a_valid_datetime_is_refused(
        self, api: ApiHarness, body: dict[str, str], code: str
    ) -> None:
        visit_id = visit(api)
        refused = move(api, visit_id, to="rescheduled", **body)
        assert refused.status_code == 422
        assert refused.json() == {"error": code}
        assert read(api, visit_id)["date"] == "2026-09-20"

    def test_the_doctor_link_expiry_follows_the_new_visit_datetime(
        self, api: ApiHarness, clock: Clock, link_redis: fakeredis.FakeRedis
    ) -> None:
        visit_id = visit(api)
        send_note(api, visit_id)
        issued_at = clock()
        issued = issue_link(api, visit_id)
        assert aware(link_row(api, str(issued["link_id"])).expires_at) == (
            instant(SCHEDULE) + DOCTOR_LINK_TTL
        )

        assert move(api, visit_id, to="rescheduled", **self.NEW).status_code == 200
        repinned = aware(link_row(api, str(issued["link_id"])).expires_at)
        assert repinned == instant(self.NEW_SCHEDULE) + DOCTOR_LINK_TTL
        # near-miss: an issue-time anchor is a different instant, by days
        assert abs(repinned - (issued_at + DOCTOR_LINK_TTL)) > timedelta(days=30)
        # the routing hint's lifetime moved with the row (fakeredis counts its
        # TTL in real seconds, so the hint is read, not waited out)
        hint_ttl = link_redis.ttl(
            "dlink:idx:" + link_row(api, str(issued["link_id"])).token_fingerprint
        )
        assert abs(hint_ttl - (repinned - clock()).total_seconds()) < 60

        # and the link still opens past its ORIGINAL expiry
        clock.now = instant(SCHEDULE) + DOCTOR_LINK_TTL + timedelta(hours=1)
        opened = open_link(api, clock, visit_id, issued)
        assert opened.status_code == 200, opened.text
        assert aware(datetime.fromisoformat(opened.json()["expires_at"])) == repinned
        repins = [
            e for e in api.audit_store.entries() if e.action == "api.doctor_link.expiry_repinned"
        ]
        assert [e.resource_ref for e in repins] == [f"doctor_link:{issued['link_id']}"]

    def test_a_revoked_link_is_not_revived_by_a_reschedule(self, api: ApiHarness) -> None:
        visit_id = visit(api)
        send_note(api, visit_id)
        issued = issue_link(api, visit_id)
        revoked = api.client.post(
            f"/v1/visits/{visit_id}/note/doctor-links/{issued['link_id']}/revoke",
            headers=api.patient(),
        )
        assert revoked.status_code == 200
        before = aware(link_row(api, str(issued["link_id"])).expires_at)
        assert move(api, visit_id, to="rescheduled", **self.NEW).status_code == 200
        row = link_row(api, str(issued["link_id"]))
        assert row.revoked_at is not None
        assert aware(row.expires_at) == before

    def test_the_note_goes_stale_seven_days_after_its_session(
        self, api: ApiHarness, clock: Clock
    ) -> None:
        visit_id = visit(api)
        sent_at = clock()
        send_note(api, visit_id)
        issued = issue_link(api, visit_id)
        clock.advance(timedelta(days=1))
        assert move(api, visit_id, to="rescheduled", **self.NEW).status_code == 200

        clock.now = sent_at + NOTE_STALE_AFTER - timedelta(seconds=1)
        fresh = read(api, visit_id)
        assert (fresh["note_stale"], fresh["delta_session_offered"]) == (False, False)

        clock.now = sent_at + NOTE_STALE_AFTER
        stale = read(api, visit_id)
        assert stale["note_stale"] is True
        # the clinic side sees the mark on the note it reads, too
        note = api.client.get(f"/v1/visits/{visit_id}/note", headers=api.admin())
        assert note.status_code == 200
        assert note.json()["stale"] is True
        # and so does the clinician who opens the Doctor Link
        opened = open_link(api, clock, visit_id, issued)
        assert opened.status_code == 200, opened.text
        assert opened.json()["note_stale"] is True
        # no reviewed copy for the offer exists, so it stays behind its flag
        assert SAFETY_FLAG_DEFAULTS[DELTA_SESSION_OFFER_FLAG] is False
        assert stale["delta_session_offered"] is False
        api.client.app.state.api.flags = InMemoryProvider({DELTA_SESSION_OFFER_FLAG: True})  # type: ignore[attr-defined]
        assert read(api, visit_id)["delta_session_offered"] is True

    def test_a_visit_that_never_moved_keeps_a_fresh_note(
        self, api: ApiHarness, clock: Clock
    ) -> None:
        visit_id = visit(api)
        send_note(api, visit_id)
        clock.advance(timedelta(days=30))
        assert read(api, visit_id)["note_stale"] is False


class TestCheckIn:
    @pytest.mark.parametrize(
        "evidence",
        [
            {"method": "qr", "scanned_by_patient": False},
            {"method": "qr"},
            {"method": "geofence", "inside_building": False},
            {"method": "geofence"},
        ],
    )
    def test_a_doubtful_check_in_is_recorded_and_yields_unknown(
        self, api: ApiHarness, evidence: dict[str, Any]
    ) -> None:
        visit_id = visit(api)
        moved = move(api, visit_id, to="checked_in", check_in=evidence)
        assert moved.status_code == 200, moved.text
        assert moved.json()["visit"]["state"] == "checked_in"
        assert moved.json()["visit"]["check_in_certain"] is False
        record = lifecycle(api, visit_id)
        assert record.location(mode="detailed") is RedLocation.UNKNOWN

    def test_a_certain_check_in_yields_on_site_in_detailed_mode(self, api: ApiHarness) -> None:
        visit_id = visit(api)
        moved = move(
            api, visit_id, to="checked_in", check_in={"method": "geofence", "inside_building": True}
        )
        assert moved.status_code == 200, moved.text
        assert moved.json()["visit"]["check_in_certain"] is True
        assert lifecycle(api, visit_id).location(mode="detailed") is RedLocation.ON_SITE

    def test_a_check_in_without_evidence_is_refused(self, api: ApiHarness) -> None:
        visit_id = visit(api)
        refused = move(api, visit_id, to="checked_in")
        assert refused.status_code == 422
        assert refused.json() == {"error": "check_in_evidence_required"}

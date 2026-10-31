"""INT-589 (3) — a note's share lives until the appointment's window closes.

From the legal review of INT-587 (#988): the server share expired 72 h after
the SEND (``store.create_share``). Meanwhile ``review.consent.untilValue``
promised three days after the appointment, share.tr.md says the link closes
at the latest 72 h after the appointment, and issuing a Doctor Link needs a
live share. So a note sent more than 72 h before its appointment could not be
linked at the visit. files/02 §2b names exactly this defect for the link:
*"A note prepared five days early currently expires before the clinician
opens it."*

The rule now (``intake_api.share_lifetime``):

- a dated visit's share lives until ``visit_instant + 72 h``, the anchor the
  Doctor Link already uses (the appointment's hour where known, else the start
  of the visit date);
- it never lives less than 72 h from the send, so no send is shorter-lived
  than before (a note sent after the appointment keeps the old window);
- an undated visit keeps ``send + 72 h``;
- a reschedule moves a live share's expiry with the visit, by the same rule
  from the original send; a revoked share is never revived.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import fakeredis
import pytest
from api_harness import ADMIN_TOKEN, PATIENT_TOKEN, ApiHarness, build_harness, run
from clinical_schemas.visit_time import VisitSchedule, VisitTime, VisitTimeSource
from intake_api.attestation import FailClosedAttestationVerifier
from intake_api.otp import AuthWiring, DevLogDeliveryAdapter
from intake_api.share_lifetime import SHARE_TTL, share_expires_at
from intake_platform.db.models import Note, Share
from intake_platform.doctor_link import DOCTOR_LINK_TTL, visit_instant
from intake_platform.safety_inbox import RedisSafetyInboxStore, SafetyInbox
from intake_platform.tokenization import Tokenizer
from lifecycle_helpers import NOTE_BODY, T0, TR, Clock, aware, move, send_note, visit
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

SENT = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
AT_1430 = VisitTime(at=dt.time(14, 30), source=VisitTimeSource.PATIENT_ENTRY)


# --- the rule, as a pure function ------------------------------------------------------


def test_the_share_ttl_is_the_link_ttl() -> None:
    assert SHARE_TTL == DOCTOR_LINK_TTL == timedelta(hours=72)


def test_an_early_send_lives_until_the_appointment_window_closes() -> None:
    schedule = VisitSchedule(date=dt.date(2026, 11, 10), time=AT_1430)
    expires = share_expires_at(schedule, SENT)
    assert expires == visit_instant(schedule) + timedelta(hours=72)
    # the defect: the old send-anchored share died days before the visit
    assert expires - (SENT + SHARE_TTL) > timedelta(days=6)
    assert SENT + SHARE_TTL < visit_instant(schedule)


def test_a_visit_without_an_hour_anchors_on_the_start_of_its_day() -> None:
    schedule = VisitSchedule(date=dt.date(2026, 11, 10), time=None)
    start_of_day_tr = datetime(2026, 11, 10, tzinfo=dt.timezone(timedelta(hours=3)))
    assert share_expires_at(schedule, SENT) == start_of_day_tr + timedelta(hours=72)


def test_near_miss_a_send_after_the_appointment_keeps_the_send_window() -> None:
    """Never shorter than before: a late send is not born dead."""
    schedule = VisitSchedule(date=dt.date(2026, 10, 20), time=AT_1430)
    assert share_expires_at(schedule, SENT) == SENT + SHARE_TTL


def test_near_miss_a_send_inside_the_window_takes_the_later_instant() -> None:
    schedule = VisitSchedule(date=dt.date(2026, 11, 1), time=AT_1430)
    # the appointment is the same day, after the send: its window is later
    assert share_expires_at(schedule, SENT) == visit_instant(schedule) + SHARE_TTL


def test_an_undated_visit_keeps_the_send_window() -> None:
    assert share_expires_at(None, SENT) == SENT + SHARE_TTL


def test_the_rule_refuses_a_naive_send_instant() -> None:
    with pytest.raises(ValueError, match="aware"):
        share_expires_at(None, datetime(2026, 11, 1, 9, 0))  # noqa: DTZ001


# --- the rule, on the note route and the reschedule -----------------------------------


@pytest.fixture()
def clock() -> Clock:
    return Clock(T0)


@pytest.fixture()
def api(tmp_path: Path, clock: Clock) -> Iterator[ApiHarness]:
    redis = fakeredis.FakeRedis()
    auth = AuthWiring(
        redis_client=redis,
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
        safety_inbox=SafetyInbox(store=RedisSafetyInboxStore(fakeredis.FakeStrictRedis())),
    )
    harness = next(harnesses)
    harness.client.app.state.api.clock = clock  # type: ignore[attr-defined]
    yield harness
    for _ in harnesses:
        pass


def _shares(api: ApiHarness, visit_id: str) -> list[Share]:
    async def _load() -> list[Share]:
        async with AsyncSession(api.engine) as session:
            note_id = await session.scalar(
                select(Note.id).where(Note.session_id == uuid.UUID(visit_id))
            )
            rows = await session.scalars(select(Share).where(Share.note_id == note_id))
            return list(rows)

    loaded: list[Share] = run(_load())
    return loaded


def _future(days: int, *, hour: str | None = "14:30") -> dict[str, Any]:
    day = (datetime.now(UTC) + timedelta(days=days)).date().isoformat()
    body: dict[str, Any] = {
        "hospital": "Sentetik Hastane",
        "department": "Kardiyoloji",
        "date": day,
    }
    if hour is not None:
        body["time"] = hour
        body["time_source"] = "patient_entry"
    return body


def _schedule(body: dict[str, Any]) -> VisitSchedule:
    time = None
    if "time" in body:
        hh, mm = (int(part) for part in body["time"].split(":"))
        time = VisitTime(at=dt.time(hh, mm), source=VisitTimeSource.PATIENT_ENTRY)
    return VisitSchedule(date=dt.date.fromisoformat(body["date"]), time=time)


def test_a_note_sent_ten_days_early_shares_until_the_visit_window(api: ApiHarness) -> None:
    body = _future(10)
    visit_id = visit(api, body)
    send_note(api, visit_id)
    [share] = _shares(api, visit_id)
    assert aware(share.expires_at) == visit_instant(_schedule(body)) + SHARE_TTL


def test_an_undated_visit_shares_for_seventy_two_hours_from_the_send(api: ApiHarness) -> None:
    visit_id = visit(api, {"hospital": "Sentetik Hastane", "department": "Kardiyoloji"})
    before = datetime.now(UTC)
    send_note(api, visit_id)
    [share] = _shares(api, visit_id)
    expires = aware(share.expires_at)
    assert before + SHARE_TTL <= expires <= datetime.now(UTC) + SHARE_TTL


def test_a_reschedule_moves_a_live_share_with_the_visit(api: ApiHarness) -> None:
    body = _future(10)
    visit_id = visit(api, body)
    send_note(api, visit_id)
    later = _future(20)
    assert (
        move(
            api,
            visit_id,
            to="rescheduled",
            date=later["date"],
            time=later["time"],
            time_source="patient_entry",
        ).status_code
        == 200
    )
    [share] = _shares(api, visit_id)
    assert aware(share.expires_at) == visit_instant(_schedule(later)) + SHARE_TTL
    repins = [e for e in api.audit_store.entries() if e.action == "api.note.share_expiry_repinned"]
    assert [e.resource_ref for e in repins] == [f"share:{share.id}"]


def test_near_miss_a_reschedule_earlier_never_cuts_below_the_send_window(
    api: ApiHarness,
) -> None:
    body = _future(10)
    visit_id = visit(api, body)
    # whole seconds: SQLite stores the share's created_at without microseconds
    before_send = datetime.now(UTC).replace(microsecond=0)
    send_note(api, visit_id)
    # the visit moves to today in Türkiye, no hour: it anchors on the start of
    # today, before the send, so its window ends before send + 72 h
    earlier = {"date": datetime.now(TR).date().isoformat()}
    assert visit_instant(_schedule(earlier)) + SHARE_TTL < before_send + SHARE_TTL
    moved = move(api, visit_id, to="rescheduled", date=earlier["date"])
    assert moved.status_code == 200, moved.text
    [share] = _shares(api, visit_id)
    assert aware(share.expires_at) >= before_send + SHARE_TTL
    assert share.revoked_at is None


def test_near_miss_a_revoked_share_is_not_revived_by_a_reschedule(api: ApiHarness) -> None:
    body = _future(10)
    visit_id = visit(api, body)
    send_note(api, visit_id)
    # a draft save takes the note back and revokes its share (notes.write_note)
    draft = api.client.put(
        f"/v1/visits/{visit_id}/note",
        json={**NOTE_BODY, "status": "draft"},
        headers=api.patient(),
    )
    assert draft.status_code == 200, draft.text
    [revoked] = _shares(api, visit_id)
    before = aware(revoked.expires_at)
    later = _future(20)
    assert (
        move(
            api,
            visit_id,
            to="rescheduled",
            date=later["date"],
            time=later["time"],
            time_source="patient_entry",
        ).status_code
        == 200
    )
    [row] = _shares(api, visit_id)
    assert row.revoked_at is not None
    assert aware(row.expires_at) == before

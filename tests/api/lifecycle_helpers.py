"""Shared doubles and helpers for the INT-407 visit lifecycle API suites
(``test_visit_lifecycle.py`` here, ``tests/safety/test_red_visit_transition.py``).

One clock for the API (``ApiState.clock``) and for the Doctor Link tier
(``AuthWiring.now_fn``), so a test advances time instead of sleeping and the two
halves of one decision can never disagree.
"""

from __future__ import annotations

import datetime as dt
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from api_harness import ApiHarness, run
from clinical_schemas.visit_time import VisitSchedule, VisitTime, VisitTimeSource
from intake_platform.db.models import DoctorLink, Slot
from intake_platform.visit_lifecycle import LIFECYCLE_SLOT, VisitLifecycle
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

TR = ZoneInfo("Europe/Istanbul")
T0 = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
SCHEDULE = VisitSchedule(
    date=dt.date(2026, 9, 20),
    time=VisitTime(at=dt.time(14, 30), source=VisitTimeSource.PATIENT_ENTRY),
)


def instant(schedule: VisitSchedule) -> datetime:
    at = schedule.time.at if schedule.time is not None else dt.time.min
    return datetime.combine(schedule.date, at, tzinfo=TR).astimezone(UTC)


class Clock:
    def __init__(self, at: datetime) -> None:
        self.now = at

    def advance(self, delta: timedelta) -> None:
        self.now += delta

    def __call__(self) -> datetime:
        return self.now

    def epoch(self) -> float:
        return self.now.timestamp()


VISIT_BODY = {
    "hospital": "Ankara Şehir Hastanesi",
    "department": "İç Hastalıkları",
    "date": "2026-09-20",
    "time": "14:30",
    "time_source": "patient_entry",
}
NOTE_BODY: dict[str, Any] = {
    "sections": [
        {"id": "chief_complaint", "title": "Başvuru nedeni", "lines": ["Sentetik şikâyet"]},
        {"id": "hpi", "title": "Şikâyet öyküsü", "lines": ["Sentetik öykü"]},
    ],
    "scopes": {},
    "status": "sent",
}


def visit(api: ApiHarness, body: dict[str, Any] | None = None) -> str:
    response = api.client.post("/v1/visits", json=body or VISIT_BODY, headers=api.patient())
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def move(api: ApiHarness, visit_id: str, **body: Any) -> Any:
    return api.client.post(f"/v1/visits/{visit_id}/transitions", json=body, headers=api.patient())


def read(api: ApiHarness, visit_id: str, headers: dict[str, str] | None = None) -> Any:
    response = api.client.get(f"/v1/visits/{visit_id}", headers=headers or api.patient())
    assert response.status_code == 200, response.text
    return response.json()


def lifecycle(api: ApiHarness, visit_id: str) -> VisitLifecycle:
    async def _load() -> dict[str, Any] | None:
        async with AsyncSession(api.engine) as session:
            row = await session.scalar(
                select(Slot).where(
                    Slot.session_id == uuid.UUID(visit_id), Slot.slot_id == LIFECYCLE_SLOT
                )
            )
            return dict(row.value) if row is not None else None

    return VisitLifecycle.from_slot(run(_load()))


def send_note(api: ApiHarness, visit_id: str) -> None:
    response = api.client.put(f"/v1/visits/{visit_id}/note", json=NOTE_BODY, headers=api.patient())
    assert response.status_code == 200, response.text


def issue_link(api: ApiHarness, visit_id: str) -> dict[str, Any]:
    response = api.client.post(
        f"/v1/visits/{visit_id}/note/doctor-links",
        json={"recipient": "Dr. Sentetik"},
        headers=api.patient(),
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def link_row(api: ApiHarness, link_id: str) -> DoctorLink:
    async def _load() -> DoctorLink:
        async with AsyncSession(api.engine) as session:
            row = await session.scalar(
                select(DoctorLink).where(DoctorLink.id == uuid.UUID(link_id))
            )
            assert row is not None
            return row

    loaded: DoctorLink = run(_load())
    return loaded


def aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def open_link(api: ApiHarness, clock: Clock, visit_id: str, issued: dict[str, Any]) -> Any:
    minted = api.client.post(
        f"/v1/visits/{visit_id}/note/doctor-links/{issued['link_id']}/otp",
        headers=api.patient(),
    )
    if minted.status_code != 200:
        return minted
    clock.advance(timedelta(minutes=2))
    return api.client.post(
        "/v1/doctor-link/view", json={"token": issued["token"], "code": minted.json()["code"]}
    )

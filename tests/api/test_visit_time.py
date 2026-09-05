"""INT-306 — the visit carries a TIME of day, or says it does not.

files/02 §2b pins Doctor Link expiry to ``visit_datetime + 72 h``. The schema
recorded a ``visit.date`` slot and no time of day, so INT-150 anchored on the
START of the visit day (never later than the appointment, therefore never
later than the spec's value) and INT-122's MHRS reader parsed an appointment
time it then had nowhere to put. Two issues reached the same missing field
from opposite ends; this file pins the field.

The three properties under test, one per acceptance clause:

1. **A known time is carried; an unknown time stays unknown.** ``00:00`` typed
   by a patient and "no time recorded" must not read back the same, because a
   defaulted midnight is indistinguishable from a real midnight appointment
   and silently shortens every later link by up to a day. The two produce the
   same *expiry instant* — necessarily, they are the same anchor — so the
   distinction has to survive in the STORED value, which is what is asserted.

2. **Every producer says which it is.** ``VisitTimeSource`` is closed over the
   three the issue enumerates — patient entry, a connector field, a document
   extraction — and the two that are not the patient's own typing must name
   the artefact they were read from. An extracted time arriving unattributed
   is not a case to reject at the boundary; it cannot be constructed.

3. **Nothing is invented.** Every refusal below leaves the field ABSENT rather
   than filled with a plausible clock (CLAUDE.md invariant 17, HB rule 1).

Near-miss negative controls, each named where it lives:

- ``test_a_real_midnight_is_not_the_absent_time`` — the defect the first
  acceptance clause describes, and the one an implementation that defaults to
  ``time.min`` passes every other test in this file with;
- ``test_the_api_refuses_an_attributed_source_with_no_ref`` and
  ``test_the_api_refuses_a_ref_the_patient_typed_a_time_for`` — provenance in
  both directions at the wire boundary, so "always require a ref" and "never
  require one" both fail. Their type-level halves, which prove the same two
  states are unconstructible rather than merely rejected, live in
  ``tests/schemas/test_visit_time_vocabulary.py``;
- ``test_a_time_that_is_not_hh_mm_is_refused`` — ``9:30``, ``14:30:00`` and
  ``24:00`` all denote something a lenient parser would accept, and accepting
  two spellings of one minute is the representation slack invariant 22 exists
  to stop;
- ``test_a_dated_visit_with_no_time_is_still_created`` — the control that must
  still be ACCEPTED: the fallback path INT-150 built is not broken by adding
  the field it was standing in for.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from api_harness import ApiHarness, run
from clinical_schemas.visit_time import VisitTimeSource
from intake_platform.db.models import Slot
from intake_platform.records.mhrs import BranchVocabulary, parse_mhrs_sms
from intake_platform.records.visit_candidate import (
    CandidateVisitFields,
    confirm_visit_candidate,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

DATE = "2026-09-20"
BASE = {"hospital": "Ankara Şehir Hastanesi", "department": "İç Hastalıkları", "date": DATE}
SCREENSHOT = "document:11111111-1111-4111-8111-111111111111"


def _post(harness: ApiHarness, **overrides: object) -> object:
    return harness.client.post("/v1/visits", json={**BASE, **overrides}, headers=harness.patient())


def _slots(harness: ApiHarness, visit_id: uuid.UUID) -> dict[str, dict[str, object]]:
    async def _rows() -> dict[str, dict[str, object]]:
        async with AsyncSession(harness.engine) as session:
            rows = (await session.scalars(select(Slot).where(Slot.session_id == visit_id))).all()
            return {slot.slot_id: dict(slot.value) for slot in rows}

    return run(_rows())


# --- 1. a known time is carried, an unknown time stays unknown ------------------------


def test_a_patient_entered_time_round_trips_through_the_api(harness: ApiHarness) -> None:
    created = _post(harness, time="14:30", time_source="patient_entry")
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["time"] == "14:30"
    assert body["time_source"] == "patient_entry"
    assert body["time_source_ref"] is None

    read = harness.client.get(f"/v1/visits/{body['id']}", headers=harness.patient())
    assert read.status_code == 200
    assert read.json() == body


def test_the_time_persists_as_one_more_visit_slot(harness: ApiHarness) -> None:
    """INT-134's precedent: a new visit fact is a new row in the already
    inventoried ``slots`` table — no new tables, no new columns (invariant 18)."""
    created = _post(harness, time="14:30", time_source="patient_entry")
    assert created.status_code == 201, created.text
    slots = _slots(harness, uuid.UUID(str(created.json()["id"])))
    assert slots["visit.time"] == {"time": "14:30", "source": "patient_entry"}


def test_a_dated_visit_with_no_time_is_still_created(harness: ApiHarness) -> None:
    """CONTROL that must stay ACCEPTED — the INT-150 fallback path still works
    and writes NO time slot rather than a defaulted one."""
    created = _post(harness)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["date"] == DATE
    assert body["time"] is None
    assert body["time_source"] is None
    assert "visit.time" not in _slots(harness, uuid.UUID(str(body["id"])))


def test_a_real_midnight_is_not_the_absent_time(harness: ApiHarness) -> None:
    """NEAR-MISS: an implementation that defaults an unknown time to midnight
    passes every expiry assertion in this repo and still loses the difference
    between "booked for 00:00" and "we do not know" — which is what silently
    shortens a link by up to a day for the 23:30 appointment next to it."""
    midnight = _post(harness, time="00:00", time_source="patient_entry")
    assert midnight.status_code == 201, midnight.text
    assert midnight.json()["time"] == "00:00"
    assert _slots(harness, uuid.UUID(str(midnight.json()["id"])))["visit.time"] == {
        "time": "00:00",
        "source": "patient_entry",
    }

    unknown = _post(harness)
    assert unknown.status_code == 201, unknown.text
    assert unknown.json()["time"] is None
    assert "visit.time" not in _slots(harness, uuid.UUID(str(unknown.json()["id"])))


def test_a_time_with_no_date_is_refused(harness: ApiHarness) -> None:
    """A time of day is not a schedule. Storing one against no date would give
    the expiry rule a half-anchor it must then guess the other half of."""
    response = harness.client.post(
        "/v1/visits",
        json={"hospital": "H", "department": "D", "time": "14:30", "time_source": "patient_entry"},
        headers=harness.patient(),
    )
    assert response.status_code == 422
    assert response.json() == {"error": "time_without_date"}


def test_a_time_that_is_not_hh_mm_is_refused(harness: ApiHarness) -> None:
    """NEAR-MISS: ``9:30`` and ``14:30:00`` denote real minutes and ``24:00``
    denotes a real instant under a lenient reading. Invariant 22 — one spelling
    per value at a representation boundary, positional digits, no grouping."""
    for bad in ("9:30", "14:30:00", "24:00", "14:60", "2:30 PM", "14.30", "1430", ""):
        response = _post(harness, time=bad, time_source="patient_entry")
        assert response.status_code == 422, bad
        assert response.json() == {"error": "bad_time"}, bad


# --- 2. every producer says which it is ----------------------------------------------


@pytest.mark.parametrize("source", list(VisitTimeSource))
def test_every_enumerated_producer_has_a_working_door(
    harness: ApiHarness, source: VisitTimeSource
) -> None:
    """Driven off the enum itself, so a member added without a path that can
    actually write it fails here rather than sitting in the vocabulary as a
    provenance nothing produces."""
    ref = None if source is VisitTimeSource.PATIENT_ENTRY else SCREENSHOT
    created = _post(harness, time="08:05", time_source=source.value, time_source_ref=ref)
    assert created.status_code == 201, created.text
    body = created.json()
    assert (body["time"], body["time_source"], body["time_source_ref"]) == (
        "08:05",
        source.value,
        ref,
    )


def test_a_time_without_a_producer_is_refused(harness: ApiHarness) -> None:
    assert _post(harness, time="14:30").status_code == 422
    assert _post(harness, time="14:30").json() == {"error": "time_source_required"}


def test_a_producer_without_a_time_is_refused(harness: ApiHarness) -> None:
    """Provenance for nothing is not a partial record; it is a claim that a
    reading happened, with the reading missing."""
    assert _post(harness, time_source="patient_entry").status_code == 422
    assert _post(harness, time_source="patient_entry").json() == {
        "error": "time_source_without_time"
    }


def test_an_unknown_producer_is_refused(harness: ApiHarness) -> None:
    response = _post(harness, time="14:30", time_source="a_hunch")
    assert response.status_code == 422
    assert response.json() == {"error": "time_source_unknown"}


def test_a_connector_time_round_trips_with_its_artefact(harness: ApiHarness) -> None:
    """The MHRS/e-Nabız connector field the issue enumerates. No connector in
    this repository produces one yet; the door it will arrive through is here,
    so it does not have to invent a provenance vocabulary when it lands."""
    created = _post(
        harness,
        time="09:15",
        time_source="connector_field",
        time_source_ref="mhrs:appointment:abc",
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert (body["time"], body["time_source"], body["time_source_ref"]) == (
        "09:15",
        "connector_field",
        "mhrs:appointment:abc",
    )
    assert _slots(harness, uuid.UUID(str(body["id"])))["visit.time"] == {
        "time": "09:15",
        "source": "connector_field",
        "source_ref": "mhrs:appointment:abc",
    }


def test_the_api_refuses_an_attributed_source_with_no_ref(harness: ApiHarness) -> None:
    response = _post(harness, time="09:15", time_source="connector_field")
    assert response.status_code == 422
    assert response.json() == {"error": "time_source_ref_required"}


def test_the_api_refuses_a_ref_the_patient_typed_a_time_for(harness: ApiHarness) -> None:
    response = _post(harness, time="09:15", time_source="patient_entry", time_source_ref=SCREENSHOT)
    assert response.status_code == 422
    assert response.json() == {"error": "time_source_ref_refused"}


# --- 2b. the extraction producer, end to end -----------------------------------------


def test_the_screenshot_time_reaches_the_visit_fields_attributed() -> None:
    """INT-122 parsed ``14:30`` off the message and ``as_visit_fields`` dropped
    it, because the API had no field for it. It has one now, and the provenance
    is DERIVED from the candidate rather than passed in — the same shape
    ``Confirmation.source_ref`` already has."""
    candidate = CandidateVisitFields(
        document_ref=SCREENSHOT,
        branch_id="kardiyoloji",
        date=dt.date(2026, 9, 13),
        time=dt.time(14, 30),
    )
    fields = confirm_visit_candidate(
        candidate,
        hospital="Acıbadem Maslak",
        visit_type="followup",
        at=dt.datetime(2026, 9, 1, 9, 0, tzinfo=dt.UTC),
    ).as_visit_fields()
    assert fields.date == "2026-09-13"
    assert fields.time == "14:30"
    assert fields.time_source == VisitTimeSource.DOCUMENT_EXTRACTION.value
    assert fields.time_source_ref == SCREENSHOT


def test_a_screenshot_that_stated_no_time_carries_no_provenance_either() -> None:
    """CONTROL: the refusal INT-122 already records stays a refusal. Nothing
    downstream may read "the reader tried and found nothing" as a time."""
    candidate = CandidateVisitFields(
        document_ref=SCREENSHOT, branch_id="kardiyoloji", date=dt.date(2026, 9, 13)
    )
    fields = confirm_visit_candidate(
        candidate, hospital="H", visit_type=None, at=dt.datetime(2026, 9, 1, 9, 0, tzinfo=dt.UTC)
    ).as_visit_fields()
    assert fields.time is None
    assert fields.time_source is None
    assert fields.time_source_ref is None


def test_the_parsed_screenshot_fields_are_accepted_by_the_api(harness: ApiHarness) -> None:
    """The whole INT-122 → INT-306 path in one assertion: what the reader
    produces is what ``POST /v1/visits`` takes, with the time it read."""
    candidate = parse_mhrs_sms(
        "Kardiyoloji 13.09.2026 14:30",
        document_ref=SCREENSHOT,
        vocabulary=BranchVocabulary.from_names({"Kardiyoloji": "kardiyoloji"}),
    )
    fields = confirm_visit_candidate(
        candidate,
        hospital="Acıbadem Maslak",
        visit_type="followup",
        at=dt.datetime(2026, 9, 1, 9, 0, tzinfo=dt.UTC),
    ).as_visit_fields()
    created = harness.client.post(
        "/v1/visits",
        json={
            "hospital": fields.hospital,
            "department": "Kardiyoloji",
            "date": fields.date,
            "time": fields.time,
            "time_source": fields.time_source,
            "time_source_ref": fields.time_source_ref,
        },
        headers=harness.patient(),
    )
    assert created.status_code == 201, created.text
    assert created.json()["time"] == "14:30"
    assert created.json()["time_source"] == "document_extraction"

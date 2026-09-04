"""INT-306 — the visit-time vocabulary itself: unconstructible states.

``tests/api/test_visit_time.py`` proves the field travels — API body, ``slots``
row, INT-122's extraction, the Doctor Link anchor. This file proves the half of
the issue the type system carries, with no API and no database in the way:

* a producer set closed over the three the issue enumerates;
* a time read off an artefact that cannot be written down without naming it,
  and a time the patient typed that cannot borrow one;
* one spelling per value at the ``HH:MM`` boundary (invariant 22);
* an unknown hour as a first-class recorded state rather than a defaulted
  midnight that no later reader can tell from a real 00:00 booking.

Every case here is a **construction** that must raise, not a validator that must
return False — which is the point of the frozen dataclass. A value this file
says is impossible has no code path that produces it, so no boundary anywhere
has to remember to check for it.
"""

from __future__ import annotations

import datetime as dt

import pytest
from clinical_schemas.visit_time import (
    ATTRIBUTED_SOURCES,
    VisitSchedule,
    VisitTime,
    VisitTimeError,
    VisitTimeSource,
    parse_visit_time,
)

REF = "document:11111111-1111-4111-8111-111111111111"


# --- the producer set ----------------------------------------------------------------


def test_the_producers_are_a_closed_set_of_three() -> None:
    """The issue enumerates them. A fourth is a deliberate edit here rather than
    a string somebody passed in at a boundary."""
    assert {member.value for member in VisitTimeSource} == {
        "patient_entry",
        "connector_field",
        "document_extraction",
    }


def test_the_two_sources_whose_evidence_is_an_artefact_are_named_once() -> None:
    """The split is data, not an ``if`` repeated at three call sites: the store,
    the API validator and the extraction projection all read this one set."""
    assert ATTRIBUTED_SOURCES == {
        VisitTimeSource.CONNECTOR_FIELD,
        VisitTimeSource.DOCUMENT_EXTRACTION,
    }
    assert VisitTimeSource.PATIENT_ENTRY not in ATTRIBUTED_SOURCES


# --- provenance, from both sides -----------------------------------------------------


@pytest.mark.parametrize("source", sorted(ATTRIBUTED_SOURCES))
def test_a_time_read_off_an_artefact_cannot_be_written_down_unattributed(
    source: VisitTimeSource,
) -> None:
    """NEAR-MISS in one direction. ``source_ref`` is required and defaultless,
    the shape ``SourceBox`` and ``Confirmation`` already use — so an extracted
    time arriving unattributed is not a case to reject, it is unconstructible."""
    with pytest.raises(VisitTimeError):
        VisitTime(at=dt.time(14, 30), source=source)
    with pytest.raises(VisitTimeError):
        VisitTime(at=dt.time(14, 30), source=source, source_ref="   ")
    assert VisitTime(at=dt.time(14, 30), source=source, source_ref=REF).source_ref == REF


def test_a_patient_entry_may_not_borrow_an_artefact() -> None:
    """NEAR-MISS in the other direction, so "always require a ref" fails too: a
    patient typing a time read it off nothing this repository holds, and a ref
    attached to it would claim an artefact was consulted."""
    with pytest.raises(VisitTimeError):
        VisitTime(at=dt.time(14, 30), source=VisitTimeSource.PATIENT_ENTRY, source_ref=REF)
    assert VisitTime(at=dt.time(14, 30), source=VisitTimeSource.PATIENT_ENTRY).source_ref is None


def test_no_refusal_message_echoes_the_time_it_refused() -> None:
    """Invariant 6: an exception message reaches a log and an appointment hour
    is patient content. Every message here names the rule."""
    with pytest.raises(VisitTimeError) as raised:
        VisitTime(at=dt.time(23, 45), source=VisitTimeSource.DOCUMENT_EXTRACTION)
    assert "23" not in str(raised.value)
    assert "45" not in str(raised.value)


# --- one spelling per value (invariant 22) -------------------------------------------


def test_the_wire_spelling_is_hh_mm_and_nothing_else() -> None:
    """NEAR-MISS: ``9:30`` and ``14:30:00`` denote real minutes and ``24:00``
    denotes a real instant under a lenient reading. ``time.fromisoformat``
    accepts two of them, which is exactly why it is not what is used."""
    for bad in (
        "9:30",
        "14:30:00",
        "14:30:00.5",
        "24:00",
        "14:60",
        "-1:00",
        "2:30 PM",
        "14.30",
        "1430",
        "14:3",
        "",
        "   ",
    ):
        with pytest.raises(VisitTimeError):
            parse_visit_time(bad, source=VisitTimeSource.PATIENT_ENTRY)


def test_the_accepted_spellings_round_trip_unchanged() -> None:
    for good, expected in (
        ("00:00", dt.time(0, 0)),
        ("08:05", dt.time(8, 5)),
        ("14:30", dt.time(14, 30)),
        ("23:59", dt.time(23, 59)),
    ):
        parsed = parse_visit_time(good, source=VisitTimeSource.PATIENT_ENTRY)
        assert parsed.at == expected
        assert parsed.render() == good


def test_surrounding_whitespace_is_trimmed_and_not_treated_as_a_second_spelling() -> None:
    assert parse_visit_time(" 14:30 ", source=VisitTimeSource.PATIENT_ENTRY).render() == "14:30"


def test_the_parse_carries_provenance_through_to_the_same_rules() -> None:
    parsed = parse_visit_time(
        "09:15", source=VisitTimeSource.CONNECTOR_FIELD, source_ref="mhrs:appointment:abc"
    )
    assert parsed.source is VisitTimeSource.CONNECTOR_FIELD
    assert parsed.source_ref == "mhrs:appointment:abc"
    with pytest.raises(VisitTimeError):
        parse_visit_time("09:15", source=VisitTimeSource.CONNECTOR_FIELD)


def test_a_visit_time_is_a_civil_time_with_no_zone_and_no_seconds() -> None:
    """The zone belongs to the visit's calendar date and is applied once, at the
    expiry anchor. A tz-bearing or second-bearing time here would be a second
    opinion about the same instant."""
    for impossible in (dt.time(14, 30, tzinfo=dt.UTC), dt.time(14, 30, 15), dt.time(14, 30, 0, 1)):
        with pytest.raises(VisitTimeError):
            VisitTime(at=impossible, source=VisitTimeSource.PATIENT_ENTRY)


def test_a_visit_time_cannot_be_re_pointed_after_construction() -> None:
    """Frozen: a caller cannot walk an unattributed reading in through a later
    assignment either — the same property ``ConfirmedVisitFields`` relies on."""
    known = VisitTime(at=dt.time(14, 30), source=VisitTimeSource.PATIENT_ENTRY)
    with pytest.raises(AttributeError):
        known.source = VisitTimeSource.DOCUMENT_EXTRACTION  # type: ignore[misc]


# --- the schedule --------------------------------------------------------------------


def test_a_schedule_states_whether_its_time_is_known() -> None:
    """The absent time is a first-class state. What reads this is forced to say
    which of the two anchor rules it is applying, instead of receiving a
    midnight it cannot tell from a booking."""
    known = VisitSchedule(
        date=dt.date(2026, 9, 20),
        time=VisitTime(at=dt.time(14, 30), source=VisitTimeSource.PATIENT_ENTRY),
    )
    unknown = VisitSchedule(date=dt.date(2026, 9, 20))
    assert known.time_is_known is True
    assert unknown.time_is_known is False
    assert unknown.time is None


def test_a_real_midnight_is_a_known_time_and_not_an_absent_one() -> None:
    """NEAR-MISS, and the defect the first acceptance clause describes: the two
    schedules below denote the same anchor instant and must not be the same
    record, because a defaulted midnight silently shortens the 23:30 booking
    beside it by 23.5 h."""
    midnight = VisitSchedule(
        date=dt.date(2026, 9, 20),
        time=VisitTime(at=dt.time(0, 0), source=VisitTimeSource.PATIENT_ENTRY),
    )
    unknown = VisitSchedule(date=dt.date(2026, 9, 20))
    assert midnight != unknown
    assert midnight.time_is_known is not unknown.time_is_known

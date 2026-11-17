"""INT-400 — the server and the device read an MHRS date by one rule.

INT-122 (PR #663, docs/evidence/INT-122.md §10.4) found two MHRS parsers with
opposite date rules. The server's guard refuses ``03.09.2026`` as
``PrintedDateAmbiguous``, because no committed source states the order an MHRS
SMS prints. INT-134's device parser read the same string day-first, as
3 September. The same pasted message gave a date on the device and a refusal
on the server. A visit date read the wrong way round books the wrong day, and
nothing on the screen shows that it is wrong.

The fix makes the device port the server's rule. This file holds the **server**
to the shared table, ``tests/fixtures/records/mhrs_dates.json``.
``apps/mobile/src/lib/taxonomy/turkishDates.test.ts`` and ``mhrsSms.test.ts``
hold the device to the same rows. Neither side can change the rule alone:

* every ``printed`` row is one value through ``parse_printed_date``, with the
  row's ``order`` (``null`` everywhere except the three rows that exercise the
  seam);
* every ``messages`` row is a whole pasted message through ``parse_mhrs_sms``,
  and only its date field and date refusal are compared;
* the table has to keep the cases that make it a guard. It needs INT-134's own
  ``03.09.2026``, a near-miss that is **not** ambiguous (``13.09.2026``), every
  refusal class, and both kinds of row;
* the app's tests have to keep reading this file.

When INT-399 fixes the order from a real sample, the rows here change, and both
parsers fail until both change (issue #666, second acceptance line).
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from intake_platform.records.mhrs import BranchVocabulary, parse_mhrs_sms
from intake_platform.records.turkish_dates import (
    DateOrder,
    PrintedDateAmbiguous,
    PrintedDateNotFound,
    PrintedDateUnreadable,
    parse_printed_date,
)
from intake_platform.records.visit_candidate import VisitFieldRefusal
from protocols.taxonomy import load_taxonomy

ROOT = Path(__file__).resolve().parents[2]
TABLE_PATH = ROOT / "tests" / "fixtures" / "records" / "mhrs_dates.json"
BRANCHES_YAML = ROOT / "packages" / "protocols" / "taxonomy" / "branches.yaml"
MOBILE_TAXONOMY = ROOT / "apps" / "mobile" / "src" / "lib" / "taxonomy"
SCREENSHOT = "document:mhrs-sms-400"

TABLE: dict[str, Any] = json.loads(TABLE_PATH.read_text(encoding="utf-8"))
PRINTED: list[dict[str, Any]] = TABLE["printed"]
MESSAGES: list[dict[str, Any]] = TABLE["messages"]


def _vocabulary() -> BranchVocabulary:
    taxonomy = load_taxonomy(BRANCHES_YAML)
    return BranchVocabulary.from_names({branch.name_tr: branch.id for branch in taxonomy.branches})


def _outcome(read: Callable[[], dt.date]) -> dict[str, str]:
    """The fixture's spelling of one read: a date, or the refusal it raised.

    The order of the ``except`` arms is ``mhrs.parse_mhrs_sms``'s own:
    ``PrintedDateAmbiguous`` and ``PrintedDateNotFound`` are both subclasses of
    ``PrintedDateUnreadable``, so the specific classes are named first.
    """
    try:
        return {"date": read().isoformat()}
    except PrintedDateAmbiguous:
        return {"refusal": VisitFieldRefusal.AMBIGUOUS.value}
    except PrintedDateNotFound:
        return {"refusal": VisitFieldRefusal.NOT_FOUND.value}
    except PrintedDateUnreadable:
        return {"refusal": VisitFieldRefusal.UNREADABLE.value}


def _order(row: dict[str, Any]) -> DateOrder | None:
    return None if row["order"] is None else DateOrder(row["order"])


class TestTheServerReadsEveryRowAsTheTableSays:
    @pytest.mark.parametrize("row", PRINTED, ids=[row["id"] for row in PRINTED])
    def test_one_printed_value(self, row: dict[str, Any]) -> None:
        got = _outcome(lambda: parse_printed_date(row["printed"], order=_order(row)))
        assert got == row["expect"]

    @pytest.mark.parametrize("row", MESSAGES, ids=[row["id"] for row in MESSAGES])
    def test_one_pasted_message(self, row: dict[str, Any]) -> None:
        candidate = parse_mhrs_sms(row["text"], document_ref=SCREENSHOT, vocabulary=_vocabulary())
        date_refusals = [
            refusal.split(":", 1)[1]
            for refusal in candidate.refusals
            if refusal.startswith("date:")
        ]
        if candidate.date is not None:
            assert date_refusals == []
            got = {"date": candidate.date.isoformat()}
        else:
            assert len(date_refusals) == 1
            got = {"refusal": date_refusals[0]}
        assert got == row["expect"]


class TestTheTableKeepsTheCasesThatMakeItAGuard:
    """A shared table that lost its hard rows would still pass on both sides.
    These pins stop it from shrinking into agreement about nothing."""

    def test_row_ids_are_unique(self) -> None:
        for rows in (PRINTED, MESSAGES):
            ids = [row["id"] for row in rows]
            assert len(ids) == len(set(ids))

    def test_every_expectation_is_a_date_or_a_named_refusal(self) -> None:
        refusals = {member.value for member in VisitFieldRefusal}
        for row in PRINTED + MESSAGES:
            expect = row["expect"]
            assert len(expect) == 1
            if "date" in expect:
                assert dt.date.fromisoformat(expect["date"]).isoformat() == expect["date"]
            else:
                assert expect["refusal"] in refusals

    def test_int134s_own_fixture_is_held_as_ambiguous(self) -> None:
        """The finding itself (INT-122 §10.4): the date INT-134's tests read
        day-first is ambiguous in both kinds of row."""
        assert {"refusal": "ambiguous"} in [
            row["expect"] for row in PRINTED if row["printed"] == "03.09.2026"
        ]
        assert any(
            "03.09.2026" in row["text"] and row["expect"] == {"refusal": "ambiguous"}
            for row in MESSAGES
        )

    def test_the_near_miss_controls_resolve(self) -> None:
        """Refusing everything would also pass the ambiguous rows. A day above
        twelve, and a day equal to its month, have one reading and are read."""
        wanted = {("13.09.2026", "2026-09-13"), ("05.05.2026", "2026-05-05")}
        printed = {
            (row["printed"], row["expect"].get("date")) for row in PRINTED if row["order"] is None
        }
        assert wanted <= printed
        assert {"2026-09-13", "2026-05-05"} <= {row["expect"].get("date") for row in MESSAGES}

    def test_every_refusal_class_appears(self) -> None:
        classes = {member.value for member in VisitFieldRefusal}
        assert {row["expect"].get("refusal") for row in MESSAGES} >= classes
        assert {row["expect"].get("refusal") for row in PRINTED} >= classes - {"not_found"}

    def test_the_seam_rows_are_the_only_rows_with_an_order(self) -> None:
        """No order is stated for an MHRS SMS, so every message row and every
        other printed row is read with none."""
        ordered = [row for row in PRINTED if row["order"] is not None]
        assert {row["order"] for row in ordered} == {member.value for member in DateOrder}
        assert all(row["id"].startswith("seam_") for row in ordered)
        assert all("order" not in row for row in MESSAGES)


class TestTheAppIsHeldToTheSameTable:
    def test_the_device_tests_read_this_same_file(self) -> None:
        dates = (MOBILE_TAXONOMY / "turkishDates.test.ts").read_text(encoding="utf-8")
        assert '"mhrs_dates.json"' in dates
        assert "parsePrintedDate(" in dates
        sms = (MOBILE_TAXONOMY / "mhrsSms.test.ts").read_text(encoding="utf-8")
        assert '"mhrs_dates.json"' in sms
        assert "parseMhrsSms(" in sms
        # the form: a pasted message never leaves an earlier date in the field
        form = (MOBILE_TAXONOMY.parent / "visits.test.ts").read_text(encoding="utf-8")
        assert '"mhrs_dates.json"' in form
        assert "parseMhrsSms(row.text" in form

"""INT-122 — e-Nabız export/PDF import parser + MHRS SMS screenshot OCR.

The acceptance line under test, verbatim (docs/backlog/issues.yaml INT-122):

    "patient-exported e-Nabiz documents parsed; MHRS SMS screenshot -> visit
     fields; no scraping of e-Nabiz (no third-party API exists; legal note
     enforced)"

sec_row: `records` (docs/security/threat-model.md "## `records` — patient
document upload and ingestion").

**Three sources, three trust profiles, and the tests are grouped by which one
they are about.** An e-Nabız export is structured data the patient obtained
from the state system and is still patient-supplied; a PDF is a *rendering*,
and whether one has a text layer at all is HB-A1, owner-only, which that row
names as blocking "INT-122's acceptance"; an MHRS SMS screenshot is an OCR of
a photograph of a text message, and a wrong appointment time read off one
sends a patient to the hospital on the wrong day.

So the property every class below is really testing is the same one: **when
this parser is unsure it produces nothing, and says which field it produced
nothing for.** A missing appointment is visible. A wrong one is not.

Everything Turkish here is what a *document* printed — a lab column header, a
booked branch name — never authored patient copy, so no `tr` resource key is
created (invariant 5 untouched, exactly as INT-121).
"""

from __future__ import annotations

import ast
import dataclasses
import datetime as dt
import inspect
import os
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml
from clinical_schemas.overlay import Confirmation, ConfirmingActor, LearnedFactSource
from clinical_schemas.records import RecordItemKind
from intake_platform.records import (
    ITEM_KEYS,
    DocumentBoundaryEscape,
    TextRegion,
    extract_record_items,
)
from intake_platform.records.enabiz import (
    CARRIED_COLUMNS,
    DROPPED_COLUMNS,
    LAB_TABLE_COLUMNS,
    LabTableParse,
    LabTableShapeUnrecognised,
    parse_lab_table,
)
from intake_platform.records.mhrs import (
    BranchNameAmbiguous,
    BranchVocabulary,
    parse_mhrs_sms,
    resolve_printed_branch,
)
from intake_platform.records.turkish_dates import (
    TURKISH_MONTHS,
    DateOrder,
    PrintedDateAmbiguous,
    PrintedDateNotFound,
    PrintedDateUnreadable,
    PrintedTimeAmbiguous,
    PrintedTimeNotFound,
    PrintedTimeUnreadable,
    find_printed_date,
    find_printed_time,
    parse_printed_date,
    parse_printed_time,
)
from intake_platform.records.visit_candidate import (
    CandidateVisitFields,
    ConfirmedVisitFields,
    VisitCandidateError,
    VisitFieldRefusal,
    confirm_visit_candidate,
)
from protocols.taxonomy import load_taxonomy

REPO_ROOT = Path(__file__).resolve().parents[2]
BRANCHES_YAML = REPO_ROOT / "packages" / "protocols" / "taxonomy" / "branches.yaml"
DOCUMENT = "document:enabiz-1"
SCREENSHOT = "document:mhrs-sms-1"
AT = dt.datetime(2026, 9, 3, 9, 0, tzinfo=dt.UTC)


# --------------------------------------------------------------------------------------------
# fixtures — every one synthesised (files/06 §5: CI carries no PHI)
# --------------------------------------------------------------------------------------------


def _cell(page: int, x0: float, x1: float, y0: float, y1: float, text: str, at: int) -> TextRegion:
    """One printed cell, with the geometry a layout stage would report."""
    return TextRegion(page=page, bbox=(x0, y0, x1, y1), start=at, end=at + len(text), text=text)


#: The six-column shape files/03 §10 says to expect in any post-2018 Turkish
#: report (the mandated *Akılcı Laboratuvar* table). Column x-ranges are the
#: fixture's own; nothing in the parser hard-codes a coordinate.
_COLUMN_X: dict[str, tuple[float, float]] = {
    "Tetkik Adı": (0.02, 0.24),
    "Sonuç": (0.26, 0.38),
    "Durum": (0.40, 0.50),
    "Birim": (0.52, 0.64),
    "Referans Aralığı": (0.66, 0.82),
    "Önceki Sonuçlar": (0.84, 0.98),
}


def _row(page: int, y: float, cells: dict[str, str], at: int) -> list[TextRegion]:
    regions: list[TextRegion] = []
    offset = at
    for column, text in cells.items():
        x0, x1 = _COLUMN_X[column]
        regions.append(_cell(page, x0, x1, y, y + 0.02, text, offset))
        offset += len(text) + 1
    return regions


def _header(page: int = 1, y: float = 0.10, at: int = 0) -> list[TextRegion]:
    return _row(page, y, {column: column for column in LAB_TABLE_COLUMNS}, at)


def _lab_document(
    rows: list[dict[str, str]] | None = None, *, page: int = 1
) -> tuple[TextRegion, ...]:
    body = rows if rows is not None else [_HAEMOGLOBIN]
    regions = _header(page=page)
    offset = 400
    for index, cells in enumerate(body):
        regions += _row(page, 0.20 + index * 0.05, cells, offset)
        offset += 200
    return tuple(regions)


_HAEMOGLOBIN: dict[str, str] = {
    "Tetkik Adı": "Hemoglobin",
    "Sonuç": "10,2",
    "Durum": "Düşük",
    "Birim": "g/dL",
    "Referans Aralığı": "12,0 - 16,0",
    "Önceki Sonuçlar": "11,4",
}


def _vocabulary() -> BranchVocabulary:
    taxonomy = load_taxonomy(BRANCHES_YAML)
    return BranchVocabulary.from_names({branch.name_tr: branch.id for branch in taxonomy.branches})


# --------------------------------------------------------------------------------------------
# Acceptance clause 1 — "patient-exported e-Nabiz documents parsed"
# --------------------------------------------------------------------------------------------


class TestTheExportIsParsedFromItsPrintedShapeNotItsProvenance:
    """files/03 §10 names the shape to expect — *"the mandated six-column
    Akılcı Laboratuvar shape (`Tetkik Adı ∣ Sonuç ∣ Durum ∣ Birim ∣ Referans
    Aralığı ∣ Önceki Sonuçlar`) in any post-2018 Turkish report"*.

    Nothing here claims to recognise e-Nabız *branding*: HB-A1 records that
    nobody on this project has seen an e-Nabız export, so a header-block
    signature would be invented. The parser reads a shape a committed source
    states, and refuses a document that does not have it.
    """

    def test_the_six_columns_are_the_ones_files_03_states(self) -> None:
        assert LAB_TABLE_COLUMNS == (
            "Tetkik Adı",
            "Sonuç",
            "Durum",
            "Birim",
            "Referans Aralığı",
            "Önceki Sonuçlar",
        )

    def test_a_lab_row_becomes_a_closed_key_set_item(self) -> None:
        parse = parse_lab_table(_lab_document())
        assert isinstance(parse, LabTableParse)
        (item,) = parse.completion["items"]
        assert set(item) <= ITEM_KEYS
        assert item["kind"] == RecordItemKind.LAB.value
        assert item["printed_name"] == "Hemoglobin"

    def test_the_parse_feeds_int_121_rather_than_replacing_it(self) -> None:
        """The whole point of the module: it produces the completion INT-121's
        parser already consumes, so the separator rule, the analyte guard and
        the unit-conflict flag are applied once, in one place."""
        parse = parse_lab_table(_lab_document())
        extraction = extract_record_items(
            parse.completion,
            document_ref=DOCUMENT,
            regions=parse.regions,
            observed_at=AT,
        )
        (extracted,) = extraction.items
        assert extracted.kind is RecordItemKind.LAB
        assert extracted.value_magnitude == Decimal("10.2")
        assert extracted.unit == "g/dL"

    def test_every_read_row_carries_a_box_that_covers_the_printed_row(self) -> None:
        parse = parse_lab_table(_lab_document())
        (item,) = parse.completion["items"]
        region = parse.regions[item["region"]]
        x0, y0, x1, y1 = region.bbox
        assert (x0, x1) == pytest.approx((0.02, 0.98))
        assert y1 > y0
        assert region.start < region.end

    def test_a_document_without_the_shape_is_refused_whole(self) -> None:
        """Not "no labs found" — that reads as a clean report."""
        loose = (
            _cell(1, 0.1, 0.4, 0.1, 0.12, "Hemoglobin", 0),
            _cell(1, 0.5, 0.7, 0.1, 0.12, "10,2", 20),
        )
        with pytest.raises(LabTableShapeUnrecognised):
            parse_lab_table(loose)

    def test_a_document_with_no_text_layer_is_refused(self) -> None:
        """HB-A1: *"Do not assume a text layer."* An empty region set is the
        `NoLayout`/`NoOcr` answer and it is a refusal, never an empty parse."""
        with pytest.raises(DocumentBoundaryEscape):
            parse_lab_table(())

    def test_a_second_page_repeating_the_header_is_read(self) -> None:
        page_one = list(_lab_document())
        page_two = list(_lab_document(page=2))
        parse = parse_lab_table(tuple(page_one + page_two))
        assert len(parse.completion["items"]) == 2

    def test_a_page_with_no_header_contributes_no_items_and_is_reported(self) -> None:
        page_one = list(_lab_document())
        orphan = _row(2, 0.2, _HAEMOGLOBIN, 900)
        parse = parse_lab_table(tuple(page_one + orphan))
        assert len(parse.completion["items"]) == 1
        assert parse.rows_unread == (1,)


class TestNoUnitAndNoMagnitudeIsTouchedBeforeTheGuardSeesIt:
    """CLAUDE.md invariant 22 at the ingestion crossing. INT-121 built the
    guard; a parser that normalises on the way in defeats it."""

    def test_the_printed_value_is_carried_as_the_string_that_was_printed(self) -> None:
        parse = parse_lab_table(_lab_document())
        (item,) = parse.completion["items"]
        assert item["printed_value"] == "10,2"
        assert not isinstance(item["printed_value"], float)

    def test_the_printed_unit_is_carried_verbatim_including_a_wrong_one(self) -> None:
        """files/03 §4.9.6's demonstrated case: a published handbook prints
        ALT in `U/mL` when the values are U/L. The magnitude outranks the
        token and the token still travels exactly as printed."""
        row = dict(_HAEMOGLOBIN, **{"Tetkik Adı": "ALT", "Sonuç": "30", "Birim": "U/mL"})
        parse = parse_lab_table(_lab_document([row]))
        (item,) = parse.completion["items"]
        assert item["printed_unit"] == "U/mL"

    def test_the_unit_conflict_flag_still_fires_through_this_parser(self) -> None:
        row = dict(_HAEMOGLOBIN, **{"Tetkik Adı": "ALT", "Sonuç": "30", "Birim": "U/mL"})
        parse = parse_lab_table(_lab_document([row]))
        extraction = extract_record_items(
            parse.completion,
            document_ref=DOCUMENT,
            regions=parse.regions,
            observed_at=AT,
            expected_units={"ALT": "U/L"},
        )
        assert extraction.items[0].unit_conflict is True
        assert extraction.items[0].value_magnitude == Decimal("30")

    def test_the_near_miss_the_same_row_printed_correctly_does_not_flag(self) -> None:
        row = dict(_HAEMOGLOBIN, **{"Tetkik Adı": "ALT", "Sonuç": "30", "Birim": "U/L"})
        parse = parse_lab_table(_lab_document([row]))
        extraction = extract_record_items(
            parse.completion,
            document_ref=DOCUMENT,
            regions=parse.regions,
            observed_at=AT,
            expected_units={"ALT": "U/L"},
        )
        assert extraction.items[0].unit_conflict is False

    def test_an_ambiguous_printed_magnitude_still_refuses_through_this_parser(self) -> None:
        from intake_platform.records import PrintedMagnitudeAmbiguous

        row = dict(_HAEMOGLOBIN, **{"Sonuç": "1.500"})
        parse = parse_lab_table(_lab_document([row]))
        with pytest.raises(PrintedMagnitudeAmbiguous):
            extract_record_items(
                parse.completion, document_ref=DOCUMENT, regions=parse.regions, observed_at=AT
            )

    def test_the_ure_guard_still_fires_through_this_parser(self) -> None:
        from intake_platform.records import AnalyteAmbiguous

        row = dict(_HAEMOGLOBIN, **{"Tetkik Adı": "Üremi"})
        parse = parse_lab_table(_lab_document([row]))
        with pytest.raises(AnalyteAmbiguous):
            extract_record_items(
                parse.completion, document_ref=DOCUMENT, regions=parse.regions, observed_at=AT
            )

    def test_ure_nitrojeni_survives_the_table_parse_as_its_own_name(self) -> None:
        """The near-miss control, carried through the new parser: the row must
        arrive at the guard spelled as the document printed it."""
        row = dict(_HAEMOGLOBIN, **{"Tetkik Adı": "Üre Nitrojeni", "Sonuç": "45"})
        parse = parse_lab_table(_lab_document([row]))
        (item,) = parse.completion["items"]
        assert item["printed_name"] == "Üre Nitrojeni"


class TestTheColumnIsDecidedByGeometryNotByPosition:
    """The failure this exists to stop: a row missing one cell shifts every
    later cell one column left under an ordinal read, so the *reference range*
    becomes the unit and the *status flag* becomes the value."""

    def test_a_row_missing_an_optional_cell_still_reads_the_right_columns(self) -> None:
        row = {
            "Tetkik Adı": "Hemoglobin",
            "Sonuç": "10,2",
            "Birim": "g/dL",
            "Önceki Sonuçlar": "11,4",
        }
        parse = parse_lab_table(_lab_document([row]))
        (item,) = parse.completion["items"]
        assert item["printed_value"] == "10,2"
        assert item["printed_unit"] == "g/dL"

    def test_a_cell_straddling_two_columns_makes_the_row_unread(self) -> None:
        regions = list(_header())
        regions.append(_cell(1, 0.02, 0.24, 0.20, 0.22, "Hemoglobin", 500))
        # spans Sonuç *and* Durum — which column it belongs to is unknowable
        regions.append(_cell(1, 0.30, 0.45, 0.20, 0.22, "10,2", 520))
        parse = parse_lab_table(tuple(regions))
        assert parse.completion["items"] == []
        assert parse.rows_unread == (0,)

    def test_a_row_with_no_result_cell_is_unread_rather_than_valueless(self) -> None:
        parse = parse_lab_table(_lab_document([{"Tetkik Adı": "Hemoglobin", "Birim": "g/dL"}]))
        assert parse.completion["items"] == []
        assert parse.rows_unread == (0,)

    def test_two_cells_in_one_column_make_the_row_unread(self) -> None:
        regions = list(_header())
        regions += _row(1, 0.20, _HAEMOGLOBIN, 500)
        regions.append(_cell(1, 0.27, 0.37, 0.20, 0.22, "9,9", 700))
        parse = parse_lab_table(tuple(regions))
        assert parse.completion["items"] == []
        assert parse.rows_unread == (0,)

    def test_an_unread_row_is_named_by_ordinal_never_by_content(self) -> None:
        parse = parse_lab_table(_lab_document([{"Tetkik Adı": "Hemoglobin"}]))
        assert all(isinstance(index, int) for index in parse.rows_unread)


class TestTheThreeInterpretiveColumnsAreDroppedOnPurpose:
    """`Durum` is an abnormality flag (invariant 1 — a document is not a rules
    engine), `Referans Aralığı` is the two-number cell files/03 §4.9.6 calls a
    signal to stop, and `Önceki Sonuçlar` is a *different* observation with a
    different date."""

    def test_only_three_of_the_six_columns_are_carried(self) -> None:
        assert CARRIED_COLUMNS == ("Tetkik Adı", "Sonuç", "Birim")
        assert DROPPED_COLUMNS == ("Durum", "Referans Aralığı", "Önceki Sonuçlar")
        assert set(CARRIED_COLUMNS) | set(DROPPED_COLUMNS) == set(LAB_TABLE_COLUMNS)

    def test_no_status_flag_reaches_the_item(self) -> None:
        parse = parse_lab_table(_lab_document())
        (item,) = parse.completion["items"]
        assert "Düşük" not in str(item)

    def test_no_reference_range_or_previous_result_reaches_the_item(self) -> None:
        parse = parse_lab_table(_lab_document())
        (item,) = parse.completion["items"]
        assert "12,0 - 16,0" not in str(item)
        assert "11,4" not in str(item)

    def test_the_dropped_columns_cannot_be_smuggled_through_the_key_set(self) -> None:
        parse = parse_lab_table(_lab_document())
        for item in parse.completion["items"]:
            assert set(item) <= ITEM_KEYS


class TestAnExportIsDataNeverInstructions:
    """Invariant 14, and the same fence INT-083 built and INT-121 moved down —
    not a third implementation."""

    def test_the_whole_text_layer_is_fenced_by_the_one_control(self) -> None:
        from intake_platform.data_boundary import DATA_TAG

        parse = parse_lab_table(_lab_document())
        assert DATA_TAG in parse.fenced.rendered
        assert "Hemoglobin" in parse.fenced.text

    def test_a_row_carrying_the_control_token_refuses_the_document_whole(self) -> None:
        from intake_platform.data_boundary import CONTROL_MARKER

        row = dict(_HAEMOGLOBIN, **{"Tetkik Adı": f"Hemoglobin {CONTROL_MARKER}"})
        with pytest.raises(DocumentBoundaryEscape):
            parse_lab_table(_lab_document([row]))

    def test_no_function_on_this_path_returns_instructions(self) -> None:
        import intake_platform.records.enabiz as module

        for name in dir(module):
            assert "prompt" not in name.casefold()
            assert "instruction" not in name.casefold()


# --------------------------------------------------------------------------------------------
# Acceptance clause 2 — "MHRS SMS screenshot -> visit fields"
# --------------------------------------------------------------------------------------------


class TestABranchNameIsNeverSubstringMatched:
    """The `üre` rule, applied to the thing an SMS actually names. A branch
    decides which protocol pack runs, so `Çocuk Göğüs Hastalıkları` read as
    `Göğüs Hastalıkları` runs an adult pack on a child.
    """

    def test_a_printed_branch_name_resolves_to_its_committed_id(self) -> None:
        assert resolve_printed_branch("Kardiyoloji", _vocabulary()) == "kardiyoloji"

    def test_the_near_miss_the_child_branch_contains_the_adult_name(self) -> None:
        """`Göğüs Hastalıkları` is a whole-token subsequence of `Çocuk Göğüs
        Hastalıkları`. The maximal printed span is the branch that was printed;
        the shorter reading is the same characters counted twice."""
        vocabulary = _vocabulary()
        assert (
            resolve_printed_branch("Çocuk Göğüs Hastalıkları", vocabulary)
            == "cocuk_gogus_hastaliklari"
        )
        assert resolve_printed_branch("Göğüs Hastalıkları", vocabulary) == "gogus_hastaliklari"

    def test_a_turkish_suffix_is_not_a_match(self) -> None:
        """`Kardiyoloji` is a *character* substring of `Çocuk Kardiyolojisi`
        and not a token of it, which is why matching is whole-token."""
        vocabulary = _vocabulary()
        assert resolve_printed_branch("Çocuk Kardiyolojisi", vocabulary) == "cocuk_kardiyolojisi"

    def test_two_different_branches_in_one_message_are_refused(self) -> None:
        with pytest.raises(BranchNameAmbiguous):
            resolve_printed_branch("Kardiyoloji ve Nöroloji", _vocabulary())

    def test_a_message_naming_no_committed_branch_resolves_to_nothing(self) -> None:
        """Not knowing is different from an ambiguity (INT-121's shape)."""
        assert resolve_printed_branch("Randevunuz olusturuldu", _vocabulary()) is None

    def test_turkish_case_folding_decides_whether_a_branch_is_found(self) -> None:
        """`İç Hastalıkları` under Python's default casefold grows a combining
        dot and stops matching its own committed name."""
        vocabulary = _vocabulary()
        assert resolve_printed_branch("İÇ HASTALIKLARI", vocabulary) == "ic_hastaliklari"
        assert "İç Hastalıkları".casefold() != "iç hastalıkları"

    def test_punctuation_around_the_name_does_not_decide_the_identity(self) -> None:
        vocabulary = _vocabulary()
        assert resolve_printed_branch("Bölüm: Kardiyoloji.", vocabulary) == "kardiyoloji"

    def test_a_vocabulary_whose_names_collide_when_folded_is_refused(self) -> None:
        with pytest.raises(VisitCandidateError):
            BranchVocabulary.from_names({"Kardiyoloji": "a", "KARDİYOLOJİ": "b"})

    def test_a_vocabulary_name_that_folds_to_no_token_is_refused(self) -> None:
        with pytest.raises(VisitCandidateError):
            BranchVocabulary.from_names({"—": "a"})

    def test_an_empty_vocabulary_fails_closed_rather_than_matching_nothing(self) -> None:
        with pytest.raises(VisitCandidateError):
            BranchVocabulary.from_names({})

    def test_the_same_name_twice_for_the_same_branch_is_not_a_collision(self) -> None:
        vocabulary = BranchVocabulary.from_names({"Kardiyoloji": "a", "KARDİYOLOJİ ": "a"})
        assert resolve_printed_branch("Kardiyoloji", vocabulary) == "a"

    def test_the_excluded_branch_resolves_and_the_taxonomy_still_refuses_it(self) -> None:
        """Acil Tıp books no pre-visit intake (files/09 §1 row 9). The refusal
        stays where INT-042 put it — one enforcement point, not two."""
        taxonomy = load_taxonomy(BRANCHES_YAML)
        branch_id = resolve_printed_branch("Acil Tıp", _vocabulary())
        assert branch_id == "acil_tip"
        branch = taxonomy.branch(branch_id)
        assert taxonomy.cluster_of(branch).intake is False


class TestATurkishPrintedDateThatReadsTwoWaysIsRefused:
    """Invariant 22 for the numerals that matter here. `03.04.2026` is 3 April
    under `gg.aa.yyyy` and 4 March under `mm.dd.yyyy`; no committed source in
    this repository states which order an MHRS SMS prints, so neither reading
    is taken."""

    @pytest.mark.parametrize(
        ("printed", "expected"),
        [
            ("2026-09-03", dt.date(2026, 9, 3)),
            ("31.12.2026", dt.date(2026, 12, 31)),
            ("13/09/2026", dt.date(2026, 9, 13)),
            ("3 Eylül 2026", dt.date(2026, 9, 3)),
            ("03 EYLÜL 2026", dt.date(2026, 9, 3)),
            ("1 Ocak 2027", dt.date(2027, 1, 1)),
        ],
    )
    def test_an_unambiguous_printed_date_resolves_exactly(
        self, printed: str, expected: dt.date
    ) -> None:
        assert parse_printed_date(printed) == expected

    @pytest.mark.parametrize("printed", ["03.04.2026", "01/02/2026", "12-11-2026"])
    def test_a_date_that_reads_two_ways_is_refused(self, printed: str) -> None:
        with pytest.raises(PrintedDateAmbiguous):
            parse_printed_date(printed)

    def test_a_declared_order_resolves_what_is_otherwise_refused(self) -> None:
        """The seam for when a human supplies the format. Until then the
        caller passes nothing and the ambiguous form stays refused."""
        assert parse_printed_date("03.04.2026", order=DateOrder.DAY_FIRST) == dt.date(2026, 4, 3)
        assert parse_printed_date("03.04.2026", order=DateOrder.MONTH_FIRST) == dt.date(2026, 3, 4)

    @pytest.mark.parametrize("printed", ["03.09.26", "3.9.26"])
    def test_a_two_digit_year_is_refused_because_the_century_is_a_guess(self, printed: str) -> None:
        with pytest.raises(PrintedDateUnreadable):
            parse_printed_date(printed)

    @pytest.mark.parametrize("printed", ["31.02.2026", "32.01.2026", "00.09.2026", "13.13.2026"])
    def test_a_date_that_is_not_a_date_is_refused(self, printed: str) -> None:
        with pytest.raises(PrintedDateUnreadable):
            parse_printed_date(printed)

    @pytest.mark.parametrize("printed", ["2026-09-2026", "2026-02-31"])
    def test_a_year_first_form_that_names_no_real_day_is_refused(self, printed: str) -> None:
        with pytest.raises(PrintedDateUnreadable):
            parse_printed_date(printed)

    def test_a_declared_order_that_names_no_real_day_is_refused(self) -> None:
        with pytest.raises(PrintedDateUnreadable):
            parse_printed_date("31.04.2026", order=DateOrder.DAY_FIRST)

    def test_a_month_first_only_reading_is_not_a_guess(self) -> None:
        """`09/13/2026` has exactly one valid reading, so taking it chooses
        nothing — 13 is not a month."""
        assert parse_printed_date("09/13/2026") == dt.date(2026, 9, 13)

    def test_the_turkish_month_names_are_the_twelve_and_nothing_else(self) -> None:
        assert len(TURKISH_MONTHS) == 12
        assert set(TURKISH_MONTHS.values()) == set(range(1, 13))

    def test_a_printed_time_resolves_or_refuses(self) -> None:
        assert parse_printed_time("14:30") == dt.time(14, 30)
        with pytest.raises(PrintedTimeUnreadable):
            parse_printed_time("24:30")
        with pytest.raises(PrintedTimeUnreadable):
            parse_printed_time("2:30 PM")


class TestScanningAMessageStopsWhenItCouldMeanTwoAppointments:
    def test_one_date_in_the_message_is_read(self) -> None:
        assert find_printed_date("Randevunuz 13.09.2026 tarihindedir") == dt.date(2026, 9, 13)

    def test_a_month_name_in_the_message_is_read(self) -> None:
        """The one printed form that needs no order at all — a month name
        cannot be read as a day."""
        assert find_printed_date("Randevunuz 13 Eylül 2026 tarihindedir") == dt.date(2026, 9, 13)

    def test_two_different_dates_refuse_rather_than_choosing_one(self) -> None:
        """A booking confirmation plausibly prints both the booking date and
        the appointment date. Choosing between them is the wrong-day error."""
        with pytest.raises(PrintedDateAmbiguous):
            find_printed_date("13.09.2026 tarihli randevunuz 20.09.2026 icin alinmistir")

    def test_the_same_date_printed_twice_is_one_date(self) -> None:
        assert find_printed_date("13.09.2026 — 13/09/2026") == dt.date(2026, 9, 13)

    def test_a_message_with_no_date_is_not_found(self) -> None:
        with pytest.raises(PrintedDateNotFound):
            find_printed_date("Randevunuz olusturuldu")

    def test_a_word_that_is_not_a_turkish_month_is_not_a_date_token(self) -> None:
        """Skipped, not refused: `3 Foo 2026` is not a date-shaped token at
        all, which is different from a date-shaped one that will not read."""
        assert find_printed_date("3 Foo 2026 — randevu 13.09.2026") == dt.date(2026, 9, 13)

    def test_the_same_shape_parsed_alone_is_still_unreadable(self) -> None:
        with pytest.raises(PrintedDateUnreadable):
            parse_printed_date("3 Foo 2026")

    def test_an_ambiguous_token_refuses_the_whole_scan(self) -> None:
        with pytest.raises(PrintedDateAmbiguous):
            find_printed_date("Randevu 03.04.2026")

    def test_two_times_refuse_and_one_resolves(self) -> None:
        assert find_printed_time("Saat 14:30") == dt.time(14, 30)
        with pytest.raises(PrintedTimeAmbiguous):
            find_printed_time("14:30 - 15:00")
        with pytest.raises(PrintedTimeNotFound):
            find_printed_time("Randevunuz olusturuldu")


class TestTheScreenshotProducesCandidatesAndNeverAVisit:
    """Invariant 12 at the type level. An OCR of a photograph of a text
    message is a candidate in the strongest sense there is."""

    def test_a_readable_message_yields_the_fields_it_can_defend(self) -> None:
        candidate = parse_mhrs_sms(
            "Sayin hastamiz, Kardiyoloji brans randevunuz 13.09.2026 saat 14:30",
            document_ref=SCREENSHOT,
            vocabulary=_vocabulary(),
        )
        assert candidate.branch_id == "kardiyoloji"
        assert candidate.date == dt.date(2026, 9, 13)
        assert candidate.time == dt.time(14, 30)
        assert candidate.refusals == ()

    def test_the_candidate_has_no_field_a_confirmation_could_occupy(self) -> None:
        fields = {field.name for field in dataclasses.fields(CandidateVisitFields)}
        assert not fields & {"confirmation", "confirmed_at", "confirmed", "source"}

    def test_the_candidate_has_no_field_a_hospital_or_visit_type_could_occupy(self) -> None:
        """Neither is attempted: no committed table maps a printed Turkish
        word to a files/09 §1 visit type, and no hospital list is committed.
        A field that is always `None` is a claim the parser tried."""
        fields = {field.name for field in dataclasses.fields(CandidateVisitFields)}
        assert not fields & {"hospital", "visit_type", "department"}

    def test_an_unconfirmed_candidate_cannot_be_spelled_as_confirmed(self) -> None:
        candidate = CandidateVisitFields(document_ref=SCREENSHOT, branch_id="kardiyoloji")
        with pytest.raises(dataclasses.FrozenInstanceError):
            candidate.branch_id = "noroloji"  # type: ignore[misc]

    def test_confirmation_reads_the_actor_off_the_vocabulary(self) -> None:
        candidate = parse_mhrs_sms(
            "Kardiyoloji 13.09.2026 14:30", document_ref=SCREENSHOT, vocabulary=_vocabulary()
        )
        confirmed = confirm_visit_candidate(
            candidate, hospital="Acıbadem Maslak", visit_type="followup", at=AT
        )
        assert confirmed.confirmation.source is LearnedFactSource.CONFIRMED_IMPORTED_RECORD
        assert confirmed.confirmation.actor is ConfirmingActor.PATIENT
        assert confirmed.confirmation.source_ref == SCREENSHOT

    def test_a_confirmation_naming_another_document_is_refused(self) -> None:
        candidate = CandidateVisitFields(document_ref=SCREENSHOT)
        with pytest.raises(VisitCandidateError):
            ConfirmedVisitFields(
                candidate=candidate,
                hospital="Acıbadem Maslak",
                visit_type=None,
                confirmation=Confirmation(
                    source=LearnedFactSource.CONFIRMED_IMPORTED_RECORD,
                    source_ref="document:another",
                    confirmed_at=AT,
                ),
            )

    def test_a_confirmation_minted_for_another_source_is_refused(self) -> None:
        candidate = CandidateVisitFields(document_ref=SCREENSHOT)
        with pytest.raises(VisitCandidateError):
            ConfirmedVisitFields(
                candidate=candidate,
                hospital="Acıbadem Maslak",
                visit_type=None,
                confirmation=Confirmation(
                    source=LearnedFactSource.CLINICIAN_ACCEPTED_NOTE,
                    source_ref=SCREENSHOT,
                    confirmed_at=AT,
                ),
            )

    def test_the_hospital_is_supplied_at_confirmation_and_may_not_be_empty(self) -> None:
        candidate = CandidateVisitFields(document_ref=SCREENSHOT)
        with pytest.raises(VisitCandidateError):
            confirm_visit_candidate(candidate, hospital="   ", visit_type=None, at=AT)

    def test_the_confirmed_fields_are_the_visit_fields_the_api_takes(self) -> None:
        candidate = parse_mhrs_sms(
            "Kardiyoloji 13.09.2026 14:30", document_ref=SCREENSHOT, vocabulary=_vocabulary()
        )
        fields = confirm_visit_candidate(
            candidate, hospital="Acıbadem Maslak", visit_type="followup", at=AT
        ).as_visit_fields()
        assert fields.hospital == "Acıbadem Maslak"
        assert fields.branch_id == "kardiyoloji"
        assert fields.visit_type == "followup"
        assert fields.date == "2026-09-13"

    def test_the_year_never_crosses_the_boundary_grouped(self) -> None:
        """Invariant 22 outbound: `useGrouping:false`, and the date is one
        atom the API's own ISO check accepts."""
        candidate = parse_mhrs_sms(
            "Kardiyoloji 13.09.2026", document_ref=SCREENSHOT, vocabulary=_vocabulary()
        )
        fields = confirm_visit_candidate(
            candidate, hospital="H", visit_type=None, at=AT
        ).as_visit_fields()
        assert fields.date is not None
        assert "." not in fields.date and "," not in fields.date
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", fields.date)


class TestWhenTheScreenshotIsUnsureItProducesNothingAndSaysSo:
    def test_an_ambiguous_date_yields_no_date_and_names_the_refusal(self) -> None:
        candidate = parse_mhrs_sms(
            "Kardiyoloji randevunuz 03.04.2026", document_ref=SCREENSHOT, vocabulary=_vocabulary()
        )
        assert candidate.branch_id == "kardiyoloji"
        assert candidate.date is None
        assert f"date:{VisitFieldRefusal.AMBIGUOUS.value}" in candidate.refusals

    def test_two_branches_yield_no_branch_and_name_the_refusal(self) -> None:
        candidate = parse_mhrs_sms(
            "Kardiyoloji / Nöroloji 13.09.2026", document_ref=SCREENSHOT, vocabulary=_vocabulary()
        )
        assert candidate.branch_id is None
        assert f"branch_id:{VisitFieldRefusal.AMBIGUOUS.value}" in candidate.refusals

    def test_a_message_yielding_nothing_is_a_candidate_that_says_nothing(self) -> None:
        candidate = parse_mhrs_sms(
            "Randevunuz olusturuldu", document_ref=SCREENSHOT, vocabulary=_vocabulary()
        )
        assert (candidate.branch_id, candidate.date, candidate.time) == (None, None, None)
        assert set(candidate.refusals) == {
            f"branch_id:{VisitFieldRefusal.NOT_FOUND.value}",
            f"date:{VisitFieldRefusal.NOT_FOUND.value}",
            f"time:{VisitFieldRefusal.NOT_FOUND.value}",
        }

    def test_an_unreadable_date_is_named_as_unreadable_not_as_missing(self) -> None:
        """A two-digit year is a date the message *did* state, and saying "not
        found" would send whoever reads the refusal looking for the wrong bug."""
        candidate = parse_mhrs_sms(
            "Kardiyoloji 03.09.26", document_ref=SCREENSHOT, vocabulary=_vocabulary()
        )
        assert candidate.date is None
        assert f"date:{VisitFieldRefusal.UNREADABLE.value}" in candidate.refusals

    def test_two_times_and_an_impossible_time_are_each_named(self) -> None:
        vocabulary = _vocabulary()
        two = parse_mhrs_sms(
            "Kardiyoloji 13.09.2026 09:00 - 10:00", document_ref=SCREENSHOT, vocabulary=vocabulary
        )
        assert two.time is None
        assert f"time:{VisitFieldRefusal.AMBIGUOUS.value}" in two.refusals
        impossible = parse_mhrs_sms(
            "Kardiyoloji 13.09.2026 saat 25:30", document_ref=SCREENSHOT, vocabulary=vocabulary
        )
        assert impossible.time is None
        assert f"time:{VisitFieldRefusal.UNREADABLE.value}" in impossible.refusals

    def test_a_refusal_names_the_field_and_the_reason_never_the_message(self) -> None:
        candidate = parse_mhrs_sms(
            "Kardiyoloji randevunuz 03.04.2026", document_ref=SCREENSHOT, vocabulary=_vocabulary()
        )
        joined = "".join(candidate.refusals)
        assert "03.04.2026" not in joined
        assert "Kardiyoloji" not in joined

    def test_the_screenshot_text_crosses_the_same_data_boundary(self) -> None:
        from intake_platform.data_boundary import CONTROL_MARKER

        with pytest.raises(DocumentBoundaryEscape):
            parse_mhrs_sms(
                f"Kardiyoloji {CONTROL_MARKER}",
                document_ref=SCREENSHOT,
                vocabulary=_vocabulary(),
            )

    def test_an_empty_screenshot_is_refused_rather_than_read_as_no_appointment(self) -> None:
        with pytest.raises(DocumentBoundaryEscape):
            parse_mhrs_sms("", document_ref=SCREENSHOT, vocabulary=_vocabulary())


# --------------------------------------------------------------------------------------------
# Acceptance clause 3 — "no scraping of e-Nabiz (no third-party API exists;
# legal note enforced)"
# --------------------------------------------------------------------------------------------

#: Assembled rather than spelled, so this file does not become the one hit its
#: own tree scan finds (the `assert_no_vendor_calls.sh` shape, one level in).
_MINISTRY_HOSTS: tuple[str, ...] = (
    "enabiz" + ".gov.tr",
    "mhrs" + ".gov.tr",
    "turkiye" + ".gov.tr",
    "sbu" + ".saglik.gov.tr",
    "sysws" + ".saglik.gov.tr",
)


class TestNoScrapingPathExistsAndNoneCanBeAdded:
    """files/03 §12 and 00_STATE: there is no e-Nabız *read* path — KSVY m.6(2)
    is a closed list of physician access tiers with no category for an
    application. The legal note is KSVY m.6 (files/06 §1, corrected 25 Aug 2026
    from the repealed m.10 and the relatives' m.9): the state channel is
    entered by patient-exported documents only.

    Three mechanical checks, because a note nothing enforces is a comment.
    """

    def test_the_egress_allow_list_names_no_ministry_host(self) -> None:
        raw = (REPO_ROOT / "infra" / "security" / "egress-allowlist.yaml").read_text("utf-8")
        for host in _MINISTRY_HOSTS:
            assert host not in raw

    def test_no_source_tree_file_names_a_ministry_host(self) -> None:
        """files/ is the historical record and docs/ is prose about it; the
        build is what may not reach one."""
        pruned = {"node_modules", ".venv", "dist", "build", "__pycache__", ".git", ".expo"}
        suffixes = {".py", ".ts", ".tsx", ".yaml", ".yml", ".json", ".sh", ".toml"}
        this = Path(__file__).resolve()
        for tree in ("packages", "services", "apps", "infra", "scripts"):
            for directory, subdirectories, filenames in os.walk(REPO_ROOT / tree):
                subdirectories[:] = [name for name in subdirectories if name not in pruned]
                for filename in filenames:
                    path = Path(directory) / filename
                    if path.suffix not in suffixes or path.resolve() == this:
                        continue
                    text = path.read_text("utf-8", errors="ignore")
                    for host in _MINISTRY_HOSTS:
                        assert host not in text, f"{path}: names {host}"

    def test_no_module_on_this_path_can_reach_a_network(self) -> None:
        """A read path is not merely absent — it is unrepresentable. No module
        imports an HTTP client, and no public entry point takes a destination.
        """
        import intake_platform.records.enabiz as enabiz
        import intake_platform.records.mhrs as mhrs
        import intake_platform.records.turkish_dates as dates
        import intake_platform.records.visit_candidate as candidate

        forbidden_imports = {"httpx", "requests", "urllib", "aiohttp", "socket", "http"}
        forbidden_params = {"url", "host", "endpoint", "client", "transport", "base_url", "api"}
        for module in (enabiz, mhrs, dates, candidate):
            tree = ast.parse(Path(module.__file__ or "").read_text("utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert alias.name.split(".")[0] not in forbidden_imports
                elif isinstance(node, ast.ImportFrom) and node.module:
                    assert node.module.split(".")[0] not in forbidden_imports
            for name in dir(module):
                member = getattr(module, name)
                if not callable(member) or name.startswith("_"):
                    continue
                try:
                    signature = inspect.signature(member)
                except (TypeError, ValueError):  # pragma: no cover - builtins
                    continue
                assert not set(signature.parameters) & forbidden_params, name

    def test_the_parsers_take_already_read_content_and_never_a_locator(self) -> None:
        assert set(inspect.signature(parse_lab_table).parameters) == {"regions"}
        assert set(inspect.signature(parse_mhrs_sms).parameters) == {
            "text",
            "document_ref",
            "vocabulary",
        }

    def test_the_backlog_row_cites_the_articles_files_06_actually_carries(self) -> None:
        """00_STATE §2: *"`06 §1` cites the WRONG KSVY articles, twice — and
        one of them is repealed"*. m.10 was lawyers' access and was repealed by
        RG 33096; m.9 is relatives' access. The e-Nabız regime is **m.6**."""
        backlog = yaml.safe_load((REPO_ROOT / "docs" / "backlog" / "issues.yaml").read_text())
        row = next(issue for issue in backlog if issue["id"] == "INT-122")
        codes = {code.strip() for code in row["legal"].split(",")}
        assert "KSVY-6" in codes
        assert not codes & {"KSVY-9", "KSVY-10"}


# --------------------------------------------------------------------------------------------
# Cross-cutting — invariant 6
# --------------------------------------------------------------------------------------------


class TestNoRefusalEchoesTheDocument:
    def test_a_refused_table_shape_names_no_printed_line(self) -> None:
        loose = (_cell(1, 0.1, 0.4, 0.1, 0.12, "Hemoglobin 10,2 g/dL", 0),)
        with pytest.raises(LabTableShapeUnrecognised) as caught:
            parse_lab_table(loose)
        assert "Hemoglobin" not in str(caught.value)

    def test_a_refused_branch_names_no_printed_branch(self) -> None:
        with pytest.raises(BranchNameAmbiguous) as caught:
            resolve_printed_branch("Kardiyoloji ve Nöroloji", _vocabulary())
        assert "Kardiyoloji" not in str(caught.value)
        assert "Nöroloji" not in str(caught.value)

    def test_a_refused_date_names_no_printed_date(self) -> None:
        with pytest.raises(PrintedDateAmbiguous) as caught:
            parse_printed_date("03.04.2026")
        assert "03.04.2026" not in str(caught.value)

    def test_nothing_added_by_this_issue_logs(self) -> None:
        for name in ("enabiz.py", "mhrs.py", "turkish_dates.py", "visit_candidate.py"):
            source = (
                REPO_ROOT
                / "packages"
                / "intake_platform"
                / "src"
                / "intake_platform"
                / "records"
                / name
            ).read_text("utf-8")
            assert "logging" not in source
            assert "print(" not in source


class TestEveryRefusalOnThisPathActuallyFires:
    """The INT-121 shape: a guard nobody can trip is a guard that is not
    there. Each row is a distinct refusal reached through the public API."""

    @pytest.mark.parametrize(
        ("call", "error"),
        [
            (lambda: parse_lab_table(()), DocumentBoundaryEscape),
            (
                lambda: parse_lab_table((_cell(1, 0.1, 0.4, 0.1, 0.12, "x", 0),)),
                LabTableShapeUnrecognised,
            ),
            (lambda: parse_printed_date("03.04.2026"), PrintedDateAmbiguous),
            (lambda: parse_printed_date("31.02.2026"), PrintedDateUnreadable),
            (lambda: find_printed_date("hic tarih yok"), PrintedDateNotFound),
            (lambda: find_printed_time("hic saat yok"), PrintedTimeNotFound),
            (lambda: find_printed_time("09:00 10:00"), PrintedTimeAmbiguous),
            (
                lambda: resolve_printed_branch("Kardiyoloji Nöroloji", _vocabulary()),
                BranchNameAmbiguous,
            ),
            (lambda: CandidateVisitFields(document_ref="  "), VisitCandidateError),
        ],
    )
    def test_the_refusal_fires(self, call: Any, error: type[Exception]) -> None:
        with pytest.raises(error):
            call()

"""INT-122 — the byte-level read paths for the two patient-supplied sources.

`tests/records/test_enabiz_pdf.py` proves the parsers: a six-column lab table
read from `TextRegion[]`, and an MHRS SMS read from its text. This file proves
what sits on either side of them, which is what a caller holding the bytes of
an upload actually calls:

* **in front** — files/03 §4.9.1 rows 20 and 21 are the only engines that may
  turn a screenshot or a PDF into regions, and §4.9.2(f) is the gate: *"no OCR
  component reaches the PHI path without a `licence_verified_at` entry read
  from the raw LICENSE blob"*. `observability/registry.yaml` registers neither
  row today, so both read paths refuse **before any byte meets an engine**, and
  say why with a status rather than returning an empty reading;
* **behind** — the lab table reaches the patient's confirm cards through the
  INT-124 unit-resolution guard (one verdict per lab value, the shipped empty
  table flags every one of them, HB-C24), and nothing enters the record until
  the patient confirms it.

Every fixture is synthesised (files/06 §5: CI carries no PHI). No e-Nabız export
and no MHRS SMS exists in this repository (HB-A1; docs/backlog/blockers.md
INT-122 Ask 2). The expectation table below is a test double in INT-124's shape
— unit tokens that name no real unit, a citation that points nowhere — and authors no
clinical content.
"""

from __future__ import annotations

import ast
import datetime as dt
import inspect
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml
from clinical_schemas.record_extraction import (
    RecordExtractionError,
    UnconfirmedRecordItem,
    confirm_record_item,
)
from clinical_schemas.visit_time import VisitTimeSource
from intake_platform.records import ConfirmedRecordStore, NoLayout, TextRegion
from intake_platform.records.document_engine import (
    DOCUMENT_ENGINE_PINS,
    OCR_LAYOUT_ROW,
    OCR_TEXT_LAYER_ROW,
    DocumentNotRead,
    DocumentReadStatus,
    read_enabiz_export,
    read_mhrs_screenshot,
    require_document_engine,
)
from intake_platform.records.enabiz import (
    LAB_TABLE_COLUMNS,
    LabTableImport,
    LabTableShapeUnrecognised,
    import_lab_table,
)
from intake_platform.records.lab_model import REGISTRY_PATH
from intake_platform.records.mhrs import BranchVocabulary
from intake_platform.records.unit_guard import (
    SHIPPED_EXPECTATIONS,
    AnalyteExpectation,
    ExpectationTable,
    GuardFlag,
    SourceCitation,
)
from intake_platform.records.visit_candidate import CandidateVisitFields, confirm_visit_candidate
from protocols.taxonomy import load_taxonomy

REPO_ROOT = Path(__file__).resolve().parents[2]
BRANCHES_YAML = REPO_ROOT / "packages" / "protocols" / "taxonomy" / "branches.yaml"
ARCHITECTURE = REPO_ROOT / "files" / "03_ARCHITECTURE.md"
DOCUMENT = "document:enabiz-export-1"
SCREENSHOT = "document:mhrs-screenshot-1"
AT = dt.datetime(2026, 9, 27, 9, 0, tzinfo=dt.UTC)
PNG = b"\x89PNG\r\n\x1a\n synthetic screenshot bytes"
PDF = b"%PDF-1.7 synthetic export bytes"


# --------------------------------------------------------------------------------------------
# fixtures — every one synthesised
# --------------------------------------------------------------------------------------------

#: INT-124's test-double shape: a citation that points nowhere, so no row of
#: this table can be mistaken for a clinical source.
TEST_DOUBLE_SOURCE = SourceCitation(
    guideline_id="test-double-not-a-clinical-source",
    version="0",
    date=dt.date(2026, 9, 27),
    url="https://example.invalid/int-122-test-double",
    retrieved_on=dt.date(2026, 9, 27),
)

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
        regions.append(
            TextRegion(
                page=page,
                bbox=(x0, y, x1, y + 0.02),
                start=offset,
                end=offset + len(text),
                text=text,
            )
        )
        offset += len(text) + 1
    return regions


def _lab_document(*rows: dict[str, str]) -> tuple[TextRegion, ...]:
    regions = _row(1, 0.10, {column: column for column in LAB_TABLE_COLUMNS}, 0)
    offset = 400
    for index, cells in enumerate(rows):
        regions += _row(1, 0.20 + index * 0.05, cells, offset)
        offset += 200
    return tuple(regions)


def _lab(name: str, value: str, unit: str) -> dict[str, str]:
    return {"Tetkik Adı": name, "Sonuç": value, "Birim": unit}


def _expectation(unit: str) -> AnalyteExpectation:
    return AnalyteExpectation(
        unit=unit,
        magnitude_low=Decimal("1"),
        magnitude_high=Decimal("100"),
        source=TEST_DOUBLE_SOURCE,
    )


def _vocabulary() -> BranchVocabulary:
    taxonomy = load_taxonomy(BRANCHES_YAML)
    return BranchVocabulary.from_names({branch.name_tr: branch.id for branch in taxonomy.branches})


class _SpyLayout:
    """A layout seam that records whether untrusted bytes ever reached it."""

    def __init__(self, regions: tuple[TextRegion, ...] = ()) -> None:
        self._regions = regions
        self.calls = 0

    def regions(self, data: bytes, content_type: str) -> tuple[TextRegion, ...]:
        self.calls += 1
        return self._regions


def _sms_regions(text: str) -> tuple[TextRegion, ...]:
    return (TextRegion(page=1, bbox=(0.05, 0.40, 0.95, 0.46), start=0, end=len(text), text=text),)


def _registry(tmp_path: Path, *rows: dict[str, Any]) -> Path:
    path = tmp_path / "registry.yaml"
    path.write_text(yaml.safe_dump({"components": list(rows)}), encoding="utf-8")
    return path


def _engine_row(component: str, **override: Any) -> dict[str, Any]:
    """A registry row with every fact the gate reads, as a test double."""
    row: dict[str, Any] = {
        "component": component,
        "self_hostable": True,
        "self_hosted_now": True,
        "phi_path": True,
        "licence_verified_at": "2026-09-27",
        "licence_blob_sha256": "0" * 64,
    }
    row.update(override)
    return row


# --------------------------------------------------------------------------------------------
# Behind the parser — the lab table reaches the cards through the INT-124 guard
# --------------------------------------------------------------------------------------------


class TestTheLabTableReachesTheCardsThroughTheUnitGuard:
    """`import_lab_table` is `parse_lab_table` handed to INT-121's parser with
    INT-124's guard switched on — the same composition `extract_lab_report`
    makes for the model path, so the deterministic path cannot be the one
    that skips the guard."""

    def test_every_lab_value_carries_one_guard_verdict(self) -> None:
        result = import_lab_table(
            _lab_document(_lab("Hemoglobin", "10,2", "g/dL"), _lab("Tetkik A", "7", "birim-a")),
            document_ref=DOCUMENT,
            observed_at=AT,
        )
        assert isinstance(result, LabTableImport)
        assert len(result.extraction.items) == 2
        assert len(result.extraction.verdicts) == 2
        assert all(verdict is not None for verdict in result.extraction.verdicts)

    def test_the_shipped_empty_table_flags_every_value(self) -> None:
        """HB-C24: nobody has authored what an analyte should print, so every
        value is flagged and every analyte is named as unchecked."""
        result = import_lab_table(
            _lab_document(_lab("Hemoglobin", "10,2", "g/dL")), document_ref=DOCUMENT, observed_at=AT
        )
        verdict = result.extraction.verdicts[0]
        assert verdict is not None
        assert GuardFlag.NO_EXPECTATION in verdict.flags
        assert result.extraction.flagged == (0,)
        assert result.extraction.units_unchecked == ("hemoglobin",)

    def test_the_default_table_is_the_shipped_one(self) -> None:
        signature = inspect.signature(import_lab_table)
        assert signature.parameters["table"].default is SHIPPED_EXPECTATIONS

    def test_the_value_and_unit_reach_the_item_as_printed(self) -> None:
        result = import_lab_table(
            _lab_document(_lab("Hemoglobin", "10,2", "g/dL")), document_ref=DOCUMENT, observed_at=AT
        )
        item = result.extraction.items[0]
        assert item.value_magnitude == Decimal("10.2")
        assert item.unit == "g/dL"

    def test_a_unit_conflict_reaches_the_card(self) -> None:
        table = ExpectationTable({"Tetkik A": _expectation("birim-a")})
        result = import_lab_table(
            _lab_document(_lab("Tetkik A", "30", "birim-b")),
            document_ref=DOCUMENT,
            observed_at=AT,
            table=table,
        )
        card = result.extraction.items[0].as_confirm_card()
        assert card.unit_conflict is True
        assert result.extraction.items[0].value_magnitude == Decimal("30")

    def test_the_near_miss_the_same_row_printed_with_the_expected_unit_does_not_flag(self) -> None:
        table = ExpectationTable({"Tetkik A": _expectation("birim-a")})
        result = import_lab_table(
            _lab_document(_lab("Tetkik A", "30", "birim-a")),
            document_ref=DOCUMENT,
            observed_at=AT,
            table=table,
        )
        assert result.extraction.items[0].as_confirm_card().unit_conflict is False
        assert result.extraction.flagged == ()

    def test_a_value_that_reads_two_ways_stops_that_value_and_not_the_document(self) -> None:
        """Through the guard, `1.500` loses its number and keeps its box; the
        other row is still read. INT-121's path without the guard refuses the
        whole document on it."""
        result = import_lab_table(
            _lab_document(_lab("Tetkik A", "1.500", "birim-a"), _lab("Tetkik B", "7", "birim-a")),
            document_ref=DOCUMENT,
            observed_at=AT,
        )
        stopped, read = result.extraction.verdicts
        assert stopped is not None and GuardFlag.SEPARATOR_AMBIGUOUS in stopped.flags
        assert result.extraction.items[0].value_magnitude is None
        assert read is not None and read.magnitude == Decimal("7")

    def test_the_ure_near_miss_stops_the_value(self) -> None:
        result = import_lab_table(
            _lab_document(_lab("Üremi", "40", "birim-a")), document_ref=DOCUMENT, observed_at=AT
        )
        verdict = result.extraction.verdicts[0]
        assert verdict is not None and GuardFlag.ANALYTE_AMBIGUOUS in verdict.flags
        assert result.extraction.items[0].value_magnitude is None

    def test_every_card_points_into_the_document_it_came_from(self) -> None:
        result = import_lab_table(
            _lab_document(_lab("Hemoglobin", "10,2", "g/dL")), document_ref=DOCUMENT, observed_at=AT
        )
        card = result.extraction.items[0].as_confirm_card()
        assert card.document_ref == DOCUMENT
        assert card.page == 1
        assert card.bbox[0] == pytest.approx(0.02) and card.bbox[2] == pytest.approx(0.64)

    def test_an_unread_row_is_carried_by_ordinal(self) -> None:
        straddling = [
            TextRegion(
                page=1, bbox=(0.02, 0.20, 0.30, 0.22), start=400, end=410, text="Hemoglobin"
            ),
        ]
        regions = _lab_document() + tuple(straddling)
        result = import_lab_table(regions, document_ref=DOCUMENT, observed_at=AT)
        assert result.rows_unread == (0,)
        assert result.extraction.items == ()

    def test_a_document_without_the_table_is_still_refused_whole(self) -> None:
        loose = (TextRegion(page=1, bbox=(0.1, 0.1, 0.4, 0.12), start=0, end=5, text="başka"),)
        with pytest.raises(LabTableShapeUnrecognised):
            import_lab_table(loose, document_ref=DOCUMENT, observed_at=AT)


class TestNothingEntersTheRecordUnconfirmed:
    def test_every_item_is_unconfirmed_by_type(self) -> None:
        result = import_lab_table(
            _lab_document(_lab("Hemoglobin", "10,2", "g/dL")), document_ref=DOCUMENT, observed_at=AT
        )
        assert all(isinstance(item, UnconfirmedRecordItem) for item in result.extraction.items)

    def test_the_store_refuses_an_item_nobody_confirmed(self) -> None:
        result = import_lab_table(
            _lab_document(_lab("Hemoglobin", "10,2", "g/dL")), document_ref=DOCUMENT, observed_at=AT
        )
        with pytest.raises(RecordExtractionError):
            ConfirmedRecordStore().admit(result.extraction.items[0])  # type: ignore[arg-type]

    def test_the_patient_confirmation_names_the_export_it_agreed_with(self) -> None:
        result = import_lab_table(
            _lab_document(_lab("Hemoglobin", "10,2", "g/dL")), document_ref=DOCUMENT, observed_at=AT
        )
        store = ConfirmedRecordStore()
        store.admit(confirm_record_item(result.extraction.items[0], at=AT))
        (admitted,) = store.admitted
        assert admitted.confirmation.source_ref == DOCUMENT


# --------------------------------------------------------------------------------------------
# In front of the parser — files/03 §4.9.1 rows 20 and 21, and the §4.9.2(f) gate
# --------------------------------------------------------------------------------------------


class TestTheEnginesAreRowsTwentyAndTwentyOne:
    def test_the_pins_are_transcribed_from_files_03(self) -> None:
        """A model that is not in §4.9.1 is not pinned (CLAUDE.md read order).
        Each pin name appears in its row of the table, verbatim."""
        table = ARCHITECTURE.read_text(encoding="utf-8")
        for row, pins in DOCUMENT_ENGINE_PINS.items():
            line = next(line for line in table.splitlines() if line.startswith(f"| {row} |"))
            assert "OCR" in line
            for pin in pins:
                assert f"`{pin}`" in line

    def test_the_two_rows_are_the_screenshot_and_the_table(self) -> None:
        assert set(DOCUMENT_ENGINE_PINS) == {OCR_TEXT_LAYER_ROW, OCR_LAYOUT_ROW}
        assert (OCR_TEXT_LAYER_ROW, OCR_LAYOUT_ROW) == (20, 21)

    def test_the_committed_registry_names_no_document_engine(self) -> None:
        components = {
            row["component"]
            for row in yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))["components"]
        }
        pins = {pin for row in DOCUMENT_ENGINE_PINS.values() for pin in row}
        assert not components & pins

    @pytest.mark.parametrize("row", [20, 21])
    def test_today_neither_row_is_registered_so_both_refuse(self, row: int) -> None:
        with pytest.raises(DocumentNotRead) as caught:
            require_document_engine(row)
        assert caught.value.status is DocumentReadStatus.ENGINE_NOT_REGISTERED
        assert caught.value.row == row

    def test_a_registered_verified_served_engine_passes(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path, _engine_row("tesseract-ocr"))
        assert require_document_engine(20, registry_path=registry) == "tesseract-ocr"

    @pytest.mark.parametrize(
        ("override", "status"),
        [
            ({"licence_verified_at": None}, DocumentReadStatus.ENGINE_LICENCE_UNVERIFIED),
            ({"licence_blob_sha256": None}, DocumentReadStatus.ENGINE_LICENCE_UNVERIFIED),
            ({"phi_path": False}, DocumentReadStatus.ENGINE_OFF_PHI_PATH),
            ({"self_hostable": False}, DocumentReadStatus.ENGINE_OFF_PHI_PATH),
            ({"self_hosted_now": False}, DocumentReadStatus.ENGINE_NOT_SERVED),
        ],
    )
    def test_each_missing_fact_is_its_own_status(
        self, tmp_path: Path, override: dict[str, Any], status: DocumentReadStatus
    ) -> None:
        registry = _registry(tmp_path, _engine_row("docling", **override))
        with pytest.raises(DocumentNotRead) as caught:
            require_document_engine(21, registry_path=registry)
        assert caught.value.status is status

    def test_an_engine_the_table_does_not_name_is_not_registered(self, tmp_path: Path) -> None:
        """Every fact present, and still refused: the component is not a
        §4.9.1 row-20 pin, so it is not pinned."""
        registry = _registry(tmp_path, _engine_row("some-other-ocr"))
        with pytest.raises(DocumentNotRead) as caught:
            require_document_engine(20, registry_path=registry)
        assert caught.value.status is DocumentReadStatus.ENGINE_NOT_REGISTERED

    def test_a_row_twenty_engine_does_not_serve_row_twenty_one(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path, _engine_row("tesseract-ocr"))
        with pytest.raises(DocumentNotRead) as caught:
            require_document_engine(21, registry_path=registry)
        assert caught.value.status is DocumentReadStatus.ENGINE_NOT_REGISTERED

    def test_a_row_that_is_not_a_document_engine_row_is_a_programming_error(self) -> None:
        with pytest.raises(ValueError):
            require_document_engine(9)


class TestTheScreenshotPathRefusesWithAStatus:
    def test_today_it_refuses_before_the_bytes_meet_an_engine(self) -> None:
        layout = _SpyLayout(_sms_regions("Kardiyoloji 14 Ekim 2026 10:30"))
        with pytest.raises(DocumentNotRead) as caught:
            read_mhrs_screenshot(
                PNG, "image/png", layout=layout, document_ref=SCREENSHOT, vocabulary=_vocabulary()
            )
        assert caught.value.status is DocumentReadStatus.ENGINE_NOT_REGISTERED
        assert caught.value.row == OCR_TEXT_LAYER_ROW
        assert layout.calls == 0

    def test_an_engine_that_reads_nothing_is_not_read_never_no_appointment(
        self, tmp_path: Path
    ) -> None:
        registry = _registry(tmp_path, _engine_row("tesseract-ocr"))
        with pytest.raises(DocumentNotRead) as caught:
            read_mhrs_screenshot(
                PNG,
                "image/png",
                layout=NoLayout(),
                document_ref=SCREENSHOT,
                vocabulary=_vocabulary(),
                registry_path=registry,
            )
        assert caught.value.status is DocumentReadStatus.NOT_READ

    def test_once_an_engine_is_registered_the_screenshot_becomes_a_candidate(
        self, tmp_path: Path
    ) -> None:
        registry = _registry(tmp_path, _engine_row("tesseract-ocr"))
        candidate = read_mhrs_screenshot(
            PNG,
            "image/png",
            layout=_SpyLayout(_sms_regions("Kardiyoloji randevunuz 14 Ekim 2026 saat 10:30")),
            document_ref=SCREENSHOT,
            vocabulary=_vocabulary(),
            registry_path=registry,
        )
        assert isinstance(candidate, CandidateVisitFields)
        assert (candidate.branch_id, candidate.date, candidate.time) == (
            "kardiyoloji",
            dt.date(2026, 10, 14),
            dt.time(10, 30),
        )

    def test_the_candidate_confirms_into_visit_fields_that_carry_their_source(
        self, tmp_path: Path
    ) -> None:
        registry = _registry(tmp_path, _engine_row("tesseract-ocr"))
        candidate = read_mhrs_screenshot(
            PNG,
            "image/png",
            layout=_SpyLayout(_sms_regions("Kardiyoloji 14 Ekim 2026 10:30")),
            document_ref=SCREENSHOT,
            vocabulary=_vocabulary(),
            registry_path=registry,
        )
        fields = confirm_visit_candidate(
            candidate, hospital="Hastane A", visit_type=None, at=AT
        ).as_visit_fields()
        assert fields.date == "2026-10-14"
        assert fields.time_source == VisitTimeSource.DOCUMENT_EXTRACTION.value
        assert fields.time_source_ref == SCREENSHOT

    def test_an_ambiguous_screenshot_date_is_still_refused_by_name(self, tmp_path: Path) -> None:
        registry = _registry(tmp_path, _engine_row("tesseract-ocr"))
        candidate = read_mhrs_screenshot(
            PNG,
            "image/png",
            layout=_SpyLayout(_sms_regions("Kardiyoloji 03.04.2026 10:30")),
            document_ref=SCREENSHOT,
            vocabulary=_vocabulary(),
            registry_path=registry,
        )
        assert candidate.date is None
        assert "date:ambiguous" in candidate.refusals


class TestTheExportPathRefusesWithAStatus:
    def test_today_it_refuses_before_the_bytes_meet_an_engine(self) -> None:
        layout = _SpyLayout(_lab_document(_lab("Hemoglobin", "10,2", "g/dL")))
        with pytest.raises(DocumentNotRead) as caught:
            read_enabiz_export(
                PDF, "application/pdf", layout=layout, document_ref=DOCUMENT, observed_at=AT
            )
        assert caught.value.status is DocumentReadStatus.ENGINE_NOT_REGISTERED
        assert caught.value.row == OCR_LAYOUT_ROW
        assert layout.calls == 0

    def test_an_engine_that_finds_no_text_layer_is_not_read(self, tmp_path: Path) -> None:
        """HB-A1: *"Do not assume a text layer"*. A PDF that has none yields no
        regions, and that is a refusal — never an export with no labs."""
        registry = _registry(tmp_path, _engine_row("docling"))
        with pytest.raises(DocumentNotRead) as caught:
            read_enabiz_export(
                PDF,
                "application/pdf",
                layout=NoLayout(),
                document_ref=DOCUMENT,
                observed_at=AT,
                registry_path=registry,
            )
        assert caught.value.status is DocumentReadStatus.NOT_READ

    def test_once_an_engine_is_registered_the_export_becomes_guarded_cards(
        self, tmp_path: Path
    ) -> None:
        registry = _registry(tmp_path, _engine_row("docling"))
        result = read_enabiz_export(
            PDF,
            "application/pdf",
            layout=_SpyLayout(_lab_document(_lab("Hemoglobin", "10,2", "g/dL"))),
            document_ref=DOCUMENT,
            observed_at=AT,
            registry_path=registry,
        )
        assert isinstance(result, LabTableImport)
        assert result.extraction.items[0].as_confirm_card().document_ref == DOCUMENT
        assert result.extraction.flagged == (0,)


# --------------------------------------------------------------------------------------------
# No scraping — the new module is held to the same structural property
# --------------------------------------------------------------------------------------------


class TestTheReadPathsCannotReachANetwork:
    def test_the_engine_module_imports_no_network_client(self) -> None:
        import intake_platform.records.document_engine as engine

        forbidden = {"httpx", "requests", "urllib", "aiohttp", "socket", "http"}
        tree = ast.parse(Path(engine.__file__ or "").read_text("utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in forbidden
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden
                assert node.module != "intake_platform.uploads"

    def test_the_read_paths_take_bytes_and_never_a_locator(self) -> None:
        assert set(inspect.signature(read_mhrs_screenshot).parameters) == {
            "data",
            "content_type",
            "layout",
            "document_ref",
            "vocabulary",
            "registry_path",
        }
        assert set(inspect.signature(read_enabiz_export).parameters) == {
            "data",
            "content_type",
            "layout",
            "document_ref",
            "observed_at",
            "table",
            "terminology",
            "registry_path",
        }
        assert set(inspect.signature(import_lab_table).parameters) == {
            "regions",
            "document_ref",
            "observed_at",
            "table",
            "terminology",
        }

    def test_a_refusal_names_the_row_and_the_status_never_the_bytes(self) -> None:
        with pytest.raises(DocumentNotRead) as caught:
            read_mhrs_screenshot(
                b"Kardiyoloji 14 Ekim 2026",
                "image/png",
                layout=NoLayout(),
                document_ref=SCREENSHOT,
                vocabulary=_vocabulary(),
            )
        message = str(caught.value)
        assert "row 20" in message
        assert DocumentReadStatus.ENGINE_NOT_REGISTERED.value in message
        assert "Kardiyoloji" not in message
        assert SCREENSHOT not in message

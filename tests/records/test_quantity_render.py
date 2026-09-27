"""INT-385 — a record quantity is written the way its reader reads it.

CLAUDE.md invariant 22: *"Numbers never cross a representation boundary
unguarded. … `useGrouping:false` for every clinical quantity; number + unit is
one non-breaking atom."*

INT-121's ``render_quantity`` wrote a full stop as the decimal point for every
reader. A Turkish reader takes a full stop as grouping (files/03 §4.9.6), so on
a Turkish screen ``12.500`` is twelve thousand five hundred. A value read as
12.5 could therefore be shown as ``12.500``, 1000 times larger, and no diff
would show it. INT-124 found it (PR #634). It stays latent while HB-C24's range
table is empty, and it breaks the invariant as soon as values flow.

What is held here:

* extract → render → re-parse gives back the value it started from, for 12.5,
  12500, 0.05 and 1,5, in ``tr`` and in ``en``. The re-parse happens twice: by
  the per-value resolver the ingestion path uses, and the way a reader of that
  locale reads the number;
* the near miss, ``12.500`` for 12.5 in ``tr``, fails that same check, and so
  does INT-121's ``12.5`` in ``tr``;
* ``useGrouping:false``: 12500 is ``12500``, never ``12.500`` or ``12,500``;
* the atom is non-breaking (U+00A0 NO-BREAK SPACE);
* the server and the app agree. Both are held to one fixture table,
  ``tests/fixtures/records/quantity_render.json``, which
  ``apps/mobile/src/lib/records/extraction.test.ts`` reads too;
* the TTS path is not touched. No numeral may reach a TTS model, and this
  renderer is for the screen only.

INT-386 holds the four text renderers INT-096 recorded to the same table: the
typed profile's numeric rail, the clinician note, the patient summary and the
FHIR document's narrative. Each writes its quantities through the one
renderer, which now lives in :mod:`clinical_schemas.quantity` so the FHIR
mapper can reach it (``clinical-schemas`` depends on pydantic alone, and
``intake_platform`` depends on it). ``intake_platform.records`` re-exports the
same objects, so there is one renderer and not a copy of it.
"""

from __future__ import annotations

import ast
import datetime as dt
import json
import subprocess
import sys
import unicodedata
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from clinical_schemas import quantity as shared
from clinical_schemas.mappers import document as fhir_document
from clinical_schemas.note import KonusmaOzellikleri, MeasureCode, SelfReportedMeasure
from intake_platform import records as records_package
from intake_platform.records import (
    DECIMAL_SEPARATORS,
    NBSP,
    PrintedMagnitudeUnreadable,
    QuantityLocaleUnknown,
    TextRegion,
    extract_record_items,
    parse_printed_magnitude,
    quantity_atom,
    render_quantity,
    summarise_item,
)
from intake_voice_runtime.note import composer as note_composer
from intake_voice_runtime.summary import builder as summary_builder
from intake_voice_runtime.typed.affordance import SlotFacts
from intake_voice_runtime.typed.render import numeric_rail, render_measure
from protocols.types import SlotType

ROOT = Path(__file__).resolve().parents[2]
TABLE = ROOT / "tests" / "fixtures" / "records" / "quantity_render.json"

DOCUMENT = "document:doc-385"
AT = dt.datetime(2026, 9, 27, 9, 30, tzinfo=dt.UTC)
REGIONS = (
    TextRegion(page=1, bbox=(0.10, 0.20, 0.60, 0.24), start=0, end=20, text="Kreatinin 12,5 mg/dL"),
)

#: How a reader of each locale reads a written number: (decimal point, grouping mark).
#: This is the reader, not the renderer. A test that asked the renderer how to
#: read its own output would pass for any renderer.
READER: dict[str, tuple[str, str]] = {"tr": (",", "."), "en": (".", ",")}

#: INT-385's four magnitudes. The issue writes the last one as ``1,5``.
#: (printed on the report, the magnitude it means)
PRINTED: list[tuple[str, Decimal]] = [
    ("12,5", Decimal("12.5")),
    ("12.5", Decimal("12.5")),
    ("12500", Decimal("12500")),
    ("0,05", Decimal("0.05")),
    ("0.05", Decimal("0.05")),
    ("1,5", Decimal("1.5")),
    ("1.5", Decimal("1.5")),
]

LOCALES = ("tr", "en")


class _NotAReading(ValueError):
    """The characters are not a number to a reader of that locale."""


def _read_as(locale: str, number: str) -> Decimal:
    """Read a written number the way a reader of ``locale`` reads it.

    The locale's point is the point. Its grouping mark is grouping, and only
    three-digit groups count as grouping. ``12.5`` is not a number to a
    Turkish reader, and ``12.500`` is 12500 to one.
    """
    point, group = READER[locale]
    sign, body = ("-", number[1:]) if number.startswith("-") else ("", number)
    integer, has_point, fraction = body.partition(point)
    if group in fraction or (has_point and not fraction.isdigit()):
        raise _NotAReading
    head, *groups = integer.split(group)
    if not head.isdigit():
        raise _NotAReading
    if groups and (not 1 <= len(head) <= 3 or not all(len(g) == 3 and g.isdigit() for g in groups)):
        raise _NotAReading
    digits = head + "".join(groups)
    return Decimal(f"{sign}{digits}.{fraction}" if has_point else f"{sign}{digits}")


def _round_trips(atom: str, *, locale: str, unit: str, value: Decimal) -> bool:
    """Re-parse one written atom and say whether it still means ``value``.

    It must split at a NO-BREAK SPACE into the number and the unit. The number
    must resolve to ``value`` under the per-value resolver the ingestion path
    uses (``parse_printed_magnitude``, which refuses a form that reads two
    ways). It must also mean ``value`` to a reader of ``locale``.
    """
    number, joiner, rest = atom.partition(NBSP)
    if joiner != NBSP or rest != unit or " " in atom:
        return False
    try:
        by_resolver = parse_printed_magnitude(number)
        by_reader = _read_as(locale, number)
    except (PrintedMagnitudeUnreadable, _NotAReading):
        return False
    return by_resolver == value and by_reader == value


def _extract(printed_value: str) -> Any:
    completion = {
        "items": [
            {
                "kind": "lab",
                "printed_name": "Kreatinin",
                "region": 0,
                "printed_value": printed_value,
                "printed_unit": "mg/dL",
                "code_system": None,
                "code": None,
                "date": "2026-09-20",
            }
        ]
    }
    (item,) = extract_record_items(
        completion, document_ref=DOCUMENT, regions=REGIONS, observed_at=AT
    ).items
    return item


def _table() -> list[dict[str, str]]:
    loaded = json.loads(TABLE.read_text(encoding="utf-8"))
    rows: list[dict[str, str]] = loaded["rows"]
    return rows


# --------------------------------------------------------------------------------------------
# Acceptance 2 — extract → render → re-parse returns the same value
# --------------------------------------------------------------------------------------------


class TestExtractRenderReparse:
    @pytest.mark.parametrize("locale", LOCALES)
    @pytest.mark.parametrize(("printed", "value"), PRINTED)
    def test_the_value_survives_the_round_trip(
        self, printed: str, value: Decimal, locale: str
    ) -> None:
        item = _extract(printed)
        assert item.value_magnitude == value
        atom = quantity_atom(item.value_magnitude, item.unit, locale=locale)
        assert _round_trips(atom, locale=locale, unit="mg/dL", value=value), atom

    @pytest.mark.parametrize(("printed", "value"), PRINTED)
    def test_the_card_summary_is_written_for_its_turkish_reader(
        self, printed: str, value: Decimal
    ) -> None:
        """The summary is the line a confirm card shows and the clinician note
        carries as ``imported_objective``. It is written once, in Turkish, for
        a Turkish report. So its number must survive a Turkish reader."""
        item = _extract(printed)
        name, _, atom = item.summary.partition(" ")
        assert name == "Kreatinin"
        assert _round_trips(atom, locale="tr", unit="mg/dL", value=value), item.summary
        assert item.as_confirm_card().summary == item.summary

    @pytest.mark.parametrize("locale", LOCALES)
    def test_summarise_item_writes_the_number_for_the_locale_it_is_given(self, locale: str) -> None:
        line = summarise_item("Kreatinin", Decimal("12.5"), "mg/dL", locale=locale)
        point = DECIMAL_SEPARATORS[locale]
        assert line == f"Kreatinin 12{point}5{NBSP}mg/dL"


# --------------------------------------------------------------------------------------------
# The near miss — `12.500` for 12.5 in tr fails
# --------------------------------------------------------------------------------------------


class TestTheNearMissFails:
    def test_twelve_point_five_hundred_for_twelve_and_a_half_fails_in_turkish(self) -> None:
        """The defect INT-385 names. A Turkish reader reads 12500, and the
        per-value resolver refuses the form because it reads two ways."""
        assert not _round_trips(
            f"12.500{NBSP}mg/dL", locale="tr", unit="mg/dL", value=Decimal("12.5")
        )

    def test_int_121s_full_stop_fails_in_turkish(self) -> None:
        """INT-121's own output, ``12.5``. The resolver reads it as 12.5, so a
        check that re-parsed with the resolver alone would pass it. To a
        Turkish reader it is not a number, so the reader check fails it."""
        assert parse_printed_magnitude("12.5") == Decimal("12.5")
        assert not _round_trips(
            f"12.5{NBSP}mg/dL", locale="tr", unit="mg/dL", value=Decimal("12.5")
        )

    def test_the_control_the_comma_passes_in_turkish(self) -> None:
        """Without this, the two failures above pass for a check that fails
        everything."""
        assert _round_trips(f"12,5{NBSP}mg/dL", locale="tr", unit="mg/dL", value=Decimal("12.5"))

    def test_the_renderer_writes_the_comma_not_the_near_miss(self) -> None:
        assert render_quantity(Decimal("12.5"), locale="tr") == "12,5"
        assert render_quantity(Decimal("12.5"), locale="tr") != "12.500"
        assert render_quantity(Decimal("12.5"), locale="en") == "12.5"

    def test_an_atom_joined_by_a_plain_space_fails(self) -> None:
        assert not _round_trips("12,5 mg/dL", locale="tr", unit="mg/dL", value=Decimal("12.5"))


# --------------------------------------------------------------------------------------------
# useGrouping:false, the separator, and the atom
# --------------------------------------------------------------------------------------------


class TestTheWrittenForm:
    @pytest.mark.parametrize("locale", LOCALES)
    def test_digits_are_never_grouped(self, locale: str) -> None:
        rendered = render_quantity(Decimal("12500"), locale=locale)
        assert rendered == "12500"
        assert rendered not in {"12.500", "12,500"}
        assert render_quantity(Decimal("1500000.25"), locale=locale) == (
            "1500000,25" if locale == "tr" else "1500000.25"
        )

    @pytest.mark.parametrize(
        ("value", "tr", "en"),
        [
            (Decimal("12.5"), "12,5", "12.5"),
            (Decimal("0.05"), "0,05", "0.05"),
            (Decimal("1.5"), "1,5", "1.5"),
            (Decimal("2.50"), "2,50", "2.50"),
            (Decimal("-2.5"), "-2,5", "-2.5"),
            (Decimal("1E+3"), "1000", "1000"),
            (Decimal("5E-7"), "0,0000005", "0.0000005"),
        ],
    )
    def test_the_decimal_separator_is_the_locales_and_nothing_else_changes(
        self, value: Decimal, tr: str, en: str
    ) -> None:
        """The locale's point, the printed precision kept (``2.50`` stays two
        places), and no exponent: an exponent beside a unit is a second way
        of writing the same magnitude."""
        assert render_quantity(value, locale="tr") == tr
        assert render_quantity(value, locale="en") == en

    def test_the_separator_table_is_closed_and_says_what_each_reader_reads(self) -> None:
        assert dict(DECIMAL_SEPARATORS) == {"tr": ",", "en": "."}
        with pytest.raises(TypeError):
            DECIMAL_SEPARATORS["de"] = ","  # type: ignore[index]

    def test_the_atom_is_joined_by_a_no_break_space(self) -> None:
        assert NBSP == " "
        assert unicodedata.name(NBSP) == "NO-BREAK SPACE"
        atom = quantity_atom(Decimal("12.5"), "mg/dL", locale="tr")
        assert atom == "12,5 mg/dL"
        assert " " not in atom

    def test_a_quantity_with_no_unit_is_the_number_alone(self) -> None:
        assert quantity_atom(Decimal("12.5"), None, locale="tr") == "12,5"
        assert quantity_atom(Decimal("12.5"), "  ", locale="en") == "12.5"

    @pytest.mark.parametrize("locale", ["de", "", "TR", "tr-TR", "Kreatinin 12,5"])
    def test_a_locale_with_no_recorded_separator_is_refused_not_guessed(self, locale: str) -> None:
        with pytest.raises(QuantityLocaleUnknown):
            render_quantity(Decimal("12.5"), locale=locale)
        with pytest.raises(QuantityLocaleUnknown):
            quantity_atom(Decimal("12.5"), "mg/dL", locale=locale)

    def test_the_refusal_does_not_echo_what_it_was_given(self) -> None:
        """A caller can pass any string as a locale, a patient's words
        included. The refusal reaches a log, so it names the known locales
        and not the one it refused (invariant 6)."""
        probe = "Kreatinin yüksek çıktı"
        with pytest.raises(QuantityLocaleUnknown) as caught:
            render_quantity(Decimal("12.5"), locale=probe)
        assert "Kreatinin" not in str(caught.value)
        assert "yüksek" not in str(caught.value)


# --------------------------------------------------------------------------------------------
# Acceptance 1 — the server renderer and the app agree (one table, two readers)
# --------------------------------------------------------------------------------------------


class TestTheSharedTable:
    def test_the_server_renderer_writes_every_row(self) -> None:
        for row in _table():
            written = quantity_atom(Decimal(row["value"]), row["unit"], locale=row["locale"])
            assert written == row["atom"], row

    def test_every_row_round_trips_for_its_reader(self) -> None:
        for row in _table():
            assert _round_trips(
                row["atom"], locale=row["locale"], unit=row["unit"], value=Decimal(row["value"])
            ), row

    def test_the_table_covers_the_four_magnitudes_in_both_locales(self) -> None:
        """Neither side can shrink the table quietly: the issue's four
        magnitudes, each in both locales."""
        covered = {(Decimal(row["value"]), row["locale"]) for row in _table()}
        wanted = {
            (value, locale)
            for value in (Decimal("12.5"), Decimal("12500"), Decimal("0.05"), Decimal("1.5"))
            for locale in LOCALES
        }
        assert wanted <= covered

    def test_the_app_test_reads_this_same_table(self) -> None:
        mobile = ROOT / "apps" / "mobile" / "src" / "lib" / "records" / "extraction.test.ts"
        source = mobile.read_text(encoding="utf-8")
        assert '"quantity_render.json"' in source
        assert "formatQuantity(" in source


# --------------------------------------------------------------------------------------------
# Acceptance 3 — no numeral reaches TTS; the compiler expansion path is untouched
# --------------------------------------------------------------------------------------------


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
        elif isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
    return found


class TestTheScreenRendererStaysOffTheSpeechPath:
    def test_nothing_on_the_protocol_or_voice_path_imports_the_records_renderer(self) -> None:
        """The comma is for a reader. Speech gets the compiler's Turkish
        orthography and never a numeral, so no TTS or compiler module may
        reach this renderer."""
        roots = (
            ROOT / "packages" / "protocols" / "src",
            ROOT / "packages" / "voice-clips" / "src",
            ROOT / "services" / "voice-runtime" / "src",
        )
        offenders = [
            str(path.relative_to(ROOT))
            for root in roots
            for path in sorted(root.rglob("*.py"))
            if any(module.startswith("intake_platform.records") for module in _imports(path))
        ]
        assert offenders == []

    def test_the_records_renderer_imports_no_speech_module(self) -> None:
        records = ROOT / "packages" / "intake_platform" / "src" / "intake_platform" / "records"
        for path in sorted(records.glob("*.py")):
            for module in _imports(path):
                assert not any(word in module for word in ("tts", "speech", "voice", "clips")), (
                    path.name,
                    module,
                )


# --------------------------------------------------------------------------------------------
# INT-386 — the typed rail, the clinician note, the patient summary and the FHIR narrative
# --------------------------------------------------------------------------------------------

#: A synthetic step id for the typed rail (files/04 §7). Not a pack reference.
STEP = "sentetik.olcum"


def _measure(value: Decimal, unit: str) -> SelfReportedMeasure:
    return SelfReportedMeasure(code=MeasureCode.WEIGHT, magnitude=value, unit=unit)


def _after_label(line: str) -> str:
    """The atom of a ``<code>: <atom>`` line, which is how the note and the
    FHIR narrative both label a self-reported measure."""
    label, joiner, atom = line.partition(": ")
    assert (label, joiner) == ("weight", ": "), line
    return atom


def _typed_rail(value: Decimal, unit: str, locale: str) -> str:
    facts = {
        STEP: SlotFacts(step_id=STEP, slot_type=SlotType.QUANTITY, critical_path=True, unit=unit)
    }
    return numeric_rail({STEP: value}, facts, locale=locale)[STEP]


#: Every text surface a clinical quantity reaches, each asked for one atom.
#: The records renderer is INT-385's. The other five are INT-386's: the four
#: renderers INT-096 recorded, with the typed profile's two entry points.
RENDERERS: dict[str, Callable[[Decimal, str, str], str]] = {
    "records.quantity_atom": lambda value, unit, locale: quantity_atom(value, unit, locale=locale),
    "typed.render_measure": lambda value, unit, locale: render_measure(value, unit, locale=locale),
    "typed.numeric_rail": _typed_rail,
    "note.composer": lambda value, unit, locale: _after_label(
        note_composer._measure_line(_measure(value, unit), locale=locale)
    ),
    "summary.builder": lambda value, unit, locale: summary_builder._measure_text(
        _measure(value, unit), locale=locale
    ),
    "mappers.document": lambda value, unit, locale: _after_label(
        fhir_document._measure_line(_measure(value, unit), locale=locale)
    ),
}


def _row_id(row: dict[str, str]) -> str:
    return f"{row['value']}-{row['locale']}"


class TestEveryTextRendererWritesTheSharedTable:
    """One table, six entry points, one answer per row (INT-386 acceptance 2)."""

    @pytest.mark.parametrize("row", _table(), ids=_row_id)
    @pytest.mark.parametrize("renderer", RENDERERS)
    def test_the_renderer_writes_the_rows_atom(self, renderer: str, row: dict[str, str]) -> None:
        written = RENDERERS[renderer](Decimal(row["value"]), row["unit"], row["locale"])
        assert written == row["atom"]

    @pytest.mark.parametrize("row", _table(), ids=_row_id)
    @pytest.mark.parametrize("renderer", RENDERERS)
    def test_what_the_renderer_writes_round_trips_for_its_reader(
        self, renderer: str, row: dict[str, str]
    ) -> None:
        """The parser that exists is the ingestion resolver, and the reader is
        the test-side model of a person of that locale. Both must read back the
        value that was rendered."""
        value = Decimal(row["value"])
        written = RENDERERS[renderer](value, row["unit"], row["locale"])
        assert _round_trips(written, locale=row["locale"], unit=row["unit"], value=value)

    @pytest.mark.parametrize("renderer", RENDERERS)
    def test_a_full_stop_in_turkish_fails(self, renderer: str) -> None:
        """The near miss. Each renderer's own Turkish output passes, and the
        same output with the comma put back as a full stop, which is what all
        four wrote before INT-386, fails."""
        written = RENDERERS[renderer](Decimal("12.5"), "mg/dL", "tr")
        assert written == f"12,5{NBSP}mg/dL"
        assert "." not in written
        assert _round_trips(written, locale="tr", unit="mg/dL", value=Decimal("12.5"))
        assert not _round_trips(
            written.replace(",", "."), locale="tr", unit="mg/dL", value=Decimal("12.5")
        )

    @pytest.mark.parametrize("locale", LOCALES)
    @pytest.mark.parametrize("renderer", RENDERERS)
    def test_no_renderer_groups_digits(self, renderer: str, locale: str) -> None:
        written = RENDERERS[renderer](Decimal("1500000.25"), "mg", locale)
        point = DECIMAL_SEPARATORS[locale]
        assert written == f"1500000{point}25{NBSP}mg"

    @pytest.mark.parametrize("renderer", RENDERERS)
    def test_no_renderer_guesses_a_point_for_an_unrecorded_locale(self, renderer: str) -> None:
        """A session locale with no recorded decimal point is refused on every
        surface, the typed rail included, rather than written with a guess."""
        with pytest.raises(QuantityLocaleUnknown):
            RENDERERS[renderer](Decimal("12.5"), "mg/dL", "de")

    def test_there_is_one_renderer_and_the_records_package_re_exports_it(self) -> None:
        """Moved to the lowest layer so the FHIR mapper can reach it. The
        records package hands out the same objects, not a second copy."""
        assert records_package.render_quantity is shared.render_quantity
        assert records_package.quantity_atom is shared.quantity_atom
        assert records_package.NBSP is shared.NBSP
        assert records_package.DECIMAL_SEPARATORS is shared.DECIMAL_SEPARATORS
        assert records_package.QuantityLocaleUnknown is shared.QuantityLocaleUnknown

    def test_the_table_names_every_text_renderer_it_holds(self) -> None:
        about = json.loads(TABLE.read_text(encoding="utf-8"))["about"]
        for name in ("render_measure", "numeric_rail", "_measure_line", "_measure_text"):
            assert name in about, name


def _konusma() -> KonusmaOzellikleri:
    return KonusmaOzellikleri(
        speech_rate_syll_s=4.1,
        pause_ratio=0.22,
        f0_mean_hz=142.5,
        f0_sd_hz=21.0,
        response_latency_ms_mean=610.25,
        reference_ranges={"speech_rate_syll_s": "sentetik"},
        recording_conditions_caveat_tr="sentetik kayıt koşulu",
    )


KONUSMA_FIELDS = (
    "speech_rate_syll_s",
    "pause_ratio",
    "f0_mean_hz",
    "f0_sd_hz",
    "response_latency_ms_mean",
)


class TestSpeechFeaturesAreQuantitiesToo:
    """The document's konuşma özellikleri lines carry measured floats. They go
    through the same renderer, by way of the digits Python prints for the
    float and never its binary expansion."""

    @pytest.mark.parametrize(
        ("locale", "expected"),
        [
            (
                "tr",
                [
                    f"speech_rate_syll_s: 4,1{NBSP}syll/s",
                    "pause_ratio: 0,22",
                    f"f0_mean_hz: 142,5{NBSP}Hz",
                    f"f0_sd_hz: 21,0{NBSP}Hz",
                    f"response_latency_ms_mean: 610,25{NBSP}ms",
                ],
            ),
            (
                "en",
                [
                    f"speech_rate_syll_s: 4.1{NBSP}syll/s",
                    "pause_ratio: 0.22",
                    f"f0_mean_hz: 142.5{NBSP}Hz",
                    f"f0_sd_hz: 21.0{NBSP}Hz",
                    f"response_latency_ms_mean: 610.25{NBSP}ms",
                ],
            ),
        ],
    )
    def test_the_document_writes_each_measure_for_its_reader(
        self, locale: str, expected: list[str]
    ) -> None:
        lines = fhir_document._konusma_lines(_konusma(), locale=locale)
        assert lines[: len(KONUSMA_FIELDS)] == expected

    def test_each_speech_measure_reads_back_as_the_float_it_was(self) -> None:
        block = _konusma()
        lines = fhir_document._konusma_lines(block, locale="tr")
        for line, field in zip(lines, KONUSMA_FIELDS, strict=False):
            number = line.partition(": ")[2].partition(NBSP)[0]
            assert float(_read_as("tr", number)) == getattr(block, field), line
            assert float(parse_printed_magnitude(number)) == getattr(block, field), line

    def test_a_float_is_read_by_its_printed_digits_not_its_binary_expansion(self) -> None:
        assert shared.float_magnitude(4.1) == Decimal("4.1")
        assert Decimal(4.1) != Decimal("4.1")
        assert shared.render_quantity(shared.float_magnitude(1e-05), locale="tr") == "0,00001"
        assert shared.render_quantity(shared.float_magnitude(1e16), locale="tr") == (
            "10000000000000000"
        )

    @pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
    def test_a_float_that_is_not_a_number_is_refused(self, value: float) -> None:
        with pytest.raises(ValueError, match="finite"):
            shared.float_magnitude(value)


#: The modules that hand text or audio to a speech model, or build the clips.
TTS_PATH: tuple[str, ...] = (
    "intake_voice_runtime.talker.speech",
    "intake_voice_runtime.adapters.speech",
    "intake_voice_runtime.talker.clips",
    "intake_voice_runtime.talker.egress",
    "voice_clips",
    "voice_clips.build",
)

#: Every module that writes a clinical quantity as screen or document text.
SCREEN_RENDERERS: tuple[str, ...] = (
    "clinical_schemas.quantity",
    "clinical_schemas.mappers.document",
    "intake_platform.records.numbers",
    "intake_voice_runtime.typed.render",
    "intake_voice_runtime.note.composer",
    "intake_voice_runtime.note.render",
    "intake_voice_runtime.summary.builder",
)

#: The only voice-runtime modules that may import the shared renderer.
RUNTIME_IMPORTERS: frozenset[str] = frozenset(
    {"typed/render.py", "note/composer.py", "note/render.py", "summary/builder.py"}
)

QUANTITY_MODULE = (
    ROOT / "packages" / "clinical-schemas" / "src" / "clinical_schemas" / "quantity.py"
)


class TestTheSharedRendererStaysOffTheSpeechPath:
    """No numeral reaches TTS (invariant 22). The typed rail lives in the
    same package as the Talker, so the boundary is checked at runtime and
    not only by reading import lines."""

    @pytest.mark.parametrize("module", TTS_PATH)
    def test_loading_a_tts_path_module_loads_no_screen_renderer(self, module: str) -> None:
        """Each module is imported in a fresh interpreter, and what that import
        pulled into ``sys.modules`` is read back."""
        probe = (
            "import importlib, json, sys\n"
            f"importlib.import_module({module!r})\n"
            f"print(json.dumps([n for n in {SCREEN_RENDERERS!r} if n in sys.modules]))\n"
        )
        done = subprocess.run(
            [sys.executable, "-c", probe], capture_output=True, text=True, check=True
        )
        assert json.loads(done.stdout) == []

    def test_the_compiler_and_the_clip_path_never_import_the_shared_renderer(self) -> None:
        roots = (
            ROOT / "packages" / "protocols" / "src",
            ROOT / "packages" / "voice-clips" / "src",
        )
        offenders = [
            str(path.relative_to(ROOT))
            for root in roots
            for path in sorted(root.rglob("*.py"))
            if "clinical_schemas.quantity" in _imports(path)
        ]
        assert offenders == []

    def test_only_the_four_screen_renderers_import_it_in_the_runtime(self) -> None:
        runtime = ROOT / "services" / "voice-runtime" / "src" / "intake_voice_runtime"
        importers = {
            path.relative_to(runtime).as_posix()
            for path in sorted(runtime.rglob("*.py"))
            if "clinical_schemas.quantity" in _imports(path)
        }
        assert importers == RUNTIME_IMPORTERS

    def test_the_shared_renderer_imports_only_the_standard_library(self) -> None:
        assert _imports(QUANTITY_MODULE) <= {
            "__future__",
            "collections.abc",
            "decimal",
            "math",
            "types",
            "typing",
        }

    def test_the_shared_renderer_holds_no_arithmetic(self) -> None:
        """INT-124's structural rule for the parser, kept for the renderer
        now that it has moved: a module with no multiplication, division or
        power operator cannot rescale a magnitude."""
        forbidden = (ast.Mult, ast.Div, ast.FloorDiv, ast.Pow, ast.Mod, ast.MatMult)
        tree = ast.parse(QUANTITY_MODULE.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.BinOp | ast.AugAssign):
                assert not isinstance(node.op, forbidden), node.lineno
            if isinstance(node, ast.Attribute):
                assert node.attr not in {"scaleb", "shift", "quantize"}, node.lineno

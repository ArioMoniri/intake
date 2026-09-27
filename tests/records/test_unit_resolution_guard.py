"""INT-124 — the Turkish unit-resolution guard (deterministic; no model involved).

The acceptance clauses under test, verbatim (docs/backlog/issues.yaml INT-124):

    "unit resolution is a GUARD, not an assumption: magnitude outranks the
     printed unit token, and disagreement raises a flag rather than converting
     silently"
    "`ure` is never substring-matched - Ure and BUN differ by a factor of 2.14,
     and `Ure Nitrojeni` contains the token but means BUN"
    "decimal separator resolved PER VALUE, not per document, cross-checked
     against the analyte's expected magnitude - Turkish handbooks mix comma and
     period within one page"
    "... a five-digit result carrying a thousands separator; a two-number
     reference cell stops the parse rather than averaging"

sec_row: `records` (docs/security/threat-model.md): *"ingestion unit rule
(CLAUDE.md invariant 22: magnitude outranks the printed unit token,
disagreement flags)"*.

**No clinical value is authored here.** The shipped expectation table is
empty (HUMAN_BLOCKERS.md HB-C24), so every behaviour that needs an expected
unit or an expected magnitude is exercised against a *test double*: synthetic
analyte names (``Analit A``), synthetic units (``birim-a``) and a citation to
``example.invalid``. Where a real analyte name appears with a unit, the unit is
the one files/03 §4.9.6 states in those words (ALT in U/L), exactly as INT-121's
suite already uses it, and its magnitude band is deliberately unbounded so the
test says nothing about what a normal ALT is.
"""

from __future__ import annotations

import ast
import datetime as dt
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from clinical_schemas.records import RecordItemKind
from intake_platform.records import TextRegion, extract_record_items
from intake_platform.records.analytes import AnalyteAmbiguous, analyte_key
from intake_platform.records.unit_guard import (
    EXPECTATION_TABLE_BLOCKER,
    SHIPPED_EXPECTATIONS,
    STOP_FLAGS,
    AnalyteExpectation,
    ExpectationTable,
    ExpectationTableInvalid,
    GuardFlag,
    LabValueVerdict,
    SeparatorResolution,
    SourceCitation,
    guard_lab_value,
)

REPO = Path(__file__).resolve().parents[2]
RECORDS_PKG = REPO / "packages" / "intake_platform" / "src" / "intake_platform" / "records"

#: A citation that cannot be mistaken for a source: the ``.invalid`` TLD is
#: reserved (RFC 2606) and the id says what it is.
TEST_DOUBLE_SOURCE = SourceCitation(
    guideline_id="test-double-not-a-clinical-source",
    version="0",
    date=dt.date(2026, 9, 27),
    url="https://example.invalid/int-124-test-double",
    retrieved_on=dt.date(2026, 9, 27),
)

#: A band that admits every magnitude a fixture prints, for tests that are
#: about the unit token and must say nothing about the magnitude.
UNBOUNDED_LOW = Decimal("0")
UNBOUNDED_HIGH = Decimal("1E+12")


def _row(
    unit: str, low: Decimal = UNBOUNDED_LOW, high: Decimal = UNBOUNDED_HIGH
) -> AnalyteExpectation:
    return AnalyteExpectation(
        unit=unit, magnitude_low=low, magnitude_high=high, source=TEST_DOUBLE_SOURCE
    )


def _table(**rows: AnalyteExpectation) -> ExpectationTable:
    return ExpectationTable({name.replace("_", " "): row for name, row in rows.items()})


def _guard(
    name: str, value: str | None, unit: str | None, table: ExpectationTable = SHIPPED_EXPECTATIONS
) -> LabValueVerdict:
    return guard_lab_value(printed_name=name, printed_value=value, printed_unit=unit, table=table)


# --------------------------------------------------------------------------------------------
# The shipped table is empty, and an empty table fails closed
# --------------------------------------------------------------------------------------------


class TestTheShippedTableIsEmptyAndFailsClosed:
    """HB-C24 is open: no human has said which unit and which magnitude band
    belong to which analyte. So the guard ships with nothing to check against,
    and "nothing to check against" is a flag on every value, never a pass."""

    def test_the_shipped_table_carries_no_expectation_at_all(self) -> None:
        assert len(SHIPPED_EXPECTATIONS) == 0
        assert EXPECTATION_TABLE_BLOCKER == "HB-C24"

    def test_the_blocker_the_table_names_is_an_open_human_blockers_row(self) -> None:
        blockers = (REPO / "files" / "HUMAN_BLOCKERS.md").read_text(encoding="utf-8")
        row = next(line for line in blockers.splitlines() if line.startswith("| **HB-C24**"))
        assert "| **open** |" in row
        assert "INT-124" in row

    @pytest.mark.parametrize(
        ("name", "value", "unit"),
        [
            ("ALT", "30", "U/L"),
            ("ALT", "30", "U/mL"),
            ("Üre", "45", "mg/dL"),
            ("Üre Nitrojeni", "21", "mg/dL"),
            ("Kalsiyum", "8,4", "mg/dL"),
            ("Potasyum", "4.5", "mmol/L"),
            ("Lökosit", "12.500,00", "/µL"),
        ],
    )
    def test_every_value_through_the_shipped_table_is_flagged(
        self, name: str, value: str, unit: str
    ) -> None:
        verdict = _guard(name, value, unit)
        assert GuardFlag.NO_EXPECTATION in verdict.flags
        assert verdict.flagged
        assert verdict.expected_unit is None

    def test_the_near_miss_a_matching_expectation_raises_no_flag(self) -> None:
        """Without this, the test above passes for a guard that flags
        everything unconditionally — which converts nothing and helps nobody."""
        verdict = _guard("Analit A", "30", "birim-a", _table(Analit_A=_row("birim-a")))
        assert verdict.flags == frozenset()
        assert not verdict.flagged
        assert verdict.magnitude == Decimal("30")

    def test_an_unflagged_verdict_is_only_reachable_through_an_authored_row(self) -> None:
        verdict = _guard("Analit A", "30", "birim-a", _table(Analit_B=_row("birim-a")))
        assert verdict.flags == {GuardFlag.NO_EXPECTATION}


# --------------------------------------------------------------------------------------------
# Magnitude outranks the printed unit token; disagreement flags, never converts
# --------------------------------------------------------------------------------------------


class TestMagnitudeOutranksThePrintedUnitToken:
    """files/03 §4.9.6: a published 2024 Turkish handbook prints adult ALT in
    ``U/mL`` when the values are ``U/L`` — wrong by 1000x. The magnitude is the
    trustworthy half; the token is the suspect. Nothing is rescaled."""

    def test_a_wrong_printed_unit_is_flagged_and_the_magnitude_is_untouched(self) -> None:
        verdict = _guard("ALT", "30", "U/mL", _table(ALT=_row("U/L")))
        assert verdict.flags == {GuardFlag.UNIT_CONFLICT}
        assert verdict.magnitude == Decimal("30")
        assert verdict.magnitude is not None
        assert verdict.magnitude.as_tuple() == Decimal("30").as_tuple()
        assert verdict.printed_unit == "U/mL"
        assert verdict.expected_unit == "U/L"

    def test_the_near_miss_the_same_line_in_the_expected_unit_is_clean(self) -> None:
        verdict = _guard("ALT", "30", "U/L", _table(ALT=_row("U/L")))
        assert GuardFlag.UNIT_CONFLICT not in verdict.flags
        assert verdict.flags == frozenset()

    def test_a_magnitude_outside_the_band_is_flagged_and_still_not_rescaled(self) -> None:
        table = _table(Analit_A=_row("birim-a", Decimal("10"), Decimal("20")))
        verdict = _guard("Analit A", "30000", "mbirim-a", table)
        assert verdict.flags == {GuardFlag.UNIT_CONFLICT, GuardFlag.MAGNITUDE_OUTSIDE_EXPECTED}
        assert verdict.magnitude == Decimal("30000")
        assert verdict.printed_unit == "mbirim-a"

    def test_inside_the_band_the_magnitude_is_believed_over_the_token(self) -> None:
        table = _table(Analit_A=_row("birim-a", Decimal("10"), Decimal("20")))
        verdict = _guard("Analit A", "15", "mbirim-a", table)
        assert verdict.flags == {GuardFlag.UNIT_CONFLICT}
        assert verdict.magnitude == Decimal("15")

    def test_the_near_miss_inside_the_band_in_the_expected_unit_is_clean(self) -> None:
        table = _table(Analit_A=_row("birim-a", Decimal("10"), Decimal("20")))
        assert _guard("Analit A", "15", "birim-a", table).flags == frozenset()

    def test_the_band_edges_are_inside(self) -> None:
        table = _table(Analit_A=_row("birim-a", Decimal("10"), Decimal("20")))
        assert _guard("Analit A", "10", "birim-a", table).flags == frozenset()
        assert _guard("Analit A", "20", "birim-a", table).flags == frozenset()
        assert _guard("Analit A", "20,01", "birim-a", table).flags == {
            GuardFlag.MAGNITUDE_OUTSIDE_EXPECTED
        }

    def test_micro_sign_and_greek_mu_are_different_units(self) -> None:
        """files/03 §4.9.6 keeps ``µ`` U+00B5 and ``μ`` U+03BC distinct on
        purpose. A synonym table is where a silent conversion comes back."""
        table = _table(Analit_A=_row("µmol/L"))
        assert _guard("Analit A", "5", "μmol/L", table).flags == {GuardFlag.UNIT_CONFLICT}
        assert _guard("Analit A", "5", "µmol/L", table).flags == frozenset()

    def test_a_missing_unit_token_against_an_expectation_is_a_conflict(self) -> None:
        verdict = _guard("Analit A", "5", None, _table(Analit_A=_row("birim-a")))
        assert verdict.flags == {GuardFlag.UNIT_CONFLICT}
        assert verdict.printed_unit is None

    def test_surrounding_whitespace_is_not_a_unit(self) -> None:
        assert _guard("Analit A", "5", "  birim-a ", _table(Analit_A=_row("birim-a"))).flags == (
            frozenset()
        )

    def test_the_printed_unit_never_decides_which_reading_of_a_separator_is_taken(self) -> None:
        table = _table(Analit_A=_row("birim-a", Decimal("1000"), Decimal("2000")))
        readings = {
            _guard("Analit A", "1.500", unit, table).magnitude
            for unit in ("birim-a", "mbirim-a", "kbirim-a", None)
        }
        assert readings == {Decimal("1500")}

    def test_the_guard_and_the_parser_contain_no_arithmetic_at_all(self) -> None:
        """*"disagreement raises a flag rather than converting silently"*,
        made structural: a module with no multiplication, division or power
        operator cannot rescale a magnitude, whatever a later edit intends."""
        forbidden = (ast.Mult, ast.Div, ast.FloorDiv, ast.Pow, ast.Mod, ast.MatMult)
        for name in ("unit_guard.py", "numbers.py", "analytes.py"):
            tree = ast.parse((RECORDS_PKG / name).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.BinOp | ast.AugAssign):
                    assert not isinstance(node.op, forbidden), f"{name}:{node.lineno}"
                if isinstance(node, ast.Attribute):
                    assert node.attr not in {"scaleb", "shift", "quantize"}, f"{name}:{node.lineno}"


# --------------------------------------------------------------------------------------------
# `üre` is never substring-matched
# --------------------------------------------------------------------------------------------


class TestUreIsNeverSubstringMatched:
    """files/03 §4.9.6: *"``Üre 45 mg/dL`` is near-normal while ``BUN 45
    mg/dL`` is markedly azotaemic (factor 2.14), and ``Üre Nitrojeni``
    contains the token 'Üre' but means BUN"*."""

    @pytest.mark.parametrize(
        ("printed", "key"),
        [
            ("Üre", "urea"),
            ("ÜRE", "urea"),
            ("BUN", "bun"),
            ("Üre Nitrojeni", "bun"),
            ("ÜRE NİTROJENİ", "bun"),
            ("üre   nitrojeni", "bun"),
            ("Kreatinin", "kreatinin"),
            ("KREATİNİN", "kreatinin"),
            ("  ALT  ", "alt"),
        ],
    )
    def test_the_key_is_the_whole_token_sequence_under_turkish_casing(
        self, printed: str, key: str
    ) -> None:
        assert analyte_key(printed) == key

    def test_the_near_miss_ure_nitrojeni_is_never_keyed_as_urea(self) -> None:
        assert analyte_key("Üre Nitrojeni") != analyte_key("Üre")

    def test_dotted_capital_i_folds_the_turkish_way_before_the_table_is_read(self) -> None:
        """Python's default ``casefold`` turns ``İ`` into ``i`` plus a
        combining dot, so ``ÜRE NİTROJENİ`` would miss the BUN row and
        ``ÜREMİ`` would stop being the same string as ``Üremi``. The Turkish
        fold makes the upper-case spellings the same near miss, refused."""
        assert "ÜREMİ".casefold() != "üremi"
        with pytest.raises(AnalyteAmbiguous):
            analyte_key("ÜREMİ")

    @pytest.mark.parametrize(
        "printed", ["Üremi", "ÜREMİ", "Üre (serum)", "Serum Üre", "BUN/Kreatinin"]
    )
    def test_a_name_that_carries_the_token_without_resolving_is_flagged_and_not_read(
        self, printed: str
    ) -> None:
        verdict = _guard(printed, "45", "mg/dL")
        assert verdict.flags == {GuardFlag.ANALYTE_AMBIGUOUS}
        assert verdict.magnitude is None
        assert verdict.analyte_key is None

    def test_the_expectation_follows_the_analyte_not_the_substring(self) -> None:
        """Routing, not just naming: ``Üre Nitrojeni`` is checked against BUN's
        row. The synthetic units make it impossible to read a clinical claim
        into the test."""
        table = _table(Üre=_row("u-birim"), BUN=_row("b-birim"))
        assert _guard("Üre Nitrojeni", "21", "b-birim", table).flags == frozenset()
        assert _guard("BUN", "21", "b-birim", table).flags == frozenset()
        assert _guard("Üre", "21", "u-birim", table).flags == frozenset()

    def test_the_near_miss_ure_nitrojeni_against_ures_row_is_a_conflict(self) -> None:
        table = _table(Üre=_row("u-birim"), BUN=_row("b-birim"))
        assert _guard("Üre Nitrojeni", "21", "u-birim", table).flags == {GuardFlag.UNIT_CONFLICT}
        assert _guard("Üre", "21", "b-birim", table).flags == {GuardFlag.UNIT_CONFLICT}

    def test_a_table_cannot_key_one_analyte_twice_under_two_spellings(self) -> None:
        with pytest.raises(ExpectationTableInvalid):
            ExpectationTable({"BUN": _row("b-birim"), "Üre Nitrojeni": _row("b-birim")})

    def test_a_table_cannot_key_a_near_miss(self) -> None:
        with pytest.raises(ExpectationTableInvalid):
            ExpectationTable({"Üremi": _row("u-birim")})

    def test_a_table_cannot_key_nothing(self) -> None:
        with pytest.raises(ExpectationTableInvalid):
            ExpectationTable({"   ": _row("birim-a")})

    def test_a_table_is_keyed_through_the_same_function_as_a_printed_name(self) -> None:
        table = ExpectationTable({"ÜRE NİTROJENİ": _row("b-birim")})
        assert table.keys() == ("bun",)
        assert table.get("bun") is not None
        assert table.get("urea") is None


# --------------------------------------------------------------------------------------------
# The decimal separator, per value, cross-checked against the expected magnitude
# --------------------------------------------------------------------------------------------


class TestTheSeparatorIsResolvedPerValue:
    """files/03 §4.9.6: *"all three hospital handbooks parsed use comma in
    monographs (``8,4 - 10,2 mg/dL``) and period in their critical-value tables
    (``≤ 2.5``, ``≥ 13.0``), and Erciyes mixes both on one page — so you cannot
    pick a locale per document"*."""

    def test_comma_and_period_decimals_on_one_page_each_resolve(self) -> None:
        page = [
            ("Kalsiyum", "8,4"),
            ("Potasyum", "4.5"),
            ("Analit A", "0,08"),
            ("Analit B", "0.123"),
        ]
        magnitudes = [_guard(name, value, "x").magnitude for name, value in page]
        assert magnitudes == [Decimal("8.4"), Decimal("4.5"), Decimal("0.08"), Decimal("0.123")]

    def test_an_unambiguous_single_reading_says_so(self) -> None:
        assert _guard("Kalsiyum", "8,4", "mg/dL").separator is SeparatorResolution.SINGLE_READING

    @pytest.mark.parametrize("printed", ["1.500", "1,500"])
    def test_with_no_expected_magnitude_a_two_way_form_stops(self, printed: str) -> None:
        verdict = _guard("Analit A", printed, "birim-a")
        assert GuardFlag.SEPARATOR_AMBIGUOUS in verdict.flags
        assert verdict.magnitude is None
        assert verdict.separator is SeparatorResolution.STOPPED

    @pytest.mark.parametrize("printed", ["1.500", "1,500"])
    def test_the_expected_magnitude_picks_the_grouped_reading(self, printed: str) -> None:
        table = _table(Analit_A=_row("birim-a", Decimal("1000"), Decimal("2000")))
        verdict = _guard("Analit A", printed, "birim-a", table)
        assert verdict.magnitude == Decimal("1500")
        assert verdict.separator is SeparatorResolution.EXPECTED_MAGNITUDE
        assert verdict.flags == frozenset()

    @pytest.mark.parametrize("printed", ["1.500", "1,500"])
    def test_the_near_miss_the_same_characters_read_as_a_decimal_elsewhere(
        self, printed: str
    ) -> None:
        table = _table(Analit_B=_row("birim-b", Decimal("1"), Decimal("2")))
        verdict = _guard("Analit B", printed, "birim-b", table)
        assert verdict.magnitude == Decimal("1.5")
        assert verdict.separator is SeparatorResolution.EXPECTED_MAGNITUDE

    def test_one_page_two_analytes_the_same_characters_two_readings(self) -> None:
        """PER VALUE, not per document: the decision belongs to the value."""
        table = _table(
            Analit_A=_row("birim-a", Decimal("1000"), Decimal("2000")),
            Analit_B=_row("birim-b", Decimal("1"), Decimal("2")),
        )
        a = _guard("Analit A", "1.500", "birim-a", table)
        b = _guard("Analit B", "1.500", "birim-b", table)
        assert (a.magnitude, b.magnitude) == (Decimal("1500"), Decimal("1.5"))

    def test_a_band_that_admits_both_readings_decides_nothing(self) -> None:
        table = _table(Analit_A=_row("birim-a", Decimal("1"), Decimal("2000")))
        verdict = _guard("Analit A", "1.500", "birim-a", table)
        assert verdict.flags == {GuardFlag.SEPARATOR_AMBIGUOUS}
        assert verdict.magnitude is None

    def test_a_band_that_admits_neither_reading_decides_nothing(self) -> None:
        table = _table(Analit_A=_row("birim-a", Decimal("3"), Decimal("4")))
        verdict = _guard("Analit A", "1.500", "birim-a", table)
        assert verdict.flags == {GuardFlag.SEPARATOR_AMBIGUOUS}
        assert verdict.magnitude is None


class TestAFiveDigitResultWithAThousandsSeparator:
    """``parseFloat("12.500")`` is ``12.5`` where Turkish grouping says
    ``12500`` — a ÷1000 error with no diff that shows it."""

    @pytest.mark.parametrize(
        ("printed", "expected"),
        [
            ("12.500,00", Decimal("12500.00")),
            ("12.500,0", Decimal("12500.0")),
            ("12,500.00", Decimal("12500.00")),
            ("1.250.000", Decimal("1250000")),
        ],
    )
    def test_a_form_with_one_reading_parses_exactly_with_no_table(
        self, printed: str, expected: Decimal
    ) -> None:
        verdict = _guard("Lökosit", printed, "/µL")
        assert verdict.magnitude == expected
        assert verdict.magnitude is not None
        assert verdict.magnitude.as_tuple() == expected.as_tuple()
        assert verdict.flags == {GuardFlag.NO_EXPECTATION}

    @pytest.mark.parametrize("printed", ["12.500", "12,500"])
    def test_the_bare_five_digit_form_is_never_read_as_twelve_and_a_half_without_a_band(
        self, printed: str
    ) -> None:
        verdict = _guard("Lökosit", printed, "/µL")
        assert verdict.magnitude is None
        assert GuardFlag.SEPARATOR_AMBIGUOUS in verdict.flags

    @pytest.mark.parametrize("printed", ["12.500", "12,500"])
    def test_the_expected_magnitude_reads_it_as_twelve_thousand_five_hundred(
        self, printed: str
    ) -> None:
        table = _table(Analit_A=_row("birim-a", Decimal("10000"), Decimal("20000")))
        assert _guard("Analit A", printed, "birim-a", table).magnitude == Decimal("12500")

    def test_the_near_miss_a_band_near_twelve_reads_twelve_and_a_half(self) -> None:
        table = _table(Analit_A=_row("birim-a", Decimal("10"), Decimal("20")))
        assert _guard("Analit A", "12.500", "birim-a", table).magnitude == Decimal("12.5")

    def test_a_space_grouped_value_is_two_numbers_and_stops(self) -> None:
        verdict = _guard("Lökosit", "12 500", "/µL")
        assert verdict.magnitude is None
        assert GuardFlag.TWO_NUMBER_CELL in verdict.flags


# --------------------------------------------------------------------------------------------
# A two-number reference cell stops the parse rather than averaging
# --------------------------------------------------------------------------------------------


class TestATwoNumberCellStopsTheParse:
    """files/03 §4.9.6: *"a two-number reference cell is a signal to stop, not
    to average — a dual-unit reference column mis-aligned by one reads glucose
    3.33–5.55 as mg/dL"*."""

    @pytest.mark.parametrize(
        "printed", ["3,33 - 5,55", "3.33–5.55", "8,4 - 10,2", "70-110", "70 / 110", "3,33 5,55"]
    )
    def test_the_parse_stops_and_no_number_comes_out(self, printed: str) -> None:
        verdict = _guard("Glukoz", printed, "mg/dL")
        assert verdict.magnitude is None
        assert GuardFlag.TWO_NUMBER_CELL in verdict.flags
        assert verdict.separator is SeparatorResolution.STOPPED

    def test_it_is_never_the_mean_and_never_either_end(self) -> None:
        verdict = _guard("Glukoz", "3,33 - 5,55", "mg/dL")
        assert verdict.magnitude not in {Decimal("4.44"), Decimal("3.33"), Decimal("5.55")}

    def test_a_band_that_would_admit_the_mean_does_not_rescue_it(self) -> None:
        table = _table(Analit_A=_row("birim-a", Decimal("4"), Decimal("5")))
        verdict = _guard("Analit A", "3,33 - 5,55", "birim-a", table)
        assert verdict.magnitude is None
        assert verdict.flags == {GuardFlag.TWO_NUMBER_CELL}

    @pytest.mark.parametrize("printed", ["-5", "+5", "5"])
    def test_the_near_miss_a_signed_single_number_is_one_number(self, printed: str) -> None:
        verdict = _guard("Analit A", printed, "birim-a")
        assert GuardFlag.TWO_NUMBER_CELL not in verdict.flags
        assert verdict.magnitude is not None

    @pytest.mark.parametrize("printed", [">100.000", "<5", "≤ 2.5", "≥ 13.0"])
    def test_a_bound_is_not_a_magnitude_and_stops(self, printed: str) -> None:
        verdict = _guard("Analit A", printed, "birim-a")
        assert verdict.magnitude is None
        assert GuardFlag.BOUND_NOT_MAGNITUDE in verdict.flags

    @pytest.mark.parametrize("printed", ["Negatif", "45.", "1,2,3", "", "   "])
    def test_a_shape_the_guard_does_not_recognise_stops(self, printed: str) -> None:
        verdict = _guard("Analit A", printed, "birim-a")
        assert verdict.magnitude is None
        assert GuardFlag.UNREADABLE in verdict.flags

    def test_a_row_with_no_value_is_flagged_rather_than_passed(self) -> None:
        verdict = _guard("Analit A", None, "birim-a", _table(Analit_A=_row("birim-a")))
        assert verdict.flags == {GuardFlag.VALUE_ABSENT}
        assert verdict.magnitude is None

    def test_every_stop_flag_leaves_no_magnitude(self) -> None:
        cases: list[tuple[str, str | None]] = [
            ("Üremi", "45"),
            ("Analit A", "1.500"),
            ("Analit A", "3,33 - 5,55"),
            ("Analit A", "<5"),
            ("Analit A", "Negatif"),
            ("Analit A", None),
        ]
        for name, value in cases:
            verdict = _guard(name, value, "x")
            assert verdict.flags & STOP_FLAGS, (name, value)
            assert verdict.magnitude is None
            assert verdict.stopped


# --------------------------------------------------------------------------------------------
# The expectation row cites a source, or it does not exist
# --------------------------------------------------------------------------------------------


class TestAnExpectationRowCitesItsSource:
    """CLAUDE.md: *"Never invent a value to unblock yourself"*. A row with no
    citation is not representable, so a plausible number with nothing behind it
    cannot enter the table by accident."""

    def test_a_row_without_a_source_cannot_be_built(self) -> None:
        with pytest.raises(TypeError):
            AnalyteExpectation(  # type: ignore[call-arg]
                unit="birim-a", magnitude_low=Decimal("1"), magnitude_high=Decimal("2")
            )

    @pytest.mark.parametrize(
        "override",
        [
            {"guideline_id": " "},
            {"version": ""},
            {"url": "http://example.invalid/x"},
            {"url": "example.invalid/x"},
        ],
    )
    def test_a_citation_that_names_nothing_is_refused(self, override: dict[str, Any]) -> None:
        fields: dict[str, Any] = {
            "guideline_id": "g",
            "version": "1",
            "date": dt.date(2026, 1, 1),
            "url": "https://example.invalid/x",
            "retrieved_on": dt.date(2026, 1, 1),
        }
        fields.update(override)
        with pytest.raises(ExpectationTableInvalid):
            SourceCitation(**fields)

    @pytest.mark.parametrize(
        ("unit", "low", "high"),
        [
            ("  ", Decimal("1"), Decimal("2")),
            ("birim-a", Decimal("2"), Decimal("1")),
            ("birim-a", Decimal("NaN"), Decimal("1")),
            ("birim-a", Decimal("1"), Decimal("Infinity")),
        ],
    )
    def test_a_row_that_bounds_nothing_is_refused(
        self, unit: str, low: Decimal, high: Decimal
    ) -> None:
        with pytest.raises(ExpectationTableInvalid):
            AnalyteExpectation(
                unit=unit, magnitude_low=low, magnitude_high=high, source=TEST_DOUBLE_SOURCE
            )


# --------------------------------------------------------------------------------------------
# Invariant 6 — the verdict and every refusal carry no document content
# --------------------------------------------------------------------------------------------


class TestNothingPrintedIsEchoed:
    def test_the_verdict_repr_names_flags_and_nothing_the_document_printed(self) -> None:
        verdict = _guard("Kalsiyum", "8,4", "mg/dL")
        for rendering in (repr(verdict), str(verdict)):
            assert "Kalsiyum" not in rendering
            assert "8,4" not in rendering and "8.4" not in rendering
            assert "mg/dL" not in rendering
            assert "no_expectation" in rendering

    def test_a_table_refusal_does_not_echo_the_key(self) -> None:
        with pytest.raises(ExpectationTableInvalid) as refusal:
            ExpectationTable({"Üremi": _row("u-birim")})
        assert "Üremi" not in str(refusal.value)
        assert "üremi" not in str(refusal.value)


# --------------------------------------------------------------------------------------------
# Wired into INT-121's parser: per-value verdicts instead of a whole-document refusal
# --------------------------------------------------------------------------------------------

DOCUMENT = "document:int124-guard"
AT = dt.datetime(2026, 9, 27, 9, 0, tzinfo=dt.UTC)
REGIONS = (
    TextRegion(page=1, bbox=(0.1, 0.10, 0.9, 0.14), start=0, end=11, text="ALT 30 U/mL"),
    TextRegion(
        page=1, bbox=(0.1, 0.16, 0.9, 0.20), start=12, end=37, text="Glukoz 3,33 - 5,55 mg/dL"
    ),
    TextRegion(page=1, bbox=(0.1, 0.22, 0.9, 0.26), start=38, end=53, text="Üremi 45 mg/dL"),
    TextRegion(page=1, bbox=(0.1, 0.28, 0.9, 0.32), start=54, end=66, text="Hipertansiyon"),
)


def _item(
    name: str, region: int, value: str | None, unit: str | None, kind: str = "lab"
) -> dict[str, Any]:
    return {
        "kind": kind,
        "printed_name": name,
        "region": region,
        "printed_value": value,
        "printed_unit": unit,
        "code_system": None,
        "code": None,
        "date": None,
    }


COMPLETION = {
    "items": [
        _item("ALT", 0, "30", "U/mL"),
        _item("Glukoz", 1, "3,33 - 5,55", "mg/dL"),
        _item("Üremi", 2, "45", "mg/dL"),
        _item("Hipertansiyon", 3, None, None, kind="diagnosis"),
    ]
}


class TestTheGuardInsideTheDocumentParser:
    def _extract(self, table: ExpectationTable = SHIPPED_EXPECTATIONS) -> Any:
        return extract_record_items(
            COMPLETION, document_ref=DOCUMENT, regions=REGIONS, observed_at=AT, guard=table
        )

    def test_every_lab_item_carries_a_verdict_and_every_other_item_none(self) -> None:
        extraction = self._extract()
        kinds = [item.kind for item in extraction.items]
        assert kinds == [RecordItemKind.LAB] * 3 + [RecordItemKind.DIAGNOSIS]
        assert [verdict is not None for verdict in extraction.verdicts] == [True, True, True, False]

    def test_a_stopped_value_keeps_its_box_and_loses_its_number(self) -> None:
        extraction = self._extract()
        glucose = extraction.items[1]
        assert glucose.value_magnitude is None
        assert glucose.box.page == 1 and glucose.box.start == 12
        assert glucose.summary == "Glukoz"

    def test_a_near_miss_analyte_is_one_flagged_row_not_a_lost_document(self) -> None:
        extraction = self._extract()
        verdict = extraction.verdicts[2]
        assert verdict is not None
        assert verdict.flags == {GuardFlag.ANALYTE_AMBIGUOUS}
        assert extraction.items[2].value_magnitude is None

    def test_through_the_shipped_table_every_guarded_value_is_flagged(self) -> None:
        extraction = self._extract()
        assert extraction.flagged == (0, 1, 2)
        assert extraction.items[0].value_magnitude == Decimal("30")
        assert extraction.units_unchecked == ("alt", "glukoz")

    def test_the_item_unit_conflict_mirrors_the_guard_flag(self) -> None:
        extraction = self._extract(_table(ALT=_row("U/L")))
        assert extraction.items[0].unit_conflict is True
        assert extraction.items[0].unit == "U/mL"
        assert extraction.items[0].value_magnitude == Decimal("30")

    def test_the_near_miss_the_same_row_in_the_expected_unit_has_no_conflict(self) -> None:
        completion = {"items": [_item("ALT", 0, "30", "U/L")]}
        extraction = extract_record_items(
            completion,
            document_ref=DOCUMENT,
            regions=REGIONS,
            observed_at=AT,
            guard=_table(ALT=_row("U/L")),
        )
        assert extraction.items[0].unit_conflict is False
        assert extraction.flagged == ()

    def test_two_sources_of_expectation_are_refused(self) -> None:
        with pytest.raises(ValueError, match="one source"):
            extract_record_items(
                COMPLETION,
                document_ref=DOCUMENT,
                regions=REGIONS,
                observed_at=AT,
                expected_units={"alt": "U/L"},
                guard=SHIPPED_EXPECTATIONS,
            )

    def test_without_the_guard_int121_behaviour_is_unchanged(self) -> None:
        """INT-121's parser refuses the document on a near-miss analyte; that
        path is not this issue's to change, and it carries no verdicts."""
        completion = {"items": [_item("ALT", 0, "30", "U/mL")]}
        extraction = extract_record_items(
            completion, document_ref=DOCUMENT, regions=REGIONS, observed_at=AT
        )
        assert extraction.verdicts == ()
        assert extraction.flagged == ()
        with pytest.raises(AnalyteAmbiguous):
            extract_record_items(
                {"items": [_item("Üremi", 2, "45", "mg/dL")]},
                document_ref=DOCUMENT,
                regions=REGIONS,
                observed_at=AT,
            )

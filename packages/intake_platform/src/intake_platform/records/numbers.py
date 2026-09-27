"""Printed magnitudes, and the three ways reading one corrupts it.

CLAUDE.md invariant 22: *"Numbers never cross a representation boundary
unguarded."* files/03 §4.9.6 channel 3 is the ingestion crossing, and every
failure below is a demonstrated one rather than a hypothetical:

* ``parseFloat("1.500")`` is ``1.5`` where Turkish grouping says ``1500`` — a
  ÷1000 error with no diff that shows it. The separator is **mixed within a
  single document** (all three Turkish hospital handbooks parsed use a comma in
  monographs and a period in their critical-value tables, and one mixes both on
  a page), so a locale cannot be chosen per document. It is resolved **per
  value**, and a form that reads two ways is refused rather than guessed.
* ``>100.000 mIU/mL`` under a naive en-US parse is ``100.0``, a 1000x error.
  A comparator makes the printed form a *bound*; dropping the qualifier to keep
  the number is itself a corruption, so the value is refused.
* ``8,4 - 10,2`` is a reference cell. §4.9.6: *"a two-number reference cell is
  a signal to stop, not to average"*.

What §4.9.6 also asks for — *"cross-checked against the analyte's expected
magnitude"* — is a clinical table no human has supplied (HUMAN_BLOCKERS.md
**HB-C24**). The fail-closed reading of the same rule is available and is what
runs: where a printed form reads two ways, refuse it. That refusal is strictly
safer than the cross-check would be and never becomes wrong when the table
lands; the table only turns some refusals into readings.

Rendering is the same rule in the other direction: ``useGrouping:false``, plain
positional notation (never an exponent, which is a second representation of the
same magnitude), and number + unit joined by a NO-BREAK SPACE so they are one
atom that cannot wrap apart in a narrow column. A rendering is written for a
reader, so its decimal separator is the reader's locale's (INT-385): a Turkish
reader takes a full stop as grouping, and ``12.500`` on a Turkish screen is
twelve thousand five hundred. Parsing picks no locale; rendering always names
one.

The renderer (:func:`render_quantity`, :func:`quantity_atom`, :data:`NBSP`,
:data:`DECIMAL_SEPARATORS`, :class:`QuantityLocaleUnknown`) lives in
:mod:`clinical_schemas.quantity` since INT-386 and is re-exported here as the
same objects. The typed rail, the clinician note, the patient summary and the
FHIR narrative write through it too, and the FHIR mapper's package cannot
import this one.

**No message here echoes a printed form** (invariant 6).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from decimal import Decimal
from typing import Final

from clinical_schemas.quantity import (
    DECIMAL_SEPARATORS,
    NBSP,
    QuantityLocaleUnknown,
    quantity_atom,
    render_quantity,
)

__all__ = [
    "COMPARATORS",
    "DECIMAL_SEPARATORS",
    "QuantityLocaleUnknown",
    "NBSP",
    "PrintedMagnitudeAmbiguous",
    "PrintedMagnitudeUnreadable",
    "UnitResolution",
    "magnitude_readings",
    "parse_printed_magnitude",
    "quantity_atom",
    "render_quantity",
    "resolve_unit",
]

#: Both ASCII and the typeset forms a Turkish lab report actually prints.
COMPARATORS: Final = "<>≤≥"

_DIGITS_ONLY: Final = re.compile(r"^\d+$")
_NUMERIC_SHAPE: Final = re.compile(r"^[+-]?\d[\d.,]*$")


class PrintedMagnitudeUnreadable(ValueError):
    """The printed form is not a single magnitude, so nothing is read from it.

    A range, a two-number reference cell, a comparator-qualified bound, or a
    shape this guard does not recognise. Each is a signal to stop.
    """


class PrintedMagnitudeAmbiguous(PrintedMagnitudeUnreadable):
    """A printed magnitude reads as two different numbers, so it reads as none.

    ``1.500`` is ``1500`` under Turkish grouping and ``1.5`` under an en-US
    decimal point. Both are valid readings of the same characters and the
    difference is a factor of 1000, so neither is taken.
    """


def _group_reading(head: str, tail: Sequence[str]) -> Decimal | None:
    """Read ``head`` plus three-digit groups, or ``None`` if that is not what
    the characters are."""
    if not _DIGITS_ONLY.match(head) or not 1 <= len(head) <= 3 or head.startswith("0"):
        return None
    if not all(_DIGITS_ONLY.match(part) and len(part) == 3 for part in tail):
        return None
    return Decimal(head + "".join(tail))


def _decimal_reading(head: str, fraction: str) -> Decimal | None:
    if not _DIGITS_ONLY.match(head) or not _DIGITS_ONLY.match(fraction):
        return None
    return Decimal(f"{head}.{fraction}")


def parse_printed_magnitude(printed: str) -> Decimal:
    """Resolve one printed magnitude, per value, refusing ambiguity.

    The rules, in order:

    * a comparator anywhere → a bound, not a magnitude → refused;
    * anything that is not one signed numeric token → refused (a range and a
      two-number reference cell both land here);
    * both separators present → the *last* one is the decimal point and the
      other must group cleanly;
    * one separator with exactly three digits after it → **both readings are
      valid** and they differ by a factor of 1000 → refused;
    * one separator whose integer part cannot be a group (a leading zero, or
      more than three digits) → it is a decimal point;
    * a repeated separator → grouping, and malformed grouping is refused.
    """
    readings = magnitude_readings(printed)
    if len(readings) > 1:
        raise PrintedMagnitudeAmbiguous(
            "the printed value reads as a grouped integer and as a decimal, and the "
            "two differ by a factor of 1000; neither reading is taken (CLAUDE.md "
            "invariant 22 — the printed form is not echoed here)"
        )
    return readings[0]


def magnitude_readings(printed: str) -> tuple[Decimal, ...]:
    """Every magnitude the printed characters support: one, or exactly two.

    The same rules as :func:`parse_printed_magnitude`, except that the one
    two-way form — a single separator followed by exactly three digits — is
    returned as both of its readings, decimal first, instead of being refused.
    That is what files/03 §4.9.6's *"cross-checked against the analyte's
    expected magnitude"* needs to choose between them; choosing is
    :mod:`intake_platform.records.unit_guard`'s job, never this function's.
    """
    text = printed.strip()
    if any(char in text for char in COMPARATORS):
        raise PrintedMagnitudeUnreadable(
            "the printed value carries a comparator, so it is a bound and not a "
            "magnitude; dropping the qualifier to keep the number is itself a "
            "corruption (the printed form is not echoed here — invariant 6)"
        )
    if not _NUMERIC_SHAPE.match(text):
        raise PrintedMagnitudeUnreadable(
            "the printed value is not a single magnitude; a range or a two-number "
            "reference cell is a signal to stop, not to average (files/03 §4.9.6)"
        )
    sign, body = ("-", text[1:]) if text.startswith("-") else ("", text.removeprefix("+"))

    dots, commas = body.count("."), body.count(",")

    if dots and commas:
        decimal_sep = "." if body.rfind(".") > body.rfind(",") else ","
        group_sep = "," if decimal_sep == "." else "."
        integer, _, fraction = body.rpartition(decimal_sep)
        head, *tail = integer.split(group_sep)
        grouped = _group_reading(head, tail)
        if grouped is None or not _DIGITS_ONLY.match(fraction):
            raise PrintedMagnitudeUnreadable(
                "the printed value mixes both separators in a shape that is neither "
                "grouping nor a decimal point"
            )
        return (Decimal(f"{sign}{grouped}.{fraction}"),)

    separator = "." if dots else ("," if commas else "")
    if not separator:
        return (Decimal(sign + body),)

    head, *rest = body.split(separator)
    if len(rest) > 1:
        # Two separators of the same kind cannot both be a decimal point.
        grouped = _group_reading(head, rest)
        if grouped is None:
            raise PrintedMagnitudeUnreadable(
                "the printed value repeats a separator in a shape that is not three-digit grouping"
            )
        return (Decimal(sign + str(grouped)),)

    as_decimal = _decimal_reading(head, rest[0])
    as_group = _group_reading(head, rest)
    readings = tuple(
        Decimal(sign + str(reading)) for reading in (as_decimal, as_group) if reading is not None
    )
    if not readings:
        raise PrintedMagnitudeUnreadable(
            "the printed value is not a magnitude this guard can resolve"
        )
    return readings


class UnitResolution:
    """What the ingestion unit guard concluded about one printed quantity.

    ``value`` is always the magnitude exactly as printed and ``unit`` always
    the token exactly as printed: this type has no path that converts, which
    is what *"disagreement raises a flag rather than converting silently"*
    means when it is a type rather than a habit.
    """

    __slots__ = ("_checked", "_unit", "_unit_conflict", "_value")

    def __init__(
        self, *, value: Decimal, unit: str | None, unit_conflict: bool, checked: bool
    ) -> None:
        self._value = value
        self._unit = unit
        self._unit_conflict = unit_conflict
        self._checked = checked

    @property
    def value(self) -> Decimal:
        return self._value

    @property
    def unit(self) -> str | None:
        return self._unit

    @property
    def unit_conflict(self) -> bool:
        return self._unit_conflict

    @property
    def checked(self) -> bool:
        """False when no expectation was authored for this analyte.

        Reported rather than passed: an unchecked value must not read as a
        value that was checked and agreed (HUMAN_BLOCKERS.md rule 2).
        """
        return self._checked


def resolve_unit(
    *, magnitude: Decimal, printed_unit: str | None, expected_unit: str | None
) -> UnitResolution:
    """CLAUDE.md invariant 22: *magnitude outranks the printed unit token, and
    disagreement raises a flag rather than converting silently.*

    files/03 §4.9.6 records the demonstrated case: a published 2024 university
    handbook prints adult ALT ``0 - 55 U/mL`` and AST ``5 - 34 U/mL`` when the
    values are U/L — wrong by 1000x — and another prints Total Protein and
    Albümin in ``mg/dL`` when both should be ``g/dL``. Two independent
    documents, same class of error. The magnitude in each is the trustworthy
    half, which is why nothing here rescales it.

    Comparison is byte equality after trimming, never a fold and never a
    synonym table: files/03 §4.9.6 keeps ``µ`` U+00B5 and ``μ`` U+03BC
    distinct on purpose, and a synonym table is exactly where a silent
    conversion would be reintroduced.
    """
    if expected_unit is None:
        return UnitResolution(
            value=magnitude, unit=printed_unit, unit_conflict=False, checked=False
        )
    printed = (printed_unit or "").strip()
    return UnitResolution(
        value=magnitude,
        unit=printed_unit,
        unit_conflict=printed != expected_unit.strip(),
        checked=True,
    )

"""The ingestion unit-resolution guard: one printed lab value in, one verdict out.

INT-124. CLAUDE.md invariant 22, verbatim: *"On ingestion, magnitude outranks
the printed unit token and disagreement raises a flag rather than converting
silently; ``üre`` is never substring-matched."* files/03 §4.9.6 adds the two
rules that ride with it — *"resolve the separator per value, cross-checked
against the analyte's expected magnitude"* and *"a two-number reference cell is
a signal to stop, not to average"* — and this module is those four sentences
as one deterministic function, :func:`guard_lab_value`. No model is involved.

**What a verdict is.** The magnitude **exactly as printed** (never rescaled),
the unit token **exactly as printed** (never relabelled), the unit an authored
expectation names, and a set of typed :class:`GuardFlag` values. A flag in
:data:`STOP_FLAGS` means the parse stopped and **no number came out**: a
two-number cell yields neither its mean nor either end, and a form that reads
two ways yields neither reading. There is no multiplication, division or power
anywhere in this module, :mod:`~intake_platform.records.numbers` or
:mod:`~intake_platform.records.analytes`, and a test holds that structurally:
code that cannot do arithmetic cannot convert.

**Where the expectations come from — nowhere yet.** Which unit and which
magnitude band belong to which analyte is a clinical judgement in exactly the
way a threshold is, and files/03 §4.9.6's own worked examples are two
*published* Turkish handbooks that printed the unit wrong by 1000x, so no
document can be its own authority. No committed source in this repository
supplies a table (HUMAN_BLOCKERS.md **HB-C24**, open), so
:data:`SHIPPED_EXPECTATIONS` is **empty** and the guard fails closed: every
value it sees is flagged :attr:`GuardFlag.NO_EXPECTATION`. When the table
lands, every row must carry a :class:`SourceCitation` — a row without one is
not constructible — and a table only turns some flags into clean verdicts; it
never makes a refusal wrong.

**No message here echoes what a document printed** (invariant 6), and a
verdict's ``repr`` names its flags and nothing else.
"""

from __future__ import annotations

import datetime as dt
import enum
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Final

from intake_platform.records.analytes import AnalyteAmbiguous, analyte_key
from intake_platform.records.numbers import (
    COMPARATORS,
    PrintedMagnitudeUnreadable,
    magnitude_readings,
)

__all__ = [
    "EXPECTATION_TABLE_BLOCKER",
    "SHIPPED_EXPECTATIONS",
    "STOP_FLAGS",
    "AnalyteExpectation",
    "ExpectationTable",
    "ExpectationTableInvalid",
    "GuardFlag",
    "LabValueVerdict",
    "SeparatorResolution",
    "SourceCitation",
    "guard_lab_value",
]

#: The HUMAN_BLOCKERS.md row the empty table waits on.
EXPECTATION_TABLE_BLOCKER: Final = "HB-C24"

#: One number: digits, optionally grouped or pointed. A cell with two of these
#: is two numbers, whatever sits between them.
_NUMBER_RUN: Final = re.compile(r"\d+(?:[.,]\d+)*")


class GuardFlag(enum.StrEnum):
    """Why a verdict is not a clean reading. Closed; each one is a test."""

    #: No authored expectation for this analyte (HB-C24) — fail closed.
    NO_EXPECTATION = "no_expectation"
    #: The printed unit token is not byte-equal to the expected unit.
    UNIT_CONFLICT = "unit_conflict"
    #: The printed magnitude lies outside the expected band.
    MAGNITUDE_OUTSIDE_EXPECTED = "magnitude_outside_expected"
    #: The printed form reads two ways and nothing decided between them.
    SEPARATOR_AMBIGUOUS = "separator_ambiguous"
    #: The cell holds two numbers: a range, or a mis-aligned reference column.
    TWO_NUMBER_CELL = "two_number_cell"
    #: A comparator makes the printed form a bound, not a magnitude.
    BOUND_NOT_MAGNITUDE = "bound_not_magnitude"
    #: Not a magnitude this guard recognises.
    UNREADABLE = "unreadable"
    #: The name carries ``üre``/``bun`` without resolving as a whole token sequence.
    ANALYTE_AMBIGUOUS = "analyte_ambiguous"
    #: The row printed no value at all.
    VALUE_ABSENT = "value_absent"


#: The flags after which no magnitude is read.
STOP_FLAGS: Final[frozenset[GuardFlag]] = frozenset(
    {
        GuardFlag.SEPARATOR_AMBIGUOUS,
        GuardFlag.TWO_NUMBER_CELL,
        GuardFlag.BOUND_NOT_MAGNITUDE,
        GuardFlag.UNREADABLE,
        GuardFlag.ANALYTE_AMBIGUOUS,
        GuardFlag.VALUE_ABSENT,
    }
)


class SeparatorResolution(enum.StrEnum):
    """How the magnitude's separator was decided, so a reader can tell."""

    #: The printed characters support exactly one reading.
    SINGLE_READING = "single_reading"
    #: Two readings; the authored magnitude band admitted exactly one.
    EXPECTED_MAGNITUDE = "expected_magnitude"
    #: No magnitude was read.
    STOPPED = "stopped"


class ExpectationTableInvalid(ValueError):
    """An expectation row or table that could not stand behind a check."""


def _require_text(value: str, what: str) -> None:
    if not value.strip():
        raise ExpectationTableInvalid(f"an expectation's {what} names nothing")


@dataclass(frozen=True, slots=True)
class SourceCitation:
    """Where an expectation row comes from — the red-flag rule's source shape.

    CLAUDE.md: every red-flag rule carries ``source: {guideline_id, version,
    date, url, retrieved_on}`` against a committed verbatim snapshot. An
    expected unit is the same class of clinical content, so it carries the same
    citation, and a row without one cannot be built.
    """

    guideline_id: str
    version: str
    date: dt.date
    url: str
    retrieved_on: dt.date

    def __post_init__(self) -> None:
        _require_text(self.guideline_id, "source guideline id")
        _require_text(self.version, "source version")
        if not self.url.startswith("https://"):
            raise ExpectationTableInvalid("an expectation's source url is not an https url")


@dataclass(frozen=True, slots=True)
class AnalyteExpectation:
    """What one analyte is expected to print: a unit and a magnitude band.

    ``source`` has no default: an expectation nobody can trace is a plausible
    number, which is the one thing this table may never hold.
    """

    unit: str
    magnitude_low: Decimal
    magnitude_high: Decimal
    source: SourceCitation

    def __post_init__(self) -> None:
        _require_text(self.unit, "unit")
        for bound in (self.magnitude_low, self.magnitude_high):
            if not bound.is_finite():
                raise ExpectationTableInvalid("an expectation's magnitude band is not finite")
        if self.magnitude_low > self.magnitude_high:
            raise ExpectationTableInvalid("an expectation's magnitude band is empty")

    def admits(self, magnitude: Decimal) -> bool:
        return self.magnitude_low <= magnitude <= self.magnitude_high


class ExpectationTable:
    """Analyte expectations, keyed exactly as a printed name is looked up.

    Every key goes through :func:`~intake_platform.records.analytes.analyte_key`
    — the function a printed name goes through — so ``Üre Nitrojeni`` and
    ``BUN`` are one key, a near miss such as ``Üremi`` cannot be a key at all,
    and two spellings of one analyte are a conflict rather than a silent
    overwrite.
    """

    __slots__ = ("_rows",)

    def __init__(self, rows: Mapping[str, AnalyteExpectation]) -> None:
        keyed: dict[str, AnalyteExpectation] = {}
        for index, (name, row) in enumerate(rows.items()):
            try:
                key = analyte_key(name)
            except AnalyteAmbiguous:
                raise ExpectationTableInvalid(
                    f"expectation row {index} is keyed by a name the analyte guard refuses; "
                    "a near miss on the guarded token cannot carry an expectation (the name "
                    "is not echoed here — invariant 6)"
                ) from None
            if not key:
                raise ExpectationTableInvalid(f"expectation row {index} is keyed by nothing")
            if key in keyed:
                raise ExpectationTableInvalid(
                    f"expectation row {index} resolves to analyte {key!r}, which an earlier "
                    "row already keys; two rows for one analyte would decide it twice"
                )
            keyed[key] = row
        self._rows: Mapping[str, AnalyteExpectation] = MappingProxyType(keyed)

    def get(self, key: str) -> AnalyteExpectation | None:
        return self._rows.get(key)

    def keys(self) -> tuple[str, ...]:
        return tuple(self._rows)

    def __len__(self) -> int:
        return len(self._rows)


#: The table ingestion ships with: empty, because HB-C24 is open. Every value
#: checked against it is flagged, which is the fail-closed reading of *"cross-
#: checked against the analyte's expected magnitude"* when nobody has said what
#: that magnitude is.
SHIPPED_EXPECTATIONS: Final[ExpectationTable] = ExpectationTable({})


@dataclass(frozen=True, slots=True, repr=False)
class LabValueVerdict:
    """What the guard concluded about one printed lab value.

    ``magnitude`` is the printed magnitude exactly — equal *and* with the
    printed exponent — or ``None`` when the parse stopped. ``printed_unit`` is
    the token exactly as printed. Neither is ever rescaled or relabelled; a
    disagreement is a flag in ``flags``.
    """

    analyte_key: str | None
    magnitude: Decimal | None
    printed_unit: str | None
    expected_unit: str | None
    flags: frozenset[GuardFlag]
    separator: SeparatorResolution

    @property
    def stopped(self) -> bool:
        return self.magnitude is None

    @property
    def flagged(self) -> bool:
        return bool(self.flags)

    def __repr__(self) -> str:
        flags = sorted(flag.value for flag in self.flags)
        return f"LabValueVerdict(flags={flags}, separator={self.separator.value!r})"

    def __str__(self) -> str:
        return self.__repr__()


def _read_magnitude(
    printed: str, expectation: AnalyteExpectation | None
) -> tuple[Decimal | None, SeparatorResolution, frozenset[GuardFlag]]:
    """The magnitude, how its separator was decided, and any stop flag."""
    stops: set[GuardFlag] = set()
    if any(char in printed for char in COMPARATORS):
        stops.add(GuardFlag.BOUND_NOT_MAGNITUDE)
    if len(_NUMBER_RUN.findall(printed)) > 1:
        stops.add(GuardFlag.TWO_NUMBER_CELL)
    if stops:
        return None, SeparatorResolution.STOPPED, frozenset(stops)
    try:
        readings = magnitude_readings(printed)
    except PrintedMagnitudeUnreadable:
        return None, SeparatorResolution.STOPPED, frozenset({GuardFlag.UNREADABLE})
    if len(readings) == 1:
        return readings[0], SeparatorResolution.SINGLE_READING, frozenset()
    admitted = [] if expectation is None else [r for r in readings if expectation.admits(r)]
    if len(admitted) == 1:
        return admitted[0], SeparatorResolution.EXPECTED_MAGNITUDE, frozenset()
    return None, SeparatorResolution.STOPPED, frozenset({GuardFlag.SEPARATOR_AMBIGUOUS})


def guard_lab_value(
    *,
    printed_name: str,
    printed_value: str | None,
    printed_unit: str | None,
    table: ExpectationTable,
) -> LabValueVerdict:
    """Apply invariant 22 to one printed lab value. Deterministic; never raises.

    1. The analyte is keyed by its whole token sequence; a near miss on
       ``üre``/``bun`` stops everything (:attr:`GuardFlag.ANALYTE_AMBIGUOUS`).
    2. The magnitude is read **per value**. A comparator, a second number or
       an unrecognised shape stops the parse. A form that reads two ways is
       decided by the expected magnitude band when exactly one reading lies in
       it, and stops otherwise. The printed unit token takes no part in this.
    3. The unit token is compared to the expected unit by byte equality after
       trimming — no fold, no synonym table (``µ`` U+00B5 is not ``μ``
       U+03BC). A difference is :attr:`GuardFlag.UNIT_CONFLICT`; the magnitude
       stays what was printed, because it is the trustworthy half.
    4. A read magnitude outside the band is
       :attr:`GuardFlag.MAGNITUDE_OUTSIDE_EXPECTED`, still unconverted.
    """
    try:
        key = analyte_key(printed_name)
    except AnalyteAmbiguous:
        return LabValueVerdict(
            analyte_key=None,
            magnitude=None,
            printed_unit=printed_unit,
            expected_unit=None,
            flags=frozenset({GuardFlag.ANALYTE_AMBIGUOUS}),
            separator=SeparatorResolution.STOPPED,
        )

    expectation = table.get(key)
    flags: set[GuardFlag] = set()
    if expectation is None:
        flags.add(GuardFlag.NO_EXPECTATION)

    if printed_value is None:
        magnitude: Decimal | None = None
        separator = SeparatorResolution.STOPPED
        flags.add(GuardFlag.VALUE_ABSENT)
    else:
        magnitude, separator, stops = _read_magnitude(printed_value.strip(), expectation)
        flags |= stops

    if expectation is not None:
        if (printed_unit or "").strip() != expectation.unit.strip():
            flags.add(GuardFlag.UNIT_CONFLICT)
        if magnitude is not None and not expectation.admits(magnitude):
            flags.add(GuardFlag.MAGNITUDE_OUTSIDE_EXPECTED)

    return LabValueVerdict(
        analyte_key=key,
        magnitude=magnitude,
        printed_unit=printed_unit,
        expected_unit=None if expectation is None else expectation.unit,
        flags=frozenset(flags),
        separator=separator,
    )

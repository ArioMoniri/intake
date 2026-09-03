"""A printed Turkish date is a numeral, and it crosses a boundary (INT-122).

CLAUDE.md invariant 22 — *"Numbers never cross a representation boundary
unguarded"* — is usually read as being about lab magnitudes. On the records
path the other numeral is the **date**, and it fails in the same shape:
``03.04.2026`` is 3 April under Turkish ``gg.aa.yyyy`` and 4 March under
``mm.dd.yyyy``, the two readings are a month apart, and **there is no diff
that makes the wrong one look wrong**. A patient sent to the hospital on the
wrong day finds out at the door.

So this module is :mod:`intake_platform.records.numbers` for temporal values,
and it obeys the same three rules:

* **resolve per value, never per document** — nothing here picks a locale and
  applies it to everything that follows;
* **a form that reads two ways is refused**, because a value that reads two
  ways reads as none. ``13.09.2026`` has exactly one valid reading (13 is not
  a month) and is taken; ``03.04.2026`` has two and is not;
* **a missing century is not inferred.** ``03.09.26`` is refused rather than
  read as 2026 — the twentieth century is as available to that string as the
  twenty-first, and no committed source in this repository says otherwise.

``order`` is the seam for the day a human states the format a source prints.
No committed source in this repository states the order an MHRS SMS uses, so
:mod:`intake_platform.records.mhrs` passes nothing and the ambiguous form
stays refused. A default here would be one engineer choosing once, for every
future patient, exactly what HUMAN_BLOCKERS.md rule 1 forbids.

Scanning a message adds one rule of its own: **more than one distinct date in
the text refuses the read**. A booking confirmation plausibly prints both the
date it was booked and the date of the appointment, and picking between them
without knowing the message's shape is the wrong-day error with extra steps.

**No message here echoes what was printed** (invariant 6).
"""

from __future__ import annotations

import datetime as dt
import enum
import re
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from intake_platform.records.analytes import fold_tr

__all__ = [
    "TURKISH_MONTHS",
    "DateOrder",
    "PrintedDateAmbiguous",
    "PrintedDateNotFound",
    "PrintedDateTimeUnreadable",
    "PrintedDateUnreadable",
    "PrintedTimeAmbiguous",
    "PrintedTimeNotFound",
    "PrintedTimeUnreadable",
    "find_printed_date",
    "find_printed_time",
    "parse_printed_date",
    "parse_printed_time",
]


class PrintedDateTimeUnreadable(ValueError):
    """A printed temporal value this guard will not resolve.

    Every subclass is a *stop*, never a fallback: the field is left unset and
    named, so the omission is visible to whoever confirms it.
    """


class PrintedDateUnreadable(PrintedDateTimeUnreadable):
    """The characters are not a date this guard can resolve."""


class PrintedDateAmbiguous(PrintedDateUnreadable):
    """The printed date reads as two different days, so it reads as none."""


class PrintedDateNotFound(PrintedDateUnreadable):
    """No date-shaped token is present at all — a different thing from an
    ambiguity, and reported as one."""


class PrintedTimeUnreadable(PrintedDateTimeUnreadable):
    """The characters are not a wall-clock time this guard can resolve."""


class PrintedTimeAmbiguous(PrintedTimeUnreadable):
    """Two different times are printed, so neither is the appointment."""


class PrintedTimeNotFound(PrintedTimeUnreadable):
    """No time-shaped token is present at all."""


class DateOrder(enum.StrEnum):
    """The reading order a *human* has stated for a source.

    There is deliberately no ``DEFAULT`` and no ``TURKISH`` member: a default
    is the choice this module exists to refuse.
    """

    DAY_FIRST = "day_first"
    MONTH_FIRST = "month_first"


#: The twelve Turkish month names, folded. This is calendar vocabulary, not
#: clinical content and not authored patient copy — it is read *from* what a
#: document printed, exactly as INT-121 reads a printed analyte name, so no
#: ``tr`` resource key is created (invariant 5 untouched).
TURKISH_MONTHS: Final[Mapping[str, int]] = MappingProxyType(
    {
        "ocak": 1,
        "şubat": 2,
        "mart": 3,
        "nisan": 4,
        "mayıs": 5,
        "haziran": 6,
        "temmuz": 7,
        "ağustos": 8,
        "eylül": 9,
        "ekim": 10,
        "kasım": 11,
        "aralık": 12,
    }
)

_NUMERIC_DATE: Final = re.compile(r"(\d{1,4})([./-])(\d{1,2})\2(\d{1,4})")
_NAMED_DATE: Final = re.compile(r"(\d{1,2})\s+([^\W\d_]+)\s+(\d{4})")
_CLOCK: Final = re.compile(r"(\d{1,2}):(\d{2})")

_NUMERIC_DATE_SCAN: Final = re.compile(rf"(?<![\d./-]){_NUMERIC_DATE.pattern}(?![\d./-])")
_NAMED_DATE_SCAN: Final = re.compile(rf"(?<!\w){_NAMED_DATE.pattern}(?!\w)")
_CLOCK_SCAN: Final = re.compile(rf"(?<![\d:]){_CLOCK.pattern}(?![\d:])")


def _as_date(year: int, month: int, day: int) -> dt.date | None:
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None


def _named(text: str) -> dt.date | None:
    """``3 Eylül 2026`` — a month *name* cannot be read as a day, so this form
    is unambiguous by construction and needs no order."""
    match = _NAMED_DATE.fullmatch(text)
    if match is None:
        return None
    month = TURKISH_MONTHS.get(fold_tr(match.group(2)))
    if month is None:
        return None
    return _as_date(int(match.group(3)), month, int(match.group(1)))


def parse_printed_date(printed: str, *, order: DateOrder | None = None) -> dt.date:
    """Resolve one printed date, refusing every form that reads two ways.

    ``order`` is supplied only where a human has stated the format the source
    prints; with no order, a form whose two readings are both valid days is
    :class:`PrintedDateAmbiguous`.
    """
    text = printed.strip()
    named = _named(text)
    if named is not None:
        return named
    match = _NUMERIC_DATE.fullmatch(text)
    if match is None:
        raise PrintedDateUnreadable(
            "the printed value is not a date this guard resolves; it is left unset "
            "rather than repaired (the printed form is not echoed here — invariant 6)"
        )
    first, middle, last = match.group(1), match.group(3), match.group(4)
    if len(first) == 4 and len(last) == 4:
        raise PrintedDateUnreadable("the printed date carries two four-digit components")
    if len(first) == 4:
        # A four-digit leading component is a year, and a year-first date is
        # year-month-day in every notation that writes one.
        resolved = _as_date(int(first), int(middle), int(last))
        if resolved is None:
            raise PrintedDateUnreadable("the printed year-first date names no real day")
        return resolved
    if len(last) != 4:
        raise PrintedDateUnreadable(
            "the printed date carries no four-digit year, and the century is not "
            "inferred — 26 is as much 1926 as 2026"
        )
    year, a, b = int(last), int(first), int(middle)
    day_first = _as_date(year, b, a)
    month_first = _as_date(year, a, b)
    if order is DateOrder.DAY_FIRST:
        readings = [day_first]
    elif order is DateOrder.MONTH_FIRST:
        readings = [month_first]
    else:
        readings = [reading for reading in (day_first, month_first) if reading is not None]
    valid = [reading for reading in readings if reading is not None]
    if not valid:
        raise PrintedDateUnreadable("the printed date names no real day in any reading")
    if len(set(valid)) > 1:
        raise PrintedDateAmbiguous(
            "the printed date reads as two different days — day-first and month-first "
            "are both real days and they are a month apart — so neither reading is "
            "taken (CLAUDE.md invariant 22; no order has been stated for this source)"
        )
    return valid[0]


def parse_printed_time(printed: str) -> dt.time:
    """Resolve one printed wall-clock time, 24-hour and minute-precise.

    A twelve-hour form with a meridiem, a seconds field or an out-of-range
    component is refused: an appointment time is one of a very small set of
    shapes, and anything else is more likely to be a different number.
    """
    match = _CLOCK.fullmatch(printed.strip())
    if match is None:
        raise PrintedTimeUnreadable(
            "the printed value is not a 24-hour wall-clock time; it is left unset"
        )
    hour, minute = int(match.group(1)), int(match.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise PrintedTimeUnreadable("the printed time names no real minute of a day")
    return dt.time(hour, minute)


def find_printed_date(text: str, *, order: DateOrder | None = None) -> dt.date:
    """The one date a message states, or a refusal.

    A date-shaped token this guard cannot read refuses the whole scan rather
    than being skipped: the unreadable token may be the appointment, and
    reading past it to a different one is exactly the wrong-day error.
    """
    found: set[dt.date] = set()
    for match in _NAMED_DATE_SCAN.finditer(text):
        if fold_tr(match.group(2)) in TURKISH_MONTHS:
            found.add(parse_printed_date(match.group(0), order=order))
    for match in _NUMERIC_DATE_SCAN.finditer(text):
        found.add(parse_printed_date(match.group(0), order=order))
    if not found:
        raise PrintedDateNotFound("no date-shaped token is present")
    if len(found) > 1:
        raise PrintedDateAmbiguous(
            "the text states more than one distinct date, and choosing between them "
            "without knowing the message's shape is the wrong-day error"
        )
    return found.pop()


def find_printed_time(text: str) -> dt.time:
    """The one wall-clock time a message states, or a refusal."""
    found = {parse_printed_time(match.group(0)) for match in _CLOCK_SCAN.finditer(text)}
    if not found:
        raise PrintedTimeNotFound("no time-shaped token is present")
    if len(found) > 1:
        raise PrintedTimeAmbiguous("the text states more than one distinct time")
    return found.pop()

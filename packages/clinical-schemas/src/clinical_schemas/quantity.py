"""How a clinical quantity is written as text, for the one reader it is for.

CLAUDE.md invariant 22: *"Numbers never cross a representation boundary
unguarded. … `useGrouping:false` for every clinical quantity; number + unit is
one non-breaking atom."*

This is INT-385's renderer. INT-386 moved it here, below every surface that
writes a quantity as text: the records confirm card and the note's
``imported_objective`` line (:mod:`intake_platform.records`, which re-exports
these objects), the typed profile's numeric rail, the clinician note, the
patient summary, and the FHIR document's narrative
(:mod:`clinical_schemas.mappers.document`). ``clinical-schemas`` depends on
pydantic alone and ``intake_platform`` depends on it, so this is the one layer
all of them can import without a cycle. Before INT-386 the four text renderers
each kept a private copy that wrote ``Decimal``'s own ``str()``, with a full
stop, for a Turkish reader.

A rendering is written for a reader, so its decimal separator is the reader's
locale's: a Turkish reader takes a full stop as grouping (files/03 §4.9.6),
and ``12.500`` on a Turkish screen is twelve thousand five hundred. Rendering
always names a locale, and there is no default.

**This is for the screen and the document only.** No numeral reaches a TTS
model: the protocol compiler expands every number to Turkish orthography
before any speech model sees it, and ``talker.speech`` refuses a digit on the
way out. Nothing on that path imports this module
(tests/records/test_quantity_render.py). It imports only the standard library
and holds no arithmetic, so it cannot rescale a magnitude.

**No message here echoes what it was given** (invariant 6).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from decimal import Decimal
from types import MappingProxyType
from typing import Final

__all__ = [
    "DECIMAL_SEPARATORS",
    "NBSP",
    "QuantityLocaleUnknown",
    "float_magnitude",
    "quantity_atom",
    "render_quantity",
]

#: NO-BREAK SPACE. CLAUDE.md invariant 22: *"number + unit is one non-breaking
#: atom"*. A dose or a lab value wrapped across a line break at the space is a
#: reading error waiting to happen, and it is invisible until the column is
#: narrow enough.
NBSP: Final = " "

#: The decimal point a reader of each display locale reads (INT-385). A
#: Turkish reader reads a comma as the point and a full stop as grouping
#: (files/03 §4.9.6), so a full stop written for a Turkish reader moves the
#: magnitude by a factor of 1000. The table is closed and read-only. A locale
#: missing from it is refused and never written with a guessed separator.
DECIMAL_SEPARATORS: Final[Mapping[str, str]] = MappingProxyType({"tr": ",", "en": "."})


class QuantityLocaleUnknown(ValueError):
    """A quantity was asked for in a locale with no recorded decimal point.

    Writing it with a guessed separator is how a value read as 12.5 reaches a
    Turkish reader as ``12.500`` (INT-385), so nothing is written. The message
    does not echo the locale it was given: a caller can pass any string.
    """


def render_quantity(magnitude: Decimal, *, locale: str) -> str:
    """One rendering of a clinical quantity, for a reader of ``locale``.

    * The decimal point is the locale's (:data:`DECIMAL_SEPARATORS`: ``tr``
      comma, ``en`` full stop). INT-121 wrote a full stop for every reader
      (INT-385).
    * No grouping, ever (``useGrouping:false``): 12500 is ``12500`` in every
      locale, never ``12.500`` or ``12,500``.
    * No exponent. ``Decimal.__str__`` switches to scientific notation for some
      exponents, and an exponent beside a unit is a second representation of
      the magnitude in the same string. ``f"{...:f}"`` is plain positional
      notation always, and it keeps the printed precision (``2.50`` is
      ``2,50`` in ``tr``).

    ``locale`` has no default. The reader is the caller's to name, and a
    locale with no recorded separator raises :class:`QuantityLocaleUnknown`.
    """
    separator = DECIMAL_SEPARATORS.get(locale)
    if separator is None:
        raise QuantityLocaleUnknown(
            "no decimal point is recorded for the requested locale (known: "
            f"{', '.join(sorted(DECIMAL_SEPARATORS))}); a guessed separator is how 12.5 "
            "reaches a Turkish reader as 12.500, so the quantity is not written "
            "(the requested locale is not echoed here)"
        )
    # Positional notation writes a full stop and never a comma, so this one
    # substitution is the whole of the locale's effect on the number.
    return f"{magnitude:f}".replace(".", separator)


def quantity_atom(magnitude: Decimal, unit: str | None, *, locale: str) -> str:
    """Number and unit as one non-breaking atom (invariant 22), for a reader of
    ``locale`` (:func:`render_quantity`)."""
    rendered = render_quantity(magnitude, locale=locale)
    if unit is None or not unit.strip():
        return rendered
    return f"{rendered}{NBSP}{unit.strip()}"


def float_magnitude(value: float) -> Decimal:
    """The magnitude a ``float`` field holds, as the digits Python prints for it.

    The speech measures of files/04 §5 ``konusma_ozellikleri`` are floats.
    ``Decimal(4.1)`` is the float's binary expansion,
    ``4.0999999999999996447286321199499070644378662109375``, which is not the
    number anybody measured or would read. ``repr`` is the shortest string
    that reads back as the same float, so ``4.1`` stays ``4.1`` and the text
    changes only by the reader's decimal point.

    A NaN or an infinity is not a quantity, so it is refused. The message does
    not echo the value (invariant 6).
    """
    if not math.isfinite(value):
        raise ValueError("a clinical quantity must be a finite number; the value is not written")
    return Decimal(repr(value))

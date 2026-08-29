"""Invariant 47 — `export_injection_guard` (files/10 §9; files/08 §0c F13).

One guard, shared. The DSAR export (INT-037) and the SDS-01 style wait-time
export (INT-241) both hand a spreadsheet a file whose content someone else
wrote, and a second copy of this function is a second copy that can drift —
so it lives here and both callers import it. ``intake_api.dsar.export``
re-exports the name it has always exported, unchanged.

The rule: control characters and CRLF collapse to spaces, and a value leading
with ``= + - @`` (or a tab or carriage return, which some importers treat the
same way) is prefixed with an apostrophe per OWASP. **The guard neutralises;
it never deletes** — an export that quietly drops what was written is a worse
answer than one with a visible apostrophe.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

__all__ = ["FORMULA_LEADS", "sanitise_cell", "sanitise_cells"]

#: Characters a spreadsheet treats as the start of a formula (OWASP).
FORMULA_LEADS: Final = ("=", "+", "-", "@", "\t", "\r")


def sanitise_cell(value: str) -> str:
    """Neutralise a value so opening the export cannot execute it, without
    changing what it says."""
    flattened = "".join(" " if (ord(char) < 0x20 or ord(char) == 0x7F) else char for char in value)
    collapsed = " ".join(flattened.split())
    if collapsed.startswith(FORMULA_LEADS):
        return "'" + collapsed
    return collapsed


def sanitise_cells(values: Iterable[object]) -> tuple[str, ...]:
    """The row form: stringify, then neutralise every cell."""
    return tuple(sanitise_cell(str(value)) for value in values)

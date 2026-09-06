"""Shared descriptive cells for the track notebooks (INT-231).

Every track begins the same way: describe the blinded cohort by its blind
condition codes. These cells read only a :class:`BlindedExtract` — never a real
arm label, never a transcript or a note — and emit COUNTS of a named cohort,
which are measurements and never properties of the product (invariant 20). They
are deterministic: their output depends only on the extract handed in.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _condition_axis(context: Mapping[str, Any]) -> str:
    """The blinded arm axis to describe by. A blinded extract records which
    dimension was masked; the first one is the condition axis."""
    extract = context["extract"]
    if not extract.blinded_dimensions:
        raise ValueError("the extract declares no blinded dimension to describe by")
    axis: str = extract.blinded_dimensions[0]
    return axis


def sessions_per_condition(context: Mapping[str, Any]) -> dict[str, int]:
    """Total ``sessions`` per blind condition code, sorted by code."""
    extract = context["extract"]
    axis = _condition_axis(context)
    totals: dict[str, int] = {}
    for row in extract.rows:
        code = row.dimensions[axis]
        totals[code] = totals.get(code, 0) + int(row.measures.get("sessions", 0))
    return dict(sorted(totals.items()))


def subjects_per_condition(context: Mapping[str, Any]) -> dict[str, int]:
    """Row (subject) count per blind condition code, sorted by code."""
    extract = context["extract"]
    axis = _condition_axis(context)
    counts: dict[str, int] = {}
    for row in extract.rows:
        code = row.dimensions[axis]
        counts[code] = counts.get(code, 0) + 1
    return dict(sorted(counts.items()))


def conditions_present(context: Mapping[str, Any]) -> list[str]:
    """The sorted set of blind condition codes present — the analyst sees how
    many arms there are, never which is which."""
    extract = context["extract"]
    axis = _condition_axis(context)
    return sorted({row.dimensions[axis] for row in extract.rows})

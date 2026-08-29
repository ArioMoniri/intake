"""INT-241 — the SDS-01 style wait-time export.

files/01 §4 and files/03 §19 record why this exists: the Ministry of Health's
facility evaluation standards (Sağlık Tesisleri Değerlendirme Standartları,
SDS-01, *poliklinik etkinliği*) already make Turkish hospitals analyse
appointment and wait figures, and files/08 §3 says the *Experience &
satisfaction* module mirrors that language for hospital tenants. This module
is the serialiser behind that export.

**Every row is a measurement of a named cohort over a stated window
(invariant 20).** The window bounds and the measurement instant are columns,
not a caption, because a caption gets dropped when someone pastes two rows
into a slide. Nothing here is a property of the product, nothing is a target,
and no row is labelled good or bad — the table reports what was measured and
says so.

**Three things this table deliberately does not have.**

- *A clinic or branch dimension.* files/08 §0c F9 names branch-level slicing
  of an operational aggregate, filtered to one small clinic on one day, as the
  thing that identifies individuals. SDS-01's own analysis is branch-level, so
  this is a real gap rather than an oversight: the observation carries no
  branch (the visit's branch lives in an encrypted slot, not a column), and
  adding one is a data-inventory decision under invariant 18, not something to
  slip into an export. Stated in docs/evidence/INT-241.md.
- *A suppressed row's figures.* A cohort below the floor keeps its ``n`` and
  loses everything else; the ``status`` column says which.
- *An omitted row.* A metric with no data still appears, because a missing row
  reads as "no wait" and the truth is "no measurement". ``status`` separates
  ``source_unavailable`` (this repo does not record one of the two instants)
  from ``no_observations`` (it does, and nobody waited in this window).

Cells run through the one committed injection guard,
``intake_platform.export_safety.sanitise_cell`` (invariant 47; files/08 §0c
F13) — the compliance officer opening this in Excel is the exact scenario that
finding describes.
"""

from __future__ import annotations

import io
from collections.abc import Mapping, Sequence

from clinical_schemas.events import WaitKind
from intake_platform.export_safety import sanitise_cell
from intake_platform.wait_times import WAIT_SOURCES, WaitSource

from intake_metrics.wait_rollups import MIN_COHORT, WaitRollup

__all__ = ["SDS01_COLUMNS", "sds01_csv", "sds01_table"]

#: The column set, pinned by test. Deliberately without a clinic, branch,
#: clinician or patient column — see the module docstring.
SDS01_COLUMNS: tuple[str, ...] = (
    "metric_id",
    "unit",
    "window_start",
    "window_end",
    "measured_at",
    "n",
    "mean",
    "status",
    "note",
)

_PUBLISHED = "published"
_SUPPRESSED = "suppressed_below_k"
_NO_OBSERVATIONS = "no_observations"
_SOURCE_UNAVAILABLE = "source_unavailable"


def _status(rollup: WaitRollup, source: WaitSource) -> str:
    if not source.observable:
        return _SOURCE_UNAVAILABLE
    if rollup.n == 0:
        return _NO_OBSERVATIONS
    if rollup.suppressed:
        return _SUPPRESSED
    return _PUBLISHED


def _note(status: str, source: WaitSource) -> str:
    if status == _SOURCE_UNAVAILABLE:
        blocker = f" (blocked by {source.blocked_by})" if source.blocked_by else ""
        return f"{source.missing_instant}{blocker}"
    if status == _SUPPRESSED:
        return f"cohort below the k >= {MIN_COHORT} floor; figures withheld"
    if status == _NO_OBSERVATIONS:
        return "no observation fell in this window"
    return ""


def _mean_cell(rollup: WaitRollup, source: WaitSource) -> str:
    """The mean in the metric's own unit, or empty when nothing may be shown.

    Observations are milliseconds; group G states the unit per id, so the
    conversion is the catalogue's, not a choice made here.
    """
    if rollup.mean_ms is None:
        return ""
    divisor = {"s": 1_000.0, "min": 60_000.0, "h": 3_600_000.0}[source.unit]
    return f"{rollup.mean_ms / divisor:.3f}"


def sds01_table(
    rollups: Sequence[WaitRollup], *, sources: Sequence[WaitSource] = WAIT_SOURCES
) -> list[list[str]]:
    """Header row plus one row per rollup, every cell neutralised."""
    by_kind: Mapping[WaitKind, WaitSource] = {source.kind: source for source in sources}
    table = [list(SDS01_COLUMNS)]
    for rollup in rollups:
        source = by_kind[rollup.kind]
        status = _status(rollup, source)
        table.append(
            [
                sanitise_cell(str(value))
                for value in (
                    source.metric_id,
                    source.unit,
                    rollup.cohort.window_start.isoformat(),
                    rollup.cohort.window_end.isoformat(),
                    rollup.measured_at.isoformat(),
                    rollup.n,
                    _mean_cell(rollup, source),
                    status,
                    _note(status, source),
                )
            ]
        )
    return table


def sds01_csv(
    rollups: Sequence[WaitRollup], *, sources: Sequence[WaitSource] = WAIT_SOURCES
) -> str:
    """RFC 4180 CSV over :func:`sds01_table`.

    ``csv.writer`` quotes; :func:`sanitise_cell` neutralises. Both are needed
    and neither substitutes for the other — quoting stops a comma breaking the
    row, and only the apostrophe stops Excel evaluating the cell.
    """
    import csv

    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerows(sds01_table(rollups, sources=sources))
    return buffer.getvalue()

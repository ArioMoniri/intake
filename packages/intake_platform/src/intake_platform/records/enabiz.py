"""The patient-exported Turkish lab report, read from its printed shape (INT-122).

**What this parses, and what it deliberately does not claim to recognise.**
files/03 §10 states the shape to expect — *"the mandated six-column *Akılcı
Laboratuvar* shape (``Tetkik Adı ∣ Sonuç ∣ Durum ∣ Birim ∣ Referans Aralığı ∣
Önceki Sonuçlar``) in any post-2018 Turkish report"* — and that is what this
module reads. It does **not** claim to detect e-Nabız *branding*:
HUMAN_BLOCKERS.md **HB-A1** records that nobody on this project has seen an
e-Nabız export (an e-Devlet citizen login is the only way to), so a header
signature would be invented, and that row names *"INT-122's acceptance"* as
what it blocks. A parser that reads a shape a committed source states is
honest; one that claims a provenance it has never seen is not.

**It does not open a PDF, and that is not an omission to fix here.** HB-A1
also records that whether the e-Nabız PDF has a text layer at all is
UNVERIFIED, with the standing instruction *"Do not assume a text layer"*. The
input is therefore :class:`~intake_platform.records.document.TextRegion` —
whatever produced it, a text layer or an OCR — so the unverified question
changes which seam fills the regions and changes nothing here. Both seams are
fail-closed today (``NoLayout``, ``NoOcr``) behind the open engine-and-sandbox
ADR (files/10 §4), and :func:`~intake_platform.records.document.read_document_regions`
already refuses an empty one.

**It feeds INT-121 rather than replacing it.** The output is the same
closed-key-set completion :func:`~intake_platform.records.extraction.extract_record_items`
already consumes, carrying ``printed_value`` and ``printed_unit`` **exactly as
printed**. Nothing here resolves a separator, normalises a unit or touches an
analyte name: a parser that helpfully normalises a unit before the invariant-22
guard sees it defeats the guard, and this one has no path that could.

**Three of the six columns are read and dropped, each for its own reason.**
``Durum`` is an abnormality flag, and a document is not a rules engine
(invariant 1); ``Referans Aralığı`` is the two-number cell files/03 §4.9.6
calls *"a signal to stop, not to average"*; ``Önceki Sonuçlar`` is a
**different observation with a different date**, and folding it into this row
would be a value attributed to the wrong day. They are still located, because
locating them is what keeps the columns aligned.

**Columns are decided by geometry, never by position in the row.** A row
missing one cell shifts every later cell one column left under an ordinal
read, so the reference range becomes the unit and the status flag becomes the
value — a wrong unit on a lab number, silently. Each cell is assigned to the
column whose header it horizontally overlaps, and a cell that overlaps two, or
none, makes the **row** unreadable rather than guessed. An unread row is
reported by ordinal, so the gap is visible without any of it being echoed
(invariant 6).

**The document is data, never instructions** (invariant 14). The whole text
layer crosses the one fence :mod:`intake_platform.data_boundary` owns — the
control INT-083 built and INT-121 moved down, not a third copy — before any
of it is read, and a document carrying the control token is refused whole.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from clinical_schemas.records import RecordItemKind

from intake_platform.records.analytes import fold_tr
from intake_platform.records.document import FencedDocument, TextRegion, fence_document_regions

__all__ = [
    "CARRIED_COLUMNS",
    "DROPPED_COLUMNS",
    "LAB_TABLE_COLUMNS",
    "LabTableParse",
    "LabTableShapeUnrecognised",
    "parse_lab_table",
]

#: The mandated six columns, verbatim from files/03 §10. Transcription, not
#: authorship: nothing is added, and the order is the order that file states.
LAB_TABLE_COLUMNS: Final[tuple[str, ...]] = (
    "Tetkik Adı",
    "Sonuç",
    "Durum",
    "Birim",
    "Referans Aralığı",
    "Önceki Sonuçlar",
)

#: The three a row is allowed to carry forward. ``Birim`` travels as printed —
#: files/03 §10: *"``Birim`` is a named, mandated column whose contents nothing
#: constrains"*, so expect free text inside it and let the guard decide.
CARRIED_COLUMNS: Final[tuple[str, ...]] = ("Tetkik Adı", "Sonuç", "Birim")

#: Located so the columns stay aligned, then dropped. See the module docstring
#: for the reason each one is not a field of an extracted item.
DROPPED_COLUMNS: Final[tuple[str, ...]] = ("Durum", "Referans Aralığı", "Önceki Sonuçlar")

_REQUIRED_CELLS: Final[tuple[str, ...]] = ("Tetkik Adı", "Sonuç")

_FOLDED_COLUMNS: Final[Mapping[str, str]] = {
    " ".join(fold_tr(column).split()): column for column in LAB_TABLE_COLUMNS
}


class LabTableShapeUnrecognised(ValueError):
    """No page of the document carries the mandated six-column header.

    Refused rather than returned empty: *"this document contains no labs"* is
    a clinical statement and this parser is not entitled to make it. The
    message names nothing the document printed (invariant 6).
    """


@dataclass(frozen=True, slots=True)
class LabTableParse:
    """What one lab-table pass produced.

    ``completion`` is the schema-constrained result INT-121's parser consumes;
    ``regions`` is one derived region per **read row**, and each item's
    ``region`` indexes into it, so the box a patient taps covers the whole
    printed row rather than one cell of it. ``rows_unread`` names the ordinals
    the geometry could not resolve — never their content. ``fenced`` is the
    whole text layer as data, which is the only form in which any of it may
    reach a model (the rows this parser could not read are INT-124's problem,
    and they must arrive fenced).
    """

    completion: Mapping[str, Any]
    regions: tuple[TextRegion, ...]
    rows_unread: tuple[int, ...]
    fenced: FencedDocument


def _normalise(text: str) -> str:
    return " ".join(fold_tr(text).split())


def _rows(regions: Sequence[TextRegion]) -> list[list[TextRegion]]:
    """Group cells into printed rows by page and vertical overlap.

    Two cells share a row when their vertical extents overlap — which is what
    a row *is* on a rendered page, and needs no tuned tolerance.
    """
    rows: list[list[TextRegion]] = []
    page = -1
    limit = 0.0
    for region in sorted(regions, key=lambda region: (region.page, region.bbox[1], region.bbox[0])):
        top, bottom = region.bbox[1], region.bbox[3]
        if rows and region.page == page and top < limit:
            rows[-1].append(region)
            limit = max(limit, bottom)
        else:
            rows.append([region])
            page, limit = region.page, bottom
    return [sorted(row, key=lambda region: region.bbox[0]) for row in rows]


def _header_columns(row: Sequence[TextRegion]) -> dict[str, tuple[float, float]] | None:
    """The header's own x-range per column, or ``None`` if this is not it."""
    columns: dict[str, tuple[float, float]] = {}
    for cell in row:
        column = _FOLDED_COLUMNS.get(_normalise(cell.text))
        if column is None or column in columns:
            return None
        columns[column] = (cell.bbox[0], cell.bbox[2])
    return columns if len(columns) == len(LAB_TABLE_COLUMNS) else None


def _assign(
    row: Sequence[TextRegion], columns: Mapping[str, tuple[float, float]]
) -> dict[str, str] | None:
    """One cell to one column by horizontal overlap, or ``None`` for the row.

    Zero columns, two columns, or two cells in one column each make the row
    unreadable. There is no nearest-column fallback: the nearest column is
    where a wrong unit comes from.
    """
    assigned: dict[str, str] = {}
    for cell in row:
        left, right = cell.bbox[0], cell.bbox[2]
        hits = [
            column
            for column, (header_left, header_right) in columns.items()
            if min(right, header_right) > max(left, header_left)
        ]
        if len(hits) != 1 or hits[0] in assigned:
            return None
        assigned[hits[0]] = cell.text
    return assigned


def _row_region(row: Sequence[TextRegion]) -> TextRegion:
    """One derived region covering the printed row, for the source box."""
    return TextRegion(
        page=row[0].page,
        bbox=(
            min(cell.bbox[0] for cell in row),
            min(cell.bbox[1] for cell in row),
            max(cell.bbox[2] for cell in row),
            max(cell.bbox[3] for cell in row),
        ),
        start=min(cell.start for cell in row),
        end=max(cell.end for cell in row),
        text=" ".join(cell.text for cell in row),
    )


def parse_lab_table(regions: Sequence[TextRegion]) -> LabTableParse:
    """Read the mandated six-column lab table out of a parsed document.

    Raises :class:`~intake_platform.records.document.DocumentBoundaryEscape`
    for a document with no text layer or one carrying the data-block control
    token, and :class:`LabTableShapeUnrecognised` when no page carries the
    header. Everything it *can* read comes back as printed; everything it
    cannot is an ordinal in ``rows_unread``.
    """
    fenced = fence_document_regions(regions)

    items: list[dict[str, Any]] = []
    row_regions: list[TextRegion] = []
    unread: list[int] = []
    columns: dict[str, tuple[float, float]] | None = None
    header_seen = False
    page = -1
    ordinal = 0

    for row in _rows(regions):
        if row[0].page != page:
            page, columns = row[0].page, None
        header = _header_columns(row)
        if header is not None:
            columns, header_seen = header, True
            continue
        index, ordinal = ordinal, ordinal + 1
        cells = _assign(row, columns) if columns is not None else None
        if cells is None or any(not cells.get(name, "").strip() for name in _REQUIRED_CELLS):
            unread.append(index)
            continue
        unit = (cells.get("Birim") or "").strip()
        items.append(
            {
                "kind": RecordItemKind.LAB.value,
                "printed_name": cells["Tetkik Adı"],
                "printed_value": cells["Sonuç"],
                "printed_unit": unit or None,
                "region": len(row_regions),
            }
        )
        row_regions.append(_row_region(row))

    if not header_seen:
        raise LabTableShapeUnrecognised(
            "no page of this document carries the mandated six-column header "
            "(files/03 §10), so it is refused whole rather than reported as a document "
            "with no lab results — that is a clinical statement this parser may not "
            "make. Nothing printed is echoed here (invariant 6)."
        )
    return LabTableParse(
        completion={"items": items},
        regions=tuple(row_regions),
        rows_unread=tuple(unread),
        fenced=fenced,
    )

"""Document extraction → confirm cards → FHIR, with a box on every value.

INT-121. The acceptance is *"labs/meds/diagnoses extracted with source boxes;
patient confirms before use; accuracy metric on corpus >=90 percent
LOINC+unit"*, and the package is split along it:

* :mod:`~intake_platform.records.document` — the geometry seam and the data
  boundary (CLAUDE.md invariant 14: a document is data, never instructions);
* :mod:`~intake_platform.records.extraction` — the closed-key-set parser, the
  triage refusal (invariant 1) and the terminology seam;
* :mod:`~intake_platform.records.numbers` and
  :mod:`~intake_platform.records.analytes` — invariant 22 at the ingestion
  crossing;
* :mod:`~intake_platform.records.corpus` — the measurement, which refuses to
  produce a figure without a named, dated corpus (invariant 20).

The confirm gate itself is :mod:`clinical_schemas.record_extraction`: an
extracted value is a candidate until a human says otherwise, and that is a
type rather than a rule (invariant 12).
"""

from __future__ import annotations

from intake_platform.records.analytes import Analyte, AnalyteAmbiguous, resolve_analyte
from intake_platform.records.document import (
    BOUNDARY_NAME,
    ESCAPE_REASON,
    DocumentBoundaryEscape,
    FencedDocument,
    LayoutExtractor,
    LayoutUnavailable,
    NoLayout,
    TextRegion,
    fence_document_regions,
    read_document_regions,
)
from intake_platform.records.extraction import (
    ITEM_KEYS,
    LEVEL_SHAPED_KEYS,
    TOP_LEVEL_KEYS,
    ConfirmedRecordStore,
    DocumentExtraction,
    NoTerminology,
    RecordSchemaViolation,
    RegionUnknown,
    TerminologyBinder,
    TriageAssertionRefused,
    extract_record_items,
    summarise_item,
)
from intake_platform.records.numbers import (
    NBSP,
    PrintedMagnitudeAmbiguous,
    PrintedMagnitudeUnreadable,
    UnitResolution,
    parse_printed_magnitude,
    quantity_atom,
    render_quantity,
    resolve_unit,
)

__all__ = [
    "BOUNDARY_NAME",
    "ESCAPE_REASON",
    "ITEM_KEYS",
    "LEVEL_SHAPED_KEYS",
    "NBSP",
    "TOP_LEVEL_KEYS",
    "Analyte",
    "AnalyteAmbiguous",
    "ConfirmedRecordStore",
    "DocumentBoundaryEscape",
    "DocumentExtraction",
    "FencedDocument",
    "LayoutExtractor",
    "LayoutUnavailable",
    "NoLayout",
    "NoTerminology",
    "PrintedMagnitudeAmbiguous",
    "PrintedMagnitudeUnreadable",
    "RecordSchemaViolation",
    "RegionUnknown",
    "TerminologyBinder",
    "TextRegion",
    "TriageAssertionRefused",
    "UnitResolution",
    "extract_record_items",
    "fence_document_regions",
    "parse_printed_magnitude",
    "quantity_atom",
    "read_document_regions",
    "render_quantity",
    "resolve_analyte",
    "resolve_unit",
    "summarise_item",
]

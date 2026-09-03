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

INT-122 adds the two patient-supplied sources beside them, each feeding the
modules above rather than re-implementing one:

* :mod:`~intake_platform.records.enabiz` — the mandated six-column Turkish lab
  table (files/03 §10), read from geometry and handed to ``extract_record_items``
  with every value still spelled as the document printed it;
* :mod:`~intake_platform.records.mhrs` and
  :mod:`~intake_platform.records.visit_candidate` — the MHRS SMS screenshot, the
  weakest source here, whose every reading is a candidate at the type level;
* :mod:`~intake_platform.records.turkish_dates` — invariant 22 for the other
  numeral on this path, the printed date.

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
from intake_platform.records.enabiz import (
    CARRIED_COLUMNS,
    DROPPED_COLUMNS,
    LAB_TABLE_COLUMNS,
    LabTableParse,
    LabTableShapeUnrecognised,
    parse_lab_table,
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
from intake_platform.records.mhrs import (
    BranchNameAmbiguous,
    BranchVocabulary,
    parse_mhrs_sms,
    resolve_printed_branch,
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
from intake_platform.records.turkish_dates import (
    TURKISH_MONTHS,
    DateOrder,
    PrintedDateAmbiguous,
    PrintedDateNotFound,
    PrintedDateTimeUnreadable,
    PrintedDateUnreadable,
    PrintedTimeAmbiguous,
    PrintedTimeNotFound,
    PrintedTimeUnreadable,
    find_printed_date,
    find_printed_time,
    parse_printed_date,
    parse_printed_time,
)
from intake_platform.records.visit_candidate import (
    CandidateVisitFields,
    ConfirmedVisitFields,
    VisitCandidateError,
    VisitFieldRefusal,
    VisitFields,
    confirm_visit_candidate,
)

__all__ = [
    "Analyte",
    "AnalyteAmbiguous",
    "BOUNDARY_NAME",
    "BranchNameAmbiguous",
    "BranchVocabulary",
    "CARRIED_COLUMNS",
    "CandidateVisitFields",
    "ConfirmedRecordStore",
    "ConfirmedVisitFields",
    "DROPPED_COLUMNS",
    "DateOrder",
    "DocumentBoundaryEscape",
    "DocumentExtraction",
    "ESCAPE_REASON",
    "FencedDocument",
    "ITEM_KEYS",
    "LAB_TABLE_COLUMNS",
    "LEVEL_SHAPED_KEYS",
    "LabTableParse",
    "LabTableShapeUnrecognised",
    "LayoutExtractor",
    "LayoutUnavailable",
    "NBSP",
    "NoLayout",
    "NoTerminology",
    "PrintedDateAmbiguous",
    "PrintedDateNotFound",
    "PrintedDateTimeUnreadable",
    "PrintedDateUnreadable",
    "PrintedMagnitudeAmbiguous",
    "PrintedMagnitudeUnreadable",
    "PrintedTimeAmbiguous",
    "PrintedTimeNotFound",
    "PrintedTimeUnreadable",
    "RecordSchemaViolation",
    "RegionUnknown",
    "TOP_LEVEL_KEYS",
    "TURKISH_MONTHS",
    "TerminologyBinder",
    "TextRegion",
    "TriageAssertionRefused",
    "UnitResolution",
    "VisitCandidateError",
    "VisitFieldRefusal",
    "VisitFields",
    "confirm_visit_candidate",
    "extract_record_items",
    "fence_document_regions",
    "find_printed_date",
    "find_printed_time",
    "parse_lab_table",
    "parse_mhrs_sms",
    "parse_printed_date",
    "parse_printed_magnitude",
    "parse_printed_time",
    "quantity_atom",
    "read_document_regions",
    "render_quantity",
    "resolve_analyte",
    "resolve_printed_branch",
    "resolve_unit",
    "summarise_item",
]

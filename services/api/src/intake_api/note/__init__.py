"""The pre-visit note composer and its renderers (INT-084).

One composer builds the note; three renderers present it. Nothing in this
package reaches the network, writes a log or declares a route: a note that
leaves the service is a *share*, which checks a consent scope and writes the
hash-chained audit entry at the delivery surface that owns it (INT-150's
Doctor Link, the connectors). This package produces bytes and hands them back.

INT-085 adds the patient half: :mod:`intake_api.note.summary` builds the
files/04 §5 ``PatientSummary`` from the same composed note, behind a positive
allow-list of the fields that may cross, and :mod:`intake_api.note.readability`
is the structural gate its authored copy must pass.
"""

from __future__ import annotations

from intake_api.note.compose import NBSP, NoteCompositionError, compose_note
from intake_api.note.document import NoteDocument, Watermark, render_note_pdf
from intake_api.note.fhir import previsit_note_bundle
from intake_api.note.readability import (
    B1_MAX_WORDS_PER_SENTENCE,
    JARGON_TERMS,
    SCORED_METRICS,
    ReadabilityCheck,
    ReadabilityFinding,
    ReadabilityMetric,
    ReadabilityReport,
    ReadabilityScore,
    SummaryText,
    TextOrigin,
    check_readability,
)
from intake_api.note.render import (
    OBJECTIVE_SECTIONS,
    SUBJECTIVE_SECTIONS,
    TRAILING_SECTIONS,
    LineKind,
    RenderedLine,
    RenderedNote,
    UnattributedLineError,
    render_soap,
)
from intake_api.note.strings import (
    NOTE_DISCLAIMER_KEY,
    NOTE_SCREENING_AI_LABEL_KEY,
    load_note_strings,
    note_string_keys,
)
from intake_api.note.summary import (
    CLINICIAN_ONLY_SECTIONS,
    PATIENT_VISIBLE_FIELDS,
    PATIENT_VISIBLE_SECTIONS,
    ComposedSummary,
    PatientSummaryReadabilityError,
    SummaryStringsMissingError,
    build_patient_summary,
    jargon_terms,
    normalise_field_ref,
    render_patient_summary,
    section_partition_error,
    summary_string_keys,
)

__all__ = [
    "B1_MAX_WORDS_PER_SENTENCE",
    "CLINICIAN_ONLY_SECTIONS",
    "JARGON_TERMS",
    "NBSP",
    "NOTE_DISCLAIMER_KEY",
    "NOTE_SCREENING_AI_LABEL_KEY",
    "OBJECTIVE_SECTIONS",
    "PATIENT_VISIBLE_FIELDS",
    "PATIENT_VISIBLE_SECTIONS",
    "SCORED_METRICS",
    "SUBJECTIVE_SECTIONS",
    "TRAILING_SECTIONS",
    "ComposedSummary",
    "LineKind",
    "NoteCompositionError",
    "NoteDocument",
    "PatientSummaryReadabilityError",
    "ReadabilityCheck",
    "ReadabilityFinding",
    "ReadabilityMetric",
    "ReadabilityReport",
    "ReadabilityScore",
    "RenderedLine",
    "RenderedNote",
    "SummaryStringsMissingError",
    "SummaryText",
    "TextOrigin",
    "UnattributedLineError",
    "Watermark",
    "build_patient_summary",
    "check_readability",
    "compose_note",
    "jargon_terms",
    "load_note_strings",
    "normalise_field_ref",
    "note_string_keys",
    "previsit_note_bundle",
    "render_note_pdf",
    "render_patient_summary",
    "render_soap",
    "section_partition_error",
    "summary_string_keys",
]

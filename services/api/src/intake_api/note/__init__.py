"""The pre-visit note composer and its renderers (INT-084).

One composer builds the note; three renderers present it. Nothing in this
package reaches the network, writes a log or declares a route: a note that
leaves the service is a *share*, which checks a consent scope and writes the
hash-chained audit entry at the delivery surface that owns it (INT-150's
Doctor Link, the connectors). This package produces bytes and hands them back.
"""

from __future__ import annotations

from intake_api.note.compose import NBSP, NoteCompositionError, compose_note
from intake_api.note.document import NoteDocument, Watermark, render_note_pdf
from intake_api.note.fhir import previsit_note_bundle
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

__all__ = [
    "NBSP",
    "NOTE_DISCLAIMER_KEY",
    "NOTE_SCREENING_AI_LABEL_KEY",
    "OBJECTIVE_SECTIONS",
    "SUBJECTIVE_SECTIONS",
    "TRAILING_SECTIONS",
    "LineKind",
    "NoteCompositionError",
    "NoteDocument",
    "RenderedLine",
    "RenderedNote",
    "UnattributedLineError",
    "Watermark",
    "compose_note",
    "load_note_strings",
    "note_string_keys",
    "previsit_note_bundle",
    "render_note_pdf",
    "render_soap",
]

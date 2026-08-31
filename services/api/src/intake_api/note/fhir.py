"""The composed note as a FHIR R4 document Bundle (INT-084).

INT-033 already built the mapping and its round-trip tests, so this is a thin,
deliberate delegation rather than a second mapper: two mappers for one note
would be two answers to *"what did the clinician receive"*. The composer's
output is the same ``PreVisitNote`` the mapper already consumes, which is why
provenance rides beside the note instead of inside it.

The candidate flags do not cross — ``previsit_note_to_document_bundle``
consumes ``triage.level`` and ``triage.rules`` and nothing else (invariant 1),
and the golden bundle in tests/engine pins that they are absent from the wire.
"""

from __future__ import annotations

from typing import Any

from clinical_schemas.composition import AttributedNote
from clinical_schemas.mappers import previsit_note_to_document_bundle, to_wire

__all__ = ["previsit_note_bundle"]


def previsit_note_bundle(note: AttributedNote, *, patient_id: str) -> dict[str, Any]:
    """The note as the JSON a FHIR server receives (camelCase, no nulls)."""
    return to_wire(previsit_note_to_document_bundle(note.note, patient_id=patient_id))

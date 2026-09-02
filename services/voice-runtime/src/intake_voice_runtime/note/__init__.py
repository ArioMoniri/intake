"""INT-084 — the pre-visit note: composer, provenance and renderers.

files/03 §11 builds this note incrementally from ``draft_note_delta`` Work, so
it lives with the Clinical Backend Agent rather than in the schema package:
composing is a session activity, and the 04 §5 types are its vocabulary.

**What "missing" means here, and why it is a decision rather than a detail.**
docs/evidence/INT-282.md left one disagreement open. The INT-081 engine counts
a ``must_ask`` step whose gate is TRUE **or UNKNOWN** as obliged; mobile's
``missingQuestions`` keeps gate-TRUE steps only and calls the rest *"skipped,
not missing"*. On a checkpointed session — files/02 §2 calls that the most
common way a detailed session ends — the two produce different answers to
*"what is absent from this note?"*, which is a note-semantics question and
therefore this issue's.

**The note takes the engine's definition**, and takes it structurally:
:class:`~intake_voice_runtime.note.facts.NoteGapReason` has a
``unresolved_precondition`` member, so an obliged step behind a gate that
never resolved has somewhere to be recorded. Mobile's definition is not
representable — it yields no gap at all — so the two cannot be reconciled by
configuration. The reason is asymmetry of harm: a clinician who reads a short
``eksik`` list believes more was covered than was, and acts on that; an
over-long one is noise they can dismiss. **This is flagged, not settled** —
files/13 §9.4 and files/04 §5 have a human owner, and when INT-096 puts
compiled packs behind both surfaces one of them has to change. See
docs/evidence/INT-084.md.
"""

from __future__ import annotations

from intake_voice_runtime.note.composer import ComposedNote, compose, facts_by_section
from intake_voice_runtime.note.copy import (
    NOTE_COPY_KEYS,
    NOTE_COPY_SECTIONS,
    NoteCopy,
    note_copy_from_legal_strings,
)
from intake_voice_runtime.note.facts import (
    SECTION_ATTRIBUTIONS,
    Attribution,
    AttributionRefused,
    FactSubject,
    NoteFact,
    NoteGap,
    NoteGapReason,
    Sourced,
    SourceKind,
    SourceSpan,
)
from intake_voice_runtime.note.render import (
    render_fhir_document,
    render_note_pdf,
    render_soap,
)

# Re-exported so a caller writes one import and the note's vocabulary and its
# 04 §5 types stay together at the call site.
from clinical_schemas.note import MeasureCode, SelfReportedMeasure  # noqa: E402  isort:skip

__all__ = [
    "NOTE_COPY_KEYS",
    "NOTE_COPY_SECTIONS",
    "SECTION_ATTRIBUTIONS",
    "Attribution",
    "AttributionRefused",
    "ComposedNote",
    "FactSubject",
    "MeasureCode",
    "NoteCopy",
    "NoteFact",
    "NoteGap",
    "NoteGapReason",
    "SelfReportedMeasure",
    "SourceKind",
    "SourceSpan",
    "Sourced",
    "compose",
    "facts_by_section",
    "note_copy_from_legal_strings",
    "render_fhir_document",
    "render_note_pdf",
    "render_soap",
]

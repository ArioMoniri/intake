"""The fixed legal strings the pre-visit note renders from (INT-084).

This module declares a KEY SET, not copy — the same contract as
:mod:`intake_api.dsar.strings` and for the same reason. CLAUDE.md invariant
18: *"consent and legal texts render only from ``docs/legal/`` with hash
binding; the fixed strings in ``docs/legal/strings.yaml`` are verbatim."*
files/06 §7 is where those strings are specified and INT-210 is where a human
authors them; that file does not exist in this repository today, so every
render below fails closed with :class:`LegalStringsMissingError` and no note
document is produced at all.

Two keys, and the second one is not scope creep:

``previsit_note.disclaimer``
    The files/06 §7 note/PDF footer. Required on every note, always.
``previsit_note.screening_ai_label``
    files/06 §7 also fixes the label that must accompany a wellbeing signal.
    A note that printed a screening score without it would be a legal defect
    on the same page as the disclaimer, so the key is required exactly when a
    score is rendered — the gate is on the content, not on the caller's
    memory.

Nothing here carries a default. A "temporary" Turkish string in source is
indistinguishable from counsel's own once merged, and it would be the one
kind of invented value CLAUDE.md reserves absolutely.
"""

from __future__ import annotations

from typing import Final

from clinical_schemas.composition import AttributedNote
from intake_platform.legal import LegalStrings, LegalStringsCatalog

__all__ = [
    "NOTE_DISCLAIMER_KEY",
    "NOTE_SCREENING_AI_LABEL_KEY",
    "load_note_strings",
    "note_string_keys",
]

NOTE_DISCLAIMER_KEY: Final = "previsit_note.disclaimer"
NOTE_SCREENING_AI_LABEL_KEY: Final = "previsit_note.screening_ai_label"


def note_string_keys(*, screening_scored: bool) -> tuple[str, ...]:
    """The fixed strings this note cannot be rendered without."""
    if screening_scored:
        return (NOTE_DISCLAIMER_KEY, NOTE_SCREENING_AI_LABEL_KEY)
    return (NOTE_DISCLAIMER_KEY,)


def load_note_strings(
    catalog: LegalStringsCatalog, note: AttributedNote, *, expected_hash: str | None = None
) -> LegalStrings:
    """The hash-bound strings for one note, or a refusal.

    ``expected_hash`` re-binds a note that was already issued: if the file has
    moved since, the loader raises rather than restate what was never shown.
    """
    return catalog.entry(
        required=note_string_keys(screening_scored=note.screening_scored()),
        expected_hash=expected_hash,
    )

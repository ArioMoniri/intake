"""The pre-visit note as a PDF (INT-084).

Reuses ``intake_platform.pdf`` for the byte-level plumbing only — that module
says so itself (*"the clinician-facing pre-visit note PDF is INT-084's own
artefact … only, if it wants it later, this module's byte-level plumbing"*).
The layout, the fixed strings and the watermark block are this module's.

**Watermark-ready, and precisely that.** files/10 §1 requires a PDF handed to
a clinician to be watermarked with recipient and timestamp. The document model
here carries that stamp as a first-class value and renders it into the
document header, so the delivery surface that actually issues a PDF
(Doctor Link, INT-150) has somewhere to put its recipient rather than
inventing one. Per-page repetition of the stamp needs a page-aware hook in
``intake_platform.pdf``, which this issue does not own; docs/evidence/INT-084.md
records that as the remaining half rather than claiming it here.

``escape_unencodable=True`` matches the INT-037 export document and for the
same reason: a clinician who receives nothing is worse off than one who
receives a page naming the one character the encoding could not draw. The
character is named as ``[U+…]``, never transliterated.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from clinical_schemas.composition import AttributedNote
from clinical_schemas.mappers.codes import DOCUMENT_TITLE_TR
from intake_platform.legal import LegalStrings
from intake_platform.pdf import render_text_pdf

from intake_api.note.render import render_soap

__all__ = ["NoteDocument", "Watermark", "render_note_pdf"]


@dataclass(frozen=True, slots=True)
class Watermark:
    """Who this copy was issued to, and when (files/10 §1)."""

    recipient: str
    issued_at: datetime

    def lines(self) -> tuple[str, ...]:
        return (
            f"watermark_recipient: {self.recipient}",
            f"watermark_issued_at: {self.issued_at.isoformat()}",
        )


@dataclass(frozen=True, slots=True)
class NoteDocument:
    """The rendered PDF plus the binding that proves what it said."""

    pdf: bytes
    legal_strings_version: str
    legal_strings_hash: str


def render_note_pdf(
    note: AttributedNote, *, strings: LegalStrings, watermark: Watermark | None = None
) -> NoteDocument:
    """Render the note as a deterministic PDF. Same inputs, same bytes."""
    rendered = render_soap(note, strings=strings)
    lines: list[str] = []
    if watermark is not None:
        lines.extend(watermark.lines())
    lines.extend(line.text for line in rendered.lines)
    return NoteDocument(
        pdf=render_text_pdf(title=DOCUMENT_TITLE_TR, lines=lines, escape_unencodable=True),
        legal_strings_version=rendered.legal_strings_version,
        legal_strings_hash=rendered.legal_strings_hash,
    )

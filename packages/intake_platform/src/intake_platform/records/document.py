"""The document side of records extraction: geometry, and the data boundary.

Two seams and one control, split out of :mod:`intake_platform.records.extraction`
so neither file has to be read whole to answer a question about the other.

- :class:`LayoutExtractor` is the geometry seam, alongside INT-120's
  :class:`~intake_platform.uploads.OcrExtractor`. It returns the page, the
  rectangle and the character interval of each region of a document, which is
  what a source box is made of. :class:`NoLayout` is the fail-closed default,
  and :func:`read_document_regions` **raises** on an empty layout rather than
  returning items with no box.
- :class:`FencedDocument` is the data boundary (CLAUDE.md invariant 14;
  docs/security/threat-model.md row ``records``: *"document text ↔ model
  context (data, never instructions)"*). The **rule** — the tag, the refused
  control marker, the text-derived nonce, the fence, the counter — lives in
  :mod:`intake_platform.data_boundary`, which is the same control INT-083 built
  for a transcript rather than a second copy of it. What lives here is the
  typed wrapper that says *this untrusted text is a document*.

There is deliberately no function in this module that takes document text and
returns instructions. That is what "data, never instructions" has to mean if it
is to survive a refactor.

**No message here echoes what a document printed** (invariant 6).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Protocol

from clinical_schemas.record_extraction import SourceBox

from intake_platform.data_boundary import (
    INJECTION_SUSPECTED_TOTAL,
    DataBoundaryEscape,
    carries_control_token,
    digest,
    render_fence,
    sentinel_for,
)

__all__ = [
    "BOUNDARY_NAME",
    "ESCAPE_REASON",
    "DocumentBoundaryEscape",
    "FencedDocument",
    "LayoutExtractor",
    "LayoutUnavailable",
    "NoLayout",
    "TextRegion",
    "fence_document_regions",
    "read_document_regions",
]

#: Named in the security event rather than spelled at each call site
#: (docs/security/threat-model.md row ``records``).
BOUNDARY_NAME: Final = "records"
ESCAPE_REASON: Final = "data_block_escape"


class LayoutUnavailable(ValueError):
    """The layout seam produced no regions, so no value could carry a box.

    Fail closed: an extraction with no geometry would be a list of numbers a
    clinician has no way to check, which is the state the acceptance's "source
    boxes" exists to make impossible.
    """


class DocumentBoundaryEscape(DataBoundaryEscape):
    """A document's text layer carries the data-block control token.

    Refused whole rather than escaped — including when the token sits in a
    hidden text run, which is the RT-11 shape (INT-102).
    """


# --- the layout seam ------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TextRegion:
    """One region of a parsed document: where it is, and what it says.

    ``start``/``end`` index the document's extracted text, so a region converts
    into a source box without either side re-deriving offsets.
    """

    page: int
    bbox: tuple[float, float, float, float]
    start: int
    end: int
    text: str

    def as_box(self, document_ref: str) -> SourceBox:
        return SourceBox(
            document_ref=document_ref,
            page=self.page,
            bbox=self.bbox,
            start=self.start,
            end=self.end,
        )


class LayoutExtractor(Protocol):
    """The geometry seam, beside INT-120's ``OcrExtractor``.

    The engine and its sandbox (files/10 §4: seccomp-isolated parsing) are the
    same open ADR that keeps ``NoOcr`` wired in production; an implementation
    plugs in here without a caller changing.
    """

    def regions(self, data: bytes, content_type: str) -> tuple[TextRegion, ...]: ...


@dataclass(frozen=True, slots=True)
class NoLayout:
    """The fail-closed default: untrusted bytes meet no parser in this process.

    Returning nothing is the honest answer, and :func:`read_document_regions`
    turns it into a refusal rather than an empty extraction — an empty result
    would read as "this document contains no labs".
    """

    def regions(self, data: bytes, content_type: str) -> tuple[TextRegion, ...]:
        return ()


def read_document_regions(
    data: bytes, content_type: str, *, layout: LayoutExtractor
) -> tuple[TextRegion, ...]:
    """Run the layout seam, refusing an empty result."""
    regions = layout.regions(data, content_type)
    if not regions:
        raise LayoutUnavailable(
            "the layout seam produced no regions, so no extracted value could carry a "
            "source box; the document stays unextracted (fail closed). Production wires "
            "NoLayout while the OCR engine-and-sandbox ADR is open."
        )
    return regions


# --- the data boundary ----------------------------------------------------------------------


@dataclass(frozen=True, repr=False)
class FencedDocument:
    """One document's text layer, wrapped so that it can only be used as data.

    Constructing this type is the boundary crossing. It is a *different type*
    from INT-083's ``PatientData`` on purpose — a transcript and a document are
    both untrusted text, and a parameter should say which one it takes — while
    the rule both obey lives in one module.
    """

    text: str

    def __post_init__(self) -> None:
        if not self.text:
            raise DocumentBoundaryEscape("a document with no text layer is not an input")
        if carries_control_token(self.text):
            INJECTION_SUSPECTED_TOTAL.inc()
            raise DocumentBoundaryEscape(
                "the document's text layer carries the data-block control token — it is "
                "refused rather than escaped, because escaping rewrites what the "
                f"document printed (CLAUDE.md invariant 14). Digest {self.sha256}; the "
                "text is deliberately not echoed here (invariant 6)."
            )

    @property
    def sha256(self) -> str:
        return digest(self.text)

    @property
    def sentinel(self) -> str:
        return sentinel_for(self.text)

    @property
    def rendered(self) -> str:
        """The fenced block, and the only rendering of a document's text here."""
        return render_fence(self.text, sentinel=self.sentinel)

    def __repr__(self) -> str:
        return f"FencedDocument(sha256={self.sha256!r}, chars={len(self.text)})"

    def __str__(self) -> str:
        return self.__repr__()


def fence_document_regions(regions: Sequence[TextRegion]) -> FencedDocument:
    """Fence a document's regions as data (invariant 14; threat row ``records``).

    The **whole** text layer goes in, hidden lines included: that is what lets
    the provenance say what the document said. A region carrying the fence
    marker refuses the document whole, never escapes it.
    """
    return FencedDocument(text="\n".join(region.text for region in regions))

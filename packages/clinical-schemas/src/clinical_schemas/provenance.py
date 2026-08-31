"""Note provenance carriers (INT-084).

The INT-084 acceptance opens with *"every fact carries source span"*. This
module makes that structural rather than procedural: there is no way to hold a
piece of note content without also holding at least one
:class:`SourceSpan`, because :class:`Attributed` and :class:`NoteFact` both
declare ``spans`` as a required, non-empty field. A caller that forgets is a
``mypy --strict`` error; a caller that passes ``()`` is a
``ValidationError``. Neither reaches a renderer.

Why a separate carrier instead of span fields on
:mod:`clinical_schemas.note`: ``PreVisitNote`` is the authoritative files/04
§5 shape and the INT-033 exchange face. Widening every item there would
change a published schema to solve a composition problem, so provenance rides
*beside* the note (:class:`~clinical_schemas.composition.AttributedNote`) and
the composer is the only thing that can put the two together.

``triage`` and ``data_gaps`` are deliberately **not** attributable sections:

- a triage level is produced by ``packages/protocols/triage`` and by nothing
  else (CLAUDE.md invariant 1), so it is not a fact anybody may attribute to
  an utterance — the note carries the rules result itself;
- a data gap is an **absence** (files/12 §2: a slot whose gate is Unknown
  renders as *"never asked"*, never as *"elicited and absent"*), and an
  absence has no source to point at. A gap that could carry a span would be
  indistinguishable from an elicited negative, which is the exact confusion
  files/12 §2 exists to end.
"""

from __future__ import annotations

import enum
from typing import Annotated, Final

from pydantic import Field, StringConstraints, model_validator

from clinical_schemas.common import FrozenModel, Ref
from clinical_schemas.note import PreVisitNote

__all__ = [
    "ATTRIBUTABLE_SECTIONS",
    "NOTE_SECTIONS",
    "Attributed",
    "FieldRef",
    "NoteFact",
    "SourceKind",
    "SourceSpan",
    "SpanSet",
]

#: Every files/04 §5 note key, in note order. ``meta`` feeds the document
#: header rather than a section, exactly as ``mappers.codes.NOTE_SECTION_IDS``
#: derives it; a test asserts the two stay equal.
NOTE_SECTIONS: Final[tuple[str, ...]] = tuple(
    name for name in PreVisitNote.model_fields if name != "meta"
)

#: The sections a :class:`NoteFact` may claim — see the module docstring for
#: why the other two are excluded.
ATTRIBUTABLE_SECTIONS: Final[tuple[str, ...]] = tuple(
    name for name in NOTE_SECTIONS if name not in {"triage", "data_gaps"}
)


class SourceKind(enum.StrEnum):
    """Where a span points. Each kind names a different store, so a reader can
    tell a spoken sentence from a printed lab line without opening either."""

    UTTERANCE = "utterance"
    """A spoken turn of this session (files/03 §4.3 ``extract_slots``)."""

    TYPED = "typed"
    """Typed-profile input, including a scripted instrument's own answer."""

    DOCUMENT = "document"
    """An uploaded document (files/03 §4.6 Provenance; page carried below)."""

    RECORD = "record"
    """A pulled hospital record (files/03 §12.1 bilateral tenants only)."""


class SourceSpan(FrozenModel):
    """A half-open ``[start, end)`` interval in one named source.

    Offsets, not text: the quoted words already live in the note line, and
    repeating them here would put the same PHI in two places for no gain
    (invariant 6 is about logs, but the minimisation reasoning is the same).
    """

    kind: SourceKind = Field(description="Which store ``source_ref`` names.")
    source_ref: Ref = Field(
        description="Id of the utterance, document or record (id shape only, never text)."
    )
    start: int = Field(ge=0, description="Inclusive character offset into the source.")
    end: int = Field(ge=1, description="Exclusive character offset; must exceed ``start``.")
    page: int | None = Field(
        default=None,
        ge=1,
        description="1-based source page — documents only (files/03 §4.6 Provenance page).",
    )

    @model_validator(mode="after")
    def _interval_and_page(self) -> SourceSpan:
        if self.end <= self.start:
            raise ValueError("a source span must cover at least one character")
        if self.page is not None and self.kind is not SourceKind.DOCUMENT:
            raise ValueError("page belongs to a document span only")
        return self


#: One or more spans. The ``min_length`` is the whole point: an empty tuple is
#: the shape a careless caller produces, and it is refused at construction.
SpanSet = Annotated[tuple[SourceSpan, ...], Field(min_length=1)]

#: A dotted path into the files/04 §5 note shape, e.g. ``hpi.oldcarts.onset``
#: or ``medications[0].name``. Indexed segments are allowed so a list item can
#: be addressed; nothing else is.
FieldRef = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z][a-z0-9_]*(\[\d+\])?(\.[a-z][a-z0-9_]*(\[\d+\])?)*$"),
]


class Attributed[ValueT](FrozenModel):
    """One value and where it came from. The composer's whole input surface is
    built from this, so content cannot enter a note unattributed."""

    value: ValueT = Field(description="The note content this attribution covers.")
    spans: SpanSet = Field(description="Where the value came from — at least one span.")


class NoteFact(FrozenModel):
    """One rendered line of note content, bound to its sources.

    A renderer emits a content line only from a ``NoteFact``, so the chain
    *line → fact → span* has no gap in it.
    """

    section: str = Field(description="files/04 §5 note key this line belongs to.")
    field_ref: FieldRef = Field(description="Dotted path of the value inside that section.")
    text: str = Field(min_length=1, description="The clinician-visible rendering of the value.")
    spans: SpanSet = Field(description="Where the value came from — at least one span.")

    @model_validator(mode="after")
    def _section_is_attributable(self) -> NoteFact:
        if self.section not in ATTRIBUTABLE_SECTIONS:
            raise ValueError(f"{self.section!r} is not an attributable note section")
        head = self.field_ref.split(".", 1)[0].split("[", 1)[0]
        if head != self.section:
            raise ValueError("field_ref must start with its own section")
        return self

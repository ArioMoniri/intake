"""Source boxes and the confirm gate for document extraction (INT-121).

The INT-121 acceptance is *"labs/meds/diagnoses extracted with source boxes;
patient confirms before use"*, and this module is the half of that which the
type system can carry. The pipeline that fills these types in lives beside
``uploads.py`` (:mod:`intake_platform.records_extraction`); nothing here
imports it, because ``clinical-schemas`` depends on pydantic and nothing else.

**Two structural properties, and neither is a check somebody could forget.**

1. *"with source boxes"* — :class:`SourceBox` is a required, defaultless field
   of :class:`UnconfirmedRecordItem`. A value with no box is not a case to
   reject; it cannot be written down. That is the line INT-084 took for note
   provenance, and the box **is** that span: :meth:`SourceBox.as_span` returns
   the very :class:`~clinical_schemas.provenance.SourceSpan` a
   :class:`~clinical_schemas.provenance.NoteFact` carries, so the geometric
   provenance a clinician clicks and the character provenance the note renders
   are one object rather than two that can disagree.

2. *"patient confirms before use"* — :class:`UnconfirmedRecordItem` and
   :class:`ConfirmedRecordItem` are different frozen dataclasses and
   :func:`confirm_record_item` is the only bridge. The confirmation vocabulary
   is **INT-170's**, reused verbatim: :class:`~clinical_schemas.overlay.
   Confirmation` and :class:`~clinical_schemas.overlay.Confirmer`. Inventing a
   second vocabulary for the same invariant is how two answers to one question
   end up in one repository.

**Why frozen dataclasses and not** :class:`~clinical_schemas.common.FrozenModel`.
Exactly INT-170's reason, and it is load-bearing: this repository enables no
pydantic mypy plugin, so ``BaseModel.__init__`` type-checks as ``**data: Any``
— a missing ``box=`` and a stray ``confirmed=True`` would both pass
``mypy --strict`` and fail only at runtime, which would make "unconstructable"
a runtime claim wearing a type's clothes. The synthesised ``__init__`` of a
frozen dataclass refuses both at the call site.

:class:`~clinical_schemas.records.ExtractedRecordItem` (INT-031) stays the
transport shape — it is the published OpenAPI/TS surface and its
``verification_status`` is a settable enum, exactly as ``LearnedFact`` is for
INT-170. The projections here are the only way this pipeline reaches it, and
they are a narrowing on the way out: nothing that reaches
``verification_status=confirmed`` was unconfirmed.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Literal

from clinical_schemas.note import ImportedObjectiveItem
from clinical_schemas.overlay import Confirmation, Confirmer, LearnedFactSource
from clinical_schemas.provenance import Attributed, SourceKind, SourceSpan
from clinical_schemas.records import (
    ExtractedRecordItem,
    RecordCode,
    RecordItemKind,
    RecordProvenance,
    VerificationStatus,
)

__all__ = [
    "IMPORTED_OBJECTIVE_KINDS",
    "IMPORTED_OBJECTIVE_TYPES",
    "ConfirmedRecordItem",
    "RecordExtractionError",
    "SourceBox",
    "UnconfirmedRecordItem",
    "confirm_record_item",
]


class RecordExtractionError(ValueError):
    """A record extraction value is not constructible as asked.

    No message in this module echoes a printed name, a magnitude or a line of
    a document: every one of them is patient content and an exception message
    reaches a log (CLAUDE.md invariant 6).
    """


#: files/04 §5: ``imported_objective[].type`` is ``lab|imaging|procedure``. A
#: medication, a diagnosis or an allergy belongs to another note section, so it
#: is refused here rather than mistyped into this one. The mapping is spelled
#: out as literals rather than derived from ``kind.value`` so the checker — not
#: a comment — is what keeps the two enumerations in step.
IMPORTED_OBJECTIVE_TYPES: Mapping[RecordItemKind, Literal["lab", "imaging", "procedure"]] = (
    MappingProxyType(
        {
            RecordItemKind.LAB: "lab",
            RecordItemKind.IMAGING: "imaging",
            RecordItemKind.PROCEDURE: "procedure",
        }
    )
)

IMPORTED_OBJECTIVE_KINDS: frozenset[RecordItemKind] = frozenset(IMPORTED_OBJECTIVE_TYPES)


@dataclass(frozen=True, slots=True)
class SourceBox:
    """Where on which page a value came from — and which characters said it.

    ``bbox`` is normalised to the page (``0.0`` – ``1.0``, origin top-left) so
    a viewer can draw it without knowing the page size, matching
    :class:`~clinical_schemas.records.RecordProvenance`. ``start``/``end`` are
    the half-open character interval into the document's extracted text, which
    is what :class:`~clinical_schemas.provenance.SourceSpan` speaks.
    """

    document_ref: str
    page: int
    bbox: tuple[float, float, float, float]
    start: int
    end: int

    def __post_init__(self) -> None:
        if not self.document_ref.strip():
            raise RecordExtractionError(
                "a source box names the document it points into (invariant 6: an id)"
            )
        if self.page < 1:
            raise RecordExtractionError("a source page is 1-based")
        x0, y0, x1, y1 = self.bbox
        if not all(0.0 <= value <= 1.0 for value in self.bbox):
            raise RecordExtractionError(
                "a source bbox is normalised to the page, so every coordinate is in [0, 1]"
            )
        if x1 <= x0 or y1 <= y0:
            raise RecordExtractionError(
                "a source bbox must enclose an area; an inverted or empty rectangle "
                "points at nothing a clinician could check"
            )
        if self.start < 0 or self.end <= self.start:
            raise RecordExtractionError(
                "a source box covers at least one character of the extracted text "
                "(half-open [start, end), as INT-084's SourceSpan)"
            )

    def as_span(self) -> SourceSpan:
        """The INT-084 provenance span this box *is*."""
        return SourceSpan(
            kind=SourceKind.DOCUMENT,
            source_ref=self.document_ref,
            start=self.start,
            end=self.end,
            page=self.page,
        )

    def as_provenance(self) -> RecordProvenance:
        """The INT-031 transport shape (files/03 §4.6: page and bbox)."""
        return RecordProvenance(document_ref=self.document_ref, page=self.page, bbox=self.bbox)

    def render_ref(self) -> str:
        """The provenance string the note already prints — ``document:doc-1 p2``."""
        return f"{self.document_ref} p{self.page}"


@dataclass(frozen=True, slots=True)
class UnconfirmedRecordItem:
    """What document extraction produces. Not usable, by construction.

    Nothing here names a confirmer or a confirmation time, so "an extraction
    that says it was confirmed" is not a case to reject — it cannot be written
    down. And ``box`` has no default, so neither can a value with no source box.

    There is deliberately no field a triage level could occupy (CLAUDE.md
    invariant 1: RED and YELLOW come from ``packages/protocols/triage`` alone,
    and a document is not a rules engine).
    """

    kind: RecordItemKind
    summary: str
    box: SourceBox
    observed_at: dt.datetime
    code: RecordCode | None = None
    value_magnitude: Decimal | None = None
    unit: str | None = None
    unit_conflict: bool = False
    date: dt.date | None = None

    def __post_init__(self) -> None:
        if not self.summary.strip():
            raise RecordExtractionError(
                "an extracted item renders something for the patient to confirm"
            )
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise RecordExtractionError("observed_at must be timezone-aware")

    def as_record_item(self) -> ExtractedRecordItem:
        """The INT-031 transport shape, still unconfirmed — this is what a
        confirm card renders."""
        return self._project(VerificationStatus.UNCONFIRMED)

    def _project(self, status: VerificationStatus) -> ExtractedRecordItem:
        return ExtractedRecordItem(
            kind=self.kind,
            summary=self.summary,
            code=self.code,
            value_magnitude=self.value_magnitude,
            unit=self.unit,
            unit_conflict=self.unit_conflict,
            date=self.date,
            verification_status=status,
            provenance=self.box.as_provenance(),
        )


@dataclass(frozen=True, slots=True)
class ConfirmedRecordItem:
    """The only shape a store, a note or the FHIR boundary accepts.

    It cannot be built without a :class:`~clinical_schemas.overlay.Confirmation`
    and the confirmation cannot be re-pointed afterwards, so a caller cannot
    walk an unconfirmed value in through a later assignment either.
    """

    observation: UnconfirmedRecordItem
    confirmation: Confirmation

    def __post_init__(self) -> None:
        if self.confirmation.source is not LearnedFactSource.CONFIRMED_IMPORTED_RECORD:
            raise RecordExtractionError(
                "a confirmed record item carries the imported-record provenance; a "
                "confirmation minted for another source describes another event"
            )
        if self.confirmation.source_ref != self.observation.box.document_ref:
            raise RecordExtractionError(
                "the confirming artefact is the document the source box points into; a "
                "confirmation naming a different document confirms a different thing"
            )

    def as_record_item(self) -> ExtractedRecordItem:
        """files/03 §4.6: confirmed only by the patient, never by the pipeline."""
        return self.observation._project(VerificationStatus.CONFIRMED)

    def as_imported_objective(self) -> Attributed[ImportedObjectiveItem]:
        """files/04 §5 ``imported_objective[]``, bound to its source box.

        The note renderer takes :class:`~clinical_schemas.provenance.Attributed`
        values only, so this is the single door from an imported value into a
        note — and it opens for a confirmed item alone.
        """
        kind = self.observation.kind
        note_type = IMPORTED_OBJECTIVE_TYPES.get(kind)
        if note_type is None:
            raise RecordExtractionError(
                f"{kind.value} is not an imported_objective type (files/04 §5: "
                "lab|imaging|procedure); it belongs to another note section"
            )
        return Attributed(
            value=ImportedObjectiveItem(
                type=note_type,
                summary=self.observation.summary,
                date=self.observation.date.isoformat() if self.observation.date else "",
                provenance=self.observation.box.render_ref(),
            ),
            spans=(self.observation.box.as_span(),),
        )


def confirm_record_item(
    item: UnconfirmedRecordItem, *, by: Confirmer, actor_ref: str, at: dt.datetime
) -> ConfirmedRecordItem:
    """The one bridge from an extraction to something usable.

    The observation carries over unchanged: confirming is agreeing with what
    was extracted, never restating it. A patient who disagrees produces a
    correction, not an edited extraction.

    The confirmation's ``source_ref`` is **derived from the box**, so a
    confirmation that names some other artefact is not a case to reject here
    either — the bridge cannot mint one.
    """
    return ConfirmedRecordItem(
        observation=item,
        confirmation=Confirmation(
            by=by,
            actor_ref=actor_ref,
            at=at,
            source=LearnedFactSource.CONFIRMED_IMPORTED_RECORD,
            source_ref=item.box.document_ref,
        ),
    )

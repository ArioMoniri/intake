"""INT-123 — a retrieved record, cited into the note with its provenance.

The last step of *"retrieval cited into notes with provenance"*. A retrieved
citation becomes a :class:`~intake_voice_runtime.note.facts.Sourced` note item
whose span is a document span carrying the document ref, the page, the box
**and the item id** — so the fact the composer files under
``imported_objective`` resolves, in every renderer's provenance block, to one
confirmed line of one page.

**Structural, not imported.** The citations are produced by
``intake_platform.records.retrieval``, and nothing under
``services/voice-runtime/src`` may import ``intake_platform.records`` — that
package holds the screen-side number renderer, and the INT-385 guard keeps it
unreachable from every module on the speech path (invariant 22). So this module
states the shape it needs as :class:`RecordCitationLike`, over
``clinical_schemas`` types only, and the platform's citation satisfies it.

**Attribution is ``RECORD`` and nothing else.** ``imported_objective`` admits
only that attribution (:data:`~intake_voice_runtime.note.facts.
SECTION_ATTRIBUTIONS`), and the value itself comes from
:meth:`~clinical_schemas.record_extraction.ConfirmedRecordItem.
as_imported_objective` — the single door from an imported value into a note,
which opens for a confirmed item alone.

**A kind with no ``imported_objective`` shape is reported, not filed.**
files/04 §5 types that section ``lab|imaging|procedure``. A retrieved
medication, diagnosis or allergy belongs to another section whose note shape
needs fields a document line does not carry (a reconciliation state, a
status); filling them in would be the composer inventing a clinical claim
(docs/backlog/blockers.md, INT-084). Those come back in
:attr:`CitedRecords.not_filed`, by item id and kind, so their absence from the
note is visible rather than silent.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from clinical_schemas.note import ImportedObjectiveItem
from clinical_schemas.record_extraction import IMPORTED_OBJECTIVE_KINDS, ConfirmedRecordItem
from clinical_schemas.records import RecordItemKind

from intake_voice_runtime.note.facts import Attribution, Sourced, SourceSpan

__all__ = ["CitedRecords", "RecordCitationLike", "cite_records"]


class RecordCitationLike(Protocol):
    """What a retrieved citation must carry to be cited: its provenance and
    the confirmed item it resolves to."""

    @property
    def item_ref(self) -> str: ...

    @property
    def document_ref(self) -> str: ...

    @property
    def page(self) -> int: ...

    @property
    def bbox(self) -> tuple[float, float, float, float]: ...

    @property
    def kind(self) -> RecordItemKind: ...

    @property
    def item(self) -> ConfirmedRecordItem: ...


@dataclass(frozen=True, slots=True)
class CitedRecords:
    """Citations ready for :func:`~intake_voice_runtime.note.compose`."""

    imported_objective: tuple[Sourced[ImportedObjectiveItem], ...]
    not_filed: tuple[tuple[str, RecordItemKind], ...]


def cite_records(citations: Iterable[RecordCitationLike]) -> CitedRecords:
    """One sourced note item per citable citation, in retrieval order."""
    filed: list[Sourced[ImportedObjectiveItem]] = []
    not_filed: list[tuple[str, RecordItemKind]] = []
    for citation in citations:
        if citation.kind not in IMPORTED_OBJECTIVE_KINDS:
            not_filed.append((citation.item_ref, citation.kind))
            continue
        filed.append(
            Sourced(
                citation.item.as_imported_objective(),
                attribution=Attribution.RECORD,
                span=SourceSpan.document(
                    document_ref=citation.document_ref,
                    page=citation.page,
                    bbox=citation.bbox,
                    item_ref=citation.item_ref,
                ),
            )
        )
    return CitedRecords(imported_objective=tuple(filed), not_filed=tuple(not_filed))

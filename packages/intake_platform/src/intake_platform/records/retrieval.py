"""Retrieval over one patient's record index, with provenance (INT-123).

The read half of *"retrieval cited into notes with provenance"*.
:meth:`RecordRetriever.retrieve` answers a query with the nearest **confirmed**
items in the patient's own namespace, each carrying where it came from: the
document ref, the page, the box, the character span and the derived item id.
``retrieve_records`` Work (``intake_voice_runtime.clinical_agent.
record_retrieval``) runs it off the speech path and the note composer files
what it returns.

Four refusals, in the order they are checked:

1. **Consent** (invariant 4): no live ``documents`` decision for the namespace,
   no retrieval — refused before the query reaches any model.
2. **No model** (invariant 19): with files/03 §4.9.1 naming no embedder, the
   query cannot be embedded and :class:`~intake_platform.records.embedding.
   EmbeddingModelUnregistered` propagates. An empty answer would look exactly
   like a patient with no records, so there is none.
3. **A hit that is no longer confirmed** is not cited. The index is derived; the
   confirmed-item store is the source of truth, and an item absent from it
   (erased, or never admitted in this process) is reported in
   :attr:`Retrieval.uncited` by id rather than cited from the vector alone.
4. **A hit whose stored box disagrees with the item** raises
   :class:`IndexProvenanceMismatch`: a citation pointing at a different line of
   a different page is a false statement in a clinical note.

Nothing here logs, and no refusal carries the query or an item's text
(invariant 6).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final, Protocol

from clinical_schemas.record_extraction import ConfirmedRecordItem, RecordExtractionError
from clinical_schemas.records import RecordItemKind

from intake_platform.records.embedding import RecordEmbedder, embed_checked, pinned_model_ref
from intake_platform.records.index import (
    IndexHit,
    RecordIndexStore,
    RecordsConsent,
    item_ref_of,
)

__all__ = [
    "MAX_K",
    "ConfirmedRecords",
    "IndexProvenanceMismatch",
    "RecordCitation",
    "RecordRetriever",
    "Retrieval",
]

#: Enough for a note section; a larger k is a query for the whole record.
MAX_K: Final = 50


class IndexProvenanceMismatch(RecordExtractionError):
    """An index row's box is not the confirmed item's box."""


class ConfirmedRecords(Protocol):
    """The source of truth a hit is resolved against."""

    @property
    def admitted(self) -> tuple[ConfirmedRecordItem, ...]: ...


@dataclass(frozen=True, slots=True)
class RecordCitation:
    """One retrieved, confirmed item and where on which page it was read."""

    item_ref: str
    document_ref: str
    page: int
    bbox: tuple[float, float, float, float]
    char_start: int
    char_end: int
    kind: RecordItemKind
    distance: float
    item: ConfirmedRecordItem

    @property
    def provenance(self) -> tuple[str, int, tuple[float, float, float, float], str]:
        """Document ref, page, bbox and item id — what the note cites."""
        return (self.document_ref, self.page, self.bbox, self.item_ref)


@dataclass(frozen=True, slots=True)
class Retrieval:
    """What one query returned: citations, nearest first, and the ids of hits
    whose item is no longer confirmed."""

    citations: tuple[RecordCitation, ...]
    uncited: tuple[str, ...]


def _matches(hit: IndexHit, item: ConfirmedRecordItem) -> bool:
    box = item.observation.box
    return (hit.document_ref, hit.page, hit.bbox, hit.char_start, hit.char_end, hit.kind) == (
        box.document_ref,
        box.page,
        box.bbox,
        box.start,
        box.end,
        item.observation.kind,
    )


@dataclass(frozen=True, slots=True)
class RecordRetriever:
    """Embeds a query with the pinned model and asks one namespace for its nearest."""

    embedder: RecordEmbedder
    store: RecordIndexStore
    records: ConfirmedRecords

    def retrieve(self, consent: RecordsConsent, query: str, *, k: int) -> Retrieval:
        if not 1 <= k <= MAX_K:
            raise ValueError(f"k must be between 1 and {MAX_K}")
        namespace = consent.require()
        model_ref = pinned_model_ref(self.embedder)
        (vector,) = embed_checked(self.embedder, [query])
        hits = self.store.nearest(namespace, model_ref=model_ref, vector=vector, k=k)
        return self._resolve(hits)

    def _resolve(self, hits: Iterable[IndexHit]) -> Retrieval:
        confirmed = {item_ref_of(item): item for item in self.records.admitted}
        citations: list[RecordCitation] = []
        uncited: list[str] = []
        for hit in hits:
            item = confirmed.get(hit.item_ref)
            if item is None:
                uncited.append(hit.item_ref)
                continue
            if not _matches(hit, item):
                raise IndexProvenanceMismatch(
                    f"index row {hit.item_ref} does not carry its confirmed item's source "
                    "box; a citation to another line is refused rather than filed"
                )
            citations.append(
                RecordCitation(
                    item_ref=hit.item_ref,
                    document_ref=hit.document_ref,
                    page=hit.page,
                    bbox=hit.bbox,
                    char_start=hit.char_start,
                    char_end=hit.char_end,
                    kind=hit.kind,
                    distance=hit.distance,
                    item=item,
                )
            )
        return Retrieval(citations=tuple(citations), uncited=tuple(uncited))

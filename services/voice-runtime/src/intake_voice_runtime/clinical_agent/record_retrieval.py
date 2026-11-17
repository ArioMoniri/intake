"""The ``retrieve_records`` background handler (INT-123).

files/03 §4.3 lists ``retrieve_records(query)`` among the Backend's Work types
and files/12 §7.4 puts it in the **background** lane: concurrent, handed a
:class:`~intake_voice_runtime.clinical_agent.work_queue.ReadOnlyContext` with
no mutator, and returning a
:class:`~intake_voice_runtime.clinical_agent.work_queue.BackgroundEffect` that
cannot express a slot write or a triage level. A retrieval therefore cannot
change what the intake has recorded or how it is triaged; it can only find the
patient's confirmed records and hand them to the note.

The handler follows ``extract_slots``' shape (INT-095):

1. **take** the query from the session's vault by the digest the request
   carries — the queue never holds text (invariant 6);
2. **retrieve** through the platform retriever
   (``intake_platform.records.retrieval.RecordRetriever``), which refuses
   without a live ``documents`` consent (invariant 4) and without a pinned
   embedder (invariant 19);
3. **keep** the citations — once per item id, in the order first found — for
   the note composer, which files them through
   :func:`~intake_voice_runtime.note.citations.cite_records`;
4. **return** an empty ``BackgroundEffect``: nothing is spoken. A record read
   back to the patient is ``parse_document``'s ``speech_tr`` at an insertion
   window, under the numeric pairing rules (invariant 22), not this Work's.

A refusal propagates and the queue turns it into a failed receipt naming the
error class; a cancelled Work keeps nothing.

**Typed by shape.** The retriever and its consent are held as protocols, not
imported: nothing under ``services/voice-runtime/src`` may import
``intake_platform.records`` (the INT-385 guard keeps the screen-side number
renderer off the speech path), and the handler only passes the consent through.

**Registration is the caller's.** The composition root does not bind this
handler: files/03 §4.9.1 names no embedding model, so there is no retriever it
could build, and ``UnregisteredWorkType`` at ``submit`` is the fail-closed
state (the ``parse_document`` precedent). :func:`register_retrieve_records` is
the one call a root makes once a model row exists.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from intake_voice_runtime.clinical_agent.work_queue import (
    BackendAgent,
    BackgroundEffect,
    ReadOnlyContext,
)
from intake_voice_runtime.note.citations import RecordCitationLike
from intake_voice_runtime.ports import WorkType
from intake_voice_runtime.transcript import TranscriptSource

__all__ = [
    "DEFAULT_K",
    "RecordRetrievalLike",
    "RetrievalLike",
    "RetrieveRecordsHandler",
    "register_retrieve_records",
]

#: How many nearest items one retrieval asks for — a handful for a note section.
DEFAULT_K = 5


class RetrievalLike(Protocol):
    @property
    def citations(self) -> Sequence[RecordCitationLike]: ...


class RecordRetrievalLike[ConsentT](Protocol):
    def retrieve(self, consent: ConsentT, query: str, *, k: int) -> RetrievalLike: ...


@dataclass
class RetrieveRecordsHandler[ConsentT]:
    """One session's retrieval: its consent, its query vault and what it found."""

    retriever: RecordRetrievalLike[ConsentT]
    consent: ConsentT
    queries: TranscriptSource
    k: int = DEFAULT_K
    _citations: dict[str, RecordCitationLike] = field(default_factory=dict, init=False, repr=False)

    def __call__(self, context: ReadOnlyContext) -> BackgroundEffect:
        query = self.queries.take(context.request.input_hash)
        found = self.retriever.retrieve(self.consent, query.text, k=self.k)
        if context.is_cancelled():
            return BackgroundEffect()
        for citation in found.citations:
            self._citations.setdefault(citation.item_ref, citation)
        return BackgroundEffect()

    @property
    def citations(self) -> tuple[RecordCitationLike, ...]:
        """Every item cited this session, once each, in the order first found."""
        return tuple(self._citations.values())


def register_retrieve_records[ConsentT](
    agent: BackendAgent, handler: RetrieveRecordsHandler[ConsentT]
) -> None:
    """Bind the handler to the background lane of one session's queue."""
    agent.register_background(WorkType.RETRIEVE_RECORDS, handler)

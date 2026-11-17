"""The record index: one namespace per patient, confirmed items only (INT-123).

Acceptance, verbatim: *"embeddings scoped by patient+consent; retrieval cited
into notes with provenance"*. This module is the write half and the scope;
:mod:`intake_platform.records.retrieval` is the read half.

**Scoped by patient.** Every entry names a :class:`RecordNamespace` — one
tenant, one patient — and the Postgres store sets both GUCs the migration's
policies read before it touches a row (0014: a PERMISSIVE tenant policy and a
RESTRICTIVE patient policy). There is no shared namespace to write into.

**Scoped by consent** (invariant 4). The purpose is files/06 §2's
``documents``: an index row is derived from a document the patient uploaded
under it. :class:`RecordsConsent` carries the live decision for one namespace,
read from the consent ledger by :func:`records_consent` — the same
``consent_state`` the API's consent guard enforces with — and both the queue
and the retriever refuse without one that stands.

**Confirmed only** (invariant 12). :meth:`RecordIndexQueue.enqueue` takes
:class:`~clinical_schemas.record_extraction.ConfirmedRecordItem` and nothing
else, and :class:`~intake_platform.records.ConfirmedRecordStore` calls it from
``admit``. An extraction nobody confirmed has no path into the index.

**A queue, not a call.** Admission is the patient tapping "doğru"; embedding is
a model call. The two are split the way the Backend Work queue splits the
Talker from Layer B: ``enqueue`` returns at once, :meth:`RecordIndexQueue.
run_pending` is the worker's pump, and each item leaves a receipt made of an
id, a closed state and an error class name — never the item's text
(invariant 6). A refusal is a receipt, not a crash.

**Erasure reaches every row.** An entry's ``document_ref`` must be
``doc:<documents.id>`` — the ref the audit chain already writes for a
document — so the retention executor can find the rows of each document it
destroys. A box pointing anywhere else is refused at write time rather than
indexed out of the erasure's reach.
"""

from __future__ import annotations

import enum
import hashlib
import uuid
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Final, Protocol

from clinical_schemas.record_extraction import ConfirmedRecordItem, RecordExtractionError
from clinical_schemas.records import RecordItemKind
from sqlalchemy.ext.asyncio import AsyncSession

from intake_platform.consent import ConsentDecision, ConsentTextCatalog, consent_state
from intake_platform.records.embedding import RecordEmbedder, embed_checked, pinned_model_ref

__all__ = [
    "DOCUMENT_REF_PREFIX",
    "RECORDS_CONSENT_SCOPE",
    "IndexEntry",
    "IndexHit",
    "IndexReceipt",
    "IndexState",
    "RecordIndexQueue",
    "RecordIndexStore",
    "RecordNamespace",
    "RecordsConsent",
    "RecordsConsentRefused",
    "UnaddressableDocumentRef",
    "document_id_of",
    "document_ref_of",
    "index_text_of",
    "item_ref_of",
    "records_consent",
]

#: files/06 §2's purpose for a patient's documents; the index is derived from them.
RECORDS_CONSENT_SCOPE: Final = "documents"

#: The ref the audit chain writes for a document (``doc:<documents.id>``).
DOCUMENT_REF_PREFIX: Final = "doc:"


class RecordsConsentRefused(PermissionError):
    """The ``documents`` decision does not stand. Names the scope, nothing else."""

    def __init__(self) -> None:
        super().__init__(f"consent scope {RECORDS_CONSENT_SCOPE!r} does not stand")


class UnaddressableDocumentRef(RecordExtractionError):
    """A source box whose document the erasure could not find by id."""


def document_ref_of(document_id: uuid.UUID) -> str:
    return f"{DOCUMENT_REF_PREFIX}{document_id}"


def document_id_of(document_ref: str) -> uuid.UUID:
    """The ``documents.id`` a ref names, or a refusal (no ref is echoed)."""
    if document_ref.startswith(DOCUMENT_REF_PREFIX):
        try:
            return uuid.UUID(document_ref.removeprefix(DOCUMENT_REF_PREFIX))
        except ValueError:
            pass
    raise UnaddressableDocumentRef(
        "an indexed item's source box names doc:<documents.id>; any other ref would put "
        "its vector out of the retention executor's reach"
    )


@dataclass(frozen=True, slots=True)
class RecordNamespace:
    """One patient's index. There is no shared one (files/10 §5 LLM08)."""

    tenant_id: uuid.UUID
    patient_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class RecordsConsent:
    """The live ``documents`` decision for one namespace.

    Built by :func:`records_consent` from the ledger. A decision for any other
    scope cannot be presented here, so a ``core`` grant cannot open the index.
    """

    namespace: RecordNamespace
    decision: ConsentDecision

    def __post_init__(self) -> None:
        if self.decision.scope != RECORDS_CONSENT_SCOPE:
            raise ValueError(
                f"the record index runs under the {RECORDS_CONSENT_SCOPE!r} purpose; a "
                "decision for another scope decides nothing here"
            )

    def require(self) -> RecordNamespace:
        """The namespace, if the decision stands; otherwise a refusal."""
        if not self.decision.allowed:
            raise RecordsConsentRefused()
        return self.namespace


async def records_consent(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    catalog: ConsentTextCatalog,
) -> RecordsConsent:
    """Read the decision from the consent ledger — the guard's own question."""
    decision = await consent_state(
        session,
        tenant_id=tenant_id,
        patient_id=patient_id,
        scope=RECORDS_CONSENT_SCOPE,
        catalog=catalog,
    )
    return RecordsConsent(
        namespace=RecordNamespace(tenant_id=tenant_id, patient_id=patient_id), decision=decision
    )


def item_ref_of(item: ConfirmedRecordItem) -> str:
    """The item's id: derived from its source box and kind, never minted.

    Confirming the same line twice yields the same id, so a re-admission is one
    row, not two — the files/12 §7.5 reasoning for ``work_id``.
    """
    box = item.observation.box
    material = "\x00".join(
        (
            box.document_ref,
            str(box.page),
            ",".join(repr(value) for value in box.bbox),
            str(box.start),
            str(box.end),
            item.observation.kind.value,
        )
    )
    return f"ri_{hashlib.sha256(material.encode('utf-8')).hexdigest()[:32]}"


def index_text_of(item: ConfirmedRecordItem) -> str:
    """What is embedded: the line the patient confirmed, verbatim, and nothing else."""
    return item.observation.summary


@dataclass(frozen=True, slots=True)
class IndexEntry:
    """One row of ``record_embeddings``. No field carries the item's text."""

    namespace: RecordNamespace
    item_ref: str
    document_ref: str
    page: int
    bbox: tuple[float, float, float, float]
    char_start: int
    char_end: int
    kind: RecordItemKind
    model_ref: str
    vector: tuple[float, ...]
    consent_scope_ref: str

    def __post_init__(self) -> None:
        document_id_of(self.document_ref)


@dataclass(frozen=True, slots=True)
class IndexHit:
    """One nearest row, as the store returns it: provenance and a distance."""

    item_ref: str
    document_ref: str
    page: int
    bbox: tuple[float, float, float, float]
    char_start: int
    char_end: int
    kind: RecordItemKind
    distance: float


class RecordIndexStore(Protocol):
    """Where entries live. Every member is scoped to one namespace."""

    def write(self, entry: IndexEntry) -> None: ...

    def nearest(
        self,
        namespace: RecordNamespace,
        *,
        model_ref: str,
        vector: Sequence[float],
        k: int,
    ) -> tuple[IndexHit, ...]: ...

    def erase(self, namespace: RecordNamespace) -> int: ...


class IndexState(enum.StrEnum):
    QUEUED = "queued"
    INDEXED = "indexed"
    FAILED = "failed"
    REFUSED = "refused"


@dataclass
class IndexReceipt:
    """A delivery receipt: an id, a closed state and an error class name."""

    item_ref: str
    state: IndexState
    error: str | None = None


@dataclass(frozen=True, slots=True)
class _IndexWork:
    namespace: RecordNamespace
    item: ConfirmedRecordItem
    receipt: IndexReceipt


@dataclass
class RecordIndexQueue:
    """FIFO of confirmed items waiting to be embedded, and the pump that runs it."""

    embedder: RecordEmbedder
    store: RecordIndexStore
    _pending: deque[_IndexWork] = field(default_factory=deque, init=False, repr=False)
    _receipts: list[IndexReceipt] = field(default_factory=list, init=False, repr=False)

    def enqueue(self, consent: RecordsConsent, item: ConfirmedRecordItem) -> str:
        """Hold one confirmed item for the pump. Runs nothing; returns its id."""
        if not isinstance(item, ConfirmedRecordItem):
            raise RecordExtractionError(
                "only a confirmed record item is indexed; an extraction nobody looked at "
                "is not retrievable into a note (files/03 §4.6)"
            )
        item_ref = item_ref_of(item)
        try:
            namespace = consent.require()
        except RecordsConsentRefused as refused:
            self._receipts.append(
                IndexReceipt(
                    item_ref=item_ref, state=IndexState.REFUSED, error=type(refused).__name__
                )
            )
            return item_ref
        receipt = IndexReceipt(item_ref=item_ref, state=IndexState.QUEUED)
        self._pending.append(_IndexWork(namespace=namespace, item=item, receipt=receipt))
        self._receipts.append(receipt)
        return item_ref

    def run_pending(self) -> int:
        """Embed and write every queued item. Returns how many were attempted."""
        ran = 0
        while self._pending:
            work = self._pending.popleft()
            ran += 1
            receipt = work.receipt
            try:
                self.store.write(self._entry(work))
            except Exception as err:  # a refusal is a receipt, not a crashed pump
                receipt.state = IndexState.FAILED
                receipt.error = type(err).__name__
            else:
                receipt.state = IndexState.INDEXED
        return ran

    @property
    def receipts(self) -> tuple[IndexReceipt, ...]:
        return tuple(self._receipts)

    def _entry(self, work: _IndexWork) -> IndexEntry:
        box = work.item.observation.box
        document_id_of(box.document_ref)
        model_ref = pinned_model_ref(self.embedder)
        (vector,) = embed_checked(self.embedder, [index_text_of(work.item)])
        return IndexEntry(
            namespace=work.namespace,
            item_ref=work.receipt.item_ref,
            document_ref=box.document_ref,
            page=box.page,
            bbox=box.bbox,
            char_start=box.start,
            char_end=box.end,
            kind=work.item.observation.kind,
            model_ref=model_ref,
            vector=vector,
            consent_scope_ref=f"scope:{RECORDS_CONSENT_SCOPE}",
        )

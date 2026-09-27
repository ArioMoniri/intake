"""INT-123 — the record index and the retrieval Work, platform half.

Acceptance, verbatim (docs/backlog/issues.yaml): *"embeddings scoped by
patient+consent; retrieval cited into notes with provenance"*. This file
covers the parts that do not need Postgres; tests/records/test_vector_rls.py
holds the schema, the RLS policy and the erasure contract, and
tests/voice/test_retrieve_records_work.py the note side.

1. **No embedding model is registered, and that is refused, not faked.**
   files/03 §4.9.1 is canonical and names no record-embedding row (row 18 is a
   *speaker* embedding, ephemeral by invariant 15, and is not one). The default
   embedder refuses every call, and the table check below fails the day a row
   appears, so the fail-closed default cannot outlive the decision.
2. **Only confirmed items are embedded.** The index queue takes
   :class:`~clinical_schemas.record_extraction.ConfirmedRecordItem` and nothing
   else, and :class:`~intake_platform.records.ConfirmedRecordStore` enqueues on
   admission — so an extraction nobody confirmed has no path into the index.
3. **Consent scope.** Indexing and retrieval both require a live ``documents``
   decision for the same patient (invariant 4); a withdrawn, absent, foreign or
   off-scope decision is refused.
4. **Provenance.** A retrieval returns document ref, page, bbox, character span
   and the derived item id — and a hit whose stored box disagrees with the
   confirmed item is refused rather than cited.

The vectors below are fixtures in the test tree (no model runs here; nothing
calls a network). Every Turkish string is a synthetic document line.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import math
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import pytest
from clinical_schemas.overlay import Confirmation, LearnedFactSource
from clinical_schemas.record_extraction import (
    ConfirmedRecordItem,
    RecordExtractionError,
    SourceBox,
    UnconfirmedRecordItem,
    confirm_record_item,
)
from clinical_schemas.records import RecordItemKind
from intake_platform.consent import ConsentDecision, ConsentTextCatalog
from intake_platform.db.models import Base, Consent, KvkkRole, Patient, Tenant
from intake_platform.records import ConfirmedRecordStore
from intake_platform.records.embedding import (
    RECORD_EMBEDDING_ROW,
    EmbeddingModelUnpinned,
    EmbeddingModelUnregistered,
    EmbeddingShapeRefused,
    NoEmbeddingModel,
    default_record_embedder,
    embed_checked,
    pinned_model_ref,
)
from intake_platform.records.index import (
    RECORDS_CONSENT_SCOPE,
    IndexEntry,
    IndexHit,
    IndexState,
    RecordIndexQueue,
    RecordNamespace,
    RecordsConsent,
    RecordsConsentRefused,
    UnaddressableDocumentRef,
    document_id_of,
    document_ref_of,
    item_ref_of,
    records_consent,
)
from intake_platform.records.retrieval import (
    IndexProvenanceMismatch,
    RecordRetriever,
)
from sqlalchemy import JSON, MetaData
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

REPO = Path(__file__).resolve().parents[2]
AT = dt.datetime(2026, 9, 20, 9, 30, tzinfo=dt.UTC)
TENANT = uuid.UUID("00000000-0000-4000-8000-000000000123")
PATIENT_A = uuid.UUID("00000000-0000-4000-8000-0000000000aa")
PATIENT_B = uuid.UUID("00000000-0000-4000-8000-0000000000bb")
DOC_1 = uuid.UUID("00000000-0000-4000-8000-00000000d001")
DOC_2 = uuid.UUID("00000000-0000-4000-8000-00000000d002")
MODEL_REF = "fixture/recorded-embedder@0123456789abcdef0123456789abcdef01234567"

NS_A = RecordNamespace(tenant_id=TENANT, patient_id=PATIENT_A)
NS_B = RecordNamespace(tenant_id=TENANT, patient_id=PATIENT_B)


def _decision(allowed: bool = True, *, scope: str = RECORDS_CONSENT_SCOPE) -> ConsentDecision:
    return ConsentDecision(
        scope=scope,
        purpose=scope,
        allowed=allowed,
        reason="granted" if allowed else "withdrawn",
    )


def _consent(namespace: RecordNamespace = NS_A, *, allowed: bool = True) -> RecordsConsent:
    return RecordsConsent(namespace=namespace, decision=_decision(allowed))


def _observation(
    *,
    summary: str = "Hemoglobin 10,2 g/dL",
    document: uuid.UUID = DOC_1,
    page: int = 1,
    bbox: tuple[float, float, float, float] = (0.10, 0.20, 0.60, 0.24),
    start: int = 0,
    end: int = 15,
    kind: RecordItemKind = RecordItemKind.LAB,
) -> UnconfirmedRecordItem:
    return UnconfirmedRecordItem(
        kind=kind,
        summary=summary,
        box=SourceBox(
            document_ref=document_ref_of(document), page=page, bbox=bbox, start=start, end=end
        ),
        observed_at=AT,
        value_magnitude=Decimal("10.2") if kind is RecordItemKind.LAB else None,
        unit="g/dL" if kind is RecordItemKind.LAB else None,
    )


HEMOGLOBIN = confirm_record_item(_observation(), at=AT)
CREATININE = confirm_record_item(
    _observation(summary="Kreatinin 0,9 mg/dL", page=2, start=40, end=60), at=AT
)
CHEST_XRAY = confirm_record_item(
    _observation(
        summary="Akciğer grafisi olağan",
        document=DOC_2,
        kind=RecordItemKind.IMAGING,
        start=0,
        end=22,
    ),
    at=AT,
)

#: Recorded vectors — fixture data, never a model output computed here.
RECORDED: dict[str, tuple[float, ...]] = {
    HEMOGLOBIN.observation.summary: (1.0, 0.0, 0.0),
    CREATININE.observation.summary: (0.0, 1.0, 0.0),
    CHEST_XRAY.observation.summary: (0.0, 0.0, 1.0),
    "kansızlık tahlili": (0.9, 0.1, 0.0),
    "böbrek değeri": (0.1, 0.9, 0.0),
}


@dataclass
class RecordedEmbedder:
    """Returns committed fixture vectors; an unknown text is a test bug."""

    model_ref: str = MODEL_REF
    dimensions: int = 3
    calls: list[tuple[str, ...]] = field(default_factory=list)

    def embed(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        self.calls.append(tuple(texts))
        return tuple(RECORDED[text] for text in texts)


def _cosine_distance(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return 1.0 - dot / norm


@dataclass
class FakeIndexStore:
    """A test double of :class:`~intake_platform.records.index.RecordIndexStore`.

    It namespaces exactly as the Postgres store is required to — every read is
    one patient's rows — so a retriever that asked for the wrong namespace would
    get nothing back here too. The live proof is RLS, in test_vector_rls.py.
    """

    rows: list[IndexEntry] = field(default_factory=list)

    def write(self, entry: IndexEntry) -> None:
        self.rows = [
            row
            for row in self.rows
            if (row.namespace, row.item_ref, row.model_ref)
            != (entry.namespace, entry.item_ref, entry.model_ref)
        ]
        self.rows.append(entry)

    def nearest(
        self,
        namespace: RecordNamespace,
        *,
        model_ref: str,
        vector: Sequence[float],
        k: int,
    ) -> tuple[IndexHit, ...]:
        mine = [row for row in self.rows if row.namespace == namespace]
        mine = [row for row in mine if row.model_ref == model_ref]
        ranked = sorted(mine, key=lambda row: _cosine_distance(row.vector, vector))
        return tuple(
            IndexHit(
                item_ref=row.item_ref,
                document_ref=row.document_ref,
                page=row.page,
                bbox=row.bbox,
                char_start=row.char_start,
                char_end=row.char_end,
                kind=row.kind,
                distance=_cosine_distance(row.vector, vector),
            )
            for row in ranked[:k]
        )

    def erase(self, namespace: RecordNamespace) -> int:
        before = len(self.rows)
        self.rows = [row for row in self.rows if row.namespace != namespace]
        return before - len(self.rows)


def _indexed(
    *items: ConfirmedRecordItem, namespace: RecordNamespace = NS_A
) -> tuple[FakeIndexStore, ConfirmedRecordStore, RecordedEmbedder]:
    store = FakeIndexStore()
    embedder = RecordedEmbedder()
    queue = RecordIndexQueue(embedder=embedder, store=store)
    consent = _consent(namespace)
    records = ConfirmedRecordStore(on_admit=lambda item: queue.enqueue(consent, item))
    for item in items:
        records.admit(item)
    queue.run_pending()
    return store, records, embedder


# --- 1. no embedding model is registered --------------------------------------------


def _stack_rows() -> list[tuple[str, str]]:
    """``(row, layer)`` for every row of the files/03 §4.9.1 table."""
    text = (REPO / "files" / "03_ARCHITECTURE.md").read_text(encoding="utf-8")
    section = text.split("### 4.9.1 The stack", 1)[1].split("### 4.9.2", 1)[0]
    rows: list[tuple[str, str]] = []
    for line in section.splitlines():
        cells = [cell.strip() for cell in line.split("|")]
        if len(cells) > 3 and re.fullmatch(r"\d+", cells[1]):
            rows.append((cells[1], cells[2]))
    return rows


def _record_embedding_rows(rows: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Rows that could pin a record/text embedder. A *speaker* embedding is not
    one: it is biometric, ephemeral and never persisted (invariant 15)."""
    return [
        (number, layer)
        for number, layer in rows
        if "embedding" in layer.casefold() and "speaker" not in layer.casefold()
    ]


class TestNoEmbeddingModelIsRegistered:
    def test_the_canonical_table_is_read_and_names_no_record_embedder(self) -> None:
        rows = _stack_rows()
        assert len(rows) >= 21, "the §4.9.1 table was not found or lost rows"
        assert ("18", "Speaker embedding") in rows, "the near-miss row must be seen"
        assert _record_embedding_rows(rows) == [], (
            "files/03 §4.9.1 now names a record embedder: pin it in "
            "observability/registry.yaml (model_id@revision + sha256 + licence_verified_at "
            "from the raw LICENSE blob), set RECORD_EMBEDDING_ROW and replace NoEmbeddingModel"
        )
        assert RECORD_EMBEDDING_ROW is None

    def test_near_miss_a_record_embedding_row_would_be_detected(self) -> None:
        planted = [*_stack_rows(), ("22", "**Record embedding**")]
        assert _record_embedding_rows(planted) == [("22", "**Record embedding**")]

    def test_the_default_embedder_refuses_every_use(self) -> None:
        embedder = default_record_embedder()
        assert isinstance(embedder, NoEmbeddingModel)
        with pytest.raises(EmbeddingModelUnregistered, match="4.9.1"):
            embedder.embed(["herhangi bir metin"])
        with pytest.raises(EmbeddingModelUnregistered):
            _ = embedder.model_ref
        with pytest.raises(EmbeddingModelUnregistered):
            _ = embedder.dimensions

    def test_the_refusal_echoes_no_text(self) -> None:
        with pytest.raises(EmbeddingModelUnregistered) as refused:
            default_record_embedder().embed(["Hemoglobin 10,2"])
        assert "Hemoglobin" not in str(refused.value)

    def test_an_unpinned_embedder_is_refused(self) -> None:
        for ref in ("fixture/recorded-embedder", "fixture/recorded-embedder@main", "@abcdef0"):
            with pytest.raises(EmbeddingModelUnpinned):
                pinned_model_ref(RecordedEmbedder(model_ref=ref))
        with pytest.raises(EmbeddingModelUnpinned):
            pinned_model_ref(RecordedEmbedder(dimensions=0))
        assert pinned_model_ref(RecordedEmbedder()) == MODEL_REF

    def test_a_vector_of_the_wrong_shape_is_refused(self) -> None:
        class Short(RecordedEmbedder):
            def embed(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
                return tuple((1.0, 0.0) for _ in texts)

        class NotFinite(RecordedEmbedder):
            def embed(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
                return tuple((math.nan, 0.0, 0.0) for _ in texts)

        class Missing(RecordedEmbedder):
            def embed(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
                return ()

        text = HEMOGLOBIN.observation.summary
        for bad in (Short(), NotFinite(), Missing()):
            with pytest.raises(EmbeddingShapeRefused):
                embed_checked(bad, [text])
        assert embed_checked(RecordedEmbedder(), [text]) == ((1.0, 0.0, 0.0),)

    def test_the_default_queue_indexes_nothing_and_says_why(self) -> None:
        store = FakeIndexStore()
        queue = RecordIndexQueue(embedder=default_record_embedder(), store=store)
        queue.enqueue(_consent(), HEMOGLOBIN)
        assert queue.run_pending() == 1
        (receipt,) = queue.receipts
        assert receipt.state is IndexState.FAILED
        assert receipt.error == "EmbeddingModelUnregistered"
        assert store.rows == []

    def test_retrieval_without_a_model_refuses_rather_than_returning_nothing(self) -> None:
        store, records, _ = _indexed(HEMOGLOBIN)
        retriever = RecordRetriever(
            embedder=default_record_embedder(), store=store, records=records
        )
        with pytest.raises(EmbeddingModelUnregistered):
            retriever.retrieve(_consent(), "kansızlık tahlili", k=3)


# --- 2. only confirmed items are embedded ---------------------------------------------


class TestOnlyConfirmedItemsAreIndexed:
    def test_admission_enqueues_and_the_pump_writes_one_row_per_item(self) -> None:
        store, _, embedder = _indexed(HEMOGLOBIN, CREATININE)
        assert [row.item_ref for row in store.rows] == [
            item_ref_of(HEMOGLOBIN),
            item_ref_of(CREATININE),
        ]
        # what is embedded is exactly what the patient confirmed, verbatim
        assert embedder.calls == [
            (HEMOGLOBIN.observation.summary,),
            (CREATININE.observation.summary,),
        ]

    def test_an_unconfirmed_item_cannot_be_enqueued(self) -> None:
        queue = RecordIndexQueue(embedder=RecordedEmbedder(), store=FakeIndexStore())
        with pytest.raises(RecordExtractionError):
            queue.enqueue(_consent(), _observation())  # type: ignore[arg-type]
        assert queue.receipts == ()

    def test_an_unconfirmed_item_never_reaches_the_hook(self) -> None:
        enqueued: list[ConfirmedRecordItem] = []
        records = ConfirmedRecordStore(on_admit=enqueued.append)
        with pytest.raises(RecordExtractionError):
            records.admit(_observation())  # type: ignore[arg-type]
        assert enqueued == []
        records.admit(HEMOGLOBIN)
        assert enqueued == [HEMOGLOBIN]

    def test_an_item_declined_by_the_patient_is_never_embedded(self) -> None:
        """A declined card is never confirmed, so it is never admitted: the
        store holds the one the patient agreed with and the index holds the
        same one, nothing more."""
        store, records, embedder = _indexed(HEMOGLOBIN)
        declined = _observation(summary="Kreatinin 0,9 mg/dL", page=2, start=40, end=60)
        assert records.admitted == (HEMOGLOBIN,)
        assert [row.item_ref for row in store.rows] == [item_ref_of(HEMOGLOBIN)]
        assert declined.summary not in {text for call in embedder.calls for text in call}

    def test_the_row_carries_the_item_box_and_nothing_else_of_the_item(self) -> None:
        store, _, _ = _indexed(HEMOGLOBIN)
        (row,) = store.rows
        box = HEMOGLOBIN.observation.box
        assert (row.document_ref, row.page, row.bbox, row.char_start, row.char_end) == (
            box.document_ref,
            box.page,
            box.bbox,
            box.start,
            box.end,
        )
        assert row.kind is RecordItemKind.LAB
        assert row.model_ref == MODEL_REF
        assert row.consent_scope_ref == f"scope:{RECORDS_CONSENT_SCOPE}"
        # the summary text is not a column of the index: the source of truth is
        # the confirmed item, and a vector is all the index holds of it
        assert HEMOGLOBIN.observation.summary not in repr(row)

    def test_the_item_id_is_derived_from_the_box_so_a_re_admission_is_one_row(self) -> None:
        again = confirm_record_item(_observation(), at=AT + dt.timedelta(minutes=5))
        assert item_ref_of(again) == item_ref_of(HEMOGLOBIN)
        store, _, _ = _indexed(HEMOGLOBIN, again)
        assert len(store.rows) == 1
        assert re.fullmatch(r"ri_[0-9a-f]{32}", item_ref_of(HEMOGLOBIN))
        assert item_ref_of(CREATININE) != item_ref_of(HEMOGLOBIN)

    def test_a_receipt_is_ids_and_closed_states_only(self) -> None:
        queue = RecordIndexQueue(embedder=RecordedEmbedder(), store=FakeIndexStore())
        queue.enqueue(_consent(), HEMOGLOBIN)
        (queued,) = queue.receipts
        assert queued.state is IndexState.QUEUED
        queue.run_pending()
        (done,) = queue.receipts
        assert done.state is IndexState.INDEXED and done.error is None
        assert HEMOGLOBIN.observation.summary not in repr(done)
        assert queue.run_pending() == 0

    def test_a_document_ref_the_erasure_cannot_address_is_never_written(self) -> None:
        """Every row is reachable by the per-document erasure, which finds rows
        by ``doc:<documents.id>``; a box pointing anywhere else is refused."""
        odd = UnconfirmedRecordItem(
            kind=RecordItemKind.LAB,
            summary=HEMOGLOBIN.observation.summary,
            box=SourceBox(
                document_ref="document:doc-1", page=1, bbox=(0.1, 0.2, 0.6, 0.24), start=0, end=5
            ),
            observed_at=AT,
        )
        queue = RecordIndexQueue(embedder=RecordedEmbedder(), store=FakeIndexStore())
        queue.enqueue(_consent(), confirm_record_item(odd, at=AT))
        queue.run_pending()
        (receipt,) = queue.receipts
        assert receipt.state is IndexState.FAILED
        assert receipt.error == "UnaddressableDocumentRef"
        with pytest.raises(UnaddressableDocumentRef):
            document_id_of("document:doc-1")
        with pytest.raises(UnaddressableDocumentRef):
            document_id_of("doc:not-a-uuid")
        assert document_id_of(document_ref_of(DOC_1)) == DOC_1

    def test_an_entry_built_around_the_queue_is_refused_too(self) -> None:
        """A writer that skipped the queue still cannot build an unaddressable row."""
        with pytest.raises(UnaddressableDocumentRef):
            IndexEntry(
                namespace=NS_A,
                item_ref=item_ref_of(HEMOGLOBIN),
                document_ref="document:doc-1",
                page=1,
                bbox=(0.1, 0.2, 0.6, 0.24),
                char_start=0,
                char_end=5,
                kind=RecordItemKind.LAB,
                model_ref=MODEL_REF,
                vector=(1.0, 0.0, 0.0),
                consent_scope_ref=f"scope:{RECORDS_CONSENT_SCOPE}",
            )


# --- 3. consent scope ------------------------------------------------------------------


class TestConsentScope:
    def test_indexing_without_a_live_documents_decision_is_refused(self) -> None:
        store = FakeIndexStore()
        queue = RecordIndexQueue(embedder=RecordedEmbedder(), store=store)
        queue.enqueue(_consent(allowed=False), HEMOGLOBIN)
        (receipt,) = queue.receipts
        assert receipt.state is IndexState.REFUSED
        assert receipt.error == "RecordsConsentRefused"
        assert queue.run_pending() == 0
        assert store.rows == []

    def test_retrieval_without_a_live_documents_decision_is_refused(self) -> None:
        store, records, embedder = _indexed(HEMOGLOBIN)
        calls_before = len(embedder.calls)
        retriever = RecordRetriever(embedder=embedder, store=store, records=records)
        with pytest.raises(RecordsConsentRefused) as refused:
            retriever.retrieve(_consent(allowed=False), "kansızlık tahlili", k=3)
        # refused before the query text reached any model, and the refusal
        # names the scope and nothing else (invariant 6)
        assert len(embedder.calls) == calls_before
        assert str(refused.value) == f"consent scope {RECORDS_CONSENT_SCOPE!r} does not stand"

    def test_a_decision_for_another_scope_cannot_be_presented(self) -> None:
        with pytest.raises(ValueError, match="documents"):
            RecordsConsent(namespace=NS_A, decision=_decision(scope="core"))

    def test_one_patients_consent_opens_only_their_own_namespace(self) -> None:
        store, records, embedder = _indexed(HEMOGLOBIN, namespace=NS_A)
        retriever = RecordRetriever(embedder=embedder, store=store, records=records)
        found = retriever.retrieve(_consent(NS_B), "kansızlık tahlili", k=3)
        assert found.citations == ()

    def test_the_decision_is_read_from_the_consent_ledger(self, tmp_path: Path) -> None:
        catalog = ConsentTextCatalog(tmp_path)

        async def decide(patient: uuid.UUID) -> RecordsConsent:
            engine = create_async_engine(
                f"sqlite+aiosqlite:///{tmp_path / 'int123.db'}", poolclass=NullPool
            )
            try:
                async with engine.begin() as conn:
                    await conn.run_sync(_sqlite_metadata().create_all)
                async with AsyncSession(engine) as session, session.begin():
                    if await session.get(Tenant, TENANT) is None:
                        session.add(
                            Tenant(
                                id=TENANT,
                                display_name="t",
                                kvkk_role=KvkkRole.PROCESSOR,
                                created_at=AT,
                            )
                        )
                        await session.flush()
                        for pid in (PATIENT_A, PATIENT_B):
                            session.add(
                                Patient(
                                    id=pid, tenant_id=TENANT, pseudonym=f"k1.{pid}", created_at=AT
                                )
                            )
                        await session.flush()
                        session.add(
                            Consent(
                                tenant_id=TENANT,
                                patient_id=PATIENT_A,
                                scope=RECORDS_CONSENT_SCOPE,
                                version="1",
                                granted_at=AT,
                            )
                        )
                    return await records_consent(
                        session, tenant_id=TENANT, patient_id=patient, catalog=catalog
                    )
            finally:
                await engine.dispose()

        granted = asyncio.run(decide(PATIENT_A))
        absent = asyncio.run(decide(PATIENT_B))
        assert granted.namespace == NS_A and granted.decision.allowed
        assert absent.namespace == NS_B and not absent.decision.allowed
        with pytest.raises(RecordsConsentRefused):
            absent.require()


def _sqlite_metadata() -> MetaData:
    clone = MetaData()
    for table in Base.metadata.sorted_tables:
        copied = table.to_metadata(clone)
        for column in copied.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()
            column.server_default = None
    return clone


# --- 4. retrieval returns provenance ----------------------------------------------------


class TestRetrievalCarriesProvenance:
    def test_the_nearest_confirmed_items_come_back_with_their_boxes(self) -> None:
        store, records, embedder = _indexed(HEMOGLOBIN, CREATININE, CHEST_XRAY)
        retriever = RecordRetriever(embedder=embedder, store=store, records=records)
        found = retriever.retrieve(_consent(), "kansızlık tahlili", k=2)
        assert [c.item_ref for c in found.citations] == [
            item_ref_of(HEMOGLOBIN),
            item_ref_of(CREATININE),
        ]
        first = found.citations[0]
        box = HEMOGLOBIN.observation.box
        assert first.provenance == (box.document_ref, box.page, box.bbox, item_ref_of(HEMOGLOBIN))
        assert (first.char_start, first.char_end) == (box.start, box.end)
        assert first.item is HEMOGLOBIN
        assert found.citations[0].distance < found.citations[1].distance
        assert found.uncited == ()

    def test_k_is_bounded(self) -> None:
        store, records, embedder = _indexed(HEMOGLOBIN)
        retriever = RecordRetriever(embedder=embedder, store=store, records=records)
        for k in (0, -1, 51):
            with pytest.raises(ValueError, match="k"):
                retriever.retrieve(_consent(), "kansızlık tahlili", k=k)

    def test_a_hit_whose_item_is_no_longer_confirmed_is_reported_not_cited(self) -> None:
        store, _, embedder = _indexed(HEMOGLOBIN, CREATININE)
        only_one = ConfirmedRecordStore()
        only_one.admit(CREATININE)
        retriever = RecordRetriever(embedder=embedder, store=store, records=only_one)
        found = retriever.retrieve(_consent(), "kansızlık tahlili", k=2)
        assert [c.item_ref for c in found.citations] == [item_ref_of(CREATININE)]
        assert found.uncited == (item_ref_of(HEMOGLOBIN),)

    def test_a_hit_whose_stored_box_disagrees_with_the_item_is_refused(self) -> None:
        store, records, embedder = _indexed(HEMOGLOBIN)
        (row,) = store.rows
        store.rows = [
            IndexEntry(
                namespace=row.namespace,
                item_ref=row.item_ref,
                document_ref=row.document_ref,
                page=row.page + 1,
                bbox=row.bbox,
                char_start=row.char_start,
                char_end=row.char_end,
                kind=row.kind,
                model_ref=row.model_ref,
                vector=row.vector,
                consent_scope_ref=row.consent_scope_ref,
            )
        ]
        retriever = RecordRetriever(embedder=embedder, store=store, records=records)
        with pytest.raises(IndexProvenanceMismatch):
            retriever.retrieve(_consent(), "kansızlık tahlili", k=1)

    def test_a_row_written_by_another_model_is_not_compared(self) -> None:
        store, records, _ = _indexed(HEMOGLOBIN)
        other = RecordedEmbedder(
            model_ref="fixture/other-embedder@fedcba9876543210fedcba9876543210fedcba98"
        )
        retriever = RecordRetriever(embedder=other, store=store, records=records)
        assert retriever.retrieve(_consent(), "kansızlık tahlili", k=3).citations == ()


# --- the confirm bridge still holds -------------------------------------------------------


def test_a_confirmation_for_another_document_still_cannot_be_built() -> None:
    with pytest.raises(RecordExtractionError):
        ConfirmedRecordItem(
            observation=_observation(),
            confirmation=Confirmation(
                source=LearnedFactSource.CONFIRMED_IMPORTED_RECORD,
                source_ref=document_ref_of(DOC_2),
                confirmed_at=AT,
            ),
        )

"""INT-123 — ``retrieve_records``: the retrieval Work, and its citations in the note.

files/12 §7.4 puts ``retrieve_records`` in the **background** lane: concurrent,
handed a ``ReadOnlyContext`` with no mutator, and returning a
``BackgroundEffect`` that cannot express a slot write or a triage level. This
file holds the Work to that and to the second half of the INT-123 acceptance —
*"retrieval cited into notes with provenance"*:

- the Work type exists, runs in the background lane, and shows the rail the
  label reading a document already has (no new patient-visible string);
- unregistered, it is refused at submit — the fail-closed state while
  files/03 §4.9.1 names no embedding model;
- registered, it cites the patient's confirmed items, and the note composer
  files each one under ``imported_objective`` with a document span carrying
  document ref, page, bbox **and item id**;
- a refused consent, a missing model or a cancellation cites nothing, and a
  retrieval speaks nothing.

Vectors are fixtures; no model runs. Every Turkish string is a synthetic
document line.
"""

from __future__ import annotations

import datetime as dt
import math
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal

import pytest
from clinical_schemas.note import NoteMeta, ScreeningBlock, ScreeningProvenance
from clinical_schemas.record_extraction import (
    ConfirmedRecordItem,
    SourceBox,
    UnconfirmedRecordItem,
    confirm_record_item,
)
from clinical_schemas.records import RecordItemKind
from clinical_schemas.triage import RulesTriageResult, TriageLevel
from intake_platform.consent import ConsentDecision
from intake_platform.records import ConfirmedRecordStore
from intake_platform.records.embedding import RecordEmbedder, default_record_embedder
from intake_platform.records.index import (
    RECORDS_CONSENT_SCOPE,
    IndexEntry,
    IndexHit,
    RecordIndexQueue,
    RecordNamespace,
    RecordsConsent,
    document_ref_of,
    item_ref_of,
)
from intake_platform.records.retrieval import RecordRetriever, Retrieval
from intake_voice_runtime.clinical_agent import IntakeEngine
from intake_voice_runtime.clinical_agent.record_retrieval import (
    RetrieveRecordsHandler,
    register_retrieve_records,
)
from intake_voice_runtime.clinical_agent.work_queue import (
    LANE_OF,
    BackendAgent,
    UnregisteredWorkType,
    WorkLane,
)
from intake_voice_runtime.note import compose, facts_by_section
from intake_voice_runtime.note.citations import cite_records
from intake_voice_runtime.note.facts import Attribution, SourceKind, SourceSpan
from intake_voice_runtime.ports import WorkRequest, WorkState, WorkType
from intake_voice_runtime.talker.activity import ACTIVITY_OF, ActivityLabel
from intake_voice_runtime.transcript import SessionTranscripts
from protocols.compile.resolve import ResolvedProtocol, ResolvedSection, ResolvedSlot
from protocols.dsl import Slot
from protocols.locale_text import DEFAULT_LOCALE as TR
from protocols.types import Delivery, SlotType

AT = dt.datetime(2026, 9, 20, 9, 30, tzinfo=dt.UTC)
SESSION = "11111111-2222-4333-8444-555555555123"
HASH = "0" * 64
TENANT = uuid.UUID("00000000-0000-4000-8000-000000000123")
PATIENT = uuid.UUID("00000000-0000-4000-8000-0000000000aa")
DOC = uuid.UUID("00000000-0000-4000-8000-00000000d001")
NS = RecordNamespace(tenant_id=TENANT, patient_id=PATIENT)
MODEL_REF = "fixture/recorded-embedder@0123456789abcdef0123456789abcdef01234567"
QUERY = "kansızlık tahlili"


def _consent(allowed: bool = True) -> RecordsConsent:
    return RecordsConsent(
        namespace=NS,
        decision=ConsentDecision(
            scope=RECORDS_CONSENT_SCOPE,
            purpose=RECORDS_CONSENT_SCOPE,
            allowed=allowed,
            reason="granted" if allowed else "withdrawn",
        ),
    )


def _confirmed(
    summary: str, *, kind: RecordItemKind, page: int, start: int, end: int
) -> ConfirmedRecordItem:
    return confirm_record_item(
        UnconfirmedRecordItem(
            kind=kind,
            summary=summary,
            box=SourceBox(
                document_ref=document_ref_of(DOC),
                page=page,
                bbox=(0.10, 0.20 + page / 10, 0.60, 0.24 + page / 10),
                start=start,
                end=end,
            ),
            observed_at=AT,
            value_magnitude=Decimal("10.2") if kind is RecordItemKind.LAB else None,
            unit="g/dL" if kind is RecordItemKind.LAB else None,
            date=dt.date(2026, 9, 1),
        ),
        at=AT,
    )


HEMOGLOBIN = _confirmed("Hemoglobin 10,2 g/dL", kind=RecordItemKind.LAB, page=1, start=0, end=15)
DIAGNOSIS = _confirmed("Demir eksikliği", kind=RecordItemKind.DIAGNOSIS, page=2, start=0, end=15)

RECORDED: dict[str, tuple[float, ...]] = {
    "Hemoglobin 10,2 g/dL": (1.0, 0.0),
    "Demir eksikliği": (0.8, 0.6),
    QUERY: (0.9, 0.1),
}


@dataclass
class RecordedEmbedder:
    model_ref: str = MODEL_REF
    dimensions: int = 2

    def embed(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        return tuple(RECORDED[text] for text in texts)


def _distance(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return 1.0 - dot / (math.hypot(*a) * math.hypot(*b))


@dataclass
class FakeIndexStore:
    rows: list[IndexEntry] = field(default_factory=list)

    def write(self, entry: IndexEntry) -> None:
        self.rows.append(entry)

    def nearest(
        self, namespace: RecordNamespace, *, model_ref: str, vector: Sequence[float], k: int
    ) -> tuple[IndexHit, ...]:
        mine = [r for r in self.rows if r.namespace == namespace and r.model_ref == model_ref]
        mine.sort(key=lambda r: _distance(r.vector, vector))
        return tuple(
            IndexHit(
                item_ref=r.item_ref,
                document_ref=r.document_ref,
                page=r.page,
                bbox=r.bbox,
                char_start=r.char_start,
                char_end=r.char_end,
                kind=r.kind,
                distance=_distance(r.vector, vector),
            )
            for r in mine[:k]
        )

    def erase(self, namespace: RecordNamespace) -> int:
        before = len(self.rows)
        self.rows = [r for r in self.rows if r.namespace != namespace]
        return before - len(self.rows)


def _retriever(*, embedder: RecordEmbedder | None = None) -> RecordRetriever:
    store = FakeIndexStore()
    recorded = RecordedEmbedder()
    queue = RecordIndexQueue(embedder=recorded, store=store)
    records = ConfirmedRecordStore(on_admit=lambda item: queue.enqueue(_consent(), item))
    records.admit(HEMOGLOBIN)
    records.admit(DIAGNOSIS)
    queue.run_pending()
    return RecordRetriever(
        embedder=embedder if embedder is not None else recorded,
        store=store,
        records=records,
    )


def _agent() -> BackendAgent:
    slot = Slot.model_validate(
        {
            "type": SlotType.INTEGER,
            "ask_tr": {TR: "Sentetik soru."},
            "follow_up_tr": {TR: "Sentetik takip."},
        }
    )
    protocol = ResolvedProtocol(
        pack_id="base.sentetik_kayit",
        version="1.0.0",
        chain=("base.sentetik_kayit",),
        sections=(
            ResolvedSection(
                id="oyku",
                delivery=Delivery.VOICE,
                allow_paraphrase=False,
                slots=(
                    ResolvedSlot(
                        section_id="oyku",
                        key="tahlil",
                        fhir_link_id="oyku.tahlil",
                        slot=slot,
                        delivery=Delivery.VOICE,
                    ),
                ),
            ),
        ),
        resolved_protocol_hash=HASH,
    )
    return BackendAgent(
        session_id=SESSION, engine=IntakeEngine(protocol=protocol, reference_time=AT)
    )


def _request(input_hash: str) -> WorkRequest:
    return WorkRequest(
        session_id=SESSION,
        work_type=WorkType.RETRIEVE_RECORDS,
        step_id="oyku.tahlil",
        input_hash=input_hash,
        protocol_hash=HASH,
        engine_version=0,
    )


def _wired(
    *, consent: RecordsConsent | None = None, retriever: RecordRetriever | None = None
) -> tuple[BackendAgent, RetrieveRecordsHandler, SessionTranscripts]:
    agent = _agent()
    queries = SessionTranscripts()
    handler = RetrieveRecordsHandler(
        retriever=retriever or _retriever(), consent=consent or _consent(), queries=queries, k=2
    )
    register_retrieve_records(agent, handler)
    return agent, handler, queries


# --- the Work type -----------------------------------------------------------------------


class TestTheWorkType:
    def test_it_runs_in_the_background_lane(self) -> None:
        assert WorkType.RETRIEVE_RECORDS.value == "retrieve_records"
        assert LANE_OF[WorkType.RETRIEVE_RECORDS] is WorkLane.BACKGROUND

    def test_the_rail_says_what_reading_a_document_already_says(self) -> None:
        assert ACTIVITY_OF[WorkType.RETRIEVE_RECORDS] is ActivityLabel.READING_DOCUMENT
        assert set(ActivityLabel) == {
            ActivityLabel.EXTRACTING,
            ActivityLabel.PLANNING,
            ActivityLabel.READING_DOCUMENT,
        }

    def test_unregistered_it_is_refused_at_submit(self) -> None:
        with pytest.raises(UnregisteredWorkType):
            _agent().submit(_request("a" * 64))

    def test_it_cannot_be_bound_to_the_state_lane(self) -> None:
        agent = _agent()
        handler = RetrieveRecordsHandler(
            retriever=_retriever(), consent=_consent(), queries=SessionTranscripts()
        )
        with pytest.raises(ValueError, match="background"):
            agent.register_state(WorkType.RETRIEVE_RECORDS, handler)


# --- the Work, run -----------------------------------------------------------------------


class TestRetrievalIsCitedWithProvenance:
    def test_the_work_cites_confirmed_items_and_speaks_nothing(self) -> None:
        agent, handler, queries = _wired()
        ticket = agent.submit(_request(queries.deposit(QUERY)))
        assert agent.run_pending() == 1
        (result,) = agent.drain_results()
        assert result.work_id == ticket.work_id and result.state is WorkState.COMPLETED
        assert result.presentation.speech_tr is None
        assert result.presentation.triage_update is None
        assert [c.item_ref for c in handler.citations] == [
            item_ref_of(HEMOGLOBIN),
            item_ref_of(DIAGNOSIS),
        ]
        # the query was taken from the vault exactly once and is gone
        assert queries.held == 0

    def test_the_composer_files_each_citation_with_its_document_span_and_item_id(self) -> None:
        agent, handler, queries = _wired()
        agent.submit(_request(queries.deposit(QUERY)))
        agent.run_pending()
        cited = cite_records(handler.citations)
        composed = compose(
            meta=NoteMeta(
                visit_id="visit-0123",
                protocol_hash="a" * 64,
                mode="detailed",
                generated_at=AT,
                model="synthetic-note-model@rev0",
                prompt_version="note-v0",
            ),
            triage=RulesTriageResult(level=TriageLevel.GREEN),
            screening=ScreeningBlock(
                provenance=ScreeningProvenance(
                    administration_mode="typed", proxy_reported=False, third_party_present=False
                )
            ),
            imported_objective=cited.imported_objective,
        )
        (fact,) = facts_by_section(composed, "imported_objective")
        box = HEMOGLOBIN.observation.box
        assert fact.attribution is Attribution.RECORD
        assert fact.span.kind is SourceKind.DOCUMENT
        assert (fact.span.ref, fact.span.page, fact.span.bbox, fact.span.item_ref) == (
            box.document_ref,
            box.page,
            box.bbox,
            item_ref_of(HEMOGLOBIN),
        )
        assert fact.span.locator.endswith(f":{item_ref_of(HEMOGLOBIN)}")
        (line,) = composed.note.imported_objective
        assert line.provenance == f"{box.document_ref} p1"
        assert line.summary == "Hemoglobin 10,2 g/dL"

    def test_a_kind_with_no_imported_objective_shape_is_reported_not_filed(self) -> None:
        agent, handler, queries = _wired()
        agent.submit(_request(queries.deposit(QUERY)))
        agent.run_pending()
        cited = cite_records(handler.citations)
        assert len(cited.imported_objective) == 1
        assert cited.not_filed == ((item_ref_of(DIAGNOSIS), RecordItemKind.DIAGNOSIS),)

    def test_a_repeated_retrieval_cites_an_item_once(self) -> None:
        agent, handler, queries = _wired()
        agent.submit(_request(queries.deposit(QUERY)))
        agent.run_pending()
        agent.submit(
            WorkRequest(
                session_id=SESSION,
                work_type=WorkType.RETRIEVE_RECORDS,
                step_id="oyku.baska",
                input_hash=queries.deposit(QUERY),
                protocol_hash=HASH,
                engine_version=1,
            )
        )
        agent.run_pending()
        assert len(handler.citations) == 2


class TestRetrievalFailsClosed:
    def test_a_refused_consent_fails_the_work_and_cites_nothing(self) -> None:
        agent, handler, queries = _wired(consent=_consent(allowed=False))
        ticket = agent.submit(_request(queries.deposit(QUERY)))
        agent.run_pending()
        assert agent.record(ticket.work_id).state is WorkState.FAILED
        assert agent.record(ticket.work_id).error == "RecordsConsentRefused"
        assert handler.citations == ()

    def test_no_registered_model_fails_the_work_and_cites_nothing(self) -> None:
        agent, handler, queries = _wired(retriever=_retriever(embedder=default_record_embedder()))
        ticket = agent.submit(_request(queries.deposit(QUERY)))
        agent.run_pending()
        assert agent.record(ticket.work_id).error == "EmbeddingModelUnregistered"
        assert handler.citations == ()

    def test_a_cancelled_retrieval_cites_nothing(self) -> None:
        agent, handler, queries = _wired()
        seen: list[bool] = []

        original = handler.retriever

        class Spy:
            def retrieve(self, consent: RecordsConsent, query: str, *, k: int) -> Retrieval:
                found = original.retrieve(consent, query, k=k)
                agent.cancel(work_id, "sentetik")
                seen.append(True)
                return found

        handler.retriever = Spy()
        work_id = agent.submit(_request(queries.deposit(QUERY))).work_id
        agent.run_pending()
        assert seen == [True]
        assert handler.citations == ()

    def test_a_query_not_held_fails_the_work(self) -> None:
        agent, handler, _ = _wired()
        ticket = agent.submit(_request("f" * 64))
        agent.run_pending()
        assert agent.record(ticket.work_id).error == "TranscriptNotHeld"
        assert handler.citations == ()


# --- the span ------------------------------------------------------------------------------


def test_a_document_span_without_an_item_id_keeps_its_locator() -> None:
    span = SourceSpan.document(document_ref="doc-1", page=3, bbox=(0.1, 0.2, 0.3, 0.4))
    assert span.item_ref is None
    assert span.locator == "document:doc-1:p3:0.1,0.2,0.3,0.4"


def test_an_item_id_is_id_shaped() -> None:
    with pytest.raises(ValueError, match="item"):
        SourceSpan.document(document_ref="doc-1", page=1, item_ref="Hemoglobin 10,2")

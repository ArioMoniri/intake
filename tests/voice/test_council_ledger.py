"""INT-430 — provenance per field, no confidence, PHI-free events, closed spans.

Medical review §11 (each note field carries its provenance; negatives only
from ASKED_ABSENT; no confidence; no critic prose) and the AI/ML review's
span-attribute allow-list and PHI scan. Near-miss controls throughout.
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Mapping

from clinical_schemas.session import AnswerState
from council_harness import (
    BEKLENTI,
    BELIRTI,
    GUVENLIK,
    IKINCI,
    OLCUM,
    SESSION,
    TENANT,
    ZAMAN,
    ScriptedTransport,
    answer,
    desk_rig,
    document,
    engine,
    ok,
    pins,
    policy,
    reading,
    round_of,
    scope,
    view,
)
from intake_platform.observability.spans import LLM_SPAN_FIELDS
from intake_voice_runtime.clinical_agent.council.adjudicate import adjudicate
from intake_voice_runtime.clinical_agent.council.desk import DeskOutcome
from intake_voice_runtime.clinical_agent.council.ledger import (
    FieldRecord,
    Provenance,
    VerifierLedger,
)
from intake_voice_runtime.clinical_agent.council.orchestrator import (
    SpanContext,
    VerifierOrchestrator,
)
from intake_voice_runtime.clinical_agent.council.readings import Reading
from intake_voice_runtime.extraction.boundary import PatientData
from intake_voice_runtime.ports import WorkRequest, WorkType
from talker_harness import FakeClock

SAID = "Sentetik belirtim yok, bazen var gibi; ölçüm yirmi bir."


def _records(ledger: VerifierLedger, live: object) -> dict[str, FieldRecord]:
    return {record.ref: record for record in ledger.field_records(live, scope())}  # type: ignore[arg-type]


class TestProvenance:
    def _contested_engine(self) -> tuple[object, VerifierLedger]:
        live = engine()
        answer(live, BELIRTI, False)
        answer(live, OLCUM, 12)
        views = {
            BELIRTI: view(BELIRTI, AnswerState.ASKED_ABSENT, False, revision=2),
            OLCUM: view(OLCUM, AnswerState.ASKED_PRESENT, 12, revision=2),
        }
        draws = round_of(
            ok(
                "m1",
                reading(BELIRTI, Reading.HEDGED, SAID, "bazen var gibi"),
                reading(OLCUM, Reading.PRESENT, SAID, "yirmi bir", number="21"),
            )
        )
        ledger = VerifierLedger()
        ledger.record_verdict(adjudicate(draws, views, scope()), stale=frozenset())
        return live, ledger

    def test_note_renders_provenance_per_field(self) -> None:
        live, ledger = self._contested_engine()
        records = _records(ledger, live)
        assert set(records) == {
            BELIRTI,
            OLCUM,
            IKINCI,
            ZAMAN,
            GUVENLIK,
            BEKLENTI,
            "kimlik.subject_role",
        }
        assert records[BELIRTI].provenance is Provenance.CONTESTED
        assert [v.provenance for v in records[BELIRTI].values] == [
            Provenance.DIRECT,
            Provenance.NARRATIVE,
        ]
        assert records[OLCUM].values[0].value == 12  # the direct answer stands
        assert records[OLCUM].values[1].value == "21"  # the contradicting reading, attributed
        assert records[ZAMAN].provenance is Provenance.NOT_ASKED
        assert Provenance.NOT_ASKED.value == "sorulmadi"

    def test_near_miss_a_patient_answer_settles_the_contest(self) -> None:
        live, ledger = self._contested_engine()
        live.append_verification(BELIRTI, *_reask(live))  # type: ignore[attr-defined]
        live.mark_asked(f"{BELIRTI}/verify/1")  # type: ignore[attr-defined]
        live.apply_extraction(f"{BELIRTI}/verify/1", {BELIRTI: True})  # type: ignore[attr-defined]
        assert _records(ledger, live)[BELIRTI].provenance is Provenance.DIRECT

    def test_no_confidence_value_in_note(self) -> None:
        for kind in (FieldRecord, *_value_types()):
            names = {field.name for field in dataclasses.fields(kind)}
            assert not {"confidence", "score", "probability"} & names
            assert "critic" not in " ".join(names)

    def test_negatives_come_only_from_a_direct_answer(self) -> None:
        live = engine()
        draws = round_of(ok("m1", reading(BELIRTI, Reading.ABSENT, SAID, "belirtim yok")))
        ledger = VerifierLedger()
        ledger.record_verdict(
            adjudicate(draws, {BELIRTI: view(BELIRTI, AnswerState.NOT_ASKED)}, scope()),
            stale=frozenset(),
        )
        record = _records(ledger, live)[BELIRTI]
        assert record.provenance is Provenance.NOT_ASKED and record.values == ()

    def test_near_miss_narrative_arming_is_marked_narrative_without_a_value(self) -> None:
        live = engine()
        draws = round_of(ok("m1", reading(BELIRTI, Reading.PRESENT, SAID, "bazen var gibi")))
        ledger = VerifierLedger()
        ledger.record_verdict(
            adjudicate(draws, {BELIRTI: view(BELIRTI, AnswerState.NOT_ASKED)}, scope()),
            stale=frozenset(),
        )
        record = _records(ledger, live)[BELIRTI]
        assert record.provenance is Provenance.NARRATIVE and record.values == ()


def _value_types() -> tuple[type, ...]:
    from intake_voice_runtime.clinical_agent.council.ledger import AttributedValue

    return (AttributedValue,)


def _reask(live: object) -> tuple[object, int]:
    from intake_voice_runtime.clinical_agent.fsm import VerificationKind

    return VerificationKind.REASK, live.slot_revision(BELIRTI)  # type: ignore[attr-defined]


class TestPhiFree:
    def _landed_rig(self) -> object:
        clock = FakeClock()
        doc = document(
            reading(BELIRTI, Reading.HEDGED, SAID, "bazen var gibi"),
            reading(OLCUM, Reading.PRESENT, SAID, "yirmi bir", number="21"),
        )
        rig = desk_rig(clock, texts={-1: doc})
        answer(rig.engine, BELIRTI, False)
        answer(rig.engine, OLCUM, 12)
        data = PatientData(text=SAID)
        rig.desk.request_verification(
            WorkRequest(
                session_id=SESSION,
                work_type=WorkType.EXTRACT_SLOTS,
                step_id=BELIRTI,
                input_hash=data.sha256,
                protocol_hash="c" * 64,
                engine_version=1,
            ),
            data,
        )
        assert clock.run(rig.desk.pump_once()) is DeskOutcome.SUBMITTED
        rig.agent.run_pending()
        return rig

    def test_every_event_is_ids_and_codes(self) -> None:
        rig = self._landed_rig()
        events = rig.desk.ledger.events  # type: ignore[attr-defined]
        assert events, "every proposal is logged"
        flat = repr(events)
        for fragment in ("Sentetik", "bazen", "yirmi", "number="):
            assert fragment not in flat

    def test_near_miss_the_field_records_do_carry_the_values_for_the_note(self) -> None:
        rig = self._landed_rig()
        records = _records(rig.desk.ledger, rig.engine)  # type: ignore[attr-defined]
        assert records[OLCUM].provenance is Provenance.CONTESTED
        assert "21" in repr(records[OLCUM])

    def test_phi_scan_of_spans(self) -> None:
        clock = FakeClock()
        emitted: list[tuple[str, Mapping[str, str | int]]] = []

        class Sink:
            def emit(self, name: str, attributes: Mapping[str, str | int]) -> None:
                emitted.append((name, dict(attributes)))

        doc = document(reading(BELIRTI, Reading.HEDGED, SAID, "bazen var gibi"))
        the_policy = policy(samples=2)
        orchestrator = VerifierOrchestrator(
            transport=ScriptedTransport(clock=clock, texts={-1: doc}),
            policy=the_policy,
            pins=pins(the_policy),
            clock=clock,
            spans=Sink(),
        )
        clock.run(
            orchestrator.convene(
                data=PatientData(text=SAID),
                scope=scope(),
                cache_salt="5" * 32,
                context=SpanContext(
                    work_id="v_sentetik",
                    session_id=SESSION,
                    tenant_id=TENANT,
                    protocol_hash="c" * 64,
                ),
            )
        )
        assert [name for name, _ in emitted] == ["llm.verification", "llm.verification"]
        for _, attributes in emitted:
            assert tuple(attributes) == LLM_SPAN_FIELDS
            values = " ".join(str(value) for value in attributes.values())
            for fragment in ("Sentetik", "bazen", SESSION, "5" * 32):
                assert fragment not in values

    def test_near_miss_no_sink_emits_nothing_and_still_convenes(self) -> None:
        clock = FakeClock()
        the_policy = policy(samples=1)
        orchestrator = VerifierOrchestrator(
            transport=ScriptedTransport(clock=clock, texts={-1: "{}"}),
            policy=the_policy,
            pins=pins(the_policy),
            clock=clock,
        )
        result = clock.run(
            orchestrator.convene(
                data=PatientData(text=SAID),
                scope=scope(),
                cache_salt="5" * 32,
                context=SpanContext("v_x", SESSION, TENANT, "c" * 64),
            )
        )
        assert len(result.results) == 1


class TestOneOutcomeClass:
    def test_refusal_truncation_and_empty_are_one_class(self) -> None:
        from intake_voice_runtime.clinical_agent.council.orchestrator import MemberOutcome
        from intake_voice_runtime.clinical_agent.council.transport import FinishReason

        outcomes = set()
        for finish, text in (
            (FinishReason.REFUSAL, "Bu konuda yardımcı olamam."),
            (FinishReason.LENGTH, '{"readings": [{"ref": '),
            (FinishReason.CONTENT_FILTER, ""),
            (FinishReason.STOP, "   "),
        ):
            clock = FakeClock()
            the_policy = policy(samples=1)
            transport = ScriptedTransport(clock=clock, texts={-1: text}, finish=finish)
            orchestrator = VerifierOrchestrator(
                transport=transport, policy=the_policy, pins=pins(the_policy), clock=clock
            )
            round_ = clock.run(
                orchestrator.convene(
                    data=PatientData(text="Kendime zarar vermeyi düşündüm."),
                    scope=scope(),
                    cache_salt="5" * 32,
                    context=SpanContext("v_x", SESSION, TENANT, "c" * 64),
                )
            )
            outcomes.add(round_.results[0].outcome)
        assert outcomes == {MemberOutcome.ABSTAINED}

    def test_near_miss_a_clean_stop_with_a_valid_document_is_ok(self) -> None:
        from intake_voice_runtime.clinical_agent.council.orchestrator import MemberOutcome

        clock = FakeClock()
        the_policy = policy(samples=1)
        orchestrator = VerifierOrchestrator(
            transport=ScriptedTransport(clock=clock, texts={-1: '{"readings": []}'}),
            policy=the_policy,
            pins=pins(the_policy),
            clock=clock,
        )
        round_ = asyncio.run(
            orchestrator.convene(
                data=PatientData(text=SAID),
                scope=scope(),
                cache_salt="5" * 32,
                context=SpanContext("v_x", SESSION, TENANT, "c" * 64),
            )
        )
        assert round_.results[0].outcome is MemberOutcome.OK

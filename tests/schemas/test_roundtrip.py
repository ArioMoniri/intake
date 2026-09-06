"""INT-031 — clinical-schemas roundtrip, invariants and codegen drift.

Acceptance under test, verbatim (docs/backlog/issues.yaml):
  "PreVisitNote, PatientSummary, ExtractedRecordItem, ConsentScope,
   TriageResult, SessionState, PatientOverlay, ObserverState, Proposal;
   events csat.v1, nps.v1, clinician_pulse.v1, audit.v1, security.v1;
   TS generated from OpenAPI"

Three layers of proof:
1. roundtrip — python model → JSON → python equality, for every clinical
   object and every event; and the JSON validates against the *committed*
   exported schema (not one regenerated on the fly).
2. invariants — triage provenance is type-level (invariant 1: an LLM
   candidate cannot carry RED or a preempt-capable level; a rules RED
   cannot omit register/location — invariant 21); PatientOverlay facts
   are confirmed-source-only at the type level (invariant 12); observer
   models are frozen read-only records (invariant 11); PatientSummary's
   annotation closure never reaches clinician-only material (files/12
   §2.3 type-graph closure).
3. drift — regenerating the OpenAPI bundle, the event JSON Schemas and
   the generated TS produces byte-identical output to what is committed,
   so `make check` fails the moment the generated artefacts go stale.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, get_args, get_origin

import clinical_schemas
import jsonschema
import pydantic
import pytest
from clinical_schemas import (
    EVENT_MODELS,
    AnswerState,
    AuditV1,
    CandidateFlag,
    ClinicianPulseV1,
    ConsentChannel,
    ConsentPurpose,
    ConsentScope,
    CsatReason,
    CsatV1,
    EvidenceBundle,
    EvidenceStats,
    ExtractedRecordItem,
    InteractionState,
    LaneSignal,
    LearnedFact,
    LearnedFactSource,
    LlmCandidateTriage,
    NpsV1,
    ObserverState,
    PatientOverlay,
    PatientSummary,
    PreVisitNote,
    Proposal,
    ProposalType,
    RecordCode,
    RecordProvenance,
    RulesTriageResult,
    SecurityV1,
    SessionBudget,
    SessionState,
    SummaryCard,
    TriageLevel,
    TriageResult,
)
from clinical_schemas.codegen import PACKAGE_ROOT, generate_artifacts
from protocols.triage import canonical_scalar

NOW = datetime(2026, 8, 28, 10, 0, 0, tzinfo=UTC)
TENANT = uuid.UUID("00000000-0000-4000-8000-000000000001")
SESSION = uuid.UUID("00000000-0000-4000-8000-000000000002")


def _note() -> PreVisitNote:
    return PreVisitNote.model_validate(
        {
            "meta": {
                "visit_id": "visit_0001",
                "protocol_hash": "a" * 64,
                "mode": "fast",
                "language": "tr",
                "generated_at": NOW.isoformat(),
                "model": "extraction-llm@r1",
                "prompt_version": "p1",
            },
            "triage": {
                "level": "YELLOW",
                "rules": [{"id": "rf.test_rule", "evidence": "slot ates=38.6"}],
                "llm_candidates": [],
            },
            "chief_complaint": {"text": "karin agrisi", "patient_goals": ["nedenini anlamak"]},
            "hpi": {
                "narrative": "iki gundur suren agri",
                "oldcarts": {
                    "onset": "iki gun once",
                    "location": "epigastrium",
                    "duration": "araliklarla",
                    "character": "yanici",
                    "aggravating": ["yemek"],
                    "relieving": [],
                    "radiation": "",
                    "timing": "geceleri",
                    "severity_nrs": 4,
                    "trajectory": "sabit",
                },
                "associated": ["bulanti"],
                "negatives": ["ates yok"],
            },
            "ros_pertinent": [{"system": "gi", "finding": "bulanti", "present": True}],
            "pmh": [
                {
                    "condition": "hipertansiyon",
                    "icd10": "I10",
                    "status": "confirmed",
                    "source": "patient",
                }
            ],
            "medications": [
                {
                    "name": "lisinopril",
                    "atc": "C09AA03",
                    "dose": "on miligram gunde bir",
                    "adherence": "duzenli",
                    "source": "patient",
                    "reconciliation": "matches",
                }
            ],
            "allergies": [{"substance": "penisilin", "reaction": "dokuntu", "severity": "orta"}],
            "family_social": {
                "family": ["babada kalp hastaligi"],
                "smoking": {"status": "never"},
                "alcohol": {"status": "none"},
                "occupation": "ogretmen",
                "living_situation": "ailesiyle",
            },
            "screening": {
                "phq2": 1,
                "gad2": None,
                "phq9": None,
                "gad7": None,
                "cssrs": None,
                "provenance": {
                    "administration_mode": "typed",
                    "proxy_reported": False,
                    "third_party_present": True,
                    "qualifier_tr": "baska bir konusmaci duyuldu",
                },
            },
            "konusma_ozellikleri": {
                "speech_rate_syll_s": 4.2,
                "pause_ratio": 0.18,
                "f0_mean_hz": 180.0,
                "f0_sd_hz": 22.0,
                "response_latency_ms_mean": 640.0,
                "reference_ranges": {"speech_rate_syll_s": "3.5-5.5"},
                "recording_conditions_caveat_tr": "telefon mikrofonu, ev ortami",
            },
            "imported_objective": [
                {
                    "type": "lab",
                    "summary": "hemoglobin on nokta iki",
                    "date": "2026-08-20",
                    "provenance": "doc_0001 s.1",
                }
            ],
            "data_gaps": ["asi karti yok"],
            "suggested_focus_questions": ["agri geceleri artiyor mu"],
            "considerations": [{"pattern": "dispepsi", "why": "yemekle iliskili yanma"}],
            "patient_confirmed_sections": ["medications"],
        }
    )


def _summary() -> PatientSummary:
    return PatientSummary(
        cards=[SummaryCard(title_tr="Anlattiklariniz", lines=["iki gundur karin agrisi"])],
        questions_for_doctor=["hangi tetkikler gerekli"],
        bring_list=["ilac kutulari"],
        triage_message_tr="Randevunuzdan once bir degisiklik olursa bize yazin.",
    )


def _record_item() -> ExtractedRecordItem:
    return ExtractedRecordItem(
        kind="lab",
        summary="hemoglobin",
        code=RecordCode(system="loinc", code="718-7"),
        value_magnitude=Decimal("10.2"),
        unit="g/dL",
        unit_conflict=False,
        verification_status="unconfirmed",
        provenance=RecordProvenance(document_ref="doc_0001", page=1, bbox=(0.1, 0.2, 0.4, 0.25)),
    )


def _consent() -> ConsentScope:
    return ConsentScope(
        purpose=ConsentPurpose.LANE_AFFECT,
        version="v3",
        text_hash="b" * 64,
        granted_at=NOW,
        channel=ConsentChannel.APP,
        evidence="consent_evt_0001",
    )


def _rules_triage() -> RulesTriageResult:
    return RulesTriageResult(
        source="rules",
        level=TriageLevel.RED,
        rules=[{"id": "base.life_threat.chest_pain", "evidence": "slot gogus_agrisi=true"}],
        register="ALERT",
        location="REMOTE",
    )


def _session_state() -> SessionState:
    return SessionState(
        session_id="sess_0001",
        protocol_id="cluster.gi",
        protocol_version="1.2.0",
        protocol_hash="c" * 64,
        mode="fast",
        status="active",
        reference_time=NOW,
        step_states={"cc.open": AnswerState.ASKED_PRESENT, "gi.melena": AnswerState.NOT_ASKED},
        slots={"ates": "38.6"},
        budget=SessionBudget(turns_used=4, turns_remaining=14),
        triage=None,
    )


def _overlay() -> PatientOverlay:
    return PatientOverlay(
        patient_ref="k1.aabbcc",
        version=2,
        facts=[
            LearnedFact(
                key="chronic.hipertansiyon",
                value="NYHA-1",
                source=LearnedFactSource.CLINICIAN_ACCEPTED_NOTE,
                source_ref="note_0001",
                confidence=0.9,
                confirmed_at=NOW,
                shared=True,
            )
        ],
    )


def _observer() -> ObserverState:
    return ObserverState(
        session_id="sess_0001",
        interaction=InteractionState(
            pace="slow",
            modality="typed",
            break_offer=False,
            confirm_by_card=True,
            repeat_request=False,
            third_party_present=True,
        ),
        linguistic_markers={"hopelessness_hits": 0},
        asr_quality={"mean_confidence": 0.91},
        engagement={"answer_latency_ms_mean": 900},
    )


def _lane_signal() -> LaneSignal:
    return LaneSignal(
        lane="linguistic",
        session_id="sess_0001",
        seq=12,
        t_monotonic_ms=84000,
        t_wall=NOW,
        window_id="w_0003",
        payload={"negation_ratio": 0.2},
        confidence=0.8,
        model_ref="lex-tr@v4",
        model_sha256="d" * 64,
        sampling_rate_hz=1.0,
        dropped_frames_in_window=0,
        gate_state="open",
        consent_version="v3",
        tombstoned=False,
    )


def _proposal() -> Proposal:
    return Proposal(
        type=ProposalType.ADD_FOLLOW_UP_TR,
        target_path="packages/protocols/packs/cluster.gi.yaml",
        diff="--- a\n+++ b\n",
        evidence=EvidenceBundle(
            stats=EvidenceStats(patients=14, clinics=3, weeks_stable=2),
            exemplars_deid=["ex_0001"],
            simulator_run="sim_0009",
            goldens="golden_0009",
            latency="lat_0009",
            shadow_replay="replay_0009",
            langfuse_experiment="lf_0009",
        ),
    )


def _events() -> list[pydantic.BaseModel]:
    return [
        CsatV1(
            tenant_id=TENANT,
            session_id=SESSION,
            score=4,
            reason=CsatReason.HELPFUL,
            text=None,
        ),
        NpsV1(tenant_id=TENANT, score=9),
        ClinicianPulseV1(tenant_id=TENANT, clinician_ref="clin_0001", score=5),
        AuditV1(
            seq=1,
            timestamp_utc="2026-08-28T10:00:00+00:00",
            actor="svc-api",
            action="note.read",
            resource_ref="note_0001",
            consent_scope_ref="share",
            prev_hash="0" * 64,
            entry_hash="e" * 64,
        ),
        SecurityV1(
            category="consent_scope_denial",
            tenant_id=TENANT,
            actor_ref="svc-api",
            resource_ref="note_0001",
            correlation_id="corr_0001",
            attributes={"denied_scope": "wellbeing"},
        ),
    ]


def _all_instances() -> list[pydantic.BaseModel]:
    return [
        _note(),
        _summary(),
        _record_item(),
        _consent(),
        _rules_triage(),
        LlmCandidateTriage(
            source="llm_candidate",
            candidate_flags=[CandidateFlag(text="gizli kanama olabilir", evidence="melena tarifi")],
        ),
        _session_state(),
        _overlay(),
        _observer(),
        _lane_signal(),
        _proposal(),
        *_events(),
    ]


# ---------------------------------------------------------------- roundtrip


@pytest.mark.parametrize("instance", _all_instances(), ids=lambda m: type(m).__name__)
def test_json_roundtrip_is_lossless(instance: pydantic.BaseModel) -> None:
    dumped = instance.model_dump_json()
    restored = type(instance).model_validate_json(dumped)
    assert restored == instance
    assert restored.model_dump_json() == dumped


def test_event_json_validates_against_committed_schema() -> None:
    schemas_dir = PACKAGE_ROOT / "schemas" / "events"
    for event in _events():
        schema_id: str = event.schema_id  # type: ignore[attr-defined]
        name = schema_id.removeprefix("intake.clinical.")
        schema_file = schemas_dir / f"{name}.json"
        assert schema_file.is_file(), f"missing committed schema {schema_file}"
        schema = pydantic.TypeAdapter(dict[str, Any]).validate_json(
            schema_file.read_text(encoding="utf-8")
        )
        jsonschema.validate(
            instance=event.model_dump(mode="json"),
            schema=schema,
            cls=jsonschema.Draft202012Validator,
        )


def test_openapi_bundle_carries_all_nine_models_and_five_events() -> None:
    openapi = pydantic.TypeAdapter(dict[str, Any]).validate_json(
        (PACKAGE_ROOT / "schemas" / "openapi.json").read_text(encoding="utf-8")
    )
    names = set(openapi["components"]["schemas"])
    for required in (
        "PreVisitNote",
        "PatientSummary",
        "ExtractedRecordItem",
        "ConsentScope",
        "RulesTriageResult",
        "LlmCandidateTriage",
        "SessionState",
        "PatientOverlay",
        "ObserverState",
        "Proposal",
        "CsatV1",
        "NpsV1",
        "ClinicianPulseV1",
        "AuditV1",
        "SecurityV1",
    ):
        assert required in names, f"OpenAPI bundle misses {required}"


# ---------------------------------------------------------------- invariants


def test_llm_candidate_triage_cannot_carry_red_or_yellow() -> None:
    """Invariant 1: LLM output is capped at YELLOW_REVIEW at the type level."""
    for forbidden in ("RED", "YELLOW", "GREEN"):
        with pytest.raises(pydantic.ValidationError):
            LlmCandidateTriage.model_validate(
                {
                    "source": "llm_candidate",
                    "level": forbidden,
                    "candidate_flags": [{"text": "x1", "evidence": "e1"}],
                }
            )
    assert (
        LlmCandidateTriage(candidate_flags=[CandidateFlag(text="x1", evidence="e1")]).level
        == "YELLOW_REVIEW"
    )


def test_llm_candidate_triage_requires_at_least_one_flag() -> None:
    with pytest.raises(pydantic.ValidationError):
        LlmCandidateTriage(candidate_flags=[])


def test_rules_red_requires_register_and_location() -> None:
    """Invariant 21: register and location are required on RED, no default."""
    with pytest.raises(pydantic.ValidationError):
        RulesTriageResult(
            source="rules",
            level=TriageLevel.RED,
            rules=[{"id": "rf.x", "evidence": "e"}],
        )
    with pytest.raises(pydantic.ValidationError):
        RulesTriageResult(
            source="rules",
            level=TriageLevel.RED,
            rules=[{"id": "rf.x", "evidence": "e"}],
            register="ALERT",
        )


def test_rules_non_green_requires_a_fired_rule() -> None:
    """Invariant 1: RED/YELLOW must name the rules-engine rules that fired."""
    with pytest.raises(pydantic.ValidationError):
        RulesTriageResult(source="rules", level=TriageLevel.YELLOW, rules=[])


def test_triage_result_discriminates_on_source() -> None:
    adapter = pydantic.TypeAdapter(TriageResult)
    rules = adapter.validate_python(_rules_triage().model_dump())
    assert isinstance(rules, RulesTriageResult)
    llm = adapter.validate_python(
        {
            "source": "llm_candidate",
            "level": "YELLOW_REVIEW",
            "candidate_flags": [{"text": "x1", "evidence": "e1"}],
        }
    )
    assert isinstance(llm, LlmCandidateTriage)


def test_session_state_triage_slot_only_accepts_rules_results() -> None:
    """Invariant 1: the state that drives routing cannot hold an LLM candidate."""
    payload = _session_state().model_dump()
    payload["triage"] = {
        "source": "llm_candidate",
        "level": "YELLOW_REVIEW",
        "candidate_flags": [{"text": "x1", "evidence": "e1"}],
    }
    with pytest.raises(pydantic.ValidationError):
        SessionState.model_validate(payload)


def test_learned_fact_rejects_unconfirmed_sources() -> None:
    """Invariant 12: PatientOverlay facts require confirmed provenance."""
    assert {source.value for source in LearnedFactSource} == {
        "confirmed_intake_extraction",
        "clinician_accepted_note",
        "confirmed_imported_record",
    }
    with pytest.raises(pydantic.ValidationError):
        LearnedFact(
            key="k1",
            value="v1",
            source="llm_unconfirmed",  # type: ignore[arg-type]
            source_ref="x_1",
            confidence=0.5,
            confirmed_at=NOW,
        )


def test_observer_models_are_frozen_and_closed() -> None:
    """Invariant 11: observer output is a read-only record, six fields exactly."""
    observer = _observer()
    with pytest.raises(pydantic.ValidationError):
        observer.interaction.pace = "normal"  # type: ignore[misc]
    assert len(InteractionState.model_fields) == 6
    with pytest.raises(pydantic.ValidationError):
        InteractionState.model_validate(
            {
                "pace": "slow",
                "modality": "typed",
                "break_offer": False,
                "confirm_by_card": False,
                "repeat_request": False,
                "third_party_present": False,
                "affect_label": "sad",
            }
        )


def test_observer_state_has_no_acoustic_field() -> None:
    """files/03 §4.7.4: acoustic output goes to the sealed research store only."""
    assert "acoustic" not in ObserverState.model_fields
    assert not any("acoustic" in name for name in PreVisitNote.model_fields)


def test_patient_summary_annotation_closure_stays_patient_safe() -> None:
    """files/12 §2.3: walk PatientSummary's transitive annotations; assert none
    reaches clinician-only material (candidate flags, rule evidence, overlays)."""
    forbidden = {CandidateFlag, RulesTriageResult, LlmCandidateTriage, PatientOverlay}
    seen: set[type[pydantic.BaseModel]] = set()

    def walk(model: type[pydantic.BaseModel]) -> None:
        if model in seen:
            return
        seen.add(model)
        for field in model.model_fields.values():
            queue = [field.annotation]
            while queue:
                ann = queue.pop()
                if isinstance(ann, type) and issubclass(ann, pydantic.BaseModel):
                    assert ann not in forbidden, f"{model.__name__} reaches {ann.__name__}"
                    walk(ann)
                else:
                    origin = get_origin(ann)
                    if origin is not None:
                        queue.extend(get_args(ann))

    walk(PatientSummary)


def test_consent_purposes_match_files_06() -> None:
    """files/06 §2.1: 'Purposes exactly: …' — no more, no fewer."""
    assert {purpose.value for purpose in ConsentPurpose} == {
        "core",
        "voice",
        "wellbeing",
        "lane:affect",
        "lane:linguistic",
        "documents",
        "learning:personal",
        "learning:service_improvement",
        "satisfaction",
        "share",
        "research",
    }


def test_share_consent_requires_share_scope() -> None:
    """files/06 §2.1: share:{recipient,visit,sections,expiry}."""
    with pytest.raises(pydantic.ValidationError):
        ConsentScope(
            purpose=ConsentPurpose.SHARE,
            version="v1",
            text_hash="b" * 64,
            granted_at=NOW,
            channel=ConsentChannel.APP,
            evidence="consent_evt_0002",
        )
    with pytest.raises(pydantic.ValidationError):
        ConsentScope(
            purpose=ConsentPurpose.CORE,
            version="v1",
            text_hash="b" * 64,
            granted_at=NOW,
            channel=ConsentChannel.APP,
            evidence="consent_evt_0002",
            share={
                "recipient": "dr_0001",
                "visit": "visit_0001",
                "sections": ["hpi"],
                "expiry": NOW.isoformat(),
            },
        )


def test_proposal_targets_only_learnable_paths() -> None:
    """files/09 §4: a proposal is a PR against packages/protocols or
    packages/llm-evals/prompts — nothing else."""
    good = _proposal()
    assert good.target_path.startswith("packages/protocols")
    with pytest.raises(pydantic.ValidationError):
        Proposal.model_validate(
            {**good.model_dump(), "target_path": "packages/protocols/../../etc/passwd"}
        )
    with pytest.raises(pydantic.ValidationError):
        Proposal.model_validate({**good.model_dump(), "target_path": "services/api/app.py"})


def test_proposal_evidence_thresholds_are_type_level() -> None:
    """files/09 §4: ≥ 10 patients, ≥ 2 clinics, stable ≥ 2 weeks."""
    with pytest.raises(pydantic.ValidationError):
        EvidenceStats(patients=9, clinics=2, weeks_stable=2)
    with pytest.raises(pydantic.ValidationError):
        EvidenceStats(patients=10, clinics=1, weeks_stable=2)
    with pytest.raises(pydantic.ValidationError):
        EvidenceStats(patients=10, clinics=2, weeks_stable=1)


def test_event_schema_ids_follow_the_ts_convention() -> None:
    """The TS side owns the id convention (packages/clinical-schemas/src/index.ts):
    intake.clinical.<name>.v<version>."""
    assert set(EVENT_MODELS) == {
        "intake.clinical.csat.v1",
        "intake.clinical.nps.v1",
        "intake.clinical.clinician_pulse.v1",
        "intake.clinical.wait.v1",
        "intake.clinical.audit.v1",
        "intake.clinical.security.v1",
    }
    for schema_id, model in EVENT_MODELS.items():
        field = model.model_fields["schema_id"]
        assert field.default == schema_id


def test_audit_v1_mirrors_the_int016_chain_entry() -> None:
    """packages/intake_platform/audit.py AuditEntry is the source of truth."""
    from dataclasses import fields as dc_fields

    from intake_platform.audit import AuditEntry

    expected = {f.name for f in dc_fields(AuditEntry)}
    assert set(AuditV1.model_fields) == expected | {"schema_id"}


def test_frozen_value_models_reject_mutation() -> None:
    consent = _consent()
    with pytest.raises(pydantic.ValidationError):
        consent.version = "v9"  # type: ignore[misc]
    item = _record_item()
    with pytest.raises(pydantic.ValidationError):
        item.unit = "mg"  # type: ignore[misc]


def test_konusma_ozellikleri_requires_reference_range_and_caveat() -> None:
    """files/04 §5 note: every measure ships with a population reference range
    and a recording-condition caveat, or it is not rendered."""
    block = _note().konusma_ozellikleri
    assert block is not None
    payload = block.model_dump()
    payload["reference_ranges"] = {}
    from clinical_schemas import KonusmaOzellikleri

    with pytest.raises(pydantic.ValidationError):
        KonusmaOzellikleri.model_validate(payload)
    payload = block.model_dump()
    payload["recording_conditions_caveat_tr"] = ""
    with pytest.raises(pydantic.ValidationError):
        KonusmaOzellikleri.model_validate(payload)


def test_public_all_names_nine_clinical_objects() -> None:
    for name in (
        "PreVisitNote",
        "PatientSummary",
        "ExtractedRecordItem",
        "ConsentScope",
        "TriageResult",
        "SessionState",
        "PatientOverlay",
        "ObserverState",
        "Proposal",
    ):
        assert name in clinical_schemas.__all__


# ---------------------------------------------------------------- drift


def test_generated_artifacts_are_committed_and_current() -> None:
    """Regenerating changes nothing — the codegen drift gate for `make check`."""
    artifacts = generate_artifacts()
    assert artifacts, "codegen produced nothing"
    for relpath, content in sorted(artifacts.items()):
        committed = Path(PACKAGE_ROOT / relpath)
        assert committed.is_file(), f"generated artefact not committed: {relpath}"
        assert committed.read_text(encoding="utf-8") == content, (
            f"stale generated artefact: {relpath} — run `make schemas-codegen`"
        )


def test_write_artifacts_reproduces_the_committed_tree(tmp_path: Path) -> None:
    from clinical_schemas.codegen import write_artifacts

    written = write_artifacts(tmp_path)
    assert written, "write_artifacts wrote nothing"
    for path in written:
        relpath = path.relative_to(tmp_path)
        committed = PACKAGE_ROOT / relpath
        assert path.read_text(encoding="utf-8") == committed.read_text(encoding="utf-8")


def test_schema_id_convention_matches_the_ts_side() -> None:
    from clinical_schemas import SCHEMA_NAMESPACE, schema_id

    assert SCHEMA_NAMESPACE == "intake.clinical"
    assert schema_id("csat", 1) == "intake.clinical.csat.v1"
    with pytest.raises(ValueError, match="invalid schema name"):
        schema_id("Csat", 1)
    with pytest.raises(ValueError, match="invalid schema version"):
        schema_id("csat", 0)


def test_fact_reconfirmation_after_twelve_months() -> None:
    """files/09 §3: a fact older than 12 months is re-confirmed before use."""
    from datetime import timedelta

    from clinical_schemas import fact_needs_reconfirmation

    fact = _overlay().facts[0]
    assert not fact_needs_reconfirmation(fact, NOW)
    assert fact_needs_reconfirmation(fact, NOW + timedelta(days=366))


def test_generated_ts_is_types_only() -> None:
    ts = (PACKAGE_ROOT / "src" / "generated" / "models.ts").read_text(encoding="utf-8")
    assert "export interface" in ts or "export type" in ts
    for runtime_marker in ("class ", "function ", "const ", "require(", "import "):
        assert runtime_marker not in ts, f"generated TS carries runtime code: {runtime_marker}"


# ----------------------------------------- INT-309: the Decimal on the wire


class TestDecimalCrossesTheWireAsItself:
    """INT-309 boundary 3 — the JSON round trip silently restrung a Decimal.

    ``Decimal("38.50")`` dumped to the JSON string ``"38.50"`` and validated
    back as a ``str``, because ``JsonScalar`` carries both ``str`` and
    ``Decimal`` and the two had the same wire form. ``canonical_scalar``
    then read the restored value as a string, so a numeric threshold over it
    read Unknown and a red-flag rule silently never fired — the INT-303
    defect, relocated to the wire, and a regression against the float the
    carrier held before INT-303.

    ADR-028 records the encoding this pins: a clinical quantity crosses
    INTAKE's own wire as a *tagged* JSON string, because a JSON number
    cannot carry the declared scale through the parser and a bare JSON
    string cannot be told apart from a string answer.
    """

    def test_a_decimal_slot_comes_back_a_decimal(self) -> None:
        state = _session_state().model_copy(update={"slots": {"ates": Decimal("38.5")}})
        restored = SessionState.model_validate_json(state.model_dump_json())
        assert isinstance(restored.slots["ates"], Decimal)
        assert restored.slots["ates"] == Decimal("38.5")

    def test_the_declared_scale_survives_the_wire(self) -> None:
        # Near-miss control: 38.50 and 38.5 are one float and two clinical
        # quantities. Any fix that goes through a float passes the test
        # above and fails this one.
        state = _session_state().model_copy(update={"slots": {"ates": Decimal("38.50")}})
        restored = SessionState.model_validate_json(state.model_dump_json())
        carried = restored.slots["ates"]
        assert isinstance(carried, Decimal)
        assert carried.as_tuple() == Decimal("38.50").as_tuple()
        assert carried.as_tuple() != Decimal("38.5").as_tuple()

    def test_an_integer_too_large_for_a_float_survives_the_wire(self) -> None:
        # Near-miss control: the first integer a float cannot represent.
        big = Decimal(2**53 + 1)
        state = _session_state().model_copy(update={"slots": {"sayim": big}})
        restored = SessionState.model_validate_json(state.model_dump_json())
        assert restored.slots["sayim"] == big
        assert restored.slots["sayim"] != Decimal(2**53)

    def test_a_string_answer_that_looks_numeric_is_still_a_string(self) -> None:
        # Negative control, and the reason the encoding has to be tagged
        # rather than merely parsed: "38.6" is a real string answer — the
        # INT-031 SessionState fixture above carries exactly that — and
        # tests/safety/test_numeric_carrier.py pins canonical_scalar("38.5")
        # as a str. A fix that promotes numeric-looking strings to Decimal
        # passes every test above and breaks both of those.
        state = _session_state().model_copy(update={"slots": {"ates": "38.50"}})
        restored = SessionState.model_validate_json(state.model_dump_json())
        assert restored.slots["ates"] == "38.50"
        assert not isinstance(restored.slots["ates"], Decimal)

    def test_a_string_that_starts_with_the_tag_survives_unchanged(self) -> None:
        # The encoding is total, not merely lucky: a patient answer that
        # happens to begin with the reserved prefix is escaped on the way
        # out and unescaped on the way back, so no free text is refused and
        # none is silently reinterpreted as a number.
        planted = {"a": "~d38.50", "b": "~~x", "c": "~"}
        state = _session_state().model_copy(update={"slots": planted})
        restored = SessionState.model_validate_json(state.model_dump_json())
        assert restored.slots == planted
        assert all(isinstance(v, str) for v in restored.slots.values())

    def test_a_decimal_nested_in_a_list_or_a_map_comes_back_a_decimal(self) -> None:
        nested = {"olcumler": [Decimal("1.10"), "1.10"], "son": {"deger": Decimal("0.50")}}
        state = _session_state().model_copy(update={"slots": nested})
        restored = SessionState.model_validate_json(state.model_dump_json())
        assert restored.slots["olcumler"] == [Decimal("1.10"), "1.10"]
        assert isinstance(restored.slots["olcumler"][0], Decimal)  # type: ignore[index]
        assert not isinstance(restored.slots["olcumler"][1], Decimal)  # type: ignore[index]
        assert restored.slots["son"] == {"deger": Decimal("0.50")}

    def test_a_learned_fact_value_crosses_the_wire_as_a_decimal(self) -> None:
        fact = _overlay().facts[0].model_copy(update={"value": Decimal("38.50")})
        restored = LearnedFact.model_validate_json(fact.model_dump_json())
        assert isinstance(restored.value, Decimal)
        assert restored.value.as_tuple() == Decimal("38.50").as_tuple()

    def test_a_restored_decimal_is_a_number_to_the_triage_grammar(self) -> None:
        # The whole point: the restored value has to be the thing a red-flag
        # threshold can compare, not a string canonical_scalar reads Unknown.
        state = _session_state().model_copy(update={"slots": {"ates": Decimal("38.50")}})
        restored = SessionState.model_validate_json(state.model_dump_json())
        assert canonical_scalar(restored.slots["ates"]) == Decimal("38.50")
        assert canonical_scalar(restored.slots["ates"]) > Decimal("38.0")


# ------------------------------------------------- INT-309 · the wire (ADR-030)


def _state_with(**slots: Any) -> SessionState:
    """A SessionState whose only interesting part is one slot value."""
    return SessionState(
        session_id="sess_0001",
        protocol_id="cluster.gi",
        protocol_version="1.2.0",
        protocol_hash="c" * 64,
        mode="fast",
        status="active",
        reference_time=NOW,
        step_states={"cc.open": AnswerState.ASKED_PRESENT},
        slots=slots,
        budget=SessionBudget(turns_used=4, turns_remaining=14),
        triage=None,
    )


class TestADecimalCrossesTheWireAsItself:
    """INT-309 boundary 3 — the JSON round trip used to restring a Decimal.

    ``Decimal("38.50")`` dumped to the JSON string ``"38.50"`` and validated
    back as a ``str``, which ``canonical_scalar`` reads as Unknown: the
    defect INT-303 fixed, relocated to the wire, and a regression against the
    pre-INT-303 ``float``. ADR-030 records why the fix is a tagged string and
    not a JSON number.
    """

    def test_a_decimal_slot_validates_back_as_a_decimal(self) -> None:
        state = _state_with(ates=Decimal("38.50"))
        restored = SessionState.model_validate_json(state.model_dump_json())
        assert isinstance(restored.slots["ates"], Decimal)
        assert restored.slots["ates"] == Decimal("38.50")
        assert restored == state

    def test_the_declared_scale_survives_the_round_trip(self) -> None:
        """Near-miss control: 38.50 and 38.5 are the same float and two
        different declared scales (files/13 §9.5). A fix that routes the
        value through ``float`` passes on 38.5 and fails here."""
        restored = SessionState.model_validate_json(
            _state_with(ates=Decimal("38.50")).model_dump_json()
        )
        value = restored.slots["ates"]
        assert isinstance(value, Decimal)
        assert value.as_tuple() == Decimal("38.50").as_tuple()
        assert value.as_tuple() != Decimal("38.5").as_tuple()

    def test_an_integer_too_large_for_a_float_survives_exactly(self) -> None:
        """Near-miss control: 2**53 + 1 is the smallest integer a float
        cannot represent, so a float-shaped fix loses the last digit."""
        big = Decimal("9007199254740993")
        assert Decimal(float(big)) != big  # the control's premise
        restored = SessionState.model_validate_json(_state_with(n=big).model_dump_json())
        assert restored.slots["n"] == big

    def test_a_numeric_looking_string_answer_is_still_a_string(self) -> None:
        """Negative control, and the reason a bare string cannot be the
        encoding: ``tests/safety/test_numeric_carrier.py`` pins
        ``canonical_scalar("38.5")`` as a ``str``, and the INT-031 fixture
        carries ``slots={"ates": "38.6"}``. A fix that reads numeric-looking
        strings back as Decimals breaks both."""
        restored = SessionState.model_validate_json(
            _state_with(ates="38.50", note="38.6").model_dump_json()
        )
        assert restored.slots["ates"] == "38.50"
        assert not isinstance(restored.slots["ates"], Decimal)
        assert not isinstance(restored.slots["note"], Decimal)

    def test_a_string_that_looks_like_the_tag_round_trips_as_that_string(self) -> None:
        """The reserved prefix is escaped, never refused: a patient answer is
        never rejected for the shape of its first character, and never
        silently becomes a number once it is on the wire.

        The inputs are spelled in wire form (``~~`` for a literal ``~``)
        because ``JsonValue`` decodes in both validation modes — it has to,
        since FastAPI validates a parsed request body in *python* mode, so a
        json-only decoder would leave every inbound API quantity a string.
        ADR-030 records that consequence."""
        state = _state_with(a="~~d38.50", b="~~", c="~~~x")
        assert state.slots["a"] == "~d38.50"  # decoded once, on the way in
        restored = SessionState.model_validate_json(state.model_dump_json())
        assert restored.slots["a"] == "~d38.50"
        assert not isinstance(restored.slots["a"], Decimal)
        assert restored.slots["b"] == "~"
        assert restored.slots["c"] == "~~x"
        assert restored == state

    def test_a_decimal_nested_in_a_list_or_a_map_survives(self) -> None:
        state = _state_with(xs=[Decimal("1.10")], m={"k": Decimal("0.10")})
        restored = SessionState.model_validate_json(state.model_dump_json())
        assert restored.slots["xs"] == [Decimal("1.10")]
        assert restored.slots["m"] == {"k": Decimal("0.10")}
        assert restored == state

    def test_a_float_lane_value_still_crosses_as_a_json_number(self) -> None:
        """Negative control for the other half of the carrier: an observer
        lane legitimately carries a float (CLAUDE.md invariant 11) and must
        not be promoted to a Decimal by the codec."""
        restored = SessionState.model_validate_json(_state_with(f=0.1).model_dump_json())
        assert isinstance(restored.slots["f"], float)
        assert restored.slots["f"] == 0.1

    def test_a_learned_fact_value_crosses_the_wire_as_a_decimal(self) -> None:
        fact = LearnedFact(
            key="baseline.ates",
            value=Decimal("38.50"),
            source=LearnedFactSource.CLINICIAN_ACCEPTED_NOTE,
            source_ref="note_0001",
            confidence=0.9,
            confirmed_at=NOW,
        )
        restored = LearnedFact.model_validate_json(fact.model_dump_json())
        assert isinstance(restored.value, Decimal)
        assert restored.value.as_tuple() == Decimal("38.50").as_tuple()

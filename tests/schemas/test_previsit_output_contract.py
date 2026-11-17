"""The ``PreVisitOutput`` contract — the finished previsit as a hospital reads it.

Three invariants are asserted here as properties of the TYPE, because that is
where this document has to hold them: the receiver is another organisation's
software, and a rule enforced only by the route that happens to serve it is a
rule the next serving path will not inherit.

- **invariant 1** — the ``triage`` union has exactly two members, and neither
  of them is ``LlmCandidateTriage``. An LLM judgement has one home in this
  document (``llm_candidates``) and no way into the routing level.
- **invariant 22** — a magnitude and its unit are one object, and the
  magnitude rides the shared ``JsonValue`` carrier (INT-309/ADR-030) rather
  than a second encoding invented here.
- **invariant 6** — no field of this document can carry a direct identifier.
  The hospital's own ``patient_number`` is what the REQUEST names; it is
  echoed from there and is not a member of the stored document at all.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from clinical_schemas.common import schema_id
from clinical_schemas.note import MeasureCode
from clinical_schemas.previsit_output import (
    PREVISIT_OUTPUT_SCHEMA_ID,
    NotEvaluatedReason,
    OutputMeasurement,
    OutputSection,
    PreVisitOutput,
    TriageNotEvaluated,
)
from clinical_schemas.triage import (
    CandidateFlag,
    LlmCandidateTriage,
    RedLocation,
    RedRegister,
    RuleFire,
    RulesTriageResult,
    TriageLevel,
)
from pydantic import ValidationError

COMPLETED_AT = datetime(2026, 9, 4, 9, 30, tzinfo=UTC)

SECTION = OutputSection(
    id="chief_complaint",
    title_tr="Şikayet",
    lines=("İki gündür göğsümde baskı var.",),
)


def build(**overrides: object) -> PreVisitOutput:
    payload: dict[str, object] = {
        "visit_ref": "9f1a2b3c-0000-4000-8000-000000000001",
        "completed_at": COMPLETED_AT,
        "locale": "tr",
        "protocol_id": "previsit.dev.visit",
        "protocol_version": "int197-dev",
        "proxy_reported": False,
        "third_party_present": False,
        "sections": (SECTION,),
        "triage": TriageNotEvaluated(reason=NotEvaluatedReason.RULES_ENGINE_NOT_ON_THIS_PATH),
    }
    payload.update(overrides)
    return PreVisitOutput(**payload)  # type: ignore[arg-type]


# --- the versioned identity the receiver branches on ------------------------------------


def test_the_schema_id_is_the_repository_convention() -> None:
    assert PREVISIT_OUTPUT_SCHEMA_ID == schema_id("previsit_output", 1)
    assert build().schema_version == PREVISIT_OUTPUT_SCHEMA_ID


def test_the_schema_version_cannot_be_overstated() -> None:
    """A receiver switches on this field, so a document may not claim a
    version this build does not implement."""
    with pytest.raises(ValidationError):
        build(schema_version="intake.clinical.previsit_output.v2")


def test_the_document_is_closed_and_frozen() -> None:
    """``extra=forbid`` and ``frozen=True``: a receiver reads a value, and a
    key nobody declared is a contract nobody agreed."""
    with pytest.raises(ValidationError):
        build(hospital_note="anything")
    with pytest.raises(ValidationError):
        build().sections[0].title_tr = "rewritten"  # type: ignore[misc]


# --- invariant 1: RED/YELLOW come only from the rules engine ----------------------------


def test_an_llm_candidate_triage_cannot_be_the_documents_triage() -> None:
    """``LlmCandidateTriage`` is not a member of the union. Its discriminator
    (``llm_candidate``) resolves to nothing, so there is no coercion path and
    no field an LLM level could be written into."""
    with pytest.raises(ValidationError):
        build(triage=LlmCandidateTriage(candidate_flags=(CandidateFlag(text="t", evidence="e"),)))


def test_candidate_flags_travel_beside_the_determination_never_inside_it() -> None:
    document = build(
        llm_candidates=(CandidateFlag(text="göğüs baskısı", evidence="turn 4"),),
    )
    assert document.triage.source == "not_evaluated"
    assert len(document.llm_candidates) == 1
    served = json.loads(document.model_dump_json())
    assert served["triage"] == {
        "source": "not_evaluated",
        "reason": "rules_engine_not_on_this_path",
    }
    assert "level" not in served["triage"]


def test_an_absent_determination_has_to_say_so_out_loud() -> None:
    """``None`` is not a member: a missing key beside a list of candidate
    flags reads as 'nothing fired', which is the laundering this refuses."""
    with pytest.raises(ValidationError):
        build(triage=None)


def test_a_rules_determination_carries_its_fired_rules() -> None:
    document = build(
        triage=RulesTriageResult(
            level=TriageLevel.RED,
            rules=(RuleFire(id="base.life_threat.chest_pain", evidence="slot:agri=8"),),
            register=RedRegister.ALERT,
            location=RedLocation.REMOTE,
        )
    )
    assert document.triage.source == "rules"
    with pytest.raises(ValidationError, match="must name the rules that fired"):
        build(triage=RulesTriageResult(level=TriageLevel.YELLOW))


# --- invariant 22: number and unit are one atom, on the shared carrier ------------------


def test_a_magnitude_keeps_its_declared_scale_and_is_never_a_float() -> None:
    measure = OutputMeasurement(code=MeasureCode.WEIGHT, magnitude=Decimal("38.50"), unit="kg")
    assert isinstance(measure.magnitude, Decimal)
    assert str(measure.magnitude) == "38.50"


def test_a_magnitude_cannot_travel_without_its_unit() -> None:
    with pytest.raises(ValidationError):
        OutputMeasurement(code=MeasureCode.HEIGHT, magnitude=Decimal("170"))  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        OutputMeasurement(code=MeasureCode.HEIGHT, magnitude=Decimal("170"), unit="")


def test_measurements_are_the_only_place_a_quantity_lives() -> None:
    document = build(
        measurements=(
            OutputMeasurement(code=MeasureCode.HEIGHT, magnitude=Decimal("170"), unit="cm"),
        )
    )
    assert document.measurements[0].unit == "cm"


# --- invariant 6: no direct identifier has a field to sit in ----------------------------


def test_the_document_names_no_patient_identifier() -> None:
    """The hospital's key is what the REQUEST carries; the stored document is
    keyed on the visit alone, so no serialised previsit output in this
    repository holds a patient number, a name or a TCKN."""
    forbidden = {
        "patient_number",
        "patient_name",
        "patient_surname",
        "cell_phone",
        "tckimlik_no",
        "name",
        "phone",
    }
    assert not forbidden & set(PreVisitOutput.model_fields)


def test_a_section_id_is_id_shaped() -> None:
    with pytest.raises(ValidationError):
        OutputSection(id="not an id", title_tr="t", lines=("l",))
    with pytest.raises(ValidationError):
        OutputSection(id="chief_complaint", title_tr="t", lines=())

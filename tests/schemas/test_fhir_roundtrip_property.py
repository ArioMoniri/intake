"""INT-033 — hypothesis roundtrip properties for the FHIR R4 mappers.

The acceptance names hypothesis: "hypothesis roundtrip". Every property
drives internal → R4 → wire JSON → R4 → internal and asserts identity on the
mappable subset. Where the mapping is lossy the loss is explicit in the
mapper signature (``questionnaire_response_to_session_state`` takes the two
non-exchanged pieces) or pinned in the example lane — never silent.

All generated data is synthetic (invariant 6). files/03 §7: the mapping
layer is bidirectional and roundtrip-tested.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from clinical_schemas import (
    AllergyItem,
    CodeSystem,
    ExtractedRecordItem,
    MedicationItem,
    PmhItem,
    RecordCode,
    RecordItemKind,
    RecordProvenance,
    RuleFire,
    RulesTriageResult,
    ScreeningBlock,
    ScreeningProvenance,
    SessionBudget,
    SessionState,
    SessionStatus,
    TriageLevel,
    VerificationStatus,
)
from clinical_schemas.mappers import (
    allergy_intolerance_to_allergy_item,
    allergy_item_to_allergy_intolerance,
    condition_to_pmh_item,
    medication_item_to_medication_statement,
    medication_statement_to_medication_item,
    observations_to_screening_block,
    pmh_item_to_condition,
    questionnaire_response_to_session_state,
    r4_to_record_item,
    record_item_to_r4,
    risk_assessment_to_triage,
    screening_to_observations,
    session_state_to_questionnaire_response,
    triage_to_risk_assessment,
)
from clinical_schemas.mappers.r4 import (
    AllergyIntolerance,
    Condition,
    MedicationStatement,
    Observation,
    QuestionnaireResponse,
    R4Resource,
    RiskAssessment,
)
from clinical_schemas.triage import RedLocation, RedRegister
from hypothesis import given, settings
from hypothesis import strategies as st

SUBJECT = "urn:uuid:00000000-0000-4000-8000-000000000001"
DOC_REF = "doc-0001"

MAX_EXAMPLES = 50

# Free text: Turkish letters included, no leading/trailing whitespace so the
# FHIR string type stays lexically clean.
_text = (
    st.text(
        alphabet="abcçdefgğhıijklmnoöprsştuüvyz ABC0123456789.,-",
        min_size=1,
        max_size=30,
    )
    .map(str.strip)
    .filter(bool)
)
_code = st.from_regex(r"[A-Za-z0-9][A-Za-z0-9.\-]{0,11}", fullmatch=True)
_ref = st.from_regex(r"[A-Za-z0-9][A-Za-z0-9._:@-]{0,20}", fullmatch=True)
_sha256 = st.text(alphabet="0123456789abcdef", min_size=64, max_size=64)
_aware_dt = st.datetimes(
    min_value=datetime.datetime(2000, 1, 1),
    max_value=datetime.datetime(2035, 1, 1),
    timezones=st.sampled_from([datetime.UTC, datetime.timezone(datetime.timedelta(hours=3))]),
)
_date = st.dates(min_value=datetime.date(1990, 1, 1), max_value=datetime.date(2035, 12, 31))
_decimal = st.decimals(
    min_value=Decimal("-1000000"),
    max_value=Decimal("1000000"),
    allow_nan=False,
    allow_infinity=False,
    places=4,
)
_float = st.floats(min_value=0, max_value=1, allow_nan=False, allow_infinity=False)

_provenance = st.builds(
    RecordProvenance,
    document_ref=_ref,
    page=st.one_of(st.none(), st.integers(min_value=1, max_value=500)),
    bbox=st.one_of(st.none(), st.tuples(_float, _float, _float, _float)),
)

_record_code = st.builds(RecordCode, system=st.sampled_from(CodeSystem), code=_code)

_OBSERVABLE = (RecordItemKind.LAB, RecordItemKind.IMAGING, RecordItemKind.PROCEDURE)
_NON_OBSERVABLE = (
    RecordItemKind.MEDICATION,
    RecordItemKind.DIAGNOSIS,
    RecordItemKind.ALLERGY,
)


@st.composite
def _record_items(draw: st.DrawFn) -> ExtractedRecordItem:
    kind = draw(st.sampled_from(tuple(RecordItemKind)))
    observable = kind in _OBSERVABLE
    return ExtractedRecordItem(
        kind=kind,
        summary=draw(_text),
        code=draw(st.one_of(st.none(), _record_code)),
        value_magnitude=draw(st.one_of(st.none(), _decimal)) if observable else None,
        unit=draw(st.one_of(st.none(), _text)) if observable else None,
        unit_conflict=draw(st.booleans()) if observable else False,
        date=draw(st.one_of(st.none(), _date)),
        verification_status=draw(st.sampled_from(VerificationStatus)),
        provenance=draw(_provenance),
    )


def _reparse(resource: R4Resource) -> R4Resource:
    """Force the value across the JSON wire, exactly as HAPI would see it."""
    return type(resource).model_validate_json(resource.model_dump_json(by_alias=True))


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(item=_record_items())
def test_record_item_roundtrip(item: ExtractedRecordItem) -> None:
    resource = record_item_to_r4(item, subject_ref=SUBJECT)
    assert r4_to_record_item(_reparse(resource), document_ref=item.provenance.document_ref) == item


@st.composite
def _triage_results(draw: st.DrawFn) -> RulesTriageResult:
    level = draw(st.sampled_from(TriageLevel))
    rules: tuple[RuleFire, ...] = ()
    if level is not TriageLevel.GREEN:
        rules = tuple(
            draw(
                st.lists(
                    st.builds(RuleFire, id=_code, evidence=_text),
                    min_size=1,
                    max_size=3,
                )
            )
        )
    return RulesTriageResult(
        level=level,
        rules=rules,
        register=draw(st.sampled_from(RedRegister)) if level is TriageLevel.RED else None,
        location=draw(st.sampled_from(RedLocation)) if level is TriageLevel.RED else None,
    )


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(result=_triage_results())
def test_triage_roundtrip(result: RulesTriageResult) -> None:
    ra = triage_to_risk_assessment(result, subject_ref=SUBJECT)
    reparsed = _reparse(ra)
    assert isinstance(reparsed, RiskAssessment)
    assert risk_assessment_to_triage(reparsed) == result


_medication_items = st.builds(
    MedicationItem,
    name=_text,
    atc=st.one_of(st.none(), _code),
    dose=st.one_of(st.just(""), _text),
    adherence=st.one_of(st.just(""), _text),
    source=st.one_of(st.just(""), _text),
    reconciliation=st.sampled_from(("matches", "new", "stopped", "conflict")),
)


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(item=_medication_items)
def test_medication_item_roundtrip(item: MedicationItem) -> None:
    ms = medication_item_to_medication_statement(item, subject_ref=SUBJECT)
    reparsed = _reparse(ms)
    assert isinstance(reparsed, MedicationStatement)
    assert medication_statement_to_medication_item(reparsed) == item


_pmh_items = st.builds(
    PmhItem,
    condition=_text,
    icd10=st.one_of(st.none(), _code),
    status=st.sampled_from(("confirmed", "unconfirmed")),
    source=st.sampled_from(("patient", "record")),
)


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(item=_pmh_items)
def test_pmh_item_roundtrip(item: PmhItem) -> None:
    cond = pmh_item_to_condition(item, subject_ref=SUBJECT)
    reparsed = _reparse(cond)
    assert isinstance(reparsed, Condition)
    assert condition_to_pmh_item(reparsed) == item


_allergy_items = st.builds(
    AllergyItem,
    substance=_text,
    reaction=st.one_of(st.just(""), _text),
    severity=st.one_of(st.just(""), _text),
)


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(item=_allergy_items)
def test_allergy_item_roundtrip(item: AllergyItem) -> None:
    ai = allergy_item_to_allergy_intolerance(item, subject_ref=SUBJECT)
    reparsed = _reparse(ai)
    assert isinstance(reparsed, AllergyIntolerance)
    assert allergy_intolerance_to_allergy_item(reparsed) == item


_screening_provenances = st.builds(
    ScreeningProvenance,
    administration_mode=st.sampled_from(("voice", "typed", "keypad")),
    proxy_reported=st.booleans(),
    third_party_present=st.booleans(),
    qualifier_tr=st.one_of(st.just(""), _text),
)


@st.composite
def _screening_blocks(draw: st.DrawFn) -> ScreeningBlock:
    block = ScreeningBlock(
        phq2=draw(st.one_of(st.none(), st.integers(0, 6))),
        gad2=draw(st.one_of(st.none(), st.integers(0, 6))),
        phq9=draw(st.one_of(st.none(), st.integers(0, 27))),
        gad7=draw(st.one_of(st.none(), st.integers(0, 21))),
        provenance=draw(_screening_provenances),
    )
    if all(s is None for s in (block.phq2, block.gad2, block.phq9, block.gad7)):
        # At least one attested score, or there is nothing to exchange.
        block = block.model_copy(update={"phq2": draw(st.integers(0, 6))})
    return block


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(block=_screening_blocks(), effective=st.one_of(st.none(), _aware_dt))
def test_screening_roundtrip(block: ScreeningBlock, effective: datetime.datetime | None) -> None:
    observations = screening_to_observations(block, subject_ref=SUBJECT, effective=effective)
    reparsed = []
    for o in observations:
        r = _reparse(o)
        assert isinstance(r, Observation)
        reparsed.append(r)
    assert observations_to_screening_block(reparsed) == block


_scalars = st.one_of(
    _text,
    st.integers(min_value=-(2**31), max_value=2**31 - 1),
    st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
    st.booleans(),
)
_slot_values = st.one_of(
    _scalars,
    st.lists(_scalars, min_size=1, max_size=4).map(list),
    st.dictionaries(_text, _scalars, min_size=1, max_size=4),
)

_session_states = st.builds(
    SessionState,
    session_id=_ref,
    protocol_id=st.from_regex(r"[a-z][a-z0-9._-]{0,20}", fullmatch=True),
    protocol_version=st.from_regex(r"[0-9][0-9A-Za-z.\-]{0,10}", fullmatch=True),
    protocol_hash=_sha256,
    mode=st.sampled_from(("fast", "detailed")),
    status=st.sampled_from(SessionStatus),
    reference_time=_aware_dt,
    step_states=st.dictionaries(_text, st.sampled_from(("NOT_ASKED", "ASKED_PRESENT")), max_size=3),
    slots=st.dictionaries(_text, _slot_values, max_size=5),
    budget=st.builds(
        SessionBudget,
        turns_used=st.integers(0, 45),
        turns_remaining=st.integers(0, 45),
    ),
)


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(state=_session_states)
def test_session_state_roundtrip(state: SessionState) -> None:
    qr = session_state_to_questionnaire_response(state, subject_ref=SUBJECT)
    reparsed = _reparse(qr)
    assert isinstance(reparsed, QuestionnaireResponse)
    # step_states and budget are engine bookkeeping, not answers; the
    # signature makes that loss explicit by requiring them back.
    restored = questionnaire_response_to_session_state(
        reparsed, step_states=dict(state.step_states), budget=state.budget
    )
    assert restored == state

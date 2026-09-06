"""INT-230 — the research export gate (files/06 §8, §3; KVKK-16, KSVY-16, ETİK).

Acceptance, verbatim from docs/backlog/issues.yaml:
  "exports only with research consent + ethics id; anonymisation validated on
   corpus; register of research extracts"

sec_row: `learning-loops`.  legal: KVKK-16, KSVY-16, ETİK.

**The word this suite refuses.** KSVY m.16(1) permits scientific work on
health data *anonim hâle getirilen* — anonymised — by the controller. What
this pipeline can actually produce is a **keyed pseudonym plus a closed
vocabulary**: reversible in principle by whoever holds the tokenization key,
and therefore personal data. So the artefact is named
:class:`PseudonymisedExtract` and rides the OTHER route files/06 §75 states —
*"All research consented (`research`) or anonymised per KSVY-16; ethics IDs
recorded on every export"* — the consent route, with the ethics id. Nothing
here calls itself anonymised, and a test holds that line by name.

**What "validated on corpus" means here, stated narrowly.** The INT-015
corpus is used to validate an **exclusion rule**, not a scrubber. Two things
it proves: no corpus sentence can become an export value (the carrier is
refused), and no bare corpus identifier can either — a TCKN and a mobile
number are *id-shaped*, so a shape rule alone would have admitted both. The
pattern tier adds refusals; acceptance comes only from the study's declared
closed vocabulary. files/10 §3 and HB-L6 are why de-identified Turkish free
text is not a claim this repo makes at all.
"""

from __future__ import annotations

import ast
import json
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from api_harness import run
from conftest import RESEARCH_TENANT_ID, ResearchHarness
from intake_platform.analytics import K_ANONYMITY_FLOOR, KAnonymityRefusal, ThresholdBelowFloor
from intake_platform.analytics import Cohort as AnalyticsCohort
from intake_platform.research import (
    RESEARCH_SCOPE,
    ExtractRecord,
    ExtractRegister,
    InMemoryExtractRegisterStore,
    PseudonymisedExtract,
    ResearchExportGate,
    ResearchExportRefused,
    ResearchExtractSpec,
    ResearchRefusalReason,
    StudyApprovalLapsedError,
    StudyApprovalNotYetInForceError,
    StudyRecord,
    StudyRegistry,
    StudyRegistryError,
    SubjectRow,
    UnknownStudyError,
    check_export_value,
    load_default_registry,
    load_registry,
)
from intake_platform.retention import DestroyableClass, RetentionPolicy, load_default_policy
from intake_platform.tokenization import Tokenizer
from sqlalchemy.ext.asyncio import AsyncSession

REPO = Path(__file__).resolve().parents[2]
CORPUS = REPO / "tests" / "fixtures" / "deid" / "pattern_corpus.jsonl"
VENDORED = REPO / "tests" / "fixtures" / "deid" / "vendor" / "pii_corpus.jsonl"

RESEARCH_SRC = REPO / "packages" / "intake_platform" / "src" / "intake_platform" / "research"

# --- fixture study, ethics id and recipient ----------------------------------------
#
# EVERY value below is synthetic test data, and that is the whole point: no
# study exists, no ethics approval exists, no recipient is approved, and none
# of those may be invented (CLAUDE.md; HUMAN_BLOCKERS.md rule 1). The shipped
# registry is empty; these rows exist only to prove the gate WOULD serve a
# real study, so the refusals below are refusals of a working gate rather
# than of a gate that refuses everything by accident.
FIXTURE_STUDY_ID = "unit.lane.study"
FIXTURE_ETHICS_ID = "unit.lane.approval"
FIXTURE_RECIPIENT = "unit.lane.investigator"
APPROVED_FROM = date(2026, 1, 1)
APPROVED_UNTIL = date(2026, 12, 31)
INSIDE_APPROVAL = datetime(2026, 6, 1, tzinfo=UTC)

WINDOW = AnalyticsCohort(
    description="unit-lane research cohort",
    window_start=datetime(2026, 1, 1, tzinfo=UTC),
    window_end=datetime(2026, 7, 1, tzinfo=UTC),
)

#: A window disjoint from ``WINDOW`` (INT-262: the differencing gate refuses a
#: second extract whose window OVERLAPS a prior one under the same study+spec,
#: so a test that legitimately needs two served extracts uses two windows that
#: do not intersect). Its own suite is tests/research/test_differencing_gate.py.
WINDOW_LATER = AnalyticsCohort(
    description="unit-lane research cohort, later and disjoint",
    window_start=datetime(2026, 8, 1, tzinfo=UTC),
    window_end=datetime(2026, 10, 1, tzinfo=UTC),
)

SPEC = ResearchExtractSpec(
    name="research.voice_vs_typed",
    dimensions={
        "profile": ("residency_tr", "typed"),
        "protocol_id": ("base.intake",),
        "week_start": ("2026-W02", "2026-W03"),
    },
    measures=("sessions",),
    cohort_description="research-consented intake sessions by delivery profile and ISO week",
    narrative_exclusion=(
        "counts and declared enumeration members only; no transcript, note, "
        "slot value or document reaches this spec (files/10 §3, HB-L6)"
    ),
)


def fixture_registry(
    *,
    study_id: str = FIXTURE_STUDY_ID,
    approval_date: date = APPROVED_FROM,
    approval_valid_until: date = APPROVED_UNTIL,
    recipients: tuple[str, ...] = (FIXTURE_RECIPIENT,),
) -> StudyRegistry:
    return StudyRegistry(
        studies=(
            StudyRecord(
                study_id=study_id,
                site="unit.lane.site",
                ethics_committee="unit.lane.committee",
                ethics_approval_id=FIXTURE_ETHICS_ID,
                approval_date=approval_date,
                approval_valid_until=approval_valid_until,
                protocol_version="v0",
                recipients=recipients,
            ),
        )
    )


def sourced_retention() -> RetentionPolicy:
    """The committed policy with the research row given a duration — the
    post-HB-I8/ethics-protocol world, in miniature. Tests that exercise the
    SHIPPED refusal use ``load_default_policy()`` instead."""
    raw = json.loads(load_default_policy().model_dump_json())
    for row in raw["classes"]:
        if row["data_class"] == DestroyableClass.RESEARCH_EXTRACTS.value:
            row["retention"] = {"kind": "years", "years": 1}
            row["status"] = "sourced"
            row["source"] = "unit-lane fixture: a stand-in for the ethics protocol's figure"
    return RetentionPolicy.model_validate(raw)


def tokenizer() -> Tokenizer:
    return Tokenizer({"v1": b"unit-lane-tokenization-key"}, "v1")


def build_gate(
    research: ResearchHarness,
    *,
    registry: StudyRegistry | None = None,
    retention: RetentionPolicy | None = None,
    now: datetime = INSIDE_APPROVAL,
) -> tuple[ResearchExportGate, ExtractRegister]:
    register = ExtractRegister(InMemoryExtractRegisterStore())
    gate = ResearchExportGate(
        registry=registry if registry is not None else fixture_registry(),
        retention=retention if retention is not None else sourced_retention(),
        tokenizer=tokenizer(),
        register=register,
        audit=research.audit,
        catalog=research.catalog,
        clock=lambda: now,
    )
    return gate, register


def rows_for(
    ids: tuple[uuid.UUID, ...], *, profile: str = "residency_tr"
) -> tuple[SubjectRow, ...]:
    return tuple(
        SubjectRow(
            patient_id=pid,
            dimensions={
                "profile": profile,
                "protocol_id": "base.intake",
                "week_start": "2026-W02",
            },
            measures={"sessions": 1},
        )
        for pid in ids
    )


def consented_pack(research: ResearchHarness, count: int) -> tuple[uuid.UUID, ...]:
    ids = research.seed_patients(count)
    for pid in ids:
        research.grant(pid, RESEARCH_SCOPE)
    return ids


def build(
    gate: ResearchExportGate,
    research: ResearchHarness,
    candidates: tuple[SubjectRow, ...],
    *,
    study_id: str = FIXTURE_STUDY_ID,
    recipient: str = FIXTURE_RECIPIENT,
    k: int = K_ANONYMITY_FLOOR,
    cohort: AnalyticsCohort = WINDOW,
) -> PseudonymisedExtract:
    async def _build() -> PseudonymisedExtract:
        async with AsyncSession(research.engine) as session:
            return await gate.build(
                session,
                tenant_id=RESEARCH_TENANT_ID,
                study_id=study_id,
                recipient=recipient,
                requested_by="unit-lane-analyst",
                spec=SPEC,
                cohort=cohort,
                k=k,
                candidates=candidates,
            )

    result = run(_build())
    assert isinstance(result, PseudonymisedExtract)
    return result


# --- the shipped registry is empty, and that is the deliverable ---------------------


def test_the_shipped_study_registry_holds_no_study() -> None:
    """No study is registered, because no study exists: HB-L1 has not named
    the site and no KAEK approval id has been issued. The mechanism ships and
    the content is empty (HUMAN_BLOCKERS.md rule 2)."""
    assert load_default_registry().studies == ()


def test_the_shipped_registry_file_records_why_it_is_empty() -> None:
    text = (RESEARCH_SRC / "study_registry.yaml").read_text(encoding="utf-8")
    assert "HB-L1" in text
    assert "HB-R1" in text


def test_an_export_naming_no_registered_study_is_refused(research: ResearchHarness) -> None:
    ids = consented_pack(research, K_ANONYMITY_FLOOR + 2)
    gate, _ = build_gate(research, registry=load_default_registry())
    with pytest.raises(UnknownStudyError):
        build(gate, research, rows_for(ids))


# --- ethics approval: three independent refusals, no grace -------------------------


def test_an_approval_that_has_lapsed_refuses_with_no_grace(research: ResearchHarness) -> None:
    ids = consented_pack(research, K_ANONYMITY_FLOOR + 2)
    last_valid = datetime(APPROVED_UNTIL.year, APPROVED_UNTIL.month, APPROVED_UNTIL.day, tzinfo=UTC)
    gate, _ = build_gate(research, now=last_valid)
    build(gate, research, rows_for(ids))  # the last valid day still serves

    lapsed, _ = build_gate(research, now=last_valid + timedelta(days=1))
    with pytest.raises(StudyApprovalLapsedError):
        build(lapsed, research, rows_for(ids))


def test_an_approval_not_yet_in_force_refuses(research: ResearchHarness) -> None:
    ids = consented_pack(research, K_ANONYMITY_FLOOR + 2)
    gate, _ = build_gate(research, now=datetime(2025, 12, 31, tzinfo=UTC))
    with pytest.raises(StudyApprovalNotYetInForceError):
        build(gate, research, rows_for(ids))


def test_a_recipient_outside_the_study_is_refused(research: ResearchHarness) -> None:
    ids = consented_pack(research, K_ANONYMITY_FLOOR + 2)
    gate, _ = build_gate(research)
    with pytest.raises(ResearchExportRefused) as caught:
        build(gate, research, rows_for(ids), recipient="someone.else")
    assert caught.value.reason is ResearchRefusalReason.RECIPIENT_NOT_APPROVED


# --- retention: an extract with no clock may not be created ------------------------


def test_the_shipped_retention_policy_refuses_a_research_extract(
    research: ResearchHarness,
) -> None:
    """files/06 §3 says "Research extracts: per ethics protocol" and no ethics
    protocol exists, so the row is ``draft_needs_source``. Creating data whose
    destruction date nobody can state is the KVKK-7 failure this refuses."""
    ids = consented_pack(research, K_ANONYMITY_FLOOR + 2)
    gate, _ = build_gate(research, retention=load_default_policy())
    with pytest.raises(ResearchExportRefused) as caught:
        build(gate, research, rows_for(ids))
    assert caught.value.reason is ResearchRefusalReason.RETENTION_UNSET


# --- consent: dropped, never flagged ----------------------------------------------


def test_a_patient_who_never_answered_is_dropped(research: ResearchHarness) -> None:
    """``research`` is off by default (files/06 §2), so silence is not consent
    and an unanswered patient never enters the cohort."""
    ids = research.seed_patients(K_ANONYMITY_FLOOR + 2)
    for pid in ids[:-1]:
        research.grant(pid, RESEARCH_SCOPE)
    gate, register = build_gate(research)
    extract = build(gate, research, rows_for(ids))
    assert extract.subjects == K_ANONYMITY_FLOOR + 1
    assert register.records()[0].subjects == K_ANONYMITY_FLOOR + 1


def test_a_patient_who_withdrew_is_dropped_and_not_flagged(research: ResearchHarness) -> None:
    ids = consented_pack(research, K_ANONYMITY_FLOOR + 2)
    refuser = ids[3]
    research.withdraw(refuser, RESEARCH_SCOPE)

    gate, register = build_gate(research)
    extract = build(gate, research, rows_for(ids))

    assert extract.subjects == K_ANONYMITY_FLOOR + 1
    # Dropped means absent: not a row, not a flag, not a count of refusals.
    # The audit half looks only at what the EXPORT wrote — the withdrawal's own
    # `consent.withdraw` entry is INT-038's and has to be there.
    blob = json.dumps(
        {
            "extract": [
                {"pseudonym": row.pseudonym, **dict(row.dimensions)} for row in extract.rows
            ],
            "register": [record.__dict__ for record in register.records()],
            "audit": [
                entry.__dict__
                for entry in research.chain._store.entries()  # noqa: SLF001
                if entry.action.startswith("research.")
            ],
        },
        default=str,
    )
    assert str(refuser) not in blob
    for leak in ("refus", "withdraw", "declin", "opt_out", "excluded"):
        assert leak not in blob.lower(), f"the export recorded who said no: {leak}"


def test_a_stale_grant_is_dropped(research: ResearchHarness, tmp_path: Path) -> None:
    """A grant bound to a superseded text is not a live consent (INT-038's
    ``stale``), and the export treats it exactly as an absence."""
    ids = consented_pack(research, K_ANONYMITY_FLOOR + 2)
    stale = ids[0]
    # move the shown text: every existing hash binding is now superseded
    path = research.catalog.root / "research.tr.md"
    path.write_text(
        "---\nconsent_text_version: 2026-09-01.1\n---\nRevised synthetic fixture body.\n",
        encoding="utf-8",
    )
    for pid in ids:
        if pid != stale:
            research.grant(pid, RESEARCH_SCOPE)

    gate, _ = build_gate(research)
    extract = build(gate, research, rows_for(ids))
    assert extract.subjects == K_ANONYMITY_FLOOR + 1


def test_the_export_consults_the_research_scope_and_not_a_neighbouring_one(
    research: ResearchHarness,
) -> None:
    """A patient who granted everything EXCEPT research is not in a research
    export. Care consent is not research consent."""
    ids = research.seed_patients(K_ANONYMITY_FLOOR + 2)
    for pid in ids:
        for scope in ("core", "voice", "documents", "learning:service_improvement"):
            research.grant(pid, scope)
    gate, _ = build_gate(research)
    with pytest.raises(KAnonymityRefusal):
        build(gate, research, rows_for(ids))


# --- the floor is imported, not chosen ---------------------------------------------


def test_the_cohort_floor_is_imported_and_never_redefined() -> None:
    """INT-240/INT-171's rule: two copies of a privacy threshold are two
    chances for one of them to drift down. The research package states no
    number of its own."""
    sources = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(RESEARCH_SRC.glob("*.py"))
    )
    assert "K_ANONYMITY_FLOOR" in sources
    for forbidden in ("MIN_COHORT =", "MIN_COHORT=", "k_floor =", "= 10"):
        assert forbidden not in sources, f"the research package defines its own floor: {forbidden}"


def test_a_threshold_below_the_floor_is_refused(research: ResearchHarness) -> None:
    ids = consented_pack(research, K_ANONYMITY_FLOOR + 2)
    gate, _ = build_gate(research)
    with pytest.raises(ThresholdBelowFloor):
        build(gate, research, rows_for(ids), k=K_ANONYMITY_FLOOR - 1)


def test_a_cohort_one_short_of_the_floor_refuses(research: ResearchHarness) -> None:
    ids = consented_pack(research, K_ANONYMITY_FLOOR - 1)
    gate, _ = build_gate(research)
    with pytest.raises(KAnonymityRefusal):
        build(gate, research, rows_for(ids))


def test_one_thin_quasi_identifier_cell_refuses_the_whole_extract(
    research: ResearchHarness,
) -> None:
    """Not suppressed — refused. A reader holding every cell but one recovers
    the missing one by subtraction from any wider aggregate."""
    ids = consented_pack(research, K_ANONYMITY_FLOOR + 2)
    healthy = rows_for(ids[:-1])
    thin = rows_for(ids[-1:], profile="typed")  # a single patient alone on `typed`
    gate, register = build_gate(research)
    with pytest.raises(KAnonymityRefusal):
        build(gate, research, healthy + thin)
    assert register.records() == (), "a refused export must not enter the register"


def test_an_empty_cohort_and_a_thin_cohort_refuse_identically(research: ResearchHarness) -> None:
    """The refusal is not an oracle: "refused" must not mean "someone was
    there, but fewer than k"."""
    research.seed_patients(K_ANONYMITY_FLOOR + 2)
    gate, _ = build_gate(research)
    with pytest.raises(KAnonymityRefusal) as empty:
        build(gate, research, ())

    ids = consented_pack(research, 2)
    with pytest.raises(KAnonymityRefusal) as thin:
        build(gate, research, rows_for(ids))
    assert str(empty.value) == str(thin.value)


def test_one_patient_wearing_many_rows_is_still_one_subject(research: ResearchHarness) -> None:
    """Rows are not people (the INT-171 rule). A chronic patient with a row
    per visit must not inflate a cohort past the floor — and asking the
    ledger once per patient rather than once per row is what makes the count
    a count of people."""
    ids = consented_pack(research, 3)
    inflated = tuple(row for _ in range(K_ANONYMITY_FLOOR) for row in rows_for(ids))
    assert len(inflated) > K_ANONYMITY_FLOOR
    gate, _ = build_gate(research)
    with pytest.raises(KAnonymityRefusal):
        build(gate, research, inflated)


def test_no_order_statistic_may_be_declared_as_a_measure() -> None:
    """A min or a max is one real patient's value at any cohort size, so it
    is not a measure this export can carry (the INT-240/INT-241 rule)."""
    for name in ("age_min", "max_duration", "earliest_visit", "latest_note", "first_seen"):
        with pytest.raises(ResearchExportRefused) as caught:
            ResearchExtractSpec(
                name="research.bad",
                dimensions={"profile": ("typed",)},
                measures=(name,),
                cohort_description="x",
                narrative_exclusion="x",
            )
        assert caught.value.reason is ResearchRefusalReason.ORDER_STATISTIC_MEASURE


# --- the exclusion rule, validated on the INT-015 corpus ---------------------------


def corpus_rows(path: Path) -> list[dict]:  # type: ignore[type-arg]
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_no_corpus_sentence_can_become_an_export_value() -> None:
    """The carrier is refused: a Turkish sentence has spaces and is long, so
    it cannot be a dimension value at all."""
    total = 0
    for path in (CORPUS, VENDORED):
        for row in corpus_rows(path):
            total += 1
            with pytest.raises(ResearchExportRefused):
                check_export_value("profile", row["text"])
    assert total >= 25, "corpus shrank — the gate needs its cases"


def test_no_bare_corpus_identifier_can_become_an_export_value() -> None:
    """The sharp half. A TCKN, a mobile number and an IBAN are all *id-shaped*
    — a shape rule alone would have admitted every one of them. This is what
    the corpus validates."""
    checked = 0
    for path in (CORPUS, VENDORED):
        for row in corpus_rows(path):
            for entity in row["entities"]:
                if entity["type"] not in {"TCKN", "PHONE", "IBAN", "EMAIL", "DATE"}:
                    continue
                value = entity["value"]
                checked += 1
                with pytest.raises(ResearchExportRefused) as caught:
                    check_export_value("profile", value)
                assert caught.value.reason in {
                    ResearchRefusalReason.VALUE_CARRIES_IDENTIFIER,
                    ResearchRefusalReason.VALUE_NOT_ID_SHAPED,
                }
                assert value not in str(caught.value), "the refusal echoed what it refused"
    assert checked >= 25, "corpus shrank — the identifier gate needs its cases"


#: Not a credential. ``Deidentifier.subject_key`` keys the per-subject DATE
#: SHIFT, and this test never shifts a date — it only asks whether a scrubbed
#: sentence is still refused as an export value. Held in a named constant so
#: no entropic literal sits beside the word ``subject_key`` (the secret
#: scanner reads that pairing, correctly, as an API-key shape).
CORPUS_SUBJECT = "corpus"


def test_a_scrubbed_corpus_sentence_is_still_refused() -> None:
    """Scrubbing is not a route in. ``[PERSON] ile 05… `` is still a sentence,
    and this pipeline admits values from a declared vocabulary only."""
    from intake_platform.deid import Deidentifier  # noqa: PLC0415

    engine = Deidentifier(ner_model_dir=None, subject_key=CORPUS_SUBJECT)
    for row in corpus_rows(CORPUS):
        with pytest.raises(ResearchExportRefused):
            check_export_value("profile", engine.deidentify(row["text"]))


def test_a_value_outside_the_declared_vocabulary_is_refused(research: ResearchHarness) -> None:
    """A bare ASCII given name is id-shaped and carries no pattern identifier.
    The closed vocabulary is what stops it — not the shape rule, and not the
    de-identifier."""
    ids = consented_pack(research, K_ANONYMITY_FLOOR + 2)
    rows = list(rows_for(ids))
    rows[0] = SubjectRow(
        patient_id=ids[0],
        dimensions={"profile": "Ahmet", "protocol_id": "base.intake", "week_start": "2026-W02"},
        measures={"sessions": 1},
    )
    gate, _ = build_gate(research)
    with pytest.raises(ResearchExportRefused) as caught:
        build(gate, research, tuple(rows))
    assert caught.value.reason is ResearchRefusalReason.VALUE_OUTSIDE_VOCABULARY
    assert "Ahmet" not in str(caught.value)


def test_a_measure_that_is_not_a_count_is_refused(research: ResearchHarness) -> None:
    ids = consented_pack(research, K_ANONYMITY_FLOOR + 2)
    rows = list(rows_for(ids))
    rows[0] = SubjectRow(
        patient_id=ids[0],
        dimensions=dict(rows[0].dimensions),
        measures={"sessions": "üç seans"},  # type: ignore[dict-item]
    )
    gate, _ = build_gate(research)
    with pytest.raises(ResearchExportRefused) as caught:
        build(gate, research, tuple(rows))
    assert caught.value.reason is ResearchRefusalReason.MEASURE_NOT_A_COUNT


# --- pseudonymisation, named as such ----------------------------------------------


def test_the_package_never_names_anything_anonymised() -> None:
    """KSVY m.16(1)'s route is anonymisation and this is not it. A public name
    that claimed otherwise would be the error that ends a study."""
    import intake_platform.research as research_pkg  # noqa: PLC0415

    for name in research_pkg.__all__:
        assert "anonym" not in name.lower(), f"{name} claims anonymisation"
    assert "pseudonymisation, not anonymisation" in (research_pkg.__doc__ or "")


def test_the_pseudonym_is_study_scoped_and_stable(research: ResearchHarness) -> None:
    ids = consented_pack(research, K_ANONYMITY_FLOOR + 2)
    gate_a, _ = build_gate(research)
    first = build(gate_a, research, rows_for(ids))
    # A rebuild over a DISJOINT window: INT-262 refuses a second extract whose
    # window overlaps the first, and the pseudonym is keyed on study+patient,
    # not the window, so it is stable across windows.
    again = build(gate_a, research, rows_for(ids), cohort=WINDOW_LATER)
    assert {r.pseudonym for r in first.rows} == {r.pseudonym for r in again.rows}

    gate_b, _ = build_gate(research, registry=fixture_registry(study_id="unit.lane.other"))
    other = build(gate_b, research, rows_for(ids), study_id="unit.lane.other")
    assert {r.pseudonym for r in first.rows}.isdisjoint({r.pseudonym for r in other.rows})


def test_no_patient_id_survives_into_the_extract(research: ResearchHarness) -> None:
    ids = consented_pack(research, K_ANONYMITY_FLOOR + 2)
    gate, _ = build_gate(research)
    extract = build(gate, research, rows_for(ids))
    blob = json.dumps([{"p": r.pseudonym, **dict(r.dimensions)} for r in extract.rows])
    for pid in ids:
        assert str(pid) not in blob
        assert pid.hex not in blob


def test_the_provenance_sentence_says_pseudonymised_not_anonymised(
    research: ResearchHarness,
) -> None:
    """Invariant 20's sentence, with the KVKK qualification attached: a
    methods section that copies this cannot accidentally claim anonymity."""
    ids = consented_pack(research, K_ANONYMITY_FLOOR + 2)
    gate, _ = build_gate(research)
    provenance = build(gate, research, rows_for(ids)).provenance
    assert FIXTURE_ETHICS_ID in provenance
    assert "NOT anonymised" in provenance
    assert f"k={K_ANONYMITY_FLOOR}" in provenance


# --- the spec and the registry refuse malformed declarations ----------------------


def test_a_spec_with_no_dimension_is_refused() -> None:
    with pytest.raises(ResearchExportRefused) as caught:
        ResearchExtractSpec(
            name="research.bad",
            dimensions={},
            measures=("sessions",),
            cohort_description="x",
            narrative_exclusion="x",
        )
    assert caught.value.reason is ResearchRefusalReason.DIMENSION_SET_MISMATCH


def test_a_dimension_with_an_open_vocabulary_is_refused() -> None:
    with pytest.raises(ResearchExportRefused) as caught:
        ResearchExtractSpec(
            name="research.bad",
            dimensions={"profile": ()},
            measures=("sessions",),
            cohort_description="x",
            narrative_exclusion="x",
        )
    assert caught.value.reason is ResearchRefusalReason.VALUE_OUTSIDE_VOCABULARY


def test_a_spec_with_no_measure_is_refused() -> None:
    with pytest.raises(ResearchExportRefused) as caught:
        ResearchExtractSpec(
            name="research.bad",
            dimensions={"profile": ("typed",)},
            measures=(),
            cohort_description="x",
            narrative_exclusion="x",
        )
    assert caught.value.reason is ResearchRefusalReason.MEASURE_NOT_A_COUNT


def test_a_spec_name_that_is_not_id_shaped_is_refused_without_echo() -> None:
    with pytest.raises(ResearchExportRefused) as caught:
        ResearchExtractSpec(
            name="Hasta Ahmet'in seansları",
            dimensions={"profile": ("typed",)},
            measures=("sessions",),
            cohort_description="x",
            narrative_exclusion="x",
        )
    assert caught.value.reason is ResearchRefusalReason.SPEC_FIELD_NOT_ID_SHAPED
    assert "Ahmet" not in str(caught.value)


def test_a_spec_cannot_declare_an_identifier_as_a_vocabulary_member() -> None:
    """Where the pattern tier actually bites. Once a vocabulary is declared,
    every admitted value is a member of it — so the tier's real job is to stop
    a SPEC AUTHOR from declaring an identifier as a member in the first place,
    which is a mistake no downstream check would catch."""
    with pytest.raises(ResearchExportRefused) as caught:
        ResearchExtractSpec(
            name="research.bad",
            dimensions={"tckn": ("10000000146",)},
            measures=("sessions",),
            cohort_description="x",
            narrative_exclusion="x",
        )
    assert caught.value.reason is ResearchRefusalReason.VALUE_CARRIES_IDENTIFIER
    assert "10000000146" not in str(caught.value)


def test_a_row_whose_dimensions_are_not_the_declared_set_is_refused(
    research: ResearchHarness,
) -> None:
    ids = consented_pack(research, K_ANONYMITY_FLOOR + 2)
    rows = list(rows_for(ids))
    rows[0] = SubjectRow(
        patient_id=ids[0],
        dimensions={"profile": "typed"},  # protocol_id and week_start missing
        measures={"sessions": 1},
    )
    gate, _ = build_gate(research)
    with pytest.raises(ResearchExportRefused) as caught:
        build(gate, research, tuple(rows))
    assert caught.value.reason is ResearchRefusalReason.DIMENSION_SET_MISMATCH


def test_a_row_whose_measures_are_not_the_declared_set_is_refused(
    research: ResearchHarness,
) -> None:
    ids = consented_pack(research, K_ANONYMITY_FLOOR + 2)
    rows = list(rows_for(ids))
    rows[0] = SubjectRow(
        patient_id=ids[0],
        dimensions=dict(rows[0].dimensions),
        measures={"sessions": 1, "notes": 1},
    )
    gate, _ = build_gate(research)
    with pytest.raises(ResearchExportRefused) as caught:
        build(gate, research, tuple(rows))
    assert caught.value.reason is ResearchRefusalReason.MEASURE_NOT_A_COUNT


def test_a_dimension_value_carrying_a_tckn_is_refused_through_the_gate(
    research: ResearchHarness,
) -> None:
    """The corpus proves the value check; this proves the gate reaches it, and
    that the refusal is audited without the identifier."""
    ids = consented_pack(research, K_ANONYMITY_FLOOR + 2)
    rows = list(rows_for(ids))
    tckn = "10000000146"  # checksum-valid, synthetic
    rows[0] = SubjectRow(
        patient_id=ids[0],
        dimensions={"profile": tckn, "protocol_id": "base.intake", "week_start": "2026-W02"},
        measures={"sessions": 1},
    )
    gate, _ = build_gate(research)
    with pytest.raises(ResearchExportRefused) as caught:
        build(gate, research, tuple(rows))
    assert caught.value.reason is ResearchRefusalReason.VALUE_CARRIES_IDENTIFIER
    assert tckn not in str(caught.value)
    entries = [entry for entry in research.chain._store.entries()]  # noqa: SLF001
    assert all(tckn not in json.dumps(entry.__dict__) for entry in entries)


def test_a_registry_field_that_is_not_id_shaped_is_refused_without_echo() -> None:
    with pytest.raises(ValueError) as caught:
        StudyRecord(
            study_id="Acıbadem KAEK çalışması",
            site="s",
            ethics_committee="c",
            ethics_approval_id="a",
            approval_date=APPROVED_FROM,
            approval_valid_until=APPROVED_UNTIL,
            protocol_version="v0",
            recipients=("r",),
        )
    assert "Acıbadem" not in str(caught.value)


def test_a_study_needs_at_least_one_recipient() -> None:
    """An empty recipient list is an open-ended transfer, not a study with a
    blank field."""
    with pytest.raises(ValueError):
        StudyRecord(
            study_id="s",
            site="s",
            ethics_committee="c",
            ethics_approval_id="a",
            approval_date=APPROVED_FROM,
            approval_valid_until=APPROVED_UNTIL,
            protocol_version="v0",
            recipients=(),
        )


def test_an_approval_window_must_move_forward() -> None:
    with pytest.raises(ValueError):
        StudyRecord(
            study_id="s",
            site="s",
            ethics_committee="c",
            ethics_approval_id="a",
            approval_date=APPROVED_UNTIL,
            approval_valid_until=APPROVED_FROM,
            protocol_version="v0",
            recipients=("r",),
        )


def test_a_registry_cannot_hold_two_rows_for_one_study() -> None:
    """TCKAY m.11 makes an amendment a fresh submission — a new row, not a
    second row under the same id that resolution would have to choose
    between."""
    with pytest.raises(ValueError):
        StudyRegistry(studies=fixture_registry().studies + fixture_registry().studies)


def test_a_registry_that_is_not_a_mapping_document_refuses(tmp_path: Path) -> None:
    path = tmp_path / "registry.yaml"
    path.write_text("- not: a mapping\n", encoding="utf-8")
    with pytest.raises(StudyRegistryError):
        load_registry(path)


def test_the_registry_resolves_only_the_study_it_was_asked_for() -> None:
    registry = StudyRegistry(
        studies=fixture_registry().studies + fixture_registry(study_id="other.study").studies
    )
    assert registry.resolve("other.study", on=APPROVED_FROM).study_id == "other.study"
    with pytest.raises(UnknownStudyError):
        registry.resolve("third.study", on=APPROVED_FROM)


# --- the register of research extracts --------------------------------------------


def test_every_served_extract_lands_in_the_register_with_its_ethics_id(
    research: ResearchHarness,
) -> None:
    ids = consented_pack(research, K_ANONYMITY_FLOOR + 2)
    gate, register = build_gate(research)
    extract = build(gate, research, rows_for(ids))

    records = register.records()
    assert len(records) == 1
    record = records[0]
    assert isinstance(record, ExtractRecord)
    assert record.study_id == FIXTURE_STUDY_ID
    assert record.ethics_approval_id == FIXTURE_ETHICS_ID
    assert record.recipient == FIXTURE_RECIPIENT
    assert record.content_sha256 == extract.content_sha256
    assert record.k == K_ANONYMITY_FLOOR
    assert record.subjects == K_ANONYMITY_FLOOR + 2


def test_the_register_carries_no_patient_id_and_no_pseudonym(research: ResearchHarness) -> None:
    ids = consented_pack(research, K_ANONYMITY_FLOOR + 2)
    gate, register = build_gate(research)
    extract = build(gate, research, rows_for(ids))
    blob = json.dumps([record.__dict__ for record in register.records()], default=str)
    for pid in ids:
        assert str(pid) not in blob
    for row in extract.rows:
        assert row.pseudonym not in blob


def test_the_register_is_append_only(research: ResearchHarness) -> None:
    ids = consented_pack(research, K_ANONYMITY_FLOOR + 2)
    gate, register = build_gate(research)
    build(gate, research, rows_for(ids))
    # A second, DISJOINT window so both serve — INT-262 refuses an overlapping
    # one, and the property under test here is the register's, not the gate's.
    build(gate, research, rows_for(ids), cohort=WINDOW_LATER)
    assert len(register.records()) == 2
    assert not hasattr(register, "delete")
    assert not hasattr(register, "update")


def test_the_register_answers_the_question_an_ethics_committee_asks(
    research: ResearchHarness,
) -> None:
    """ "What has been taken under my approval?" — one call, and it does not
    return another study's rows."""
    ids = consented_pack(research, K_ANONYMITY_FLOOR + 2)
    gate, register = build_gate(research)
    build(gate, research, rows_for(ids))
    assert len(register.for_study(FIXTURE_STUDY_ID)) == 1
    assert register.for_study("some.other.study") == ()


def test_a_register_row_cannot_record_a_cohort_below_its_own_threshold() -> None:
    """A guard on the type, not on the writer: a row asserting 4 subjects at
    k=10 would be a record of something the gate cannot have served."""
    with pytest.raises(ValueError):
        ExtractRecord(
            content_sha256="0" * 64,
            study_id=FIXTURE_STUDY_ID,
            ethics_approval_id=FIXTURE_ETHICS_ID,
            protocol_version="v0",
            recipient=FIXTURE_RECIPIENT,
            requested_by="analyst",
            spec_name=SPEC.name,
            window_start=WINDOW.window_start.isoformat(),
            window_end=WINDOW.window_end.isoformat(),
            subjects=4,
            k=K_ANONYMITY_FLOOR,
            recorded_at=INSIDE_APPROVAL.isoformat(),
        )


def test_a_register_timestamp_must_carry_a_timezone() -> None:
    with pytest.raises(ValueError):
        ExtractRegister.recorded_at(datetime(2026, 6, 1))  # noqa: DTZ001


# --- every share is audited (invariant 4) -----------------------------------------


def actions(research: ResearchHarness) -> list[str]:
    return [entry.action for entry in research.chain._store.entries()]  # noqa: SLF001


def test_a_served_extract_is_audited_in_the_hash_chain(research: ResearchHarness) -> None:
    ids = consented_pack(research, K_ANONYMITY_FLOOR + 2)
    gate, _ = build_gate(research)
    build(gate, research, rows_for(ids))
    assert "research.extract.served" in actions(research)
    assert research.chain.verify().ok


def test_a_refused_export_is_audited_with_a_reason_class_and_nothing_else(
    research: ResearchHarness,
) -> None:
    ids = consented_pack(research, K_ANONYMITY_FLOOR + 2)
    gate, _ = build_gate(research, registry=load_default_registry())
    with pytest.raises(UnknownStudyError):
        build(gate, research, rows_for(ids))
    refusals = [action for action in actions(research) if action.startswith("research.extract.")]
    assert refusals == ["research.extract.refused.unknown_study"]
    assert research.chain.verify().ok


# --- narrative is excluded, not scrubbed ------------------------------------------


# The AST gates below replace an earlier substring scan, and the upgrade is
# INT-172's (tests/learning/test_proposal_scope.py on int-172-learning, not yet
# merged): a scan that greps source text misses `from x import Note as N`, an
# aliased module, and a name that only ever appears as an attribute. Parsing is
# not optional rigour here — the whole claim of this package is about what it
# CANNOT reach.
#
# What is deliberately NOT copied is INT-172's transitive closure. That gate
# suits a package that must never touch the ORM at all; this one must, because
# evaluating the `research` consent scope means reading the consents table
# through `consent_state`, whose own closure legitimately reaches
# `intake_platform.db.models` — where `Note` and `Slot` also live. A transitive
# ban would therefore be either false or vacuous. The honest boundary for this
# package is narrower and is stated as three separate gates: a declared
# first-party allow-list, no narrative NAME bound or touched anywhere, and no
# query composed at all. The grant remains the real narrative boundary, exactly
# as INT-171 recorded it.

#: Every first-party module the research package may import. A new entry is a
#: deliberate widening of what this code can reach, reviewable as one line.
RESEARCH_IMPORT_ALLOW_LIST = frozenset(
    {
        "intake_platform.analytics",
        "intake_platform.consent",
        "intake_platform.consent.service",
        "intake_platform.deid",
        "intake_platform.research.artefact",
        "intake_platform.research.extract",
        "intake_platform.research.register",
        "intake_platform.research.studies",
        "intake_platform.research.values",
        "intake_platform.retention",
        "intake_platform.retention.policy",
        "intake_platform.tokenization",
    }
)

#: Names that would mean narrative had entered this package. `Note` and `Slot`
#: are ORM models whose columns carry the patient's own words; `Document` and
#: `CsatText` likewise. `cells_query` / `read_cells` are INT-171's ungated
#: projection — the gated `materialise_view` is the only sanctioned read.
FORBIDDEN_NAMES = frozenset(
    {
        "Note",
        "Slot",
        "Document",
        "CsatText",
        "Transcript",
        "cells_query",
        "read_cells",
    }
)

#: Anything that composes or runs a query. This package holds its rows already.
QUERY_CALLS = frozenset({"select", "text", "execute", "scalars", "scalar", "stream"})


def research_modules() -> list[tuple[Path, ast.Module]]:
    return [
        (path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        for path in sorted(RESEARCH_SRC.glob("*.py"))
    ]


def imported_modules(tree: ast.Module) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            found.add(node.module)
    return found


def test_the_scan_walks_a_real_corpus() -> None:
    """A gate over an empty corpus passes vacuously. Pin that it is not."""
    modules = research_modules()
    assert len(modules) >= 5, "the research package lost modules — the AST gates below are vacuous"


def test_the_research_package_imports_nothing_outside_its_allow_list() -> None:
    for path, tree in research_modules():
        first_party = {m for m in imported_modules(tree) if m.split(".")[0].startswith("intake_")}
        unexpected = sorted(first_party - RESEARCH_IMPORT_ALLOW_LIST)
        assert unexpected == [], f"{path.name} reaches an undeclared module: {unexpected}"


def test_the_research_package_binds_or_touches_no_narrative_name() -> None:
    """Not a substring scan: an aliased import (`import Note as N`) and a name
    used only as an attribute both fail a grep and are caught here."""
    for path, tree in research_modules():
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    assert alias.name not in FORBIDDEN_NAMES, f"{path.name} imports {alias.name!r}"
            elif isinstance(node, ast.Attribute):
                assert node.attr not in FORBIDDEN_NAMES, (
                    f"{path.name} touches attribute {node.attr!r}"
                )
            elif isinstance(node, ast.Name):
                assert node.id not in FORBIDDEN_NAMES, f"{path.name} names {node.id!r}"


def test_the_research_package_composes_no_query_of_its_own() -> None:
    """The one database read this package performs goes through
    `consent_state`, which owns its own statement. Anything else would be a
    second read path with no consent check in front of it (invariant 4)."""
    for path, tree in research_modules():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            assert name not in QUERY_CALLS, f"{path.name} composes a query: {name}()"


def test_the_gate_would_catch_a_narrative_import(tmp_path: Path) -> None:
    """Near-miss negative control: the gates above pass on the real package, so
    prove they can fail. An aliased import is the case a grep would miss."""
    planted = tmp_path / "leaky.py"
    planted.write_text(
        "from intake_platform.db.models import Note as _N\n\n\ndef f() -> object:\n    return _N\n",
        encoding="utf-8",
    )
    tree = ast.parse(planted.read_text(encoding="utf-8"))
    bound = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert bound & FORBIDDEN_NAMES == {"Note"}
    first_party = {m for m in imported_modules(tree) if m.split(".")[0].startswith("intake_")}
    assert sorted(first_party - RESEARCH_IMPORT_ALLOW_LIST) == ["intake_platform.db.models"]

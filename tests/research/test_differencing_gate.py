"""INT-262 — the differencing gate across the extract register.

Acceptance, verbatim from docs/backlog/issues.yaml:
  "the export gate reads the register for prior extracts of the same
   study+spec and refuses an overlapping window unless the study's registry
   row states an explicit query budget; the budget has no default and an
   absent one fails closed; golden test differences two extracts and proves
   the second is refused"

sec_row: `learning-loops`.  legal: KVKK-16, KSVY-16, ETİK.

**The attack this closes.** INT-230's k gate holds for ONE extract: every
quasi-identifier combination carries at least k subjects. It does not compare
a new request against the extracts already served, so an investigator who
takes the same spec over 2026-Q1 and then over 2026-Jan..Feb *differences* the
two and recovers March's cells — at any k. The register already records what a
gate would need (study, spec, window, subjects, k, content hash); INT-262 adds
the policy that reads it.

**The parameter no agent may pick.** How much overlap, and how many requests,
a study may make is an ethics-committee decision (HB-R1). So the budget has NO
default: a study whose registry row states no ``query_budget`` refuses every
overlapping window (fail closed, invariant 17), and a study that states one
permits overlap only up to the explicit count it names.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from api_harness import run
from conftest import RESEARCH_TENANT_ID, ResearchHarness
from intake_platform.analytics import K_ANONYMITY_FLOOR
from intake_platform.analytics import Cohort as AnalyticsCohort
from intake_platform.research import (
    RESEARCH_SCOPE,
    ExtractRegister,
    InMemoryExtractRegisterStore,
    PseudonymisedExtract,
    ResearchExportGate,
    ResearchExportRefused,
    ResearchExtractSpec,
    ResearchRefusalReason,
    StudyRecord,
    StudyRegistry,
    SubjectRow,
)
from intake_platform.retention import DestroyableClass, RetentionPolicy, load_default_policy
from intake_platform.tokenization import Tokenizer
from sqlalchemy.ext.asyncio import AsyncSession

# --- fixture study, ethics id and recipient (all synthetic — no study exists) ------
FIXTURE_STUDY_ID = "unit.diff.study"
FIXTURE_ETHICS_ID = "unit.diff.approval"
FIXTURE_RECIPIENT = "unit.diff.investigator"
APPROVED_FROM = date(2026, 1, 1)
APPROVED_UNTIL = date(2026, 12, 31)
INSIDE_APPROVAL = datetime(2026, 6, 1, tzinfo=UTC)

# The classic differencing pair: a wide window and a narrower one wholly inside
# it. Subtracting the second from the first recovers the excluded weeks.
WINDOW_WIDE = AnalyticsCohort(
    description="diff-lane cohort, 2026-Q1",
    window_start=datetime(2026, 1, 1, tzinfo=UTC),
    window_end=datetime(2026, 4, 1, tzinfo=UTC),
)
WINDOW_NARROW = AnalyticsCohort(
    description="diff-lane cohort, 2026 Jan..Feb (contained in Q1)",
    window_start=datetime(2026, 1, 1, tzinfo=UTC),
    window_end=datetime(2026, 3, 1, tzinfo=UTC),
)
WINDOW_INNER = AnalyticsCohort(
    description="diff-lane cohort, 2026 mid-Jan..mid-Feb (overlaps both)",
    window_start=datetime(2026, 1, 15, tzinfo=UTC),
    window_end=datetime(2026, 2, 15, tzinfo=UTC),
)
WINDOW_DISJOINT = AnalyticsCohort(
    description="diff-lane cohort, 2026 June (no overlap with Q1)",
    window_start=datetime(2026, 6, 1, tzinfo=UTC),
    window_end=datetime(2026, 7, 1, tzinfo=UTC),
)
# Half-open windows that touch but do not overlap: [.., 04-01) and [04-01, ..).
WINDOW_ADJACENT = AnalyticsCohort(
    description="diff-lane cohort, 2026-Q2 start (adjacent to Q1, no overlap)",
    window_start=datetime(2026, 4, 1, tzinfo=UTC),
    window_end=datetime(2026, 7, 1, tzinfo=UTC),
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
    narrative_exclusion="counts and declared enumeration members only",
)
OTHER_SPEC = ResearchExtractSpec(
    name="research.triage_validation",
    dimensions={
        "profile": ("residency_tr", "typed"),
        "protocol_id": ("base.intake",),
        "week_start": ("2026-W02", "2026-W03"),
    },
    measures=("sessions",),
    cohort_description="a different spec entirely, over the same weeks",
    narrative_exclusion="counts and declared enumeration members only",
)


def fixture_registry(
    *,
    study_id: str = FIXTURE_STUDY_ID,
    query_budget: object | None = None,
    extra: tuple[StudyRecord, ...] = (),
) -> StudyRegistry:
    row = StudyRecord(
        study_id=study_id,
        site="unit.diff.site",
        ethics_committee="unit.diff.committee",
        ethics_approval_id=FIXTURE_ETHICS_ID,
        approval_date=APPROVED_FROM,
        approval_valid_until=APPROVED_UNTIL,
        protocol_version="v0",
        recipients=(FIXTURE_RECIPIENT,),
        query_budget=query_budget,  # type: ignore[arg-type]
    )
    return StudyRegistry(studies=(row, *extra))


def sourced_retention() -> RetentionPolicy:
    """The committed policy with the research row given a duration — the
    post-HB-I8/ethics-protocol world in miniature, so a served extract can be
    created and land in the register for the next request to difference."""
    raw = json.loads(load_default_policy().model_dump_json())
    for row in raw["classes"]:
        if row["data_class"] == DestroyableClass.RESEARCH_EXTRACTS.value:
            row["retention"] = {"kind": "years", "years": 1}
            row["status"] = "sourced"
            row["source"] = "unit-diff fixture: a stand-in for the ethics protocol's figure"
    return RetentionPolicy.model_validate(raw)


def build_gate(
    research: ResearchHarness,
    *,
    registry: StudyRegistry | None = None,
) -> tuple[ResearchExportGate, ExtractRegister]:
    """One gate over ONE register, so a second build() sees the first's row."""
    register = ExtractRegister(InMemoryExtractRegisterStore())
    gate = ResearchExportGate(
        registry=registry if registry is not None else fixture_registry(),
        retention=sourced_retention(),
        tokenizer=Tokenizer({"v1": b"unit-diff-tokenization-key"}, "v1"),
        register=register,
        audit=research.audit,
        catalog=research.catalog,
        clock=lambda: INSIDE_APPROVAL,
    )
    return gate, register


def rows_for(ids: tuple[uuid.UUID, ...]) -> tuple[SubjectRow, ...]:
    return tuple(
        SubjectRow(
            patient_id=pid,
            dimensions={
                "profile": "residency_tr",
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
    cohort: AnalyticsCohort,
    spec: ResearchExtractSpec = SPEC,
    study_id: str = FIXTURE_STUDY_ID,
    k: int = K_ANONYMITY_FLOOR,
) -> PseudonymisedExtract:
    async def _build() -> PseudonymisedExtract:
        async with AsyncSession(research.engine) as session:
            return await gate.build(
                session,
                tenant_id=RESEARCH_TENANT_ID,
                study_id=study_id,
                recipient=FIXTURE_RECIPIENT,
                requested_by="unit-diff-analyst",
                spec=spec,
                cohort=cohort,
                k=k,
                candidates=candidates,
            )

    result = run(_build())
    assert isinstance(result, PseudonymisedExtract)
    return result


# --- the golden test: difference two extracts, prove the second is refused ---------


def test_a_second_extract_over_an_overlapping_window_is_refused(research: ResearchHarness) -> None:
    """The acceptance's golden. A study with no query budget serves the first
    extract, then refuses a second whose window overlaps it — the differencing
    attack is blocked, fail closed."""
    ids = consented_pack(research, K_ANONYMITY_FLOOR + 2)
    gate, register = build_gate(research)  # no query_budget → fail closed on overlap

    first = build(gate, research, rows_for(ids), cohort=WINDOW_WIDE)
    assert first.subjects == K_ANONYMITY_FLOOR + 2
    assert len(register.records()) == 1

    with pytest.raises(ResearchExportRefused) as caught:
        build(gate, research, rows_for(ids), cohort=WINDOW_NARROW)
    assert caught.value.reason is ResearchRefusalReason.OVERLAPPING_WINDOW_UNBUDGETED
    # The refused request produced no extract, so it did not enter the register.
    assert len(register.records()) == 1


def test_the_refusal_names_no_window_and_no_cohort(research: ResearchHarness) -> None:
    """The refusal is a class, not an oracle: it must not echo the requested
    window, which is itself a fact about when the cohort was measured."""
    ids = consented_pack(research, K_ANONYMITY_FLOOR + 2)
    gate, _ = build_gate(research)
    build(gate, research, rows_for(ids), cohort=WINDOW_WIDE)
    with pytest.raises(ResearchExportRefused) as caught:
        build(gate, research, rows_for(ids), cohort=WINDOW_NARROW)
    message = str(caught.value)
    assert WINDOW_NARROW.window_end.isoformat() not in message
    assert WINDOW_WIDE.window_end.isoformat() not in message
    assert str(K_ANONYMITY_FLOOR + 2) not in message


def test_a_disjoint_second_window_is_served(research: ResearchHarness) -> None:
    """The gate bites on OVERLAP, not on a second request. A window that does
    not intersect any prior extract's window serves, budget or no budget."""
    ids = consented_pack(research, K_ANONYMITY_FLOOR + 2)
    gate, register = build_gate(research)
    build(gate, research, rows_for(ids), cohort=WINDOW_WIDE)
    build(gate, research, rows_for(ids), cohort=WINDOW_DISJOINT)
    assert len(register.records()) == 2


def test_an_adjacent_window_does_not_overlap(research: ResearchHarness) -> None:
    """Windows are half-open [start, end): Q1 ends where Q2 begins, so the two
    touch without intersecting and the second serves."""
    ids = consented_pack(research, K_ANONYMITY_FLOOR + 2)
    gate, register = build_gate(research)
    build(gate, research, rows_for(ids), cohort=WINDOW_WIDE)
    build(gate, research, rows_for(ids), cohort=WINDOW_ADJACENT)
    assert len(register.records()) == 2


def test_the_gate_is_spec_scoped(research: ResearchHarness) -> None:
    """Same study, overlapping window, DIFFERENT spec: served. The register is
    read for the same study AND spec, because two specs over one window do not
    difference to a smaller cohort."""
    ids = consented_pack(research, K_ANONYMITY_FLOOR + 2)
    gate, register = build_gate(research)
    build(gate, research, rows_for(ids), cohort=WINDOW_WIDE, spec=SPEC)
    build(gate, research, rows_for(ids), cohort=WINDOW_NARROW, spec=OTHER_SPEC)
    assert len(register.records()) == 2


def test_the_gate_is_study_scoped(research: ResearchHarness) -> None:
    """A second study's overlapping window is served: an extract under study A
    cannot be differenced against one under study B (their pseudonyms are
    unrelatable, INT-230), so the budget is per study."""
    ids = consented_pack(research, K_ANONYMITY_FLOOR + 2)
    other = StudyRecord(
        study_id="unit.diff.study.b",
        site="unit.diff.site",
        ethics_committee="unit.diff.committee",
        ethics_approval_id=FIXTURE_ETHICS_ID,
        approval_date=APPROVED_FROM,
        approval_valid_until=APPROVED_UNTIL,
        protocol_version="v0",
        recipients=(FIXTURE_RECIPIENT,),
    )
    gate, register = build_gate(research, registry=fixture_registry(extra=(other,)))
    build(gate, research, rows_for(ids), cohort=WINDOW_WIDE, study_id=FIXTURE_STUDY_ID)
    build(gate, research, rows_for(ids), cohort=WINDOW_NARROW, study_id="unit.diff.study.b")
    assert len(register.records()) == 2


# --- the budget has no default; an explicit one permits overlap up to its count ----


def test_a_study_with_no_query_budget_defaults_to_none() -> None:
    """The field has no default value that permits anything: a row that states
    no budget carries ``None`` and refuses every overlapping window."""
    study = fixture_registry().studies[0]
    assert study.query_budget is None


def test_the_query_budget_count_has_no_default() -> None:
    """Invariant 17: a budget block that omits the count does not construct —
    no agent may pick how many overlapping requests a study may make."""
    from intake_platform.research import QueryBudget  # noqa: PLC0415

    with pytest.raises(ValueError):
        QueryBudget()  # type: ignore[call-arg]
    with pytest.raises(ValueError):
        QueryBudget(max_overlapping_extracts=0)  # a budget of zero is not a budget


def test_an_explicit_budget_permits_overlap_up_to_its_count(research: ResearchHarness) -> None:
    """A study that states ``max_overlapping_extracts: 2`` serves a first and a
    second overlapping extract, then refuses the third with the budget
    exhausted — a different reason class from the unbudgeted refusal."""
    from intake_platform.research import QueryBudget  # noqa: PLC0415

    ids = consented_pack(research, K_ANONYMITY_FLOOR + 2)
    gate, register = build_gate(
        research, registry=fixture_registry(query_budget=QueryBudget(max_overlapping_extracts=2))
    )
    build(gate, research, rows_for(ids), cohort=WINDOW_WIDE)  # 1st, no prior overlap
    build(gate, research, rows_for(ids), cohort=WINDOW_NARROW)  # 2nd, within budget
    assert len(register.records()) == 2

    with pytest.raises(ResearchExportRefused) as caught:
        build(gate, research, rows_for(ids), cohort=WINDOW_INNER)  # 3rd overlapping
    assert caught.value.reason is ResearchRefusalReason.QUERY_BUDGET_EXHAUSTED
    assert len(register.records()) == 2


def test_a_budget_of_one_still_refuses_the_second_overlapping_window(
    research: ResearchHarness,
) -> None:
    """An explicit budget of 1 is a study saying "one extract per window group"
    — behaviourally like the unbudgeted case, but a stated choice rather than a
    default, which is what the acceptance requires."""
    from intake_platform.research import QueryBudget  # noqa: PLC0415

    ids = consented_pack(research, K_ANONYMITY_FLOOR + 2)
    gate, _ = build_gate(
        research, registry=fixture_registry(query_budget=QueryBudget(max_overlapping_extracts=1))
    )
    build(gate, research, rows_for(ids), cohort=WINDOW_WIDE)
    with pytest.raises(ResearchExportRefused) as caught:
        build(gate, research, rows_for(ids), cohort=WINDOW_NARROW)
    assert caught.value.reason is ResearchRefusalReason.QUERY_BUDGET_EXHAUSTED


# --- the refusal is audited in the hash chain, carrying only the reason class ------


def actions(research: ResearchHarness) -> list[str]:
    return [entry.action for entry in research.chain._store.entries()]  # noqa: SLF001


def test_an_overlap_refusal_is_audited_with_a_reason_class(research: ResearchHarness) -> None:
    ids = consented_pack(research, K_ANONYMITY_FLOOR + 2)
    gate, _ = build_gate(research)
    build(gate, research, rows_for(ids), cohort=WINDOW_WIDE)
    with pytest.raises(ResearchExportRefused):
        build(gate, research, rows_for(ids), cohort=WINDOW_NARROW)
    assert "research.extract.refused.overlapping_window_unbudgeted" in actions(research)
    assert research.chain.verify().ok
    # No window, no cohort size leaked into the chain.
    blob = json.dumps(
        [entry.__dict__ for entry in research.chain._store.entries()],  # noqa: SLF001
        default=str,
    )
    assert WINDOW_NARROW.window_end.isoformat() not in blob


def test_the_differencing_check_runs_before_any_patient_row_is_read(
    research: ResearchHarness,
) -> None:
    """An overlapping request refuses on the window alone — it never reaches
    the consent filter or the cross-tab, so no patient data is processed for a
    request that was always going to refuse. A candidate carrying a free-text
    value would trip the row check; here the overlap gate fires first."""
    ids = consented_pack(research, K_ANONYMITY_FLOOR + 2)
    gate, _ = build_gate(research)
    build(gate, research, rows_for(ids), cohort=WINDOW_WIDE)
    poisoned = list(rows_for(ids))
    poisoned[0] = SubjectRow(
        patient_id=ids[0],
        dimensions={
            "profile": "Ahmet Yılmaz bir cümle",
            "protocol_id": "base.intake",
            "week_start": "2026-W02",
        },
        measures={"sessions": 1},
    )
    with pytest.raises(ResearchExportRefused) as caught:
        build(gate, research, tuple(poisoned), cohort=WINDOW_NARROW)
    # The overlap reason, not the value reason — the gate fired before the rows.
    assert caught.value.reason is ResearchRefusalReason.OVERLAPPING_WINDOW_UNBUDGETED


def test_the_research_package_states_no_overlap_default() -> None:
    """A grep guard mirroring INT-230's floor test: the differencing gate must
    not carry a hard-coded permissive overlap count anywhere in the package."""
    src = Path(__file__).resolve().parents[2] / (
        "packages/intake_platform/src/intake_platform/research"
    )
    sources = "\n".join(path.read_text(encoding="utf-8") for path in sorted(src.glob("*.py")))
    for forbidden in ("DEFAULT_BUDGET", "default_budget", "max_overlapping_extracts = ", "= 3  #"):
        assert forbidden not in sources, f"the package invented an overlap default: {forbidden}"

"""INT-172 — the Inspector → Architect pipeline (files/09 §4).

files/09 §4, verbatim: "``services/learning`` runs weekly as an **Inspector →
Architect** pipeline …: Inspectors write case-level findings on de-identified
traces; the Architect commits only **recurring, cross-patient** patterns that
pass thresholds (≥ 10 patients, ≥ 2 clinics, effect size + direction stable
over 2 weeks) into **proposals**, never direct changes."

Three of those four numbers are stated by the blueprint and are pinned here.
The fourth — what counts as a large enough *effect* — is not stated anywhere,
and this file asserts that the Architect **refuses** rather than picking one
(CLAUDE.md: "Never invent a value to unblock yourself").

The subject floor is not a fourth number either: it is INT-171's
``K_ANONYMITY_FLOOR``, imported. A learning pipeline that re-declared "10"
could later drift from the gate that actually suppresses the cell.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from intake_learning.architect import (
    MIN_TENANTS,
    STABILITY_WEEKS,
    AwaitingHumanValue,
    EffectSizeFloor,
    PromotionThresholds,
    RefusalReason,
    propose,
)
from intake_learning.evidence import EvidenceSource
from intake_learning.inspector import (
    Finding,
    Signal,
    inspect_session_outcomes,
    inspect_step_coverage,
)
from intake_learning.proposals import CandidateRedFlag
from intake_platform.analytics import (
    K_ANONYMITY_FLOOR,
    SESSION_OUTCOMES,
    STEP_COVERAGE,
    Cell,
    Cohort,
    Measurement,
    materialise,
)

WEEK_1 = "2026-08-03"
WEEK_2 = "2026-08-10"
WEEK_3 = "2026-08-17"


def _cohort(view_description: str) -> Cohort:
    return Cohort(
        description=view_description,
        window_start=datetime(2026, 8, 3, tzinfo=UTC),
        window_end=datetime(2026, 8, 24, tzinfo=UTC),
    )


def _sessions(*weeks: str, sessions: int = 40, subjects: int = 40) -> Measurement:
    cells = [
        Cell(
            dimensions={
                "protocol_id": "base.intake",
                "protocol_version": "1.4.0",
                "week_start": week,
            },
            subjects=subjects,
            tenants=3,
            measures={"sessions": sessions, "completed": sessions - 2, "cancelled": 2},
        )
        for week in weeks
    ]
    return materialise(
        SESSION_OUTCOMES,
        cells,
        cohort=_cohort(SESSION_OUTCOMES.cohort_description),
        k=K_ANONYMITY_FLOOR,
    )


def _steps(*weeks: str, answered: int = 10, subjects: int = 40, tenants: int = 3) -> Measurement:
    cells = [
        Cell(
            dimensions={
                "protocol_id": "base.intake",
                "slot_id": "medication_adherence",
                "week_start": week,
            },
            subjects=subjects,
            tenants=tenants,
            measures={"sessions_answered": answered},
        )
        for week in weeks
    ]
    return materialise(
        STEP_COVERAGE,
        cells,
        cohort=_cohort(STEP_COVERAGE.cohort_description),
        k=K_ANONYMITY_FLOOR,
    )


def _floor(value: float = 0.5) -> EffectSizeFloor:
    """A test-supplied effect-size floor.

    A fixture may state one; the repository may not (see
    :func:`test_the_blueprint_states_no_effect_size_floor_so_none_is_shipped`).
    """
    return EffectSizeFloor(value=value, recorded_in=EvidenceSource.TEST_FIXTURE)


def _thresholds(value: float = 0.5) -> PromotionThresholds:
    return PromotionThresholds(effect_size_floor=_floor(value))


# --- the Inspector ----------------------------------------------------------------


def test_inspectors_read_measurements_and_never_a_row() -> None:
    """A finding is derived from a gated aggregate, never from a session.

    The only inputs the Inspector accepts are
    :class:`~intake_platform.analytics.Measurement` values, which INT-171 will
    not construct below the floor. There is no code path from a patient row to
    a finding because there is no argument that could carry one.
    """
    findings = inspect_step_coverage(sessions=_sessions(WEEK_1), steps=_steps(WEEK_1))
    assert len(findings) == 1
    finding = findings[0]
    assert finding.pack_id == "base.intake"
    assert finding.slot_id == "medication_adherence"
    assert finding.week_start == WEEK_1
    # 10 of 40 sessions answered the step -> a 0.75 skip rate
    assert finding.numerator == 30
    assert finding.denominator == 40
    assert finding.rate == pytest.approx(0.75)


def test_a_finding_cannot_be_constructed_by_hand() -> None:
    """Findings come out of an Inspector or they do not exist.

    The same posture INT-091 used for RED preemption: the constructor is not
    reachable from outside the module, so a caller cannot mint a finding that
    never passed through a gated measurement.
    """
    with pytest.raises(TypeError):
        Finding(  # type: ignore[call-arg]
            signal=Signal.STEP_SKIP_RATE,
            view=STEP_COVERAGE.name,
            pack_id="base.intake",
            slot_id="medication_adherence",
            week_start=WEEK_1,
            subjects=40,
            tenants=3,
            numerator=30,
            denominator=40,
        )


def test_step_coverage_without_a_matching_session_week_yields_no_finding() -> None:
    assert inspect_step_coverage(sessions=_sessions(WEEK_1), steps=_steps(WEEK_2)) == ()


def test_the_inspector_refuses_a_measurement_from_the_wrong_view() -> None:
    with pytest.raises(ValueError, match="learning.step_coverage"):
        inspect_step_coverage(sessions=_sessions(WEEK_1), steps=_sessions(WEEK_1))


def test_session_outcome_inspector_reports_abandonment() -> None:
    findings = inspect_session_outcomes(_sessions(WEEK_1))
    assert [f.signal for f in findings] == [Signal.SESSION_ABANDONMENT]
    assert findings[0].numerator == 2
    assert findings[0].denominator == 40
    assert findings[0].slot_id is None


# --- the thresholds ---------------------------------------------------------------


def test_the_three_stated_thresholds_are_the_blueprint_numbers() -> None:
    thresholds = PromotionThresholds(effect_size_floor=_floor())
    # files/09 §4: "≥ 10 patients" — inherited from INT-171, not re-declared
    assert thresholds.min_subjects == K_ANONYMITY_FLOOR == 10
    # files/09 §4: "≥ 2 clinics"
    assert thresholds.min_tenants == 2
    # files/09 §4: "stable over 2 weeks"
    assert thresholds.stability_weeks == 2


def test_the_subject_floor_may_be_raised_and_never_lowered() -> None:
    PromotionThresholds(effect_size_floor=_floor(), min_subjects=25)
    with pytest.raises(ValueError, match="K_ANONYMITY_FLOOR|floor"):
        PromotionThresholds(effect_size_floor=_floor(), min_subjects=K_ANONYMITY_FLOOR - 1)


def test_the_blueprint_states_no_effect_size_floor_so_none_is_shipped() -> None:
    """files/09 §4 says "effect size" and states no number.

    ``from_blueprint`` is the constructor a scheduled run would use. It raises,
    naming the human and the single question they must answer, rather than
    choosing a threshold that would decide which protocol changes reach a
    clinician's review queue.
    """
    with pytest.raises(AwaitingHumanValue) as caught:
        PromotionThresholds.from_blueprint()
    message = str(caught.value)
    assert "effect size" in message
    assert "clinical lead" in message
    assert "files/09" in message


def test_an_effect_size_floor_must_say_where_it_came_from() -> None:
    with pytest.raises(TypeError):
        EffectSizeFloor(value=0.5)  # type: ignore[call-arg]


# --- the Architect ----------------------------------------------------------------


def test_a_single_week_never_becomes_a_proposal() -> None:
    """ "recurring" is the word files/09 §4 uses. One week is not recurrence."""
    findings = inspect_step_coverage(sessions=_sessions(WEEK_1), steps=_steps(WEEK_1))
    assert propose(findings, thresholds=_thresholds()) == ()


def test_two_consecutive_weeks_above_the_floor_become_one_proposal() -> None:
    findings = inspect_step_coverage(
        sessions=_sessions(WEEK_1, WEEK_2), steps=_steps(WEEK_1, WEEK_2)
    )
    proposals = propose(findings, thresholds=_thresholds())
    assert len(proposals) == 1
    assert proposals[0].target.pack_id == "base.intake"
    assert proposals[0].target.slot_id == "medication_adherence"
    assert proposals[0].weeks == (WEEK_1, WEEK_2)


def test_two_non_consecutive_weeks_are_not_stability() -> None:
    findings = inspect_step_coverage(
        sessions=_sessions(WEEK_1, WEEK_3), steps=_steps(WEEK_1, WEEK_3)
    )
    assert propose(findings, thresholds=_thresholds()) == ()


def test_an_effect_below_the_floor_is_not_proposed() -> None:
    findings = inspect_step_coverage(
        sessions=_sessions(WEEK_1, WEEK_2), steps=_steps(WEEK_1, WEEK_2, answered=38)
    )
    assert propose(findings, thresholds=_thresholds(0.5)) == ()


def test_fewer_than_two_clinics_is_not_cross_patient() -> None:
    findings = inspect_step_coverage(
        sessions=_sessions(WEEK_1, WEEK_2), steps=_steps(WEEK_1, WEEK_2, tenants=1)
    )
    assert propose(findings, thresholds=_thresholds()) == ()


def test_the_architect_never_emits_a_candidate_red_flag_on_its_own() -> None:
    """files/09 §4 allows a *candidate* red flag as a proposal type; invariant
    12 forbids the pipeline from setting a level. The Architect's own signals
    (skip rate, abandonment) map to wording and ordering targets only — no
    Architect path constructs a :class:`CandidateRedFlag`, which is why the
    type's YELLOW_REVIEW constant is a cap on a clinician's *review queue*
    entry rather than on anything this service decides.
    """

    findings = (
        *inspect_step_coverage(sessions=_sessions(WEEK_1, WEEK_2), steps=_steps(WEEK_1, WEEK_2)),
        *inspect_session_outcomes(_sessions(WEEK_1, WEEK_2, sessions=40)),
    )
    proposals = propose(findings, thresholds=_thresholds(0.01))
    assert proposals
    assert not any(isinstance(p.target, CandidateRedFlag) for p in proposals)


def test_an_abandonment_finding_maps_to_no_stated_target_and_is_metered() -> None:
    """files/09 §4 names abandonment as a signal and does not say which of its
    allowed changes an abandoned session implies.

    So the Architect records a refusal with its reason rather than inventing a
    mapping — the same posture as the missing effect-size floor, one level
    down. The refusal is a console signal (files/10 §9: "rejections"), so the
    finding is visible to a human even though nothing is proposed from it.
    """
    from intake_learning.architect import LEARNING_PROPOSALS_REFUSED

    before = LEARNING_PROPOSALS_REFUSED.labels(
        signal=Signal.SESSION_ABANDONMENT.value,
        reason=RefusalReason.NO_STATED_TARGET_MAPPING.value,
    )._value.get()

    findings = inspect_session_outcomes(_sessions(WEEK_1, WEEK_2))
    assert propose(findings, thresholds=_thresholds(0.01)) == ()

    after = LEARNING_PROPOSALS_REFUSED.labels(
        signal=Signal.SESSION_ABANDONMENT.value,
        reason=RefusalReason.NO_STATED_TARGET_MAPPING.value,
    )._value.get()
    assert after == before + 1


def test_the_stated_thresholds_may_be_raised_and_never_lowered() -> None:
    PromotionThresholds(effect_size_floor=_floor(), min_tenants=5, stability_weeks=4)
    with pytest.raises(ValueError, match=str(MIN_TENANTS)):
        PromotionThresholds(effect_size_floor=_floor(), min_tenants=MIN_TENANTS - 1)
    with pytest.raises(ValueError, match=str(STABILITY_WEEKS)):
        PromotionThresholds(effect_size_floor=_floor(), stability_weeks=STABILITY_WEEKS - 1)


def test_an_effect_size_floor_is_a_proportion() -> None:
    for value in (0.0, 1.0, 1.5, -0.2):
        with pytest.raises(ValueError, match="proportion"):
            EffectSizeFloor(value=value, recorded_in=EvidenceSource.TEST_FIXTURE)


def test_a_finding_needs_a_population_to_be_a_fraction_of() -> None:
    """A zero denominator is a division by zero dressed as a rate."""
    empty = materialise(
        SESSION_OUTCOMES,
        [
            Cell(
                dimensions={
                    "protocol_id": "base.intake",
                    "protocol_version": "1.4.0",
                    "week_start": WEEK_1,
                },
                subjects=40,
                tenants=3,
                measures={"sessions": 0, "completed": 0, "cancelled": 0},
            )
        ],
        cohort=_cohort(SESSION_OUTCOMES.cohort_description),
        k=K_ANONYMITY_FLOOR,
    )
    with pytest.raises(ValueError, match="population"):
        inspect_session_outcomes(empty)


def test_a_proposal_reports_its_smallest_weekly_cohort() -> None:
    """Not the largest, and not an average: the honest number behind a claim
    made over two weeks is the week that had the fewest people in it."""
    steps = materialise(
        STEP_COVERAGE,
        [
            Cell(
                dimensions={
                    "protocol_id": "base.intake",
                    "slot_id": "medication_adherence",
                    "week_start": week,
                },
                subjects=subjects,
                tenants=tenants,
                measures={"sessions_answered": 10},
            )
            for week, subjects, tenants in ((WEEK_1, 40, 3), (WEEK_2, 12, 2))
        ],
        cohort=_cohort(STEP_COVERAGE.cohort_description),
        k=K_ANONYMITY_FLOOR,
    )
    proposal = propose(
        inspect_step_coverage(sessions=_sessions(WEEK_1, WEEK_2), steps=steps),
        thresholds=_thresholds(),
    )[0]
    assert proposal.subjects == 12
    assert proposal.tenants == 2


def test_a_raised_subject_floor_actually_bites() -> None:
    """``min_subjects`` may be raised (never lowered), and raising it refuses.

    The k gate guarantees every cell holds at least 10 people, so this branch
    is only reachable when a caller asks for more than the blueprint's floor —
    which is exactly the affordance ``PromotionThresholds`` offers, and an
    affordance no test exercises is an affordance nobody knows is real.
    """
    findings = inspect_step_coverage(
        sessions=_sessions(WEEK_1, WEEK_2), steps=_steps(WEEK_1, WEEK_2)
    )
    strict = PromotionThresholds(effect_size_floor=_floor(), min_subjects=100)
    assert propose(findings, thresholds=strict) == ()
    assert propose(findings, thresholds=_thresholds())  # the same findings, at the floor

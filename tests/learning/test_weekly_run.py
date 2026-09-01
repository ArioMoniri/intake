"""INT-172 — the weekly run, end to end, on INT-171's read-only path.

files/09 §4: "``services/learning`` runs weekly as an **Inspector → Architect**
pipeline". files/09 §7: it "runs with **read-only** credentials on
de-identified views (never on raw tables)".

The session here is a fake that answers the two SELECTs
:func:`intake_learning.run.read_view` issues through INT-171's
``materialise_view``. Mocking the driver rather than the gate is the point:
every assertion below is about what the *real* ``materialise_view`` does with
the rows it is given — the k floor, the id-shape check, the refusal on a thin
cell — none of which the fake can soften. The grant boundary itself
(``svc_learning_reader`` reaching the views and no base table) is INT-171's
integration lane in ``tests/learning/test_analytics_views_db.py``, against real
Postgres, and is not restated here.

sec_row: `learning-loops`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from typing import Any

import pytest
from intake_learning.architect import AwaitingHumanValue, EffectSizeFloor, PromotionThresholds
from intake_learning.evidence import EvidenceSource
from intake_learning.proposals import QuestionWording
from intake_learning.run import (
    LEARNING_READER_ROLE,
    RUN_CITATIONS,
    ProposalPackage,
    run_weekly,
)
from intake_learning.signing import verify_bundle
from intake_platform.analytics import (
    K_ANONYMITY_FLOOR,
    SESSION_OUTCOMES,
    STEP_COVERAGE,
    KAnonymityRefusal,
    RefusalReason,
    ThresholdBelowFloor,
)

WINDOW_START = datetime(2026, 8, 3, tzinfo=UTC)
WINDOW_END = datetime(2026, 8, 17, tzinfo=UTC)
WEEK_1 = date(2026, 8, 3)
WEEK_2 = date(2026, 8, 10)

TEST_KEY = b"int-172-test-signing-key--32bytes"

#: The planted adversary again, at the one surface a *database* controls: a
#: dimension value coming back off the wire. Same sentence as
#: tests/learning/test_evidence_bundle.py, for the same reason.
TURKISH_SYMPTOM = "Göğsümde iki gündür şiddetli bir ağrı var ve nefes almakta zorlanıyorum."


def _session_rows(*, subjects: int = 40, cancelled: int = 2) -> list[dict[str, Any]]:
    return [
        {
            "protocol_id": "base.intake",
            "protocol_version": "1.4.0",
            "week_start": week,
            "subjects": subjects,
            "tenants": 3,
            "sessions": 40,
            "completed": 40 - cancelled,
            "cancelled": cancelled,
        }
        for week in (WEEK_1, WEEK_2)
    ]


def _step_rows(
    *, slot_id: str = "medication_adherence", answered: int = 10, subjects: int = 40
) -> list[dict[str, Any]]:
    return [
        {
            "protocol_id": "base.intake",
            "slot_id": slot_id,
            "week_start": week,
            "subjects": subjects,
            "tenants": 3,
            "sessions_answered": answered,
        }
        for week in (WEEK_1, WEEK_2)
    ]


class _FakeResult:
    def __init__(self, rows: Sequence[Mapping[str, Any]]) -> None:
        self._rows = list(rows)

    def mappings(self) -> _FakeResult:
        return self

    def all(self) -> list[Mapping[str, Any]]:
        return self._rows


class _FakeSession:
    """Answers by relation name, and records what it was asked.

    Deliberately not a SQLAlchemy mock: it captures the compiled statement so a
    test can assert the run issued two SELECTs and nothing else.
    """

    def __init__(self, by_relation: Mapping[str, Sequence[Mapping[str, Any]]]) -> None:
        self._by_relation = by_relation
        self.statements: list[str] = []

    async def execute(self, statement: Any) -> _FakeResult:
        rendered = str(statement)
        self.statements.append(rendered)
        for relation, rows in self._by_relation.items():
            if relation in rendered:
                return _FakeResult(rows)
        raise AssertionError(f"unexpected relation in: {rendered}")


def _session(
    *,
    sessions: Sequence[Mapping[str, Any]] | None = None,
    steps: Sequence[Mapping[str, Any]] | None = None,
) -> _FakeSession:
    return _FakeSession(
        {
            "v_session_outcomes": _session_rows() if sessions is None else sessions,
            "v_step_coverage": _step_rows() if steps is None else steps,
        }
    )


def _thresholds(value: float = 0.5) -> PromotionThresholds:
    return PromotionThresholds(
        effect_size_floor=EffectSizeFloor(value=value, recorded_in=EvidenceSource.TEST_FIXTURE)
    )


def _run(
    session: _FakeSession,
    *,
    k: int = K_ANONYMITY_FLOOR,
    thresholds: PromotionThresholds | None = None,
    key: bytes = TEST_KEY,
) -> tuple[ProposalPackage, ...]:
    return asyncio.run(
        run_weekly(
            session,  # type: ignore[arg-type]
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            k=k,
            thresholds=thresholds or _thresholds(),
            key=key,
            key_id="learning-dev",
        )
    )


# --- the happy path ---------------------------------------------------------------


def test_a_weekly_run_produces_a_signed_package_per_proposal() -> None:
    session = _session()
    packages = _run(session)

    assert len(packages) == 1
    package = packages[0]
    assert isinstance(package.proposal.target, QuestionWording)
    assert package.proposal.target.pack_id == "base.intake"
    assert package.proposal.target.slot_id == "medication_adherence"
    assert package.proposal.weeks == ("2026-08-03", "2026-08-10")
    assert verify_bundle(package.evidence, key=TEST_KEY) is True
    # files/09 §4's artefacts are unavailable, so nothing can become a PR yet
    assert package.evidence.is_complete is False


def test_the_run_reads_exactly_the_two_views_and_issues_nothing_else() -> None:
    session = _session()
    _run(session)
    assert len(session.statements) == 2
    assert any("analytics.v_session_outcomes" in s for s in session.statements)
    assert any("analytics.v_step_coverage" in s for s in session.statements)
    for statement in session.statements:
        assert statement.lstrip().upper().startswith("SELECT")


def test_every_bundle_cites_the_same_five_sources() -> None:
    citations = _run(_session())[0].evidence.bundle.citations
    assert citations == RUN_CITATIONS
    assert EvidenceSource.CLAUDE_INVARIANT_12 in citations
    assert EvidenceSource.INT_171_ANALYTICS in citations


def test_the_reader_role_is_named_for_an_operator_to_grep() -> None:
    """The grant is the control; the constant is how someone finds it."""
    assert LEARNING_READER_ROLE == "svc_learning_reader"


# --- the gate is INT-171's, and the fake cannot soften it -------------------------


def test_a_thin_cell_off_the_wire_stops_the_whole_run() -> None:
    session = _session(steps=_step_rows(subjects=4))
    with pytest.raises(KAnonymityRefusal) as refusal:
        _run(session)
    assert refusal.value.reason is RefusalReason.BELOW_K


def test_a_narrative_slot_id_off_the_wire_stops_the_whole_run() -> None:
    """The adversary at the surface a database controls.

    A compromised or mis-defined view returning narrative in a dimension does
    not produce a scrubbed proposal — it produces no proposal, and the refusal
    does not echo what it refused.
    """
    session = _session(steps=_step_rows(slot_id=TURKISH_SYMPTOM))
    with pytest.raises(KAnonymityRefusal) as refusal:
        _run(session)
    assert refusal.value.reason is RefusalReason.DIMENSION_NOT_ID_SHAPED
    message = f"{refusal.value!r} {refusal.value}"
    assert TURKISH_SYMPTOM not in message
    assert "Göğsümde" not in message


def test_the_run_cannot_be_asked_for_a_threshold_below_the_floor() -> None:
    with pytest.raises(ThresholdBelowFloor):
        _run(_session(), k=K_ANONYMITY_FLOOR - 1)


def test_an_empty_window_refuses_rather_than_reporting_nothing_happened() -> None:
    """INT-171's rule, inherited: an empty result and a below-floor result
    refuse identically, because telling them apart is itself the disclosure."""
    session = _session(sessions=[], steps=[])
    with pytest.raises(KAnonymityRefusal) as refusal:
        _run(session)
    assert refusal.value.reason is RefusalReason.BELOW_K


def test_a_scheduled_run_cannot_supply_its_own_thresholds() -> None:
    """``run_weekly`` takes ``thresholds`` with no default, and the constructor
    a scheduler would reach for raises. The loop is wired and cannot turn."""
    with pytest.raises(AwaitingHumanValue):
        _run(_session(), thresholds=PromotionThresholds.from_blueprint())


def test_the_run_fails_closed_without_a_usable_signing_key() -> None:
    from intake_learning.signing import SigningKeyUnavailable

    with pytest.raises(SigningKeyUnavailable):
        _run(_session(), key=b"too-short")


def test_a_run_below_the_effect_floor_proposes_nothing() -> None:
    session = _session(steps=_step_rows(answered=38))
    assert _run(session) == ()
    # and the views were still read: silence is a decision, not a skipped read
    assert len(session.statements) == 2


def test_the_measurements_in_the_bundle_are_the_ones_the_run_read() -> None:
    """Not a re-read, and not a summary: the bundle carries the same cells the
    Architect reasoned over, so a reviewer checks the proposal against the
    numbers that produced it (invariant 20)."""
    package = _run(_session())[0]
    (measurement,) = package.evidence.bundle.measurements
    assert measurement.view == STEP_COVERAGE.name
    assert measurement.k == K_ANONYMITY_FLOOR
    assert [cell.dimensions["week_start"] for cell in measurement.cells] == [
        "2026-08-03",
        "2026-08-10",
    ]
    assert measurement.cohort.description == STEP_COVERAGE.cohort_description
    assert SESSION_OUTCOMES.cohort_description != measurement.cohort.description

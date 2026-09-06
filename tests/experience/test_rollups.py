"""INT-240 — satisfaction rollups in services/metrics (files/08 §4 group F).

Two properties this suite exists for, both of them named by the `experience`
threat row in docs/security/threat-model.md:

- **[I] "patient-typed free text carrying identifiers into analytics".** The
  rollup path is *structurally* incapable of carrying a fragment: the reader
  projects each event payload into a frozen point type that has no text field,
  so even a payload that somehow acquired one is dropped at the boundary rather
  than filtered downstream. ``test_a_rollup_of_adversarial_responses_exposes_none_of_it``
  is the adversarial proof, and it tampers with the stored payloads on purpose.
- **[L] linking satisfaction data beyond need** — the k >= 10 floor (files/06 §8;
  files/08 §0c F9; the threat row's own control line) suppresses every figure in
  a cohort too small to hide in, and suppression is total: no mean, no
  distribution, no split, only the count that says why.

And invariant 20 all through: a CSAT or NPS figure is a measurement of a NAMED
COHORT over a STATED WINDOW, taken on a date. The rollup types cannot be
constructed without all three, so a number can never travel as a property of
the product.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from api_harness import ApiHarness, run
from clinical_schemas.events import CsatReason
from intake_api.dev_fixture import DEV_TENANT_ID
from intake_metrics.metrics import (
    CLINICIAN_PULSE,
    CSAT_REASON,
    CSAT_SCORE,
    NPS_MONTHLY,
    publish_csat,
    publish_nps,
    publish_pulse,
)
from intake_metrics.rollups import (
    MIN_COHORT,
    Cohort,
    CsatPoint,
    csat_rollup,
    nps_rollup,
    pulse_rollup,
    roll_up_csat,
    roll_up_nps,
    roll_up_pulse,
)
from intake_platform.db.models import Event
from legal_harness import grant_bound
from prometheus_client import REGISTRY
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

#: A closed window in the past — deliberately not "this month", so a reader
#: scoped to it can be shown to exclude rows written now.
WINDOW_START = datetime(2025, 8, 1, tzinfo=UTC)
WINDOW_END = datetime(2025, 9, 1, tzinfo=UTC)

ADVERSARIAL_FRAGMENTS = (
    "göğsümde baskı",  # a symptom sentence
    "05321234567",  # a reachable phone number
    "Ayşe Yılmaz",  # a clinician's name
)


def _cohort(tenant_id: uuid.UUID = DEV_TENANT_ID) -> Cohort:
    return Cohort(tenant_id=tenant_id, window_start=WINDOW_START, window_end=WINDOW_END)


def _points(n: int, *, score: int = 4, reason: CsatReason = CsatReason.HELPFUL) -> list[CsatPoint]:
    return [CsatPoint(score=score, reason=reason) for _ in range(n)]


# --- shape: a figure is a measurement of a cohort on a date (invariant 20) ----------


def test_a_rollup_cannot_exist_without_its_cohort_and_window() -> None:
    rollup = roll_up_csat(_points(MIN_COHORT), cohort=_cohort())

    assert rollup.cohort.tenant_id == DEV_TENANT_ID
    assert rollup.cohort.window_start == WINDOW_START
    assert rollup.cohort.window_end == WINDOW_END
    assert rollup.measured_at.tzinfo is not None


def test_a_window_that_does_not_move_forward_is_refused() -> None:
    with pytest.raises(ValueError, match="window"):
        Cohort(tenant_id=DEV_TENANT_ID, window_start=WINDOW_END, window_end=WINDOW_START)


def test_a_naive_window_bound_is_refused() -> None:
    with pytest.raises(ValueError, match="timezone"):
        Cohort(
            tenant_id=DEV_TENANT_ID,
            window_start=datetime(2026, 8, 1),  # noqa: DTZ001 — the point of the test
            window_end=WINDOW_END,
        )


# --- csat -------------------------------------------------------------------------


def test_csat_rollup_reports_the_score_distribution_and_the_reason_counts() -> None:
    points = [
        *_points(6, score=5, reason=CsatReason.FELT_HEARD),
        *_points(4, score=3, reason=CsatReason.TOO_LONG),
    ]

    rollup = roll_up_csat(points, cohort=_cohort())

    assert rollup.n == 10
    assert rollup.suppressed is False
    assert rollup.score_counts == {3: 4, 5: 6}
    assert rollup.reason_counts == {CsatReason.FELT_HEARD: 6, CsatReason.TOO_LONG: 4}
    assert rollup.mean_score == pytest.approx(4.2)


def test_a_one_tap_score_without_a_reason_counts_in_the_mean_but_invents_no_reason() -> None:
    """INT-305: a one-tap CSAT is a complete score with no reason. Its score
    joins the distribution and the mean like any other rating, but no reason
    bucket is invented for it — a ``None`` counted as a reason would be a
    fabricated category indistinguishable from a real one (invariant 6)."""
    points = [
        *_points(8, score=5, reason=CsatReason.FELT_HEARD),
        CsatPoint(score=4, reason=None),
        CsatPoint(score=2, reason=None),
    ]

    rollup = roll_up_csat(points, cohort=_cohort())

    assert rollup.n == 10
    assert rollup.suppressed is False
    assert rollup.score_counts == {2: 1, 4: 1, 5: 8}
    # the two reasonless taps raise the count and move the mean, but add no key
    assert rollup.reason_counts == {CsatReason.FELT_HEARD: 8}
    assert rollup.mean_score == pytest.approx(4.6)


def test_csat_rollup_below_the_k_anonymity_floor_is_suppressed_entirely() -> None:
    rollup = roll_up_csat(_points(MIN_COHORT - 1), cohort=_cohort())

    assert rollup.n == MIN_COHORT - 1
    assert rollup.suppressed is True
    assert rollup.mean_score is None
    assert rollup.score_counts == {}
    assert rollup.reason_counts == {}


def test_an_empty_cohort_is_suppressed_rather_than_reported_as_zero() -> None:
    rollup = roll_up_csat([], cohort=_cohort())

    assert rollup.n == 0
    assert rollup.suppressed is True
    assert rollup.mean_score is None


# --- nps --------------------------------------------------------------------------


def test_nps_rollup_uses_the_standard_promoter_detractor_split() -> None:
    scores = [10, 10, 9, 9, 8, 8, 7, 6, 3, 0]  # 4 promoters, 3 passives, 3 detractors

    rollup = roll_up_nps(scores, cohort=_cohort())

    assert rollup.n == 10
    assert (rollup.promoters, rollup.passives, rollup.detractors) == (4, 3, 3)
    assert rollup.nps == pytest.approx(10.0)


def test_nps_rollup_below_the_floor_reports_no_split_and_no_score() -> None:
    rollup = roll_up_nps([10] * (MIN_COHORT - 1), cohort=_cohort())

    assert rollup.suppressed is True
    assert rollup.nps is None
    assert (rollup.promoters, rollup.passives, rollup.detractors) == (None, None, None)


# --- clinician pulse ----------------------------------------------------------------


def test_pulse_rollup_reports_the_mean_and_distribution() -> None:
    rollup = roll_up_pulse([5] * 5 + [3] * 5, cohort=_cohort())

    assert rollup.n == 10
    assert rollup.suppressed is False
    assert rollup.mean_score == pytest.approx(4.0)
    assert rollup.score_counts == {3: 5, 5: 5}


def test_pulse_rollup_below_the_floor_is_suppressed() -> None:
    rollup = roll_up_pulse([5] * (MIN_COHORT - 1), cohort=_cohort())

    assert rollup.suppressed is True
    assert rollup.mean_score is None


# --- the adversarial rollup (the acceptance's own test) -----------------------------


def _tamper_payloads_with_free_text(
    harness: ApiHarness, *, extra: dict[str, object] | None = None
) -> None:
    """Force the failure mode the threat row names: satisfaction free text
    sitting in the very rows the analytics path reads.

    ``text`` is a legal member of csat.v1, so this is the realistic regression
    — a future writer that stops splitting the comment out — and it passes
    schema validation. The rollup must expose nothing anyway, because the
    projection into :class:`CsatPoint` is what drops it, not a filter that
    somebody has to remember to keep.
    """

    async def _tamper() -> None:
        async with AsyncSession(harness.engine) as session, session.begin():
            rows = list(await session.scalars(select(Event).where(Event.event_type == "csat.v1")))
            for row in rows:
                poisoned = dict(row.payload)
                poisoned["text"] = (
                    "Üç gündür göğsümde baskı var, Doktor Ayşe Yılmaz baktı, telefonum 05321234567."
                )
                poisoned.update(extra or {})
                await session.execute(
                    update(Event).where(Event.id == row.id).values(payload=poisoned)
                )

    run(_tamper())


def test_a_rollup_of_adversarial_responses_exposes_none_of_it(harness: ApiHarness) -> None:
    grant_bound(harness, "core", "satisfaction")
    visit = harness.client.post(
        "/v1/visits",
        json={"hospital": "H", "department": "D", "date": "2026-09-03"},
        headers=harness.patient(),
    )
    session_id = visit.json()["id"]
    for index in range(MIN_COHORT):
        response = harness.client.post(
            f"/v1/sessions/{session_id}/csat",
            json={
                "score": (index % 5) + 1,
                "reason": "helpful",
                "text": (
                    "Üç gündür göğsümde baskı ve nefes darlığı var, Doktor Ayşe "
                    "Yılmaz çok ilgilendi, 05321234567 numaralı telefondan "
                    "arayabilirsiniz."
                ),
            },
            headers=harness.patient(),
        )
        assert response.status_code == 201, response.text
    _tamper_payloads_with_free_text(harness)

    cohort = Cohort(
        tenant_id=DEV_TENANT_ID,
        window_start=datetime.now(UTC) - timedelta(days=1),
        window_end=datetime.now(UTC) + timedelta(days=1),
    )

    async def _roll() -> Any:
        async with AsyncSession(harness.engine) as session:
            return await csat_rollup(session, cohort=cohort)

    rollup = run(_roll())

    assert rollup.n == MIN_COHORT
    assert rollup.suppressed is False
    rendered = repr(rollup)
    for fragment in ADVERSARIAL_FRAGMENTS:
        assert fragment not in rendered, f"rollup leaked {fragment!r}"
    assert "text" not in rendered
    # and the point type the reader projects into cannot even hold one
    assert set(CsatPoint.__dataclass_fields__) == {"score", "reason"}


def test_a_payload_the_schema_does_not_recognise_is_refused_rather_than_counted(
    harness: ApiHarness,
) -> None:
    """The other half of the boundary: ``csat.v1`` forbids extra members, so a
    row carrying an unknown key stops the rollup loudly instead of being
    aggregated together with whatever it smuggled in."""
    grant_bound(harness, "core", "satisfaction")
    visit = harness.client.post(
        "/v1/visits",
        json={"hospital": "H", "department": "D", "date": "2026-09-03"},
        headers=harness.patient(),
    )
    harness.client.post(
        f"/v1/sessions/{visit.json()['id']}/csat",
        json={"score": 5, "reason": "helpful"},
        headers=harness.patient(),
    )
    _tamper_payloads_with_free_text(harness, extra={"operator_note": "göğsümde baskı"})

    cohort = Cohort(
        tenant_id=DEV_TENANT_ID,
        window_start=datetime.now(UTC) - timedelta(days=1),
        window_end=datetime.now(UTC) + timedelta(days=1),
    )

    async def _roll() -> Any:
        async with AsyncSession(harness.engine) as session:
            return await csat_rollup(session, cohort=cohort)

    with pytest.raises(ValidationError):
        run(_roll())


def test_the_published_exposition_carries_no_fragment_of_the_free_text(
    harness: ApiHarness,
) -> None:
    grant_bound(harness, "core", "satisfaction")
    visit = harness.client.post(
        "/v1/visits",
        json={"hospital": "H", "department": "D", "date": "2026-09-03"},
        headers=harness.patient(),
    )
    session_id = visit.json()["id"]
    for _ in range(MIN_COHORT):
        harness.client.post(
            f"/v1/sessions/{session_id}/csat",
            json={"score": 5, "reason": "felt_heard", "text": "göğsümde baskı, Ayşe Yılmaz"},
            headers=harness.patient(),
        )
    _tamper_payloads_with_free_text(harness)

    cohort = Cohort(
        tenant_id=DEV_TENANT_ID,
        window_start=datetime.now(UTC) - timedelta(days=1),
        window_end=datetime.now(UTC) + timedelta(days=1),
    )

    async def _roll() -> Any:
        async with AsyncSession(harness.engine) as session:
            return await csat_rollup(session, cohort=cohort)

    publish_csat(run(_roll()))

    exposition = "\n".join(
        f"{name} {sample}"
        for name, sample in ((metric.name, str(metric.samples)) for metric in REGISTRY.collect())
    )
    for fragment in ADVERSARIAL_FRAGMENTS:
        assert fragment not in exposition


# --- publication: catalogued families only, and nothing when suppressed --------------


def test_publishing_moves_the_catalogued_families() -> None:
    before_score = CSAT_SCORE._sum.get()  # noqa: SLF001 — the family is the assertion
    before_reason = CSAT_REASON.labels(reason="helpful")._value.get()  # noqa: SLF001

    publish_csat(roll_up_csat(_points(MIN_COHORT, score=4), cohort=_cohort()))
    publish_nps(roll_up_nps([10] * MIN_COHORT, cohort=_cohort()))
    publish_pulse(roll_up_pulse([4] * MIN_COHORT, cohort=_cohort()))

    assert CSAT_SCORE._sum.get() == before_score + 4 * MIN_COHORT  # noqa: SLF001
    assert CSAT_REASON.labels(reason="helpful")._value.get() == before_reason + MIN_COHORT  # noqa: SLF001
    assert NPS_MONTHLY._value.get() == pytest.approx(100.0)  # noqa: SLF001
    assert CLINICIAN_PULSE._value.get() == pytest.approx(4.0)  # noqa: SLF001


def test_a_suppressed_rollup_publishes_nothing() -> None:
    before_score = CSAT_SCORE._sum.get()  # noqa: SLF001
    before_nps = NPS_MONTHLY._value.get()  # noqa: SLF001
    before_pulse = CLINICIAN_PULSE._value.get()  # noqa: SLF001

    publish_csat(roll_up_csat(_points(MIN_COHORT - 1), cohort=_cohort()))
    publish_nps(roll_up_nps([10] * (MIN_COHORT - 1), cohort=_cohort()))
    publish_pulse(roll_up_pulse([4] * (MIN_COHORT - 1), cohort=_cohort()))

    assert CSAT_SCORE._sum.get() == before_score  # noqa: SLF001
    assert NPS_MONTHLY._value.get() == before_nps  # noqa: SLF001
    assert CLINICIAN_PULSE._value.get() == before_pulse  # noqa: SLF001


# --- the DB readers ------------------------------------------------------------------


def test_readers_scope_to_the_cohorts_tenant_and_window(harness: ApiHarness) -> None:
    grant_bound(harness, "satisfaction")
    for score in (9, 9, 10):
        harness.client.post("/v1/feedback/nps", json={"score": score}, headers=harness.patient())

    async def _roll(cohort: Cohort) -> Any:
        async with AsyncSession(harness.engine) as session:
            return await nps_rollup(session, cohort=cohort)

    inside = run(
        _roll(
            Cohort(
                tenant_id=DEV_TENANT_ID,
                window_start=datetime.now(UTC) - timedelta(days=1),
                window_end=datetime.now(UTC) + timedelta(days=1),
            )
        )
    )
    outside = run(_roll(_cohort()))
    other_tenant = run(
        _roll(
            Cohort(
                tenant_id=uuid.uuid4(),
                window_start=datetime.now(UTC) - timedelta(days=1),
                window_end=datetime.now(UTC) + timedelta(days=1),
            )
        )
    )

    assert inside.n == 3
    assert outside.n == 0
    assert other_tenant.n == 0


def test_the_pulse_reader_reads_clinician_pulse_events(harness: ApiHarness) -> None:
    async def _seed() -> None:
        async with AsyncSession(harness.engine) as session, session.begin():
            for _ in range(MIN_COHORT):
                session.add(
                    Event(
                        tenant_id=DEV_TENANT_ID,
                        session_id=None,
                        event_type="clinician_pulse.v1",
                        payload={
                            "schema_id": "intake.clinical.clinician_pulse.v1",
                            "tenant_id": str(DEV_TENANT_ID),
                            "clinician_ref": "clinician:abc",
                            "score": 4,
                        },
                    )
                )

    run(_seed())

    async def _roll() -> Any:
        async with AsyncSession(harness.engine) as session:
            return await pulse_rollup(
                session,
                cohort=Cohort(
                    tenant_id=DEV_TENANT_ID,
                    window_start=datetime.now(UTC) - timedelta(days=1),
                    window_end=datetime.now(UTC) + timedelta(days=1),
                ),
            )

    rollup = run(_roll())

    assert rollup.n == MIN_COHORT
    assert rollup.mean_score == pytest.approx(4.0)
    # the clinician's id never becomes a label or a rollup member (invariant 6)
    assert "clinician:abc" not in repr(rollup)

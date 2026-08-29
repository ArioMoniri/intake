"""INT-171 — the k-anonymity gate (files/09 §6 ``k_anonymity``; files/10 §9 learning row).

Acceptance line under test, verbatim (docs/backlog/issues.yaml):
  "k>=10 enforced at query layer; refusals metered; no free-text outside
   review UI"

The point of this suite is that the helper is a **gate**, not a utility. A
k-anonymity function nobody is obliged to call is decoration; every test here
asks whether a small cell can reach a caller by some route:

- a cohort of one;
- a cohort of one wearing forty sessions (rows are not people);
- a cohort that is fine until a filter narrows it;
- a quasi-identifier combination (branch × age band × date) that singles a
  person out even though each dimension alone is coarse;
- one small cell among many good ones (suppress-and-continue would let the
  small cell be recovered by subtraction, so the whole view refuses);
- the refusal itself as a side channel — which cohort failed, how big it was,
  and whether "nothing to report" is distinguishable from "too few to report".

legal: KVKK-16, KSVY-16.  sec_row: `learning-loops`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime

import pytest
from intake_platform.analytics import (
    K_ANONYMITY_FLOOR,
    AnalyticsView,
    Cell,
    Cohort,
    KAnonymityRefusal,
    RefusalReason,
    ThresholdBelowFloor,
    materialise,
)
from intake_platform.analytics.k_anonymity import (
    ANALYTICS_VIEW_MATERIALISED,
    ANALYTICS_VIEW_REFUSED,
)

# A view shaped like the three real ones, declared here so the adversarial
# cases can hold the data still. `age_band` is deliberately part of the
# quasi-identifier set in this fixture and deliberately absent from the
# production registry: no date of birth is collected or persisted anywhere in
# the product (files/HUMAN_BLOCKERS.md HB-L20), so an age band is a dimension
# the gate must handle rather than one our own views can offer.
BRANCH_VIEW = AnalyticsView(
    name="test.branch_age_week",
    relation="analytics.v_test_branch_age_week",
    dimensions=("branch", "age_band", "week_start"),
    measures=("sessions",),
    cohort_description="intake sessions by branch, age band and ISO week",
    narrative_exclusion="counts only; this fixture carries no narrative column",
)


def _cohort() -> Cohort:
    return Cohort(
        description="INTAKE pilot tenants, completed intakes",
        window_start=datetime(2026, 8, 3, tzinfo=UTC),
        window_end=datetime(2026, 8, 31, tzinfo=UTC),
    )


def _cell(
    branch: str,
    age_band: str,
    week_start: str,
    *,
    subjects: int,
    sessions: int | None = None,
    tenants: int = 3,
) -> Cell:
    return Cell(
        dimensions={"branch": branch, "age_band": age_band, "week_start": week_start},
        subjects=subjects,
        tenants=tenants,
        measures={"sessions": subjects if sessions is None else sessions},
    )


def _healthy_cells(count: int = 4) -> tuple[Cell, ...]:
    return tuple(
        _cell("dermatoloji", "adult", f"2026-08-{3 + 7 * i:02d}", subjects=K_ANONYMITY_FLOOR + i)
        for i in range(count)
    )


def _counter_value(counter: object, **labels: str) -> float:
    child = counter.labels(**labels)  # type: ignore[attr-defined]
    return float(child._value.get())  # noqa: SLF001


# --- the threshold is supplied, never assumed -------------------------------------


def test_the_gate_has_no_default_threshold() -> None:
    """`k` is keyword-only with no default: a caller states the threshold it
    is claiming, or it does not get a figure."""
    with pytest.raises(TypeError):
        materialise(BRANCH_VIEW, _healthy_cells(), cohort=_cohort())  # type: ignore[call-arg]


def test_a_threshold_below_the_blueprint_floor_is_refused() -> None:
    """files/06 §8, files/09 §4/§6 and the INT-171 acceptance all state k >= 10.
    A caller may raise the bar; it may not lower it."""
    with pytest.raises(ThresholdBelowFloor):
        materialise(BRANCH_VIEW, _healthy_cells(), cohort=_cohort(), k=K_ANONYMITY_FLOOR - 1)


def test_a_higher_threshold_is_honoured() -> None:
    cells = (_cell("dermatoloji", "adult", "2026-08-03", subjects=12),)
    assert materialise(BRANCH_VIEW, cells, cohort=_cohort(), k=K_ANONYMITY_FLOOR).cells == cells
    with pytest.raises(KAnonymityRefusal):
        materialise(BRANCH_VIEW, cells, cohort=_cohort(), k=25)


def test_exactly_k_materialises_and_one_below_refuses() -> None:
    """Near-miss control on the boundary itself."""
    at_floor = (_cell("uroloji", "adult", "2026-08-10", subjects=K_ANONYMITY_FLOOR),)
    below = (_cell("uroloji", "adult", "2026-08-10", subjects=K_ANONYMITY_FLOOR - 1),)
    assert materialise(BRANCH_VIEW, at_floor, cohort=_cohort(), k=K_ANONYMITY_FLOOR).cells
    with pytest.raises(KAnonymityRefusal):
        materialise(BRANCH_VIEW, below, cohort=_cohort(), k=K_ANONYMITY_FLOOR)


# --- adversarial re-identification -------------------------------------------------


def test_a_cohort_of_one_refuses_the_whole_view() -> None:
    cells = (_cell("tibbi_genetik", "adult", "2026-08-17", subjects=1),)
    with pytest.raises(KAnonymityRefusal) as raised:
        materialise(BRANCH_VIEW, cells, cohort=_cohort(), k=K_ANONYMITY_FLOOR)
    assert raised.value.reason is RefusalReason.BELOW_K


def test_forty_sessions_from_one_patient_is_still_a_cohort_of_one() -> None:
    """The trap this gate exists for: row counts are not people. A chronic
    patient with weekly follow-ups produces a fat cell that is one person."""
    cells = (_cell("nefroloji", "adult", "2026-08-17", subjects=1, sessions=40),)
    with pytest.raises(KAnonymityRefusal) as raised:
        materialise(BRANCH_VIEW, cells, cohort=_cohort(), k=K_ANONYMITY_FLOOR)
    assert raised.value.reason is RefusalReason.BELOW_K


def test_a_cohort_that_becomes_one_after_filtering_refuses() -> None:
    """Every cell clears the floor until the caller narrows to one branch."""
    cells = (
        *_healthy_cells(),
        _cell("tibbi_genetik", "adult", "2026-08-17", subjects=1),
    )
    with pytest.raises(KAnonymityRefusal):
        materialise(BRANCH_VIEW, cells, cohort=_cohort(), k=K_ANONYMITY_FLOOR)
    with pytest.raises(KAnonymityRefusal):
        materialise(
            BRANCH_VIEW,
            cells,
            cohort=_cohort(),
            k=K_ANONYMITY_FLOOR,
            where={"branch": "tibbi_genetik"},
        )
    # ... and the filter that keeps only healthy cells is served
    served = materialise(
        BRANCH_VIEW,
        cells,
        cohort=_cohort(),
        k=K_ANONYMITY_FLOOR,
        where={"branch": "dermatoloji"},
    )
    assert len(served.cells) == len(_healthy_cells())


def test_branch_and_age_band_and_date_together_single_someone_out() -> None:
    """Each dimension is coarse on its own; the combination is a person.

    The branch has 30 subjects that month and the age band has 40 across
    branches, so a one-dimensional view of either is safe. Crossed with the
    week, one cell holds a single patient — and the view refuses.
    """
    cells = (
        _cell("cocuk_endokrinoloji", "child", "2026-08-03", subjects=14),
        _cell("cocuk_endokrinoloji", "child", "2026-08-10", subjects=15),
        # the one 84-year-old seen in that clinic, that week
        _cell("cocuk_endokrinoloji", "geriatric", "2026-08-17", subjects=1),
    )
    with pytest.raises(KAnonymityRefusal) as raised:
        materialise(BRANCH_VIEW, cells, cohort=_cohort(), k=K_ANONYMITY_FLOOR)
    assert raised.value.reason is RefusalReason.BELOW_K


def test_one_small_cell_refuses_the_entire_view_rather_than_suppressing_it() -> None:
    """Suppress-and-continue is the wrong shape: a reader who receives every
    cell but one, plus any wider aggregate of the same population, recovers the
    missing cell by subtraction. The artefact is atomic — all of it or none."""
    cells = (*_healthy_cells(), _cell("algoloji", "adult", "2026-08-24", subjects=2))
    with pytest.raises(KAnonymityRefusal) as raised:
        materialise(BRANCH_VIEW, cells, cohort=_cohort(), k=K_ANONYMITY_FLOOR)
    assert getattr(raised.value, "cells", None) is None
    assert not [
        attribute
        for attribute in vars(raised.value).values()
        if isinstance(attribute, (list, tuple)) and attribute
    ]


# --- the refusal is not a side channel ---------------------------------------------


def test_the_refusal_names_no_cohort_and_no_count() -> None:
    """Saying *which* cell failed, or how many subjects it held, is the
    disclosure the gate exists to prevent."""
    cells = (
        *_healthy_cells(),
        _cell("adli_tip", "geriatric", "2026-08-24", subjects=3, sessions=3),
    )
    with pytest.raises(KAnonymityRefusal) as raised:
        materialise(BRANCH_VIEW, cells, cohort=_cohort(), k=K_ANONYMITY_FLOOR)
    rendered = f"{raised.value!r} {raised.value}"
    for leak in ("adli_tip", "geriatric", "2026-08-24"):
        assert leak not in rendered
    # no bare small integer that could be read as the offending subject count
    assert not re.search(r"\b[1-9]\b", rendered.replace(str(K_ANONYMITY_FLOOR), ""))
    assert raised.value.view == BRANCH_VIEW.name
    assert raised.value.k == K_ANONYMITY_FLOOR


def test_an_empty_result_and_a_single_subject_result_refuse_identically() -> None:
    """Otherwise refusal is an oracle: refuse means "someone was there, but
    fewer than k"; empty means "nobody". Distinguishing them discloses the
    existence of a patient in a cell the gate just declined to describe."""
    with pytest.raises(KAnonymityRefusal) as on_empty:
        materialise(BRANCH_VIEW, (), cohort=_cohort(), k=K_ANONYMITY_FLOOR)
    with pytest.raises(KAnonymityRefusal) as on_one:
        materialise(
            BRANCH_VIEW,
            (_cell("kbb", "adult", "2026-08-24", subjects=1),),
            cohort=_cohort(),
            k=K_ANONYMITY_FLOOR,
        )
    assert on_empty.value.reason is on_one.value.reason
    assert str(on_empty.value) == str(on_one.value)


def test_a_filter_that_matches_nothing_refuses_like_a_small_cohort() -> None:
    with pytest.raises(KAnonymityRefusal) as raised:
        materialise(
            BRANCH_VIEW,
            _healthy_cells(),
            cohort=_cohort(),
            k=K_ANONYMITY_FLOOR,
            where={"branch": "kardiyoloji"},
        )
    assert raised.value.reason is RefusalReason.BELOW_K


# --- no free text, structurally ----------------------------------------------------


def test_a_free_text_dimension_value_is_refused_and_never_echoed() -> None:
    """ "No free-text outside the review UI" is enforced on the value, not on a
    reviewer's memory: a dimension that is not id-shaped stops the view, and
    the refusal does not repeat the sentence it just refused."""
    sentence = "iki gündür göğsümde baskı var, Ahmet Bey aradı"
    cells = (
        Cell(
            dimensions={"branch": sentence, "age_band": "adult", "week_start": "2026-08-24"},
            subjects=40,
            tenants=4,
            measures={"sessions": 40},
        ),
    )
    with pytest.raises(KAnonymityRefusal) as raised:
        materialise(BRANCH_VIEW, cells, cohort=_cohort(), k=K_ANONYMITY_FLOOR)
    assert raised.value.reason is RefusalReason.DIMENSION_NOT_ID_SHAPED
    assert sentence not in f"{raised.value!r} {raised.value}"
    assert "Ahmet" not in f"{raised.value!r} {raised.value}"


def test_an_over_long_identifier_is_refused() -> None:
    cells = (_cell("x" * 65, "adult", "2026-08-24", subjects=40),)
    with pytest.raises(KAnonymityRefusal) as raised:
        materialise(BRANCH_VIEW, cells, cohort=_cohort(), k=K_ANONYMITY_FLOOR)
    assert raised.value.reason is RefusalReason.DIMENSION_NOT_ID_SHAPED


def test_a_non_integer_measure_is_refused() -> None:
    cells = (
        Cell(
            dimensions={"branch": "kbb", "age_band": "adult", "week_start": "2026-08-24"},
            subjects=40,
            tenants=4,
            measures={"sessions": "kırk"},  # type: ignore[dict-item]
        ),
    )
    with pytest.raises(KAnonymityRefusal) as raised:
        materialise(BRANCH_VIEW, cells, cohort=_cohort(), k=K_ANONYMITY_FLOOR)
    assert raised.value.reason is RefusalReason.MEASURE_NOT_A_COUNT


def test_a_cell_whose_dimensions_do_not_match_the_view_is_refused() -> None:
    cells = (
        Cell(
            dimensions={"branch": "kbb", "week_start": "2026-08-24"},
            subjects=40,
            tenants=4,
            measures={"sessions": 40},
        ),
    )
    with pytest.raises(KAnonymityRefusal) as raised:
        materialise(BRANCH_VIEW, cells, cohort=_cohort(), k=K_ANONYMITY_FLOOR)
    assert raised.value.reason is RefusalReason.DIMENSION_SET_MISMATCH


def test_filtering_on_a_dimension_the_view_does_not_declare_is_a_programming_error() -> None:
    with pytest.raises(ValueError, match="not a dimension"):
        materialise(
            BRANCH_VIEW,
            _healthy_cells(),
            cohort=_cohort(),
            k=K_ANONYMITY_FLOOR,
            where={"tenant_id": "acibadem"},
        )


# --- invariant 20: a figure is a measurement, never a property ---------------------


def test_a_materialisation_carries_its_cohort_window_and_instant() -> None:
    before = datetime.now(UTC)
    measurement = materialise(BRANCH_VIEW, _healthy_cells(), cohort=_cohort(), k=K_ANONYMITY_FLOOR)
    assert measurement.cohort == _cohort()
    assert before <= measurement.measured_at <= datetime.now(UTC)
    assert measurement.k == K_ANONYMITY_FLOOR
    provenance = measurement.provenance
    assert "INTAKE pilot tenants" in provenance
    assert "2026-08-03" in provenance and "2026-08-31" in provenance
    assert "measured" in provenance.lower()


def test_a_cohort_needs_a_description_and_a_forward_window_with_timezones() -> None:
    with pytest.raises(ValueError, match="description"):
        Cohort(
            description="  ",
            window_start=datetime(2026, 8, 3, tzinfo=UTC),
            window_end=datetime(2026, 8, 31, tzinfo=UTC),
        )
    with pytest.raises(ValueError, match="timezone"):
        Cohort(
            description="x",
            window_start=datetime(2026, 8, 3),
            window_end=datetime(2026, 8, 31, tzinfo=UTC),
        )
    with pytest.raises(ValueError, match="strictly after"):
        Cohort(
            description="x",
            window_start=datetime(2026, 8, 31, tzinfo=UTC),
            window_end=datetime(2026, 8, 3, tzinfo=UTC),
        )


# --- "refusals metered" ------------------------------------------------------------


def test_refusals_are_metered_by_view_and_reason() -> None:
    before = _counter_value(
        ANALYTICS_VIEW_REFUSED, view=BRANCH_VIEW.name, reason=RefusalReason.BELOW_K.value
    )
    with pytest.raises(KAnonymityRefusal):
        materialise(
            BRANCH_VIEW,
            (_cell("kbb", "adult", "2026-08-24", subjects=2),),
            cohort=_cohort(),
            k=K_ANONYMITY_FLOOR,
        )
    after = _counter_value(
        ANALYTICS_VIEW_REFUSED, view=BRANCH_VIEW.name, reason=RefusalReason.BELOW_K.value
    )
    assert after == before + 1


def test_materialisations_are_metered() -> None:
    before = _counter_value(ANALYTICS_VIEW_MATERIALISED, view=BRANCH_VIEW.name)
    materialise(BRANCH_VIEW, _healthy_cells(), cohort=_cohort(), k=K_ANONYMITY_FLOOR)
    after = _counter_value(ANALYTICS_VIEW_MATERIALISED, view=BRANCH_VIEW.name)
    assert after == before + 1


def test_the_refusal_metric_labels_carry_no_cohort_values() -> None:
    """A metric label is a low-cardinality enumeration (inv. 6). Labelling a
    refusal with the offending branch or week would publish exactly the cell
    the refusal withheld — to Prometheus, which retains it."""
    labels: Mapping[str, object] = ANALYTICS_VIEW_REFUSED._labelnames  # noqa: SLF001
    assert tuple(labels) == ("view", "reason")
    assert tuple(ANALYTICS_VIEW_MATERIALISED._labelnames) == ("view",)  # noqa: SLF001

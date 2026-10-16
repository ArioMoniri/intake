"""INT-490 — small-cell suppression and the check across views (LD-06).

Every property is paired with its near miss:

- a cell of 9 withholds the whole view, a cell of 10 shows it;
- a view whose population is under 10 is not even listed, one of exactly 10
  is;
- a dimension combination that isolates fewer than 10 people (a thin
  protocol version, a thin question outcome) is suppressed while its wide
  neighbours show;
- a cross-view subtraction that WOULD recover a small group (the funnel's
  population minus the platform view's population) is found and the
  lower-priority view is withheld — and an independent, exhaustive oracle
  (``research_population.recoverable_small_groups``) confirms both that the
  attack existed before the check and that nothing small is recoverable after;
- overlapping views that do NOT determine a small group are left alone.

legal: LD-06 admin_analytics.conditions; KVKK m.28(1)(b); Yönetmelik m.10.
"""

from __future__ import annotations

import random

import pytest
from intake_platform.analytics import K_ANONYMITY_FLOOR, ThresholdBelowFloor
from intake_platform.analytics.research import (
    FAMILY_VIEW_KINDS,
    QUESTION_VIEW_KINDS,
    NotCollected,
    Period,
    Platform,
    QuestionOutcome,
    QuestionRecord,
    RepeatBand,
    Stage,
    SubjectRecord,
    ViewId,
    ViewKind,
    WithheldReason,
    build_release,
    find_recoverable_small_set,
)
from research_population import (
    PROTOCOL,
    VERSION,
    people,
    person,
    recoverable_small_groups,
    release_is_safe,
    shown_cells,
    skipped,
    typed_answer,
)

K = K_ANONYMITY_FLOOR
WEEK = Period(2026, 39)
ALL = frozenset(ViewKind)


def release(records: list[SubjectRecord], collected: frozenset[ViewKind] = ALL):  # type: ignore[no-untyped-def]
    return build_release(
        records,
        period=WEEK,
        k=K,
        collected=collected,
        not_collected={kind: "not_recorded" for kind in set(ViewKind) - set(collected)},
    )


def funnel(protocol: str = PROTOCOL, version: str = VERSION) -> ViewId:
    return ViewId(ViewKind.FUNNEL, protocol, version)


def stages(invited: int, started: int, finished: int, shared: int, **kw: object) -> list:  # type: ignore[type-arg]
    return [
        *people(invited, Stage.INVITED, **kw),
        *people(started, Stage.STARTED, **kw),
        *people(finished, Stage.FINISHED, **kw),
        *people(shared, Stage.SHARED, **kw),
    ]


# --- the floor, within a view ------------------------------------------------------


def test_the_floor_is_int171s_and_cannot_be_lowered() -> None:
    assert K == 10
    with pytest.raises(ThresholdBelowFloor):
        build_release([], period=WEEK, k=9, collected=ALL, not_collected={})


def test_a_cell_of_nine_withholds_the_whole_view() -> None:
    out = release(stages(10, 10, 10, 9))
    item = out.lookup(funnel())
    assert item is not None and not hasattr(item, "cells")
    assert item.reason is WithheldReason.BELOW_K  # type: ignore[union-attr]


def test_a_cell_of_ten_shows_the_view() -> None:
    out = release(stages(10, 10, 10, 10))
    item = out.lookup(funnel())
    assert item is not None and hasattr(item, "cells")
    assert {cell.value: cell.subjects for cell in item.cells} == {  # type: ignore[union-attr]
        "invited": 10,
        "started": 10,
        "finished": 10,
        "shared": 10,
    }


def test_a_zero_cell_is_published_as_int171_publishes_it() -> None:
    out = release(stages(10, 0, 10, 10))
    item = out.lookup(funnel())
    assert item is not None and hasattr(item, "cells")
    assert {c.value: c.subjects for c in item.cells}["started"] == 0  # type: ignore[union-attr]


def test_a_population_under_the_floor_is_not_even_listed() -> None:
    out = release(stages(9, 0, 0, 0))
    assert out.lookup(funnel()) is None
    assert out.shown == () and out.withheld == ()


def test_a_population_of_exactly_ten_is_listed() -> None:
    out = release(stages(10, 0, 0, 0))
    assert out.lookup(funnel()) is not None


def test_a_withheld_view_carries_no_cell_at_all() -> None:
    out = release(stages(10, 10, 10, 3))
    funnel_view = out.lookup(funnel())
    assert funnel_view is not None and not hasattr(funnel_view, "cells")
    assert out.withheld and all(not hasattr(item, "cells") for item in out.withheld)


# --- dimension combinations that isolate fewer than k ------------------------------


def test_a_thin_protocol_version_is_suppressed_beside_a_wide_one() -> None:
    wide = stages(10, 10, 10, 10)
    thin = stages(3, 0, 9, 0, version="v2")
    out = release(wide + thin)
    assert hasattr(out.lookup(funnel()), "cells")
    thin_view = out.lookup(funnel(version="v2"))
    assert thin_view is not None and thin_view.reason is WithheldReason.BELOW_K  # type: ignore[union-attr]


def test_a_question_outcome_isolating_three_people_is_suppressed() -> None:
    """Fifteen reached the question, three abandoned it. The outcome view is
    withheld for its cell of three — and so is every view that would hand the
    three back by subtraction: the twelve who answered, shown by mode or by
    time, taken from the fifteen who started, IS the three."""
    answered = people(12, Stage.STARTED, questions={"q.onset": typed_answer()})
    abandoned = people(
        3,
        Stage.STARTED,
        questions={
            "q.onset": QuestionRecord(outcome=QuestionOutcome.ABANDONED, repeat=RepeatBand.NONE)
        },
    )
    records = answered + abandoned
    out = release(records)
    outcome = out.lookup(ViewId(ViewKind.QUESTION_OUTCOME, PROTOCOL, VERSION, "q.onset"))
    assert outcome is not None and outcome.reason is WithheldReason.BELOW_K  # type: ignore[union-attr]
    for kind in (ViewKind.QUESTION_MODE, ViewKind.QUESTION_TIME):
        item = out.lookup(ViewId(kind, PROTOCOL, VERSION, "q.onset"))
        assert item is not None and item.reason is WithheldReason.CROSS_VIEW  # type: ignore[union-attr]
    # the oracle agrees the attack was real, and that nothing small is left
    attack = [funnel(), ViewId(ViewKind.QUESTION_MODE, PROTOCOL, VERSION, "q.onset")]
    assert 3 in recoverable_small_groups(shown_cells(attack, records), K)
    assert hasattr(out.lookup(funnel()), "cells")
    assert release_is_safe(out, records)


# --- across views -----------------------------------------------------------------


def _platform_population() -> list[SubjectRecord]:
    """Thirty people; the platform is known for twenty-seven of them, so the
    funnel total minus the platform total is a group of three."""
    records = [
        *people(5, Stage.INVITED, platform=Platform.IOS),
        *people(5, Stage.INVITED, platform=Platform.ANDROID),
        *people(5, Stage.FINISHED, platform=Platform.IOS),
        *people(4, Stage.FINISHED, platform=Platform.ANDROID),
        *people(4, Stage.SHARED, platform=Platform.IOS),
        *people(4, Stage.SHARED, platform=Platform.ANDROID),
    ]
    records += [person(Stage.FINISHED), person(Stage.SHARED), person(Stage.SHARED)]
    return records


def test_the_cross_view_attack_exists_without_the_check() -> None:
    records = _platform_population()
    views = [funnel(), ViewId(ViewKind.PLATFORM, PROTOCOL, VERSION)]
    assert 3 in recoverable_small_groups(shown_cells(views, records), K)


def test_a_cross_view_subtraction_yields_no_recoverable_cell() -> None:
    records = _platform_population()
    out = release(records, collected=frozenset({ViewKind.FUNNEL, ViewKind.PLATFORM}))
    assert hasattr(out.lookup(funnel()), "cells")
    platform = out.lookup(ViewId(ViewKind.PLATFORM, PROTOCOL, VERSION))
    assert platform is not None and platform.reason is WithheldReason.CROSS_VIEW  # type: ignore[union-attr]
    assert release_is_safe(out, records)


def test_the_check_iterates_until_nothing_small_is_recoverable() -> None:
    """Twenty-five started; question 2 was reached by twenty-two, so both of
    its views over 'who reached q2' give away the three who did not."""
    reached_both = people(
        12, Stage.STARTED, questions={"q.1": typed_answer(), "q.2": typed_answer()}
    )
    reached_both += people(10, Stage.STARTED, questions={"q.1": skipped(), "q.2": skipped()})
    reached_one = people(3, Stage.STARTED, questions={"q.1": skipped()})
    records = reached_both + reached_one
    out = release(records, collected=frozenset({ViewKind.FUNNEL, *QUESTION_VIEW_KINDS}))
    for kind in (ViewKind.QUESTION_OUTCOME, ViewKind.QUESTION_REPEAT):
        item = out.lookup(ViewId(kind, PROTOCOL, VERSION, "q.2"))
        assert item is not None and not hasattr(item, "cells"), kind
    assert release_is_safe(out, records)


def test_overlapping_views_that_determine_nothing_small_are_left_alone() -> None:
    cells = {
        "a": frozenset(range(1, 13)),
        "b": frozenset(range(3, 15)),
    }
    assert find_recoverable_small_set(cells, k=K) is None
    nested = {"a": frozenset(range(1, 13)), "b": frozenset(range(1, 11))}
    violation = find_recoverable_small_set(nested, k=K)
    assert violation is not None and violation.cells == {"a", "b"}


def test_running_out_of_search_budget_fails_closed() -> None:
    nested = {"a": frozenset(range(1, 13)), "b": frozenset(range(1, 11))}
    violation = find_recoverable_small_set(nested, k=K, budget=0)
    assert violation is not None and violation.exhausted


@pytest.mark.parametrize("seed", [3, 17, 29, 101, 4049])
def test_random_populations_always_release_safely(seed: int) -> None:
    rng = random.Random(seed)  # noqa: S311 — a reproducible synthetic population, not a secret
    records = [
        person(
            rng.choice([Stage.INVITED, Stage.FINISHED, Stage.SHARED]),
            platform=rng.choice([Platform.IOS, Platform.ANDROID, None]),
        )
        for _ in range(rng.randint(25, 60))
    ]
    out = release(records, collected=frozenset({ViewKind.FUNNEL, ViewKind.PLATFORM}))
    assert release_is_safe(out, records)


# --- shape and structure ------------------------------------------------------------


def test_a_kind_without_a_source_is_reported_with_its_reason_never_absent() -> None:
    out = release(stages(10, 10, 10, 10), collected=frozenset({ViewKind.FUNNEL}))
    assert NotCollected(ViewKind.TRIAGE, "not_recorded") in out.not_collected
    assert {item.kind for item in out.not_collected} == set(ViewKind) - {ViewKind.FUNNEL}
    with pytest.raises(ValueError, match="exactly once"):
        build_release([], period=WEEK, k=K, collected=FAMILY_VIEW_KINDS, not_collected={})


@pytest.mark.parametrize(
    "bad",
    [
        {"protocol": "göğüs ağrısı"},
        {"version": "v 2"},
        {"questions": {"what did you say": skipped()}},
    ],
)
def test_free_text_in_a_dimension_value_is_refused(bad: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="id-shaped"):
        release([person(Stage.STARTED, **bad)])  # type: ignore[arg-type]


def test_a_person_counts_once_per_protocol_version() -> None:
    twin = person(Stage.INVITED, subject="same")
    with pytest.raises(ValueError, match="once"):
        release([twin, person(Stage.SHARED, subject="same")])


def test_structurally_impossible_records_are_refused() -> None:
    from intake_platform.analytics.research import TriageBucket

    with pytest.raises(ValueError):
        person(Stage.STARTED, triage=TriageBucket.RED)
    with pytest.raises(ValueError):
        person(Stage.INVITED, questions={"q.1": skipped()})
    with pytest.raises(ValueError):
        QuestionRecord(
            outcome=QuestionOutcome.SKIPPED,
            repeat=RepeatBand.NONE,
            time_band=None,
            input_mode=typed_answer().input_mode,
        )


def test_periods_are_closed_iso_weeks_only() -> None:
    from datetime import UTC, datetime

    from intake_platform.analytics.research import PeriodRefused

    assert Period.parse("2026-W39") == WEEK
    assert WEEK.id == "2026-W39" and WEEK.end - WEEK.start == WEEK.following.start - WEEK.start
    assert WEEK.previous.following == WEEK
    for text in ("2026-39", "2026-W60", "26-W01", "2026-W3"):
        with pytest.raises(PeriodRefused):
            Period.parse(text)
    now = datetime(2026, 9, 24, 12, tzinfo=UTC)  # inside 2026-W39
    assert Period.latest_closed(now) == Period(2026, 38)
    with pytest.raises(PeriodRefused, match="period_not_closed"):
        WEEK.require_closed(now)
    assert Period(2026, 38).require_closed(now) == Period(2026, 38)
    with pytest.raises(ValueError):
        Period.containing(datetime(2026, 9, 24))  # noqa: DTZ001 — a naive instant is the point

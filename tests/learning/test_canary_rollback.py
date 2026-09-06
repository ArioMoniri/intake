"""INT-173 — `canary_rollback`: the guardrail controller promotes or reverts.

Acceptance line under test, verbatim (docs/backlog/issues.yaml INT-173):
  "auto-rollback on acceptance -5, safety blocks +50 percent, completion -5,
   CSAT -0.3; simulated dip test"

The magnitudes and their units are the blueprint's, not this file's. files/09 §4
"Path to production" states them exactly:
  "canary 5 % → 25 % → 100 % with automatic rollback if guardrail KPIs move
   (acceptance −5 pts, safety blocks +50 %, completion −5 pts, CSAT −0.3)"
and files/09 §6 states the test's shape:
  "`canary_rollback`: simulated KPI dip triggers rollback within one evaluation
   window."

So acceptance and completion move in **percentage points** (the `note.acceptance_rate`
and `session.completion_rate` catalogue ratios, read as a percentage — their 08 §4
targets are written ">= 70 %" / ">= 80 %"); CSAT moves on the 1–5 `csat.score`; and
safety blocks move as a **relative** rise on a per-session block rate (the raw
`policyguard.blocks_total` count is meaningless across a 5 % vs a 25 % cohort, so the
guardrail is a rate). Every regression is measured against the pre-canary baseline —
never an invented one (CLAUDE.md invariant 17): a window with no baseline, or a stage
with no reading, does not promote.

Determinism is the whole point of a "simulated dip test": the controller is pure —
synthetic KPI snapshots in, a decision out, no wall-clock and no network (docs/TDD.md
rule 6). The near-miss negative control (docs/TDD.md rule 2) matters more than the
positive: a threshold set one point too generous would let a real regression through
and nothing would go red in production.

sec_row: `learning-loops`.
"""

from __future__ import annotations

import pytest
from intake_learning.canary import (
    ACCEPTANCE_DROP_PTS,
    CANARY_STAGES,
    COMPLETION_DROP_PTS,
    CSAT_DROP,
    SAFETY_BLOCK_RISE_FRACTION,
    CanaryAction,
    CanaryStage,
    GuardrailKpis,
    RolloutStatus,
    evaluate_window,
    run_canary,
)

# A steady, healthy production baseline the canary is measured against. Values are
# plausible for a live intake service but nothing here depends on their being real —
# the controller only ever compares a window to this baseline.
BASELINE = GuardrailKpis(
    acceptance_rate=82.0,  # percentage points (note.acceptance_rate ×100)
    safety_block_rate=0.04,  # PolicyGuard blocks per session
    completion_rate=88.0,  # percentage points (session.completion_rate ×100)
    csat=4.4,  # mean score on 1–5 (csat.score)
)


def _healthy_like_baseline() -> GuardrailKpis:
    """A window that reproduces the baseline — no guardrail has moved at all."""
    return GuardrailKpis(
        acceptance_rate=BASELINE.acceptance_rate,
        safety_block_rate=BASELINE.safety_block_rate,
        completion_rate=BASELINE.completion_rate,
        csat=BASELINE.csat,
    )


def _windows(**overrides: GuardrailKpis) -> dict[CanaryStage, GuardrailKpis]:
    """A healthy reading for every stage, with the named stages overridden."""
    windows = {stage: _healthy_like_baseline() for stage in CANARY_STAGES}
    for stage_name, snapshot in overrides.items():
        windows[CanaryStage[stage_name]] = snapshot
    return windows


# --- the stages are the blueprint's 5 / 25 / 100 -----------------------------------


def test_the_canary_stages_are_five_twentyfive_hundred_in_order() -> None:
    assert [int(stage) for stage in CANARY_STAGES] == [5, 25, 100]


def test_the_thresholds_are_the_blueprint_numbers_verbatim() -> None:
    # files/09 §4: acceptance −5 pts, safety blocks +50 %, completion −5 pts, CSAT −0.3.
    assert ACCEPTANCE_DROP_PTS == 5.0
    assert SAFETY_BLOCK_RISE_FRACTION == 0.50
    assert COMPLETION_DROP_PTS == 5.0
    assert CSAT_DROP == 0.3


# --- the healthy path: advance 5 → 25 → 100 ----------------------------------------


def test_a_healthy_stream_promotes_through_every_stage_to_complete() -> None:
    outcome = run_canary(baseline=BASELINE, windows=_windows())
    assert outcome.status is RolloutStatus.COMPLETE
    assert outcome.final_stage is CanaryStage.HUNDRED
    assert outcome.tripped is None
    # every stage was visited, and each earlier one promoted to the next
    assert [d.stage for d in outcome.decisions] == list(CANARY_STAGES)
    assert [d.action for d in outcome.decisions] == [
        CanaryAction.PROMOTE,
        CanaryAction.PROMOTE,
        CanaryAction.COMPLETE,
    ]
    assert outcome.decisions[0].next_stage is CanaryStage.TWENTY_FIVE
    assert outcome.decisions[1].next_stage is CanaryStage.HUNDRED


def test_a_single_window_at_five_percent_promotes_to_twentyfive() -> None:
    decision = evaluate_window(CanaryStage.FIVE, BASELINE, _healthy_like_baseline())
    assert decision.action is CanaryAction.PROMOTE
    assert decision.next_stage is CanaryStage.TWENTY_FIVE
    assert decision.tripped is None


def test_an_improvement_over_baseline_never_rolls_back() -> None:
    better = GuardrailKpis(
        acceptance_rate=95.0,
        safety_block_rate=0.0,
        completion_rate=99.0,
        csat=5.0,
    )
    decision = evaluate_window(CanaryStage.TWENTY_FIVE, BASELINE, better)
    assert decision.action is CanaryAction.PROMOTE


# --- the simulated dip test: one guardrail past its threshold rolls back -----------


@pytest.mark.parametrize(
    ("dip", "guardrail_name"),
    [
        # acceptance −5 pts: 82.0 → 77.0 is exactly the trip
        (
            GuardrailKpis(
                acceptance_rate=77.0, safety_block_rate=0.04, completion_rate=88.0, csat=4.4
            ),
            "acceptance",
        ),
        # safety blocks +50 %: 0.04 → 0.06 is exactly +50 %
        (
            GuardrailKpis(
                acceptance_rate=82.0, safety_block_rate=0.06, completion_rate=88.0, csat=4.4
            ),
            "safety_blocks",
        ),
        # completion −5 pts: 88.0 → 83.0 is exactly the trip
        (
            GuardrailKpis(
                acceptance_rate=82.0, safety_block_rate=0.04, completion_rate=83.0, csat=4.4
            ),
            "completion",
        ),
        # CSAT −0.3: 4.4 → 4.1 is exactly the trip
        (
            GuardrailKpis(
                acceptance_rate=82.0, safety_block_rate=0.04, completion_rate=88.0, csat=4.1
            ),
            "csat",
        ),
    ],
)
def test_a_guardrail_dip_at_the_first_stage_rolls_back(
    dip: GuardrailKpis, guardrail_name: str
) -> None:
    outcome = run_canary(baseline=BASELINE, windows=_windows(FIVE=dip))
    assert outcome.status is RolloutStatus.ROLLED_BACK
    assert outcome.final_stage is CanaryStage.FIVE
    assert outcome.tripped is not None
    assert outcome.tripped.value == guardrail_name
    # a rollback stops the rollout: 25 % and 100 % are never evaluated
    assert [d.stage for d in outcome.decisions] == [CanaryStage.FIVE]


def test_a_dip_at_twentyfive_promotes_five_then_rolls_back() -> None:
    dip = GuardrailKpis(
        acceptance_rate=82.0, safety_block_rate=0.04, completion_rate=80.0, csat=4.4
    )
    outcome = run_canary(baseline=BASELINE, windows=_windows(TWENTY_FIVE=dip))
    assert outcome.status is RolloutStatus.ROLLED_BACK
    assert outcome.final_stage is CanaryStage.TWENTY_FIVE
    assert outcome.tripped is not None
    assert outcome.tripped.value == "completion"
    assert [d.action for d in outcome.decisions] == [
        CanaryAction.PROMOTE,
        CanaryAction.ROLLBACK,
    ]


def test_a_dip_only_at_the_final_stage_still_rolls_back() -> None:
    dip = GuardrailKpis(
        acceptance_rate=82.0, safety_block_rate=0.04, completion_rate=88.0, csat=4.0
    )
    outcome = run_canary(baseline=BASELINE, windows=_windows(HUNDRED=dip))
    assert outcome.status is RolloutStatus.ROLLED_BACK
    assert outcome.final_stage is CanaryStage.HUNDRED
    assert outcome.tripped is not None
    assert outcome.tripped.value == "csat"


# --- the near-miss negative controls: just under the threshold must NOT trip -------
# docs/TDD.md rule 2: the negative matters more than the positive. A threshold one
# point too generous lets a real regression through and nothing goes red.


@pytest.mark.parametrize(
    "near_miss",
    [
        # acceptance drops 4.9 pts (< 5) — under the trip
        GuardrailKpis(acceptance_rate=77.1, safety_block_rate=0.04, completion_rate=88.0, csat=4.4),
        # safety rises to +49 % (< +50 %): 0.04 → 0.0596
        GuardrailKpis(
            acceptance_rate=82.0, safety_block_rate=0.0596, completion_rate=88.0, csat=4.4
        ),
        # completion drops 4.9 pts (< 5)
        GuardrailKpis(acceptance_rate=82.0, safety_block_rate=0.04, completion_rate=83.1, csat=4.4),
        # CSAT drops 0.29 (< 0.3)
        GuardrailKpis(
            acceptance_rate=82.0, safety_block_rate=0.04, completion_rate=88.0, csat=4.11
        ),
    ],
)
def test_a_move_just_under_the_threshold_promotes(near_miss: GuardrailKpis) -> None:
    decision = evaluate_window(CanaryStage.FIVE, BASELINE, near_miss)
    assert decision.action is CanaryAction.PROMOTE
    assert decision.tripped is None


# --- the +50 % rule is relative, and safe from a zero baseline ---------------------


def test_safety_block_guardrail_is_relative_to_the_baseline_rate() -> None:
    # a high but STABLE safety-block rate is not a regression: 0.20 → 0.20
    high_baseline = GuardrailKpis(
        acceptance_rate=82.0, safety_block_rate=0.20, completion_rate=88.0, csat=4.4
    )
    steady = GuardrailKpis(
        acceptance_rate=82.0, safety_block_rate=0.20, completion_rate=88.0, csat=4.4
    )
    assert evaluate_window(CanaryStage.FIVE, high_baseline, steady).action is CanaryAction.PROMOTE
    # the same absolute rise (0.20 → 0.26, +30 %) from that baseline does not trip
    small_rise = GuardrailKpis(
        acceptance_rate=82.0, safety_block_rate=0.26, completion_rate=88.0, csat=4.4
    )
    assert (
        evaluate_window(CanaryStage.FIVE, high_baseline, small_rise).action is CanaryAction.PROMOTE
    )
    # but +50 % (0.20 → 0.30) does
    big_rise = GuardrailKpis(
        acceptance_rate=82.0, safety_block_rate=0.30, completion_rate=88.0, csat=4.4
    )
    tripped = evaluate_window(CanaryStage.FIVE, high_baseline, big_rise)
    assert tripped.action is CanaryAction.ROLLBACK
    assert tripped.tripped is not None
    assert tripped.tripped.value == "safety_blocks"


def test_any_new_safety_blocks_from_a_zero_baseline_roll_back() -> None:
    # +50 % of zero is zero, so a strict ratio can't be formed; the safe reading is
    # that a change that introduces PolicyGuard blocks where there were none is a
    # regression (fail closed).
    zero = GuardrailKpis(
        acceptance_rate=82.0, safety_block_rate=0.0, completion_rate=88.0, csat=4.4
    )
    now_blocking = GuardrailKpis(
        acceptance_rate=82.0, safety_block_rate=0.01, completion_rate=88.0, csat=4.4
    )
    decision = evaluate_window(CanaryStage.FIVE, zero, now_blocking)
    assert decision.action is CanaryAction.ROLLBACK
    assert decision.tripped is not None
    assert decision.tripped.value == "safety_blocks"


def test_a_zero_safety_baseline_that_stays_zero_promotes() -> None:
    zero = GuardrailKpis(
        acceptance_rate=82.0, safety_block_rate=0.0, completion_rate=88.0, csat=4.4
    )
    still_zero = GuardrailKpis(
        acceptance_rate=82.0, safety_block_rate=0.0, completion_rate=88.0, csat=4.4
    )
    assert evaluate_window(CanaryStage.FIVE, zero, still_zero).action is CanaryAction.PROMOTE


# --- invariant 17: a missing input never promotes ----------------------------------


def test_a_stage_with_no_reading_fails_closed_and_rolls_back() -> None:
    windows = {CanaryStage.FIVE: _healthy_like_baseline()}  # 25 % and 100 % absent
    outcome = run_canary(baseline=BASELINE, windows=windows)
    assert outcome.status is RolloutStatus.ROLLED_BACK
    assert outcome.final_stage is CanaryStage.TWENTY_FIVE
    assert outcome.tripped is not None
    assert outcome.tripped.value == "missing_input"


@pytest.mark.parametrize(
    "hole",
    [
        GuardrailKpis(acceptance_rate=None, safety_block_rate=0.04, completion_rate=88.0, csat=4.4),
        GuardrailKpis(acceptance_rate=82.0, safety_block_rate=None, completion_rate=88.0, csat=4.4),
        GuardrailKpis(acceptance_rate=82.0, safety_block_rate=0.04, completion_rate=None, csat=4.4),
        GuardrailKpis(
            acceptance_rate=82.0, safety_block_rate=0.04, completion_rate=88.0, csat=None
        ),
        GuardrailKpis(
            acceptance_rate=float("nan"), safety_block_rate=0.04, completion_rate=88.0, csat=4.4
        ),
    ],
)
def test_an_absent_or_nonfinite_kpi_fails_closed(hole: GuardrailKpis) -> None:
    decision = evaluate_window(CanaryStage.FIVE, BASELINE, hole)
    assert decision.action is CanaryAction.ROLLBACK
    assert decision.tripped is not None
    assert decision.tripped.value == "missing_input"


def test_a_missing_baseline_never_promotes() -> None:
    incomplete_baseline = GuardrailKpis(
        acceptance_rate=None, safety_block_rate=0.04, completion_rate=88.0, csat=4.4
    )
    decision = evaluate_window(CanaryStage.FIVE, incomplete_baseline, _healthy_like_baseline())
    assert decision.action is CanaryAction.ROLLBACK
    assert decision.tripped is not None
    assert decision.tripped.value == "missing_input"


# --- determinism (docs/TDD.md rule 6) ----------------------------------------------


def test_the_controller_is_deterministic() -> None:
    windows = _windows(
        TWENTY_FIVE=GuardrailKpis(
            acceptance_rate=82.0, safety_block_rate=0.04, completion_rate=82.0, csat=4.4
        )
    )
    first = run_canary(baseline=BASELINE, windows=windows)
    second = run_canary(baseline=BASELINE, windows=windows)
    assert first == second


# --- the rollback is a console signal (files/10 §9 learning row) --------------------


def test_a_rollback_increments_the_catalogued_rollbacks_metric() -> None:
    from intake_learning.canary import LEARNING_ROLLBACKS

    labelled = LEARNING_ROLLBACKS.labels(guardrail="csat", stage="5")
    before = labelled._value.get()  # noqa: SLF001
    dip = GuardrailKpis(
        acceptance_rate=82.0, safety_block_rate=0.04, completion_rate=88.0, csat=4.0
    )
    decision = evaluate_window(CanaryStage.FIVE, BASELINE, dip)
    assert decision.action is CanaryAction.ROLLBACK
    after = labelled._value.get()  # noqa: SLF001
    assert after == before + 1


def test_the_rollbacks_metric_is_in_the_catalogue() -> None:
    from pathlib import Path

    from intake_platform.slo import load_metrics_catalog

    repo = Path(__file__).resolve().parents[2]
    catalog = load_metrics_catalog(repo / "observability" / "metrics_catalog.yaml")
    assert catalog.covers("learning_rollbacks_total")

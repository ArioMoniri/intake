"""INT-173 — the canary/rollback controller on the guardrail KPIs.

files/09 §4 "Path to production" ends a proposal's journey with a staged rollout:

    "CODEOWNER clinician approves → canary 5 % → 25 % → 100 % with automatic
     rollback if guardrail KPIs move (acceptance −5 pts, safety blocks +50 %,
     completion −5 pts, CSAT −0.3) → protocol version + hash recorded on every
     session so any effect is attributable."

and files/09 §6 fixes the test that keeps it honest:

    "`canary_rollback`: simulated KPI dip triggers rollback within one
     evaluation window."

This module is that controller, and only that. It **advances** a rollout through
the three stages, and at each stage it **reverts** the moment a guardrail KPI has
regressed past its threshold relative to the pre-canary baseline. It does not
apply anything, choose who is in the cohort, or read a metric back: like
:mod:`intake_learning.publisher` and :mod:`intake_platform.admin.flag_governance`,
it is pure rule — snapshots in, a decision out. The exposure change a decision
implies is the deployment surface's to make, gated by the same least-privilege
identity that opens the PR (files/09 §7); inv. 12 keeps this package unable to
touch red-flag levels, instruments, consent texts, the Talker tool list,
PolicyGuard or profile routing, and ``tests/learning/test_proposal_scope.py``
holds that true of the source, this module included.

**Units come from the blueprint, and are stated so they are not re-guessed.**

- ``acceptance_rate`` and ``completion_rate`` are **percentage points** in
  ``[0, 100]`` — the ``note.acceptance_rate`` and ``session.completion_rate``
  catalogue ratios read as a percent (their 08 §4 targets are written ">= 70 %"
  and ">= 80 %"), so the blueprint's "−5 pts" is a literal 5.0 here.
- ``csat`` is the mean ``csat.score`` on its 1–5 scale, so "CSAT −0.3" is 0.3.
- ``safety_block_rate`` is a **rate**: PolicyGuard blocks per session, i.e.
  ``policyguard.blocks_total`` normalised by the session count of the cohort.
  The raw counter cannot be compared across a 5 % and a 25 % cohort, so the
  guardrail is a *relative* rise on the rate — "+50 %" is a multiplier of 1.5.

**Every comparison is against the baseline, never an invented number.** A window
with no reading, a baseline with a hole, or a non-finite value does not promote:
it fails closed to a rollback (CLAUDE.md invariant 17). A rollback is a console
signal (files/10 §9 learning row: "rollbacks"), counted by
:data:`LEARNING_ROLLBACKS` and by nothing that carries a cohort (invariant 6).

sec_row: `learning-loops`.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, TypeGuard

from prometheus_client import Counter

__all__ = [
    "ACCEPTANCE_DROP_PTS",
    "CANARY_STAGES",
    "COMPLETION_DROP_PTS",
    "CSAT_DROP",
    "LEARNING_ROLLBACKS",
    "SAFETY_BLOCK_RISE_FRACTION",
    "CanaryAction",
    "CanaryDecision",
    "CanaryStage",
    "Guardrail",
    "GuardrailKpis",
    "RolloutOutcome",
    "RolloutStatus",
    "evaluate_window",
    "run_canary",
]

# --- the blueprint's numbers, once (files/09 §4) -----------------------------------

#: acceptance −5 pts: a drop of at least this many percentage points rolls back.
ACCEPTANCE_DROP_PTS: Final = 5.0
#: completion −5 pts.
COMPLETION_DROP_PTS: Final = 5.0
#: CSAT −0.3, on the 1–5 score.
CSAT_DROP: Final = 0.3
#: safety blocks +50 %: a rise to at least 1.5× the baseline per-session rate.
SAFETY_BLOCK_RISE_FRACTION: Final = 0.50

#: Float-comparison slack. The thresholds above are the blueprint's exact numbers,
#: but a KPI rate is a ratio of two counts and 1.5× a rate is not exactly
#: representable in binary — without a tolerance a value mathematically *at* the
#: threshold can miss it by one ULP on some platform and let a real regression
#: through. This is numerical hygiene, not a threshold (invariant 17): at 1e-9 it
#: is orders of magnitude below any KPI's resolution, so it pulls no near-miss
#: across — it only makes the boundary deterministic instead of float-dependent.
_FLOAT_SLACK: Final = 1e-9


class CanaryStage(enum.IntEnum):
    """The exposure fractions files/09 §4 names, in order. The value is the
    percentage of traffic the proposal is live for."""

    FIVE = 5
    TWENTY_FIVE = 25
    HUNDRED = 100


#: The staged rollout, 5 % → 25 % → 100 %. Ordered; the last stage completes.
CANARY_STAGES: Final[tuple[CanaryStage, ...]] = (
    CanaryStage.FIVE,
    CanaryStage.TWENTY_FIVE,
    CanaryStage.HUNDRED,
)


class Guardrail(enum.StrEnum):
    """Which guardrail moved. A closed set — a metric label, never a cohort."""

    ACCEPTANCE = "acceptance"
    SAFETY_BLOCKS = "safety_blocks"
    COMPLETION = "completion"
    CSAT = "csat"
    #: fail-closed: a baseline or a window reading was absent or non-finite, so
    #: no guardrail could be evaluated (CLAUDE.md invariant 17).
    MISSING_INPUT = "missing_input"


class CanaryAction(enum.StrEnum):
    """What the controller decided for one evaluation window."""

    PROMOTE = "promote"
    COMPLETE = "complete"
    ROLLBACK = "rollback"


class RolloutStatus(enum.StrEnum):
    """How a whole staged rollout ended."""

    COMPLETE = "complete"
    ROLLED_BACK = "rolled_back"


LEARNING_ROLLBACKS = Counter(
    "learning_rollbacks_total",
    "Canary rollouts reverted by the INT-173 controller, by the guardrail that "
    "moved and the stage it moved at. files/10 §9's learning row asks for "
    "rollbacks; this is them. Labels carry no pack, clinic or cohort (inv. 6).",
    ["guardrail", "stage"],
)


@dataclass(frozen=True)
class GuardrailKpis:
    """The four guardrail KPIs of files/09 §4, as one snapshot.

    A field is ``None`` when that KPI was not measured for this cohort/window;
    a ``None`` (or a non-finite value) is not a zero and is never treated as
    one — it fails the rollout closed rather than inventing a baseline.
    """

    #: note.acceptance_rate, as a percentage in [0, 100].
    acceptance_rate: float | None
    #: policyguard.blocks_total per session (a non-negative rate).
    safety_block_rate: float | None
    #: session.completion_rate, as a percentage in [0, 100].
    completion_rate: float | None
    #: csat.score mean, on the 1–5 scale.
    csat: float | None


@dataclass(frozen=True)
class CanaryDecision:
    """The decision for a single evaluation window at ``stage``."""

    action: CanaryAction
    stage: CanaryStage
    #: the stage to move to on :attr:`CanaryAction.PROMOTE`; ``None`` otherwise.
    next_stage: CanaryStage | None
    #: the guardrail that moved on :attr:`CanaryAction.ROLLBACK`; ``None`` otherwise.
    tripped: Guardrail | None


@dataclass(frozen=True)
class RolloutOutcome:
    """How a run of :func:`run_canary` ended, with every decision it made."""

    status: RolloutStatus
    final_stage: CanaryStage
    tripped: Guardrail | None
    decisions: tuple[CanaryDecision, ...]


def _finite(value: float | None) -> TypeGuard[float]:
    """True only for a real, present number. ``None`` is absent; ``NaN`` fails
    ``value == value``; ``±inf`` is excluded explicitly. No ``math`` import, so
    the pipeline's allow-list (``test_proposal_scope``) stays short. The
    ``TypeGuard`` lets a caller narrow ``float | None`` to ``float`` without an
    ``assert``."""
    return value is not None and value == value and value not in (float("inf"), float("-inf"))


def _readable(kpis: GuardrailKpis | None) -> tuple[float, float, float, float] | None:
    """The four guardrails as present, finite floats — or ``None`` if any is
    absent or non-finite, which is how a snapshot fails the rollout closed
    (invariant 17). Returning the narrowed tuple keeps the comparisons below
    ``assert``-free and typed."""
    if kpis is None:
        return None
    acceptance, safety, completion, csat = (
        kpis.acceptance_rate,
        kpis.safety_block_rate,
        kpis.completion_rate,
        kpis.csat,
    )
    if _finite(acceptance) and _finite(safety) and _finite(completion) and _finite(csat):
        return (acceptance, safety, completion, csat)
    return None


def _dropped(baseline_value: float, observed_value: float, threshold: float) -> bool:
    """True when ``observed`` fell at least ``threshold`` below ``baseline``,
    tolerant of float rounding at the boundary (see :data:`_FLOAT_SLACK`)."""
    return baseline_value - observed_value >= threshold - _FLOAT_SLACK


def _safety_regressed(baseline_rate: float, observed_rate: float) -> bool:
    """A rise to at least 1.5× the baseline per-session block rate.

    From a zero baseline no ratio can be formed, so the safe reading is that a
    change which introduces PolicyGuard blocks where there were none is a
    regression: any strictly positive observed rate rolls back.
    """
    if observed_rate <= baseline_rate:
        return False
    limit = baseline_rate * (1.0 + SAFETY_BLOCK_RISE_FRACTION)
    return observed_rate >= limit - _FLOAT_SLACK


def _first_breach(baseline: GuardrailKpis, observed: GuardrailKpis | None) -> Guardrail | None:
    """The first guardrail that has regressed, or ``None`` if all are healthy.

    Completeness is checked before any comparison: a guardrail that cannot be
    read is a guardrail that must be assumed to have moved (fail closed).
    """
    base = _readable(baseline)
    obs = _readable(observed)
    if base is None or obs is None:
        return Guardrail.MISSING_INPUT
    base_acceptance, base_safety, base_completion, base_csat = base
    obs_acceptance, obs_safety, obs_completion, obs_csat = obs

    if _dropped(base_acceptance, obs_acceptance, ACCEPTANCE_DROP_PTS):
        return Guardrail.ACCEPTANCE
    if _safety_regressed(base_safety, obs_safety):
        return Guardrail.SAFETY_BLOCKS
    if _dropped(base_completion, obs_completion, COMPLETION_DROP_PTS):
        return Guardrail.COMPLETION
    if _dropped(base_csat, obs_csat, CSAT_DROP):
        return Guardrail.CSAT
    return None


def _next_stage(stage: CanaryStage) -> CanaryStage | None:
    """The stage after ``stage`` in :data:`CANARY_STAGES`, or ``None`` at the last."""
    index = CANARY_STAGES.index(stage)
    if index + 1 < len(CANARY_STAGES):
        return CANARY_STAGES[index + 1]
    return None


def evaluate_window(
    stage: CanaryStage, baseline: GuardrailKpis, observed: GuardrailKpis | None
) -> CanaryDecision:
    """Decide one evaluation window: promote, complete, or roll back.

    A regression past any threshold (or a missing input) rolls back and is
    counted on :data:`LEARNING_ROLLBACKS`. Otherwise the stage promotes to the
    next, or — at the final stage — completes.
    """
    tripped = _first_breach(baseline, observed)
    if tripped is not None:
        LEARNING_ROLLBACKS.labels(guardrail=tripped.value, stage=str(int(stage))).inc()
        return CanaryDecision(
            action=CanaryAction.ROLLBACK, stage=stage, next_stage=None, tripped=tripped
        )
    following = _next_stage(stage)
    if following is None:
        return CanaryDecision(
            action=CanaryAction.COMPLETE, stage=stage, next_stage=None, tripped=None
        )
    return CanaryDecision(
        action=CanaryAction.PROMOTE, stage=stage, next_stage=following, tripped=None
    )


def run_canary(
    *, baseline: GuardrailKpis, windows: Mapping[CanaryStage, GuardrailKpis]
) -> RolloutOutcome:
    """Advance a rollout through 5 % → 25 % → 100 %, evaluating each stage.

    ``windows`` supplies the observed KPIs at each stage. A stage with no
    reading fails closed (invariant 17). The run stops at the first rollback or
    when the final stage completes, so a reverted rollout never reaches a wider
    cohort. Pure and deterministic: no wall-clock, no network (docs/TDD.md
    rule 6) — the same inputs always yield the same outcome.
    """
    decisions: list[CanaryDecision] = []
    for stage in CANARY_STAGES:
        decision = evaluate_window(stage, baseline, windows.get(stage))
        decisions.append(decision)
        if decision.action is CanaryAction.ROLLBACK:
            return RolloutOutcome(
                status=RolloutStatus.ROLLED_BACK,
                final_stage=stage,
                tripped=decision.tripped,
                decisions=tuple(decisions),
            )
        if decision.action is CanaryAction.COMPLETE:
            return RolloutOutcome(
                status=RolloutStatus.COMPLETE,
                final_stage=stage,
                tripped=None,
                decisions=tuple(decisions),
            )
    # Unreachable: the final stage always completes or rolls back. Named so the
    # type is total rather than implicitly falling off the end.
    raise AssertionError("CANARY_STAGES ended without a terminal decision")

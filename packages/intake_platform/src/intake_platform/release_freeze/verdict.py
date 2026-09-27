"""May this deployment ship now? The one rule the console and the deploy path read.

INT-187's acceptance is "deploy-freeze on budget exhaustion", and files/08 §3
puts a manual "freeze deploys" beside it. Both stop the same deploy, so they
are one verdict, computed here from two inputs and nothing else:

- **the freeze record** (:mod:`.store`) — engaged refuses; a record nobody can
  read refuses too, because a deploy path that cannot see a freeze does not get
  to assume there is none;
- **the error budget** — any declared SLO whose remaining budget is at or below
  zero refuses (the SLO files and their SLIs are the INT-181 ones, evaluated by
  ``services/api``); a budget source the tier declares but that cannot answer
  refuses. A tier that declares **no** budget source (no Prometheus configured)
  is *noted*, not refused: there is no budget to exhaust there, and saying so
  on every run is what keeps that from passing as a measurement. An SLO with no
  series yet is likewise noted as unmeasured — never counted as within budget.

``services/api``'s console renders :class:`ReleaseVerdict` as the deploy-gate
tile and ``intake_api.admin.release_gate`` exits on it, so the two cannot
disagree about a deploy.
"""

from __future__ import annotations

from dataclasses import dataclass

from intake_platform.release_freeze.model import DeployFreeze

__all__ = ["ErrorBudget", "ReleaseVerdict", "release_verdict"]


@dataclass(frozen=True)
class ErrorBudget:
    """What the SLO files' budgets say, or why they say nothing."""

    #: The tier declares a budget source (a Prometheus the API is told to read).
    configured: bool
    #: The declared source could not answer — a machine code.
    failure: str | None = None
    #: ``<service>/<slo>`` whose remaining budget is at or below zero.
    exhausted: tuple[str, ...] = ()
    #: ``<service>/<slo>`` with no series yet: nothing measured, nothing claimed.
    unmeasured: tuple[str, ...] = ()

    @classmethod
    def not_configured(cls) -> ErrorBudget:
        return cls(configured=False)

    @classmethod
    def failed(cls, code: str) -> ErrorBudget:
        return cls(configured=True, failure=code)

    @classmethod
    def measured(cls, *, exhausted: tuple[str, ...], unmeasured: tuple[str, ...]) -> ErrorBudget:
        return cls(configured=True, exhausted=exhausted, unmeasured=unmeasured)


@dataclass(frozen=True)
class ReleaseVerdict:
    allowed: bool
    #: Why a deploy is refused, every reason, in a fixed order — machine codes.
    refusals: tuple[str, ...]
    #: What the verdict could not weigh, stated rather than assumed.
    notes: tuple[str, ...]


def release_verdict(
    *, freeze: DeployFreeze | None, freeze_failure: str | None, budget: ErrorBudget
) -> ReleaseVerdict:
    """The verdict. ``freeze`` is ``None`` exactly when it could not be read,
    and then ``freeze_failure`` names why."""
    refusals: list[str] = []
    notes: list[str] = []
    if freeze is None:
        if not freeze_failure:
            raise ValueError("an unread freeze needs the code that says why")
        refusals.append(freeze_failure)
    elif freeze.engaged:
        refusals.append("deploy_freeze_engaged")
    if not budget.configured:
        notes.append("error_budget_not_configured")
    elif budget.failure is not None:
        refusals.append("error_budget_unreadable")
    else:
        if budget.exhausted:
            refusals.append("error_budget_exhausted")
        if budget.unmeasured:
            notes.append("error_budget_unmeasured")
    return ReleaseVerdict(allowed=not refusals, refusals=tuple(refusals), notes=tuple(notes))

"""INT-038 — the withdrawal-cascade schedule contract (files/06 §2: cascade
≤ 1 min; the acceptance's "withdrawal cascades within 1 min").

The synchronous pass in service.withdraw_consent already revokes dependents
and live shares at the withdrawal instant — the normal path is immediate.
This module bounds the ABNORMAL path: a crash between the revocation mark
and its cascade leaves a partial state that service.sweep_withdrawals
repairs, and the schedule here proves the repair lands inside the minute:

    worst case = one full interval (the withdrawal lands just after a tick)
               + one pass budget (the sweep transaction itself)
    30 s      + 25 s = 55 s  ≤  60 s

The numbers are engineering margins, not clinical values: the interval is
how often the worker wakes, the pass budget is the transaction ceiling the
deployment must alarm on (a pass that exceeds it breaches the contract and
pages — files/06 §8b treats consent machinery as a monitored control).
Tests drive this with a fake clock — no sleeps, no wall time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

__all__ = [
    "SWEEP_INTERVAL",
    "SWEEP_PASS_BUDGET",
    "WITHDRAWAL_CASCADE_BUDGET",
    "SweepSchedule",
]

WITHDRAWAL_CASCADE_BUDGET = timedelta(minutes=1)
SWEEP_INTERVAL = timedelta(seconds=30)
SWEEP_PASS_BUDGET = timedelta(seconds=25)


@dataclass(frozen=True)
class SweepSchedule:
    """Fixed-grid schedule: ticks at ``epoch + n * interval``. A grid (not
    "interval after last finish") so a slow pass cannot silently stretch
    the detection bound."""

    interval: timedelta = SWEEP_INTERVAL
    pass_budget: timedelta = SWEEP_PASS_BUDGET

    def __post_init__(self) -> None:
        if self.interval <= timedelta(0) or self.pass_budget <= timedelta(0):
            raise ValueError("sweep interval and pass budget must be positive")
        if self.interval + self.pass_budget > WITHDRAWAL_CASCADE_BUDGET:
            raise ValueError(
                "interval + pass budget exceed the 1-minute withdrawal-cascade "
                "budget (files/06 §2; INT-038 acceptance)"
            )

    def next_run_after(self, instant: datetime, *, epoch: datetime) -> datetime:
        """The first grid tick STRICTLY after ``instant`` — a withdrawal
        landing exactly on a tick is picked up by the next one, which is
        the honest worst case."""
        if instant < epoch:
            return epoch
        elapsed = instant - epoch
        ticks = elapsed // self.interval
        candidate = epoch + (ticks + 1) * self.interval
        return candidate

    def worst_case_completion(self, withdrawal_at: datetime, *, epoch: datetime) -> datetime:
        return self.next_run_after(withdrawal_at, epoch=epoch) + self.pass_budget

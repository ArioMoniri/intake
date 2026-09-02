"""What `make runtime-sim` prints, and the one thing it must never imply.

The harness measures the **Talker's own turn** on a virtual clock: from the
moment ``take_turn`` is entered to the moment it returns. files/02 §8.1's
budget measures something strictly larger — *"last patient speech sample →
first agent audio sample, on device, client clock"* — which additionally
contains end-of-utterance detection, the STT flush, the uplink and downlink,
the jitter buffer and device output, none of which this process can see.

So every rendered line says **server-side**, and the budget column is printed
beside the measurement rather than compared to it. A harness that subtracted
one from the other and printed "headroom" would be publishing a round-trip
figure it never measured, which is precisely the shape invariant 20 forbids.

Where no budget is published the row says so and names the sentence that
refuses; it never prints a substitute.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from clinical_schemas.common import FrozenModel
from pydantic import Field

from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.simulator.budgets import (
    BudgetNotPublished,
    NetworkProfile,
    TurnClass,
    published_budget,
)

__all__ = ["ScenarioReport", "TurnRecord", "render_report"]


class TurnRecord(FrozenModel):
    """One turn of one scenario run, as the virtual clock charged it."""

    index: int = Field(ge=0)
    elapsed_ms: float = Field(ge=0.0)
    spoke: bool = Field(description="False for a held turn — see TurnHold.")


class ScenarioReport(FrozenModel):
    """One scenario, on one profile, over one named network profile."""

    scenario_id: str = Field(min_length=1)
    profile: VoiceProfile
    turn_class: TurnClass
    network: NetworkProfile
    turns: tuple[TurnRecord, ...] = Field(default=())

    @property
    def max_elapsed_ms(self) -> float:
        return max((turn.elapsed_ms for turn in self.turns), default=0.0)

    @property
    def spoken_turns(self) -> int:
        return sum(1 for turn in self.turns if turn.spoke)


def _budget_column(report: ScenarioReport) -> str:
    try:
        budget = published_budget(report.profile, report.turn_class, network=report.network)
    except BudgetNotPublished as refusal:
        return f"no published budget ({refusal})"
    parts = [
        f"p50 {budget.p50_ms:g} ms" if budget.p50_ms is not None else "p50 OPEN",
        f"p95 {budget.p95_ms:g} ms" if budget.p95_ms is not None else "p95 OPEN",
    ]
    if budget.open_reason:
        parts.append(budget.open_reason)
    return " · ".join(parts)


def render_report(reports: Iterable[ScenarioReport]) -> str:
    """A plain-text table. One block per (scenario, profile, network)."""
    lines: list[str] = [
        "runtime-sim · per-turn budgets per profile",
        "measurement: server-side Talker turn on a virtual clock "
        "(NOT the files/02 §8.1 round trip, which this process cannot see)",
        "",
    ]
    ordered: Sequence[ScenarioReport] = list(reports)
    for report in ordered:
        lines.append(
            f"{report.scenario_id}  profile={report.profile.value}  "
            f"turn_class={report.turn_class.value}  network={report.network.value}"
        )
        lines.append(f"  published budget : {_budget_column(report)}")
        lines.append(
            f"  measured         : {len(report.turns)} turns, "
            f"{report.spoken_turns} spoken, "
            f"max server-side {report.max_elapsed_ms:.1f} ms"
        )
        for turn in report.turns:
            state = "spoke" if turn.spoke else "held"
            lines.append(f"    turn {turn.index}: {turn.elapsed_ms:.1f} ms ({state})")
        lines.append("")
    return "\n".join(lines)

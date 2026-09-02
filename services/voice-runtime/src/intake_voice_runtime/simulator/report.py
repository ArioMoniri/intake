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

__all__ = ["ParityTrace", "ScenarioReport", "TurnRecord", "render_report"]


class TurnRecord(FrozenModel):
    """One turn of one scenario run, as the virtual clock charged it.

    Two groups of fields, and the split is the whole of INT-096's parity
    check. ``elapsed_ms`` is a **measurement of a transport** and legitimately
    differs between profiles — a screen write charges no playback. Everything
    else is what the turn *did*: which step, which Turkish, which Work, which
    results delivered, whether it held and why. That group may not differ, and
    :class:`ParityTrace` is exactly this record with the first group removed.
    """

    index: int = Field(ge=0)
    elapsed_ms: float = Field(ge=0.0)
    spoke: bool = Field(description="False for a held turn — see TurnHold.")
    step_id: str | None = Field(default=None, description="The step this turn asked, if any.")
    text_tr: str = Field(
        default="",
        description="The agent's own authored Turkish, never patient speech — safe "
        "to carry here for the same reason a clip manifest is (invariant 6).",
    )
    from_clip: bool = Field(
        default=False,
        description="Whether the clip cache served it. Transport-specific: always "
        "False on 'typed', which has no clips.",
    )
    work_id: str | None = Field(default=None, description="Derived id, if a Work was submitted.")
    drained_results: int = Field(default=0, ge=0)
    delivered_work_ids: tuple[str, ...] = Field(default=())
    held: str | None = Field(default=None, description="TurnHold value, if the turn held.")


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


class ParityTrace(FrozenModel):
    """One scenario run with every transport-specific quantity removed.

    files/03 §4.6 invariant 8 asks that *"the same simulator scenarios pass"*
    on both profiles, and the word doing the work is **same**. Two runs cannot
    be compared field for field: a typed turn charges no playback, fetches no
    clip and synthesises nothing, so an equality over
    :class:`ScenarioReport` would be false for the right reasons and would
    have to be weakened into uselessness.

    So the comparison is over what the turn *did* — the step, the Turkish, the
    Work, the deliveries, the hold — and :meth:`divergence` names every field
    that differs rather than returning a bare ``False``. A parity failure that
    says only "not equal" is a parity failure nobody can act on.
    """

    scenario_id: str = Field(min_length=1)
    steps: tuple[str | None, ...] = Field(default=())
    texts: tuple[str, ...] = Field(default=())
    work_ids: tuple[str | None, ...] = Field(default=())
    drained: tuple[int, ...] = Field(default=())
    delivered: tuple[tuple[str, ...], ...] = Field(default=())
    holds: tuple[str | None, ...] = Field(default=())

    @classmethod
    def of(cls, report: ScenarioReport) -> ParityTrace:
        return cls(
            scenario_id=report.scenario_id,
            steps=tuple(turn.step_id for turn in report.turns),
            texts=tuple(turn.text_tr for turn in report.turns),
            work_ids=tuple(turn.work_id for turn in report.turns),
            drained=tuple(turn.drained_results for turn in report.turns),
            delivered=tuple(turn.delivered_work_ids for turn in report.turns),
            holds=tuple(turn.held for turn in report.turns),
        )

    def divergence(self, other: ParityTrace) -> tuple[str, ...]:
        """Every field on which two runs of the same scenario disagree."""
        if self.scenario_id != other.scenario_id:
            return (f"scenario_id: {self.scenario_id} vs {other.scenario_id}",)
        return tuple(
            f"{name}: {getattr(self, name)!r} vs {getattr(other, name)!r}"
            for name in ("steps", "texts", "work_ids", "drained", "delivered", "holds")
            if getattr(self, name) != getattr(other, name)
        )


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

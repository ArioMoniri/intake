"""Per-turn budgets per voice profile, and what a harness may claim (INT-094).

files/02 §8.1 is the source of record, and the honest reading of it is short:
**the blueprint publishes exactly one per-turn figure for the one voice
profile** — ``residency_tr`` p50 ≤ 1300 ms — and deliberately leaves the p95
*"OPEN — to be measured"*. Everything else in that section is either the
arithmetic of a transport configuration we are leaving (kept *"only for the
arithmetic they contain, relabelled — not as live profiles"*) or stated per
**network** profile rather than per **voice** profile.

So this table has one number in it and seven stated absences. That is the
point of the module rather than a gap in it: CLAUDE.md forbids inventing a
value to unblock ourselves, and a latency target is exactly the kind of
plausible number that reads as authoritative to every later reader. A row with
no number therefore has to say *why* — and, where a human owes us a
measurement, name the HUMAN_BLOCKERS id that owes it.

**What a report built on this table may and may not say.** files/02 §8.1 fixes
the measurement point once: *"last patient speech sample → first agent audio
sample, on device, client clock."* A harness with no microphone, no model and
no media transport does not measure that, and no amount of care with the
arithmetic turns virtual orchestration milliseconds into it. So
:class:`TurnBudgetReport` reports the two side by side and
:meth:`TurnBudgetReport.verdict` **raises**: there is no pass/fail to compute,
and a method that quietly returned one would manufacture a performance claim
out of a harness artefact (CLAUDE.md invariant 20).
"""

from __future__ import annotations

import enum
from typing import NoReturn

from clinical_schemas.common import FrozenModel
from pydantic import Field, model_validator

from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.steps import StepKind

__all__ = [
    "TURN_BUDGETS",
    "Bound",
    "NotALatencyMeasurement",
    "TurnBudget",
    "TurnBudgetReport",
    "TurnKind",
    "TurnObservation",
    "VIRTUAL_MS_PLACES",
    "UnsetReason",
    "budget_for",
]


class TurnKind(enum.StrEnum):
    """files/02 §8.1 prices a *scripted* turn and a *dynamic* turn apart."""

    SCRIPTED = "scripted"
    DYNAMIC = "dynamic"

    @classmethod
    def of(cls, kind: StepKind) -> TurnKind:
        """Which turn a step is, derived from the one field that decides it.

        A step the protocol permits to be reworded is the step an LLM and a
        live synthesiser stand behind; every other kind is spoken verbatim
        from ``text_tr`` and is clip-cache eligible (CLAUDE.md invariant 10).
        The division is therefore ``allow_paraphrase`` and nothing else, so it
        cannot disagree with the router's own refusal.
        """
        return cls.DYNAMIC if kind.allow_paraphrase else cls.SCRIPTED


class Bound(enum.StrEnum):
    """The two percentiles files/02 §8.1 publishes per row."""

    P50 = "p50"
    P95 = "p95"


class UnsetReason(enum.StrEnum):
    """Why a cell carries no number. Never "we did not get to it"."""

    #: files/02 §8.1 states the cell is open and a human owes the measurement.
    AWAITING_MEASUREMENT = "awaiting_measurement"
    #: The figure exists but is published per *network* profile, which the
    #: runtime does not know; picking one would be choosing a number.
    STATED_PER_NETWORK_PROFILE = "stated_per_network_profile"
    #: §8.1's measurement point does not exist in this profile at all.
    NO_MEASUREMENT_POINT = "no_measurement_point"


class TurnBudget(FrozenModel):
    """One cell of the per-profile budget table, with its source."""

    profile: VoiceProfile
    turn_kind: TurnKind
    bound: Bound
    limit_ms: float | None = Field(
        default=None, gt=0.0, description="The published figure, or None when unset."
    )
    unset: UnsetReason | None = Field(
        default=None, description="Why there is no figure. Required when limit_ms is None."
    )
    blueprint_quote: str = Field(
        min_length=1,
        description="Verbatim substring of files/02 §8.1 carrying this cell. "
        "Re-read at test time, so a transcription cannot drift from its source.",
    )
    blocker: str | None = Field(
        default=None,
        description="HUMAN_BLOCKERS id that owes the measurement. Required for "
        "AWAITING_MEASUREMENT and forbidden everywhere else.",
    )

    @model_validator(mode="after")
    def _a_cell_is_a_number_or_a_reason(self) -> TurnBudget:
        if (self.limit_ms is None) == (self.unset is None):
            raise ValueError(
                "a budget cell carries either a number or a reason it has none, "
                "never both and never neither (CLAUDE.md: never invent a value "
                "to unblock yourself)"
            )
        awaiting = self.unset is UnsetReason.AWAITING_MEASUREMENT
        if awaiting and not self.blocker:
            raise ValueError(
                "a cell awaiting a measurement must name the blocker that owes "
                "it, so the ask is attached to a named human rather than left "
                "as a hole (HUMAN_BLOCKERS Rule 1)"
            )
        if self.blocker and not awaiting:
            raise ValueError("only a cell awaiting a measurement carries a blocker id")
        return self


#: files/02 §8.1's "Other profiles" table, the one row that names a voice profile.
_RESIDENCY_P50_QUOTE = "**`residency_tr`** *(the only voice profile)* | **≤ 1300 ms**"
_RESIDENCY_P95_QUOTE = "**OPEN — to be measured** | Deliberately unset."

#: The scripted-turn figures are indexed by network profile — home or wifi,
#: 5G-class, mid LTE, weak LTE — not by voice profile. The runtime does not
#: know the client's RTT class, and §8.1's own fix (a) says the target is
#: "derived from the client's own measured RTT class", which is a client-side
#: input this harness does not have.
_SCRIPTED_QUOTE = "**Scripted turn (~70 % of fast-mode turns), p50 / p95 / p99:** home or wifi"

#: The measurement point itself, which is what rules the typed lane out.
_MEASUREMENT_POINT_QUOTE = (
    "**Measurement point, stated once and applying to every row: last patient "
    "speech sample → first agent audio sample, on device, client clock.**"
)

#: The measurement HB-C10 owes: files/HUMAN_BLOCKERS.md names it as the row the
#: ASR pin, the TTS pin "and the `§4.5` latency budget all rest on".
_LATENCY_BLOCKER = "HB-C10"


def _typed_cells() -> tuple[TurnBudget, ...]:
    return tuple(
        TurnBudget(
            profile=VoiceProfile.TYPED,
            turn_kind=turn_kind,
            bound=bound,
            unset=UnsetReason.NO_MEASUREMENT_POINT,
            blueprint_quote=_MEASUREMENT_POINT_QUOTE,
        )
        for turn_kind in TurnKind
        for bound in Bound
    )


TURN_BUDGETS: tuple[TurnBudget, ...] = (
    TurnBudget(
        profile=VoiceProfile.RESIDENCY_TR,
        turn_kind=TurnKind.DYNAMIC,
        bound=Bound.P50,
        limit_ms=1300.0,
        blueprint_quote=_RESIDENCY_P50_QUOTE,
    ),
    TurnBudget(
        profile=VoiceProfile.RESIDENCY_TR,
        turn_kind=TurnKind.DYNAMIC,
        bound=Bound.P95,
        unset=UnsetReason.AWAITING_MEASUREMENT,
        blocker=_LATENCY_BLOCKER,
        blueprint_quote=_RESIDENCY_P95_QUOTE,
    ),
    TurnBudget(
        profile=VoiceProfile.RESIDENCY_TR,
        turn_kind=TurnKind.SCRIPTED,
        bound=Bound.P50,
        unset=UnsetReason.STATED_PER_NETWORK_PROFILE,
        blueprint_quote=_SCRIPTED_QUOTE,
    ),
    TurnBudget(
        profile=VoiceProfile.RESIDENCY_TR,
        turn_kind=TurnKind.SCRIPTED,
        bound=Bound.P95,
        unset=UnsetReason.STATED_PER_NETWORK_PROFILE,
        blueprint_quote=_SCRIPTED_QUOTE,
    ),
    *_typed_cells(),
)


def budget_for(profile: VoiceProfile, turn_kind: TurnKind, bound: Bound) -> TurnBudget:
    """The one cell for this profile, turn kind and percentile."""
    for budget in TURN_BUDGETS:
        if (budget.profile, budget.turn_kind, budget.bound) == (profile, turn_kind, bound):
            return budget
    raise LookupError(  # pragma: no cover - the table is exhaustive by construction
        f"no budget cell for {profile.value}/{turn_kind.value}/{bound.value}"
    )


#: Decimal places every virtual figure is rounded to before it is reported or
#: compared. Six is far below any quantity this harness works with and far
#: above the ~1e-14 drift binary floating-point accumulation introduces.
VIRTUAL_MS_PLACES = 6


class NotALatencyMeasurement(RuntimeError):
    """Something asked an orchestration report for a latency verdict."""


class TurnObservation(FrozenModel):
    """One turn, as the harness saw it on a virtual clock.

    ``charged_ms`` is everything the turn cost on the session clock;
    ``modelled_playback_ms`` is the part the harness itself put there by
    modelling agent playback at a declared rate. The difference is the only
    figure that says anything about the runtime — every await the Talker
    performs that is not playback lands in it, which is why a stalled backend
    or a stalled lane must leave it at zero.
    """

    index: int = Field(ge=0)
    step_id: str = Field(min_length=1)
    turn_kind: TurnKind
    charged_ms: float = Field(ge=0.0)
    modelled_playback_ms: float = Field(ge=0.0)

    @property
    def orchestration_ms(self) -> float:
        """Virtual milliseconds the runtime's own awaits cost this turn.

        Rounded at :data:`VIRTUAL_MS_PLACES`: the virtual clock accumulates in
        binary floating point, so a turn whose sleeps sum to exactly 24 ms can
        read back as 23.999999999999986. Rounding a virtual quantity is not a
        measurement decision — there is no instrument here whose precision
        could be overstated by it.
        """
        return round(self.charged_ms - self.modelled_playback_ms, VIRTUAL_MS_PLACES)

    @model_validator(mode="after")
    def _playback_cannot_exceed_the_turn(self) -> TurnObservation:
        if self.modelled_playback_ms - self.charged_ms > 10.0**-VIRTUAL_MS_PLACES:
            raise ValueError(
                "modelled playback exceeds the turn it happened in; the meter "
                "is wired wrong and a negative orchestration figure would hide it"
            )
        return self


class TurnBudgetReport(FrozenModel):
    """Per-turn observations for one profile, beside the budgets that exist."""

    profile: VoiceProfile
    scenario_id: str = Field(min_length=1)
    clock: str = Field(
        default="virtual",
        description="Always virtual. A wall-clock latency assertion in CI is a "
        "flake, and this repository has already paid for one.",
    )
    measures: tuple[str, ...] = Field(min_length=1)
    does_not_measure: tuple[str, ...] = Field(min_length=1)
    turns: tuple[TurnObservation, ...] = Field(default=())

    def budget_for_turn(self, turn: TurnObservation, bound: Bound) -> TurnBudget:
        """The published budget cell this turn would be judged against — if the
        harness measured the thing the cell is about, which it does not."""
        return budget_for(self.profile, turn.turn_kind, bound)

    def verdict(self) -> NoReturn:
        """Always raises. There is no budget verdict to compute here.

        files/02 §8.1 measures *"last patient speech sample → first agent audio
        sample, on device, client clock"*. This report measures virtual
        orchestration in a container with no microphone, no model and no media
        transport. Comparing them would publish a performance figure that no
        corpus and no date stand behind (CLAUDE.md invariant 20).
        """
        raise NotALatencyMeasurement(
            f"{self.scenario_id} on {self.profile.value} reports orchestration on a "
            f"{self.clock} clock; files/02 §8.1's measurement point is a device "
            "clock from last patient speech sample to first agent audio sample, "
            "and this harness measures none of: " + ", ".join(self.does_not_measure)
        )

    def render(self) -> str:
        """The report, as a text table for docs/evidence."""
        header = (
            f"profile={self.profile.value} scenario={self.scenario_id} clock={self.clock}\n"
            f"measures: {'; '.join(self.measures)}\n"
            f"does NOT measure: {'; '.join(self.does_not_measure)}\n"
            "turn | step_id | kind | charged_ms | modelled_playback_ms | "
            "orchestration_ms | p50 budget | p95 budget"
        )
        rows = [
            " | ".join(
                (
                    str(turn.index),
                    turn.step_id,
                    turn.turn_kind.value,
                    f"{turn.charged_ms:.1f}",
                    f"{turn.modelled_playback_ms:.1f}",
                    f"{turn.orchestration_ms:.1f}",
                    _render_budget(self.budget_for_turn(turn, Bound.P50)),
                    _render_budget(self.budget_for_turn(turn, Bound.P95)),
                )
            )
            for turn in self.turns
        ]
        return "\n".join([header, *rows])


def _render_budget(budget: TurnBudget) -> str:
    if budget.limit_ms is not None:
        return f"<= {budget.limit_ms:.0f} ms"
    unset = budget.unset.value if budget.unset else "unset"
    return f"unset ({unset}{f'; {budget.blocker}' if budget.blocker else ''})"

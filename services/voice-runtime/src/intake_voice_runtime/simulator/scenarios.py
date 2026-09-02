"""RT-01 … RT-08 as data, including the one that cannot be run.

files/04 §6 writes the eight runtime scenarios in prose. This module is the
same eight as typed rows, so that ``make runtime-sim`` can name one, the suite
can assert against one, and — the part that matters — a scenario naming a
profile that no longer exists **refuses** instead of quietly running against a
substitute.

RT-06 is that scenario. It is written for the speech-to-speech cloud profile
with a second pass in the cascaded cloud profile — ``s2s_cloud`` and
``cascade_fast`` — and CLAUDE.md invariant 19 says both were deleted: *"a
reference to either is a defect."* The backlog agrees from the other side:
INT-098 is ``withdrawn``, *"Replaced by a test that proves no S2S/cloud profile
can be constructed."*

So RT-06 keeps its row and carries :attr:`RuntimeScenario.withdrawn` instead of
a profile list, and :meth:`RuntimeScenario.require_runnable` raises. The two
names appear in this docstring and nowhere in the code below, because
``tests/voice/test_voice_runtime_service.py`` enforces exactly that split —
the record may say what was displaced, the runtime may not name it.

Deleting the row would lose the fact that a numbered blueprint scenario has no
runtime at all; substituting ``residency_tr`` would be worse, because RT-06 is
*about* a profile with no text before audio, and ``residency_tr`` has text
before audio, so the substitute would pass by testing a different thing.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from clinical_schemas.common import FrozenModel
from pydantic import Field, model_validator

from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.simulator.budgets import TurnClass

__all__ = ["SCENARIOS", "RuntimeScenario", "ScenarioNotRunnable", "runnable_scenarios"]


class ScenarioNotRunnable(LookupError):
    """The scenario names something the shipped runtime does not have."""


class RuntimeScenario(FrozenModel):
    """One row of files/04 §6, with the profiles it can be run on."""

    id: str = Field(pattern=r"^RT-\d{2}$")
    title: str = Field(min_length=1)
    blueprint: str = Field(min_length=1, description="The sentence, near enough to find it.")
    turn_class: TurnClass
    profiles: tuple[VoiceProfile, ...] = Field(
        default=(),
        description="The profiles this scenario runs on. Empty only when withdrawn.",
    )
    withdrawn: str | None = Field(
        default=None,
        description="Why the scenario has no runtime. A scenario is either runnable "
        "on at least one profile or withdrawn with a reason; there is no third state, "
        "and in particular no state in which it quietly runs on a substitute.",
    )

    @model_validator(mode="after")
    def _runnable_or_withdrawn_never_neither(self) -> RuntimeScenario:
        if bool(self.profiles) == bool(self.withdrawn):
            raise ValueError(
                f"{self.id}: a scenario names the profiles it runs on, or it says why "
                "it has none. Both would let a withdrawn scenario run on a substitute; "
                "neither would let it vanish."
            )
        return self

    @property
    def runnable(self) -> bool:
        return bool(self.profiles)

    def require_runnable(self) -> tuple[VoiceProfile, ...]:
        """The profiles to run on, or a refusal carrying the reason."""
        if self.profiles:
            return self.profiles
        raise ScenarioNotRunnable(f"{self.id} is withdrawn: {self.withdrawn}")


_BOTH: Final[tuple[VoiceProfile, ...]] = (VoiceProfile.RESIDENCY_TR, VoiceProfile.TYPED)

SCENARIOS: Final[Mapping[str, RuntimeScenario]] = {
    scenario.id: scenario
    for scenario in (
        RuntimeScenario(
            id="RT-01",
            title="Two documents parse while the patient keeps talking",
            blueprint="patient keeps talking for 40 s while two documents parse in the background",
            turn_class=TurnClass.SCRIPTED,
            profiles=_BOTH,
        ),
        RuntimeScenario(
            id="RT-02",
            title="RED fires mid-sentence",
            blueprint="RED rule fires while the agent is mid-sentence",
            turn_class=TurnClass.SCRIPTED,
            profiles=_BOTH,
        ),
        RuntimeScenario(
            id="RT-03",
            title="Backend Agent stalled ten seconds",
            blueprint="Backend Agent stalled 10 s",
            turn_class=TurnClass.SCRIPTED,
            profiles=_BOTH,
        ),
        RuntimeScenario(
            id="RT-04",
            title="Clarification for step n after step n+1 was asked",
            blueprint="extraction returns clarification_needed for step n",
            turn_class=TurnClass.SCRIPTED,
            profiles=_BOTH,
        ),
        RuntimeScenario(
            id="RT-05",
            title="Five answers in three seconds",
            blueprint="five answers submitted in 3 s (fast talker)",
            turn_class=TurnClass.SCRIPTED,
            profiles=_BOTH,
        ),
        RuntimeScenario(
            id="RT-06",
            title="Output-transcript monitor catches a diagnostic sentence",
            blueprint="the speech-to-speech profile attempts a diagnostic sentence",
            turn_class=TurnClass.DYNAMIC,
            withdrawn=(
                "the two cloud voice profiles it is written for were deleted by the "
                "all-self-hosted constraint (CLAUDE.md invariant 19; files/00 §0b; "
                "files/02 §8.1 profile-stack correction), and INT-098 - the backlog "
                "issue that would have built one - is withdrawn, 'Replaced by a test "
                "that proves no S2S/cloud profile can be constructed'. There is no "
                "runtime with an output-transcript monitor because there is no runtime "
                "without text before audio."
            ),
        ),
        RuntimeScenario(
            id="RT-07",
            title="YELLOW waits for the insertion window",
            blueprint="YELLOW rule fires - spoken only at the insertion window",
            turn_class=TurnClass.SCRIPTED,
            profiles=_BOTH,
        ),
        RuntimeScenario(
            id="RT-08",
            title="The patient steps away mid-turn",
            blueprint="backchannel suppressed, turn detector holds",
            turn_class=TurnClass.SCRIPTED,
            profiles=_BOTH,
        ),
    )
}


def runnable_scenarios() -> tuple[RuntimeScenario, ...]:
    """Every scenario the shipped profile set can actually carry."""
    return tuple(scenario for scenario in SCENARIOS.values() if scenario.runnable)

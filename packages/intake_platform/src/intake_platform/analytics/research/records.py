"""INT-490 — one person in one protocol version in one week, in memory only.

A :class:`SubjectRecord` is the unit the release is counted over. It exists
for the length of one request: the sources build it, the release counts it,
and it is dropped. It has no serialiser and is never logged, cached or written
(LD-06: what the panel holds is the aggregate; the record is the processing
that produces it).

**A person counts once per protocol version per week.** When the same person
ran the same version twice in one week, their latest session speaks for them
(``subject`` is the pseudonymous patient key, held only in this process). A
person who ran two versions appears in both families with the same
``subject``, which is what lets the cross-view check see that the two families
share them.

**Structural rules are checked at construction.** A triage bucket only on an
intake that finished (a finished intake may have none: the level is recorded
nowhere this release may read, see :mod:`.sources`); question records only on
an intake that started; an
answer mode, time and recognition band exactly where the outcome makes them
meaningful. A record that breaks one is refused rather than counted, because a
cell that cannot exist would otherwise be a cell the gate never meant to show.
"""

from __future__ import annotations

from collections.abc import Hashable, Mapping
from dataclasses import dataclass, field

from intake_platform.analytics.research.catalogue import (
    AnswerTimeBand,
    AsrBand,
    InputMode,
    Platform,
    QuestionOutcome,
    RepeatBand,
    Stage,
    TriageBucket,
)

__all__ = ["QuestionRecord", "SubjectRecord"]

_FINISHED = frozenset({Stage.FINISHED, Stage.SHARED})


@dataclass(frozen=True)
class QuestionRecord:
    """How one question went for one person."""

    outcome: QuestionOutcome
    repeat: RepeatBand
    input_mode: InputMode | None = None
    time_band: AnswerTimeBand | None = None
    asr_band: AsrBand | None = None

    def __post_init__(self) -> None:
        answered = self.outcome is QuestionOutcome.ANSWERED
        if answered != (self.input_mode is not None) or answered != (self.time_band is not None):
            raise ValueError("an answer mode and time exist exactly when the question was answered")
        by_voice = self.input_mode is InputMode.VOICE
        if by_voice != (self.asr_band is not None):
            raise ValueError("a recognition band exists exactly when the answer was spoken")


@dataclass(frozen=True)
class SubjectRecord:
    """One person, one protocol version, one week. Never leaves the process."""

    subject: Hashable = field(repr=False)
    tenant: Hashable = field(repr=False)
    protocol: str
    protocol_version: str
    stage: Stage
    locale: str
    triage: TriageBucket | None = None
    platform: Platform | None = None
    questions: Mapping[str, QuestionRecord] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.triage is not None and self.stage not in _FINISHED:
            raise ValueError("a triage bucket exists only on an intake that finished")
        if self.questions and self.stage is Stage.INVITED:
            raise ValueError("a question was reached only by an intake that started")

    @property
    def family(self) -> tuple[str, str]:
        return (self.protocol, self.protocol_version)

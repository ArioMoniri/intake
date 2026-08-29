"""What ``protocol_next`` hands the Talker (files/03 §4.2 return shape).

``{step_id, kind: scripted|paraphrase_ok|confirm|choice|follow_up, text_tr,
clip_id?, choices[]}`` — the row of the six-tool table, plus the
``engine_version`` files/12 §7.2 makes ``submit_utterance`` carry back.

``allow_paraphrase`` is derived from ``kind`` rather than stored beside it:
CLAUDE.md invariant 10 permits paraphrase *only* where the protocol says so,
and a second field that could disagree with the first is exactly how that
permission would drift.
"""

from __future__ import annotations

import enum

from clinical_schemas.common import FrozenModel
from pydantic import Field

__all__ = ["NextStep", "Step", "StepKind"]


class StepKind(enum.StrEnum):
    """The five step kinds files/03 §4.2 names."""

    SCRIPTED = "scripted"
    PARAPHRASE_OK = "paraphrase_ok"
    CONFIRM = "confirm"
    CHOICE = "choice"
    FOLLOW_UP = "follow_up"

    @property
    def allow_paraphrase(self) -> bool:
        """Only ``paraphrase_ok`` may be reworded (invariant 10)."""
        return self is StepKind.PARAPHRASE_OK


class Step(FrozenModel):
    """One deterministic step from the IntakeEngine."""

    step_id: str = Field(min_length=1, description="Stable step id within the session.")
    kind: StepKind = Field(description="Delivery kind (files/03 §4.2).")
    text_tr: str = Field(
        min_length=1,
        description="The authored Turkish, already tr-expanded by the compiler "
        "(CLAUDE.md invariant 22). Spoken verbatim unless kind allows paraphrase.",
    )
    choices_tr: tuple[str, ...] = Field(
        default=(), description="Choice labels for kind=choice (files/03 §4.2)."
    )


class NextStep(Step):
    """A :class:`Step` stamped with the snapshot version it was read from.

    files/12 §7.2: ``protocol_next`` is a lock-free atomic attribute read and
    ``submit_utterance`` carries ``engine_version`` back, so Layer B can tell
    a legitimate ask-ahead answer from one bound to an invalidated step.
    """

    engine_version: int = Field(ge=0, description="EngineSnapshot version this was read at.")
    allow_paraphrase: bool = Field(description="Derived from kind; never authored separately.")

    @classmethod
    def of(cls, step: Step, engine_version: int) -> NextStep:
        return cls(
            step_id=step.step_id,
            kind=step.kind,
            text_tr=step.text_tr,
            choices_tr=step.choices_tr,
            engine_version=engine_version,
            allow_paraphrase=step.kind.allow_paraphrase,
        )

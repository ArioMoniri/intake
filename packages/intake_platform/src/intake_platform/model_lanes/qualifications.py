"""Which exact model versions may serve a gated lane (INT-428; medical review,
finding 12, binding).

A lane or model swap on a lane whose output feeds red-flag extraction is gated
on two recorded eval runs **for that exact model version** — the red-flag
extraction goldens and the Turkish negation set — both green. The record lives
in ``infra/model-lanes/qualifications.yaml``; a row names the lane, the
provider (or ``self_hosted``), the model id, its version, and for a
self-hosted model the weights-manifest sha256, so a re-quantised or re-pulled
model is a different model with no qualification.

The file ships with **no rows**: the golden set a swap requires and the
extraction-sensitivity floor it must clear are a physician's decision (medical
review, physician decision 8), and the runs are live model calls that only
``make eval-live`` may make. Until a row exists, every gated swap is refused
with ``model_not_qualified`` — at the console when the switch is requested and
approved, and on every call for a real-PHI deployment.

Ungated lanes are named, not implied: ``tts`` speaks scripted, verbatim text
(invariant 10) and extracts nothing, so it is held by the invariant-22 numeral
refusal and the clip round-trip gate rather than by extraction goldens.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from intake_platform.model_lanes.model import Lane
from intake_platform.model_lanes.models import ModelRef

__all__ = [
    "QUALIFICATIONS_DEFAULT",
    "EvalRun",
    "EvalStatus",
    "Qualification",
    "QualificationRegistry",
]

QUALIFICATIONS_DEFAULT: Final = "infra/model-lanes/qualifications.yaml"
_RUN_ID: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{2,127}$")


class EvalStatus(enum.StrEnum):
    GREEN = "green"
    RED = "red"


class EvalRun(BaseModel):
    """One recorded run: its status, its id and its date. Ids only."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: EvalStatus
    run_id: str
    run_on: date

    @field_validator("run_id")
    @classmethod
    def _id_shaped(cls, value: str) -> str:
        if _RUN_ID.match(value) is None:
            raise ValueError("a run id is an id, never prose")
        return value


class Qualification(BaseModel):
    """One model version's qualification for one lane."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    lane: Lane
    provider: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    sha256: str | None = None
    rf_extraction_goldens: EvalRun
    negation_set: EvalRun

    @property
    def green(self) -> bool:
        return (
            self.rf_extraction_goldens.status is EvalStatus.GREEN
            and self.negation_set.status is EvalStatus.GREEN
        )

    def matches(self, lane: Lane, ref: ModelRef) -> bool:
        return (
            self.lane is lane
            and self.provider == ref.provider
            and self.model_id == ref.model_id
            and self.version == ref.version
            and self.sha256 == ref.sha256
        )

    @property
    def run_ids(self) -> str:
        return f"{self.rf_extraction_goldens.run_id}+{self.negation_set.run_id}"


class _QualificationsFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1]
    gated_lanes: tuple[Lane, ...]
    qualifications: list[Qualification] = Field(default_factory=list)


@dataclass(frozen=True)
class QualificationRegistry:
    gated_lanes: frozenset[Lane]
    rows: tuple[Qualification, ...]

    @classmethod
    def load(cls, path: Path) -> QualificationRegistry:
        """Load and validate; a malformed file raises rather than reading as
        "nothing qualified", which would look like a policy and be an accident."""
        parsed = _QualificationsFile.model_validate(
            yaml.safe_load(path.read_text(encoding="utf-8"))
        )
        return cls(gated_lanes=frozenset(parsed.gated_lanes), rows=tuple(parsed.qualifications))

    @classmethod
    def gating(cls, *lanes: Lane) -> QualificationRegistry:
        """A registry that gates ``lanes`` and qualifies nothing."""
        return cls(gated_lanes=frozenset(lanes), rows=())

    def gated(self, lane: Lane) -> bool:
        return lane in self.gated_lanes

    def qualification(self, lane: Lane, ref: ModelRef | None) -> Qualification | None:
        """The green row for this exact model version, or ``None``."""
        if ref is None:
            return None
        for row in self.rows:
            if row.matches(lane, ref) and row.green:
                return row
        return None

    def qualified(self, lane: Lane, ref: ModelRef | None) -> bool:
        """An ungated lane is always qualified; a gated one needs a green row."""
        return not self.gated(lane) or self.qualification(lane, ref) is not None

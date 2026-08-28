"""Triage result schemas (INT-031).

Invariant 1 is carried in the types, not in a comment: RED/YELLOW exist only
on ``RulesTriageResult`` (source ``rules``), and ``LlmCandidateTriage`` can
express exactly one level — the ``YELLOW_REVIEW`` ceiling. files/12 §2.3:
``YELLOW_REVIEW`` is clinician-only and *not* a patient-routing level, which
is why it is not a member of ``TriageLevel`` at all.
"""

from __future__ import annotations

import enum
import warnings
from typing import Annotated, Literal

from pydantic import Field, model_validator

from clinical_schemas.common import FrozenModel


class TriageLevel(enum.StrEnum):
    """Patient-routing levels, rules-engine only (files/04 §5 ``triage.level``:
    RED|YELLOW|GREEN; files/03 §4.3 result shape)."""

    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


class RedRegister(enum.StrEnum):
    """How a RED is told (files/02 §5.3 register axis; CLAUDE.md invariant 21)."""

    ALERT = "ALERT"
    CALM = "CALM"
    SILENT = "SILENT"
    DEFERRED_CLINICIAN = "DEFERRED_CLINICIAN"


class RedLocation(enum.StrEnum):
    """What a RED tells the patient to do (files/02 §5.3 Axis 3: REMOTE |
    ON_SITE | UNKNOWN; a geofence misfire yields UNKNOWN, files/02 §3)."""

    REMOTE = "REMOTE"
    ON_SITE = "ON_SITE"
    UNKNOWN = "UNKNOWN"


class RuleFire(FrozenModel):
    """One fired rules-engine rule (files/04 §5 ``triage.rules[{id,evidence}]``)."""

    id: str = Field(
        description="Rule id from packages/protocols/triage (files/04 §5; invariant 1)."
    )
    evidence: str = Field(
        description="Which slot values satisfied the rule (files/04 §5 triage.rules.evidence)."
    )


class CandidateFlag(FrozenModel):
    """One LLM candidate flag (files/04 §5 ``triage.llm_candidates[{text,evidence}]``;
    files/03 §4.6: extraction may emit candidate_flags[], at most YELLOW_REVIEW)."""

    text: str = Field(
        description="Candidate concern as clinician-facing text (files/04 §5 llm_candidates.text)."
    )
    evidence: str = Field(
        description="Transcript/document evidence for the candidate (files/04 §5)."
    )


# The blueprint names the RED axis field `register` (CLAUDE.md invariant 21;
# files/02 §5.3); pydantic warns because ABCMeta exposes a classmethod of the
# same name. The blueprint name wins — suppress exactly that warning.
warnings.filterwarnings(
    "ignore",
    message='Field name "register" in "RulesTriageResult" shadows an attribute in parent',
    category=UserWarning,
)


class RulesTriageResult(FrozenModel):
    """A triage determination produced by ``packages/protocols/triage`` rules —
    the only producer of RED/YELLOW (invariant 1)."""

    source: Literal["rules"] = Field(
        default="rules",
        description="Provenance discriminator: this level came from the rules engine "
        "(invariant 1).",
    )
    level: TriageLevel = Field(
        description="Patient-routing level GREEN|YELLOW|RED (files/04 §5 triage.level)."
    )
    rules: tuple[RuleFire, ...] = Field(
        default=(),
        description="Rules that fired, with evidence (files/04 §5 triage.rules); "
        "non-GREEN levels must name at least one (invariant 1).",
    )
    register: RedRegister | None = Field(
        default=None,
        description="RED register axis — required on RED with no permitted default "
        "(CLAUDE.md invariant 21; files/02 §5.3); absent on GREEN/YELLOW.",
    )
    location: RedLocation | None = Field(
        default=None,
        description="RED location axis — required on RED with no permitted default "
        "(CLAUDE.md invariant 21; files/02 §5.3 Axis 3); absent on GREEN/YELLOW.",
    )

    @model_validator(mode="after")
    def _red_axes_and_rule_evidence(self) -> RulesTriageResult:
        if self.level is not TriageLevel.GREEN and not self.rules:
            raise ValueError(f"a {self.level.value} result must name the rules that fired")
        if self.level is TriageLevel.RED:
            if self.register is None or self.location is None:
                raise ValueError("RED requires register and location — no default (invariant 21)")
        elif self.register is not None or self.location is not None:
            raise ValueError("register/location are RED axes only (files/02 §5.3)")
        return self


class LlmCandidateTriage(FrozenModel):
    """LLM candidate output. The type can express exactly one level:
    ``YELLOW_REVIEW`` — the ceiling of files/03 §4.6 and invariant 1, kept out
    of ``TriageLevel`` per files/12 §2.3 (clinician-only, never routing)."""

    source: Literal["llm_candidate"] = Field(
        default="llm_candidate",
        description="Provenance discriminator: an LLM produced this (invariant 1).",
    )
    level: Literal["YELLOW_REVIEW"] = Field(
        default="YELLOW_REVIEW",
        description="Type-level maximum for LLM candidates (files/03 §4.6; files/12 §2.3).",
    )
    candidate_flags: tuple[CandidateFlag, ...] = Field(
        min_length=1,
        description="The candidate concerns with evidence (files/03 §4.6 candidate_flags[]).",
    )


type TriageResult = Annotated[RulesTriageResult | LlmCandidateTriage, Field(discriminator="source")]
"""Discriminated on ``source`` (``rules`` | ``llm_candidate``) so provenance is
part of the value, never an out-of-band convention (INT-031 scope item 1)."""

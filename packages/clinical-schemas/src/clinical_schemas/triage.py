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

from clinical_schemas.common import FrozenModel, JsonValue


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


class EvidenceSlot(FrozenModel):
    """One slot a fired rule read, and what it carried (INT-404).

    These are the parts of ``triage.rules[].evidence``. A number stays a
    number here: the clinical carrier's ``Decimal`` (files/13 §9.5), tagged on
    the wire like every other ``JsonValue``. It becomes text only on the
    surface that knows its reader (:mod:`clinical_schemas.rule_evidence`),
    because the decimal point is the reader's (CLAUDE.md invariant 22)."""

    slot: str = Field(
        min_length=1,
        description="The dotted slot reference exactly as the rule's when predicate "
        "spells it (files/03 §6 atoms).",
    )
    values: tuple[JsonValue, ...] = Field(
        min_length=1,
        description="The value(s) the slot carried: one, or head + superseded when "
        "contested (files/12 §7.3). A number is a number, never text (files/13 §9.5).",
    )
    unit: str | None = Field(
        default=None,
        min_length=1,
        description="The slot's declared unit (files/03 §6 ``unit:``), written beside "
        "each number as one non-breaking atom (invariant 22). Absent when the slot "
        "declares none.",
    )


class RuleFire(FrozenModel):
    """One fired rules-engine rule (files/04 §5 ``triage.rules[{id,evidence}]``)."""

    id: str = Field(
        description="Rule id from packages/protocols/triage (files/04 §5; invariant 1)."
    )
    evidence: str = Field(
        description="Which slot values satisfied the rule (files/04 §5 "
        "triage.rules.evidence), as the rules engine recorded it: slot=value pairs "
        "with JSON's decimal point, written for no reader in particular. A line a "
        "person reads is written from ``evidence_slots`` for that reader "
        "(clinical_schemas.rule_evidence; INT-404). A fire that arrived as text "
        "alone, such as a FHIR import, is carried as written."
    )
    evidence_slots: tuple[EvidenceSlot, ...] = Field(
        default=(),
        description="The same reading in parts (slot, carried values, declared "
        "unit), from which each reader's evidence line is written with that "
        "reader's decimal point (CLAUDE.md invariant 22; INT-404). Empty for a "
        "fire that arrived as text alone.",
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
    red_rule_id: str | None = Field(
        default=None,
        description="RED only: the fired rule whose register and action script this "
        "RED delivers, as the rules engine chose it (INT-453). ``rules`` is ordered by "
        "severity then id, which is not the engine's winner order, so a consumer reads "
        "this and never a position. The engine sets it on every RED; absent elsewhere.",
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
        if self.red_rule_id is not None:
            if self.level is not TriageLevel.RED:
                raise ValueError("red_rule_id is a RED axis only (INT-453)")
            if self.red_rule_id not in {fire.id for fire in self.rules}:
                raise ValueError("red_rule_id must name a rule that fired (INT-453)")
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

"""The generic RED escalation copy and its serve precondition (INT-453).

When a RED's own pre-positioned script cannot be addressed, the voice
runtime still triggers a RED on the device: the generic escalation, under the
script ids below. Its words come from one document, ``kind: generic_red``,
whose copy is a clinical decision (CD-24 in the INT-432 register, agent
author plus independent verifier, D18). Until CD-24 lands, the copy is
``draft_needs_source``.

A blank generic must never reach a live tenant. :func:`generic_red_refusals`
is the precondition. Nothing serves RED scripts, and ``device_functions`` is
not enabled, while it refuses — that is, while the copy is absent or
``draft_needs_source``. A missing document refuses. Nothing defaults to
servable (HUMAN_BLOCKERS rule 2: build the mechanism, wire the gate, make it
fail closed, leave the content empty).

The document also carries the register the generic is told in, because that
is part of the same clinical decision. ``DEFAULT_GENERIC_RED_REGISTER`` (ALERT)
applies only until a servable document says otherwise.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Literal

import yaml
from clinical_schemas.common import FrozenModel
from clinical_schemas.triage import RedLocation, RedRegister
from pydantic import Field, ValidationError, model_validator

from protocols.dsl import RedFlagAction, SourceBlock
from protocols.types import RuleStatus

__all__ = [
    "DEFAULT_GENERIC_RED_REGISTER",
    "GENERIC_RED_DECISION",
    "GENERIC_RED_SCRIPT_IDS",
    "GenericRedCopy",
    "GenericRedError",
    "generic_red_refusals",
    "generic_red_register",
    "load_generic_red",
]

#: The clinical-decisions register row that owns the copy and the register.
GENERIC_RED_DECISION = "CD-24"

#: The ids the trigger names and the device catalog keys on, one per location.
#: The device mirrors them (apps/mobile/src/lib/livekit/red.ts).
GENERIC_RED_SCRIPT_IDS: Mapping[RedLocation, str] = {
    RedLocation.REMOTE: "base.generic_red.remote",
    RedLocation.ON_SITE: "base.generic_red.on_site",
    RedLocation.UNKNOWN: "base.generic_red.unknown",
}

#: The register until CD-24 says otherwise: the most conservative.
DEFAULT_GENERIC_RED_REGISTER = RedRegister.ALERT


class GenericRedError(ValueError):
    """The generic RED document could not be read or is malformed."""


class GenericRedCopy(FrozenModel):
    """The ``kind: generic_red`` document."""

    kind: Literal["generic_red"] = Field(description="Document kind.")
    decision: Literal["CD-24"] = Field(
        description="The INT-432 clinical-decisions register row that owns this copy."
    )
    status: RuleStatus = Field(description="``active`` only with a source and the copy.")
    register: RedRegister = Field(description="How the generic is told (CD-24).")
    source: SourceBlock | None = Field(default=None, description="Required when active.")
    source_gap: str | None = Field(default=None, description="Required when draft.")
    action: RedFlagAction | None = Field(
        default=None,
        description="REMOTE and ON_SITE scripts and the UNKNOWN question, verbatim tr; "
        "ON_SITE never offers 112 (the DSL refuses it).",
    )

    @model_validator(mode="after")
    def _status_carries_what_it_claims(self) -> GenericRedCopy:
        if self.status is RuleStatus.ACTIVE:
            if self.source is None or self.action is None:
                raise ValueError("an active generic RED carries its source and its copy")
        elif not self.source_gap:
            raise ValueError("a draft generic RED says what it is waiting for (source_gap)")
        return self


def load_generic_red(path: Path) -> GenericRedCopy:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return GenericRedCopy.model_validate(raw)
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise GenericRedError(f"{path.name}: generic RED document unusable") from exc


def generic_red_refusals(copy: GenericRedCopy | None) -> tuple[str, ...]:
    """Why the generic RED is not servable; empty means servable."""
    if copy is None:
        return ("generic_red_absent",)
    if copy.status is not RuleStatus.ACTIVE:
        return ("generic_red_draft_needs_source",)
    return ()


def generic_red_register(copy: GenericRedCopy | None) -> RedRegister:
    """CD-24's register once a servable document carries it; ALERT until then."""
    if copy is None or generic_red_refusals(copy):
        return DEFAULT_GENERIC_RED_REGISTER
    return copy.register

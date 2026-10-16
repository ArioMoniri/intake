"""The generic RED escalation copy and its serve precondition (INT-453; CD-24).

When a RED's own pre-positioned script cannot be addressed, the voice
runtime still triggers a RED on the device: the generic escalation, under the
script ids below. Its words come from one document, ``kind: generic_red``, and
are decided by CD-24 in the INT-432 clinical-decisions register (agent author
plus independent verifier, D18: simulated-patient testing only, with a licensed
physician's review required before any real patient). CD-24 is the source of
truth (``packages/protocols/decisions/CD-24.yaml`` on #757).

**Register.** CD-24 decides ``carry_engine_register``: the generic trigger
carries the register of the engine result that produced it and is never
fixed at ALERT. An always-ALERT generic is a default register chosen once by
an engineer, which CLAUDE.md invariant 21 forbids. The policy is a literal in
the document, so it cannot drift from the code that implements it. The copy
for a SILENT generic, and the register when fired rules declare different
registers, stay ``draft_needs_source`` in CD-24. Meanwhile there is a delivery
floor: intake stops, and the clinic is told when a generic is delivered
silently.

**Serve precondition.** A blank generic must never reach a live tenant.
:func:`generic_red_refusals` is the precondition. Nothing serves RED scripts,
and ``device_functions`` is not enabled, while it refuses — that is, while the
document is absent or ``draft_needs_source``. Nothing defaults to servable
(HUMAN_BLOCKERS rule 2).
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Literal

import yaml
from clinical_schemas.common import FrozenModel
from clinical_schemas.triage import RedLocation
from pydantic import Field, ValidationError, model_validator

from protocols.dsl import RedFlagAction, SourceBlock
from protocols.types import RuleStatus

__all__ = [
    "GENERIC_RED_DECISION",
    "GENERIC_RED_SCRIPT_IDS",
    "GenericRedCopy",
    "GenericRedError",
    "generic_red_refusals",
    "load_generic_red",
]

#: The clinical-decisions register row that owns the copy and the register policy.
GENERIC_RED_DECISION = "CD-24"

#: The ids the trigger names and the device catalog keys on, one per location.
#: The device mirrors them (apps/mobile/src/lib/livekit/red.ts).
GENERIC_RED_SCRIPT_IDS: Mapping[RedLocation, str] = {
    RedLocation.REMOTE: "base.generic_red.remote",
    RedLocation.ON_SITE: "base.generic_red.on_site",
    RedLocation.UNKNOWN: "base.generic_red.unknown",
}


class GenericRedError(ValueError):
    """The generic RED document could not be read or is malformed."""


class GenericRedCopy(FrozenModel):
    """The ``kind: generic_red`` document."""

    kind: Literal["generic_red"] = Field(description="Document kind.")
    decision: Literal["CD-24"] = Field(
        description="The INT-432 clinical-decisions register row that owns this copy."
    )
    status: RuleStatus = Field(description="``active`` only with a source and the copy.")
    register_policy: Literal["carry_engine_register"] = Field(
        description="CD-24: the generic carries the engine result's own register, "
        "never a fixed one (CLAUDE.md invariant 21)."
    )
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

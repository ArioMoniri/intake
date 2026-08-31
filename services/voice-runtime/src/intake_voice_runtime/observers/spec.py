"""One lane's manifest — invariant 29 (``lane_intended_purpose_manifest``).

files/03 §4.6 invariant 29: *"every lane ships a reviewed ``intended_purpose``
string in its manifest; CI fails without one. The strings are the ones that go
into the technical file, so they are reviewed as regulatory text, not as
comments."*

The framework's contribution is to make its absence unrepresentable:
``intended_purpose`` is required with ``min_length=1``, so a lane without one
does not construct and therefore never reaches registration. The *content* of
the string belongs to the lane (INT-111 ff.) and to the module it sits in —
:data:`~intake_voice_runtime.observers.module_boundary.MODULE_INTENDED_PURPOSE`
carries the four module-level statements verbatim from files/03 §4.7.1.
"""

from __future__ import annotations

from clinical_schemas.common import FrozenModel
from clinical_schemas.observers import Lane
from pydantic import Field

from intake_voice_runtime.observers.budget import LaneBudget
from intake_voice_runtime.observers.module_boundary import LANE_MODULE, LaneModule

__all__ = ["LaneSpec"]


class LaneSpec(FrozenModel):
    """What a lane declares about itself before it is allowed to read anything."""

    lane: Lane = Field(description="Which of the five lanes this is (invariant 11).")
    intended_purpose: str = Field(
        min_length=1,
        description="The reviewed regulatory string for the technical file "
        "(invariant 29). Required: a lane without one does not construct.",
    )
    budget: LaneBudget = Field(description="Window, depth and deadline (files/03 §4.7.6).")

    @property
    def module(self) -> LaneModule:
        """The MDCG module boundary this lane sits inside (files/03 §4.7.1)."""
        return LANE_MODULE[self.lane]

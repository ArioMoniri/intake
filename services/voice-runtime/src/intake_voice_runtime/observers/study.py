"""The `acoustic` module's study gate — invariant 23, files/03 §4.7.4.

CLAUDE.md invariant 11, second sentence: *"``acoustic`` is unreachable unless
{study_id, protocol_version, ICF_version, approval_date} all assert, and fails
closed on protocol amendment."*

Both halves are types here rather than checks:

- **all four assert.** :class:`StudyAssertion` has four required fields and no
  defaults, so an incomplete assertion does not construct. There is no partial
  value to pass around and no branch that could decide three out of four is
  close enough.
- **fails closed on amendment.** :class:`StudyGate` compares the approved
  ``protocol_version`` with the one actually running. TCKAY m.11 makes an
  amendment a *fresh submission*, so a complete, signed, still-valid assertion
  for version 1.0 authorises nothing at all once version 1.1 is live. The gate
  does not warn, downgrade or shadow-run: files/03 §4.7.4 is explicit that
  *"outside the investigation the module is genuinely unreachable, not merely
  unrendered … there is no shadow mode for ``acoustic``"*.

What is deliberately absent: any way to construct a gate that admits. The
values come from the registered investigation and no agent may supply one —
the study registry (INT-230) holds ``studies: []`` today and every export
refuses, which is the same fail-closed posture one layer down.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import date

from clinical_schemas.common import FrozenModel, Ref
from pydantic import Field

__all__ = ["StudyAssertion", "StudyGate", "StudyGateState"]


class StudyGateState(enum.StrEnum):
    """Why the acoustic module is or is not reachable. Three answers, no default."""

    ADMITTED = "admitted"
    #: No registered investigation asserted anything — the commercial default.
    NO_ASSERTION = "no_assertion"
    #: The protocol running is not the protocol approved (TCKAY m.11).
    AMENDED = "amended"


class StudyAssertion(FrozenModel):
    """The four fields, all required. An incomplete assertion has no value."""

    study_id: Ref = Field(description="The registered investigation's id.")
    protocol_version: str = Field(
        min_length=1, description="The approved protocol version, exactly as approved."
    )
    icf_version: str = Field(
        min_length=1,
        description="The informed-consent form version the participant signed "
        "(files/06 §2.4 — an ICF, not a consent row).",
    )
    approval_date: date = Field(description="Date of the ethics/TİTCK approval on record.")


@dataclass(frozen=True)
class StudyGate:
    """Reachability for the M3 module. Closed unless every condition holds."""

    assertion: StudyAssertion | None
    live_protocol_version: str

    @property
    def state(self) -> StudyGateState:
        if self.assertion is None:
            return StudyGateState.NO_ASSERTION
        if self.assertion.protocol_version != self.live_protocol_version:
            return StudyGateState.AMENDED
        return StudyGateState.ADMITTED

    @property
    def admits(self) -> bool:
        return self.state is StudyGateState.ADMITTED

"""The files/02 §2b re-show of a RED when its visit moves (INT-407).

files/02 §2b: a ``rescheduled`` or ``cancelled`` transition on a RED visit
*"re-shows the crisis signposting to the patient in the register the original
RED used (§5.3)"*.

A :class:`RedResurface` is a **pointer, never words** — the RED's ``work_id``,
the rule it addressed, the register it was told in and a location — for the
reason invariant 21 gives the data-channel trigger: every RED script is
pre-positioned on the device before any session starts, so the server sends
nothing the device could render except what it already holds verbatim. That is
also how no field here can reintroduce the 112 affordance under ``ON_SITE``:
there is no field to put it in.

Three rules, each a refusal to guess:

- **The register is the RED's own** — the one its inbox entry recorded
  (``InboxEntry.register``). An entry that recorded none is re-shown to the
  clinic (the transition entry is raised regardless) and **not** to the
  patient: choosing a register for it is the default files/02 §5.3 forbids.
- **``DEFERRED_CLINICIAN`` is not re-shown** — *"Patient screen unchanged.
  Finding routes to the clinician only."* Its clinic entry is still raised.
- **The location is re-derived, not copied.** The original RED's location
  described where the patient stood then; the re-show describes now, from the
  visit's new state (:func:`~intake_platform.visit_lifecycle.derive_location`).
  The rule addressed is the first of the entry's rule ids, as on the
  data-channel trigger (``RedPreemption`` addresses ``rule_ids[0]``).

Invariant 1 is untouched: nothing here produces a level. It re-points at a
RED the rules engine already produced.
"""

from __future__ import annotations

import re
import warnings
from collections.abc import Iterable
from typing import Final

from clinical_schemas.triage import RedLocation, RedRegister
from pydantic import BaseModel, ConfigDict, field_validator

from intake_platform.safety_inbox import EntryKind, InboxEntry

__all__ = ["PATIENT_FACING_REGISTERS", "RedResurface", "red_resurface"]

#: files/02 §5.3 Axis 2: every register but DEFERRED_CLINICIAN changes the
#: patient's screen.
PATIENT_FACING_REGISTERS: Final = frozenset(
    {RedRegister.ALERT, RedRegister.CALM, RedRegister.SILENT}
)

_ID: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
#: ``ID_SHAPE`` of the RED trigger, which every rules-engine rule id satisfies.
_RULE: Final = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")

# The blueprint names the RED axis field `register` (invariant 21); pydantic
# warns because ABCMeta exposes a classmethod of the same name.
warnings.filterwarnings(
    "ignore",
    message='Field name "register" in "RedResurface" shadows an attribute in parent',
    category=UserWarning,
)


class RedResurface(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    work_id: str
    rule_id: str
    register: RedRegister
    location: RedLocation

    @field_validator("work_id")
    @classmethod
    def _id_shaped(cls, value: str) -> str:
        if not _ID.fullmatch(value):
            raise ValueError("a work id is id-shaped; the value is not echoed")
        return value

    @field_validator("rule_id")
    @classmethod
    def _rule_shaped(cls, value: str) -> str:
        if not _RULE.fullmatch(value):
            raise ValueError("a rule id is id-shaped; the value is not echoed")
        return value


def red_resurface(reds: Iterable[InboxEntry], *, location: RedLocation) -> tuple[RedResurface, ...]:
    """One pointer per patient-facing RED whose register was recorded."""
    return tuple(
        RedResurface(
            work_id=entry.source_ref,
            rule_id=entry.rule_ids[0],
            register=entry.register,
            location=location,
        )
        for entry in reds
        if entry.kind is EntryKind.RED
        and entry.register is not None
        and entry.register in PATIENT_FACING_REGISTERS
    )

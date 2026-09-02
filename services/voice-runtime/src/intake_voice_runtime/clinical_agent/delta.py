"""Delta mode, driven by ``PatientOverlay`` (INT-081).

files/09 §3 lists what Loop 1 changes deterministically: *"confirm-don't-
reask; **delta mode** for follow-ups … full HPI only on change; … pre-fill
with ``confirm`` steps; activate patient overlays …"*. Delta mode and
overlay-pack activation are **siblings** in that list, both driven by the
same object; delta mode is not downstream of activation, which is why this
module reads the :class:`~clinical_schemas.overlay.PatientOverlay` directly
rather than waiting on an overlay pack to exist.

The mechanism, and nothing beyond it:

- a confirmed fact whose key names a step in this session's plan **pre-fills
  that step's slot as unconfirmed**, and the step is offered as a
  ``confirm`` step spoken from the slot's own ``confirm_tr`` instead of a
  full ask — files/03 §5 verbatim: *"Prior-record facts pre-fill slots as
  unconfirmed → ``confirm`` steps instead of re-asking."*
- **delta mode never removes a step.** It changes a step's *kind*, never the
  frontier's membership, which is how files/04 §2.3's *"they never remove
  questions clinicians marked ``must_ask``"* holds without a special case
  for ``must_ask``.
- a fact past its twelve-month re-confirmation window is **withheld**
  (files/09 §3), through the same
  :func:`~clinical_schemas.overlay.fact_needs_reconfirmation` predicate
  INT-258's overlay activation uses, so the two cannot drift apart on what
  "in date" means.
- a fact for a slot the author gave no ``confirm_tr`` **does not pre-fill**.
  There is no improvised confirmation (CLAUDE.md invariant 10), and the
  fail-closed direction here is to ask the question in full.

The *content* that will one day switch a patient into delta mode by default
— ``overlay.frequent_attender`` (files/04 §2.3) — is INT-056 and is not
here. This module honours whatever facts arrive; it authors none.
"""

from __future__ import annotations

import enum
from datetime import datetime

from clinical_schemas.common import FrozenModel, JsonValue
from clinical_schemas.overlay import PatientOverlay, fact_needs_reconfirmation
from pydantic import Field

from intake_voice_runtime.clinical_agent.plan import IntakePlan

__all__ = ["DeltaDecision", "DeltaMode", "DeltaPrefill", "decide_delta"]


class DeltaMode(enum.StrEnum):
    """Whether this session runs in delta mode (files/09 §3)."""

    OFF = "off"
    ON = "on"


class DeltaPrefill(FrozenModel):
    """One slot pre-filled from a confirmed fact — unconfirmed until asked."""

    slot_ref: str = Field(min_length=1, description="The step/slot the fact fills.")
    value: JsonValue = Field(description="The prior value, carried unconfirmed (files/03 §5).")
    confirm_tr: str = Field(
        min_length=1,
        description="The slot's own verbatim confirm text. Carried on the prefill "
        "rather than looked up later because a prefill is only representable when "
        "the author wrote one — there is no improvised confirmation (invariant 10).",
    )
    fact_key: str = Field(min_length=1, description="PatientOverlay fact key (files/09 §3).")
    source_ref: str = Field(
        min_length=1,
        description="The confirming artefact — the 'where from' every learned fact "
        "must show (files/09 §3 guardrails).",
    )


class DeltaDecision(FrozenModel):
    """What the patient's overlay did, and did not, do to this session."""

    mode: DeltaMode = Field(description="ON iff at least one slot pre-filled.")
    prefills: tuple[DeltaPrefill, ...] = Field(
        default=(), description="Pre-filled slots, sorted by slot reference."
    )
    withheld_fact_keys: tuple[str, ...] = Field(
        default=(),
        description="Facts a step could have used but which are past the twelve-month "
        "re-confirmation window (files/09 §3).",
    )
    unconfirmable_fact_keys: tuple[str, ...] = Field(
        default=(),
        description="Facts a step could have used but whose slot carries no "
        "confirm_tr — asked in full instead (CLAUDE.md invariant 10).",
    )


def decide_delta(
    *, plan: IntakePlan, overlay_facts: PatientOverlay | None, now: datetime
) -> DeltaDecision:
    """Decide delta mode for one session from the patient's confirmed facts.

    ``now`` is the session's ``reference_time`` (files/13 §9.2), never a wall
    clock, so the same overlay replays to the same decision.
    """
    if overlay_facts is None:
        return DeltaDecision(mode=DeltaMode.OFF)

    by_id = plan.by_id
    prefills: list[DeltaPrefill] = []
    withheld: list[str] = []
    unconfirmable: list[str] = []
    for fact in sorted(overlay_facts.facts, key=lambda item: item.key):
        step = by_id.get(fact.key)
        if step is None:
            continue  # a fact no step in this protocol reads changes nothing
        if fact_needs_reconfirmation(fact, now):
            withheld.append(fact.key)
            continue
        confirm_tr = step.confirm_tr
        if confirm_tr is None:
            unconfirmable.append(fact.key)
            continue
        prefills.append(
            DeltaPrefill(
                slot_ref=step.step_id,
                value=fact.value,
                confirm_tr=confirm_tr,
                fact_key=fact.key,
                source_ref=fact.source_ref,
            )
        )
    return DeltaDecision(
        mode=DeltaMode.ON if prefills else DeltaMode.OFF,
        prefills=tuple(prefills),
        withheld_fact_keys=tuple(withheld),
        unconfirmable_fact_keys=tuple(unconfirmable),
    )

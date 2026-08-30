"""How a slot may be answered when the channel is a keyboard (INT-096).

CLAUDE.md invariant 22, its own words: *"No free numeric text entry on the
clinical critical path."* files/00 §2 records where that ruling came from and
what it costs to ignore — ``parseFloat("2,5")`` is ``2`` (a Turkish-typed
2,5 mg dose read as 2 mg) and ``parseFloat("1.500")`` is ``1.5`` (a
Turkish-*formatted* 1500 mg read as 1.5 mg, a factor of a thousand), and
neither leaves a diff that looks wrong. The same row states the remedy in the
same breath: *"doses use ``tam``/``yarım``/``çeyrek`` chips"*.

So this module answers one question — **may this slot be answered by typing?**
— and it answers it by refusing, not by degrading. A numeric slot with no
authored ``choices_tr`` has no typed affordance at all:
:class:`FreeNumericEntryRefused` is raised and the pack is at fault. There is
deliberately no fallback text field, no "numbers only" input and no parser
that would make one safe, because the failure mode is not malformed input —
it is well-formed input that means something else.

**"Critical path" is read as ``must_ask or required``** — the set a session
cannot legitimately finish without. That is the same reading ``tests/sim``
applies to files/02 §3's neighbouring low-literacy rule, and the two are kept
in step deliberately: they are different obligations (that one governs free
*text*, this one free *numbers*) over the same set of slots.

Nothing here can reach a model, a network or the triage engine. It reads a
resolved protocol and returns a decision about an input control.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from typing import Final

from clinical_schemas.common import FrozenModel
from protocols.compile.resolve import ResolvedProtocol
from protocols.types import SlotType
from pydantic import Field

__all__ = [
    "NUMERIC_SLOT_TYPES",
    "AffordanceKind",
    "FreeNumericEntryRefused",
    "SlotFacts",
    "free_numeric_critical_path_steps",
    "slot_facts",
]

NUMERIC_SLOT_TYPES: Final[frozenset[SlotType]] = frozenset(
    {SlotType.INTEGER, SlotType.DECIMAL, SlotType.DURATION, SlotType.QUANTITY}
)
"""Every slot type whose answer is a magnitude.

``DURATION`` and ``QUANTITY`` are in the set because they are numbers — a
duration is typed as a count of units and a quantity is a magnitude plus a
unit — and leaving either out is how a gate written for ``integer`` and
``decimal`` quietly stops covering the two slot types a clinical pack
actually uses for doses and intervals.
"""


class FreeNumericEntryRefused(ValueError):
    """A numeric slot offers no discrete answers, so typed cannot render it.

    Raised rather than degraded: the alternative is a text field on the
    clinical critical path, which CLAUDE.md invariant 22 forbids outright.
    """


class AffordanceKind(enum.StrEnum):
    """What the typed lane puts under the question.

    Two members, because there are only two safe shapes: pick one of the
    labels the pack authored, or write prose. A third — "type a number" — is
    the one this module exists to refuse.
    """

    CHOICE = "choice"
    FREE_TEXT = "free_text"


class SlotFacts(FrozenModel):
    """The little a typed lane needs to know about one slot.

    A projection rather than the resolved slot itself, so the lane cannot
    reach ``ask_if``, ``skip_if`` or an openEHR path: the frontier is the
    engine's decision (files/13 §9.2) and nothing here re-derives it.
    """

    step_id: str = Field(min_length=1)
    slot_type: SlotType
    critical_path: bool = Field(
        description="``must_ask or required`` — the set a session cannot "
        "legitimately finish without."
    )
    choices_tr: tuple[str, ...] = Field(
        default=(), description="Authored answer labels, verbatim (invariant 10)."
    )
    unit: str | None = Field(
        default=None, description="Authored unit for a quantity slot (files/03 §6)."
    )

    @property
    def numeric(self) -> bool:
        return self.slot_type in NUMERIC_SLOT_TYPES

    def affordance(self) -> AffordanceKind:
        """The input control, or a refusal.

        Order matters. Discrete labels win for every slot type, so a numeric
        slot the pack gave chips to is answered by tapping one. Only a numeric
        slot with no labels reaches the refusal, and it reaches it whether or
        not it is on the critical path: the display hazard of files/00 §2 is a
        property of the number, not of the slot's importance, and the
        critical-path boundary is where the *pack gate*
        (:func:`free_numeric_critical_path_steps`) draws the line invariant 22
        draws.
        """
        if self.choices_tr:
            return AffordanceKind.CHOICE
        if self.numeric:
            raise FreeNumericEntryRefused(
                f"{self.step_id}: a {self.slot_type.value} slot with no choices_tr has "
                "no typed affordance — the only remaining control is a numeric text "
                "field, and CLAUDE.md invariant 22 forbids free numeric text entry on "
                "the clinical critical path. The pack must author the discrete answers "
                "(files/00 §2: doses use tam/yarım/çeyrek chips); that content is "
                "clinical and awaits sign-off (HUMAN_BLOCKERS HB-C6, HB-C11)."
            )
        return AffordanceKind.FREE_TEXT


def slot_facts(protocol: ResolvedProtocol) -> Mapping[str, SlotFacts]:
    """Project every slot of a resolved protocol, keyed by step id."""
    return {
        f"{section.id}.{resolved.key}": SlotFacts(
            step_id=f"{section.id}.{resolved.key}",
            slot_type=resolved.slot.type,
            critical_path=resolved.slot.must_ask or resolved.slot.required,
            choices_tr=tuple(resolved.slot.choices_tr or ()),
            unit=resolved.slot.unit,
        )
        for section in protocol.sections
        for resolved in section.slots
    }


def free_numeric_critical_path_steps(protocol: ResolvedProtocol) -> tuple[str, ...]:
    """Steps that would need a numeric text field to be answered typed.

    The gate invariant 22 asks for, in the invariant's own boundary: numeric,
    on the clinical critical path, and with no authored discrete answers. A
    pack that lists any is a pack the kill-switch target cannot complete, so
    the emptiness of this tuple is a serving precondition and not a style
    preference.
    """
    offenders: list[str] = []
    for facts in slot_facts(protocol).values():
        if not (facts.critical_path and facts.numeric):
            continue
        if facts.choices_tr:
            continue
        offenders.append(facts.step_id)
    return tuple(offenders)

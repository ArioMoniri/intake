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
cannot legitimately finish without.

The refusal fires for *every* numeric slot with no labels, on the critical
path or not, while :func:`free_numeric_critical_path_steps` — the pack gate —
draws the line where invariant 22 draws it. That asymmetry is deliberate: the
display hazard of files/00 §2 is a property of the number, not of the slot's
importance, so the control is refused wherever it would appear; what the
invariant makes a *serving* precondition is the narrower set.

Nothing here can reach a model, a network or the triage engine. It reads a
resolved protocol and returns a decision about an input control.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from typing import Final

from clinical_schemas.common import FrozenModel
from protocols.compile.resolve import ResolvedProtocol
from protocols.dsl import Slot
from protocols.locale_text import entry_for
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
    """What the typed profile puts under the question.

    Two members, because there are only two safe shapes: pick one of the
    labels the pack authored, or write prose. A third — "type a number" — is
    the one this module exists to refuse.
    """

    CHOICE = "choice"
    FREE_TEXT = "free_text"


class SlotFacts(FrozenModel):
    """The little the typed transport needs to know about one slot.

    A projection rather than the resolved slot itself, so the transport cannot
    reach ``ask_if``, ``skip_if`` or an openEHR path: the frontier is the
    engine's decision (files/13 §9.2) and nothing here re-derives it. That is
    the same discipline the profile as a whole runs under — the transport
    renders, it does not decide.
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
        slot with no labels reaches the refusal.
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
                "clinical and awaits sign-off (HUMAN_BLOCKERS HB-C6)."
            )
        return AffordanceKind.FREE_TEXT


def _choices(slot: Slot, locale: str) -> tuple[str, ...]:
    """The locale's own answer options, in the pack's order.

    Written as a function rather than inline because ``tuple(mapping or ())``
    is *silently* wrong on a locale map: it yields the keys, so the chip list
    would read ``("tr",)`` and every parity test would compare one chip named
    after a language against three named after answers (INT-297).
    """
    if slot.choices_tr is None:
        return ()
    return tuple(entry_for(slot.choices_tr, locale))


def slot_facts(protocol: ResolvedProtocol) -> Mapping[str, SlotFacts]:
    """Project every slot of a resolved protocol, keyed by step id.

    The key is ``<section>.<slot>`` — the same dotted reference
    ``build_plan`` mints, a gate atom spells and a red-flag predicate spells
    (files/03 §6), so this map is joinable with the engine's own by equality.
    """
    return {
        f"{section.id}.{resolved.key}": SlotFacts(
            step_id=f"{section.id}.{resolved.key}",
            slot_type=resolved.slot.type,
            critical_path=resolved.slot.must_ask or resolved.slot.required,
            choices_tr=_choices(resolved.slot, protocol.locale),
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
    return tuple(
        facts.step_id
        for facts in slot_facts(protocol).values()
        if facts.critical_path and facts.numeric and not facts.choices_tr
    )

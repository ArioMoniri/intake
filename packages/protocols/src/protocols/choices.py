"""Binding a submitted choice set to a slot answer (INT-604, ADR-043).

Two functions, and the difference between them is the point.

:func:`bind_choice_set` is the slot binding: it checks a submitted set against
the slot's declared shape and refuses anything the shape does not admit — a
value outside the value set, several values on a single-select slot, and the
slot's exclusive option beside any other member. It **refuses**; it never
trims. Trimming "yok" would keep a symptom the patient took back, and trimming
the symptom would drop a value that may fire a red-flag rule. Neither is a
decision the server may take after the patient pressed submit: the lanes clear
the conflicting selection on screen, visibly, before submit.

:func:`submitted_set_answer` is how the triage hop reads a set it is handed
(``services/api triage_hop``): whole. A single member is that member; several
are the files/12 §7.3 union, which the engine evaluates world by world and
joins with Kleene OR — any member that fires, fires (escalation only). It
applies no exclusivity, because a set refused there would leave a firing
symptom unevaluated, and that is suppression by another name.

Nothing here logs and no error message carries a submitted value (invariant 6).
"""

from __future__ import annotations

from collections.abc import Sequence

from clinical_schemas.session import AnswerState

from protocols.dsl import Slot
from protocols.triage.context import SlotAnswer
from protocols.types import SlotType

__all__ = ["ChoiceSetRefused", "bind_choice_set", "submitted_set_answer"]


class ChoiceSetRefused(ValueError):
    """A submitted set the slot's declared shape does not admit. Names the rule
    broken, never a value (invariant 6)."""


def _distinct(values: Sequence[str]) -> tuple[str, ...]:
    seen: list[str] = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return tuple(seen)


def submitted_set_answer(values: Sequence[str]) -> SlotAnswer | None:
    """The whole submitted set as one slot answer; None for an empty set."""
    members = _distinct(values)
    if not members:
        return None
    if len(members) == 1:
        return SlotAnswer(state=AnswerState.ASKED_PRESENT, values=members)
    return SlotAnswer(state=AnswerState.CONTESTED, values=members)


def bind_choice_set(slot: Slot, values: Sequence[str], members: Sequence[str]) -> SlotAnswer:
    """Bind ``values`` to a code slot whose value set is ``members``, or refuse."""
    if slot.type is not SlotType.CODE:
        raise ChoiceSetRefused("a choice set binds to a code slot only")
    chosen = _distinct(values)
    if not chosen:
        raise ChoiceSetRefused("an empty choice set is no answer")
    allowed = set(members)
    if any(value not in allowed for value in chosen):
        raise ChoiceSetRefused("a submitted choice is not a member of the slot's value set")
    if len(chosen) > 1 and not slot.multiple:
        raise ChoiceSetRefused("a single-select slot binds exactly one member")
    exclusive = set(slot.exclusive_choices())
    if len(chosen) > 1 and exclusive.intersection(chosen):
        raise ChoiceSetRefused(
            "the slot's exclusive option was submitted beside another member; the set "
            "is refused whole, never trimmed (ADR-043)"
        )
    state = AnswerState.ASKED_PRESENT if len(chosen) == 1 else AnswerState.CONTESTED
    return SlotAnswer(state=state, values=chosen)

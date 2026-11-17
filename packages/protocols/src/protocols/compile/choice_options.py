"""Exclusive multi-select options, checked at compile time (INT-604, ADR-043).

The schema (:class:`protocols.dsl.Slot`) already refuses ``exclusive`` on a
single-select slot and a second exclusive option on one slot. Two checks need
the value set and the authored choices, so they run here, on the merged
document, beside :mod:`protocols.compile.gate_values`:

- ``OPTION_OUTSIDE_CHOICES`` — an ``options`` key is not a member of the slot's
  committed value set (or, while no set is committed, not one of its ``tr``
  choices). An attribute on an option nobody can choose asserts nothing, and a
  misspelt "yok" would leave the real one unmarked.
- ``NONE_CHOICE_NOT_EXCLUSIVE`` — a multi-select slot offers a choice that
  means "none of these" (:data:`NONE_WORDS`, compared whole after NFC and
  lower-casing) without declaring it exclusive. Without the flag a patient can
  hold "yok" beside a symptom, and the note reads both.

The check only refuses. It never marks an option, rewrites a choice or touches
a red-flag rule (CLAUDE.md invariants 1 and 7).
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Sequence
from typing import Final

from protocols.bindings import fhir_link_id
from protocols.compile.errors import Refusal, RefusalCode
from protocols.dsl import Slot
from protocols.locale_text import DEFAULT_LOCALE
from protocols.types import SlotType
from protocols.valuesets import ValueSetTable

__all__ = ["NONE_WORDS", "choice_option_refusals"]

SlotEntry = tuple[str, str, Slot]

#: Whole choices that mean "none of the listed options". A choice that merely
#: contains one ("belli bir saati yok") is a different answer and is not here.
NONE_WORDS: Final[frozenset[str]] = frozenset({"yok", "hiçbiri", "hiçbiri yok", "hiçbirisi"})

_CITATION = "(INT-604; ADR-043)"


def _normal(text: str) -> str:
    return unicodedata.normalize("NFC", text).strip().lower()


def _choices(slot: Slot) -> tuple[str, ...]:
    if slot.choices_tr is None:
        return ()
    return tuple(slot.choices_tr.get(DEFAULT_LOCALE, ()))


def choice_option_refusals(slots: Iterable[SlotEntry], valuesets: ValueSetTable) -> list[Refusal]:
    """Every option attribute naming no member, and every unmarked none-choice."""
    refusals: list[Refusal] = []
    for section_id, key, slot in slots:
        if slot.type is not SlotType.CODE:
            continue
        subject = fhir_link_id(section_id, key)
        committed = valuesets.members(slot.valueset or "")
        members: Sequence[str] = committed if committed is not None else _choices(slot)
        stray = [option for option in slot.options if option not in members]
        if stray:
            refusals.append(
                Refusal(
                    code=RefusalCode.OPTION_OUTSIDE_CHOICES,
                    subject=subject,
                    message=(
                        f"option(s) {', '.join(repr(o) for o in stray)} name no member of "
                        f"{slot.valueset} ({', '.join(repr(m) for m in members)}); an "
                        f"attribute on an option nobody can choose asserts nothing {_CITATION}"
                    ),
                )
            )
        if not slot.multiple:
            continue
        exclusive = set(slot.exclusive_choices())
        unmarked = [c for c in _choices(slot) if _normal(c) in NONE_WORDS and c not in exclusive]
        if unmarked:
            refusals.append(
                Refusal(
                    code=RefusalCode.NONE_CHOICE_NOT_EXCLUSIVE,
                    subject=subject,
                    message=(
                        f"multi-select choice(s) {', '.join(repr(c) for c in unmarked)} mean "
                        "'none of these' but are not declared exclusive, so the patient can "
                        "hold them beside a symptom; declare options: {<choice>: {exclusive: "
                        f"true}} {_CITATION}"
                    ),
                )
            )
    return refusals

"""INT-297 — which locales a pack can actually be run in.

Invariant 10 restated per locale rather than weakened: *scripted questions,
red-flag action scripts and validated instruments are spoken verbatim from the
locale's own entry, and a locale whose entry is absent cannot be selected for
that pack.*

Two rules, and the second is the one that matters.

**Intersection, never union.** A pack is selectable in a locale only if *every*
speakable field carries an entry for it. A locale that can ask the first
question and not the second cannot run the intake: offering it produces the
session half in one language and half in Turkish that INT-296 spent its design
refusing, and the patient meets that seam in the middle of a symptom question.

**The fields INT-297 did not migrate clamp the answer to Turkish.** Five fields
became locale maps: ``text_tr``, ``ask_tr``, ``follow_up_tr``, ``choices_tr``
and ``why_tr``. ``confirm_tr``, ``action_tr``, ``do_nots_tr`` and ``ask_one_tr``
did not — they are outside this issue's acceptance — and they are spoken.
A pack that carries one of them therefore has a string with no locale entry at
all, so :func:`selectable_locales` clamps it to ``tr``. That is not a
work-around; it is the same rule applied to a field whose map is, for now, of
size one. When those fields are migrated the clamp lifts on its own, and until
then a red-flag action script cannot be spoken in a language nobody wrote it in.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping

from protocols.dsl import Instrument, RedFlagRule, Section, Slot
from protocols.locale_text import DEFAULT_LOCALE, common_locales, known_locales
from protocols.ops import AddRuleOp, AddSlotOp, OverrideTextOp, TightenRuleOp
from protocols.pack import ProtocolPack

__all__ = ["MONOLINGUAL_SPOKEN_FIELDS", "selectable_locales"]

#: Spoken fields that are still one string rather than a map. Named here so the
#: clamp is a list a reader can check against the DSL, not a buried condition.
MONOLINGUAL_SPOKEN_FIELDS = ("confirm_tr", "action_tr", "do_nots_tr", "ask_one_tr")


def _slot_maps(slot: Slot) -> Iterator[Mapping[str, object] | None]:
    yield slot.ask_tr
    yield slot.follow_up_tr
    yield slot.choices_tr


def _instrument_maps(instrument: Instrument) -> Iterator[Mapping[str, object] | None]:
    if instrument.voice is not None:
        yield instrument.voice.allow_paraphrase
    for item in instrument.items:
        yield item.text_tr
        yield item.allow_paraphrase


def _rule_maps(rule: RedFlagRule) -> Iterator[Mapping[str, object] | None]:
    if rule.action is None:
        return
    for location in (rule.action.remote, rule.action.on_site):
        if location is not None:
            yield location.why_tr


def _section_maps(section: Section) -> Iterator[Mapping[str, object] | None]:
    if section.voice is not None:
        yield section.voice.allow_paraphrase
    for slot in section.slots.values():
        yield from _slot_maps(slot)


def _is_monolingual_spoken(rule: RedFlagRule) -> bool:
    if rule.action is None:
        return False
    if rule.action.unknown is not None:
        return True
    return any(
        location is not None and (location.action_tr is not None or location.do_nots_tr)
        for location in (rule.action.remote, rule.action.on_site)
    )


def _carries_a_monolingual_string(pack: ProtocolPack) -> bool:
    for section in pack.sections.values():
        for slot in section.slots.values():
            if slot.confirm_tr is not None:
                return True
    for rule in _declared_rules(pack):
        if _is_monolingual_spoken(rule):
            return True
    for op in pack.ops:
        if isinstance(op, AddSlotOp) and op.slot.confirm_tr is not None:
            return True
        if isinstance(op, AddRuleOp | TightenRuleOp) and _is_monolingual_spoken(op.rule):
            return True
    return False


def _declared_rules(pack: ProtocolPack) -> Iterator[RedFlagRule]:
    yield from pack.red_flags
    for op in pack.ops:
        if isinstance(op, AddRuleOp | TightenRuleOp):
            yield op.rule


def selectable_locales(pack: ProtocolPack) -> frozenset[str]:
    """Every locale in which this pack can be run, one pack at a time.

    The caller intersects across the resolved chain; a pack that says nothing
    constrains nothing, which is why an empty pack returns the whole registry
    rather than the empty set.
    """
    maps: list[Mapping[str, object] | None] = []
    if pack.voice is not None:
        maps.append(pack.voice.allow_paraphrase)
    for section in pack.sections.values():
        maps.extend(_section_maps(section))
    for instrument in pack.instruments:
        maps.extend(_instrument_maps(instrument))
    for rule in _declared_rules(pack):
        maps.extend(_rule_maps(rule))
    for op in pack.ops:
        if isinstance(op, AddSlotOp):
            maps.extend(_slot_maps(op.slot))
        elif isinstance(op, OverrideTextOp):
            maps.append(op.text_tr)
    common = common_locales(maps)
    if _carries_a_monolingual_string(pack):
        common &= {DEFAULT_LOCALE}
    return common & known_locales()

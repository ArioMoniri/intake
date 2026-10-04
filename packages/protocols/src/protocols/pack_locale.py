"""INT-297/INT-314 — which locales a pack can actually be run in.

Invariant 10 restated per locale rather than weakened: *scripted questions,
red-flag action scripts and validated instruments are spoken verbatim from the
locale's own entry, and a locale whose entry is absent cannot be selected for
that pack.*

**Intersection, never union.** A pack is selectable in a locale only if *every*
speakable field carries an entry for it. A locale that can ask the first
question and not the second cannot run the intake: offering it produces the
session half in one language and half in Turkish that INT-296 spent its design
refusing, and the patient meets that seam in the middle of a symptom question.

**INT-314 removed the clamp that stood in for the action half.** INT-297 left
``confirm_tr``, ``action_tr``, ``do_nots_tr`` and ``ask_one_tr`` as single
strings, and rather than ignore that, this module intersected the answer with
``{tr}`` whenever a pack carried one of them — fail-closed, so no language could
speak a red-flag script nobody had written in it. The four are locale maps now,
so the special case is gone entirely rather than left as a condition that can
no longer fire: a clamp that outlives its reason is a silent restriction nobody
can see, and a reader cannot tell a dead one from a live one.

What replaced it is not a weaker rule but the *same* rule applied to four more
fields — they are simply in the intersection now, like every other speakable
field. The one asymmetry is ``do_nots_tr``: an empty map means this branch has
no do-nots in any language, which constrains nothing, so it is passed as
``None``. Reading an empty map as "speaks no locales" would make every rule
without a do-not list unselectable in every language, Turkish included.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping

from protocols.dsl import Instrument, RedFlagRule, Section, Slot
from protocols.locale_text import common_locales, known_locales
from protocols.ops import AddRuleOp, AddSlotOp, OverrideTextOp, TightenRuleOp
from protocols.pack import ProtocolPack

__all__ = ["selectable_locales"]


def _constraining(mapping: Mapping[str, object]) -> Mapping[str, object] | None:
    """An empty map says nothing about which languages a pack can be run in."""
    return mapping or None


def _slot_maps(slot: Slot) -> Iterator[Mapping[str, object] | None]:
    yield slot.ask_tr
    yield slot.confirm_tr
    yield slot.follow_up_tr
    yield slot.choices_tr
    if slot.proxy is not None:
        # INT-483 / ADR-040: what a proxy hears is a speakable field like any
        # other, so it joins the intersection rather than getting a fallback.
        yield slot.proxy.ask_tr
        yield slot.proxy.confirm_tr
        yield slot.proxy.follow_up_tr


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
            yield location.action_tr
            yield _constraining(location.do_nots_tr)
            yield location.why_tr
    if rule.action.unknown is not None:
        yield rule.action.unknown.ask_one_tr


def _section_maps(section: Section) -> Iterator[Mapping[str, object] | None]:
    if section.voice is not None:
        yield section.voice.allow_paraphrase
    for slot in section.slots.values():
        yield from _slot_maps(slot)


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
    return common_locales(maps) & known_locales()

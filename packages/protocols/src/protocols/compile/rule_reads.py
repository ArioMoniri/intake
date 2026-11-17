"""No op leaves a red-flag rule reading a slot the merged pack removed (INT-382).

A red flag fires only on TRUE (files/12 §1.1), and a rule whose slot no
longer exists reads Unknown for the whole session, so it never fires. The
closed op set makes deleting a rule unrepresentable (files/12 §3.1), but a
``suppress_slot`` of the slot the rule reads removes the flag all the same,
without ever naming it: removal by another door, which CLAUDE.md invariant 7
forbids in every layer.

INT-258 closed that door for overlays only (``OVERLAY_REMOVES_RULE_SLOT`` in
:mod:`protocols.compile.overlay`). The PR #628 verification (H-1) measured the
same op in a chain pack (cluster to specialty) compiling under all eight
clusters, with the rule that reads the removed slot served and never firing.
This module is the check for every layer. It runs once, on the merged pack,
after the chain is merged and every op of every layer is applied, so the
layer that removed the slot and the order it ran in no longer matter: what is
judged is what would be served.

What it reads, per rule:

- every slot reference in ``when``, through the parser and reference set the
  rules engine uses (:func:`protocols.triage.expr.referenced_slots`);
- ``tense_anchor``, which the engine unions into that set (files/12 §2.4);
- nothing else. No other :class:`protocols.dsl.RedFlagRule` field names a
  slot: the action block names locations and action codes.

Which rules: every pack rule after overlay composition, and every
``base.life_threat`` rule. The sibling set sits outside the inheritance chain
and nothing may extend it (files/12 §1), yet a pack that suppresses the slot a
life-threat rule reads relaxes that rule just the same, and the overlay
composer never sees those rules. Draft rules count: a ``draft_needs_source``
rule is signed with the reads it has, so a draft anchored on a removed slot is
refused now rather than served dead later. A draft ``when`` in the
invariant-17 pending form reads no slot; its ``tense_anchor`` still does.

A reference names a slot of the merged pack when it is spelled
``<section>.<slot>`` or bare ``<slot>``, the two spellings ``when`` and
``tense_anchor`` use (files/12 §2.4). A read the merged pack lacks is refused
as ``RULE_READS_REMOVED_SLOT`` when an applied ``suppress_slot`` names it,
because ``suppress_slot`` is the one op that takes a slot away. The message
names the rule, the slot, and each suppressing pack and pointer, ids only.
Where every suppressor is an overlay the composer already judged against a
pack rule it could parse, ``OVERLAY_REMOVES_RULE_SLOT`` has reported it and it
is not reported twice. A draft in the pending form is the exception: the
composer refuses it as unreadable without naming the slot, so the removal is
named here.

Out of scope: a read that no pack ever declared. No op leaves that; it is
files/04 §8.2's ``no_rule_references_an_undeclared_slot``, part of INT-043's
acceptance and blocked on the base.intake additions of HUMAN_BLOCKERS HB-C6.

When a slot is suppressed anywhere, a rule whose ``when`` falls outside the
closed grammar is refused as a validation finding. Its reads cannot be listed,
so the suppression cannot be shown to leave it intact (the INT-258 overlay
gate's reasoning).

The check only refuses. It never adds a slot, never rewrites a rule, and never
touches a level, a predicate or the life-threat set (CLAUDE.md invariants 1
and 7).
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass

from protocols.compile.errors import Refusal, RefusalCode
from protocols.dsl import RedFlagRule
from protocols.triage.expr import WhenGrammarError, parse_when, referenced_slots
from protocols.validator import PLACEHOLDER_SIGNOFF_RE

__all__ = ["RuleReads", "pointer_slot_names", "rule_read_refusals", "rule_reads"]


def pointer_slot_names(pointer: str) -> frozenset[str]:
    """Both spellings a ``/sections/<s>/slots/<k>`` pointer can be read under:
    the dotted reference a ``when`` predicate uses and the bare key a
    ``tense_anchor`` may use. A pointer that does not address one slot names
    nothing here; that is the validator's UNKNOWN_TARGET."""
    parts = pointer.lstrip("/").split("/")
    if len(parts) != 4 or parts[0] != "sections" or parts[2] != "slots":
        return frozenset()
    return frozenset({f"{parts[1]}.{parts[3]}", parts[3]})


@dataclass(frozen=True, slots=True)
class RuleReads:
    """The slot references one rule reads, split by the field that reads them.

    ``parsed`` is False for the invariant-17 pending form, which is not a
    predicate: the overlay composer cannot parse it, so it refuses such a rule
    as unreadable and never names the rule's anchor.
    """

    when: frozenset[str]
    tense_anchor: str
    parsed: bool = True

    @property
    def all(self) -> frozenset[str]:
        """Every reference, as the engine unions them (files/12 §2.4)."""
        return self.when | {self.tense_anchor}

    def fields_reading(self, ref: str) -> str:
        """Which rule fields read ``ref``, for the refusal message."""
        fields = [
            name
            for name, reads in (
                ("when", ref in self.when),
                ("tense_anchor", ref == self.tense_anchor),
            )
            if reads
        ]
        return " and ".join(fields)


def rule_reads(rule: RedFlagRule) -> RuleReads | None:
    """What ``rule`` reads, or ``None`` when its ``when`` cannot be parsed.

    The invariant-17 pending form is not a predicate and reads no slot; the
    validator owns where that form may appear (PLACEHOLDER_OUTSIDE_DRAFT).
    """
    if PLACEHOLDER_SIGNOFF_RE.fullmatch(rule.when.strip()):
        return RuleReads(when=frozenset(), tense_anchor=rule.tense_anchor, parsed=False)
    try:
        node = parse_when(rule.when)
    except WhenGrammarError:
        return None
    return RuleReads(when=referenced_slots(node), tense_anchor=rule.tense_anchor)


@dataclass(frozen=True, slots=True)
class _Suppression:
    pack_id: str
    pointer: str
    names: frozenset[str]


def _declared_names(declared: Iterable[tuple[str, str]]) -> frozenset[str]:
    names: set[str] = set()
    for section_id, key in declared:
        names.add(f"{section_id}.{key}")
        names.add(key)
    return frozenset(names)


def rule_read_refusals(
    *,
    pack_rules: Sequence[RedFlagRule],
    life_threat_rules: Sequence[RedFlagRule],
    declared: Iterable[tuple[str, str]],
    suppressions: Iterable[tuple[str, str]],
    overlay_checked: Collection[str] = (),
) -> list[Refusal]:
    """Refuse every rule read that an applied ``suppress_slot`` removed.

    ``declared`` is every ``(section_id, slot_key)`` of the merged pack after
    every op applied. ``suppressions`` is every applied ``suppress_slot`` as
    ``(pack_id, pointer)``. ``overlay_checked`` names the overlays whose
    suppressions :func:`protocols.compile.overlay.compose_overlay_rules`
    already judged against ``pack_rules``; a fault it reported is not
    reported again.

    Returns every refusal, ordered by rule id and then slot reference, so one
    compile names every rule it would otherwise serve dead.
    """
    removals = [
        _Suppression(pack_id=pack_id, pointer=pointer, names=pointer_slot_names(pointer))
        for pack_id, pointer in suppressions
    ]
    if not removals:
        return []
    names = _declared_names(declared)
    checked = frozenset(overlay_checked)
    # The composer refuses every unparseable pack rule once an overlay it
    # applied suppresses a slot; saying so again here would be one fault twice.
    composer_read_pack_rules = any(removal.pack_id in checked for removal in removals)

    refusals: list[Refusal] = []
    entries = [(rule, False) for rule in pack_rules] + [(rule, True) for rule in life_threat_rules]
    for rule, sibling in sorted(entries, key=lambda entry: (entry[0].id, entry[1])):
        kind = "base.life_threat rule" if sibling else "red-flag rule"
        reads = rule_reads(rule)
        if reads is None:
            if sibling or not composer_read_pack_rules:
                refusals.append(_unreadable(rule.id, kind))
            continue
        # The composer names a removed read itself only for a pack rule it
        # could parse; a pending-form draft it refuses as unreadable instead.
        composer_named = not sibling and reads.parsed
        for ref in sorted(reads.all - names):
            by = [removal for removal in removals if ref in removal.names]
            if not by or (composer_named and all(removal.pack_id in checked for removal in by)):
                continue
            refusals.append(_removed(rule.id, ref, kind, reads.fields_reading(ref), by))
    return refusals


def _removed(rule_id: str, ref: str, kind: str, fields: str, by: Sequence[_Suppression]) -> Refusal:
    named = ", ".join(sorted(f"{removal.pack_id}{removal.pointer}" for removal in by))
    return Refusal(
        code=RefusalCode.RULE_READS_REMOVED_SLOT,
        subject=f"{rule_id}:{ref}",
        message=f"the {kind} {rule_id} reads {ref!r} in its {fields}, and suppress_slot "
        f"removes that slot from the merged pack ({named}). A red flag whose slot is gone "
        "reads Unknown and never fires, so the op removes the flag without naming it, in "
        "a chain pack exactly as in an overlay (CLAUDE.md invariant 7; files/12 §3.1; "
        "files/04 §2.3). A draft rule counts: it is signed with the reads it has",
    )


def _unreadable(rule_id: str, kind: str) -> Refusal:
    return Refusal(
        code=RefusalCode.VALIDATION_FINDING,
        subject=rule_id,
        message=f"a slot is suppressed and the {kind}'s when is outside the closed when "
        "grammar, so the slots it reads cannot be listed and the suppression cannot be "
        "shown to leave it intact (files/03 §6; CLAUDE.md invariant 7)",
    )

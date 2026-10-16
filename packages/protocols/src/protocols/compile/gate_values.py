"""A gate compares a code slot only against a value the slot can carry (INT-441).

A gate opens only on TRUE (files/13 §9.5). Comparing a code slot against a
literal the slot never carries makes the comparison answer the same for every
patient: ``==`` never opens and ``!=`` always does. ``base.intake`` shipped
both shapes (``subject_role != 'kendim'`` against the choice ``"kendim için"``;
``pregnancy_status != 'hayir'`` against ``"hayır"``), and INT-489 found the
first again from the proxy side. The values a code slot carries are its
committed value set (:mod:`protocols.valuesets`), so the check is exact
membership in that set.

Three refusals, each naming the gated step, the slot and the value set:

- ``GATE_VALUE_OUTSIDE_VALUESET`` — a literal compared against a code slot is
  not a member: a prefix (``'kendim'``), an ASCII folding (``'hayir'``), a case
  change, a stray space or a non-string all refuse;
- ``GATE_VALUESET_UNCOMMITTED`` — the code slot's value set is not committed,
  so nothing shows the literal is reachable. That is fail closed by design: it
  is how the defect went unseen;
- ``CHOICE_OUTSIDE_VALUESET`` — a ``tr`` choice of a code slot whose value set
  is committed is not a member, so the committed set and what the patient is
  offered have drifted apart.

Every comparison the closed ``when`` grammar can place is read: ``==``, ``!=``
and the ordered operators either way round, set membership, and comparisons
under ``!``, ``&&`` and ``||``, in ``ask_if`` and ``skip_if`` alike. Only gates
are read. A red-flag ``when`` is the rules engine's and is untouched, and the
check only refuses: it never rewrites a gate (CLAUDE.md invariants 1 and 7).
A gate outside the grammar, or one whose slot reference does not resolve, is
refused elsewhere (``GATE_NOT_PROJECTABLE``; ``GATE_REF_*``) and skipped here.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from decimal import Decimal

from protocols.bindings import fhir_link_id
from protocols.compile.errors import Refusal, RefusalCode
from protocols.dsl import Slot
from protocols.gates import SlotNamespace, qualify_gate
from protocols.locale_text import DEFAULT_LOCALE
from protocols.triage.expr import (
    And,
    Compare,
    InSet,
    Lit,
    Not,
    Or,
    Ref,
    WhenGrammarError,
    WhenNode,
    parse_when,
)
from protocols.types import SlotType
from protocols.valuesets import ValueSetTable

__all__ = ["GateComparison", "code_gate_comparisons", "gate_value_refusals"]

SlotEntry = tuple[str, str, Slot]
"""``(section_id, slot_key, slot)`` — one slot of the merged document."""

_GATE_FIELDS = ("ask_if", "skip_if")
_CITATION = "(INT-441; INT-489; files/13 §9.5)"


@dataclass(frozen=True, slots=True)
class GateComparison:
    """One literal a gate compares against a code slot."""

    step: str
    field: str
    gate: str
    target: str
    literal: bool | Decimal | str


def code_gate_comparisons(slots: Iterable[SlotEntry]) -> tuple[GateComparison, ...]:
    """Every literal compared against a code slot by any gate, in document order."""
    entries = tuple(slots)
    namespace = SlotNamespace((section_id, key) for section_id, key, _ in entries)
    by_ref = {fhir_link_id(section_id, key): slot for section_id, key, slot in entries}
    found: list[GateComparison] = []
    for section_id, key, slot in entries:
        for field_name in _GATE_FIELDS:
            text: str | None = getattr(slot, field_name)
            if text is None:
                continue
            try:
                node = parse_when(text)
            except WhenGrammarError:
                continue
            qualified, issues = qualify_gate(node, namespace)
            if issues:
                continue
            found.extend(
                GateComparison(
                    step=fhir_link_id(section_id, key),
                    field=field_name,
                    gate=text,
                    target=target,
                    literal=literal,
                )
                for target, literal in _literals(qualified)
                if by_ref[target].type is SlotType.CODE
            )
    return tuple(found)


def gate_value_refusals(slots: Iterable[SlotEntry], valuesets: ValueSetTable) -> list[Refusal]:
    """Every gate literal and ``tr`` choice the committed value sets do not hold."""
    entries = tuple(slots)
    by_ref = {fhir_link_id(section_id, key): slot for section_id, key, slot in entries}
    refusals: list[Refusal] = []
    uncommitted: set[tuple[str, str, str]] = set()
    for comparison in code_gate_comparisons(entries):
        valueset_id = by_ref[comparison.target].valueset or ""
        members = valuesets.members(valueset_id)
        if members is None:
            key = (comparison.step, comparison.field, comparison.target)
            if key not in uncommitted:
                uncommitted.add(key)
                refusals.append(_uncommitted(comparison, valueset_id))
        elif not isinstance(comparison.literal, str) or comparison.literal not in members:
            refusals.append(_outside(comparison, valueset_id, members))
    refusals.extend(_choice_refusals(entries, valuesets))
    return refusals


def _literals(node: WhenNode) -> Iterator[tuple[str, bool | Decimal | str]]:
    if isinstance(node, Compare):
        for ref, lit in ((node.left, node.right), (node.right, node.left)):
            if isinstance(ref, Ref) and isinstance(lit, Lit):
                yield ref.name, lit.value
    elif isinstance(node, InSet):
        if isinstance(node.operand, Ref):
            for element in node.elements:
                yield node.operand.name, element.value
    elif isinstance(node, Not):
        yield from _literals(node.item)
    elif isinstance(node, (And, Or)):
        for item in node.items:
            yield from _literals(item)


def _members_text(members: Sequence[str]) -> str:
    return ", ".join(repr(member) for member in members)


def _outside(comparison: GateComparison, valueset_id: str, members: Sequence[str]) -> Refusal:
    return Refusal(
        code=RefusalCode.GATE_VALUE_OUTSIDE_VALUESET,
        subject=comparison.step,
        message=(
            f"{comparison.field} {comparison.gate!r} compares {comparison.target} with "
            f"{comparison.literal!r}, which is not a member of {valueset_id} "
            f"({_members_text(members)}). The slot never carries it, so the comparison "
            "answers the same for every patient; compare against an exact member "
            f"{_CITATION}"
        ),
    )


def _uncommitted(comparison: GateComparison, valueset_id: str) -> Refusal:
    return Refusal(
        code=RefusalCode.GATE_VALUESET_UNCOMMITTED,
        subject=comparison.step,
        message=(
            f"{comparison.field} {comparison.gate!r} compares {comparison.target}, whose "
            f"value set {valueset_id} is not committed, so nothing shows the literal is a "
            "value the slot can carry. Commit the set as the slot's authored tr choices "
            f"in packages/protocols/base/valuesets.yaml {_CITATION}"
        ),
    )


def _choice_refusals(entries: Sequence[SlotEntry], valuesets: ValueSetTable) -> list[Refusal]:
    refusals: list[Refusal] = []
    for section_id, key, slot in entries:
        if slot.type is not SlotType.CODE or slot.choices_tr is None:
            continue
        valueset_id = slot.valueset or ""
        members = valuesets.members(valueset_id)
        if members is None:
            continue
        outside = [c for c in slot.choices_tr.get(DEFAULT_LOCALE, ()) if c not in members]
        if outside:
            refusals.append(
                Refusal(
                    code=RefusalCode.CHOICE_OUTSIDE_VALUESET,
                    subject=fhir_link_id(section_id, key),
                    message=(
                        f"tr choice(s) {_members_text(outside)} are not members of the "
                        f"committed value set {valueset_id} ({_members_text(members)}); an "
                        "offered choice the set does not hold is a value no gate can be "
                        f"checked against {_CITATION}"
                    ),
                )
            )
    return refusals

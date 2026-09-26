"""Gate slot references, resolved against the resolved chain (INT-355).

files/03 §6 atoms may be section-qualified (``identity_check.subject_role``)
or bare (``subject_role``) — :data:`protocols.types.SLOT_REF_PATTERN` admits
both, and ``base.intake`` writes the bare form. Everything that reads a gate
keys a slot ``<section>.<slot>``: the engine's step id, the FHIR linkId and
the JSON pointer are one identity (:func:`protocols.bindings.fhir_link_id`).
A bare name therefore has to be *resolved* to that key before anything
evaluates it. Read as written, it names a key no slot carries, evaluates
Unknown for the whole session, and — because a gate opens only on TRUE
(files/13 §9.5) — the question it guards is silently never asked.

Resolution is exact and fails closed:

- a qualified name resolves to itself when that slot exists;
- a bare name resolves to the ONE slot of that name across every section of
  the resolved chain (base + cluster + specialty + overlays);
- a bare name held by two or more sections is :attr:`GateRefProblem.AMBIGUOUS`
  — an authoring error, never a first- or last-writer pick;
- a name nothing holds is :attr:`GateRefProblem.UNKNOWN` — a gate on it could
  never open.

The compiler refuses both (``RefusalCode.GATE_REF_AMBIGUOUS`` /
``GATE_REF_UNKNOWN``) and the engine refuses them again at plan build, so a
document that never went through the compiler cannot reintroduce the defect.

Only gates are resolved here. A red-flag ``when`` and its ``tense_anchor`` are
read by the rules engine through its own reference set and are untouched
(CLAUDE.md invariant 1).
"""

from __future__ import annotations

import enum
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from protocols.bindings import fhir_link_id
from protocols.triage.expr import (
    And,
    BoolRef,
    Compare,
    InSet,
    Not,
    Operand,
    Or,
    Ref,
    WhenNode,
    referenced_slots,
)

__all__ = ["GateRefIssue", "GateRefProblem", "SlotNamespace", "qualify_gate"]


class GateRefProblem(enum.StrEnum):
    """Why a gate reference does not resolve to exactly one slot."""

    AMBIGUOUS = "ambiguous"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class GateRefIssue:
    """One gate reference that names two or more slots, or none."""

    name: str
    problem: GateRefProblem
    candidates: tuple[str, ...] = ()

    def describe(self) -> str:
        if self.problem is GateRefProblem.AMBIGUOUS:
            return (
                f"{self.name!r} is ambiguous: {len(self.candidates)} sections of the "
                f"resolved chain hold it ({', '.join(self.candidates)}); a bare gate "
                "name must match exactly one slot — qualify it as <section>.<slot>"
            )
        return f"{self.name!r} names no slot in the resolved chain"


class SlotNamespace:
    """Every slot a gate may read, addressable qualified or bare."""

    __slots__ = ("_bare", "_qualified")

    def __init__(self, slots: Iterable[tuple[str, str]]) -> None:
        qualified: set[str] = set()
        bare: dict[str, set[str]] = {}
        for section_id, key in slots:
            ref = fhir_link_id(section_id, key)
            qualified.add(ref)
            bare.setdefault(key, set()).add(ref)
        self._qualified = frozenset(qualified)
        self._bare = {key: tuple(sorted(refs)) for key, refs in bare.items()}

    def resolve(self, name: str) -> str | GateRefIssue:
        """The qualified key ``name`` reads, or why there is not exactly one."""
        if "." in name:
            if name in self._qualified:
                return name
            return GateRefIssue(name=name, problem=GateRefProblem.UNKNOWN)
        holders = self._bare.get(name, ())
        if len(holders) == 1:
            return holders[0]
        if not holders:
            return GateRefIssue(name=name, problem=GateRefProblem.UNKNOWN)
        return GateRefIssue(name=name, problem=GateRefProblem.AMBIGUOUS, candidates=holders)


def qualify_gate(
    node: WhenNode, namespace: SlotNamespace
) -> tuple[WhenNode, tuple[GateRefIssue, ...]]:
    """Rewrite every slot reference in a parsed gate to its qualified key.

    Returns the rewritten gate and no issues, or the gate unchanged and
    **every** issue (sorted by name) — an author fixing one should not have to
    rebuild to discover the next. Literals are never touched: the rewrite is
    over the parsed tree, so a string that happens to spell a slot name stays
    a string.
    """
    resolved: dict[str, str] = {}
    issues: list[GateRefIssue] = []
    for name in sorted(referenced_slots(node)):
        outcome = namespace.resolve(name)
        if isinstance(outcome, GateRefIssue):
            issues.append(outcome)
        else:
            resolved[name] = outcome
    if issues:
        return node, tuple(issues)
    return _rewrite(node, resolved.__getitem__), ()


def _operand(operand: Operand, rename: Callable[[str], str]) -> Operand:
    return Ref(name=rename(operand.name)) if isinstance(operand, Ref) else operand


def _rewrite(node: WhenNode, rename: Callable[[str], str]) -> WhenNode:
    if isinstance(node, BoolRef):
        return BoolRef(ref=Ref(name=rename(node.ref.name)))
    if isinstance(node, Compare):
        return Compare(
            left=_operand(node.left, rename), op=node.op, right=_operand(node.right, rename)
        )
    if isinstance(node, InSet):
        return InSet(operand=_operand(node.operand, rename), elements=node.elements)
    if isinstance(node, Not):
        return Not(item=_rewrite(node.item, rename))
    if isinstance(node, And):
        return And(items=tuple(_rewrite(item, rename) for item in node.items))
    return Or(items=tuple(_rewrite(item, rename) for item in node.items))

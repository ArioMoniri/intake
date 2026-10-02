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

**Ask order (INT-375).** files/13 §9.5 stratified acyclicity: "a gate on step
*S* may reference only slots owned by steps of strictly lower ``(priority,
order)``". The engine re-reads every gate on every turn and an unasked slot
reads Unknown, so a gate on a later slot does not drop its question — it passes
it over at its own place and asks it once the later slot is answered, out of
the frozen plan order. :func:`gates_reading_later_slots` finds every such read
over the merged, op-applied slot sequence; the compiler refuses each one
(``RefusalCode.GATE_READS_LATER_SLOT``). It never reorders anything.
"""

from __future__ import annotations

import enum
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Literal

from protocols.bindings import fhir_link_id
from protocols.dsl import Slot
from protocols.triage.expr import (
    And,
    BoolRef,
    Compare,
    InSet,
    Not,
    Operand,
    Or,
    Ref,
    WhenGrammarError,
    WhenNode,
    parse_when,
    referenced_slots,
)

__all__ = [
    "DETAIL_CLASS",
    "MUST_ASK_CLASS",
    "AskRank",
    "GateRefIssue",
    "GateRefProblem",
    "LaterSlotRead",
    "SlotNamespace",
    "ask_ranks",
    "gates_reading_later_slots",
    "qualify_gate",
]

type AskRank = tuple[int, int]
"""``(priority_class, order)`` — the engine's sort key less its id tiebreak,
which never decides between two slots because ``order`` is unique."""

# files/13 §9.1: the two priority classes a resolved slot takes today. The
# engine mints the same two from the same field (a clinician-marked must-ask is
# MUST_ASK, every other slot DETAIL — ``clinical_agent.plan.StepPriority``), and
# tests/engine/test_gate_ask_order_engine.py pins the two against each other.
MUST_ASK_CLASS = 5
DETAIL_CLASS = 7

type GateField = Literal["ask_if", "skip_if"]


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


@dataclass(frozen=True, slots=True)
class LaterSlotRead:
    """One gate that reads a slot not strictly before the slot it gates."""

    reader: str
    field: GateField
    read: str
    reader_rank: AskRank
    read_rank: AskRank

    def describe(self) -> str:
        """Ids and ranks only — never the gate text or a question."""
        if self.read == self.reader:
            return f"{self.field} on {self.reader} (ask rank {self.reader_rank}) reads itself"
        return (
            f"{self.field} on {self.reader} (ask rank {self.reader_rank}) reads "
            f"{self.read} (ask rank {self.read_rank}), which is not strictly before it"
        )


def ask_ranks(slots: Iterable[tuple[str, str, Slot]]) -> dict[str, AskRank]:
    """The files/13 §9.1 rank of every ``(section_id, key, slot)``, in merged order.

    ``order`` counts across sections, as the engine's plan does, so a slot in a
    later section is later whatever its index within that section.
    """
    ranks: dict[str, AskRank] = {}
    for section_id, key, slot in slots:
        ranks[fhir_link_id(section_id, key)] = (
            MUST_ASK_CLASS if slot.must_ask else DETAIL_CLASS,
            len(ranks),
        )
    return ranks


def gates_reading_later_slots(
    slots: Iterable[tuple[str, str, Slot]],
) -> tuple[LaterSlotRead, ...]:
    """Every ``ask_if``/``skip_if`` read of a slot whose rank is not strictly lower.

    ``slots`` is the resolved sequence — chain merged and every op applied —
    because that is the order the engine asks in. A reference that does not
    resolve to exactly one slot is INT-355's refusal and a gate outside the
    ``when`` grammar the emitter's; neither is judged here. Two spellings of one
    slot in one gate are one read. Reads come back in merged order of the gated
    slot, then field, then the slot read.
    """
    ordered = tuple(slots)
    ranks = ask_ranks(ordered)
    namespace = SlotNamespace((section_id, key) for section_id, key, _ in ordered)
    late: list[LaterSlotRead] = []
    for section_id, key, slot in ordered:
        reader = fhir_link_id(section_id, key)
        gates: tuple[tuple[GateField, str | None], ...] = (
            ("ask_if", slot.ask_if),
            ("skip_if", slot.skip_if),
        )
        for field_name, text in gates:
            if text is None:
                continue
            try:
                node = parse_when(text)
            except WhenGrammarError:
                continue
            reads = {namespace.resolve(name) for name in referenced_slots(node)}
            late.extend(
                LaterSlotRead(
                    reader=reader,
                    field=field_name,
                    read=read,
                    reader_rank=ranks[reader],
                    read_rank=ranks[read],
                )
                for read in sorted(r for r in reads if isinstance(r, str))
                if ranks[read] >= ranks[reader]
            )
    return tuple(late)


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

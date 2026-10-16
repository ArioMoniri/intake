"""CD-112's per-slot answer mappings: a hedge on a gating slot records an authored choice.

Clinical decision CD-112 (files/00_STATE.md D18; ``packages/protocols/decisions/
CD-112.yaml``, INT-519 items 2 and 3, applied by INT-546) decides that on two
base slots a review-queue cluster gates on, a hedged answer is never UNCLEAR:
an UNCLEAR slot reads Unknown, and an Unknown gate opens nothing (files/13
§9.2), so the item the gate guards would never be asked of a patient who is not
sure. Instead the hedge records the slot's authored non-committal choice, the
one the decision names (``records_choice``):

- ``pmh_fh_sh.immunosuppression`` (``gates[1].hedge_mapping``), where an
  answer still off-choice after the slot's follow-up records it too
  (``unresolved_after_follow_up``), so once the question has been asked the
  gate never reads Unknown;
- ``pmh_fh_sh.pregnancy_status`` (``gates[2].hedge_mapping``, the
  machine-readable form of CD-100 T4(c)), where an answer still off-choice
  after the follow-up is not mapped — CD-100 round 4 names it the remaining gap.

This module is the build of that and of nothing else:

- **The mappings are read from CD-112 through** :mod:`protocols.clinical_decisions`,
  which refuses a decision that does not hold its own provenance. No slot,
  choice or label is written here; a test pins that this module's source names
  none of the decision's choices and none of CD-04's surfaces.
- **The hedges are CD-04's ``*`` entries** — the :class:`AnswerStateTable`
  the onset anchor reads — and the mapping is read before them on its slot
  (CD-112 ``precedence``). A CD-04 entry that names a mapped slot itself would
  make that precedence a guess, so it is refused.
- **Each mapped choice opens its gate and the plain negative closes it.** The
  choice is a member of the slot's committed value set, is not the plain
  negative, is in the gate's ``opens_on``, and the gate's ``closes_on`` is the
  plain negative alone: a mapping that left the gate shut would undo the
  decision it builds.

**Nothing here echoes a value** (invariant 6): :class:`MappedAnswer`'s repr
names the slot, the label and the decision, never the choice it recorded.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from protocols.answer_states import (
    ANY_SLOT,
    AnswerStateTable,
    load_answer_state_table,
)
from protocols.clinical_decisions import (
    REGISTER_DIR,
    ClinicalDecision,
    DecisionStatus,
    load_decision,
)
from protocols.valuesets import ValueSetTable, load_committed_valuesets

__all__ = [
    "MAPPING_DECISION_ID",
    "AnswerMappingError",
    "AnswerMappingTable",
    "MappedAnswer",
    "MappingSource",
    "SlotChoiceMapping",
    "answer_mapping_table",
    "load_answer_mapping_table",
]

#: The register entry this module builds (files/00_STATE.md D18).
MAPPING_DECISION_ID: Final = "CD-112"
#: The answer state a mapping must never leave the slot in.
_NEVER_UNCLEAR: Final = "UNCLEAR"


class AnswerMappingError(ValueError):
    """A decision this module cannot follow exactly, or a table outside it."""


class MappingSource(enum.StrEnum):
    """What the mapped choice was recorded from (CD-112 ``record_label_by_source``)."""

    #: A CD-04 ``*`` entry read on the slot.
    HEDGE = "hedge"
    #: An answer still off-choice once the slot's follow-up is spent.
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class SlotChoiceMapping:
    """One slot's mapping: the choice a hedge records, and the label of each source."""

    slot: str
    valueset: str
    records_choice: str
    plain_negative: str
    labels: Mapping[MappingSource, str]

    @property
    def maps_unresolved(self) -> bool:
        """Whether an answer still off-choice after the follow-up is mapped too."""
        return MappingSource.UNRESOLVED in self.labels


@dataclass(frozen=True, repr=False)
class MappedAnswer:
    """The authored choice one answer to a mapped slot records, and why."""

    slot: str
    choice: str
    source: MappingSource
    label: str
    decision_id: str

    def __repr__(self) -> str:
        return (
            f"MappedAnswer(slot={self.slot!r}, label={self.label!r}, "
            f"decision_id={self.decision_id!r})"
        )

    def __str__(self) -> str:
        return self.__repr__()


@dataclass(frozen=True)
class AnswerMappingTable:
    """CD-112 as the runtime reads it: one mapping per slot, over CD-04's hedges."""

    decision_id: str
    mappings: Mapping[str, SlotChoiceMapping]
    hedges: AnswerStateTable

    @property
    def slots(self) -> frozenset[str]:
        """The step ids a mapping reads on."""
        return frozenset(self.mappings)

    def read(self, slot: str, text: str) -> MappedAnswer | None:
        """The choice ``text`` records on ``slot`` because it is a hedge, or ``None``.

        A CD-04 ``*`` entry read on the slot is a hedge; a plain answer — the
        plain negative included — reads as nothing here and binds as answered.
        """
        mapping = self.mappings.get(slot)
        if mapping is None or self.hedges.read(slot, text) is None:
            return None
        return self._mapped(mapping, MappingSource.HEDGE)

    def unresolved(self, slot: str) -> MappedAnswer | None:
        """The choice an answer still off-choice after the follow-up records, if decided."""
        mapping = self.mappings.get(slot)
        if mapping is None or not mapping.maps_unresolved:
            return None
        return self._mapped(mapping, MappingSource.UNRESOLVED)

    def _mapped(self, mapping: SlotChoiceMapping, source: MappingSource) -> MappedAnswer:
        return MappedAnswer(
            slot=mapping.slot,
            choice=mapping.records_choice,
            source=source,
            label=mapping.labels[source],
            decision_id=self.decision_id,
        )


def load_answer_mapping_table(directory: Path = REGISTER_DIR) -> AnswerMappingTable:
    """CD-112 from the committed register, over CD-04 and the committed value sets."""
    return answer_mapping_table(
        load_decision(directory / f"{MAPPING_DECISION_ID}.yaml"),
        load_answer_state_table(directory),
        load_committed_valuesets(),
    )


def answer_mapping_table(
    decision: ClinicalDecision, hedges: AnswerStateTable, valuesets: ValueSetTable
) -> AnswerMappingTable:
    """Build the table from one decision, refusing anything it cannot follow exactly."""
    where = decision.id
    if decision.status is not DecisionStatus.ACTIVE:
        raise AnswerMappingError(
            f"{where} is {decision.status.value}: a draft decision maps no answer"
        )
    mappings: dict[str, SlotChoiceMapping] = {}
    for gate in _list(decision.value.get("gates"), where, "gates"):
        if not isinstance(gate, Mapping):
            raise _refuse(where, "a gate is not a mapping")
        if "hedge_mapping" not in gate:
            continue
        mapping = _mapping(gate, valuesets, where)
        _require(mapping.slot not in mappings, where, "two mappings read on one slot")
        mappings[mapping.slot] = mapping
    _require(bool(mappings), where, "no gate carries a hedge mapping")
    _require_any_slot_hedges_only(hedges, frozenset(mappings), where)
    return AnswerMappingTable(decision_id=decision.id, mappings=mappings, hedges=hedges)


def _refuse(where: str, reason: str) -> AnswerMappingError:
    return AnswerMappingError(f"{where}: {reason}, which this build does not follow")


def _require(condition: bool, where: str, reason: str) -> None:
    if not condition:
        raise _refuse(where, reason)


def _list(node: object, where: str, what: str) -> Sequence[Any]:
    if not isinstance(node, list) or not node:
        raise _refuse(where, f"{what} is not a non-empty list")
    return node


def _text(node: object, where: str, what: str) -> str:
    if not isinstance(node, str) or not node.strip():
        raise _refuse(where, f"{what} is empty")
    return node


def _mapping(gate: Mapping[str, Any], valuesets: ValueSetTable, where: str) -> SlotChoiceMapping:
    """One gate's ``hedge_mapping``, checked against the gate and its value set."""
    _require(gate.get("status") == DecisionStatus.ACTIVE.value, where, "a mapped gate is draft")
    raw = gate["hedge_mapping"]
    if not isinstance(raw, Mapping):
        raise _refuse(where, "a hedge mapping is not a mapping")
    slot = _text(raw.get("slot"), where, "a mapping's slot")
    _require(slot.count(".") == 1, where, "a mapping's slot is not a <section>.<slot> step")
    valueset = _text(gate.get("valueset"), where, "a mapped gate's value set")
    members = valuesets.members(valueset)
    _require(members is not None, where, "a mapped gate's value set is not committed")
    choice = _text(raw.get("records_choice"), where, "a mapping's choice")
    negative = _text(raw.get("plain_negative_only"), where, "a mapping's plain negative")
    _require(choice in (members or ()), where, "a mapped choice is not a value-set member")
    _require(negative in (members or ()), where, "the plain negative is not a member")
    _require(choice != negative, where, "a hedge records the plain negative")
    never = raw.get("never")
    _require(
        isinstance(never, list) and _NEVER_UNCLEAR in never and negative in never,
        where,
        "a mapping may leave the slot UNCLEAR or record the plain negative",
    )
    _text(raw.get("precedence"), where, "a mapping's precedence")
    _require(
        choice in (gate.get("opens_on") or ()), where, "a mapped choice does not open its gate"
    )
    _require(
        gate.get("closes_on") == [negative], where, "the gate closes on more than the negative"
    )
    return SlotChoiceMapping(
        slot=slot,
        valueset=valueset,
        records_choice=choice,
        plain_negative=negative,
        labels=_labels(raw, where),
    )


def _labels(raw: Mapping[str, Any], where: str) -> Mapping[MappingSource, str]:
    """``record_label_by_source``: a hedge label always; an unresolved one iff decided."""
    labels = raw.get("record_label_by_source")
    if not isinstance(labels, Mapping):
        raise _refuse(where, "a mapping's labels are not a mapping")
    _require(
        set(labels) <= {source.value for source in MappingSource},
        where,
        "a mapping labels a source this build does not know",
    )
    _require(MappingSource.HEDGE.value in labels, where, "a mapping has no hedge label")
    decided = "unresolved_after_follow_up" in raw
    _require(
        (MappingSource.UNRESOLVED.value in labels) == decided,
        where,
        "an unresolved label without the unresolved decision, or the reverse",
    )
    return {
        MappingSource(source): _text(label, where, "a mapping's label")
        for source, label in labels.items()
    }


def _require_any_slot_hedges_only(
    hedges: AnswerStateTable, slots: frozenset[str], where: str
) -> None:
    """The mapping is read before CD-04's ``*`` entries: no entry may name the slot."""
    for entry in hedges.entries:
        named = sorted(entry.slots & slots)
        if named:
            raise AnswerMappingError(
                f"{where}: {hedges.decision_id} names the mapped slot(s) {', '.join(named)} "
                f"itself, so the mapping's precedence over its '{ANY_SLOT}' entries would be "
                "a guess; this build does not follow it"
            )

"""CD-112 at runtime: a hedge on a gating slot binds the authored choice (INT-546).

CD-112 (INT-519 items 2 and 3, D18-verified) decides that on
``pmh_fh_sh.immunosuppression`` and ``pmh_fh_sh.pregnancy_status`` a hedged
answer is never UNCLEAR: an UNCLEAR slot reads Unknown, and an Unknown gate
opens nothing (files/13 §9.2), so a review-queue cluster item gated on the slot
— ``bagisiklik_tedavisinde_enfeksiyon``, ``gebelik_dogrulandi`` — would never be
asked of a patient who is not sure. The table is
:class:`protocols.answer_mappings.AnswerMappingTable`, read from the decision;
:class:`SessionAnswerMappings` is one session's use of it:

- **A hedge binds the mapped choice at once** — read before CD-04's ``*``
  entries, and over any choice the model guessed (a hedged negative the model
  read as the negative is exactly what the mapping exists to stop).
- **An answer that binds no choice asks the slot's follow-up**, CD-04's once
  (``unclear_follow_up_tr_asks``, handed to the engine for the mapped slots);
  once it is spent, the slot records the mapped choice where CD-112 decides it
  (``mapped_from_unresolved``), and UNCLEAR where it does not — for pregnancy,
  CD-100 round 4's remaining gap.
- **A plain answer binds as answered.** The plain negative stays the patient's
  own answer, and closes the gate.

The record (:attr:`SessionAnswerMappings.record`) names the slot, the label and
the decision, never the choice (invariant 6). Nothing here produces a triage
level (invariant 1); no red-flag rule reads either slot.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field

from protocols.answer_mappings import AnswerMappingTable, MappedAnswer

__all__ = ["SessionAnswerMappings"]


@dataclass
class SessionAnswerMappings:
    """One session's CD-112 mappings and the record of what each recorded."""

    table: AnswerMappingTable
    #: ``{slot step id: the mapped answer the engine bound}``.
    record: dict[str, MappedAnswer] = field(default_factory=dict, init=False)

    @property
    def refs(self) -> frozenset[str]:
        """The step ids a mapping reads on."""
        return self.table.slots

    def follow_up_bounds(self, steps: Collection[str]) -> dict[str, int]:
        """CD-04's once for each mapped slot among ``steps``."""
        asks = self.table.hedges.unclear_follow_up_tr_asks
        return {ref: asks for ref in sorted(self.refs.intersection(steps))}

    def hedge(self, slot: str, text: str) -> MappedAnswer | None:
        """The choice ``text`` records on ``slot`` as a hedge, or ``None``."""
        return self.table.read(slot, text)

    def unresolved(self, slot: str) -> MappedAnswer | None:
        """The choice an answer still off-choice after the follow-up records, if decided."""
        return self.table.unresolved(slot)

    def note(self, mapped: MappedAnswer) -> None:
        """Record a mapped answer the engine bound."""
        self.record[mapped.slot] = mapped

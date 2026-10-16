"""What the verifier may read, decided from the served pack and nothing else.

ADR-036 narrows the council to a **verifier**: it re-reads an answer the
primary extraction has already bound, and only on two kinds of slot: those a
red-flag rule reads, and numeric ones. Everything else is out of scope, and
"out of scope" is a property of the *type*: a :class:`VerifiableRef` exists
only for a slot this module admitted, and the member output schema is built
from those refs alone. A model cannot answer about a slot that is not in its
schema, and a reading for one is dropped before adjudication sees it.

**Excluded even when the slot is red-flag or numeric:**

- a rule's ``tense_anchor``. The medical review's §4 is categorical: the
  council never fills, and never even reads, a RED tense anchor. The anchor is
  asked as a scripted closed choice and resolved against ``reference_time``.
- any slot delivered ``text_only``. That is how files/13 §13 marks
  safeguarding and screening content, and no extra model reads it (medical
  review §10).

Validated instruments are not slots at all (``ResolvedProtocol.instruments``
is a separate tuple), so their items have no ref this module could admit;
``tests/voice/test_council_scope.py`` asserts that rather than trusting it.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from protocols.compile.resolve import ResolvedProtocol
from protocols.types import Delivery, SlotType

from intake_voice_runtime.clinical_agent.plan import red_flag_slot_refs
from intake_voice_runtime.extraction.schema import NUMERIC_SLOT_TYPES

__all__ = ["ScopeExclusion", "VerifiableRef", "VerifierScope", "verifier_scope"]


class ScopeExclusion(enum.StrEnum):
    """Why a slot is not verifiable. A closed set, and PHI-free."""

    TENSE_ANCHOR = "tense_anchor"
    TEXT_ONLY = "text_only"
    NOT_RED_FLAG_OR_NUMERIC = "not_red_flag_or_numeric"


@dataclass(frozen=True, slots=True)
class VerifiableRef:
    """One slot the verifier may read. Constructed only by :func:`verifier_scope`."""

    ref: str
    slot_type: SlotType
    red_flag: bool
    numeric: bool


@dataclass(frozen=True, slots=True)
class VerifierScope:
    """The verifiable refs of one served pack, and why every other slot is not."""

    refs: Mapping[str, VerifiableRef]
    excluded: Mapping[str, ScopeExclusion]

    def __contains__(self, ref: object) -> bool:
        return ref in self.refs

    @property
    def ordered(self) -> tuple[str, ...]:
        """The verifiable refs, sorted — the order every schema and verdict uses."""
        return tuple(sorted(self.refs))

    def is_text_only(self, ref: str) -> bool:
        return self.excluded.get(ref) is ScopeExclusion.TEXT_ONLY


def verifier_scope(protocol: ResolvedProtocol) -> VerifierScope:
    """Admit red-flag and numeric slots; exclude anchors and ``text_only``."""
    when_refs, anchor_refs = red_flag_slot_refs(protocol)
    refs: dict[str, VerifiableRef] = {}
    excluded: dict[str, ScopeExclusion] = {}
    for section in protocol.sections:
        for resolved in section.slots:
            ref = f"{section.id}.{resolved.key}"
            slot_type = resolved.slot.type
            red_flag = ref in when_refs
            numeric = slot_type in NUMERIC_SLOT_TYPES
            if ref in anchor_refs:
                excluded[ref] = ScopeExclusion.TENSE_ANCHOR
            elif Delivery.TEXT_ONLY in (resolved.delivery, section.delivery):
                excluded[ref] = ScopeExclusion.TEXT_ONLY
            elif not (red_flag or numeric):
                excluded[ref] = ScopeExclusion.NOT_RED_FLAG_OR_NUMERIC
            else:
                refs[ref] = VerifiableRef(
                    ref=ref, slot_type=slot_type, red_flag=red_flag, numeric=numeric
                )
    return VerifierScope(refs=MappingProxyType(refs), excluded=MappingProxyType(excluded))

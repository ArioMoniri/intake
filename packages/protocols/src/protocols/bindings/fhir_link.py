"""FHIR ``linkId`` derivation (INT-041; files/12 §8).

One rule, and it is the whole module: ``fhir_link_id`` is **derived from the
slot id, never a counter**. A counter re-points an existing stored answer at
a different question the moment a slot is inserted, reordered or suppressed —
and nothing in the data makes that visible, because the answer still has a
linkId and the linkId still resolves. Derivation makes the identity a
property of the question rather than of its position.
"""

from __future__ import annotations

__all__ = ["fhir_link_id"]


def fhir_link_id(section_id: str, slot_key: str) -> str:
    """The stable ``Questionnaire.item.linkId`` for one slot.

    ``<section_id>.<slot_key>`` — the same pair the protocol DSL already uses
    to address a slot (files/12 §3.1 pointers ``/sections/<s>/slots/<k>``), so
    the linkId, the JSON pointer and the binding-table key are one identity
    expressed three ways rather than three identities kept in step by hand.
    """
    return f"{section_id}.{slot_key}"

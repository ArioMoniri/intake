"""INT-224 — the store declaration, derived rather than hand-maintained.

A Data safety / App Privacy declaration that disagrees with the data inventory
is a defect, and the way that defect normally arrives is a human filling in a
web form once and the schema moving afterwards. So the declaration is a
function of two inputs and nothing else:

    facts (ours, :mod:`intake_platform.store.facts`)
      × taxonomy (theirs, :mod:`intake_platform.store.taxonomy`)
      → declaration

Both directions are closed. A fact with no mapping raises
:class:`UnmappedFactError` — a new column or a new flow cannot slip into the
product without somebody deciding what the form calls it. And the taxonomy's
own booleans decide what "collected" and "shared" mean, because those are the
vendors' definitions and not ours.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from intake_platform.store.facts import DataFact, data_facts
from intake_platform.store.taxonomy import StoreTaxonomy, load_taxonomy, taxonomy_dir

__all__ = [
    "DeclarationRow",
    "UnmappedFactError",
    "build_declaration",
    "declaration_for_store",
]


class UnmappedFactError(Exception):
    """A fact the taxonomy says nothing about. Refused, never defaulted."""


@dataclass(frozen=True, order=True)
class DeclarationRow:
    """One row of the form, and the inventory facts behind it."""

    data_type: str
    label: str
    collected: bool
    shared: bool
    fact_ids: tuple[str, ...]


@dataclass
class _Bucket:
    collected: bool = False
    shared: bool = False
    fact_ids: set[str] = field(default_factory=set)


def build_declaration(
    taxonomy: StoreTaxonomy, facts: Sequence[DataFact]
) -> tuple[DeclarationRow, ...]:
    """Fold ``facts`` through ``taxonomy`` into the rows of one store's form."""
    merged: dict[str, _Bucket] = {}
    unmapped: list[str] = []
    for fact in facts:
        mapping = taxonomy.mapping_for(fact.category, fact.sharing)
        if mapping is None:
            unmapped.append(fact.fact_id)
            continue
        bucket = merged.setdefault(mapping.data_type, _Bucket())
        bucket.collected = bucket.collected or mapping.collected
        bucket.shared = bucket.shared or mapping.shared
        bucket.fact_ids.add(fact.fact_id)
    if unmapped:
        raise UnmappedFactError(
            "inventory facts not mapped by "
            f"{taxonomy.provenance.store}/{taxonomy.provenance.form}: {sorted(unmapped)}"
        )
    return tuple(
        sorted(
            DeclarationRow(
                data_type=data_type,
                label=taxonomy.data_types[data_type].label,
                collected=bucket.collected,
                shared=bucket.shared,
                fact_ids=tuple(sorted(bucket.fact_ids)),
            )
            for data_type, bucket in merged.items()
        )
    )


def declaration_for_store(repo: Path, store: str) -> tuple[DeclarationRow, ...]:
    """The declaration for one store from the committed snapshot.

    Raises :class:`~intake_platform.store.taxonomy.StoreTaxonomyMissingError`
    on today's tree, and will keep doing so until HB-A12 lands.
    """
    taxonomy = load_taxonomy(taxonomy_dir(repo) / f"{store}.yaml")
    return build_declaration(taxonomy, data_facts())

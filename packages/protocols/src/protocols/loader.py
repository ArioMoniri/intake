"""YAML loader and pack registry (INT-040).

The loader parses one pack file into :class:`protocols.pack.ProtocolPack`,
converting YAML and schema failures into :class:`PackSchemaError` so callers
see one error type at the boundary. The registry is the in-memory pack
index the validator resolves ``extends`` chains against (files/03 §6).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import yaml
from pydantic import ValidationError

from protocols.pack import ProtocolPack

__all__ = ["PackRegistry", "PackSchemaError", "check_rule_sources", "load_pack"]


#: The committed pack tree (packages/protocols/), the one the registry serves
#: from; derived from this file's location, as protocols.source_snapshots does.
_COMMITTED_PACK_TREE = Path(__file__).resolve().parents[2]


class PackSchemaError(ValueError):
    """A pack file that the DSL schema rejects (or a registry misuse)."""


def load_pack(path: Path) -> ProtocolPack:
    """Load and schema-validate one pack YAML file.

    Only ``kind: pack`` documents load here; ``life_threat_set`` documents
    are handled by the compiler slice (INT-041) and are refused so a chain
    pack can never impersonate the sibling set (files/12 §1).
    """
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise PackSchemaError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise PackSchemaError(f"{path}: a pack document must be a YAML mapping")
    kind = raw.get("kind")
    if kind != "pack":
        raise PackSchemaError(
            f"{path}: unsupported kind {kind!r} — the INT-040 loader accepts "
            "kind: pack only (files/12 §1)"
        )
    try:
        pack = ProtocolPack.model_validate(raw)
    except ValidationError as exc:
        raise PackSchemaError(f"{path}: {exc}") from exc
    check_rule_sources(path, pack, committed=path.resolve().is_relative_to(_COMMITTED_PACK_TREE))
    return pack


def check_rule_sources(path: Path, pack: ProtocolPack, *, committed: bool) -> None:
    """A chain pack's cited source holds against its committed snapshot (INT-619).

    ``dsl.SourceBlock`` requires a red-flag rule's quote to appear verbatim in a
    committed snapshot, and promises that a chain pack's loader runs the same
    check as the life-threat loader once a chain-pack rule cites one. base.intake
    is the first that does. A source block must name its ``quote_snapshot``, and
    :func:`protocols.source_snapshots.source_snapshot_problem` must find nothing
    wrong with it, or the pack does not load: a citation the snapshot does not
    hold is refused, never repaired. A draft rule carries no source block (the
    DSL refuses one), so it is not reached here.

    The snapshot is mandatory for a ``committed`` pack, one under
    ``packages/protocols/``, the tree the registry serves from. A SENTETİK
    test pack elsewhere may cite a source without one; when it names one,
    the same check runs, with the ``tests/fixtures/protocols/sources/``
    prefix admitted, exactly as the life-threat loader's
    ``allow_fixture_snapshots`` flag does for test sets.
    """
    # Imported here: protocols.source_snapshots reaches protocols.validator,
    # which imports this module for PackRegistry.
    from protocols.source_snapshots import source_snapshot_problem  # noqa: PLC0415

    for rule in pack.red_flags:
        source = rule.source
        if source is None or (source.quote_snapshot is None and not committed):
            continue
        if source.quote_snapshot is None:
            raise PackSchemaError(
                f"{path}: {rule.id}: a cited source names its committed snapshot "
                "(quote_snapshot) under packages/protocols/sources/ "
                "(files/04 §8.1 rule 3; files/12 §2.5)"
            )
        problem = source_snapshot_problem(
            quote_snapshot=source.quote_snapshot,
            guideline_id=source.guideline_id,
            quote=source.quote,
            url=source.url,
            retrieved_on=source.retrieved_on,
            version_or_date=source.version_or_date,
            allow_fixture_snapshots=not committed,
        )
        if problem is not None:
            raise PackSchemaError(
                f"{path}: {rule.id}: {problem} (files/04 §8.1 rule 3 — a citation "
                "the snapshot does not hold is refused, never repaired)"
            )


class PackRegistry:
    """Packs by id, duplicate-rejecting (pack ids are unique by construction
    — files/12 §3.3 relies on that as the total tiebreaker)."""

    def __init__(self) -> None:
        self._packs: dict[str, ProtocolPack] = {}

    def add(self, pack: ProtocolPack) -> None:
        if pack.id in self._packs:
            raise PackSchemaError(f"duplicate pack id {pack.id!r} (files/12 §3.3)")
        self._packs[pack.id] = pack

    def get(self, pack_id: str) -> ProtocolPack:
        return self._packs[pack_id]

    def maybe(self, pack_id: str) -> ProtocolPack | None:
        return self._packs.get(pack_id)

    def __iter__(self) -> Iterator[ProtocolPack]:
        return iter(self._packs.values())

    def __len__(self) -> int:
        return len(self._packs)

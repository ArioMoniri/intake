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

__all__ = ["PackRegistry", "PackSchemaError", "load_pack"]


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
        return ProtocolPack.model_validate(raw)
    except ValidationError as exc:
        raise PackSchemaError(f"{path}: {exc}") from exc


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

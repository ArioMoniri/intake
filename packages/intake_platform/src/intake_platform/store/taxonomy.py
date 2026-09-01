"""INT-224 — the vendors' published form taxonomies, behind a committed snapshot.

Apple's App Privacy data types, Google Play's Data safety categories, the Play
Health apps policy and the IARC questionnaire are **published artefacts that
move**. Writing one down from memory is the same class of error as inventing a
clinical threshold: it reads as authoritative to every later reader, and there
is no diff that makes it look wrong.

So this loader refuses to work from anything but a file that carries, together:

- ``source_url`` and ``retrieved_on`` — where and when the words were taken;
- ``snapshot`` — a **verbatim copy of the published text**, committed beside
  the machine-readable file;
- ``snapshot_sha256`` — which binds the two, so the taxonomy cannot outlive the
  text it was read from.

Nothing is committed yet (HUMAN_BLOCKERS.md **HB-A12**), so
:func:`load_taxonomy` raises today and every label path fails closed behind it.
That is the whole design: the derivation is finished and exercised, and the
only thing missing is the vendors' own words, missing loudly.

The mapping section is the seam between their vocabulary and ours: each row
takes one ``(category, sharing)`` pair from
:mod:`intake_platform.store.facts` and says which of *their* data types it is,
and whether their form counts it as collected and as shared. Those two
booleans are the vendor's definition applied to our fact — the determination
counsel owes (HB-L21) — and neither is defaulted here.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

import yaml

from intake_platform.store.facts import Sharing

__all__ = [
    "PROVENANCE_FIELDS",
    "StoreDataType",
    "StoreTaxonomy",
    "StoreTaxonomyError",
    "StoreTaxonomyInvalidError",
    "StoreTaxonomyMissingError",
    "TaxonomyMapping",
    "TaxonomyProvenance",
    "load_taxonomy",
    "taxonomy_dir",
]

PROVENANCE_FIELDS: Final[tuple[str, ...]] = (
    "store",
    "form",
    "source_url",
    "retrieved_on",
    "snapshot",
    "snapshot_sha256",
)

_MISSING_HINT = (
    "no committed store-form taxonomy at {path} — Apple's App Privacy types, Google "
    "Play's Data safety categories, the Play Health apps policy and the IARC "
    "questionnaire are published artefacts that move, and none of them may be written "
    "from memory. A dated verbatim snapshot is owed by HUMAN_BLOCKERS.md HB-A12; until "
    "it lands nothing renders."
)


class StoreTaxonomyError(Exception):
    """Base for taxonomy-loading failures."""


class StoreTaxonomyMissingError(StoreTaxonomyError):
    """No snapshot has been committed. Fail closed."""


class StoreTaxonomyInvalidError(StoreTaxonomyError):
    """A snapshot exists but breaks the provenance or mapping contract."""


@dataclass(frozen=True)
class TaxonomyProvenance:
    store: str
    form: str
    source_url: str
    retrieved_on: date
    snapshot: str
    snapshot_sha256: str


@dataclass(frozen=True)
class StoreDataType:
    id: str
    label: str


@dataclass(frozen=True)
class TaxonomyMapping:
    """One of our facts, expressed in the vendor's vocabulary."""

    category: str
    sharing: Sharing
    data_type: str
    collected: bool
    shared: bool


@dataclass(frozen=True)
class StoreTaxonomy:
    provenance: TaxonomyProvenance
    text_hash: str
    path: Path
    data_types: Mapping[str, StoreDataType]
    mappings: tuple[TaxonomyMapping, ...]

    def mapping_for(self, category: str, sharing: Sharing) -> TaxonomyMapping | None:
        for row in self.mappings:
            if row.category == category and row.sharing is sharing:
                return row
        return None


def taxonomy_dir(repo: Path) -> Path:
    """Where a committed snapshot belongs — inside ``docs/legal`` so invariant
    18's "legal texts render only from docs/legal" and invariant 20's claims
    gate both already reach it."""
    return repo / "docs" / "legal" / "store" / "taxonomy"


def _require_str(body: Mapping[str, Any], key: str, path: Path) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value.strip():
        raise StoreTaxonomyInvalidError(f"{path}: provenance field {key!r} is absent or empty")
    return value.strip()


def _parse_provenance(raw: Any, path: Path) -> TaxonomyProvenance:
    if not isinstance(raw, dict):
        raise StoreTaxonomyInvalidError(f"{path}: no provenance block")
    values = {field: _require_str(raw, field, path) for field in PROVENANCE_FIELDS}
    try:
        retrieved_on = date.fromisoformat(values["retrieved_on"])
    except ValueError as exc:
        raise StoreTaxonomyInvalidError(
            f"{path}: provenance field 'retrieved_on' is not an ISO date — an undated "
            "snapshot of a moving policy is not a snapshot"
        ) from exc
    if len(values["snapshot_sha256"]) != 64:
        raise StoreTaxonomyInvalidError(
            f"{path}: provenance field 'snapshot_sha256' is not a sha256 digest"
        )
    return TaxonomyProvenance(
        store=values["store"],
        form=values["form"],
        source_url=values["source_url"],
        retrieved_on=retrieved_on,
        snapshot=values["snapshot"],
        snapshot_sha256=values["snapshot_sha256"],
    )


def _verify_snapshot(provenance: TaxonomyProvenance, path: Path) -> None:
    snapshot_path = path.parent / provenance.snapshot
    if not snapshot_path.is_file():
        raise StoreTaxonomyInvalidError(
            f"{path}: the verbatim snapshot {provenance.snapshot!r} is not committed beside it"
        )
    digest = hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
    if digest != provenance.snapshot_sha256:
        raise StoreTaxonomyInvalidError(
            f"{path}: snapshot_sha256 does not match {provenance.snapshot!r} — the taxonomy "
            "has outlived the text it was read from"
        )


def _parse_data_types(raw: Any, path: Path) -> Mapping[str, StoreDataType]:
    if not isinstance(raw, list) or not raw:
        raise StoreTaxonomyInvalidError(f"{path}: data_types is absent or empty")
    types: dict[str, StoreDataType] = {}
    for entry in raw:
        if not isinstance(entry, dict):
            raise StoreTaxonomyInvalidError(f"{path}: a data_types entry is not a mapping")
        type_id = entry.get("id")
        label = entry.get("label")
        if not isinstance(type_id, str) or not type_id.strip():
            raise StoreTaxonomyInvalidError(f"{path}: a data_types entry has no id")
        if not isinstance(label, str) or not label.strip():
            raise StoreTaxonomyInvalidError(f"{path}: data type {type_id!r} has no label")
        types[type_id] = StoreDataType(id=type_id, label=label)
    return MappingProxyType(types)


def _parse_mappings(
    raw: Any, data_types: Mapping[str, StoreDataType], path: Path
) -> tuple[TaxonomyMapping, ...]:
    if not isinstance(raw, list) or not raw:
        raise StoreTaxonomyInvalidError(f"{path}: mapping is absent or empty")
    rows: list[TaxonomyMapping] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise StoreTaxonomyInvalidError(f"{path}: a mapping entry is not a mapping")
        category = entry.get("category")
        if not isinstance(category, str) or not category.strip():
            raise StoreTaxonomyInvalidError(f"{path}: a mapping entry has no category")
        raw_sharing = entry.get("sharing")
        try:
            sharing = Sharing(raw_sharing if isinstance(raw_sharing, str) else "")
        except ValueError as exc:
            raise StoreTaxonomyInvalidError(
                f"{path}: mapping for {category!r} has an unknown sharing value"
            ) from exc
        data_type = entry.get("data_type")
        if not isinstance(data_type, str) or data_type not in data_types:
            raise StoreTaxonomyInvalidError(
                f"{path}: mapping for {category!r} names a data_type the snapshot does not list"
            )
        collected = entry.get("collected")
        shared = entry.get("shared")
        if not isinstance(collected, bool) or not isinstance(shared, bool):
            raise StoreTaxonomyInvalidError(
                f"{path}: mapping for {category!r} must state 'collected' and 'shared' as "
                "booleans — the vendor's definition applied to our fact, never defaulted"
            )
        rows.append(
            TaxonomyMapping(
                category=category,
                sharing=sharing,
                data_type=data_type,
                collected=collected,
                shared=shared,
            )
        )
    return tuple(rows)


def load_taxonomy(path: Path) -> StoreTaxonomy:
    """One store's form taxonomy, or a fail-closed error."""
    try:
        raw_bytes = path.read_bytes()
    except FileNotFoundError as exc:
        raise StoreTaxonomyMissingError(_MISSING_HINT.format(path=path)) from exc
    try:
        body = yaml.safe_load(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise StoreTaxonomyInvalidError(f"{path}: not readable as UTF-8 YAML") from exc
    if not isinstance(body, dict):
        raise StoreTaxonomyInvalidError(f"{path}: top level is not a mapping")
    provenance = _parse_provenance(body.get("provenance"), path)
    _verify_snapshot(provenance, path)
    data_types = _parse_data_types(body.get("data_types"), path)
    mappings = _parse_mappings(body.get("mapping"), data_types, path)
    return StoreTaxonomy(
        provenance=provenance,
        text_hash=hashlib.sha256(raw_bytes).hexdigest(),
        path=path,
        data_types=data_types,
        mappings=mappings,
    )

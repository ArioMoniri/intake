"""INT-495 — the App Store creative-asset manifest and its file checks.

``docs/store/asc/assets.yaml`` states, per App Store slot (the product page
header and the iPhone screenshot groups), the sizes Apple's pages gave on
2026-10-16 and the files that fill it. This module loads that manifest and
checks a file against its slot: PNG, RGB with no alpha, one of the slot's exact
sizes, and a file name that does not say it is a development or demo capture.

It reads only the PNG header and chunk types; it never decodes pixels and never
touches the network. Uploading is INT-502's step (GitHub #856).
"""

from __future__ import annotations

import re
import struct
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import yaml

__all__ = [
    "MANIFEST",
    "AssetEntry",
    "AssetManifest",
    "ManifestError",
    "check_file",
    "load_manifest",
]

REPO: Final[Path] = Path(__file__).resolve().parents[2]
MANIFEST: Final[Path] = REPO / "docs" / "store" / "asc" / "assets.yaml"

_PNG_SIGNATURE: Final[bytes] = b"\x89PNG\r\n\x1a\n"
#: PNG colour types that carry an alpha channel (greyscale+alpha, RGBA).
_ALPHA_COLOUR_TYPES: Final[frozenset[int]] = frozenset({4, 6})
#: A production asset is a release-build capture; a name that says otherwise
#: is refused before anyone has to look at the picture.
_BANNED_NAME: Final[re.Pattern[str]] = re.compile(
    r"(?i)deneme|demo|mock|test|sample|expo[-_ ]?go|dev[-_]?client|fixture"
)


class ManifestError(ValueError):
    """The manifest breaks its own contract."""


@dataclass(frozen=True)
class AssetEntry:
    asset_id: str
    placement_type: str
    category: str
    placement_group: str | None
    sizes: tuple[tuple[int, int], ...]
    max_per_locale: int
    required: bool
    files: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True)
class AssetManifest:
    retrieved_on: str
    entries: tuple[AssetEntry, ...]


def _entry(raw: Mapping[str, Any]) -> AssetEntry:
    try:
        sizes = tuple((int(w), int(h)) for w, h in raw["sizes"])
        files = {str(k): tuple(str(f) for f in v) for k, v in raw["files"].items()}
        entry = AssetEntry(
            asset_id=str(raw["id"]),
            placement_type=str(raw["placement_type"]),
            category=str(raw["category"]),
            placement_group=None if raw["placement_group"] is None else str(raw["placement_group"]),
            sizes=sizes,
            max_per_locale=int(raw["max_per_locale"]),
            required=bool(raw["required"]),
            files=files,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ManifestError(f"asset entry {raw.get('id', '?')!r} is malformed") from exc
    if not entry.sizes:
        raise ManifestError(f"{entry.asset_id}: no size")
    for locale, paths in entry.files.items():
        if len(paths) > entry.max_per_locale:
            raise ManifestError(f"{entry.asset_id}[{locale}]: more than {entry.max_per_locale}")
    return entry


def load_manifest(path: Path) -> AssetManifest:
    body = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(body, Mapping) or not isinstance(body.get("assets"), list):
        raise ManifestError(f"{path}: no assets list")
    return AssetManifest(
        retrieved_on=str(body["retrieved_on"]),
        entries=tuple(_entry(raw) for raw in body["assets"]),
    )


def _png_facts(data: bytes) -> tuple[int, int, int, bool] | None:
    """(width, height, colour type, has tRNS) from the header, or None."""
    if not data.startswith(_PNG_SIGNATURE) or data[12:16] != b"IHDR":
        return None
    width, height, _depth, colour = struct.unpack(">IIBB", data[16:26])
    offset, transparency = 8, False
    while offset + 8 <= len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        kind = data[offset + 4 : offset + 8]
        transparency = transparency or kind == b"tRNS"
        if kind == b"IEND":
            break
        offset += 12 + length
    return width, height, colour, transparency


def check_file(path: Path, entry: AssetEntry) -> tuple[str, ...]:
    """Every reason ``path`` cannot fill ``entry``'s slot, or ``()``."""
    problems: list[str] = []
    if _BANNED_NAME.search(path.name):
        problems.append(f"{path.name}: the file name marks a non-production capture")
    if not path.is_file():
        return (*problems, f"{path}: no such file")
    facts = _png_facts(path.read_bytes())
    if facts is None:
        return (*problems, f"{path.name}: not a PNG (this pipeline takes PNG only)")
    width, height, colour, transparency = facts
    if colour in _ALPHA_COLOUR_TYPES or transparency:
        problems.append(f"{path.name}: has an alpha channel or transparency")
    if (width, height) not in entry.sizes:
        problems.append(f"{path.name}: size {width}x{height} is not one of {list(entry.sizes)}")
    return tuple(problems)

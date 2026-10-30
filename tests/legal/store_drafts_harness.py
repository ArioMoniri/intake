"""Shared helpers for the INT-482 store suites — uniquely named so test modules
import it directly (the legal_harness precedent).

The drafts under ``docs/legal/drafts/store`` are read here and only here, from
``tests/``: no code under packages/, services/, apps/ or infra/ may name that
tree (tests/legal/test_legal_drafts.py), and nothing here is a loader — the
promotion dry-run copies each draft into a temporary tree at its served name
and lets the real loaders read it there.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[2]
DRAFTS = REPO / "docs" / "legal" / "drafts" / "store"
#: INT-495 promoted the App Store listing and submission to their served paths;
#: the Play copy stays a draft (Play is deferred, INT-496).
SERVED_LISTING = REPO / "docs" / "legal" / "store" / "listing"
SERVED_SUBMISSION = REPO / "docs" / "legal" / "store" / "submission" / "app-store.yaml"

#: GitHub #825: the store name. INT-420 (#729) renames the app itself.
APP_NAME = "Önvizit"
LOCALES = ("tr", "en-US")
STORES = ("app-store", "google-play")
BANNER = (
    "TASLAK — hukuk danışmanı onayı gerektirir / DRAFT — requires counsel sign-off; not in force"
)
#: Invariant 20 at the tier a store listing gets: every group, bare percentages included.
STRICT = ("performance", "satisfaction", "bare_percentage")


def listing_source(store: str, locale: str) -> Path:
    """The served listing where it has been promoted, else its draft."""
    served = SERVED_LISTING / f"{store}.{locale}.yaml"
    return served if served.exists() else DRAFTS / f"{store}.{locale}.draft.yaml"


def submission_source() -> Path:
    if SERVED_SUBMISSION.exists():
        return SERVED_SUBMISSION
    return DRAFTS / "app-store.submission.draft.yaml"


def store_texts() -> list[Path]:
    """Every store artefact under docs/legal: the drafts and the served files."""
    served = [p for p in (SERVED_LISTING, SERVED_SUBMISSION.parent) if p.is_dir()]
    return sorted([*DRAFTS.iterdir(), *(f for d in served for f in d.glob("*.yaml"))])


def body(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict), path
    return loaded


def lines(text: str) -> list[str]:
    """The non-empty lines of a field, bullets stripped."""
    return [line.removeprefix("• ").strip() for line in text.splitlines() if line.strip()]


def cited_path(source: str) -> Path:
    """The repo file a ``source`` string starts with."""
    return REPO / source.split(" ", 1)[0].rstrip(";:,")


def promote(tmp: Path, *, stores: tuple[str, ...] = STORES) -> Path:
    """The promotion PR, in a temporary tree: drafts at their served names."""
    listing = tmp / "docs" / "legal" / "store" / "listing"
    listing.mkdir(parents=True)
    for store in stores:
        for locale in LOCALES:
            shutil.copy(listing_source(store, locale), listing / f"{store}.{locale}.yaml")
    submission = tmp / "docs" / "legal" / "store" / "submission"
    submission.mkdir(parents=True)
    shutil.copy(submission_source(), submission / "app-store.yaml")
    return tmp

"""INT-134 — the loaded, versioned branch taxonomy the API serves.

The source of truth is ``packages/protocols/taxonomy/branches.yaml``
(files/09 §1); loading and cross-checking belong to
:mod:`protocols.taxonomy` (INT-042) and are reused, never re-implemented.
The feed adds exactly one thing: a VERSION — the sha256 of the served
file's bytes — so a client can cache last-good honestly and detect change
without diffing 92 branches.

No FastAPI in this module: the router lives in taxonomy_routes.py, the
lazy per-app cache on :class:`intake_api.state.ApiState`.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

from protocols.taxonomy import Taxonomy, TaxonomyError, load_taxonomy

__all__ = ["LoadedTaxonomy", "load_taxonomy_feed"]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LoadedTaxonomy:
    """The validated taxonomy plus the content hash the feed serves."""

    version: str
    taxonomy: Taxonomy


def load_taxonomy_feed(path: Path) -> LoadedTaxonomy | None:
    """Load and hash the taxonomy, or ``None`` when it cannot be served —
    the callers turn ``None`` into a 503 (fail closed, never an empty
    list). The log line carries the path and the failure class only: the
    file is a committed artefact, so this is not PHI (invariant 6), but the
    exception text is still dropped to keep the rule mechanical."""
    try:
        raw = path.read_bytes()
        taxonomy = load_taxonomy(path)
    except (OSError, TaxonomyError) as exc:
        logger.error("taxonomy feed unavailable: %s (%s)", path, type(exc).__name__)
        return None
    return LoadedTaxonomy(version=hashlib.sha256(raw).hexdigest(), taxonomy=taxonomy)

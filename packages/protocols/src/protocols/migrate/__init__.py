"""INT-297 — the migration that turned five ``*_tr`` fields into locale maps.

It ships with the package rather than living as a throwaway script for one
reason: the acceptance requires the rewrite to be **idempotent** and the result
to be **byte-identical for Turkish**, and both are properties a test has to be
able to import and re-run. A migration that ran once, on one laptop, and left
only its diff behind cannot be re-checked by anybody.

* :mod:`~protocols.migrate.locale_maps` rewrites a tree, in both directions.
* :mod:`~protocols.migrate.tr_baseline` extracts what a Turkish patient hears,
  from either shape, so the same code produced the committed baseline before the
  migration and re-derives it after.
"""

from __future__ import annotations

from protocols.migrate.locale_maps import (
    MIGRATED_FIELDS,
    migrate_document,
    migrate_tree,
    unmigrate_document,
)
from protocols.migrate.tr_baseline import authored_baseline

__all__ = [
    "MIGRATED_FIELDS",
    "authored_baseline",
    "migrate_document",
    "migrate_tree",
    "unmigrate_document",
]

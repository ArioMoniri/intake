#!/usr/bin/env python3
"""INT-297 — run the ``*_tr`` → locale-map migration over a pack tree.

The migration itself lives in :mod:`protocols.migrate.locale_maps`, inside the
package, so it is type-checked, importable and re-runnable by the tests that
assert it is idempotent and that it changed no Turkish. This file is the
committed entry point the migration was actually performed with:

    uv run python scripts/protocols/migrate_locale_maps.py \\
        packages/protocols files/protocols tests/fixtures/protocols

    # and afterwards, to prove there is nothing left to do:
    uv run python scripts/protocols/migrate_locale_maps.py --check packages/protocols

``--check`` exits non-zero if any file would still change, which is the shape a
CI gate wants; without it the files are rewritten in place. Re-running either
form is safe: the rewrite recognises an already-migrated field and leaves it
byte for byte as it found it.

``--baseline`` re-derives the content baseline — every one of the five fields in
every document, with its ``expand_tr`` expansion — from whichever shape the tree
is currently in. That is how the committed
``tests/fixtures/protocols/int297_tr_content_baseline.json`` was produced before
the migration, and how ``tests/protocols/test_migration_is_identity_for_tr.py``
re-derives it after.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages" / "protocols" / "src"))

from protocols.migrate.locale_maps import migrate_file, pending  # noqa: E402
from protocols.migrate.tr_baseline import authored_baseline  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tree", type=Path, nargs="+", help="directories to walk")
    parser.add_argument("--check", action="store_true", help="report, do not write")
    parser.add_argument("--baseline", type=Path, help="write the content baseline here instead")
    args = parser.parse_args(argv)

    if args.baseline is not None:
        payload: dict[str, object] = {}
        for tree in args.tree:
            payload.update(authored_baseline(tree, root=REPO_ROOT))
        args.baseline.parent.mkdir(parents=True, exist_ok=True)
        args.baseline.write_text(
            json.dumps(dict(sorted(payload.items())), indent=2, sort_keys=True, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
        print(f"{len(payload)} documents -> {args.baseline}")
        return 0

    outstanding: list[Path] = []
    changed: list[Path] = []
    for tree in args.tree:
        for path in sorted(tree.rglob("*.yaml")):
            if args.check:
                if pending(path):
                    outstanding.append(path)
            elif migrate_file(path):
                changed.append(path)
    if args.check:
        for path in outstanding:
            print(f"would migrate: {path}")
        print(f"{len(outstanding)} file(s) still to migrate")
        return 1 if outstanding else 0
    for path in changed:
        print(f"migrated: {path}")
    print(f"{len(changed)} file(s) migrated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

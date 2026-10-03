"""Render ``apps/mobile/store.config.json`` from the served store copy (INT-482).

The EAS Metadata file is never written by hand. This script is the only writer,
and it reads only the served, hash-bound files under ``docs/legal/store``
(:func:`intake_platform.store.eas_metadata.render_for_repo`).

Exit codes:

- ``0`` written, or ``--check`` found the committed file equal to the render;
- ``1`` ``--check`` found drift, or a ``store.config.json`` exists with no
  served listing behind it;
- ``2`` a served artefact was refused (a link in copy, a claim, a field limit);
- ``3`` nothing is served yet (HB-L21): the fail-closed state, nothing written.

Every field the render leaves out is printed as ``blocked: <reason>`` with the
blocker that owes it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from intake_platform.legal.documents import LegalDocumentError
from intake_platform.store.eas_metadata import (
    StoreConfigError,
    render_for_repo,
    serialise,
    store_config_path,
)
from intake_platform.store.listing import StoreListingError, StoreListingMissingError

REPO = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--check", action="store_true", help="compare, do not write")
    args = parser.parse_args(argv)
    target = store_config_path(args.repo)
    try:
        result = render_for_repo(args.repo)
    except StoreListingMissingError as exc:
        if target.exists():
            print(f"render_store_config: FAIL — {target} exists with no served listing")
            return 1
        print(f"render_store_config: BLOCKED — {exc}")
        return 3
    except (StoreConfigError, StoreListingError, LegalDocumentError) as exc:
        print(f"render_store_config: REFUSED — {exc}")
        return 2
    for path, digest in sorted(result.sources.items()):
        print(f"source: {path} sha256={digest}")
    for reason in result.blocked:
        print(f"blocked: {reason}")
    text = serialise(result.config)
    if args.check:
        current = target.read_text(encoding="utf-8") if target.exists() else ""
        if current != text:
            print(f"render_store_config: DRIFT — {target} differs from the render")
            return 1
        print(f"render_store_config: OK — {target} matches the render")
        return 0
    target.write_text(text, encoding="utf-8")
    print(f"render_store_config: wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

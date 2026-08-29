"""INT-206 — `python -m intake_platform.ci`, the same entry point `make ci-policy` calls."""

from __future__ import annotations

import sys

from intake_platform.ci.cli import main

__all__ = ["main"]

if __name__ == "__main__":  # pragma: no cover - exercised through cli.main
    sys.exit(main())

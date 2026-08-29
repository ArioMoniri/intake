"""INT-205 — `python -m intake_platform.siem`, the same CLI the scripts call."""

from __future__ import annotations

import sys

from intake_platform.siem.cli import main

__all__ = ["main"]

if __name__ == "__main__":  # pragma: no cover - exercised through cli.main
    sys.exit(main())

"""INT-320 — the embed suite reuses the services/api unit-lane harness
(tests/api/api_harness.py). Like tests/admin and tests/experience, the shim
puts that directory on sys.path so ``api_harness`` imports directly rather than
duplicating the harness."""

from __future__ import annotations

import sys
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parents[1]
if str(_TESTS_DIR / "api") not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR / "api"))

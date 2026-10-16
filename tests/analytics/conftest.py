"""Fixture wiring for the INT-490 research analytics suite.

The unit-lane DB helpers live in ``tests/api/api_harness.py`` and the admin
harness in ``tests/admin``; both directories go on ``sys.path`` rather than
being copied, the same pattern tests/admin and tests/research use.
"""

from __future__ import annotations

import sys
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parents[1]
for _directory in (_TESTS_DIR / "api", _TESTS_DIR / "admin", Path(__file__).resolve().parent):
    if str(_directory) not in sys.path:
        sys.path.insert(0, str(_directory))

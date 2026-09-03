"""Fixture wiring for the admin shell suite (INT-180).

The services/api unit-lane harness lives in ``tests/api/api_harness.py``; the
established pattern in this repo (tests/legal, tests/research, tests/clinician)
is to put that directory on ``sys.path`` rather than duplicate the harness,
because a second harness drifts from the first and then proves nothing about
the app the service actually builds.
"""

from __future__ import annotations

import sys
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parents[1]
if str(_TESTS_DIR / "api") not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR / "api"))

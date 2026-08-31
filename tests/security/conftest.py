"""Fixture wiring for the security lane's API-backed suites (INT-016).

The access-log view is reached over the real app, so this file borrows the
INT-197 harness that already builds one (``tests/api/api_harness.py``) rather
than growing a second, drifting copy of the same wiring — the same shim
``tests/legal/conftest.py`` uses, for the same reason.

The path shim must run before the harness import, hence the split import
block and its E402 waivers.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

import pytest  # noqa: E402
from api_harness import ADMIN_TOKEN, PATIENT_TOKEN, ApiHarness, build_harness  # noqa: E402


@pytest.fixture()
def api(tmp_path: Path) -> Iterator[ApiHarness]:
    """The INT-197 dev-tier app over SQLite: seeded dev patient, seeded
    ``core`` grant, a real hash-chained audit store behind it."""
    yield from build_harness(tmp_path, token_patient=PATIENT_TOKEN, token_admin=ADMIN_TOKEN)

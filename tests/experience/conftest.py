"""Fixture wiring for the INT-240 experience lane.

Reuses the services/api unit-lane harness (tests/api/api_harness.py) and the
consent-text fixtures (tests/legal/legal_harness.py) through the same explicit
sys.path shim legal_harness itself uses — the harness modules are uniquely
named precisely so sibling suites can import them directly.

The harness here is built WITH consent texts on disk, because ``satisfaction``
is not one of dev_fixture.DEV_CONSENT_SCOPES: a CSAT route must be reachable
only after a hash-bound grant, and the default (ungranted) state is itself
under test.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parents[1]
for _sibling in ("api", "legal"):
    if str(_TESTS_DIR / _sibling) not in sys.path:
        sys.path.insert(0, str(_TESTS_DIR / _sibling))

from api_harness import ADMIN_TOKEN, PATIENT_TOKEN, ApiHarness, build_harness  # noqa: E402
from legal_harness import write_all_consent_texts  # noqa: E402


@pytest.fixture()
def harness(tmp_path: Path) -> Iterator[ApiHarness]:
    legal_root = write_all_consent_texts(tmp_path / "legal")
    yield from build_harness(
        tmp_path,
        token_patient=PATIENT_TOKEN,
        token_admin=ADMIN_TOKEN,
        legal_root=legal_root,
    )

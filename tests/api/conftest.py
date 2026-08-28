"""Fixture wiring for the services/api unit lane (INT-197). The harness
itself lives in api_harness.py (a uniquely named module, so tests can import
it directly without relying on conftest's special import handling)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from api_harness import ADMIN_TOKEN, PATIENT_TOKEN, ApiHarness, build_harness


@pytest.fixture()
def harness(tmp_path: Path) -> Iterator[ApiHarness]:
    yield from build_harness(tmp_path, token_patient=PATIENT_TOKEN, token_admin=ADMIN_TOKEN)


@pytest.fixture()
def unconfigured_harness(tmp_path: Path) -> Iterator[ApiHarness]:
    """Tokens absent from the environment — the dev tier must fail closed."""
    yield from build_harness(tmp_path, token_patient=None, token_admin=None)

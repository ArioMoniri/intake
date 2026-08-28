"""Fixture wiring for the legal-lane suites (INT-038). The helpers live in
legal_harness.py (uniquely named, importable from test modules directly —
the api_harness precedent); this file only binds them into fixtures.

The path shim must run before the harness imports, so the import block is
deliberately split (hence the E402 waivers)."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

import pytest  # noqa: E402
from api_harness import ADMIN_TOKEN, PATIENT_TOKEN, ApiHarness, build_harness  # noqa: E402
from legal_harness import BOUND_SCOPES, grant_bound, write_all_consent_texts  # noqa: E402


@pytest.fixture()
def legal_root(tmp_path: Path) -> Path:
    return write_all_consent_texts(tmp_path / "legal" / "consents")


@pytest.fixture()
def harness(tmp_path: Path) -> Iterator[ApiHarness]:
    """The plain INT-197 harness: no consent texts on disk (docs/legal is
    still awaiting INT-210), seeded dev-tier grants only."""
    yield from build_harness(tmp_path, token_patient=PATIENT_TOKEN, token_admin=ADMIN_TOKEN)


@pytest.fixture()
def bound_harness(tmp_path: Path, legal_root: Path) -> Iterator[ApiHarness]:
    """A harness whose catalog holds fixture texts AND whose dev patient has
    hash-bound grants for the scopes the API slice checks — the post-INT-210
    world, in miniature."""
    for built in build_harness(
        tmp_path, token_patient=PATIENT_TOKEN, token_admin=ADMIN_TOKEN, legal_root=legal_root
    ):
        grant_bound(built, *BOUND_SCOPES)
        yield built

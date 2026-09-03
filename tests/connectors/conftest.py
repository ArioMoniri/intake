"""Suite-wide wiring for the INT-160 connector tests.

A registered destination is a ``phi_allowed`` allow-list row, so INT-018's
runtime double gate — ``INTAKE_ALLOW_PHI_EGRESS=explicit-yes`` — applies to a
connector push exactly as it applies to a vendor call. Setting it here rather
than in each test keeps the tests about connectors; the one test that proves
the gate still bites deletes the variable itself.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _phi_egress_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTAKE_ALLOW_PHI_EGRESS", "explicit-yes")

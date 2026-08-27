"""INT-002 — coverage thresholds per CLAUDE.md invariant 8, and they only rise.

Acceptance line under test, verbatim:
  "coverage thresholds enforced exactly as CLAUDE.md invariant 8 (api >= 85,
   protocols >= 95, triage rules 100 percent branch, schemas/mappers >= 90,
   voice-runtime core >= 90, ts >= 85) and may only rise"
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
THRESHOLDS = REPO / "scripts" / "ci" / "coverage_thresholds.yaml"

INVARIANT_8_FLOORS = {
    "services/api": 85,
    "packages/protocols": 95,
    "packages/protocols/triage": 100,
    "packages/clinical-schemas": 90,
    "services/voice-runtime": 90,
}


def test_thresholds_meet_invariant_8_floors() -> None:
    cfg = yaml.safe_load(THRESHOLDS.read_text(encoding="utf-8"))
    for path, floor in INVARIANT_8_FLOORS.items():
        assert path in cfg["python"], f"missing coverage floor for {path}"
        assert cfg["python"][path] >= floor, f"{path} below invariant-8 floor {floor}"
    assert cfg["ts"]["default"] >= 85


def test_makefile_enforces_existing_python_floor() -> None:
    cfg = yaml.safe_load(THRESHOLDS.read_text(encoding="utf-8"))
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    m = re.search(r"--cov-fail-under=(\d+)", makefile)
    assert m, "check-py does not enforce a coverage floor"
    assert int(m.group(1)) >= cfg["python"]["packages/intake_platform"]


def test_vitest_enforces_ts_floor() -> None:
    cfg = yaml.safe_load(THRESHOLDS.read_text(encoding="utf-8"))
    vitest = (REPO / "packages" / "clinical-schemas" / "vitest.config.ts").read_text(
        encoding="utf-8"
    )
    m = re.search(r"lines:\s*(\d+)", vitest)
    assert m, "vitest config carries no coverage threshold"
    assert int(m.group(1)) >= cfg["ts"]["default"]


def test_ci_workflow_runs_gates_without_vendor_network() -> None:
    wf = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    for needle in (
        "check-py",
        "check-ts",
        "no_placeholders.sh",
        "assert_no_vendor_calls.sh",
        "evidence_check.sh",
    ):
        assert needle in wf, f"ci.yml missing {needle}"
    assert "secrets." not in wf, "ci.yml must not inject secrets — CI never calls vendors"

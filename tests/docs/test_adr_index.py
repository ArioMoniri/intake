"""INT-003 — ADRs 000..023 and the documentation index.

Acceptance (verbatim, with the count correction stated in issues.yaml):
  "docs/adr/ has ADR-000 template and 001..023 Accepted, one paragraph each
   (list in 07 §3.12)"
  "files/ contains files 01..11 verbatim; docs/index.md links everything"
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ADR = REPO / "docs" / "adr"

# Anchors from 07 §3.12 — an ADR that exists but says the wrong thing is worse
# than a missing one, so each amended/high-stakes decision is content-checked.
CONTENT_ANCHORS = {
    2: ["FHIR R4", "openEHR", "P3", "archetype-path"],
    7: ["residency_tr_media", "residency_tr_models", "capacity contract"],
    9: ["six tools", "preemption", "qwen-audio-agent"],
    10: ["residency_tr", "typed", "cascade_fast"],
    12: ["read-only", "acoustic", "investigation"],
    20: ["device_functions", "Class IIb"],
    21: ["self-hosted", "LICENSE blob", "4.9.1"],
    22: ["No accuracy claims", "docs/evidence/"],
    23: ["route", "register", "location", "no default"],
}


def _adr_file(n: int) -> Path:
    matches = sorted(ADR.glob(f"ADR-{n:03d}-*.md"))
    assert matches, f"missing ADR-{n:03d}"
    return matches[0]


def test_template_exists() -> None:
    text = _adr_file(0).read_text(encoding="utf-8")
    for section in ("## Context", "## Decision", "## Consequences"):
        assert section in text, f"ADR-000 template missing {section}"


def test_all_23_adrs_accepted_with_three_sections() -> None:
    for n in range(1, 24):
        text = _adr_file(n).read_text(encoding="utf-8")
        assert re.search(r"^Status:\s+Accepted", text, re.M), f"ADR-{n:03d} not Accepted"
        for section in ("## Context", "## Decision", "## Consequences"):
            assert section in text, f"ADR-{n:03d} missing {section}"


def test_amended_adrs_carry_their_amendment() -> None:
    for n in (2, 7, 10, 20):
        text = _adr_file(n).read_text(encoding="utf-8")
        assert "amended" in text.lower(), f"ADR-{n:03d} lost its amendment note"


def test_content_anchors() -> None:
    for n, anchors in CONTENT_ANCHORS.items():
        text = _adr_file(n).read_text(encoding="utf-8")
        for needle in anchors:
            assert needle in text, f"ADR-{n:03d} missing anchor {needle!r}"


def test_blueprint_files_present() -> None:
    files = REPO / "files"
    expected = [
        "00_STATE.md",
        "01_MARKET_AND_STRATEGY.md",
        "02_PRODUCT_SPEC.md",
        "03_ARCHITECTURE.md",
        "04_CLINICAL_PROTOCOLS.md",
        "05_ROADMAP.md",
        "06_COMPLIANCE_TR.md",
        "07_CLAUDE_CODE_MASTER_PROMPT.md",
        "08_ADMIN_CONSOLE_AND_OBSERVABILITY.md",
        "09_SPECIALTY_COVERAGE_AND_LEARNING.md",
        "10_SECURITY_AND_TECHNICAL_MONITORING.md",
        "11_ISSUE_BACKLOG.md",
        "12_DSL_V2_AND_RUNTIME_SPEC.md",
        "13_QUESTION_FLOW.md",
        "HUMAN_BLOCKERS.md",
        "README.md",
    ]
    for name in expected:
        assert (files / name).is_file(), f"files/{name} missing"
    assert (files / "protocols" / "base.life_threat.yaml").is_file()


def test_index_links_everything() -> None:
    index = (REPO / "docs" / "index.md").read_text(encoding="utf-8")
    for n in range(0, 24):
        assert re.search(rf"ADR-{n:03d}", index), f"docs/index.md does not link ADR-{n:03d}"
    for name in (
        "00_STATE.md",
        "HUMAN_BLOCKERS.md",
        "07_CLAUDE_CODE_MASTER_PROMPT.md",
        "13_QUESTION_FLOW.md",
        "base.life_threat.yaml",
    ):
        assert name in index, f"docs/index.md does not link {name}"
    for gov in ("CLAUDE.md", "LOOP.md", "GOALS.md", "DoD.md", "TDD.md", "PROGRESS.md"):
        assert gov in index, f"docs/index.md does not link {gov}"

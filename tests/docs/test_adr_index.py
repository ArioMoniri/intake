"""INT-003 — ADRs 000..023 and the documentation index.

Acceptance (verbatim, with the count correction stated in issues.yaml):
  "docs/adr/ has ADR-000 template and 001..023 Accepted, one paragraph each
   (list in 07 §3.12)"
  "files/ contains files 01..11 verbatim; docs/index.md links everything"

INT-332 adds the proposed-ADR pins: an ADR drafted for owner ratification
stays "Proposed" until the owner ratifies it, and its open questions stay
awaiting-human with their named owners.
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


# ADRs drafted for owner ratification (INT-332 onward). The Status line is
# pinned to "Proposed" so an unratified decision can never read as settled:
# the ratifying commit changes this pin, the Status line and the 00_STATE §3
# row together. Each anchor is a clause the ADR exists to carry.
PROPOSED_ANCHORS = {
    33: [
        "opacity",
        "120 ms",
        "150 ms",
        "platform fact",
        "snap, never queue",
        "hold, never rest",
        "exits are instant",
        "root layer",
        "the one permitted co-occurrence",
        "server-confirmed",
        "sticky",
        "fail closed",
    ],
}

# The five open questions of INT-332 and who must answer each.
MOTION_QUESTION_OWNERS = {
    "Q1": "owner",
    "Q2": "Dr Efe Onganer",
    "Q3": "Dr Efe Onganer",
    "Q4": "Dr Efe Onganer",
    "Q5": "owner",
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


def test_proposed_adrs_await_ratification() -> None:
    index = (REPO / "docs" / "index.md").read_text(encoding="utf-8")
    for n, anchors in PROPOSED_ANCHORS.items():
        text = _adr_file(n).read_text(encoding="utf-8")
        assert re.search(r"^Status:\s+Proposed", text, re.M), f"ADR-{n:03d} not Proposed"
        assert not re.search(r"^Status:\s+Accepted", text, re.M), (
            f"ADR-{n:03d} reads Accepted before the owner ratified it"
        )
        for section in ("## Context", "## Decision", "## Consequences"):
            assert section in text, f"ADR-{n:03d} missing {section}"
        for needle in anchors:
            assert needle in text, f"ADR-{n:03d} missing anchor {needle!r}"
        assert re.search(rf"\(adr/ADR-{n:03d}-[^)]+\.md\)", index), (
            f"docs/index.md does not register ADR-{n:03d}"
        )


def test_motion_adr_records_each_open_question_awaiting_its_owner() -> None:
    text = _adr_file(33).read_text(encoding="utf-8")
    for qid, owner in MOTION_QUESTION_OWNERS.items():
        row = re.search(rf"^\|\s*\*\*{qid}\*\*\s*\|.*$", text, re.M)
        assert row, f"ADR-033 has no table row for {qid}"
        line = row.group(0)
        assert owner in line, f"ADR-033 {qid} does not name {owner!r}"
        assert "awaiting-human" in line, f"ADR-033 {qid} is not awaiting-human"
        assert "Meanwhile" in line, f"ADR-033 {qid} states no fail-closed default"


def test_motion_adr_recommendations_do_not_ratify() -> None:
    """Each open question carries a recommended resolution, and a
    recommendation leaves the question open: the owner or the ClinicalAuthor
    still answers it, so its row stays awaiting-human and the ADR Proposed."""
    text = _adr_file(33).read_text(encoding="utf-8")
    section = re.search(r"^### 9\. Recommended resolution.*?(?=^## |\Z)", text, re.M | re.S)
    assert section, "ADR-033 has no recommended-resolution section"
    body = section.group(0)
    assert "not a ratification" in body
    for qid in MOTION_QUESTION_OWNERS:
        rec = re.search(rf"^\*\*{qid} — Recommended resolution:\*\*\s*(.+)$", body, re.M)
        assert rec, f"ADR-033 has no recommended resolution for {qid}"
        # Grounded: every recommendation cites Apple's guidance or the spec.
        para = body[rec.start() : body.find("\n\n", rec.start())]
        assert re.search(
            r"developer\.apple\.com/design/human-interface-guidelines|files/02", para
        ), f"ADR-033 {qid} recommendation cites neither Apple's HIG nor files/02"
    # The recommendation changes no status: the rows and the Status line hold.
    assert re.search(r"^Status:\s+Proposed", text, re.M)
    for qid in MOTION_QUESTION_OWNERS:
        row = re.search(rf"^\|\s*\*\*{qid}\*\*\s*\|.*$", text, re.M)
        assert row and "awaiting-human" in row.group(0)


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

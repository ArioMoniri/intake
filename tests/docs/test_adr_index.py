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


# INT-332 — ADR-033 ratifies the motion system as revised in
# docs/design/motion/motion-verification.md, with its 00_STATE row and the
# mobile-ui.md §Motion pointer, and records the five open questions
# awaiting-human with their named owners, each failing closed meanwhile.
MOTION_ANCHORS = [
    "motion-verification.md",
    "opacity",
    "120 ms",
    '["red", "yellowPill", "workChip", "railCommit", "content", "ambient"]',
    "snap, never queue",
    "hold, never rest",
    "exits are instant",
    "root layer",
    "150 ms",
    "invariant 21",
    "the one permitted co-occurrence",
]

# question -> (HUMAN_BLOCKERS id, named owner, words of its fail-closed default)
MOTION_QUESTIONS = {
    "Q1": ("HB-O10", "owner", "no RED is ever drawn as a push or a modal"),
    "Q2": ("HB-C26", "Dr Efe Onganer", "never"),
    "Q3": ("HB-C27", "Dr Efe Onganer", "no announcement"),
    "Q4": ("HB-C28", "Dr Efe Onganer", "withheld"),
    "Q5": ("HB-O11", "owner", "opacity-only"),
}


def _motion_adr() -> str:
    return _adr_file(33).read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    nxt = text.find("\n## ", start + len(heading))
    return text[start:] if nxt == -1 else text[start:nxt]


def _hb_row(hb_id: str) -> str:
    text = (REPO / "files" / "HUMAN_BLOCKERS.md").read_text(encoding="utf-8")
    rows = [line for line in text.splitlines() if line.startswith(f"| **{hb_id}** |")]
    assert len(rows) == 1, f"{hb_id} must appear exactly once in HUMAN_BLOCKERS.md"
    return rows[0]


def test_motion_adr_is_accepted_with_three_sections_and_its_anchors() -> None:
    text = _motion_adr()
    assert re.search(r"^Status:\s+Accepted", text, re.M), "ADR-033 not Accepted"
    for section in ("## Context", "## Decision", "## Consequences"):
        assert section in text, f"ADR-033 missing {section}"
    for needle in MOTION_ANCHORS:
        assert needle in text, f"ADR-033 missing anchor {needle!r}"


def test_motion_adr_never_lets_motion_delay_red() -> None:
    red = _section(_motion_adr(), "### 5. RED")
    for needle in ("0 ms", "never a native-stack push", "never an RN `Modal`", "ON_SITE"):
        assert needle in red, f"ADR-033 §5 missing {needle!r}"


def _question_gaps(line: str, hb_id: str, owner: str, default: str) -> list[str]:
    # The default must sit in the last cell (the "Meanwhile" column), not merely
    # somewhere in the row: Q4's question itself contains "withheld".
    gaps = [n for n in ("awaiting-human", hb_id, owner) if n not in line]
    meanwhile = line.rstrip().rstrip("|").rsplit("|", 1)[-1]
    if default not in meanwhile:
        gaps.append(default)
    return gaps


def test_motion_open_questions_are_awaiting_human_with_owner_and_fail_closed_default() -> None:
    questions = _section(_motion_adr(), "## Open questions")
    for q, (hb_id, owner, default) in MOTION_QUESTIONS.items():
        lines = [line for line in questions.splitlines() if line.startswith(f"| **{q}** |")]
        assert len(lines) == 1, f"ADR-033 must record {q} exactly once"
        gaps = _question_gaps(lines[0], hb_id, owner, default)
        assert not gaps, f"ADR-033 {q} missing {gaps}"
        row = _hb_row(hb_id)
        for needle in ("awaiting-human", "ADR-033", owner, default, "One sentence closes it"):
            assert needle in row, f"{hb_id} missing {needle!r}"


def test_near_miss_a_question_recorded_as_answered_or_without_its_default_is_refused() -> None:
    answered = "| **Q2** | ALERT haptic | Dr Efe Onganer | answered | HB-C26 | never |"
    assert _question_gaps(answered, "HB-C26", "Dr Efe Onganer", "never") == ["awaiting-human"]
    no_default = "| **Q5** | orb scale | owner | awaiting-human | HB-O11 | scale 1.06 |"
    assert _question_gaps(no_default, "HB-O11", "owner", "opacity-only") == ["opacity-only"]


def test_motion_state_row_and_mobile_ui_pointer() -> None:
    state = (REPO / "files" / "00_STATE.md").read_text(encoding="utf-8")
    rows = [line for line in state.splitlines() if line.startswith("| **D40** |")]
    assert len(rows) == 1, "files/00_STATE.md §3 must carry D40 exactly once"
    for needle in (
        "ADR-033",
        "INT-332",
        "awaiting-human",
        *(v[0] for v in MOTION_QUESTIONS.values()),
    ):
        assert needle in rows[0], f"D40 missing {needle!r}"
    mobile = (REPO / "docs" / "design" / "mobile-ui.md").read_text(encoding="utf-8")
    motion = _section(mobile, "## Motion")
    assert "adr/ADR-033-motion-system-v1.md" in motion, "mobile-ui.md §Motion must point to ADR-033"
    index = (REPO / "docs" / "index.md").read_text(encoding="utf-8")
    assert "adr/ADR-033-motion-system-v1.md" in index, "docs/index.md must link ADR-033"

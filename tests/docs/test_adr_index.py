"""INT-003 — ADRs 000..023 and the documentation index.

Acceptance (verbatim, with the count correction stated in issues.yaml):
  "docs/adr/ has ADR-000 template and 001..023 Accepted, one paragraph each
   (list in 07 §3.12)"
  "files/ contains files 01..11 verbatim; docs/index.md links everything"

INT-332 adds the proposed-ADR pins: an ADR drafted for owner ratification
stays "Proposed" until the owner ratifies it, and its open questions stay
awaiting-human with their named owners. Once ratified, "Accepted" requires a
ratification record for every open question (INT-332's ratifying commit,
2026-09-27): ADR-033 carries the owner's answers instead of "awaiting-human",
and a near-miss negative control checks that a lone unrecorded question is
still caught.
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
    # ADR-033 was drafted for owner ratification and is now Accepted
    # (2026-09-27, INT-332); these clauses stay content-checked regardless
    # of status, same as every other accepted ADR above.
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


# ADRs drafted for owner ratification (INT-332 onward), still awaiting it.
# The Status line is pinned to "Proposed" so an unratified decision can never
# read as settled. Empty once every drafted ADR has been ratified — ADR-033
# graduated out of this dict on 2026-09-27; see
# test_accepted_adr_requires_ratification_for_every_question below for the
# check that replaces it.
PROPOSED_ANCHORS: dict[int, list[str]] = {}

# The five open questions of INT-332 and who must answer each. The "Owner"
# column in ADR-033 §8 still names these domain owners after ratification —
# it records whose clinical or product judgment the question calls for, not
# who ratified the answer in chat (that is always the product owner, and the
# ratification record says so explicitly; see RATIFICATION_MARKER).
MOTION_QUESTION_OWNERS = {
    "Q1": "owner",
    "Q2": "Dr Efe Onganer",
    "Q3": "Dr Efe Onganer",
    "Q4": "Dr Efe Onganer",
    "Q5": "owner",
}

# The owner ratified ADR-033 in chat on 2026-09-27 ("ratify ADR-033 as
# recommended"). Every open-question row must carry this exact marker for
# the ADR to read Accepted; test_accepted_adr_requires_ratification_for_every_question
# enforces it, and test_near_miss_... proves the enforcement actually bites.
RATIFICATION_MARKER = "ratified by the owner in chat, 2026-09-27"

# The answers ratified, taken verbatim from ADR-033 §9 "Recommended
# resolution": Q1 yes, Q2 no, Q3 no, Q4 yes, Q5 no.
RATIFIED_ANSWERS = {"Q1": "yes", "Q2": "no", "Q3": "no", "Q4": "yes", "Q5": "no"}


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


def _question_row(text: str, qid: str) -> str:
    row = re.search(rf"^\|\s*\*\*{qid}\*\*\s*\|.*$", text, re.M)
    assert row, f"ADR-033 has no table row for {qid}"
    return row.group(0)


def _missing_ratifications(text: str, qids) -> list[str]:
    """Return the qids whose table row lacks RATIFICATION_MARKER. Only
    meaningful once Status reads Accepted — an ADR still Proposed is
    expected to be missing every one, so callers gate on Status themselves.
    Shared by the real ADR-033 check and its near-miss negative control, so
    the same logic that must pass on the real file is proven to actually
    catch a broken one."""
    missing = []
    for qid in qids:
        row = _question_row(text, qid)
        if RATIFICATION_MARKER not in row:
            missing.append(qid)
    return missing


def test_motion_adr_status_is_accepted_and_dated() -> None:
    text = _adr_file(33).read_text(encoding="utf-8")
    status = re.search(r"^Status:.*$", text, re.M)
    assert status, "ADR-033 has no Status line"
    assert re.match(r"Status:\s+Accepted\b", status.group(0)), (
        "ADR-033 is not Accepted — INT-332's ratification did not land"
    )
    assert "2026-09-27" in status.group(0), "ADR-033 Status line is not dated 2026-09-27"


def test_accepted_adr_requires_ratification_for_every_question() -> None:
    """INT-332's rule: an ADR cannot read Accepted while any of its open
    questions still lacks a ratification record. ADR-033 is Accepted, so
    every row in MOTION_QUESTION_OWNERS must carry RATIFICATION_MARKER."""
    text = _adr_file(33).read_text(encoding="utf-8")
    assert re.search(r"^Status:\s+Accepted\b", text, re.M), "ADR-033 not Accepted"
    missing = _missing_ratifications(text, MOTION_QUESTION_OWNERS)
    assert missing == [], f"ADR-033 is Accepted but missing ratification for {missing}"


def test_motion_adr_ratified_answers_match_section_9() -> None:
    """Each row's ratified answer must be the one §9 "Recommended
    resolution" proposed for that question (Q1 yes, Q2 no, Q3 no, Q4 yes,
    Q5 no), and the marker must be a real ratification, not "awaiting-human"
    reworded."""
    text = _adr_file(33).read_text(encoding="utf-8")
    section = re.search(r"^### 9\. Recommended resolution.*?(?=^## |\Z)", text, re.M | re.S)
    assert section, "ADR-033 has no recommended-resolution section"
    body = section.group(0)
    for qid, answer in RATIFIED_ANSWERS.items():
        rec = re.search(
            rf"^\*\*{qid} — Recommended resolution:\*\*\s*answer\s+\*\*(\w+)\*\*", body, re.M
        )
        assert rec, f"ADR-033 has no recommended resolution for {qid}"
        assert rec.group(1) == answer, (
            f"ADR-033 {qid} §9 proposes {rec.group(1)!r}, "
            f"RATIFIED_ANSWERS says {answer!r} — fixture drifted"
        )
        row = _question_row(text, qid)
        assert f"**{answer}**" in row, (
            f"ADR-033 {qid} row does not record the ratified answer {answer!r}"
        )
        assert "awaiting-human" not in row, f"ADR-033 {qid} still reads awaiting-human"


def test_motion_adr_records_each_open_question_ratified_by_its_named_context() -> None:
    text = _adr_file(33).read_text(encoding="utf-8")
    for qid, owner in MOTION_QUESTION_OWNERS.items():
        row = _question_row(text, qid)
        assert owner in row, f"ADR-033 {qid} does not name {owner!r}"
        assert RATIFICATION_MARKER in row, f"ADR-033 {qid} has no ratification record"
        assert "Meanwhile" in row, f"ADR-033 {qid} states no fail-closed default"


def test_motion_adr_q2_does_not_claim_clinical_author_signed() -> None:
    """The owner ratified Q2's conservative "no" in chat; Dr Efe Onganer
    (the ClinicalAuthor named as Q2's question owner) has not signed off.
    The row must say so, and must not read as if the ClinicalAuthor
    ratified, signed or confirmed the answer."""
    text = _adr_file(33).read_text(encoding="utf-8")
    row = _question_row(text, "Q2")
    assert RATIFICATION_MARKER in row
    assert "has not signed" in row, "ADR-033 Q2 does not disclaim clinical sign-off"
    assert not re.search(r"Efe Onganer (ratified|signed|confirmed|answered)", row), (
        "ADR-033 Q2 reads as if the ClinicalAuthor ratified the answer"
    )


def test_near_miss_accepted_with_one_unratified_question_is_caught() -> None:
    """Negative control for _missing_ratifications / the Accepted-requires-
    ratification rule: strip Q2's ratification record from an otherwise
    fully-ratified ADR-033 and confirm the checker isolates exactly Q2.
    Guards against a checker that never actually inspects the rows (e.g.
    one that only looks at the Status line and always returns [])."""
    text = _adr_file(33).read_text(encoding="utf-8")
    assert _missing_ratifications(text, MOTION_QUESTION_OWNERS) == []  # sanity: real file is clean

    q2_row = _question_row(text, "Q2")
    stripped = q2_row.replace(RATIFICATION_MARKER, "awaiting-human")
    assert stripped != q2_row
    mutated = text.replace(q2_row, stripped)
    assert mutated != text

    missing = _missing_ratifications(mutated, MOTION_QUESTION_OWNERS)
    assert missing == ["Q2"], f"near-miss control did not isolate Q2: {missing}"


def test_motion_adr_section_9_no_longer_reads_as_recommendation_only() -> None:
    """§9's heading/intro must no longer say "recommendation, not a
    ratification" (INT-332 was ratified on 2026-09-27), but each
    recommendation's grounding — the Apple HIG / files/02 citations — must
    still be there, unchanged, for every question."""
    text = _adr_file(33).read_text(encoding="utf-8")
    section = re.search(r"^### 9\. Recommended resolution.*?(?=^## |\Z)", text, re.M | re.S)
    assert section, "ADR-033 has no recommended-resolution section"
    body = section.group(0)
    assert "not a ratification" not in body, "ADR-033 §9 still disclaims ratification"
    assert "ratified" in body.lower(), "ADR-033 §9 does not record that it was ratified"
    for qid in MOTION_QUESTION_OWNERS:
        rec = re.search(rf"^\*\*{qid} — Recommended resolution:\*\*\s*(.+)$", body, re.M)
        assert rec, f"ADR-033 has no recommended resolution for {qid}"
        # Grounded: every recommendation still cites Apple's guidance or the spec.
        para = body[rec.start() : body.find("\n\n", rec.start())]
        assert re.search(
            r"developer\.apple\.com/design/human-interface-guidelines|files/02", para
        ), f"ADR-033 {qid} recommendation cites neither Apple's HIG nor files/02"


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

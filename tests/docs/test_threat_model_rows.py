"""INT-020 — the threat model covers every backlog sec_row (files/10 §9).

Acceptance line under test, verbatim:
  "docs/security/threat-model.md STRIDE+LINDDUN seeded from 10 §9; ..."

files/10 §8: "Backlog `sec_row:` fields point at the §9 rows below, so every
feature PR links its threat row by construction." That construction only holds
if the working threat model actually has a section for every row the backlog
uses — which is what this file pins.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
DOC = REPO / "docs" / "security" / "threat-model.md"
ISSUES = REPO / "docs" / "backlog" / "issues.yaml"

# Every section heading is exactly "## `<slug>` — <title>" so both this test
# and scripts/ci/check_sec_row_linkage.py can match rows mechanically.
HEADING = re.compile(r"^## `([a-z0-9-]+)` — .+$", re.M)

SECTION_FIELDS = (
    "**Assets:**",
    "**Trust boundaries:**",
    "**Threats (STRIDE/LINDDUN):**",
    "**Controls (files/10):**",
    "**Signals:**",
    "**Tests:**",
)


def _sec_rows() -> set[str]:
    issues = yaml.safe_load(ISSUES.read_text(encoding="utf-8"))
    return {i["sec_row"] for i in issues if i.get("sec_row")}


def _doc() -> str:
    assert DOC.is_file(), "docs/security/threat-model.md is missing"
    return DOC.read_text(encoding="utf-8")


def test_every_backlog_sec_row_has_a_section_heading() -> None:
    headed = set(HEADING.findall(_doc()))
    missing = sorted(_sec_rows() - headed)
    assert not missing, f"threat-model.md has no section for sec_row(s): {missing}"


def test_no_section_for_a_row_the_backlog_does_not_carry() -> None:
    # A heading without a backlog row is either a typo or a row that was
    # renamed in issues.yaml without the model following — both are drift.
    stale = sorted(set(HEADING.findall(_doc())) - _sec_rows())
    assert not stale, f"threat-model.md sections without a backlog sec_row: {stale}"


def test_every_section_carries_the_six_required_fields() -> None:
    text = _doc()
    matches = list(HEADING.finditer(text))
    assert matches, "threat-model.md has no `## `row`` sections at all"
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.start() : end]
        for field in SECTION_FIELDS:
            assert field in body, f"section for {m.group(1)!r} is missing {field}"


def test_model_states_its_derivation_from_files_10() -> None:
    text = _doc()
    for anchor in ("files/10", "§9", "STRIDE", "LINDDUN"):
        assert anchor in text, f"threat-model.md never mentions {anchor!r}"

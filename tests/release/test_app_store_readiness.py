"""INT-613: docs/release/app-store-readiness.md uses a closed set of states, its counts
are its own table's, and it covers every item the brief names."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DOC = REPO / "docs" / "release" / "app-store-readiness.md"
TEXT = DOC.read_text(encoding="utf-8")
ROW = re.compile(
    r"^\| (\d+) \| (.+?) \| (done|open PR #\d+|missing|needs credentials|needs a human) \| (.+) \|$"
)


def _rows() -> list[tuple[int, str, str]]:
    section = TEXT.split("## Checklist", 1)[1].split("## Counts", 1)[0]
    lines = [line for line in section.splitlines() if re.match(r"^\| \d+ \|", line)]
    rows = []
    for line in lines:
        match = ROW.match(line)
        assert match, f"row with an unknown state or shape: {line[:80]}"
        rows.append((int(match.group(1)), match.group(2), match.group(3)))
    return rows


def test_rows_are_numbered_in_order() -> None:
    numbers = [n for n, _, _ in _rows()]
    assert numbers == list(range(1, len(numbers) + 1))


def test_the_counts_table_is_the_checklist_counted() -> None:
    counted = Counter(
        "open PR" if state.startswith("open PR") else state for _, _, state in _rows()
    )
    table = dict(
        re.findall(
            r"^\| (done|open PR|missing|needs credentials|needs a human) \| (\d+) \|$", TEXT, re.M
        )
    )
    assert {k: int(v) for k, v in table.items()} == dict(counted)


def test_every_open_pr_named_is_one_of_the_store_lane_prs() -> None:
    prs = {state for _, _, state in _rows() if state.startswith("open PR")}
    assert prs <= {"open PR #860", "open PR #1009", "open PR #1010"}


def test_every_item_of_the_brief_is_covered() -> None:
    items = " ".join(item for _, item, _ in _rows()).lower()
    for needle in (
        "app record",
        "bundle id",
        "name",
        "subtitle",
        "keywords",
        "description",
        "promotional text",
        "category",
        "age rating",
        "privacy nutrition labels",
        "privacy policy url",
        "support url",
        "itsappusesnonexemptencryption",
        "nsmicrophoneusagedescription",
        "nscamerausagedescription",
        "nshealthshareusagedescription",
        "nsfaceidusagedescription",
        'iphone 6.9"',
        'iphone 6.5"',
        "ipad",
        "app review notes",
        "demo sign-in",
        "healthkit justification",
        "guideline 1.4.1",
        "guideline 5.1.1",
        "version string",
        "build number",
        "testflight",
    ):
        assert needle in items, needle

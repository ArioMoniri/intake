"""INT-498 — the feature audit keeps its own arithmetic honest.

``docs/evidence/INT-498.md`` is the owner's answer to "all features working,
nothing demo". It will be edited as PRs merge, so these checks hold the
properties a reader relies on:

- every feature row carries exactly one status from the closed vocabulary;
- the stated counts are the table's counts, not a remembered number;
- WORKING means working on the synthetic host, so a row whose host cell says
  the feature is not deployed or not reachable can never be WORKING;
- the GATED list names the five gates the owner asked for, in order, and each
  one carries a fastest legitimate path and at least one source.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "docs" / "evidence" / "INT-498.md"
STATUSES = ("WORKING", "PARTIAL", "NOT BUILT", "DEMO-ONLY", "GATED")
ROW = re.compile(r"^\| (F\d{2}) \|")
HOST_NOT_SERVING = ("not deployed", "not reachable", "not in the staging compose")
GATES = {
    "G1": "Türkiye",
    "G2": "physician",
    "G3": "lawyer",
    "G4": "device",
    "G5": "Apple",
}


def _text() -> str:
    return AUDIT.read_text(encoding="utf-8")


def _rows() -> list[list[str]]:
    return [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in _text().splitlines()
        if ROW.match(line)
    ]


def test_every_row_has_one_status_from_the_closed_vocabulary() -> None:
    rows = _rows()
    assert len(rows) >= 30, "the audit covers every requested feature"
    ids = [row[0] for row in rows]
    assert len(ids) == len(set(ids)), "feature ids are unique"
    for row in rows:
        assert len(row) == 7, f"{row[0]}: id, feature, main, open PR, host, status, next"
        assert row[5] in STATUSES, f"{row[0]}: status {row[5]!r}"


def test_the_stated_counts_are_the_table_counts() -> None:
    match = re.search(r"^Counts: (.+)$", _text(), re.MULTILINE)
    assert match, "the audit states its counts on one 'Counts:' line"
    stated = {
        name: int(number)
        for name, number in re.findall(
            r"(WORKING|PARTIAL|NOT BUILT|DEMO-ONLY|GATED) (\d+)", match.group(1)
        )
    }
    counted = Counter(row[5] for row in _rows())
    assert stated == {status: counted.get(status, 0) for status in STATUSES}


def test_working_means_working_on_the_host() -> None:
    for row in _rows():
        if row[5] != "WORKING":
            continue
        host = row[4].lower()
        assert host not in ("", "—"), f"{row[0]}: WORKING needs a host observation"
        for phrase in HOST_NOT_SERVING:
            assert phrase not in host, f"{row[0]}: WORKING but the host cell says {phrase!r}"


def test_the_gated_list_names_the_five_gates_with_a_path_and_a_source() -> None:
    text = _text()
    start = text.index("## 4. GATED")
    section = text[start : text.index("\n## ", start + 1)]
    blocks = re.split(r"^### ", section, flags=re.MULTILINE)[1:]
    assert [block[:2] for block in blocks] == list(GATES)
    for block in blocks:
        gate, heading = block[:2], block.splitlines()[0]
        assert GATES[gate].lower() in heading.lower(), f"{gate}: heading names {GATES[gate]!r}"
        assert "Fastest path" in block, f"{gate}: no fastest path"
        # a fetched URL, a Resmî Gazete number, or the project's sourced
        # compliance register (files/06), which carries the dated citation
        assert re.search(r"https://|RG \d{5}|files/06 row", block), f"{gate}: no source"

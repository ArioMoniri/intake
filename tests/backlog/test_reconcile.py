"""INT-396 — scripts/backlog/reconcile.py: backlog rows against what merged.

Acceptance line under test, verbatim:
  "`scripts/backlog/reconcile.py` reports, for each row: its merged PRs (by
   title), whether each said `Closes` or `Refs`, the GitHub issue states, the
   evidence file, and blockers.md / HUMAN_BLOCKERS references. It recommends a
   status, and a human-held row keeps `awaiting-human` with its blocker named"

The decision is reconcile_lib (pure); the CLI in reconcile.py is driven as a
subprocess. Every case is hermetic: the PR and issue lists are fixtures in the
shape `gh --json` returns, so no test touches the network. Each rule that recommends
`done` has a near-miss control that must leave the row as it is.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "backlog" / "reconcile.py"
sys.path.insert(0, str(REPO / "scripts" / "backlog"))

import reconcile_lib as rc  # noqa: E402
from sync_issues import build_plan, owned_issue_numbers  # noqa: E402


def _pr(number: int, title: str, body: str) -> dict[str, Any]:
    return {"number": number, "title": title, "body": body, "mergedAt": "2026-09-27T00:00:00Z"}


def _issue(number: int, title: str, state: str) -> dict[str, Any]:
    return {"number": number, "title": title, "state": state}


ROW = {"id": "INT-901", "status": "todo"}
OWNED = _issue(11, "INT-901: the row's own issue", "CLOSED")


def _one(
    row: dict[str, Any],
    prs: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    *,
    evidence: str | None = "## Acceptance, line by line\nall met\n",
    blockers: str = "",
    human: str = "",
) -> Any:
    reports = rc.reconcile(
        [row],
        prs,
        issues,
        rc.blocker_refs(blockers, human),
        lambda _iid: evidence,
    )
    assert len(reports) == 1
    return reports[0]


# ---- the one rule that recommends `done` -----------------------------------


def test_closed_by_a_merged_pr_with_evidence_and_no_blocker_is_done() -> None:
    r = _one(ROW, [_pr(50, "INT-901: deliver it", "Closes #11")], [OWNED])
    assert r.new_status == "done"
    assert r.add_evidence
    assert not r.ambiguous
    assert r.prs[0].closes == (11,)
    assert "#50" in r.reason


def test_near_miss_refs_only_is_left_and_reported() -> None:
    r = _one(ROW, [_pr(50, "INT-901: part of it", "Refs #11")], [OWNED])
    assert r.new_status is None and not r.add_evidence
    assert r.ambiguous
    assert r.prs[0].refs == (11,) and r.prs[0].closes == ()
    assert "Refs" in r.reason


def test_near_miss_a_pr_titled_for_another_id_is_not_counted() -> None:
    r = _one(ROW, [_pr(50, "INT-902: other work", "Closes #11")], [OWNED])
    assert r.prs == ()
    assert r.new_status is None


def test_near_miss_closing_a_scoped_duplicate_is_not_closing_the_row() -> None:
    issues = [
        _issue(40, "INT-901 core: the first slice", "CLOSED"),
        _issue(11, "INT-901: the row's own issue", "OPEN"),
    ]
    r = _one(ROW, [_pr(50, "INT-901: core slice", "Closes #40")], issues)
    assert r.new_status is None
    assert r.ambiguous
    assert r.owned == 11
    assert [i.number for i in r.duplicates] == [40]
    assert "#40" in r.reason and "#11" in r.reason


def test_near_miss_a_reopened_issue_is_left_and_reported() -> None:
    issues = [_issue(11, "INT-901: the row's own issue", "OPEN")]
    r = _one(ROW, [_pr(50, "INT-901: deliver it", "Closes #11")], issues)
    assert r.new_status is None
    assert r.ambiguous
    assert "open" in r.reason


def test_near_miss_no_evidence_file_is_left_and_reported() -> None:
    r = _one(ROW, [_pr(50, "INT-901: deliver it", "Closes #11")], [OWNED], evidence=None)
    assert r.new_status is None
    assert r.ambiguous
    assert "evidence" in r.reason


def test_near_miss_evidence_marking_a_clause_pending_is_left_and_reported() -> None:
    # INT-330's shape: the PR closed the issue, and the evidence file records
    # the owner's device measurement as not yet taken.
    text = "## Device measurement: PENDING\nThe owner's two reference devices.\n"
    r = _one(ROW, [_pr(50, "INT-901: deliver it", "Closes #11")], [OWNED], evidence=text)
    assert r.new_status is None
    assert r.ambiguous
    assert "PENDING" in r.reason


def test_near_miss_not_met_in_capitals_is_left_and_reported() -> None:
    text = "| 5 | counsel sign-off | **NOT MET** |\n"
    r = _one(ROW, [_pr(50, "INT-901: deliver it", "Closes #11")], [OWNED], evidence=text)
    assert r.new_status is None and r.ambiguous


def test_lower_case_pending_in_prose_does_not_hold_a_row() -> None:
    text = "HB-C1 is pending and outside this issue's acceptance.\n"
    r = _one(ROW, [_pr(50, "INT-901: deliver it", "Closes #11")], [OWNED], evidence=text)
    assert r.new_status == "done"


# ---- blockers --------------------------------------------------------------

BLOCKERS_ROW = """
| issue | status | who | the one sentence they must answer | HB id |
|---|---|---|---|---|
| INT-901 | awaiting-human (content; mechanism shipped) | owner | Which value? | HB-X1 |
| INT-990 (split from INT-902, 27 Sep 2026) | awaiting-human (corpus) | owner | Which corpus? | — |
| — | resolved (no action) | coordinator | INT-903 was already merged. | — |
"""

HUMAN_OPEN = """
| id | what is needed | who | what it blocks | status | raised |
|---|---|---|---|---|---|
| **HB-X2** | A decision | owner | INT-904 | **open** | 1 Sep 2026 |
| **HB-X3** | ~~An old ask~~ | owner | INT-905 | **closed by D1** — moot | 1 Sep 2026 |
"""


def test_a_blocker_row_keeps_a_closed_row_from_done_and_is_named() -> None:
    row = {"id": "INT-901", "status": "doing"}
    r = _one(row, [_pr(50, "INT-901: deliver it", "Closes #11")], [OWNED], blockers=BLOCKERS_ROW)
    assert r.new_status is None
    assert r.ambiguous
    assert any("awaiting-human (content" in b for b in r.blockers)


def test_awaiting_human_keeps_its_status_and_names_its_blocker() -> None:
    row = {"id": "INT-901", "status": "awaiting-human"}
    r = _one(row, [_pr(50, "INT-901: mechanism", "Closes #11")], [OWNED], blockers=BLOCKERS_ROW)
    assert r.new_status is None
    assert not r.ambiguous
    assert r.blockers and "blocker" in r.reason


def test_awaiting_human_with_no_blocker_naming_it_is_reported() -> None:
    row = {"id": "INT-901", "status": "awaiting-human"}
    r = _one(row, [_pr(50, "INT-901: mechanism", "Closes #11")], [OWNED])
    assert r.new_status is None
    assert r.ambiguous


def test_blocker_parsing_reads_the_row_id_not_its_history() -> None:
    refs = rc.blocker_refs(BLOCKERS_ROW + "\n## INT-906 · a narrative section\n", HUMAN_OPEN)
    assert "INT-990" in refs
    assert "INT-902" not in refs, "'split from INT-902' names history, not a blocked row"
    assert "INT-903" not in refs, "a resolved row blocks nothing"
    assert "INT-906" in refs, "a blockers.md section heading names its issue"
    assert refs["INT-904"] == ["HUMAN_BLOCKERS HB-X2"]
    assert "INT-905" not in refs, "a closed HUMAN_BLOCKERS row blocks nothing"


def test_an_open_human_blockers_row_keeps_a_row_from_done() -> None:
    row = {"id": "INT-904", "status": "todo"}
    owned = _issue(14, "INT-904: x", "CLOSED")
    r = _one(row, [_pr(50, "INT-904: x", "Closes #14")], [owned], human=HUMAN_OPEN)
    assert r.new_status is None and r.ambiguous
    assert r.blockers == ("HUMAN_BLOCKERS HB-X2",)


def test_near_miss_a_closed_human_blockers_row_does_not_block() -> None:
    row = {"id": "INT-905", "status": "todo"}
    owned = _issue(15, "INT-905: x", "CLOSED")
    r = _one(row, [_pr(50, "INT-905: x", "Closes #15")], [owned], human=HUMAN_OPEN)
    assert r.new_status == "done"


# ---- evidence on rows that stay --------------------------------------------


def test_a_done_row_gains_its_evidence_key_when_the_file_exists() -> None:
    r = _one({"id": "INT-901", "status": "done"}, [], [])
    assert r.add_evidence and r.new_status is None and not r.ambiguous


def test_a_done_row_without_an_evidence_file_is_reported_not_fabricated() -> None:
    r = _one({"id": "INT-901", "status": "done"}, [], [], evidence=None)
    assert not r.add_evidence
    assert r.ambiguous


def test_a_todo_row_carrying_evidence_loses_the_key_and_keeps_its_status() -> None:
    row = {"id": "INT-901", "status": "todo", "evidence": "docs/evidence/INT-901.md"}
    r = _one(row, [], [])
    assert r.drop_evidence and r.new_status is None


# ---- the sync's ownership is the reconciler's ownership --------------------


def test_owned_issue_is_the_one_the_sync_maps() -> None:
    # gh lists newest first; the sync keeps the last match, i.e. the oldest.
    existing = [
        _issue(40, "INT-901 — a later copy", "CLOSED"),
        _issue(11, "INT-901: the row's own issue", "OPEN"),
    ]
    assert owned_issue_numbers(existing) == {"INT-901": 11}
    plan = build_plan([{"id": "INT-901", "title": "t", "phase": "P0", "epic": "E"}], existing)
    assert plan["actions"][0]["number"] == 11


def test_link_parsing() -> None:
    closes, refs = rc.parse_links("Fixes #3. closes #4\nRefs #5 and Resolved: #6; related #7")
    assert closes == (3, 4, 6)
    assert refs == (5,)


# ---- --apply ---------------------------------------------------------------

BACKLOG = """\
# header comment survives
- id: INT-901
  epic: E00-governance
  phase: P0
  title: "closed by a merged PR"
  depends_on: []
  labels: []
  # a comment on the row survives
  status: todo
  acceptance: ["x"]
- id: INT-902
  epic: E00-governance
  phase: P0
  title: "todo carrying evidence"
  depends_on: []
  labels: []
  status: todo
  evidence: docs/evidence/INT-902.md
  acceptance: ["x"]
- id: INT-903
  epic: E00-governance
  phase: P0
  title: "done without the key"
  depends_on: []
  labels: []
  status: done
  acceptance: ["x"]
- id: INT-904
  epic: E00-governance
  phase: P0
  title: "untouched"
  depends_on: []
  labels: []
  status: awaiting-human
  evidence: docs/evidence/INT-904.md
  acceptance: ["x"]
"""


def _fixtures(tmp_path: Path) -> None:
    (tmp_path / "issues.yaml").write_text(BACKLOG, encoding="utf-8")
    (tmp_path / "prs.json").write_text(
        json.dumps([_pr(50, "INT-901: deliver it", "Closes #11")]), encoding="utf-8"
    )
    (tmp_path / "gh_issues.json").write_text(
        json.dumps([_issue(11, "INT-901: x", "CLOSED")]), encoding="utf-8"
    )
    (tmp_path / "blockers.md").write_text("", encoding="utf-8")
    (tmp_path / "hb.md").write_text("", encoding="utf-8")
    ev = tmp_path / "evidence"
    ev.mkdir()
    for iid in ("INT-901", "INT-902", "INT-903", "INT-904"):
        (ev / f"{iid}.md").write_text("x", encoding="utf-8")


def _invoke(tmp_path: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--issues-file",
            str(tmp_path / "issues.yaml"),
            "--prs-json",
            str(tmp_path / "prs.json"),
            "--issues-json",
            str(tmp_path / "gh_issues.json"),
            "--blockers",
            str(tmp_path / "blockers.md"),
            "--human-blockers",
            str(tmp_path / "hb.md"),
            "--evidence-dir",
            str(tmp_path / "evidence"),
            *extra,
        ],
        capture_output=True,
        text=True,
        cwd=REPO,
    )


def test_read_only_by_default(tmp_path: Path) -> None:
    _fixtures(tmp_path)
    out = _invoke(tmp_path)
    assert out.returncode == 0, out.stderr
    assert (tmp_path / "issues.yaml").read_text(encoding="utf-8") == BACKLOG
    assert "INT-901" in out.stdout and "done" in out.stdout
    assert "changes: 3" in out.stdout


def test_apply_edits_only_what_it_recommends_and_keeps_comments(tmp_path: Path) -> None:
    _fixtures(tmp_path)
    out = _invoke(tmp_path, "--apply")
    assert out.returncode == 0, out.stderr
    text = (tmp_path / "issues.yaml").read_text(encoding="utf-8")
    assert "# header comment survives" in text
    assert "# a comment on the row survives" in text
    rows = {r["id"]: r for r in yaml.safe_load(text)}
    assert rows["INT-901"]["status"] == "done"
    assert rows["INT-901"]["evidence"] == "docs/evidence/INT-901.md"
    assert rows["INT-902"]["status"] == "todo" and "evidence" not in rows["INT-902"]
    assert rows["INT-903"]["evidence"] == "docs/evidence/INT-903.md"
    assert rows["INT-904"] == yaml.safe_load(BACKLOG)[3]
    # a second pass finds nothing left to change
    again = _invoke(tmp_path)
    assert again.returncode == 0, again.stderr
    assert "changes: 0" in again.stdout

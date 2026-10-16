"""INT-452 — the roadmap is generated from the backlog plus GitHub state, never by hand.

Acceptance lines under test (docs/backlog/issues.yaml INT-452), verbatim:
  "scripts/backlog/render_roadmap.py renders the live status section of
   files/05_ROADMAP.md from docs/backlog/issues.yaml, docs/backlog/epics.yaml,
   files/HUMAN_BLOCKERS.md, docs/backlog/blockers.md and the committed GitHub
   snapshot docs/backlog/github_snapshot.json: per phase and epic, done, in
   flight (open PR and branch), blocked (blocker record and named owner) and
   todo, each with an owner (a named human or an agent role)"
  "`make roadmap-snapshot` is the only step that calls GitHub; CI and the tests
   read the committed snapshot or fixtures, and a pytest check fails when the
   committed roadmap or files/11 differs from the generator output"
  "the three hard-coded backlog count pins become one derived check: ids are
   unique, the sync plans exactly one action per row, and no id recorded in the
   snapshot's row floor (which only the snapshot step may raise) loses its row"

Everything here is hermetic: no test reaches GitHub, and the snapshot step's
gh and git calls go through a fake runner.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "backlog"))

import backlog_lib  # noqa: E402
import render_roadmap  # noqa: E402
import roadmap_lib as rl  # noqa: E402
import roadmap_render as rr  # noqa: E402
import roadmap_snapshot as snap  # noqa: E402

# ---- fixtures -----------------------------------------------------------------


def _row(iid: str, **kw: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": iid,
        "epic": kw.pop("epic", "E03-protocols"),
        "phase": kw.pop("phase", "P0"),
        "title": kw.pop("title", f"title of {iid}"),
        "depends_on": kw.pop("depends_on", []),
        "labels": kw.pop("labels", []),
        "status": kw.pop("status", "todo"),
        "acceptance": ["x"],
    }
    row.update(kw)
    return row


EPICS = [
    {"id": "E03-protocols", "charter": "packs"},
    {"id": "E08-mobile", "charter": "app"},
]

HUMAN_BLOCKERS = """
| id | what is needed | who | what it blocks | status | raised |
|---|---|---|---|---|---|
| **HB-C1** | sign the pack | **Dr Example** (physician of record) | INT-902 | **open** | 1 Sep |
| **HB-L5** | a contract | ~~owner~~ | INT-903 | **closed by D-x** — moot | 1 Sep |
| **HB-I9** | a WORM target | owner | the anchor | **open** | 1 Sep |
"""

BLOCKERS = """
| issue | status | who | the one sentence they must answer | HB id |
|---|---|---|---|---|
| INT-905 (split from INT-901) | awaiting-human (a choice) | owner + counsel | Choose. | HB-L9 |
| INT-906 | resolved (done) | owner | Old. | — |
"""


def _rows() -> list[dict[str, Any]]:
    return [
        _row("INT-901", status="done", evidence="docs/evidence/INT-901.md"),
        _row("INT-902", status="awaiting-human", labels=["approval:human-clinical"]),
        _row("INT-903", depends_on=["INT-901"], labels=["area:mobile"], epic="E08-mobile"),
        _row("INT-904", depends_on=["INT-902"], labels=["area:protocols"]),
        _row("INT-905", status="awaiting-human", phase="P1"),
        _row("INT-906", status="doing", phase="P1", epic="E08-mobile"),
        _row("INT-907", depends_on=["INT-906"], phase="P1", title="a | pipe"),
        _row("INT-908", status="withdrawn", phase="P1"),
        _row("INT-909", labels=["blocked:contract"], phase="P2"),
        _row("INT-910", phase="P2", labels=["approval:human-legal", "area:legal"]),
    ]


def _snapshot(**kw: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "schema": 1,
        "repo": "ArioMoniri/intake",
        "captured_at": "2026-10-16T06:00:00Z",
        "base": "0123456789abcdef0123456789abcdef01234567",
        "row_floor": [f"INT-9{n:02d}" for n in range(1, 11)],
        "open_prs": [
            {
                "number": 50,
                "title": "INT-903: build the screen",
                "branch": "int-903-screen",
                "draft": False,
                "mergeable": "MERGEABLE",
                "rows_added": [],
            },
            {
                "number": 51,
                "title": "INT-902: draft pack",
                "branch": "int-902-pack",
                "draft": False,
                "mergeable": "CONFLICTING",
                "rows_added": [],
            },
            {
                "number": 52,
                "title": "INT-950: a new thing",
                "branch": "int-950-new",
                "draft": True,
                "mergeable": "UNKNOWN",
                "rows_added": ["INT-950", "INT-951"],
            },
            {
                "number": 53,
                "title": "fix(ci): no id here",
                "branch": "fix-ci",
                "draft": False,
                "mergeable": "MERGEABLE",
                "rows_added": None,
            },
        ],
        "open_issues": [
            {"number": 10, "title": "INT-901: done already", "phase": "P0"},
            {"number": 60, "title": "INT-950: a new thing", "phase": "P1"},
            {"number": 61, "title": "INT-951: stacked on #52", "phase": "P1"},
            {"number": 62, "title": "INT-960: nobody has it", "phase": "P2"},
            {"number": 63, "title": "INT-961: unlabelled", "phase": None},
            {"number": 64, "title": "not a backlog issue", "phase": None},
        ],
        "merged_prs": {"INT-901": [40], "INT-904": [41]},
    }
    data.update(kw)
    return data


def _inputs(**kw: Any) -> rl.Inputs:
    rows = kw.pop("rows", _rows())
    return rl.Inputs(
        rows=rows,
        epics=kw.pop("epics", EPICS),
        snapshot=kw.pop("snapshot", _snapshot()),
        human_blockers_md=kw.pop("human_blockers_md", HUMAN_BLOCKERS),
        blockers_md=kw.pop("blockers_md", BLOCKERS),
        row_texts=kw.pop("row_texts", {"INT-909": "  # waits on HB-I9 and HB-L5\n"}),
    )


# ---- owners -------------------------------------------------------------------


def test_owner_of_a_blocked_row_is_the_blockers_md_who() -> None:
    model = rl.build(_inputs())
    assert model.items["INT-905"].owner == "owner + counsel"
    assert "HB-L9" in model.items["INT-905"].note


def test_owner_of_a_blocked_row_falls_back_to_its_open_hb_row() -> None:
    model = rl.build(_inputs())
    assert model.items["INT-902"].owner.startswith("HB-C1: Dr Example (physician of record)")


def test_owner_from_an_hb_id_in_the_rows_own_text_skips_closed_hb_rows() -> None:
    # INT-909's block names HB-I9 (open) and HB-L5 (closed): only the open one counts.
    item = rl.build(_inputs()).items["INT-909"]
    assert item.state == "blocked"
    assert item.owner == "HB-I9: owner"
    assert "HB-L5" not in item.note


def test_near_miss_a_blocked_row_with_no_record_names_the_gap() -> None:
    rows = _rows() + [_row("INT-911", status="awaiting-human")]
    item = rl.build(_inputs(rows=rows, snapshot=_snapshot(row_floor=[]))).items["INT-911"]
    assert item.owner == rl.NO_RECORD_OWNER


def test_owner_of_an_unblocked_row_is_an_agent_role_with_its_sign_off() -> None:
    model = rl.build(_inputs())
    assert model.items["INT-903"].owner == "agent (mobile)"
    assert model.items["INT-904"].owner == "agent · clinical-reviewer"
    assert model.items["INT-910"].owner == "agent · legal-reviewer; sign-off: counsel"
    assert model.items["INT-907"].owner == "agent"


def test_label_only_owner_is_what_files11_shows() -> None:
    assert rl.owner_for(_row("INT-1", labels=["approval:human-clinical"])) == (
        "agent; sign-off: physician of record (D18 agent lane for simulated patients)"
    )
    assert rl.owner_for(_row("INT-1", status="awaiting-human")) == rl.NO_RECORD_OWNER
    assert rl.owner_for(_row("INT-1", labels=["blocked:contract"])) == "owner (contract)"


# ---- states -------------------------------------------------------------------


def test_states_combine_the_row_and_github() -> None:
    items = rl.build(_inputs()).items
    assert items["INT-901"].state == "done"
    assert items["INT-902"].state == "blocked"  # awaiting-human wins over an open PR
    assert "#51" in items["INT-902"].note and "conflicting" in items["INT-902"].note
    assert items["INT-903"].state == "in flight"
    assert items["INT-903"].note.startswith("#50 `int-903-screen`")
    assert items["INT-904"].state == "todo"
    assert items["INT-906"].state == "in flight"
    assert items["INT-908"].state == "withdrawn"
    assert items["INT-909"].state == "blocked"


def test_todo_is_ready_only_when_every_dependency_is_satisfied() -> None:
    items = rl.build(_inputs()).items
    # INT-904 depends on an awaiting-human row: satisfied (LOOP.md step 1).
    assert items["INT-904"].note == "ready"
    # INT-907 depends on a `doing` row: not satisfied, and the note names it.
    assert items["INT-907"].note == "waits on INT-906"


def test_drift_is_reported_not_repaired() -> None:
    drift = rl.build(_inputs()).drift
    assert drift.todo_with_open_pr == ["INT-903"]
    assert drift.doing_without_pr == ["INT-906"]
    assert drift.merged_not_done == [("INT-904", [41])]
    assert drift.done_issue_open == [("INT-901", [10])]
    assert drift.awaiting_without_record == []


def test_rowless_work_is_listed_from_the_snapshot() -> None:
    model = rl.build(_inputs())
    assert [p["number"] for p in model.prs_without_row] == [52]
    assert [p["number"] for p in model.prs_without_id] == [53]
    # INT-951 has a row on PR #52's branch, so only INT-960/961 have none anywhere.
    assert [i["id"] for i in model.issues_without_row] == ["INT-960", "INT-961"]


# ---- rendering ----------------------------------------------------------------


def test_render_counts_every_row_once_per_phase() -> None:
    block = rr.render(_inputs())
    assert "| P0 | 4 | 1 | 1 | 1 | 1 | 0 |" in block
    assert "| P1 | 4 | 0 | 1 | 1 | 1 | 1 |" in block
    assert "| P2 | 2 | 0 | 0 | 1 | 1 | 0 |" in block
    assert "| **all** | **10** | **1** | **2** | **3** | **3** | **1** |" in block


def test_render_is_deterministic_escapes_pipes_and_is_marked() -> None:
    a, b = rr.render(_inputs()), rr.render(_inputs())
    assert a == b
    assert a.startswith(rl.BEGIN) and a.rstrip("\n").endswith(rl.END)
    assert "a \\| pipe" in a
    assert "2026-10-16T06:00:00Z" in a and "`0123456789ab`" in a


def test_render_lists_remaining_items_but_not_done_ones() -> None:
    block = rr.render(_inputs())
    assert "| INT-903 |" in block and "| INT-902 |" in block
    assert "| INT-901 |" not in block  # done rows are counted, not listed


def test_splice_replaces_only_the_marked_section() -> None:
    doc = f"# Roadmap\n\nintro\n\n{rl.BEGIN}\nold\n{rl.END}\n\n## 0. facts\n"
    out = rl.splice(doc, f"{rl.BEGIN}\nnew\n{rl.END}\n")
    assert out == f"# Roadmap\n\nintro\n\n{rl.BEGIN}\nnew\n{rl.END}\n\n## 0. facts\n"


@pytest.mark.parametrize(
    "doc",
    ["# no markers\n", f"{rl.BEGIN}\n{rl.END}\n{rl.BEGIN}\n{rl.END}\n", f"{rl.END}\n{rl.BEGIN}\n"],
)
def test_splice_refuses_missing_doubled_or_reversed_markers(doc: str) -> None:
    with pytest.raises(rl.MarkerError):
        rl.splice(doc, f"{rl.BEGIN}\nnew\n{rl.END}\n")


def test_blanking_the_generated_section_keeps_the_hand_written_text_and_line_numbers() -> None:
    doc = f"hand 1\n{rl.BEGIN}\nrow naming a thing\nrow two\n{rl.END}\nhand 2 naming a thing\n"
    out = rl.blank_generated_section(doc)
    assert out.count("\n") == doc.count("\n")
    assert "row" not in out and rl.BEGIN not in out
    # near miss: the hand-written lines around the section are untouched
    assert out.splitlines()[0] == "hand 1"
    assert out.splitlines()[-1] == "hand 2 naming a thing"
    assert rl.blank_generated_section("no markers here\n") == "no markers here\n"


# ---- the CI check: committed output == generator output ---------------------


def test_committed_roadmap_matches_the_generator() -> None:
    out = subprocess.run(
        ["uv", "run", "python", "scripts/backlog/render_roadmap.py", "--check"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, (
        "files/05_ROADMAP.md's live status is stale — run `make backlog-render` "
        "and commit\n" + out.stdout + out.stderr
    )


def test_near_miss_a_hand_edit_inside_the_block_fails_the_check(tmp_path: Path) -> None:
    current = render_roadmap.ROADMAP_FILE.read_text(encoding="utf-8")
    edited = current.replace("| **all** |", "| **ALL** |", 1)
    assert edited != current
    target = tmp_path / "05_ROADMAP.md"
    target.write_text(edited, encoding="utf-8")
    assert render_roadmap.main(["--check", "--roadmap", str(target)]) == 1
    target.write_text(current, encoding="utf-8")
    assert render_roadmap.main(["--check", "--roadmap", str(target)]) == 0


def test_rendering_never_calls_github(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_a: object, **_k: object) -> None:
        raise AssertionError("the renderer must not run a subprocess (gh/git)")

    monkeypatch.setattr(subprocess, "run", refuse)
    monkeypatch.setattr(subprocess, "Popen", refuse)
    assert rl.BEGIN in render_roadmap.expected_document()


# ---- the snapshot step --------------------------------------------------------


class FakeRunner:
    """Answers the snapshot's gh/git reads from fixtures and records every call."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.base_yaml = "- id: INT-901\n- id: INT-902\n"
        self.branch_yaml = {"int-950-new": "- id: INT-901\n- id: INT-902\n- id: INT-950\n"}

    def __call__(self, args: list[str]) -> str:
        self.calls.append(args)
        if args[:3] == ["gh", "pr", "list"] and "open" in args:
            return json.dumps(
                [
                    {
                        "number": 52,
                        "title": "INT-950: a new thing",
                        "headRefName": "int-950-new",
                        "isDraft": True,
                        "mergeable": "UNKNOWN",
                    },
                    {
                        "number": 53,
                        "title": "fix: gone",
                        "headRefName": "deleted-branch",
                        "isDraft": False,
                        "mergeable": "MERGEABLE",
                    },
                ]
            )
        if args[:3] == ["gh", "pr", "list"]:
            return json.dumps(
                [
                    {"number": 41, "title": "INT-904: x"},
                    {"number": 40, "title": "INT-901: y"},
                    {"number": 39, "title": "chore: z"},
                ]
            )
        if args[:3] == ["gh", "issue", "list"]:
            return json.dumps(
                [
                    {"number": 62, "title": "INT-960: n", "labels": [{"name": "ph:P2"}]},
                    {"number": 63, "title": "INT-961: u", "labels": [{"name": "area:x"}]},
                ]
            )
        if args[:3] == ["git", "rev-parse", "origin/main"]:
            return "0123456789abcdef0123456789abcdef01234567\n"
        if args[:2] == ["git", "show"]:
            ref = args[2].split(":", 1)[0]
            if ref == "origin/main":
                return self.base_yaml
            branch = ref.removeprefix("origin/")
            if branch in self.branch_yaml:
                return self.branch_yaml[branch]
            raise snap.RefMissing(ref)
        raise AssertionError(f"unexpected command {args}")


def test_snapshot_reads_github_and_git_only_through_read_commands() -> None:
    runner = FakeRunner()
    data = snap.collect(runner, ["INT-901", "INT-902"], [], "2026-10-16T06:00:00Z")
    verbs = {tuple(c[:3]) for c in runner.calls}
    assert verbs <= {
        ("gh", "pr", "list"),
        ("gh", "issue", "list"),
        ("git", "rev-parse", "origin/main"),
    } | {("git", "show", c[2]) for c in runner.calls if c[:2] == ["git", "show"]}
    assert data["open_prs"][0]["rows_added"] == ["INT-950"]
    assert data["open_prs"][1]["rows_added"] is None  # the branch ref is gone
    assert data["merged_prs"] == {"INT-901": [40], "INT-904": [41]}
    assert data["open_issues"] == [
        {"number": 62, "title": "INT-960: n", "phase": "P2"},
        {"number": 63, "title": "INT-961: u", "phase": None},
    ]
    assert data["base"] == "0123456789abcdef0123456789abcdef01234567"


def test_snapshot_floor_only_rises() -> None:
    assert snap.ratchet(["INT-001", "INT-003"], ["INT-001", "INT-002", "INT-003"]) == [
        "INT-001",
        "INT-002",
        "INT-003",
    ]


def test_near_miss_snapshot_refuses_when_a_floor_row_disappeared() -> None:
    with pytest.raises(snap.FloorShrank, match="INT-003"):
        snap.ratchet(["INT-001", "INT-003"], ["INT-001", "INT-002"])


def test_snapshot_serialisation_is_stable() -> None:
    data = snap.collect(FakeRunner(), ["INT-902", "INT-901"], [], "2026-10-16T06:00:00Z")
    text = snap.dumps(data)
    assert text == snap.dumps(json.loads(text))
    assert text.endswith("\n")
    assert json.loads(text)["row_floor"] == ["INT-901", "INT-902"]


def test_committed_snapshot_is_well_formed() -> None:
    data = backlog_lib.load_snapshot()
    assert data["schema"] == 1 and data["repo"] == "ArioMoniri/intake"
    assert data["row_floor"] == sorted(set(data["row_floor"]))
    assert snap.dumps(data) == backlog_lib.SNAPSHOT_FILE.read_text(encoding="utf-8")


# ---- the derived count check (replaces the three hard-coded pins) ----------


def test_row_floor_check_passes_on_the_real_backlog() -> None:
    ids = [i["id"] for i in backlog_lib.load_issues()]
    floor = backlog_lib.load_snapshot()["row_floor"]
    assert backlog_lib.row_floor_violations(ids, floor) == []


def test_near_miss_a_vanished_row_fails_the_floor_check() -> None:
    floor = ["INT-001", "INT-002", "INT-003"]
    assert backlog_lib.row_floor_violations(["INT-001", "INT-003"], floor, minimum=2) == [
        "INT-002 is in the snapshot's row floor but has no row (rows are withdrawn, never removed)"
    ]


def test_near_miss_a_new_row_never_fails_the_floor_check() -> None:
    floor = ["INT-001", "INT-002"]
    ids = ["INT-001", "INT-002", "INT-003"]
    assert backlog_lib.row_floor_violations(ids, floor, minimum=2) == []


def test_near_miss_a_duplicated_or_shrunken_floor_fails() -> None:
    assert backlog_lib.row_floor_violations(["INT-001", "INT-001"], ["INT-001"], minimum=1) == [
        "duplicate row ids: INT-001"
    ]
    assert backlog_lib.row_floor_violations(["INT-001"], ["INT-001"], minimum=2) == [
        f"the snapshot's row floor holds 1 ids, below the minimum of 2 ({backlog_lib.__name__}"
        ".ROW_FLOOR_MINIMUM only rises)"
    ]


def test_files11_carries_an_owner_column() -> None:
    import render_backlog

    text = render_backlog.render()
    assert "| id | title | epic | depends on | labels | status | owner |" in text
    int043 = next(line for line in text.splitlines() if line.startswith("| INT-043 |"))
    assert "physician of record" in int043


def test_the_floor_minimum_is_the_count_the_three_pins_held() -> None:
    # 343 rows on main at 6cd8c988 (16 Oct 2026), counted three ways in
    # docs/evidence/INT-452.md before the pins were replaced.
    assert backlog_lib.ROW_FLOOR_MINIMUM >= 343

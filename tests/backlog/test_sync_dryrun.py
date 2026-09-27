"""INT-004 — GitHub sync (dry-run), templates, renderer, backlog-status.

Acceptance lines under test, verbatim:
  "scripts/backlog/sync_issues.py creates/updates GitHub issues via gh with
   labels ph:*, area:*, risk:*, approval:*, milestones P0..P3 and a Project
   board Backlog/Ready/In progress/In review/Blocked/Done"
  ".github/ISSUE_TEMPLATE/feature.yml + pull_request_template.md with the DoD
   checklist and mandatory links (issue, 10 §9 row, 06 legal codes, evidence file)"
  "docs/backlog/blockers.md format + `make backlog-status` report"

Dry-run with an injected existing-issues file makes the planner hermetic — no
gh, no network, still the same decision code the live sync runs.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]


def _plan(tmp_path: Path, existing: list[dict]) -> dict:
    ef = tmp_path / "existing.json"
    ef.write_text(json.dumps(existing), encoding="utf-8")
    out = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "scripts/backlog/sync_issues.py",
            "--dry-run",
            "--existing-json",
            str(ef),
            "--plan-json",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_dryrun_plans_creates_and_updates(tmp_path: Path) -> None:
    existing = [
        {
            "number": 1,
            "title": "INT-001: Monorepo bootstrap: workspaces, Makefile, pre-commit, compose.dev",
        },
        {"number": 3, "title": "INT-002: CI base + evidence gates"},
    ]
    plan = _plan(tmp_path, existing)
    actions = {a["id"]: a for a in plan["actions"]}
    # tracks test_schema.py (175 blueprint + added issues incl. INT-321 + INT-322 + INT-323)
    # tracks test_schema.py (175 blueprint + added issues incl. INT-321 + INT-322 + INT-323,
    # and INT-372 from the INT-354 consolidation)
    # and INT-370 from the INT-354 consolidation)
    # tracks test_schema.py (175 blueprint + added issues incl. INT-321 + INT-322 + INT-323
    # + INT-317, carried from int-demo by INT-354)
    # tracks test_schema.py (175 blueprint + added issues, latest INT-376)
    # + INT-318, the INT-354 slice S2 row)
    # + INT-380 and INT-381, split out of INT-121 and INT-124 by INT-124's PR
    # + INT-385 (record quantities in the locale's decimal separator, GitHub #635)
    # + INT-392, the session-deletion fix found on check-integration)
    # + INT-393, the Doctor Link erasure fix found by INT-392)
    # + INT-391 (every valid WebAuthn credential id admitted, GitHub #646)
    # + INT-386 (the typed rail, note, summary and FHIR narrative quantities, GitHub #638)
    # + INT-387 (the a11y conformance report re-rated after INT-361..363, GitHub #640)
    # + INT-397 (the last three SC 4.1.3 status lines are announced, GitHub #659)
    # + INT-406 (RED acknowledgement Safety inbox, invariant 49, GitHub #681)
    # + INT-407 (the 02 §2b visit lifecycle state machine, GitHub #684)
    assert len(actions) == 311
    assert actions["INT-001"]["action"] == "update"
    assert actions["INT-001"]["number"] == 1
    assert actions["INT-004"]["action"] == "create"


def test_dryrun_labels_and_milestones(tmp_path: Path) -> None:
    plan = _plan(tmp_path, [])
    actions = {a["id"]: a for a in plan["actions"]}
    assert "ph:P0" in actions["INT-001"]["labels"]
    assert actions["INT-001"]["milestone"] == "P0"
    assert "approval:human-clinical" in actions["INT-043"]["labels"]
    assert "gpu" in actions["INT-097"]["labels"]
    assert "blocked:contract" in actions["INT-097"]["labels"]
    assert actions["INT-097"]["milestone"] == "P3"
    # the board column set the project must carry
    expected_columns = ["Backlog", "Ready", "In progress", "In review", "Blocked", "Done"]
    assert plan["board_columns"] == expected_columns
    # every label the plan uses is declared so the sync can create them first
    used = {label for a in plan["actions"] for label in a["labels"]}
    assert used <= set(plan["labels"]), used - set(plan["labels"])


def test_issue_template_and_pr_template() -> None:
    feature = yaml.safe_load(
        (REPO / ".github" / "ISSUE_TEMPLATE" / "feature.yml").read_text(encoding="utf-8")
    )
    assert feature["name"]
    field_ids = {b.get("id") for b in feature["body"] if isinstance(b, dict)}
    assert {"acceptance", "phase", "legal", "sec_row"} <= field_ids

    pr = (REPO / ".github" / "pull_request_template.md").read_text(encoding="utf-8")
    for needle in ("Closes #", "docs/evidence/", "10 §9", "legal", "red run", "make check"):
        assert needle.lower() in pr.lower(), f"pull_request_template.md missing {needle}"


def test_files11_rendering_matches_backlog() -> None:
    out = subprocess.run(
        ["uv", "run", "python", "scripts/backlog/render_backlog.py", "--check"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, (
        "files/11_ISSUE_BACKLOG.md is stale — run `uv run python "
        "scripts/backlog/render_backlog.py` and commit\n" + out.stdout + out.stderr
    )


def test_backlog_status_report() -> None:
    out = subprocess.run(
        ["uv", "run", "python", "scripts/backlog/backlog_status.py", "--no-github"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, out.stderr
    for needle in ("P0", "done", "next", "blockers"):
        assert needle.lower() in out.stdout.lower(), f"backlog-status missing {needle}"

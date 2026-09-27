"""Sync docs/backlog/issues.yaml to GitHub: issues, labels, milestones, board.

Modes:
  --dry-run --existing-json FILE --plan-json
      Hermetic planning (no gh, no network): print the action plan as JSON.
  (live, default)
      Ensure labels + milestones exist, create/update one GitHub issue per
      backlog row (matched by the INT-xxx title prefix), and print board
      guidance. Uses `gh` (HB-I3).

The project board (Backlog/Ready/In progress/In review/Blocked/Done) is
attempted via `gh project`; if the token lacks the `project` scope the sync
reports exactly what the owner must run — it never fails the issue sync.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backlog_lib import labels_for, load_issues  # noqa: E402

REPO_SLUG = "ArioMoniri/intake"
BOARD_COLUMNS = ["Backlog", "Ready", "In progress", "In review", "Blocked", "Done"]
MILESTONES = ["P0", "P1", "P2", "P3"]

LABEL_COLOURS = {
    "ph:": "1d76db",
    "area:": "0e8a16",
    "risk:": "d93f0b",
    "approval:": "fbca04",
    "blocked:": "b60205",
    "live-smoke": "5319e7",
    "gpu": "5319e7",
}


def issue_body(issue: dict[str, Any]) -> str:
    lines = [
        f"Backlog: docs/backlog/issues.yaml → {issue['id']} "
        f"(epic {issue['epic']}, phase {issue['phase']}).",
        "",
        "### Acceptance",
    ]
    for a in issue.get("acceptance", []):
        lines.append(f"- [ ] {a}")
    if issue.get("depends_on"):
        lines += ["", "Depends on: " + ", ".join(issue["depends_on"])]
    if issue.get("tests"):
        lines += ["", "Tests: " + ", ".join(map(str, issue["tests"]))]
    if issue.get("legal"):
        lines += ["", f"Legal codes (files/06 §1): {issue['legal']}"]
    if issue.get("sec_row"):
        lines += ["", f"Security row (files/10 §9): {issue['sec_row']}"]
    lines += ["", f"Evidence (on close): docs/evidence/{issue['id']}.md"]
    return "\n".join(lines)


def owned_issue_numbers(existing: list[dict[str, Any]]) -> dict[str, int]:
    """The GitHub issue number the sync edits for each backlog id.

    Matched on the 7-character `INT-xxx` title prefix; when several issues
    share it the last one listed wins. `gh issue list` lists newest first, so
    the sync owns the OLDEST issue carrying the id — every other one is a
    duplicate (scripts/backlog/reconcile.py reports them).
    """
    by_prefix: dict[str, int] = {}
    for e in existing:
        title = e.get("title", "")
        if title[:7].startswith("INT-"):
            by_prefix[title[:7]] = e["number"]
    return by_prefix


def build_plan(issues: list[dict[str, Any]], existing: list[dict[str, Any]]) -> dict[str, Any]:
    by_prefix = owned_issue_numbers(existing)

    actions = []
    used_labels: set[str] = set()
    for issue in issues:
        labels = labels_for(issue)
        used_labels.update(labels)
        number = by_prefix.get(issue["id"])
        actions.append(
            {
                "id": issue["id"],
                "action": "update" if number is not None else "create",
                "number": number,
                "title": f"{issue['id']}: {issue['title']}",
                "labels": labels,
                "milestone": issue["phase"],
                "state": "closed" if issue.get("status") in {"done", "withdrawn"} else "open",
                "body": issue_body(issue),
            }
        )
    return {
        "actions": actions,
        "labels": sorted(used_labels),
        "milestones": MILESTONES,
        "board_columns": BOARD_COLUMNS,
    }


def gh(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=check)


def fetch_existing() -> list[dict[str, Any]]:
    out = gh(
        "issue",
        "list",
        "-R",
        REPO_SLUG,
        "--state",
        "all",
        "--limit",
        "500",
        "--json",
        "number,title",
    )
    return json.loads(out.stdout)


def ensure_labels(labels: list[str]) -> None:
    for label in labels:
        colour = "cccccc"
        for prefix, c in LABEL_COLOURS.items():
            if label.startswith(prefix) or label == prefix:
                colour = c
                break
        gh(
            "label",
            "create",
            label,
            "-R",
            REPO_SLUG,
            "--color",
            colour,
            "--force",
            check=False,
        )


def ensure_milestones() -> dict[str, int]:
    out = gh("api", f"repos/{REPO_SLUG}/milestones?state=all&per_page=100")
    have = {m["title"]: m["number"] for m in json.loads(out.stdout)}
    for title in MILESTONES:
        if title not in have:
            created = gh(
                "api",
                f"repos/{REPO_SLUG}/milestones",
                "-f",
                f"title={title}",
                "-f",
                f"description=Phase {title} (gate-driven, files/05 §1a)",
            )
            have[title] = json.loads(created.stdout)["number"]
    return have


def apply_plan(plan: dict[str, Any]) -> None:
    ensure_labels(plan["labels"])
    ensure_milestones()
    total = len(plan["actions"])
    for n, action in enumerate(plan["actions"], 1):
        label_args: list[str] = []
        for label in action["labels"]:
            label_args += ["--add-label" if action["action"] == "update" else "--label", label]
        if action["action"] == "create":
            out = gh(
                "issue",
                "create",
                "-R",
                REPO_SLUG,
                "--title",
                action["title"],
                "--body",
                action["body"],
                "--milestone",
                action["milestone"],
                *label_args,
                check=False,
            )
            status = "created" if out.returncode == 0 else f"FAILED: {out.stderr.strip()[:120]}"
        else:
            out = gh(
                "issue",
                "edit",
                str(action["number"]),
                "-R",
                REPO_SLUG,
                "--title",
                action["title"],
                "--body",
                action["body"],
                "--milestone",
                action["milestone"],
                *label_args,
                check=False,
            )
            status = "updated" if out.returncode == 0 else f"FAILED: {out.stderr.strip()[:120]}"
        print(f"[{n}/{total}] {action['id']} {status}", flush=True)
        time.sleep(0.4)  # stay far from the secondary rate limit

    board = gh("project", "list", "--owner", "ArioMoniri", check=False)
    if board.returncode != 0:
        print(
            "project board: token lacks the `project` scope — owner: run "
            "`gh auth refresh -s project` then `scripts/backlog/sync_issues.py --board-only`"
        )


def ensure_board() -> None:
    lst = gh("project", "list", "--owner", "ArioMoniri", "--format", "json", check=False)
    if lst.returncode != 0:
        print("cannot reach projects — `gh auth refresh -s project` first")
        return
    projects = json.loads(lst.stdout).get("projects", [])
    title = "INTAKE backlog"
    proj = next((p for p in projects if p["title"] == title), None)
    if proj is None:
        created = gh(
            "project",
            "create",
            "--owner",
            "ArioMoniri",
            "--title",
            title,
            "--format",
            "json",
        )
        proj = json.loads(created.stdout)
        print(f"created project {proj['number']}")
    gh(
        "project",
        "field-create",
        str(proj["number"]),
        "--owner",
        "ArioMoniri",
        "--name",
        "Status2",
        "--data-type",
        "SINGLE_SELECT",
        "--single-select-options",
        ",".join(BOARD_COLUMNS),
        check=False,
    )
    print(f"board ready: project {proj['number']} with columns {', '.join(BOARD_COLUMNS)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--existing-json", type=Path)
    parser.add_argument("--plan-json", action="store_true")
    parser.add_argument("--board-only", action="store_true")
    args = parser.parse_args()

    if args.board_only:
        ensure_board()
        return 0

    issues = load_issues()
    if args.dry_run:
        existing = (
            json.loads(args.existing_json.read_text(encoding="utf-8")) if args.existing_json else []
        )
        plan = build_plan(issues, existing)
        if args.plan_json:
            print(json.dumps(plan))
        else:
            creates = sum(1 for a in plan["actions"] if a["action"] == "create")
            print(f"plan: {creates} creates, {len(plan['actions']) - creates} updates")
        return 0

    plan = build_plan(issues, fetch_existing())
    apply_plan(plan)
    ensure_board()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

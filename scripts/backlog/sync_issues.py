"""Sync docs/backlog/issues.yaml to GitHub: issues, labels, milestones, board.

Modes:
  --dry-run [--existing-json FILE] [--plan-json] [--issues-file FILE]
      Print the action plan and change nothing: creates/updates, then every
      issue the live run would close or reopen. With --existing-json the
      listing comes from FILE (hermetic: no gh, no network); without it the
      listing is read from GitHub, read-only.
  (live, default: `make backlog-sync`, run by the operator)
      Ensure labels + milestones exist, create/update one GitHub issue per
      backlog row (matched by the INT-xxx title prefix), close the owned issue
      of a `done` row (reason: completed), reopen it for a row moved back from
      `done`, and print board guidance. Uses `gh` (HB-I3).

INT-405: the listing pages through GitHub's REST issue list until a page comes
back short, and refuses (ListingIncomplete, nothing changed) unless it holds
exactly as many issues as GitHub's own count. A lost page would hide issues,
and the oldest ones are the ones the sync owns.

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
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backlog_lib import ISSUES_FILE, labels_for, load_issues  # noqa: E402

REPO_SLUG = "ArioMoniri/intake"
BOARD_COLUMNS = ["Backlog", "Ready", "In progress", "In review", "Blocked", "Done"]
MILESTONES = ["P0", "P1", "P2", "P3"]
PER_PAGE = 100  # the REST maximum
ISSUE_COUNT_QUERY = (
    "query($owner: String!, $name: String!) "
    "{ repository(owner: $owner, name: $name) { issues { totalCount } } }"
)

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
    share it the last one listed wins. `fetch_existing` (like `gh issue list`)
    lists newest first, so the sync owns the OLDEST issue carrying the id —
    every other one is a duplicate (scripts/backlog/reconcile.py reports them).
    """
    by_prefix: dict[str, int] = {}
    for e in existing:
        title = e.get("title", "")
        if title[:7].startswith("INT-"):
            by_prefix[title[:7]] = e["number"]
    return by_prefix


def state_change(status: str, creating: bool, issue_state: str | None) -> str | None:
    """What the sync does to the owned issue's open/closed state (INT-405).

    A `done` row closes its issue (reason: completed), including one it has
    just created. A row that is not done (todo, doing, blocked,
    awaiting-human) reopens a closed issue: the row moved back from `done`.
    `withdrawn` is left as it is either way, and so is an issue whose state the
    listing does not carry. Only the owned issue is ever passed in.
    """
    if status == "done":
        return "close" if creating or issue_state == "OPEN" else None
    if status == "withdrawn":
        return None
    return "reopen" if issue_state == "CLOSED" else None


def build_plan(issues: list[dict[str, Any]], existing: list[dict[str, Any]]) -> dict[str, Any]:
    by_prefix = owned_issue_numbers(existing)
    states = {e["number"]: str(e["state"]).upper() for e in existing if e.get("state")}

    actions = []
    used_labels: set[str] = set()
    for issue in issues:
        labels = labels_for(issue)
        used_labels.update(labels)
        number = by_prefix.get(issue["id"])
        status = str(issue.get("status", "todo"))
        issue_state = states.get(number) if number is not None else None
        actions.append(
            {
                "id": issue["id"],
                "action": "update" if number is not None else "create",
                "number": number,
                "title": f"{issue['id']}: {issue['title']}",
                "labels": labels,
                "milestone": issue["phase"],
                "status": status,
                "state": "closed" if status in {"done", "withdrawn"} else "open",
                "issue_state": issue_state,
                "state_change": state_change(status, number is None, issue_state),
                "body": issue_body(issue),
            }
        )
    return {
        "actions": actions,
        "labels": sorted(used_labels),
        "milestones": MILESTONES,
        "board_columns": BOARD_COLUMNS,
    }


def describe_state_changes(plan: dict[str, Any]) -> list[str]:
    """The dry-run's list of every close and reopen the live run would make."""
    lines: list[str] = []
    closes = reopens = after_create = 0
    for a in plan["actions"]:
        if a["state_change"] is None:
            continue
        if a["number"] is None:
            after_create += 1
            lines.append(f"close {a['id']} once created (row {a['status']})")
        elif a["state_change"] == "close":
            closes += 1
            lines.append(f"close #{a['number']} {a['id']} (row {a['status']}, issue open)")
        else:
            reopens += 1
            lines.append(f"reopen #{a['number']} {a['id']} (row {a['status']}, issue closed)")
    head = f"state: {closes} to close, {reopens} to reopen, {after_create} to close once created"
    return [head, *lines]


def gh(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=check)


class GhRunner(Protocol):
    def __call__(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]: ...


class IssueListing(Protocol):
    def page(self, number: int, per_page: int) -> list[dict[str, Any]]: ...

    def total(self) -> int: ...


class ListingIncomplete(RuntimeError):
    """The paged listing does not hold every issue GitHub counts; nothing is synced."""


class GhIssueClient:
    """GitHub's REST issue listing and its GraphQL issue count, through `gh api`.

    Oldest first: an issue filed while the listing runs lands on the last
    page instead of shifting every earlier one.
    """

    def __init__(self, run: GhRunner) -> None:
        self._run = run

    def page(self, number: int, per_page: int) -> list[dict[str, Any]]:
        query = f"state=all&sort=created&direction=asc&per_page={per_page}&page={number}"
        out = self._run("api", f"repos/{REPO_SLUG}/issues?{query}")
        items: list[dict[str, Any]] = json.loads(out.stdout)
        return items

    def total(self) -> int:
        owner, name = REPO_SLUG.split("/")
        out = self._run(
            "api",
            "graphql",
            "-f",
            f"query={ISSUE_COUNT_QUERY}",
            "-f",
            f"owner={owner}",
            "-f",
            f"name={name}",
        )
        return int(json.loads(out.stdout)["data"]["repository"]["issues"]["totalCount"])


def fetch_existing(listing: IssueListing | None = None) -> list[dict[str, Any]]:
    """Every issue on the repo, newest first, as `{number, title, state}`.

    Pages until one comes back short. Pull requests share the REST listing
    (and the `INT-xxx:` titles), so they are dropped. Raises ListingIncomplete
    when a full page lists nothing new, or when the issues listed are not
    exactly GitHub's count, taken before and after the listing.
    """
    source = listing if listing is not None else GhIssueClient(gh)
    before = source.total()
    seen: set[int] = set()
    issues: dict[int, dict[str, Any]] = {}
    number = 0
    while True:
        number += 1
        items = source.page(number, PER_PAGE)
        fresh = [i for i in items if int(i["number"]) not in seen]
        if len(items) == PER_PAGE and not fresh:
            raise ListingIncomplete(
                f"page {number} lists only items already listed; nothing was changed, rerun"
            )
        for item in fresh:
            n = int(item["number"])
            seen.add(n)
            if "pull_request" not in item:
                state = str(item["state"]).upper()
                issues[n] = {"number": n, "title": str(item["title"]), "state": state}
        if len(items) < PER_PAGE:
            break
    after = source.total()
    if not before == after == len(issues):
        moved = f" (it was {before} when the listing began)" if before != after else ""
        raise ListingIncomplete(
            f"listed {len(issues)} issues over {number} pages, GitHub counts {after}{moved}; "
            "nothing was changed, rerun"
        )
    return sorted(issues.values(), key=lambda e: int(e["number"]), reverse=True)


def ensure_labels(labels: list[str], run: GhRunner = gh) -> None:
    for label in labels:
        colour = "cccccc"
        for prefix, c in LABEL_COLOURS.items():
            if label.startswith(prefix) or label == prefix:
                colour = c
                break
        run(
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


def ensure_milestones(run: GhRunner = gh) -> dict[str, int]:
    out = run("api", f"repos/{REPO_SLUG}/milestones?state=all&per_page=100")
    have = {m["title"]: m["number"] for m in json.loads(out.stdout)}
    for title in MILESTONES:
        if title not in have:
            created = run(
                "api",
                f"repos/{REPO_SLUG}/milestones",
                "-f",
                f"title={title}",
                "-f",
                f"description=Phase {title} (gate-driven, files/05 §1a)",
            )
            have[title] = json.loads(created.stdout)["number"]
    return have


def _failed(out: subprocess.CompletedProcess[str]) -> str:
    return f"FAILED: {out.stderr.strip()[:120]}"


def _created_number(stdout: str) -> int | None:
    """`gh issue create` prints the new issue's URL; its last segment is the number."""
    tail = stdout.strip().rsplit("/", 1)[-1]
    return int(tail) if tail.isdigit() else None


def _apply_state(change: str, number: int | None, run: GhRunner) -> str:
    """Close (reason: completed) or reopen the owned issue; never any other."""
    if number is None:
        return f"; {change} skipped: gh printed no issue number"
    if change == "close":
        out = run(
            "issue", "close", str(number), "-R", REPO_SLUG, "--reason", "completed", check=False
        )
    else:
        out = run("issue", "reopen", str(number), "-R", REPO_SLUG, check=False)
    if out.returncode != 0:
        return f"; {change} #{number} {_failed(out)}"
    return f"; {'closed' if change == 'close' else 'reopened'} #{number}"


def apply_plan(
    plan: dict[str, Any], run: GhRunner = gh, pause: Callable[[float], None] = time.sleep
) -> None:
    ensure_labels(plan["labels"], run)
    ensure_milestones(run)
    total = len(plan["actions"])
    for n, action in enumerate(plan["actions"], 1):
        creating = action["action"] == "create"
        label_args: list[str] = []
        for label in action["labels"]:
            label_args += ["--label" if creating else "--add-label", label]
        fields = ["--title", action["title"], "--body", action["body"]]
        fields += ["--milestone", action["milestone"], *label_args]
        if creating:
            out = run("issue", "create", "-R", REPO_SLUG, *fields, check=False)
            number = _created_number(out.stdout) if out.returncode == 0 else None
            status = "created" if out.returncode == 0 else _failed(out)
        else:
            number = action["number"]
            out = run("issue", "edit", str(number), "-R", REPO_SLUG, *fields, check=False)
            status = "updated" if out.returncode == 0 else _failed(out)
        if action["state_change"] is not None and (out.returncode == 0 or not creating):
            status += _apply_state(action["state_change"], number, run)
        print(f"[{n}/{total}] {action['id']} {status}", flush=True)
        pause(0.4)  # stay far from the secondary rate limit

    board = run("project", "list", "--owner", "ArioMoniri", check=False)
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
    parser.add_argument("--existing-json", type=Path, help="with --dry-run: the listing to plan on")
    parser.add_argument("--plan-json", action="store_true")
    parser.add_argument("--board-only", action="store_true")
    parser.add_argument("--issues-file", type=Path, default=ISSUES_FILE)
    args = parser.parse_args()

    if args.board_only:
        ensure_board()
        return 0
    if args.existing_json and not args.dry_run:
        parser.error("--existing-json plans on a saved listing, so it needs --dry-run")

    issues = load_issues(args.issues_file)
    try:
        existing: list[dict[str, Any]] = (
            json.loads(args.existing_json.read_text(encoding="utf-8"))
            if args.existing_json
            else fetch_existing()
        )
    except ListingIncomplete as err:
        print(f"backlog sync refused: {err}", file=sys.stderr)
        return 1
    plan = build_plan(issues, existing)

    if args.dry_run:
        if args.plan_json:
            print(json.dumps(plan))
        else:
            creates = sum(1 for a in plan["actions"] if a["action"] == "create")
            print(f"plan: {creates} creates, {len(plan['actions']) - creates} updates")
            print("\n".join(describe_state_changes(plan)))
        return 0

    apply_plan(plan)
    ensure_board()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

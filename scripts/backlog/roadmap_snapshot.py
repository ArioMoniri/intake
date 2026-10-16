"""INT-452 — capture the GitHub state the roadmap renders from, offline.

`make roadmap-snapshot` runs this after `git fetch origin`. It is the only step
in the roadmap pipeline that calls GitHub, and it only reads:

  gh pr list --state open      number, title, branch, draft, mergeable
  gh pr list --state merged    number, title (an `INT-xxx:` title maps to its id)
  gh issue list --state open   number, title, ph:* label
  git rev-parse origin/main    the base the branch rows are measured against
  git show <ref>:docs/backlog/issues.yaml
                               which row ids each open PR's branch adds

It writes docs/backlog/github_snapshot.json (sorted keys, stable order) and
raises the row floor: the snapshot's `row_floor` is the union of the previous
floor and every id with a row now. It refuses (FloorShrank, nothing written)
when an id in the previous floor has lost its row, because rows are withdrawn,
never removed (backlog_lib.row_floor_violations is the CI side of that rule).

Every command goes through a runner callable, so tests pass a fake one and
never reach GitHub. CI never runs this script; it renders from the commit.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backlog_lib import REPO, SNAPSHOT_FILE, load_issues, load_snapshot  # noqa: E402
from roadmap_lib import title_id  # noqa: E402
from sync_issues import REPO_SLUG  # noqa: E402

SCHEMA = 1
ISSUES_PATH = "docs/backlog/issues.yaml"
BASE_REF = "origin/main"
LIMITS = {"open_prs": 500, "merged_prs": 5000, "open_issues": 2000}
ROW_ID_RE = re.compile(r"^- id: (INT-\d{3})\s*$", re.M)

Runner = Callable[[list[str]], str]


class CommandFailed(RuntimeError):
    """A gh or git read failed."""


class RefMissing(CommandFailed):
    """`git show` found no such ref or path (a deleted or unfetched branch)."""


class FloorShrank(ValueError):
    """An id in the previous snapshot's row floor has no row any more."""


def run(args: list[str]) -> str:
    out = subprocess.run(args, cwd=REPO, capture_output=True, text=True)
    if out.returncode != 0:
        if args[:2] == ["git", "show"]:
            raise RefMissing(args[2])
        raise CommandFailed(f"{' '.join(args[:3])} exited {out.returncode}: {out.stderr[:300]}")
    return out.stdout


def ratchet(previous: list[str], current: list[str]) -> list[str]:
    missing = sorted(set(previous) - set(current))
    if missing:
        raise FloorShrank(
            "rows vanished since the last snapshot (withdraw a row, never remove it): "
            + ", ".join(missing)
        )
    return sorted(set(previous) | set(current))


def _listing(runner: Runner, kind: str, args: list[str]) -> list[dict[str, Any]]:
    limit = LIMITS[kind]
    data: list[dict[str, Any]] = json.loads(runner([*args, "--limit", str(limit)]))
    if len(data) >= limit:
        raise CommandFailed(f"{kind}: {len(data)} entries reached --limit {limit}; raise it")
    return data


def _row_ids(runner: Runner, ref: str) -> set[str]:
    return set(ROW_ID_RE.findall(runner(["git", "show", f"{ref}:{ISSUES_PATH}"])))


def _phase(labels: list[dict[str, Any]]) -> str | None:
    phases = sorted(str(lab["name"])[3:] for lab in labels if str(lab["name"]).startswith("ph:"))
    return phases[0] if phases else None


def collect(
    runner: Runner, row_ids: list[str], previous_floor: list[str], captured_at: str
) -> dict[str, Any]:
    base = runner(["git", "rev-parse", BASE_REF]).strip()
    gh = ["-R", REPO_SLUG]
    open_prs = _listing(
        runner,
        "open_prs",
        [
            "gh",
            "pr",
            "list",
            *gh,
            "--state",
            "open",
            "--json",
            "number,title,headRefName,isDraft,mergeable",
        ],
    )
    merged = _listing(
        runner,
        "merged_prs",
        ["gh", "pr", "list", *gh, "--state", "merged", "--json", "number,title"],
    )
    issues = _listing(
        runner,
        "open_issues",
        ["gh", "issue", "list", *gh, "--state", "open", "--json", "number,title,labels"],
    )
    base_ids = _row_ids(runner, BASE_REF)
    prs = []
    for pr in sorted(open_prs, key=lambda p: int(p["number"])):
        try:
            added: list[str] | None = sorted(
                _row_ids(runner, f"origin/{pr['headRefName']}") - base_ids
            )
        except CommandFailed:
            added = None
        prs.append(
            {
                "number": int(pr["number"]),
                "title": str(pr["title"]),
                "branch": str(pr["headRefName"]),
                "draft": bool(pr.get("isDraft")),
                "mergeable": str(pr.get("mergeable") or "UNKNOWN"),
                "rows_added": added,
            }
        )
    merged_by_id: dict[str, list[int]] = {}
    for pr in merged:
        match = re.match(r"(INT-\d{3}):", str(pr.get("title", "")))
        if match:
            merged_by_id.setdefault(match.group(1), []).append(int(pr["number"]))
    return {
        "schema": SCHEMA,
        "repo": REPO_SLUG,
        "captured_at": captured_at,
        "base": base,
        "row_floor": ratchet(previous_floor, row_ids),
        "open_prs": prs,
        "open_issues": sorted(
            (
                {"number": int(i["number"]), "title": str(i["title"]), "phase": _phase(i["labels"])}
                for i in issues
                if title_id(str(i["title"])) is not None
            ),
            key=lambda i: int(i["number"]),
        ),
        "merged_prs": {k: sorted(v) for k, v in sorted(merged_by_id.items())},
    }


def dumps(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=SNAPSHOT_FILE)
    args = parser.parse_args(argv)
    out: Path = args.out
    previous = load_snapshot(out)["row_floor"] if out.is_file() else []
    row_ids = [r["id"] for r in load_issues()]
    captured_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        data = collect(run, row_ids, previous, captured_at)
    except (CommandFailed, FloorShrank) as exc:
        print(f"roadmap snapshot refused, nothing written: {exc}", file=sys.stderr)
        return 1
    out.write_text(dumps(data), encoding="utf-8")
    print(
        f"wrote {out}: {len(data['open_prs'])} open PRs, {len(data['open_issues'])} open INT "
        f"issues, {len(data['merged_prs'])} ids with merged PRs, row floor {len(data['row_floor'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

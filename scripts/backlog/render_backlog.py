"""Render docs/backlog/issues.yaml into files/11_ISSUE_BACKLOG.md, and the roadmap.

files/11 is defined as the human-readable rendering of issues.yaml (07 §3.11);
a test diffs them so the two can never drift. INT-452: every row carries an
owner (scripts/backlog/roadmap_lib.owner_for, from its labels alone), and the
same command re-renders the live status section of files/05_ROADMAP.md
(scripts/backlog/render_roadmap.py), so one habit keeps both current.
`--check` exits 1 when either is stale.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render_roadmap  # noqa: E402
from backlog_lib import REPO, load_issues  # noqa: E402
from roadmap_lib import owner_for  # noqa: E402

TARGET = REPO / "files" / "11_ISSUE_BACKLOG.md"


def render() -> str:
    issues = load_issues()
    counts = Counter(i["phase"] for i in issues)
    status_counts = Counter(i.get("status", "todo") for i in issues)
    lines = [
        "# 11 · ISSUE BACKLOG — generated rendering, do not edit by hand",
        "",
        "> Generated from `docs/backlog/issues.yaml` by `scripts/backlog/render_backlog.py`",
        "> (INT-004). Regenerate with `uv run python scripts/backlog/render_backlog.py`;",
        "> a CI test diffs the two. The YAML is the source of record; the GitHub issues",
        "> are its sync target. One issue == one PR (`07 §3.11`). The owner column is",
        "> who acts next, from the row's labels (`scripts/backlog/roadmap_lib.py`); the",
        "> live status with GitHub state and named blocker owners is the generated",
        "> section of `files/05_ROADMAP.md` (INT-452).",
        "",
        f"**{len(issues)} issues.** By phase: "
        + " · ".join(f"{p} {counts[p]}" for p in ("P0", "P1", "P2", "P3"))
        + ". By status: "
        + " · ".join(f"{s} {n}" for s, n in sorted(status_counts.items()))
        + ".",
        "",
    ]
    for phase in ("P0", "P1", "P2", "P3"):
        lines += [
            f"## {phase}",
            "",
            "| id | title | epic | depends on | labels | status | owner |",
            "|---|---|---|---|---|---|---|",
        ]
        for i in issues:
            if i["phase"] != phase:
                continue
            deps = ", ".join(i.get("depends_on", [])) or "—"
            labels = ", ".join(i.get("labels", [])) or "—"
            title = str(i["title"]).replace("|", "\\|")
            lines.append(
                f"| {i['id']} | {title} | {i['epic']} | {deps} | {labels} "
                f"| {i.get('status', 'todo')} | {owner_for(i)} |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    content = render()
    if args.check:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        stale = 0
        if current != content:
            print("files/11_ISSUE_BACKLOG.md is stale relative to issues.yaml")
            stale = 1
        else:
            print("files/11 matches issues.yaml")
        return render_roadmap.main(["--check"]) or stale
    TARGET.write_text(content, encoding="utf-8")
    print(f"wrote {TARGET} ({len(content.splitlines())} lines)")
    return render_roadmap.main([])


if __name__ == "__main__":
    raise SystemExit(main())

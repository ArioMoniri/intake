"""`make backlog-status` — phase progress, next Ready issues, blockers,
awaiting-human work with HUMAN_BLOCKERS ids. `--no-github` skips `gh pr list`
(used by tests and offline runs)."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backlog_lib import (  # noqa: E402
    REPO,
    awaiting_human,
    blocked,
    load_issues,
    ready_issues,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-github", action="store_true")
    args = parser.parse_args()

    issues = load_issues()

    print("phase progress:")
    for phase in ("P0", "P1", "P2", "P3"):
        in_phase = [i for i in issues if i["phase"] == phase]
        by_status = Counter(i.get("status", "todo") for i in in_phase)
        done = by_status.get("done", 0) + by_status.get("withdrawn", 0)
        detail = ", ".join(f"{s}={n}" for s, n in sorted(by_status.items()))
        print(f"  {phase}: {done}/{len(in_phase)} done ({detail})")

    print("\nnext 5 ready issues:")
    for issue in ready_issues(issues)[:5]:
        print(f"  {issue['id']} [{issue['phase']}] {issue['title']}")

    waiting = awaiting_human(issues)
    print(f"\nawaiting-human ({len(waiting)}):")
    for issue in waiting:
        labels = ", ".join(
            label for label in issue.get("labels", []) if label.startswith("approval:")
        )
        print(f"  {issue['id']} {labels or ''}".rstrip())

    blocked_issues = blocked(issues)
    print(f"\nblocked ({len(blocked_issues)}):")
    for issue in blocked_issues:
        labels = ", ".join(
            label for label in issue.get("labels", []) if label.startswith("blocked:")
        )
        print(f"  {issue['id']} {labels}")

    blockers_md = (REPO / "docs" / "backlog" / "blockers.md").read_text(encoding="utf-8")
    rows = [
        line
        for line in blockers_md.splitlines()
        if line.startswith("| INT") or line.startswith("| lic")
    ]
    print(
        f"\nblockers file (docs/backlog/blockers.md): {len(rows)} row(s); "
        "HUMAN_BLOCKERS.md is the register"
    )

    if not args.no_github:
        out = subprocess.run(
            ["gh", "pr", "list", "-R", "ArioMoniri/intake", "--state", "open"],
            capture_output=True,
            text=True,
        )
        print("\nopen PRs:")
        print(out.stdout.strip() or "  (none or gh unavailable)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

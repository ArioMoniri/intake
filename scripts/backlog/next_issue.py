"""Print the next Ready issue id per LOOP.md step 1 — or the exact terminal
state: DONE (nothing left) / WAITING_HUMAN with the ids the human must act on."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backlog_lib import awaiting_human, blocked, load_issues, select_next  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, default=None)
    args = parser.parse_args()

    issues = load_issues(args.file)
    nxt = select_next(issues)
    if nxt is not None:
        print(nxt["id"])
        return 0

    todo_left = [i for i in issues if i.get("status", "todo") in {"todo", "doing"}]
    waiting = awaiting_human(issues)
    if waiting or (todo_left and all(b.get("status") != "todo" or True for b in todo_left)):
        if waiting:
            ids = ", ".join(i["id"] for i in waiting)
            print(f"WAITING_HUMAN: {ids}")
            return 0
    if todo_left:
        ids = ", ".join(i["id"] for i in blocked(issues)) or "unresolvable dependencies"
        print(f"BLOCKED: {ids}")
        return 0
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

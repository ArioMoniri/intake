"""INT-452 — render the live status section of files/05_ROADMAP.md.

The section between roadmap_lib.BEGIN and roadmap_lib.END is generated from
docs/backlog/issues.yaml, docs/backlog/epics.yaml, files/HUMAN_BLOCKERS.md,
docs/backlog/blockers.md and the committed GitHub snapshot
docs/backlog/github_snapshot.json. The rest of files/05 is hand-written and is
left exactly as it is. This script reads files only: GitHub is reached solely
by `make roadmap-snapshot` (scripts/backlog/roadmap_snapshot.py), so CI renders
from what is committed.

  uv run python scripts/backlog/render_roadmap.py          # rewrite the section
  uv run python scripts/backlog/render_roadmap.py --check  # exit 1 when stale

`make backlog-render` (scripts/backlog/render_backlog.py) runs this too, so the
command that regenerates files/11 regenerates the roadmap with it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import roadmap_lib as rl  # noqa: E402
import roadmap_render  # noqa: E402
from backlog_lib import ISSUES_FILE, REPO, SNAPSHOT_FILE, load_issues, load_snapshot  # noqa: E402

ROADMAP_FILE = REPO / "files" / "05_ROADMAP.md"
EPICS_FILE = REPO / "docs" / "backlog" / "epics.yaml"
HUMAN_BLOCKERS_FILE = REPO / "files" / "HUMAN_BLOCKERS.md"
BLOCKERS_FILE = REPO / "docs" / "backlog" / "blockers.md"


def load_inputs(snapshot: Path = SNAPSHOT_FILE, issues: Path = ISSUES_FILE) -> rl.Inputs:
    return rl.Inputs(
        rows=load_issues(issues),
        epics=yaml.safe_load(EPICS_FILE.read_text(encoding="utf-8")),
        snapshot=load_snapshot(snapshot),
        human_blockers_md=HUMAN_BLOCKERS_FILE.read_text(encoding="utf-8"),
        blockers_md=BLOCKERS_FILE.read_text(encoding="utf-8"),
        row_texts=rl.row_texts(issues.read_text(encoding="utf-8")),
    )


def expected_document(roadmap: Path = ROADMAP_FILE, snapshot: Path = SNAPSHOT_FILE) -> str:
    """files/05 as it must read: its own text with the generated section re-rendered."""
    block = roadmap_render.render(load_inputs(snapshot))
    return rl.splice(roadmap.read_text(encoding="utf-8"), block)


def check(roadmap: Path = ROADMAP_FILE, snapshot: Path = SNAPSHOT_FILE) -> bool:
    return roadmap.read_text(encoding="utf-8") == expected_document(roadmap, snapshot)


def write(roadmap: Path = ROADMAP_FILE, snapshot: Path = SNAPSHOT_FILE) -> None:
    roadmap.write_text(expected_document(roadmap, snapshot), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit 1 when the section is stale")
    parser.add_argument("--roadmap", type=Path, default=ROADMAP_FILE)
    parser.add_argument("--snapshot", type=Path, default=SNAPSHOT_FILE)
    args = parser.parse_args(argv)
    if args.check:
        if not check(args.roadmap, args.snapshot):
            print(f"{args.roadmap}: the generated live status is stale — run `make backlog-render`")
            return 1
        print(f"{args.roadmap}: the generated live status matches the backlog and the snapshot")
        return 0
    write(args.roadmap, args.snapshot)
    print(f"wrote the generated live status of {args.roadmap}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

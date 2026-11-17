"""INT-396 — reconcile docs/backlog/issues.yaml with what actually merged.

For every backlog row this reports:
  * its merged PRs, meaning those whose title starts `INT-xxx:`, and whether
    each body says `Closes #n` or only `Refs #n`;
  * the GitHub issues carrying the id and their states: which one the backlog
    sync owns (`sync_issues.owned_issue_numbers`, the sync's own mapping) and
    which are duplicates;
  * whether docs/evidence/INT-xxx.md exists, and whether it declares a clause
    `PENDING` or `NOT MET` (the evidence files' own status words);
  * every docs/backlog/blockers.md row or section, and every open
    files/HUMAN_BLOCKERS.md row, that names the id.

It then recommends. The rules never guess:
  * `done` (plus `evidence:`) only when a merged `INT-xxx:` PR says `Closes #n`
    for the issue the sync owns, that issue is closed, the evidence file
    exists and declares nothing `PENDING` or `NOT MET`, and no blocker names
    the id;
  * an `awaiting-human` row keeps its status, with its blockers named;
  * a `done` row with no `evidence:` gains the key when the file exists and
    is listed, never given a fabricated file, when it does not;
  * a `todo` row that carries `evidence:` keeps its status and loses the key
    (the status is the recorded decision; the file stays);
  * anything else stays as it is and is reported with the reason.

Read-only by default. `--apply` writes the recommendations into issues.yaml as
line edits, so the file's comments and layout survive, then re-parses the
result and refuses to write if anything else moved. `--prs-json` and
`--issues-json` replace the live `gh` calls, so tests stay hermetic.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backlog_lib import ISSUES_FILE, REPO, load_issues  # noqa: E402
from reconcile_lib import (  # noqa: E402
    RowReport,
    apply_changes,
    blocker_refs,
    open_done_issues,
    reconcile,
    verify_applied,
)
from sync_issues import REPO_SLUG  # noqa: E402

BLOCKERS_FILE = REPO / "docs" / "backlog" / "blockers.md"
HUMAN_BLOCKERS_FILE = REPO / "files" / "HUMAN_BLOCKERS.md"
EVIDENCE_DIR = REPO / "docs" / "evidence"


def _gh_json(*args: str) -> list[dict[str, Any]]:
    out = subprocess.run(["gh", *args], capture_output=True, text=True, check=True)
    data: list[dict[str, Any]] = json.loads(out.stdout)
    return data


def fetch_merged_prs() -> list[dict[str, Any]]:
    fields = "number,title,body,mergedAt"
    return _gh_json(
        "pr", "list", "-R", REPO_SLUG, "--state", "merged", "--limit", "1000", "--json", fields
    )


def fetch_issues() -> list[dict[str, Any]]:
    # gh lists newest first, which is the order owned_issue_numbers expects.
    fields = "number,title,state"
    return _gh_json(
        "issue", "list", "-R", REPO_SLUG, "--state", "all", "--limit", "2000", "--json", fields
    )


def _issues_cell(r: RowReport) -> str:
    if r.owned is None:
        return "none"
    cell = f"#{r.owned} {str(r.owned_state).lower()}"
    if r.duplicates:
        cell += "; dup " + ", ".join(f"#{d.number} {d.state.lower()}" for d in r.duplicates)
    return cell


def _prs_cell(r: RowReport) -> str:
    return "; ".join(f"#{p.number} {p.says()}" for p in r.prs) or "—"


def _transition(r: RowReport) -> str:
    new = r.new_status or r.status
    notes = []
    if r.add_evidence:
        notes.append("+ `evidence:`")
    if r.drop_evidence:
        notes.append("− `evidence:`")
    return f"{r.status} → {new}" + (" " + " ".join(notes) if notes else "")


def render_markdown(reports: list[RowReport]) -> str:
    esc = str.maketrans({"|": "\\|"})
    changed = [r for r in reports if r.changed]
    kept = [r for r in reports if not r.changed and r.status not in {"done", "withdrawn"}]
    kept += [r for r in reports if not r.changed and r.status == "done" and r.ambiguous]
    dups = [r for r in reports if r.duplicates]
    lines = ["### Changes", "", "| id | old → new | PR | reason |", "|---|---|---|---|"]
    for r in changed:
        prs = ", ".join(f"#{p.number}" for p in r.prs) or "—"
        lines.append(f"| {r.id} | {_transition(r)} | {prs} | {r.reason.translate(esc)} |")
    lines += ["", "### Rows left as they are", ""]
    lines += [
        "| id | status | merged PRs | issues | evidence file | why |",
        "|---|---|---|---|---|---|",
    ]
    for r in kept:
        flag = "**ambiguous** — " if r.ambiguous else ""
        cells = [r.id, r.status, _prs_cell(r), _issues_cell(r), "yes" if r.evidence_file else "no"]
        lines.append(
            "| "
            + " | ".join(c.translate(esc) for c in cells)
            + f" | {flag}{r.reason.translate(esc)} |"
        )
    lines += ["", "### Duplicate GitHub issues", ""]
    lines += ["| id | sync owns | duplicates |", "|---|---|---|"]
    for r in dups:
        dup = ", ".join(f"#{d.number} {d.state.lower()}" for d in r.duplicates)
        lines.append(f"| {r.id} | #{r.owned} {str(r.owned_state).lower()} | {dup} |")
    lines += ["", "### `done` rows whose sync-owned issue is open", ""]
    lines.append(", ".join(f"{r.id} (#{r.owned})" for r in open_done_issues(reports)) or "none")
    return "\n".join(lines) + "\n"


def render_text(reports: list[RowReport]) -> str:
    lines = []
    for r in reports:
        if not (r.changed or r.ambiguous):
            continue
        mark = "CHANGE" if r.changed else "REPORT"
        lines.append(
            f"{mark} {r.id} {_transition(r)} | prs: {_prs_cell(r)} | issues: {_issues_cell(r)}"
        )
        lines.append(f"       {r.reason}")
    changes = sum(r.changed for r in reports)
    ambiguous = sum(r.ambiguous and not r.changed for r in reports)
    open_dups = sum(1 for r in reports for d in r.duplicates if d.state == "OPEN")
    lines.append(
        f"rows: {len(reports)} · changes: {changes} · reported: {ambiguous}"
        f" · open duplicates: {open_dups}"
    )
    return "\n".join(lines) + "\n"


def _load_json(path: Path) -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write the recommendations")
    parser.add_argument("--issues-file", type=Path, default=ISSUES_FILE)
    parser.add_argument("--prs-json", type=Path, help="merged PRs, in `gh pr list --json` shape")
    parser.add_argument("--issues-json", type=Path, help="issues, in `gh issue list --json` shape")
    parser.add_argument("--blockers", type=Path, default=BLOCKERS_FILE)
    parser.add_argument("--human-blockers", type=Path, default=HUMAN_BLOCKERS_FILE)
    parser.add_argument("--evidence-dir", type=Path, default=EVIDENCE_DIR)
    parser.add_argument("--format", choices=["text", "markdown"], default="text")
    args = parser.parse_args(argv)

    rows = load_issues(args.issues_file)
    prs = _load_json(args.prs_json) if args.prs_json else fetch_merged_prs()
    issues = _load_json(args.issues_json) if args.issues_json else fetch_issues()
    refs = blocker_refs(
        args.blockers.read_text(encoding="utf-8"),
        args.human_blockers.read_text(encoding="utf-8"),
    )
    evidence_dir: Path = args.evidence_dir

    def evidence(iid: str) -> str | None:
        path = evidence_dir / f"{iid}.md"
        return path.read_text(encoding="utf-8") if path.is_file() else None

    reports = reconcile(rows, prs, issues, refs, evidence)

    print(render_markdown(reports) if args.format == "markdown" else render_text(reports), end="")
    if args.apply:
        before = args.issues_file.read_text(encoding="utf-8")
        after = apply_changes(before, reports)
        problems = verify_applied(before, after, reports)
        if problems:
            print("refusing to write:\n  " + "\n  ".join(problems), file=sys.stderr)
            return 1
        args.issues_file.write_text(after, encoding="utf-8")
        print(f"applied {sum(r.changed for r in reports)} change(s) to {args.issues_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

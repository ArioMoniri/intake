#!/usr/bin/env python3
"""INT-020 — the sec_row PR-linkage gate (CLAUDE.md invariant 16; files/10 §8).

files/10 §8: "Backlog `sec_row:` fields point at the §9 rows below, so every
feature PR links its threat row by construction." This script is that
construction's enforcement: given a PR title and body it verifies that

  1. the title names a real backlog issue (`INT-xxx: ...`);
  2. when that issue carries a `sec_row`, the body carries a matching
     `Sec-Row: <row>` line (the PR template prompts for it);
  3. that row has a `## `row`` section heading in docs/security/threat-model.md.

An issue without a `sec_row` passes with no line (or with `Sec-Row: —`).

stdlib only, on purpose: the CI `gates` job runs shell gates on the bare
runner without uv, so this must run under plain python3. The line-based parse
of issues.yaml is pinned against yaml.safe_load by
tests/security/test_threat_model.py (`--dump-rows` exists for that test).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_ISSUES = REPO / "docs" / "backlog" / "issues.yaml"
DEFAULT_MODEL = REPO / "docs" / "security" / "threat-model.md"

TITLE_RE = re.compile(r"^(INT-\d{3}): .+")
ID_LINE_RE = re.compile(r"^- id: (INT-\d{3})\s*$")
SEC_ROW_LINE_RE = re.compile(r'^  sec_row: "?([A-Za-z0-9_-]+)"?\s*$')
BODY_LINE_RE = re.compile(r"^\s*Sec-Row:\s*(.*?)\s*$")
NONE_MARKERS = frozenset({"—", "-", "none", "n/a"})


def parse_issue_rows(issues_path: Path) -> dict[str, str | None]:
    """Map every backlog issue id to its sec_row (None when it has none)."""
    rows: dict[str, str | None] = {}
    current: str | None = None
    for line in issues_path.read_text(encoding="utf-8").splitlines():
        id_match = ID_LINE_RE.match(line)
        if id_match:
            current = id_match.group(1)
            rows[current] = None
            continue
        row_match = SEC_ROW_LINE_RE.match(line)
        if row_match and current is not None:
            rows[current] = row_match.group(1)
    return rows


def declared_rows(body: str) -> list[str]:
    """Every value declared on a `Sec-Row:` line in the PR body, in order."""
    values: list[str] = []
    for line in body.splitlines():
        match = BODY_LINE_RE.match(line)
        if match:
            values.append(match.group(1))
    return values


def heading_present(model_path: Path, row: str) -> bool:
    if not model_path.is_file():
        return False
    pattern = re.compile(rf"^##\s.*`{re.escape(row)}`", re.M)
    return pattern.search(model_path.read_text(encoding="utf-8")) is not None


def fail(message: str) -> int:
    print(f"sec_row_linkage: FAIL — {message}")
    return 1


def check(title: str, body: str, issues_path: Path, model_path: Path) -> int:
    if not issues_path.is_file():
        return fail(f"backlog file not found: {issues_path}")
    title_match = TITLE_RE.match(title)
    if not title_match:
        return fail(f"PR title must be 'INT-xxx: <title>' (got: {title})")
    issue = title_match.group(1)
    rows = parse_issue_rows(issues_path)
    if issue not in rows:
        return fail(f"{issue} is not in docs/backlog/issues.yaml")
    expected = rows[issue]

    declared = declared_rows(body)
    unfilled = [v for v in declared if "<" in v or ">" in v or not v]
    if unfilled:
        return fail(
            f"the 'Sec-Row:' line is unfilled ({unfilled[0]!r}); "
            f"set it to the issue's sec_row, or '—' when the issue has none"
        )
    substantive = [v for v in declared if v.lower() not in NONE_MARKERS]

    if expected is None:
        if substantive:
            return fail(
                f"{issue} carries no sec_row in the backlog, but the body claims "
                f"'Sec-Row: {substantive[0]}'; drop the line or give the issue a sec_row"
            )
        print(f"sec_row_linkage: OK ({issue} has no sec_row; nothing to link)")
        return 0

    if not substantive:
        return fail(
            f"{issue} has sec_row '{expected}' (files/10 §9) but the PR body has no "
            f"'Sec-Row: {expected}' line (CLAUDE.md invariant 16)"
        )
    wrong = sorted(set(substantive) - {expected})
    if wrong:
        return fail(f"body declares Sec-Row {wrong[0]!r} but {issue}'s sec_row is {expected!r}")
    if not heading_present(model_path, expected):
        return fail(
            f"sec_row '{expected}' has no '## `{expected}`' section heading in "
            f"{model_path} — add the section before shipping the feature"
        )
    print(f"sec_row_linkage: OK ({issue} → {expected})")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("title", nargs="?", default=None, help="PR title")
    parser.add_argument("body", nargs="?", default=None, help="PR body")
    parser.add_argument("--issues", type=Path, default=DEFAULT_ISSUES)
    parser.add_argument("--threat-model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument(
        "--dump-rows",
        action="store_true",
        help="print 'id sec_row' per issue and exit (parser-parity test hook)",
    )
    args = parser.parse_args(argv)

    issues_path: Path = args.issues
    if args.dump_rows:
        for iid, row in parse_issue_rows(issues_path).items():
            print(f"{iid} {row}" if row else iid)
        return 0
    if args.title is None or args.body is None:
        parser.error("title and body are required unless --dump-rows is given")
    return check(args.title, args.body, issues_path, args.threat_model)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

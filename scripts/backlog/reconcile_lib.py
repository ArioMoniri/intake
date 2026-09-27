"""INT-396 — the pure half of scripts/backlog/reconcile.py.

Parsing (PR links, blocker records), the per-row decision and the line edit
that applies it. No I/O: every input is passed in, so tests stay hermetic. The
rules are stated in reconcile.py's docstring.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backlog_lib import evidence_path  # noqa: E402
from sync_issues import owned_issue_numbers  # noqa: E402

ID_RE = re.compile(r"INT-\d{3}")
HB_RE = re.compile(r"HB-[A-Z]+\d+[a-z]?")
CLOSES_RE = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b:?\s*#(\d+)", re.I)
REFS_RE = re.compile(r"\brefs?\b:?\s*#(\d+)", re.I)
HEADING_SPLIT_RE = re.compile(r"\s[—–·-]\s")
ID_LINE_RE = re.compile(r"^- id: (INT-\d{3})\s*$")
STATUS_LINE_RE = re.compile(r"^  status: \S+\s*$")
EVIDENCE_LINE_RE = re.compile(r"^  evidence: \S+\s*$")
# Case-sensitive on purpose: evidence files write a clause's status in capitals
# ("## Device measurement: PENDING", "| **NOT MET** |"); prose says "pending".
UNMET_RE = re.compile(r"\b(?:PENDING|NOT MET)\b")
LABEL_WIDTH = 90


@dataclass(frozen=True)
class PullRef:
    number: int
    merged_at: str
    closes: tuple[int, ...]
    refs: tuple[int, ...]

    def says(self) -> str:
        if self.closes:
            return "Closes " + ", ".join(f"#{n}" for n in self.closes)
        if self.refs:
            return "Refs " + ", ".join(f"#{n}" for n in self.refs)
        return "neither Closes nor Refs"


@dataclass(frozen=True)
class IssueRef:
    number: int
    state: str
    title: str


@dataclass(frozen=True)
class RowReport:
    id: str
    status: str
    evidence_key: bool
    evidence_file: bool
    prs: tuple[PullRef, ...]
    owned: int | None
    owned_state: str | None
    duplicates: tuple[IssueRef, ...]
    blockers: tuple[str, ...]
    new_status: str | None
    add_evidence: bool
    drop_evidence: bool
    ambiguous: bool
    reason: str

    @property
    def changed(self) -> bool:
        return self.new_status is not None or self.add_evidence or self.drop_evidence


def _unique(numbers: list[str]) -> tuple[int, ...]:
    return tuple(dict.fromkeys(int(n) for n in numbers))


def parse_links(body: str) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """(closing issue numbers, `Refs` issue numbers) named by a PR body."""
    return _unique(CLOSES_RE.findall(body)), _unique(REFS_RE.findall(body))


def _label(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= LABEL_WIDTH else text[: LABEL_WIDTH - 1] + "…"


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def blocker_refs(blockers_md: str, human_blockers_md: str) -> dict[str, list[str]]:
    """Every blocker record naming each id.

    blockers.md: a table row names the ids in its first cell before any
    parenthesis (`INT-380 (split from INT-121, …)` names INT-380 only), unless
    its status reads `resolved`; a `## INT-xxx — …` section names the ids in
    its heading before the first separator. HUMAN_BLOCKERS.md: an HB row that
    is not closed names every id it mentions.
    """
    refs: dict[str, list[str]] = {}

    def add(iid: str, label: str) -> None:
        found = refs.setdefault(iid, [])
        if label not in found:
            found.append(label)

    for line in blockers_md.splitlines():
        if line.startswith("## "):
            heading = line[3:].strip()
            lead = HEADING_SPLIT_RE.split(heading, maxsplit=1)[0]
            for iid in ID_RE.findall(lead):
                add(iid, _label(f"blockers.md § {heading}"))
        elif line.startswith("|"):
            cells = _cells(line)
            if len(cells) < 2 or cells[1].lower().startswith("resolved"):
                continue
            for iid in ID_RE.findall(cells[0].split("(")[0]):
                add(iid, _label(f"blockers.md row: {cells[1]}"))

    for line in human_blockers_md.splitlines():
        if not line.startswith("| **HB-"):
            continue
        cells = _cells(line)
        hb = HB_RE.search(cells[0])
        closed = any(c.lstrip("*").lower().startswith("closed") for c in cells[1:])
        if hb is None or closed:
            continue
        for iid in dict.fromkeys(ID_RE.findall(line)):
            add(iid, f"HUMAN_BLOCKERS {hb.group(0)}")
    return refs


def _pull_refs(prs: list[dict[str, Any]]) -> dict[str, list[PullRef]]:
    out: dict[str, list[PullRef]] = {}
    for pr in sorted(prs, key=lambda p: int(p["number"])):
        match = re.match(r"(INT-\d{3}):", pr.get("title", ""))
        if match is None:
            continue
        closes, refs = parse_links(pr.get("body") or "")
        ref = PullRef(int(pr["number"]), str(pr.get("mergedAt", "")), closes, refs)
        out.setdefault(match.group(1), []).append(ref)
    return out


def _issue_refs(issues: list[dict[str, Any]]) -> dict[str, list[IssueRef]]:
    out: dict[str, list[IssueRef]] = {}
    for issue in issues:
        title = str(issue.get("title", ""))
        if title[:7].startswith("INT-"):
            ref = IssueRef(int(issue["number"]), str(issue.get("state", "")), title)
            out.setdefault(title[:7], []).append(ref)
    return out


@dataclass(frozen=True)
class _Decision:
    reason: str
    new_status: str | None = None
    add_evidence: bool = False
    ambiguous: bool = False


def _why_not_closed(prs: list[PullRef], owned: int | None, dups: list[IssueRef]) -> str:
    dup_numbers = {d.number for d in dups}
    parts = []
    for pr in prs:
        said = pr.says()
        other = [n for n in pr.closes if n in dup_numbers]
        if other:
            said += f" (a duplicate the sync does not own; it owns #{owned})"
        parts.append(f"#{pr.number} says {said}")
    target = f"#{owned}" if owned is not None else "an issue (none carries this id)"
    return f"no merged PR closes {target}: " + "; ".join(parts)


def _decide(
    status: str,
    iid: str,
    prs: list[PullRef],
    owned: int | None,
    owned_state: str | None,
    dups: list[IssueRef],
    blockers: list[str],
    evidence_text: str | None,
    evidence_key: bool,
) -> _Decision:
    named = "; ".join(blockers)
    evidence_file = evidence_text is not None
    if status == "withdrawn":
        return _Decision("withdrawn")
    if status == "done":
        if evidence_key:
            return _Decision("done; evidence recorded")
        if evidence_file:
            return _Decision(f"done without `evidence:`; {evidence_path(iid)} exists", None, True)
        return _Decision("done with no evidence file: listed, not fabricated", ambiguous=True)
    if status == "awaiting-human":
        if blockers:
            return _Decision(f"awaiting-human; blocker: {named}")
        return _Decision("awaiting-human, but no blocker row names it", ambiguous=True)

    closing = [p for p in prs if owned is not None and owned in p.closes]
    if closing:
        by = ", ".join(f"#{p.number}" for p in closing)
        if owned_state != "CLOSED":
            why = f"merged PR {by} says Closes #{owned}, but #{owned} is {str(owned_state).lower()}"
            return _Decision(why, ambiguous=True)
        if blockers:
            return _Decision(
                f"merged PR {by} closed #{owned}, but a blocker names it: {named}", ambiguous=True
            )
        if evidence_text is None:
            return _Decision(
                f"merged PR {by} closed #{owned}, but {evidence_path(iid)} is missing",
                ambiguous=True,
            )
        unmet = UNMET_RE.search(evidence_text)
        if unmet:
            return _Decision(
                f"merged PR {by} closed #{owned}, but {evidence_path(iid)} marks a clause "
                f"{unmet.group(0)}",
                ambiguous=True,
            )
        why = f"merged PR {by} closed #{owned}; evidence exists; no blocker names it"
        return _Decision(why, "done", not evidence_key)
    if prs:
        why = _why_not_closed(prs, owned, dups)
        return _Decision(why + (f"; blocker: {named}" if blockers else ""), ambiguous=True)
    if evidence_file:
        return _Decision("evidence file exists but no merged INT PR", ambiguous=True)
    return _Decision("no merged INT PR" + (f"; blocker: {named}" if blockers else ""))


def reconcile(
    rows: list[dict[str, Any]],
    prs: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    blockers: dict[str, list[str]],
    evidence: Callable[[str], str | None],
) -> list[RowReport]:
    """One report per backlog row. Pure: every input is passed in.

    `evidence(id)` returns the text of docs/evidence/<id>.md, or None.
    """
    pulls = _pull_refs(prs)
    by_id = _issue_refs(issues)
    owned_by_id = owned_issue_numbers(issues)
    reports = []
    for row in rows:
        iid = row["id"]
        status = str(row.get("status", "todo"))
        owned = owned_by_id.get(iid)
        carrying = by_id.get(iid, [])
        owned_state = next((i.state for i in carrying if i.number == owned), None)
        dups = sorted((i for i in carrying if i.number != owned), key=lambda i: i.number)
        row_prs = pulls.get(iid, [])
        named = blockers.get(iid, [])
        evidence_key = "evidence" in row
        evidence_text = evidence(iid)
        d = _decide(
            status, iid, row_prs, owned, owned_state, dups, named, evidence_text, evidence_key
        )
        drop = d.new_status is None and status == "todo" and evidence_key
        reason = d.reason
        if drop:
            reason += "; a todo row may not carry `evidence:` (key removed, file kept)"
        reports.append(
            RowReport(
                iid,
                status,
                evidence_key,
                evidence_text is not None,
                tuple(row_prs),
                owned,
                owned_state,
                tuple(dups),
                tuple(named),
                d.new_status,
                d.add_evidence,
                drop,
                d.ambiguous,
                reason,
            )
        )
    return reports


def apply_changes(text: str, reports: list[RowReport]) -> str:
    """Line edits on issues.yaml: the status line, and the `evidence:` line under it."""
    changes = {r.id: r for r in reports if r.changed}
    out: list[str] = []
    current: str | None = None
    for line in text.splitlines(keepends=True):
        match = ID_LINE_RE.match(line)
        if match:
            current = match.group(1)
        report = changes.get(current) if current else None
        if report is None:
            out.append(line)
        elif report.drop_evidence and EVIDENCE_LINE_RE.match(line):
            continue
        elif STATUS_LINE_RE.match(line):
            out.append(f"  status: {report.new_status}\n" if report.new_status else line)
            if report.add_evidence:
                out.append(f"  evidence: {evidence_path(report.id)}\n")
        else:
            out.append(line)
    return "".join(out)


def verify_applied(before: str, after: str, reports: list[RowReport]) -> list[str]:
    """Every difference between the two parses is one the reports asked for."""
    old = {r["id"]: r for r in yaml.safe_load(before)}
    new = {r["id"]: r for r in yaml.safe_load(after)}
    problems = [] if list(old) == list(new) else ["the row ids or their order changed"]
    by_id = {r.id: r for r in reports}
    for iid, row in old.items():
        expected = dict(row)
        report = by_id.get(iid)
        if report is not None and report.new_status:
            expected["status"] = report.new_status
        if report is not None and report.add_evidence:
            expected["evidence"] = evidence_path(iid)
        if report is not None and report.drop_evidence:
            expected.pop("evidence", None)
        if new.get(iid) != expected:
            problems.append(f"{iid} does not match its recommendation")
    return problems


def open_done_issues(reports: list[RowReport]) -> list[RowReport]:
    """Rows that are (or become) `done` while the issue the sync owns is still open."""
    return [
        r
        for r in reports
        if (r.new_status or r.status) == "done" and r.owned is not None and r.owned_state == "OPEN"
    ]

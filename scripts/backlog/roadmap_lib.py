"""INT-452 — the pure half of the generated roadmap (scripts/backlog/render_roadmap.py).

Every input is passed in. Nothing here reads a file or runs a command, so the
renderer can never reach GitHub and the tests stay hermetic. GitHub state comes
only from the committed snapshot that `make roadmap-snapshot` writes.

State, one per row:
  done        status `done`
  withdrawn   status `withdrawn`
  blocked     status `awaiting-human` or `blocked`, or a `blocked:*` label
  in flight   an open PR whose title names the id, or status `doing`
  todo        anything else; `ready` when every dependency is satisfied
              (backlog_lib.DEP_SATISFIED_STATUSES, LOOP.md step 1)

Owner, one per row: who acts next.
  blocked     the `who` of a docs/backlog/blockers.md row naming the id; else
              the open files/HUMAN_BLOCKERS.md row naming it; else an open HB id
              written in the row's own YAML block; else the human its
              `approval:*` / `blocked:*` label names; else NO_RECORD_OWNER.
  otherwise   the agent role the first area label implies (the reviewer
              subagent .claude/agents/ requires for that area), plus the human
              sign-off an `approval:*` label adds.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backlog_lib import DEP_SATISFIED_STATUSES, is_blocked  # noqa: E402

BEGIN = (
    "<!-- BEGIN generated live status (scripts/backlog/render_roadmap.py) — do not edit by hand -->"
)
END = "<!-- END generated live status -->"

PHASE_NAMES = {
    "P0": "Foundation",
    "P1": "Fast mode, device-off",
    "P2": "Hospital pilot",
    "P3": "The record that travels",
}
STATES = ("done", "in flight", "blocked", "todo", "withdrawn")
NO_RECORD_OWNER = "owner — no blocker record names it"

# The human an approval:/blocked: label puts on the item. D18 (files/00 §3):
# clinical decisions for simulated-patient testing go through the agent lane;
# a licensed physician signs before any real patient.
GATE_OWNERS = {
    "approval:human-clinical": "physician of record (D18 agent lane for simulated patients)",
    "approval:human-legal": "counsel",
    "approval:human-infra": "owner (infrastructure)",
    "approval:human-vendor": "owner (vendor)",
    "approval:owner": "owner",
    # LOOP.md step 7: a `gpu` or `live-smoke` label also stops the auto-merge.
    "gpu": "owner (the target GPU host)",
    "live-smoke": "owner (the live smoke run)",
    "blocked:contract": "owner (contract)",
    "blocked:study-site": "owner (study site)",
    "blocked:runtime": "owner (runtime)",
}
# The reviewer subagent each area needs (.claude/agents/*.md, "Use ..." lines):
# clinical-reviewer for packs and patient copy, legal-reviewer for data,
# consent, sharing and store artefacts, runtime-reviewer for voice-runtime,
# sre-reviewer for services, endpoints, models and infrastructure.
AGENT_ROLES = {
    "area:protocols": "agent · clinical-reviewer",
    "area:clinical": "agent · clinical-reviewer",
    "area:safety": "agent · clinical-reviewer",
    "area:engine": "agent · clinical-reviewer",
    "area:i18n": "agent · clinical-reviewer",
    "area:legal": "agent · legal-reviewer",
    "area:data": "agent · legal-reviewer",
    "area:records": "agent · legal-reviewer",
    "area:release": "agent · legal-reviewer",
    "area:voice": "agent · runtime-reviewer",
    "area:lanes": "agent · runtime-reviewer",
    "area:api": "agent · sre-reviewer",
    "area:infra": "agent · sre-reviewer",
    "area:observability": "agent · sre-reviewer",
    "area:platform": "agent · sre-reviewer",
    "area:connectors": "agent · sre-reviewer",
    "area:security": "agent · security-reviewer",
    "area:ci": "agent · security-reviewer",
    "area:admin": "agent · security-reviewer",
    "area:mobile": "agent (mobile)",
    "area:a11y": "agent (mobile)",
}

ID_RE = re.compile(r"INT-\d{3}(?!\d)")
TITLE_ID_RE = re.compile(r"(INT-\d{3})(?!\d)")
HB_RE = re.compile(r"HB-[A-Z]+\d+[a-z]?")
TITLE_WIDTH = 110
WHO_WIDTH = 70


class MarkerError(ValueError):
    """The roadmap file does not carry exactly one BEGIN … END section."""


@dataclass(frozen=True)
class Inputs:
    rows: list[dict[str, Any]]
    epics: list[dict[str, Any]]
    snapshot: dict[str, Any]
    human_blockers_md: str
    blockers_md: str
    row_texts: dict[str, str]  # id -> the row's raw YAML block, comments included


@dataclass(frozen=True)
class Item:
    id: str
    phase: str
    epic: str
    title: str
    state: str
    note: str
    owner: str


@dataclass
class Drift:
    todo_with_open_pr: list[str] = field(default_factory=list)
    doing_without_pr: list[str] = field(default_factory=list)
    merged_not_done: list[tuple[str, list[int]]] = field(default_factory=list)
    done_issue_open: list[tuple[str, list[int]]] = field(default_factory=list)
    awaiting_without_record: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Model:
    items: dict[str, Item]  # file order
    drift: Drift
    prs_without_row: list[dict[str, Any]]
    prs_without_id: list[dict[str, Any]]
    issues_without_row: list[dict[str, Any]]


@dataclass(frozen=True)
class _Hb:
    who: str
    open: bool
    ids: tuple[str, ...]


@dataclass
class _Records:
    table: dict[str, list[tuple[str, str]]] = field(default_factory=dict)  # id -> (who, hb)
    sections: set[str] = field(default_factory=set)


# ---- parsing ------------------------------------------------------------------


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def clip(text: str, width: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 1].rstrip() + "…"


def _clean(text: str) -> str:
    return clip(re.sub(r"\*\*|~~|`", "", text), WHO_WIDTH)


def title_id(title: str) -> str | None:
    match = TITLE_ID_RE.match(title or "")
    return match.group(1) if match else None


def parse_human_blockers(text: str) -> dict[str, _Hb]:
    out: dict[str, _Hb] = {}
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = _cells(line)
        hb = HB_RE.search(cells[0]) if cells else None
        if hb is None or len(cells) < 3 or hb.group(0) in out:
            continue
        closed = any(c.lstrip("*").lower().startswith("closed") for c in cells[1:])
        ids = tuple(dict.fromkeys(ID_RE.findall(line)))
        out[hb.group(0)] = _Hb(_clean(cells[2]), not closed, ids)
    return out


def parse_blockers(text: str) -> _Records:
    """docs/backlog/blockers.md, read the way scripts/backlog/reconcile_lib.py reads it."""
    recs = _Records()
    for line in text.splitlines():
        if line.startswith("## "):
            lead = re.split(r"\s[—–·-]\s", line[3:].strip(), maxsplit=1)[0]
            recs.sections.update(ID_RE.findall(lead))
        elif line.startswith("|"):
            cells = _cells(line)
            if len(cells) < 3 or cells[1].lower().startswith("resolved"):
                continue
            hb_cell = cells[4] if len(cells) > 4 else ""
            for iid in ID_RE.findall(cells[0].split("(")[0]):
                recs.table.setdefault(iid, []).append((_clean(cells[2]), hb_cell))
    return recs


def row_texts(issues_yaml: str) -> dict[str, str]:
    """Each row's raw YAML block, so HB ids written in its comments are seen."""
    out: dict[str, str] = {}
    current: str | None = None
    for line in issues_yaml.splitlines(keepends=True):
        match = re.match(r"^- id: (INT-\d{3})\s*$", line)
        if match:
            current = match.group(1)
            out[current] = ""
        if current is not None:
            out[current] += line
    return out


# ---- owners and states --------------------------------------------------------


def _blocked_row(row: dict[str, Any]) -> bool:
    return row.get("status") in {"awaiting-human", "blocked"} or is_blocked(row)


def owner_for(row: dict[str, Any]) -> str:
    """The owner from the row's labels alone (what files/11 shows)."""
    labels = list(row.get("labels", []))
    gate = next((GATE_OWNERS[lab] for lab in labels if lab in GATE_OWNERS), None)
    if _blocked_row(row):
        return gate or NO_RECORD_OWNER
    role = next((AGENT_ROLES[lab] for lab in labels if lab in AGENT_ROLES), "agent")
    return f"{role}; sign-off: {gate}" if gate else role


def _pr_note(pr: dict[str, Any]) -> str:
    note = f"#{pr['number']} `{pr['branch']}`"
    if pr.get("draft"):
        note += " draft"
    if pr.get("mergeable") == "CONFLICTING":
        note += " conflicting"
    return note


def _blocked_owner(
    row: dict[str, Any], recs: _Records, hbs: dict[str, _Hb], text: str
) -> tuple[str, str, bool]:
    """(owner, blocker note, whether any record names the row)."""
    iid = row["id"]
    table = recs.table.get(iid)
    if table:
        who, hb_cell = table[0]
        named = list(dict.fromkeys(HB_RE.findall(hb_cell)))
        return who, " · ".join(named) or "blockers.md", True
    naming = [h for h, r in hbs.items() if r.open and iid in r.ids]
    if not naming:
        naming = [h for h in dict.fromkeys(HB_RE.findall(text)) if h in hbs and hbs[h].open]
    if naming:
        return f"{naming[0]}: {hbs[naming[0]].who}", " · ".join(naming), True
    owner = owner_for(row)
    if iid in recs.sections:
        if owner == NO_RECORD_OWNER:
            owner = f"named in blockers.md § {iid}"
        return owner, "blockers.md §", True
    return owner, "no blocker record", False


def build(inputs: Inputs) -> Model:
    rows = inputs.rows
    by_id = {r["id"]: r for r in rows}
    snapshot = inputs.snapshot
    open_prs = sorted(snapshot.get("open_prs", []), key=lambda p: int(p["number"]))
    prs_by_id: dict[str, list[dict[str, Any]]] = {}
    for pr in open_prs:
        iid = title_id(pr["title"])
        if iid is not None:
            prs_by_id.setdefault(iid, []).append(pr)
    issues_by_id: dict[str, list[int]] = {}
    issue_phase: dict[str, str | None] = {}
    for issue in sorted(snapshot.get("open_issues", []), key=lambda i: int(i["number"])):
        iid = title_id(issue["title"])
        if iid is not None:
            issues_by_id.setdefault(iid, []).append(int(issue["number"]))
            issue_phase.setdefault(iid, issue.get("phase"))
    merged = {k: [int(n) for n in v] for k, v in snapshot.get("merged_prs", {}).items()}
    recs = parse_blockers(inputs.blockers_md)
    hbs = parse_human_blockers(inputs.human_blockers_md)

    items: dict[str, Item] = {}
    drift = Drift()
    for row in rows:
        iid, status = row["id"], str(row.get("status", "todo"))
        prs = prs_by_id.get(iid, [])
        pr_text = "; ".join(_pr_note(p) for p in prs)
        owner = owner_for(row)
        if status in {"done", "withdrawn"}:
            state, note = status, ""
        elif _blocked_row(row):
            owner, note, recorded = _blocked_owner(row, recs, hbs, inputs.row_texts.get(iid, ""))
            state = "blocked"
            note += f" · PR {pr_text}" if pr_text else ""
            if status == "awaiting-human" and not recorded:
                drift.awaiting_without_record.append(iid)
        elif prs or status == "doing":
            state, note = "in flight", pr_text or "doing; no open PR"
        else:
            waiting = [
                d
                for d in row.get("depends_on", [])
                if by_id.get(d, {}).get("status", "todo") not in DEP_SATISFIED_STATUSES
            ]
            state, note = "todo", "waits on " + ", ".join(waiting) if waiting else "ready"
        if status == "todo" and state == "in flight":
            drift.todo_with_open_pr.append(iid)
        if status == "doing" and not prs:
            drift.doing_without_pr.append(iid)
        if status in {"todo", "doing"} and merged.get(iid):
            drift.merged_not_done.append((iid, merged[iid]))
        if status == "done" and issues_by_id.get(iid):
            drift.done_issue_open.append((iid, issues_by_id[iid]))
        items[iid] = Item(
            iid, row["phase"], row["epic"], str(row["title"]), state, note.strip(), owner
        )

    on_branches = {i for p in open_prs for i in (p.get("rows_added") or [])}
    named_by_pr = set(prs_by_id)
    prs_without_row = [
        {**p, "id": title_id(p["title"]), "phase": issue_phase.get(title_id(p["title"]) or "")}
        for p in open_prs
        if title_id(p["title"]) is not None and title_id(p["title"]) not in by_id
    ]
    prs_without_id = [p for p in open_prs if title_id(p["title"]) is None]
    issues_without_row = sorted(
        (
            {**i, "id": title_id(i["title"])}
            for i in snapshot.get("open_issues", [])
            if title_id(i["title"]) is not None
            and title_id(i["title"]) not in by_id
            and title_id(i["title"]) not in on_branches
            and title_id(i["title"]) not in named_by_pr
        ),
        key=lambda i: (str(i["id"]), int(i["number"])),
    )
    return Model(items, drift, prs_without_row, prs_without_id, issues_without_row)


# ---- the generated section ----------------------------------------------


def blank_generated_section(document: str) -> str:
    """`document` with its generated section blanked, line numbers kept.

    Repository scans that exempt files/11 (a rendering of the backlog) use this
    for files/05, whose generated section renders the same row titles, so the
    hand-written rest of files/05 is still scanned.
    """
    start, end = document.find(BEGIN), document.find(END)
    if start == -1 or end < start:
        return document
    stop = end + len(END)
    return document[:start] + "\n" * document.count("\n", start, stop) + document[stop:]


def splice(document: str, block: str) -> str:
    """Replace the one BEGIN … END section of `document` with `block`."""
    if document.count(BEGIN) != 1 or document.count(END) != 1:
        raise MarkerError("the roadmap must carry exactly one generated section")
    start, end = document.index(BEGIN), document.index(END)
    if end < start:
        raise MarkerError("the generated section's END marker precedes its BEGIN marker")
    stop = end + len(END)
    if document[stop : stop + 1] == "\n":
        stop += 1
    return document[:start] + block + document[stop:]

"""INT-452 — the markdown half of the generated roadmap.

`render(inputs)` turns roadmap_lib's model into the live status section of
files/05_ROADMAP.md, BEGIN and END markers included. Pure: no file is read and
no command is run (scripts/backlog/render_roadmap.py does the I/O).
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backlog_lib import PHASE_ORDER  # noqa: E402
from roadmap_lib import (  # noqa: E402
    BEGIN,
    END,
    PHASE_NAMES,
    STATES,
    TITLE_WIDTH,
    Drift,
    Inputs,
    Model,
    build,
    clip,
)


def _esc(text: str) -> str:
    return text.replace("|", "\\|")


def _row(cells: list[str]) -> str:
    return "| " + " | ".join(_esc(c) for c in cells) + " |"


def _ids_with(pairs: list[tuple[str, list[int]]]) -> str:
    return ", ".join(f"{i} ({', '.join(f'#{n}' for n in nums)})" for i, nums in pairs) or "none"


def _summary(model: Model) -> list[str]:
    counts: dict[str, Counter[str]] = {p: Counter() for p in PHASE_ORDER}
    for item in model.items.values():
        counts.setdefault(item.phase, Counter())[item.state] += 1
    pr_phase = Counter(p.get("phase") or "—" for p in model.prs_without_row)
    issue_phase = Counter(i.get("phase") or "—" for i in model.issues_without_row)
    phases = list(counts)
    if pr_phase.get("—") or issue_phase.get("—"):
        phases.append("—")
    lines = [
        "| phase | rows | done | in flight | blocked | todo | withdrawn "
        "| open PRs, no row on main | open issues, no row anywhere |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    total: Counter[str] = Counter()
    for phase in phases:
        c = counts.get(phase, Counter())
        cells = [sum(c.values()), *(c[s] for s in STATES), pr_phase[phase], issue_phase[phase]]
        total.update({str(k): v for k, v in enumerate(cells)})
        lines.append(f"| {phase} | " + " | ".join(str(v) for v in cells) + " |")
    lines.append(
        "| **all** | " + " | ".join(f"**{total[str(k)]}**" for k in range(len(STATES) + 3)) + " |"
    )
    return lines


def _phase_section(model: Model, phase: str, epic_order: list[str]) -> list[str]:
    items = [i for i in model.items.values() if i.phase == phase]
    name = PHASE_NAMES.get(phase, phase)
    # "Live ·" keeps these headings (and their anchors) apart from §1a's
    # hand-written phase-gate headings further down the same file.
    lines = [f"### Live · {phase} — {name}", ""]
    if not items:
        return lines + ["_No rows._", ""]
    by_epic: dict[str, Counter[str]] = {}
    for item in items:
        if item.state != "withdrawn":  # counted in the phase summary, not per epic
            by_epic.setdefault(item.epic, Counter())[item.state] += 1
    lines += ["| epic | done | in flight | blocked | todo |", "|---|---:|---:|---:|---:|"]
    for epic in [e for e in epic_order if e in by_epic] + sorted(set(by_epic) - set(epic_order)):
        c = by_epic[epic]
        lines.append(f"| {epic} | {c['done']} | {c['in flight']} | {c['blocked']} | {c['todo']} |")
    remaining = [i for i in items if i.state in {"in flight", "blocked", "todo"}]
    lines.append("")
    if not remaining:
        return lines + ["_Every row in this phase is done or withdrawn._", ""]
    lines += [
        f"Remaining, in file order ({len(remaining)}):",
        "",
        "| id | title | epic | state | PR · blocker · dependencies | owner |",
        "|---|---|---|---|---|---|",
    ]
    for i in remaining:
        lines.append(
            _row([i.id, clip(i.title, TITLE_WIDTH), i.epic, i.state, i.note or "—", i.owner])
        )
    return lines + [""]


def _rowless(model: Model) -> list[str]:
    lines = ["### Open PRs whose id has no row on main", ""]
    if model.prs_without_row:
        lines += [
            "| PR | id | phase | branch | rows the branch adds | title |",
            "|---|---|---|---|---|---|",
        ]
        for p in model.prs_without_row:
            added = p.get("rows_added")
            rows = "branch gone" if added is None else (", ".join(added) or "none")
            flag = " (draft)" if p.get("draft") else ""
            flag += " (conflicting)" if p.get("mergeable") == "CONFLICTING" else ""
            lines.append(
                _row(
                    [
                        f"#{p['number']}{flag}",
                        str(p["id"]),
                        p.get("phase") or "—",
                        f"`{p['branch']}`",
                        rows,
                        clip(p["title"], TITLE_WIDTH),
                    ]
                )
            )
    else:
        lines.append("None.")
    lines += ["", "### Open PRs that name no backlog id", ""]
    if model.prs_without_id:
        lines += ["| PR | branch | title |", "|---|---|---|"]
        for p in model.prs_without_id:
            lines.append(
                _row([f"#{p['number']}", f"`{p['branch']}`", clip(p["title"], TITLE_WIDTH)])
            )
    else:
        lines.append("None.")
    lines += ["", "### Open issues with no row on main or on any open PR branch", ""]
    if model.issues_without_row:
        lines += ["| issue | id | phase | title |", "|---|---|---|---|"]
        for i in model.issues_without_row:
            phase = i.get("phase") or "—"
            lines.append(
                _row([f"#{i['number']}", str(i["id"]), phase, clip(i["title"], TITLE_WIDTH)])
            )
    else:
        lines.append("None.")
    return lines + [""]


def _drift(drift: Drift) -> list[str]:
    def ids(values: list[str]) -> str:
        return ", ".join(values) or "none"

    return [
        "### Drift the generator sees — reported here, never repaired by it",
        "",
        f"- **`done` rows whose GitHub issue is still open** ({len(drift.done_issue_open)}; "
        f"`make backlog-sync` closes them, and the live sync is the operator's): "
        f"{_ids_with(drift.done_issue_open)}",
        f"- **`todo`/`doing` rows with a merged INT PR** ({len(drift.merged_not_done)}; "
        f"`scripts/backlog/reconcile.py` decides whether they are done): "
        f"{_ids_with(drift.merged_not_done)}",
        f"- **`todo` rows with an open PR** ({len(drift.todo_with_open_pr)}; shown in flight "
        f"above): {ids(drift.todo_with_open_pr)}",
        f"- **`doing` rows with no open PR** ({len(drift.doing_without_pr)}): "
        f"{ids(drift.doing_without_pr)}",
        f"- **`awaiting-human` rows no blocker record names** "
        f"({len(drift.awaiting_without_record)}): {ids(drift.awaiting_without_record)}",
        "",
    ]


def render(inputs: Inputs) -> str:
    model = build(inputs)
    snap = inputs.snapshot
    epic_order = [str(e["id"]) for e in inputs.epics]
    lines = [
        BEGIN,
        "## Live status — generated from the backlog and GitHub",
        "",
        "> **Generated; do not edit this section by hand.** "
        "`scripts/backlog/render_roadmap.py` renders it from `docs/backlog/issues.yaml`, "
        "`docs/backlog/epics.yaml`, `files/HUMAN_BLOCKERS.md`, `docs/backlog/blockers.md` and "
        "the GitHub snapshot `docs/backlog/github_snapshot.json`, captured "
        f"**{snap.get('captured_at', '—')}** against main `{str(snap.get('base', ''))[:12]}`. "
        "`make roadmap-snapshot` refreshes the GitHub state and is the only step that calls "
        "GitHub; `make backlog-render` re-renders; `tests/backlog/test_roadmap.py` fails CI "
        "when this section is stale.",
        ">",
        "> **States.** done · in flight (an open PR names the id, or the row is `doing`) · "
        "blocked (`awaiting-human`/`blocked`, or a `blocked:*` label) · todo (`ready` when "
        "every dependency is satisfied, LOOP.md step 1) · withdrawn. **Owner** is who acts "
        "next: for a blocked item the named human from its blocker record, otherwise the "
        "agent role its area implies plus any human sign-off (`scripts/backlog/roadmap_lib.py`).",
        "",
        *_summary(model),
        "",
    ]
    for phase in PHASE_ORDER:
        lines += _phase_section(model, phase, epic_order)
    lines += _rowless(model)
    lines += _drift(model.drift)
    lines.append(END)
    return "\n".join(lines) + "\n"

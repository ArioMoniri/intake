"""INT-354 · int-demo consolidates into main, and main is the build source.

Acceptance, verbatim (docs/backlog/issues.yaml, INT-354):

1. "every int-demo commit not on main (git log main..int-demo) lands through
   one-issue PRs or is dropped with its reason recorded in
   docs/evidence/INT-354.md"
2. "demo-scoped code (hardcoded connector refs, recipients.demo.yaml) never
   reaches main"
3. "main carries exactly one apps/mobile/app.json and one apps/mobile/eas.json"
4. "an EAS build from main installs on a device and shows Önvizit" (a device
   step for the owner, HB-A3; not provable from a test)

Clause 1 is checked against a pinned snapshot of ``git log --no-merges
origin/main..origin/int-demo``. CI checkouts are shallow and carry no int-demo
ref, so the set is pinned here and its derivation is recorded in the evidence.
int-demo is frozen: nothing new may be committed to it, so the set cannot grow.
Every pinned commit needs exactly one ledger row with a disposition from a
closed vocabulary, and a ``landed`` row must name the backlog row and PR it
landed through. A row that is not yet ``landed`` or ``dropped`` keeps the issue
open; the test proves the record is complete, not that the work is.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
EVIDENCE = REPO / "docs" / "evidence" / "INT-354.md"
ISSUES = REPO / "docs" / "backlog" / "issues.yaml"

#: ``git log --no-merges --format=%h --abbrev=8 origin/main..origin/int-demo``
#: at int-demo 82c1a1e6 (frozen since 2026-09-27), re-run on 2026-11-17.
INT_DEMO_COMMITS = frozenset(
    {
        "82c1a1e6",
        "0115c60b",
        "4cfe29f7",
        "a23f838a",
        "8fd3a6e9",
        "2402ff27",
        "211e1ca9",
        "01e224a2",
        "545abfa7",
        "2cabe9fa",
        "20aca9e2",
        "148a7dbd",
        "b2301f8e",
        "bf30fd94",
        "fce1164f",
        "278cfe8b",
        "2b23bbb8",
        "dc8e49df",
        "cada99e0",
        "a5dfd9a5",
        "56e8c19b",
        "48eaa418",
        "3ddff8e7",
        "f91738e0",
        "6afc25e2",
        "50bf1dbc",
    }
)

#: landed: merged to main through the named one-issue PR.
#: dropped: never lands; the reason column says why.
#: pr-open: its one-issue PR exists and is not merged.
#: held: waits on a named human decision.
#: needs-issue: no backlog id yet; the owner allocates one (no agent mints ids).
DISPOSITIONS = frozenset({"landed", "dropped", "pr-open", "held", "needs-issue"})

LEDGER_HEADING = "## Disposition ledger"
ROW = re.compile(r"^\|\s*`(?P<sha>[0-9a-f]{8})`\s*\|\s*(?P<disp>[a-z-]+)\s*\|(?P<rest>.*)\|\s*$")
ISSUE_ID = re.compile(r"\bINT-\d+\b")
PR_REF = re.compile(r"#\d+\b")

#: Literal refs the int-demo route built its connector row from (audit F06),
#: split so this file is not itself a hit.
DEMO_LITERALS = (
    "dev-acibadem" + "-dpa",
    "dev-acibadem" + "-approval",
    "acibadem" + "-demo",
)
DEMO_FILES = ("recipients" + ".demo.yaml",)
#: Prose may name the refs as history; code, config and tests may not.
PROSE_ROOTS = ("docs/", "files/")


def _tracked() -> list[str]:
    out = subprocess.run(  # noqa: S603 — fixed argv, no shell
        ["git", "ls-files", "-z"],  # noqa: S607 — git on PATH, as every repo gate
        cwd=REPO,
        capture_output=True,
        check=True,
    ).stdout
    paths = [p.decode("utf-8") for p in out.split(b"\0") if p]
    assert len(paths) > 1000, "git ls-files returned almost nothing; the scan would be vacuous"
    return paths


def _ledger() -> dict[str, list[tuple[str, str]]]:
    text = EVIDENCE.read_text(encoding="utf-8")
    assert LEDGER_HEADING in text, f"{EVIDENCE.name} has no '{LEDGER_HEADING}' section"
    section = text.split(LEDGER_HEADING, 1)[1].split("\n## ", 1)[0]
    rows: dict[str, list[tuple[str, str]]] = {}
    for line in section.splitlines():
        m = ROW.match(line)
        if m:
            rows.setdefault(m["sha"], []).append((m["disp"], m["rest"]))
    return rows


def _backlog_ids() -> set[str]:
    data = yaml.safe_load(ISSUES.read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else data["issues"]
    return {item["id"] for item in items}


def test_every_int_demo_commit_has_exactly_one_ledger_row() -> None:
    rows = _ledger()
    missing = sorted(INT_DEMO_COMMITS - rows.keys())
    extra = sorted(rows.keys() - INT_DEMO_COMMITS)
    doubled = sorted(sha for sha, r in rows.items() if len(r) != 1)
    assert not missing, f"int-demo commits with no disposition: {missing}"
    assert not extra, f"ledger rows for commits outside main..int-demo: {extra}"
    assert not doubled, f"commits with more than one disposition: {doubled}"


def test_every_disposition_is_from_the_closed_vocabulary() -> None:
    bad = {sha: d for sha, [(d, _)] in _ledger().items() if d not in DISPOSITIONS}
    assert not bad, f"unknown dispositions: {bad}"


def test_a_landed_commit_names_its_backlog_row_and_pr() -> None:
    ids = _backlog_ids()
    for sha, [(disp, rest)] in _ledger().items():
        if disp != "landed":
            continue
        named = ISSUE_ID.findall(rest)
        assert named, f"{sha} is landed but names no INT id"
        assert set(named) <= ids, f"{sha} names an id with no backlog row: {named}"
        assert PR_REF.search(rest), f"{sha} is landed but names no PR"


def test_a_dropped_commit_records_its_reason() -> None:
    for sha, [(disp, rest)] in _ledger().items():
        if disp == "dropped":
            reason = rest.split("|")[-1].strip()
            assert len(reason) >= 20, f"{sha} is dropped without a recorded reason"


def test_no_demo_recipient_overlay_is_tracked() -> None:
    hits = [p for p in _tracked() if p.rsplit("/", 1)[-1] in DEMO_FILES]
    assert not hits, f"demo-scoped files on the tree: {hits}"


def test_no_hardcoded_demo_connector_ref_outside_prose() -> None:
    hits: list[str] = []
    for rel in _tracked():
        if rel.startswith(PROSE_ROOTS):
            continue
        try:
            data = (REPO / rel).read_bytes()
        except (FileNotFoundError, IsADirectoryError):
            continue
        if b"\0" in data:
            continue
        text = data.decode("utf-8", errors="replace")
        hits.extend(f"{rel}: {lit}" for lit in DEMO_LITERALS if lit in text)
    assert not hits, f"hardcoded demo connector refs (audit F06): {hits}"


def test_main_carries_exactly_one_app_json_and_one_eas_json() -> None:
    tracked = _tracked()
    app = [p for p in tracked if p.rsplit("/", 1)[-1] == "app.json"]
    eas = [p for p in tracked if p.rsplit("/", 1)[-1] == "eas.json"]
    assert app == ["apps/mobile/app.json"], app
    assert eas == ["apps/mobile/eas.json"], eas


def test_the_one_eas_json_has_the_production_build_profile() -> None:
    """main is the build source: the store build is cut from its eas.json."""
    eas = json.loads((REPO / "apps/mobile/eas.json").read_text(encoding="utf-8"))
    assert "production" in eas["build"], "eas.json has no production build profile"
    assert "production" in eas["submit"], "eas.json has no production submit profile"

"""INT-004 — GitHub sync (dry-run), templates, renderer, backlog-status.

Acceptance lines under test, verbatim:
  "scripts/backlog/sync_issues.py creates/updates GitHub issues via gh with
   labels ph:*, area:*, risk:*, approval:*, milestones P0..P3 and a Project
   board Backlog/Ready/In progress/In review/Blocked/Done"
  ".github/ISSUE_TEMPLATE/feature.yml + pull_request_template.md with the DoD
   checklist and mandatory links (issue, 10 §9 row, 06 legal codes, evidence file)"
  "docs/backlog/blockers.md format + `make backlog-status` report"

Dry-run with an injected existing-issues file makes the planner hermetic — no
gh, no network, still the same decision code the live sync runs.

INT-405 acceptance lines under test, verbatim:
  "`fetch_existing` pages until exhausted (a test with a fake paginated client
   over 1,200 issues, and a near-miss where page 3 is dropped)"
  "the sync closes the owned issue of a `done` row (state_reason completed) and
   reopens it for a row moved back from `done`; dry-run lists these actions;
   the live run is the operator's"
  "duplicates are never touched, only the owned issue per id
   (`owned_issue_numbers()`)"
The listing and the gh calls are fakes: no test here reaches GitHub.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "backlog"))

import sync_issues as sync  # noqa: E402


def _plan(tmp_path: Path, existing: list[dict]) -> dict:
    ef = tmp_path / "existing.json"
    ef.write_text(json.dumps(existing), encoding="utf-8")
    out = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "scripts/backlog/sync_issues.py",
            "--dry-run",
            "--existing-json",
            str(ef),
            "--plan-json",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_dryrun_plans_creates_and_updates(tmp_path: Path) -> None:
    existing = [
        {
            "number": 1,
            "title": "INT-001: Monorepo bootstrap: workspaces, Makefile, pre-commit, compose.dev",
        },
        {"number": 3, "title": "INT-002: CI base + evidence gates"},
    ]
    plan = _plan(tmp_path, existing)
    actions = {a["id"]: a for a in plan["actions"]}
    # tracks test_schema.py (175 blueprint + added issues incl. INT-321 + INT-322 + INT-323)
    # tracks test_schema.py (175 blueprint + added issues incl. INT-321 + INT-322 + INT-323,
    # and INT-372 from the INT-354 consolidation)
    # and INT-370 from the INT-354 consolidation)
    # tracks test_schema.py (175 blueprint + added issues incl. INT-321 + INT-322 + INT-323
    # + INT-317, carried from int-demo by INT-354)
    # tracks test_schema.py (175 blueprint + added issues, latest INT-376)
    # + INT-318, the INT-354 slice S2 row)
    # + INT-380 and INT-381, split out of INT-121 and INT-124 by INT-124's PR
    # + INT-385 (record quantities in the locale's decimal separator, GitHub #635)
    # + INT-392, the session-deletion fix found on check-integration)
    # + INT-393, the Doctor Link erasure fix found by INT-392)
    # + INT-391 (every valid WebAuthn credential id admitted, GitHub #646)
    # + INT-386 (the typed rail, note, summary and FHIR narrative quantities, GitHub #638)
    # + INT-387 (the a11y conformance report re-rated after INT-361..363, GitHub #640)
    # + INT-397 (the last three SC 4.1.3 status lines are announced, GitHub #659)
    # + INT-390, the Keycloak upgrade INT-378 found
    # + INT-396 (backlog status reconciliation and drift guard, GitHub #655)
    # + INT-405 (sync paging past 500 issues and issue state, GitHub #675)
    # + INT-398..400 (split out of INT-122 by its own PR, #663)
    # + INT-401 (console rollback split out of INT-187)
    # + INT-409 (Vizitlerim reads today from the device clock, not a pinned date, GitHub #688)
    # + INT-410 (release bundles carry no synthetic seed accounts, audit F30, GitHub #689)
    # + INT-404 (triage rule evidence lines in the reader's locale, GitHub #673)
    # + INT-382 (rule-read slot removal refused in every layer; GitHub #629)
    # + INT-415 (ElevenLabs delivery profiles + on-prem TTS wiring guide, GitHub #706)
    # + INT-429 (vulnerabilities gate: dependency upgrades + time-boxed node-forge row, GitHub #727)
    # + INT-431 (the embed sample's JWT fixture built at runtime, GitHub #733)
    # + INT-430 (the agent council as a post-bind verifier, GitHub #732)
    assert len(actions) == 329
    assert actions["INT-001"]["action"] == "update"
    assert actions["INT-001"]["number"] == 1
    assert actions["INT-004"]["action"] == "create"


def test_dryrun_labels_and_milestones(tmp_path: Path) -> None:
    plan = _plan(tmp_path, [])
    actions = {a["id"]: a for a in plan["actions"]}
    assert "ph:P0" in actions["INT-001"]["labels"]
    assert actions["INT-001"]["milestone"] == "P0"
    assert "approval:human-clinical" in actions["INT-043"]["labels"]
    assert "gpu" in actions["INT-097"]["labels"]
    assert "blocked:contract" in actions["INT-097"]["labels"]
    assert actions["INT-097"]["milestone"] == "P3"
    # the board column set the project must carry
    expected_columns = ["Backlog", "Ready", "In progress", "In review", "Blocked", "Done"]
    assert plan["board_columns"] == expected_columns
    # every label the plan uses is declared so the sync can create them first
    used = {label for a in plan["actions"] for label in a["labels"]}
    assert used <= set(plan["labels"]), used - set(plan["labels"])


def test_issue_template_and_pr_template() -> None:
    feature = yaml.safe_load(
        (REPO / ".github" / "ISSUE_TEMPLATE" / "feature.yml").read_text(encoding="utf-8")
    )
    assert feature["name"]
    field_ids = {b.get("id") for b in feature["body"] if isinstance(b, dict)}
    assert {"acceptance", "phase", "legal", "sec_row"} <= field_ids

    pr = (REPO / ".github" / "pull_request_template.md").read_text(encoding="utf-8")
    for needle in ("Closes #", "docs/evidence/", "10 §9", "legal", "red run", "make check"):
        assert needle.lower() in pr.lower(), f"pull_request_template.md missing {needle}"


def test_files11_rendering_matches_backlog() -> None:
    out = subprocess.run(
        ["uv", "run", "python", "scripts/backlog/render_backlog.py", "--check"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, (
        "files/11_ISSUE_BACKLOG.md is stale — run `uv run python "
        "scripts/backlog/render_backlog.py` and commit\n" + out.stdout + out.stderr
    )


def test_backlog_status_report() -> None:
    out = subprocess.run(
        ["uv", "run", "python", "scripts/backlog/backlog_status.py", "--no-github"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, out.stderr
    for needle in ("P0", "done", "next", "blockers"):
        assert needle.lower() in out.stdout.lower(), f"backlog-status missing {needle}"


# ---- INT-405: the listing pages until GitHub has nothing left ---------------

SLUG = sync.REPO_SLUG
N_ISSUES = 1200
PER_PAGE = 100


def _is_pr(n: int) -> bool:
    # REST lists pull requests with issues; they share one number sequence.
    return n % 13 == 2


def _rest_listing() -> list[dict[str, Any]]:
    """1,200 issues and 100 pull requests, oldest first (sort=created, direction=asc).

    #1 is the INT-001 issue the sync owns, #2 its PR (same title, as on the
    real repo) and #1251 a newer copy carrying the same prefix.
    """
    items: list[dict[str, Any]] = []
    for n in range(1, N_ISSUES + 101):
        title = "INT-001: Monorepo bootstrap" if n in (1, 2, 1251) else f"chore {n}"
        item: dict[str, Any] = {
            "number": n,
            "title": title,
            "state": "closed" if n < 600 else "open",
            "state_reason": "completed" if n < 600 else None,
        }
        if _is_pr(n):
            item["pull_request"] = {"url": f"https://api.github.com/repos/{SLUG}/pulls/{n}"}
        items.append(item)
    assert sum(not _is_pr(i["number"]) for i in items) == N_ISSUES
    return items


class _FakeListing:
    """GitHub's paged REST issue listing and its GraphQL issue count."""

    def __init__(self, items: list[dict[str, Any]], fault: str | None = None) -> None:
        self.items = items
        self.fault = fault
        self.requested: list[int] = []
        self.counted = 0

    def page(self, number: int, per_page: int) -> list[dict[str, Any]]:
        self.requested.append(number)
        served = number
        if number == 3 and self.fault == "dropped":
            return []  # the page comes back empty: the loop believes it is done
        if number >= 3 and self.fault == "skipped":
            served = number + 1  # page 3's issues are never served
        if number == 3 and self.fault == "repeated":
            served = 2
        start = (served - 1) * per_page
        return [dict(i) for i in self.items[start : start + per_page]]

    def total(self) -> int:
        self.counted += 1
        grown = 1 if self.fault == "grew" and self.counted > 1 else 0
        return sum(1 for i in self.items if "pull_request" not in i) + grown


def test_fetch_existing_pages_until_exhausted() -> None:
    listing = _FakeListing(_rest_listing())
    existing = sync.fetch_existing(listing)
    assert len(existing) == N_ISSUES
    assert listing.requested == list(range(1, 15))  # 13 full pages, then an empty one
    numbers = [e["number"] for e in existing]
    assert numbers == sorted(numbers, reverse=True)  # newest first, as owned_issue_numbers reads
    assert not [n for n in numbers if _is_pr(n)]
    assert existing[-1] == {"number": 1, "title": "INT-001: Monorepo bootstrap", "state": "CLOSED"}
    assert sync.owned_issue_numbers(existing)["INT-001"] == 1


def test_control_a_500_cap_would_have_owned_the_newer_copy() -> None:
    # The fixture discriminates: capped at the newest 500, as before INT-405,
    # #1 drops out and the sync would edit the copy.
    everything = sync.fetch_existing(_FakeListing(_rest_listing()))
    assert sync.owned_issue_numbers(everything[:500])["INT-001"] == 1251


@pytest.mark.parametrize(
    ("fault", "refusal"),
    [
        # page 3 comes back empty; pages 1-2 hold 184 issues and 16 PRs
        ("dropped", "listed 184 issues over 3 pages, GitHub counts 1200;"),
        # page 3 (93 issues, 7 PRs) is never served; the rest are
        ("skipped", "listed 1107 issues over 13 pages, GitHub counts 1200;"),
        # page 3 serves page 2 again: refused there (a listing stuck on one
        # full page would otherwise never end), not at the final count
        ("repeated", "page 3 lists only items already listed"),
        # an issue is filed mid-listing: the two counts disagree
        ("grew", "GitHub counts 1201 (it was 1200 when the listing began)"),
    ],
)
def test_near_miss_a_lost_page_is_refused_not_synced(fault: str, refusal: str) -> None:
    with pytest.raises(sync.ListingIncomplete) as err:
        sync.fetch_existing(_FakeListing(_rest_listing(), fault=fault))
    assert refusal in str(err.value)
    assert "nothing was changed" in str(err.value)


def _completed(args: tuple[str, ...], stdout: str, rc: int = 0) -> Any:
    return subprocess.CompletedProcess(list(args), rc, stdout, "" if rc == 0 else "boom")


def test_gh_client_lists_every_state_oldest_first_and_reads_the_count() -> None:
    calls: list[tuple[str, ...]] = []

    def run(*args: str, check: bool = True) -> Any:
        calls.append(args)
        if args[:2] == ("api", "graphql"):
            count = {"data": {"repository": {"issues": {"totalCount": 409}}}}
            return _completed(args, json.dumps(count))
        return _completed(args, json.dumps([{"number": 5, "title": "t", "state": "open"}]))

    client = sync.GhIssueClient(run)
    assert client.page(3, PER_PAGE) == [{"number": 5, "title": "t", "state": "open"}]
    assert client.total() == 409
    path, query = calls[0][1].split("?", 1)
    assert calls[0][0] == "api" and path == f"repos/{SLUG}/issues"
    params = dict(p.split("=", 1) for p in query.split("&"))
    assert params == {
        "state": "all",
        "sort": "created",
        "direction": "asc",
        "per_page": "100",
        "page": "3",
    }
    owner, name = SLUG.split("/")
    assert f"owner={owner}" in calls[1] and f"name={name}" in calls[1]


# ---- INT-405: issue state follows the row -----------------------------------


def _row(iid: str, status: str) -> dict[str, Any]:
    return {"id": iid, "title": "t", "phase": "P1", "epic": "E00", "status": status}


ROWS = [
    _row("INT-901", "done"),  # owned #11 open, an open slice copy #40 → close #11 only
    _row("INT-902", "todo"),  # owned #12 closed → reopen
    _row("INT-903", "done"),  # owned #13 closed → nothing
    _row("INT-904", "todo"),  # owned #14 open → nothing
    _row("INT-905", "withdrawn"),  # owned #15 open → nothing
    _row("INT-906", "awaiting-human"),  # owned #16 closed → reopen
    _row("INT-907", "done"),  # no issue → create, then close
    _row("INT-908", "done"),  # owned #18 closed, an open copy #48 → nothing
    _row("INT-909", "todo"),  # owned #19, listing without state → nothing
    _row("INT-910", "withdrawn"),  # owned #20 closed → nothing (not reopened)
]
EXISTING = sorted(
    [
        {"number": 11, "title": "INT-901: t", "state": "OPEN"},
        {"number": 40, "title": "INT-901 core: a slice", "state": "OPEN"},
        {"number": 12, "title": "INT-902: t", "state": "CLOSED"},
        {"number": 13, "title": "INT-903: t", "state": "CLOSED"},
        {"number": 14, "title": "INT-904: t", "state": "OPEN"},
        {"number": 15, "title": "INT-905: t", "state": "OPEN"},
        {"number": 16, "title": "INT-906: t", "state": "CLOSED"},
        {"number": 18, "title": "INT-908: t", "state": "CLOSED"},
        {"number": 48, "title": "INT-908: a copy", "state": "OPEN"},
        {"number": 19, "title": "INT-909: t"},
        {"number": 20, "title": "INT-910: t", "state": "CLOSED"},
    ],
    key=lambda e: -int(e["number"]),
)
DUPLICATES = {"40", "48"}


def test_plan_closes_done_rows_and_reopens_rows_moved_back() -> None:
    plan = sync.build_plan(ROWS, EXISTING)
    got = {a["id"]: (a["action"], a["number"], a["state_change"]) for a in plan["actions"]}
    assert got == {
        "INT-901": ("update", 11, "close"),
        "INT-902": ("update", 12, "reopen"),
        "INT-903": ("update", 13, None),
        "INT-904": ("update", 14, None),
        "INT-905": ("update", 15, None),
        "INT-906": ("update", 16, "reopen"),
        "INT-907": ("create", None, "close"),
        "INT-908": ("update", 18, None),
        "INT-909": ("update", 19, None),
        "INT-910": ("update", 20, None),
    }


def _fake_gh(fail_create: bool = False) -> tuple[list[tuple[str, ...]], Any]:
    calls: list[tuple[str, ...]] = []

    def run(*args: str, check: bool = True) -> Any:
        calls.append(args)
        if args[:2] == ("issue", "create"):
            if fail_create:
                return _completed(args, "", rc=1)
            return _completed(args, f"https://github.com/{SLUG}/issues/1301\n")
        if args[0] == "api" and "milestones" in args[1]:
            have = [{"title": t, "number": n} for n, t in enumerate(sync.MILESTONES, 1)]
            return _completed(args, json.dumps(have))
        return _completed(args, "")

    return calls, run


def _state_calls(calls: list[tuple[str, ...]]) -> list[tuple[str, ...]]:
    return [c for c in calls if c[:2] in {("issue", "close"), ("issue", "reopen")}]


def test_apply_closes_completed_and_reopens_only_owned_issues() -> None:
    calls, run = _fake_gh()
    sync.apply_plan(sync.build_plan(ROWS, EXISTING), run=run, pause=lambda _s: None)
    assert _state_calls(calls) == [
        ("issue", "close", "11", "-R", SLUG, "--reason", "completed"),
        ("issue", "reopen", "12", "-R", SLUG),
        ("issue", "reopen", "16", "-R", SLUG),
        ("issue", "close", "1301", "-R", SLUG, "--reason", "completed"),
    ]
    edited = {c[2] for c in calls if c[:2] == ("issue", "edit")}
    assert edited == {"11", "12", "13", "14", "15", "16", "18", "19", "20"}
    touched = {c[2] for c in calls if c[0] == "issue" and c[1] in {"edit", "close", "reopen"}}
    assert not touched & DUPLICATES


def test_near_miss_a_failed_create_closes_nothing() -> None:
    calls, run = _fake_gh(fail_create=True)
    plan = sync.build_plan([_row("INT-907", "done")], [])
    sync.apply_plan(plan, run=run, pause=lambda _s: None)
    assert _state_calls(calls) == []


def test_dry_run_lists_the_state_actions_and_changes_nothing(tmp_path: Path) -> None:
    rows = tmp_path / "issues.yaml"
    rows.write_text(yaml.safe_dump(ROWS, sort_keys=False), encoding="utf-8")
    ef = tmp_path / "existing.json"
    ef.write_text(json.dumps(EXISTING), encoding="utf-8")
    out = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "scripts/backlog/sync_issues.py",
            "--dry-run",
            "--issues-file",
            str(rows),
            "--existing-json",
            str(ef),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, out.stderr
    lines = out.stdout.splitlines()
    assert "plan: 1 creates, 9 updates" in lines
    assert "state: 1 to close, 2 to reopen, 1 to close once created" in lines
    assert "close #11 INT-901 (row done, issue open)" in lines
    assert "reopen #12 INT-902 (row todo, issue closed)" in lines
    assert "reopen #16 INT-906 (row awaiting-human, issue closed)" in lines
    assert "close INT-907 once created (row done)" in lines
    for n in ("#13", "#14", "#15", "#18", "#19", "#20", "#40", "#48"):
        assert n not in out.stdout

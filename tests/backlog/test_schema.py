"""INT-004 — backlog schema validation + the deterministic issue selector.

Acceptance line under test, verbatim:
  "docs/backlog/issues.yaml (this backlog) validated by schema test; …"
  "loop.sh implements LOOP.md: pick next Ready issue by order with deps done
   and no blocked label; …"

The selector (scripts/backlog/next_issue.py) is the executable form of
LOOP.md step 1, including the deliberate rule that `awaiting-human` SATISFIES a
dependency — without it 58 % of the backlog silently never becomes Ready.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
ISSUES = REPO / "docs" / "backlog" / "issues.yaml"
EPICS = REPO / "docs" / "backlog" / "epics.yaml"

PHASES = {"P0", "P1", "P2", "P3"}
STATUSES = {"todo", "doing", "done", "blocked", "awaiting-human", "withdrawn"}
LABEL_PREFIXES = ("area:", "risk:", "approval:", "blocked:")
LABEL_LITERALS = {"live-smoke", "gpu"}


def _issues() -> list[dict]:
    return yaml.safe_load(ISSUES.read_text(encoding="utf-8"))


def test_ids_unique_and_well_formed() -> None:
    issues = _issues()
    ids = [i["id"] for i in issues]
    assert len(ids) == len(set(ids))
    # 175 blueprint + INT-176..178 (security review) + INT-179/193 (mobile,
    # owner directive 2026-08-27) + INT-294 (the end-to-end walkthrough
    # measured TTS admission consuming the clip deadline, and the resulting
    # mute latching for the session) + INT-319 (dev on-prem TTS lane + latency
    # harness) + INT-320 (embeddable white-label integration: partner
    # "Start pre-visit" button + tenant handshake, ADR-029) + INT-321 (mobile
    # intake mode chooser up front) + INT-322 (embed intake mode bound inside
    # the signed launch ticket) + INT-323 (department-dynamic previsit routing:
    # inbound department → branch → served pack) + INT-324..329 and
    # INT-343..345 (the 2026-09-26 production audit's agent-owned P0/P1 fixes:
    # audio guard, prod refusal of dev config, George route, generator marker,
    # mobile API base, Twilio, George client, attestation, staging artefact) +
    # INT-330..342 (motion system MOTION-1..13 from
    # docs/design/motion/motion-verification.md) + INT-346 (CI restoration
    # after the billing outage) + INT-347 (withdrawn MinIO image)
    # + INT-348 (Play Integrity + device login smoke, split from INT-344)
    # + INT-349..354 (2026-09-26 owner follow-ups: sensitive intake categories,
    # CI part 2, admin ops console, production API host, specialty review
    # queue landing, int-demo consolidation into main)
    # + INT-355 (bare ask_if/skip_if slot names never resolved across the
    # pack chain, so gated questions were never asked)
    # + INT-356 (counsel-supplied values for the data-category register that
    # INT-349's fail-closed gate reads; split out because no agent may author
    # them)
    # + INT-357 (staging passes App Attest and SMS configuration to the API
    # and fails closed when unset; the work of PR #573, filed so it closes its
    # own issue instead of INT-352's)
    # + INT-358 (the owner's SMS vendor decision — DPA, KVKK Art. 9
    # cross-border mechanism, egress allow-list row — split out of INT-329
    # because no agent may make it)
    # + INT-359 (accessibility device audit and statement publication, split
    # out of INT-226 because they are owner and counsel work)
    # + INT-360..363 (the four WCAG defects the INT-226 report found:
    # orientation lock, OTP paste/autofill, iOS error/status announcements,
    # kiosk idle warning)
    # + INT-364 (the owner's organisational evidence and counsel's readings
    # for Board decision 2018/10, split out of INT-215)
    # + INT-365..369 (the engineering gaps the INT-215 mapping found: staff
    # second factor and session bounds, access review and offboarding, key
    # rotation schedule, dependency updates, API fuzzing in CI).
    # Grow this count only with a stated reason.
    # + INT-372 (slice S5 of INT-354: the int-demo visit-card chevron fix,
    # ported to main as its own one-issue PR)
    # + INT-379 (the question-set generator's duration=omit, code answers and
    # skip_if, asked for by the department verifications, GitHub #623).
    assert len(ids) == 295
    import re

    for i in ids:
        assert re.fullmatch(r"INT-\d{3}", i), f"malformed id {i}"


def test_fields_valid() -> None:
    epic_ids = {e["id"] for e in yaml.safe_load(EPICS.read_text(encoding="utf-8"))}
    ids = {i["id"] for i in _issues()}
    for issue in _issues():
        iid = issue["id"]
        assert issue["phase"] in PHASES, f"{iid}: bad phase"
        assert issue.get("status", "todo") in STATUSES, f"{iid}: bad status"
        assert issue["epic"] in epic_ids, f"{iid}: unknown epic {issue['epic']}"
        for dep in issue.get("depends_on", []):
            assert dep in ids, f"{iid}: depends on unknown {dep}"
        for label in issue.get("labels", []):
            ok = label in LABEL_LITERALS or label.startswith(LABEL_PREFIXES)
            assert ok, f"{iid}: unknown label {label}"
        if issue.get("status") != "withdrawn":
            assert issue.get("title") and issue.get("acceptance"), f"{iid}: empty"


def test_no_dependency_cycles() -> None:
    graph = {i["id"]: list(i.get("depends_on", [])) for i in _issues()}
    WHITE, GREY, BLACK = 0, 1, 2
    colour = dict.fromkeys(graph, WHITE)

    def visit(node: str, stack: list[str]) -> None:
        colour[node] = GREY
        for dep in graph[node]:
            if colour[dep] == GREY:
                raise AssertionError(f"cycle: {' -> '.join([*stack, node, dep])}")
            if colour[dep] == WHITE:
                visit(dep, [*stack, node])
        colour[node] = BLACK

    for node in graph:
        if colour[node] == WHITE:
            visit(node, [])


SELECTOR_FIXTURE = """
- id: INT-901
  epic: E00-governance
  phase: P0
  title: "done already"
  depends_on: []
  labels: []
  status: done
  acceptance: ["x"]
- id: INT-902
  epic: E00-governance
  phase: P0
  title: "awaiting a human"
  depends_on: [INT-901]
  labels: [approval:human-clinical]
  status: awaiting-human
  acceptance: ["x"]
- id: INT-903
  epic: E00-governance
  phase: P1
  title: "later phase, ready"
  depends_on: [INT-901]
  labels: []
  status: todo
  acceptance: ["x"]
- id: INT-904
  epic: E00-governance
  phase: P0
  title: "blocked by label"
  depends_on: [INT-901]
  labels: ["blocked:contract"]
  status: todo
  acceptance: ["x"]
- id: INT-905
  epic: E00-governance
  phase: P0
  title: "dep not satisfied"
  depends_on: [INT-906]
  labels: []
  status: todo
  acceptance: ["x"]
- id: INT-906
  epic: E00-governance
  phase: P0
  title: "still todo"
  depends_on: []
  labels: []
  status: doing
  acceptance: ["x"]
- id: INT-907
  epic: E00-governance
  phase: P0
  title: "ready via awaiting-human dep"
  depends_on: [INT-902]
  labels: []
  status: todo
  acceptance: ["x"]
"""


def _select(fixture: str, tmp_path: Path) -> str:
    f = tmp_path / "issues.yaml"
    f.write_text(fixture, encoding="utf-8")
    out = subprocess.run(
        ["uv", "run", "python", "scripts/backlog/next_issue.py", "--file", str(f)],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


def test_selector_follows_loop_rules(tmp_path: Path) -> None:
    # INT-907 is the first P0 todo whose deps are satisfied: 904 is blocked:*,
    # 905's dep is only `doing`, and 902's awaiting-human SATISFIES 907's dep.
    assert _select(SELECTOR_FIXTURE, tmp_path) == "INT-907"


def test_selector_reports_waiting_human_when_nothing_workable(tmp_path: Path) -> None:
    ready_todo = (
        'title: "ready via awaiting-human dep"\n'
        "  depends_on: [INT-902]\n  labels: []\n  status: todo"
    )
    fixture = SELECTOR_FIXTURE.replace(
        ready_todo,
        ready_todo.replace("status: todo", "status: done"),
    ).replace(
        'title: "later phase, ready"\n  depends_on: [INT-901]\n  labels: []\n  status: todo',
        'title: "later phase, ready"\n  depends_on: [INT-901]\n  labels: []\n  status: done',
    )
    out = _select(fixture, tmp_path)
    assert out.startswith("WAITING_HUMAN"), out
    assert "INT-902" in out, "must list the exact awaiting-human ids"

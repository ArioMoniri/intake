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
    # + INT-396 (backlog status reconciliation and its drift guard).
    # + INT-401 (console rollback split out of INT-187; waits on a CD target).
    # + INT-402..403 (split out of INT-123: the embedding-model choice and
    # the consent-withdrawal handling of record vectors; both the owner's).
    # + INT-408 (workers-tier SLO targets, split out of INT-021; the owner's).
    # + INT-398..400 (split out of INT-122: the document-engine choice, the
    # real e-Nabiz/MHRS samples, the on-device MHRS date-order defect).
    # + INT-412 (Apple-native chrome: symbol registry, Liquid Glass, icon proposal).
    # + INT-413 (counsel drafts for the open legal texts; never served).
    # Grow this count only with a stated reason.
    # + INT-372 (slice S5 of INT-354: the int-demo visit-card chevron fix,
    # ported to main as its own one-issue PR).
    # + INT-370 (slice S3 of INT-354: the int-demo visits calendar and Geçmiş
    # list, ported to main as its own one-issue PR).
    # + INT-317 (previsit output store + hospital read-back: filed on int-demo
    # on 2026-09-04 and carried to main by INT-354 slice 1 with its code; the
    # id is held by no other row on main or any remote branch).
    # + INT-376 (the production API's move to Frankfurt, split out of INT-352
    # because it waits on AWS approving the eu-central-1 GPU quota).
    # + INT-318 (the Acıbadem appointments read source and /v1/visits/sync,
    # INT-354 slice S2: cited by int-demo code with no backlog row anywhere).
    # kiosk idle warning).
    # + INT-377 (a malformed probe-results file 500'd /admin/models and
    # /admin/ops; found by INT-181, fixed and closed in the same PR).
    # + INT-380 (INT-121 clause 3, the LOINC+unit score on a named corpus,
    # awaiting-human) + INT-381 (INT-124's on-hardware latency and live smoke,
    # gpu), both split out by INT-124's PR so each delivered row can close.
    # + INT-385 (record quantities render with the locale's decimal separator;
    # found by INT-124's PR, filed as GitHub #635 and delivered as its own PR).
    # + INT-373 (the Keycloak realm emits the claims the admin console
    # requires; found by INT-365).
    # + INT-392 (a session with a previsit output could not be deleted by the
    # DSAR erasure, the retention executor or the integration teardown; found
    # on main's check-integration, fixed and closed in the same PR).
    # + INT-393 (a patient who issued a Doctor Link could not be erased; found
    # by INT-392, fixed and closed in the same PR).
    # + INT-391 (the console accepts every valid WebAuthn credential id; found
    # by INT-378's PR, filed as GitHub #646 and delivered as its own PR).
    # + INT-386 (the typed rail, note, patient summary and FHIR narrative write
    # quantities through INT-385's renderer; INT-096's recorded defect, GitHub #638).
    # + INT-387 (the accessibility conformance report re-rated after the
    # INT-361..363 fixes, with a guard against rows that outlive their fix;
    # found by INT-360's PR, filed as GitHub #640).
    # + INT-397 (the three status lines INT-362 left silent are announced, and
    # SC 4.1.3 moves to Supports; found by INT-387's MC-26, GitHub #659).
    # + INT-390 (Keycloak 26.1.4 carried 64 OSV advisories and the realm on
    # main never imported; found by INT-378, fixed and closed in the same PR).
    # + INT-396 (backlog rows reconciled with what merged, and the status
    # consistency guard; GitHub #655, carried by its own PR).
    # + INT-405 (the backlog sync pages past 500 issues and keeps issue state in
    # step with rows; found by INT-396, GitHub #675).
    # + INT-409 (Vizitlerim reads "today" from an injected clock in the
    # Europe/Istanbul day instead of a date pinned in every build; found by
    # INT-179's close-out, GitHub #688).
    # + INT-410 (the synthetic seed accounts leave the release bundle, proven
    # over the production export; audit F30, found by INT-179's close-out,
    # GitHub #689).
    # + INT-404 (triage rule evidence lines write quantities for the reader's
    # locale; INT-386's finding, GitHub #673).
    # + INT-382 (the compiler refuses a suppress_slot in any layer that removes
    # a slot a red-flag rule reads; H-1 of the PR #628 verification, GitHub #629).
    # + INT-415 (ElevenLabs delivery profiles per question context and the
    # on-prem TTS wiring guide; owner request, GitHub #706).
    # + INT-429 (the vulnerabilities gate: brace-expansion and urllib3 upgrades,
    # time-boxed node-forge exception; owner decision, GitHub #727).
    # + INT-431 (the embed sample's JWT fixture is built at runtime so no
    # token-shaped literal sits at rest; found merging main into #481, #733).
    # + INT-395 (no path erased notification_preferences and the DSAR export
    # did not list Doctor Links; found by INT-393, fixed and closed in the
    # same PR).
    # + INT-406 (RED acknowledgement: the clinic Safety inbox, its clock and
    # SLA page — invariant 49, found unowned by INT-020's PR as GitHub #681).
    # + INT-426 (CI on AWS: the gate runner over S3 + SSM with the aws-ci
    # commit status; owner request, GitHub #721).
    # + INT-407 (the files/02 §2b visit lifecycle — a RED visit cannot silently
    # move; found by INT-406's PR, whose visit_transition had no caller, #684).
    # + INT-432 (the clinical decisions register under owner decision D18,
    # agent-authored and independently agent-verified; GitHub #735).
    # + INT-378 (the Keycloak provider that writes the aaguid and credential_id
    # session notes, GitHub #621) and INT-389 (its TOTP clause split out as an
    # owner decision, GitHub #644).
    # + INT-448 (the #642 sign-off packet items resolved under D18; GitHub #759).
    # + INT-414 (conversational delivery around verbatim questions, stacked on
    # INT-415; owner request, GitHub #705).
    # + INT-447 (INT-414's 48 delivery lines verified under D18; GitHub #758).
    # + INT-449 (Turkish voice casting: a native Turkish voice and model, owner
    # request, GitHub #762).
    # + INT-421 (production release: the admin tier on the AWS host, GitHub #713).
    # + INT-463 (all CI jobs on the AWS self-hosted runner intake-aws-ci; owner
    # order of 3 Oct 2026, GitHub #790) and INT-467 (that runner as a pool of
    # three, each with its own user, daemon and network namespace, GitHub #799).
    # + INT-500 (lockfile advisories since 4 Oct upgraded, not ignored, so the
    # vulnerabilities gate stops blocking every merge; GitHub #851).
    # order of 3 Oct 2026, GitHub #790).
    # + INT-460 (a second admin approver on the synthetic host is a second
    # Keycloak user, not a dev bearer; owner request, GitHub #785).
    # + INT-453 (the voice-runtime RED path triggers the winning rule's own
    # script, not rule_ids[0]; found by INT-446, GitHub #767).
    # + INT-446 (a RED fires end to end in the app: the rules-engine hop on
    # both lanes and the pre-positioned RED screen mounted; found by the
    # INT-440 voice end-to-end test, GitHub #756).
    # + INT-465 (the generic RED active from CD-24, and the synthetic host's red
    # rule set signed with a synthetic-only OpenBao test key, D23; GitHub #794).
    # + INT-424 (ElevenLabs delivery profiles v2 tuned from rendered samples and
    # the expressive-model ADR proposal; owner request, GitHub #719).
    # order of 3 Oct 2026, GitHub #790).
    # + INT-430 (the agent council, reshaped into a post-bind verifier by the
    # medical and AI/ML challenger reviews; owner request, GitHub #732).
    # + INT-428 (hosted model lanes for the synthetic deployment, switchable
    # from the admin panel with a GPU switch-over; owner decision, ADR-035,
    # GitHub #724).
    # + INT-475 (a hop RED reaches the clinic Safety inbox and the device's
    # location answer reaches the server, so ON_SITE notifies staff; found by
    # the #796 clinical reviews, INT-465 finding 6; GitHub #814).
    assert len(ids) == 351
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

"""INT-544 — the path filter: which ci.yml lanes a pull request's diff can skip.

Acceptance lines under test (docs/backlog/issues.yaml, INT-544):
  - lanes unaffected by a diff are skipped, with a conservative mapping and a
    test of the mapping;
  - the security gates (gitleaks, semgrep, bandit, trivy, osv, checkov,
    licence, SBOM, PHI scan, claims scan) and the evidence and no_placeholders
    gates are never skipped;
  - a skipped lane still reports success to its required check.

scripts/ci/lanes.py decides; ci.yml applies the decision step by step. The
first half of this file runs the decision on real git repositories and on the
committed tree; the second half reads the workflows.
"""

from __future__ import annotations

import copy
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "ci"))

import lanes  # noqa: E402

WORKFLOWS = REPO / ".github" / "workflows"
EVERY = {"python": True, "ts": True, "integration": True}
ROOTS = frozenset({"apps/mobile", "apps/admin-web", "packages/clinical-schemas"})


# --- the mapping ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("paths", "expected"),
    [
        # Python only: check-ts has nothing to read.
        (
            ["services/api/src/intake_api/app.py", "tests/api/test_visits.py", "uv.lock"],
            {"python": True, "ts": False, "integration": True},
        ),
        # docs, files and infra are read by Python tests and the compose tier.
        (
            ["docs/evidence/INT-544.md", "files/00_STATE.md", "infra/docker-compose.dev.yml"],
            {"python": True, "ts": False, "integration": True},
        ),
        # TypeScript only: the compose tier reads no workspace file, but Python
        # tests read apps/ (source slicing, catalogues), so check-py still runs.
        (
            ["apps/mobile/src/app/session.tsx", "apps/admin-web/src/ops/load.ts"],
            {"python": True, "ts": True, "integration": False},
        ),
        # A shared package is both: run everything that can read it.
        (
            ["packages/clinical-schemas/schemas/openapi.json", "packages/protocols/x.py"],
            EVERY,
        ),
        # The root TypeScript and pnpm configuration.
        (["pnpm-lock.yaml"], {"python": True, "ts": True, "integration": False}),
        (["tsconfig.base.json"], {"python": True, "ts": True, "integration": False}),
        # CI itself runs every lane, including a change to this filter.
        (["scripts/ci/lanes.py"], EVERY),
        (["infra/ci/aws-runner/seed.sh"], EVERY),
        ([".github/workflows/ci.yml"], EVERY),
        (["Makefile"], EVERY),
        # Nothing to reason about: run everything.
        ([], EVERY),
    ],
)
def test_the_mapping(paths: list[str], expected: dict[str, bool]) -> None:
    assert lanes.lanes_for(paths, ROOTS) == expected


def test_python_runs_for_every_path_class() -> None:
    for path in ("apps/mobile/a.ts", "docs/x.md", "package.json", "tests/a.py", "Makefile"):
        assert lanes.lanes_for([path], ROOTS)["python"] is True, path


def test_python_files_read_the_typescript_workspaces() -> None:
    """The premise that keeps check-py on every diff: Python reads apps/."""
    hits = subprocess.run(
        ["git", "grep", "-l", "-E", "apps/mobile|apps/admin-web", "--", "*.py"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert any(hit.startswith("tests/") for hit in hits), hits


def test_no_typescript_workspace_reads_python_tests_docs_or_infra() -> None:
    """The premise that lets check-ts skip a diff outside the workspaces."""
    pattern = r"(\.\./)+(docs|files|tests|services|infra|migrations)/"
    hits = subprocess.run(
        [
            "git",
            "grep",
            "-n",
            "-E",
            pattern,
            "--",
            "apps",
            "packages/clinical-schemas",
            "packages/embed-sdk",
            ":!*.md",
            ":!*.py",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    assert hits == "", hits


def test_the_workspace_roots_come_from_pnpm_workspace_yaml() -> None:
    globs = lanes.workspace_globs((REPO / "pnpm-workspace.yaml").read_text(encoding="utf-8"))
    assert globs == tuple(yaml.safe_load((REPO / "pnpm-workspace.yaml").read_text())["packages"])
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.split()
    roots = lanes.ts_workspace_roots(tracked, globs)
    assert {"apps/mobile", "apps/admin-web", "packages/clinical-schemas"} <= roots
    assert not any(root.startswith(".claude") for root in roots)
    # every root holds a package.json, and only those do
    assert all((REPO / root / "package.json").is_file() for root in roots)


@pytest.mark.parametrize(
    "text",
    [
        "packages:\n  - foo/*\nonlyBuiltDependencies: esbuild\n",
        "packages:\n  - '!apps/x'\n",
        "packages:\n  foo/*\n",
        "catalog:\n  a: 1\n",
    ],
)
def test_a_workspace_file_it_cannot_read_is_refused(text: str) -> None:
    with pytest.raises(ValueError):
        lanes.workspace_globs(text)


# --- the decision on a real repository --------------------------------------------------


def _git(repo: Path, *args: str) -> str:
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
    }
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True, env=env
    ).stdout


def _merge_repo(tmp_path: Path, change: dict[str, str | None]) -> Path:
    """A base commit, a pull request head with `change`, and their merge commit."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    files = {
        "pnpm-workspace.yaml": 'packages:\n  - "apps/*"\n',
        "apps/web/package.json": "{}\n",
        "apps/web/src/a.ts": "export {};\n",
        "services/api/app.py": "x = 1\n",
        "docs/a.md": "a\n",
    }
    for name, body in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(body)
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "base")
    _git(repo, "checkout", "-q", "-b", "pr")
    for name, body in change.items():
        if body is None:
            _git(repo, "rm", "-q", name)
        else:
            (repo / name).parent.mkdir(parents=True, exist_ok=True)
            (repo / name).write_text(body)
            _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", "pr")
    _git(repo, "checkout", "-q", "main")
    (repo / "docs/b.md").write_text("main moved on\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "main")
    _git(repo, "merge", "-q", "--no-ff", "--no-edit", "pr")
    return repo


def _decide(
    repo: Path, monkeypatch: pytest.MonkeyPatch, event: str = "pull_request"
) -> tuple[dict[str, bool], str]:
    monkeypatch.chdir(repo)
    return lanes.decide(event, "HEAD^1", "HEAD")


def test_a_python_only_pull_request_skips_check_ts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _merge_repo(tmp_path, {"services/api/app.py": "x = 2\n"})
    decided, reason = _decide(repo, monkeypatch)
    assert decided == {"python": True, "ts": False, "integration": True}
    assert "skipped: ts" in reason
    # the merge commit's first parent is main: main's own change is not the PR's
    assert "1 changed paths" in reason


def test_a_workspace_only_pull_request_skips_the_compose_tier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _merge_repo(tmp_path, {"apps/web/src/a.ts": "export const a = 1;\n"})
    assert _decide(repo, monkeypatch)[0] == {"python": True, "ts": True, "integration": False}


def test_a_move_out_of_a_workspace_still_runs_check_ts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Near miss: with rename detection the diff would name only docs/a.ts."""
    repo = _merge_repo(tmp_path, {"apps/web/src/a.ts": None, "docs/a.ts": "export {};\n"})
    assert _decide(repo, monkeypatch)[0]["ts"] is True


def test_a_push_runs_every_lane(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _merge_repo(tmp_path, {"services/api/app.py": "x = 2\n"})
    assert _decide(repo, monkeypatch, event="push")[0] == EVERY


def test_a_checkout_that_is_not_a_merge_commit_runs_every_lane(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _merge_repo(tmp_path, {"services/api/app.py": "x = 2\n"})
    _git(repo, "checkout", "-q", "pr")
    decided, reason = _decide(repo, monkeypatch)
    assert decided == EVERY and "two-parent merge" in reason


def test_a_git_failure_runs_every_lane(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    not_a_repo = tmp_path / "plain"
    not_a_repo.mkdir()
    decided, reason = _decide(not_a_repo, monkeypatch)
    assert decided == EVERY and "could not be read" in reason


def test_the_output_is_what_github_output_reads(capsys: pytest.CaptureFixture[str]) -> None:
    assert lanes.main(["--event", "push"]) == 0
    out = capsys.readouterr()
    assert out.out == "python=true\nts=true\nintegration=true\n"
    assert out.err.startswith("lanes: ")


# --- the workflows ------------------------------------------------------------------------

#: ci.yml job -> the lane that may skip its steps. Every other job of ci.yml, and
#: every job of security.yml, must never read the lane decision.
LANE_OF_JOB = {
    "check-py-shard": "python",
    "check-py": "python",
    "check-ts": "ts",
    "check-integration": "integration",
}


def _workflow(name: str) -> dict[str, object]:
    document = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _jobs(name: str) -> dict[str, dict[str, object]]:
    jobs = _workflow(name)["jobs"]
    assert isinstance(jobs, dict)
    return jobs


def _lane_findings(job: str, body: dict[str, object], lane: str) -> list[str]:
    """How a lane job could skip a lane it must run."""
    out: list[str] = []
    steps = body["steps"]
    assert isinstance(steps, list)
    ids = [step.get("id") for step in steps]
    if ids.count("lanes") != 1:
        return [f"{job}: no single decision step"]
    index = ids.index("lanes")
    decide = steps[index]
    if index != 1 or steps[0].get("with", {}).get("fetch-depth") != 2:
        out.append(f"{job}: the decision must follow a checkout that has the merge's parents")
    run = str(decide.get("run"))
    if "scripts/ci/lanes.py" not in run or "GITHUB_OUTPUT" not in run:
        out.append(f"{job}: the decision step does not run lanes.py into GITHUB_OUTPUT")
    if "if" in decide:
        out.append(f"{job}: the decision step itself is conditional")
    for step in steps[index + 1 :]:
        if f"steps.lanes.outputs.{lane} != 'false'" not in str(step.get("if", "")):
            what = step.get("name") or step.get("uses") or step.get("run")
            out.append(f"{job}: step {what!r} does not run unless {lane} is exactly false")
    job_if = str(body.get("if", ""))
    if job_if and "cancelled()" not in job_if:
        out.append(f"{job}: a job-level condition would skip the job, not just its steps")
    return out


def test_each_lane_job_decides_first_and_skips_only_on_an_explicit_false() -> None:
    jobs = _jobs("ci.yml")
    findings = [
        finding
        for job, lane in LANE_OF_JOB.items()
        for finding in _lane_findings(job, jobs[job], lane)
    ]
    assert findings == []


def _missing_output_skips(steps: list[dict[str, object]]) -> None:
    # `== 'true'` would skip the lane whenever the decision wrote nothing
    steps[-1]["if"] = "steps.lanes.outputs.ts == 'true'"


def _unconditional(steps: list[dict[str, object]]) -> None:
    steps[-1].pop("if", None)


def _shallow(steps: list[dict[str, object]]) -> None:
    steps[0].pop("with", None)


def _conditional_decision(steps: list[dict[str, object]]) -> None:
    steps[1]["if"] = "github.event_name == 'pull_request'"


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (_missing_output_skips, "does not run unless"),
        (_unconditional, "does not run unless"),
        (_shallow, "merge's parents"),
        (_conditional_decision, "itself is conditional"),
    ],
)
def test_a_near_miss_lane_job_is_caught(
    mutate: Callable[[list[dict[str, object]]], None], expected: str
) -> None:
    body = copy.deepcopy(_jobs("ci.yml")["check-ts"])
    mutate(body["steps"])  # type: ignore[arg-type]
    assert any(expected in finding for finding in _lane_findings("check-ts", body, "ts"))


def test_a_job_level_lane_condition_is_caught() -> None:
    body = copy.deepcopy(_jobs("ci.yml")["check-ts"])
    body["if"] = "github.event_name == 'push'"
    assert any("job-level" in finding for finding in _lane_findings("check-ts", body, "ts"))


def test_no_other_job_reads_the_lane_decision() -> None:
    for name in ("ci.yml", "security.yml"):
        for job, body in _jobs(name).items():
            if name == "ci.yml" and job in LANE_OF_JOB:
                continue
            text = yaml.safe_dump(body)
            assert "lanes" not in text, f"{name}:{job} reads the path filter"


@pytest.mark.parametrize(
    "gate",
    ["gitleaks", "sast", "vulnerabilities", "iac", "licenses", "sbom", "phi-scan", "claims-scan"],
)
def test_the_security_gates_have_no_condition(gate: str) -> None:
    job = _jobs("security.yml")[gate]
    assert "if" not in job, gate
    assert all("if" not in step for step in job["steps"]), gate


def test_the_gates_job_runs_its_scans_on_every_diff() -> None:
    steps = _jobs("ci.yml")["gates"]["steps"]
    for script in ("no_placeholders.sh", "assert_no_vendor_calls.sh"):
        step = next(s for s in steps if script in str(s.get("run", "")))
        assert "if" not in step, script
    evidence = next(s for s in steps if "evidence_check.sh" in str(s.get("run", "")))
    assert evidence["if"] == "github.event_name == 'pull_request'"

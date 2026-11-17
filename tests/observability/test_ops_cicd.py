"""INT-187 — the ops collector's CI/CD read: runs, failing jobs, gates, releases.

Fixtures (tests/fixtures/ops/github_cicd_*.json) are ``gh api`` recordings of
``repos/ArioMoniri/intake/<path>`` taken 2026-09-27 — each file names its path
(``runs_main`` = ``actions/runs?branch=main``, ``jobs`` keyed by run id,
``check_runs`` keyed by sha, ``pulls_open``, ``branch_main``, ``rules_main``,
``releases``, ``tags``, ``security_tag_runs`` for deid-tr-ner-v1) — trimmed to
the fields the source reads plus identifying context, with every personal or
free-text field (actor, head_commit, display_title, user, title, body, author,
committer, message, labels, assignees) dropped. runs_main keeps the newest 12
runs: the 13th's id passes the TCKN checksum, which the no-PHI gate refuses.
Main is unprotected, no ruleset; every ci run failed on check-integration.
No test dials GitHub.

The repository has no ``v*`` tag, so the signing path runs on a variant
DERIVED IN-TEST from the recorded release, security run and its jobs, with
``sign-and-attest`` set to each state; every derivation says so where it is.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from intake_api.admin.ops_prom import BRANCH_LABEL, ID_LABEL
from intake_platform.egress import EgressDenied
from intake_platform.slo import load_metrics_catalog
from intake_probes.ops_ci import GITHUB_API, CiSourceError
from intake_probes.ops_cicd import REQUIRED_GATES, SIGN_TAG_PREFIX, CicdSnapshot, GithubCicdSource
from intake_probes.ops_collector import (
    OPS_CICD_FAMILIES,
    OPS_COLLECTOR_SOURCE_UP,
    OpsCollector,
    ops_collector_from_env,
)
from prometheus_client import REGISTRY, generate_latest

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "ops"
WORKFLOWS = REPO / ".github" / "workflows"
CATALOG = REPO / "observability" / "metrics_catalog.yaml"
TOKEN = "gh-read-only-secret-value"
MAIN_HEAD = "f893dcf5e90a6289831a553bd12be87a7e7a9b6b"
RELEASE_SHA = "1a0977c8c630cd5ff8232bf7a27be2599e1322ab"
FAILED_CI_RUN, SECURITY_RUN = 36297500470, 36297500448
JOBS_814 = f"/actions/runs/{FAILED_CI_RUN}/jobs"
MAIN_CHECKS = f"/commits/{MAIN_HEAD}/check-runs"
SIGN_RUNS = "/actions/workflows/security.yml/runs"
SIGNED = {"status": "completed", "conclusion": "success"}
MARK = "zz-personal-marker"  # id-shaped on purpose: only construction keeps it out
ENV = {"INTAKE_OPS_GITHUB_REPO": "ArioMoniri/intake", "INTAKE_OPS_GITHUB_TOKEN_PATH": "x/github"}

COLLECTED = (*OPS_CICD_FAMILIES, OPS_COLLECTOR_SOURCE_UP)

#: The families and labels the API composite queries (INT-187 contract).
FAMILIES = {
    "ops_cicd_run": ["workflow", "branch", "run_number", "status", "conclusion", "head_sha"],
    "ops_cicd_run_duration_seconds": ["workflow", "branch", "run_number"],
    "ops_cicd_run_updated_seconds": ["workflow", "branch", "run_number"],
    "ops_cicd_failed_job": ["workflow", "branch", "run_number", "job"],
    "ops_cicd_failed_jobs": ["workflow", "branch", "run_number"],
    "ops_cicd_branch_gate": ["branch", "workflow", "gate", "conclusion"],
    "ops_cicd_pr_gate": ["pr", "workflow", "gate", "conclusion"],
    "ops_cicd_branch_checks_enforced": ["branch"],
    "ops_cicd_release": ["tag", "head_sha"],
    "ops_cicd_release_published_seconds": ["tag"],
    "ops_cicd_release_signing": ["tag", "state"],
}


def _load(name: str) -> Any:
    return json.loads((FIXTURES / f"github_cicd_{name}.json").read_text(encoding="utf-8"))


def recorded() -> dict[str, Any]:
    """Every recorded answer, keyed by the API path the source asks for."""
    answers: dict[str, Any] = {
        "/actions/runs": _load("runs_main"),
        "/branches/main": _load("branch_main"),
        "/rules/branches/main": _load("rules_main"),
        "/pulls": _load("pulls_open"),
        "/releases": _load("releases"),
        "/tags": _load("tags"),
        SIGN_RUNS: _load("security_tag_runs"),
    }
    answers.update({f"/actions/runs/{i}/jobs": body for i, body in _load("jobs").items()})
    answers.update({f"/commits/{s}/check-runs": body for s, body in _load("check_runs").items()})
    return answers


class FakeGitHub:
    """An ``httpx.MockTransport`` handler over the recordings, routed by path."""

    def __init__(self) -> None:
        self.answers = recorded()
        self.calls: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == f"Bearer {TOKEN}"
        path = request.url.path.removeprefix("/repos/ArioMoniri/intake")
        self.calls.append(path)
        answer = self.answers.get(path)
        if isinstance(answer, BaseException):
            raise answer
        if isinstance(answer, httpx.Response):
            return answer
        return httpx.Response(200, json=answer) if answer is not None else httpx.Response(404)

    def source(self, token: Callable[[], str] = lambda: TOKEN, **kw: Any) -> GithubCicdSource:
        return GithubCicdSource(
            "ArioMoniri/intake", token, transport=httpx.MockTransport(self), **kw
        )

    def read_twice(self, **kw: Any) -> CicdSnapshot:
        """Read, forget the calls, read again: ``calls`` is then the steady state."""
        source = self.source(**kw)
        source.read()
        self.calls.clear()
        return source.read()

    def entry(self, run_id: int) -> Any:
        return next(r for r in self.answers["/actions/runs"]["workflow_runs"] if r["id"] == run_id)

    def jobs(self, run_id: int) -> Any:
        return self.answers[f"/actions/runs/{run_id}/jobs"]["jobs"]


def _run(github: FakeGitHub, workflow: str, number: int) -> Any:
    runs = github.source().read().runs
    return next(r for r in runs if (r.workflow, r.run_number) == (workflow, number))


def _v_release(
    github: FakeGitHub, sign_job: dict[str, Any] | None, run_sha: str | None = RELEASE_SHA
) -> None:
    """DERIVED IN-TEST: the release as ``v1.0.0``; ``run_sha=None`` keeps "no run"."""
    github.answers["/releases"][0]["tag_name"] = "v1.0.0"
    github.answers["/tags"][0]["name"] = "v1.0.0"
    if run_sha is not None:
        run = {**github.entry(SECURITY_RUN), "head_branch": "v1.0.0", "head_sha": run_sha}
        github.answers[SIGN_RUNS] = {"total_count": 1, "workflow_runs": [run]}
    jobs = github.jobs(SECURITY_RUN)
    recorded_sign = next(job for job in jobs if job["name"] == "sign-and-attest")
    jobs.remove(recorded_sign)
    if sign_job is not None:
        jobs.append({**recorded_sign, **sign_job})


def _samples() -> list[tuple[str, dict[str, str]]]:
    return [(s.name, s.labels) for f in COLLECTED for m in f.collect() for s in m.samples]


def _sample(name: str, **labels: str) -> float | None:
    return REGISTRY.get_sample_value(name, labels)


def _secrets() -> Any:
    return type("S", (), {"get_kv": lambda self, path: {"token": TOKEN}})()


@pytest.fixture(autouse=True)
def _clear_children() -> None:
    for family in COLLECTED:
        family.clear()


def _pull_request_jobs() -> dict[str, tuple[str, ...]]:
    """Workflow stem -> jobs every pull request runs, read from the workflow YAML."""
    gates: dict[str, tuple[str, ...]] = {}
    for path in sorted(WORKFLOWS.glob("*.yml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        if "pull_request" in doc.get("on", doc.get(True)):  # YAML 1.1: bare `on:` is True
            jobs = {j: s for j, s in doc["jobs"].items() if "refs/tags" not in s.get("if", "")}
            fed = {n for s in jobs.values() for n in ([s["needs"]] if "needs" in s else [])}
            gates[path.stem] = tuple(j for j in jobs if j not in fed)  # INT-544: shard feeds
    return gates


class TestRequiredGates:
    def test_required_gates_are_the_jobs_every_pull_request_runs_named_once(self) -> None:
        assert dict(REQUIRED_GATES) == _pull_request_jobs()
        # the near-miss: the tag-only signing job runs on no pull request
        names = [gate for gates in REQUIRED_GATES.values() for gate in gates]
        assert "sign-and-attest" not in names and len(names) == len(set(names))

    def test_the_signing_prefix_is_the_one_security_yml_signs_on(self) -> None:
        doc = yaml.safe_load((WORKFLOWS / "security.yml").read_text(encoding="utf-8"))
        assert doc.get("on", doc.get(True))["push"]["tags"] == [f"{SIGN_TAG_PREFIX}*"]
        sign_if = doc["jobs"]["sign-and-attest"]["if"]
        assert sign_if == f"startsWith(github.ref, 'refs/tags/{SIGN_TAG_PREFIX}')"


class TestRuns:
    def test_recent_runs_per_workflow_newest_first_with_completed_durations(self) -> None:
        runs = FakeGitHub().source().read().runs
        assert [(r.workflow, r.run_number) for r in runs] == [
            *(("ci", n) for n in (814, 809, 806, 801, 797)),
            *(("security", n) for n in (340, 335, 332, 327, 323)),
        ]
        assert _run(FakeGitHub(), "ci", 814).duration_s == 1371  # 05:32:28Z -> 05:55:19Z
        assert _run(FakeGitHub(), "security", 340).duration_s == 53
        capped = FakeGitHub().source(runs_per_workflow=2).read().runs
        assert [r.run_number for r in capped] == [814, 809, 340, 335]

    def test_a_running_run_has_no_duration_no_conclusion_and_no_jobs_call(self) -> None:
        github = FakeGitHub()
        # DERIVED IN-TEST: the recorded ci #814 as it looked while running
        github.entry(FAILED_CI_RUN).update(status="in_progress", conclusion=None)
        run = _run(github, "ci", 814)
        assert (run.status, run.conclusion, run.duration_s) == ("in_progress", "none", None)
        assert run.failed_job_count is None and JOBS_814 not in github.calls

    def test_a_failed_run_names_id_shaped_failing_jobs_and_counts_every_one(self) -> None:
        ci = _run(FakeGitHub(), "ci", 814)
        assert (ci.failed_jobs, ci.failed_job_count) == (("check-integration",), 1)
        assert _run(FakeGitHub(), "security", 340).failed_job_count is None  # green: no count
        github = FakeGitHub()
        jobs = github.jobs(FAILED_CI_RUN)
        # DERIVED IN-TEST: a second failing job whose name is free text
        jobs.append({**jobs[0], "id": 1, "name": "Check (py 3.12)", "conclusion": "timed_out"})
        ci = _run(github, "ci", 814)
        assert (ci.failed_jobs, ci.failed_job_count) == (("check-integration",), 2)

    def test_a_completed_attempt_s_jobs_are_read_once_while_it_is_shown(self) -> None:
        github = FakeGitHub()
        source = github.source(runs_per_workflow=4)

        def jobs_calls() -> list[str]:
            github.calls.clear()
            source.read()
            return [call for call in github.calls if call.endswith("/jobs")]

        assert len(jobs_calls()) == 4
        assert jobs_calls() == []
        # the near-miss: a re-run is a new attempt, so its jobs are read again
        # (DERIVED IN-TEST: #814 and its recorded jobs as attempt 2)
        github.entry(FAILED_CI_RUN)["run_attempt"] = 2
        for job in github.jobs(FAILED_CI_RUN):
            job["run_attempt"] = 2
        assert jobs_calls() == [JOBS_814]
        # the cache holds only what the latest read shows: #814 drops out of the
        # window (DERIVED IN-TEST) and, back again, is read afresh
        runs, entry = github.answers["/actions/runs"]["workflow_runs"], github.entry(FAILED_CI_RUN)
        runs.remove(entry)
        assert jobs_calls() == ["/actions/runs/36292732181/jobs"]  # #797 enters the window
        runs.insert(0, entry)
        assert jobs_calls() == [JOBS_814]

    def test_jobs_answered_for_another_attempt_are_unknown_and_not_cached(self) -> None:
        github = FakeGitHub()
        # DERIVED IN-TEST: a re-run of #814 started between the runs and the jobs call
        for job in github.jobs(FAILED_CI_RUN):
            job["run_attempt"] = 2
        run = next(r for r in github.read_twice().runs if r.run_number == 814)
        assert (run.failed_jobs, run.failed_job_count) == ((), None)  # unknown, never zero
        assert JOBS_814 in github.calls


class TestGates:
    def test_every_required_gate_on_the_branch_head_and_each_pr_is_reported(self) -> None:
        snapshot = FakeGitHub().source().read()
        assert snapshot.head_sha == MAIN_HEAD
        expected = {(w, g): "success" for w, gates in REQUIRED_GATES.items() for g in gates}
        expected[("ci", "check-integration")] = "failure"
        assert {(g.workflow, g.gate): g.conclusion for g in snapshot.branch_gates} == expected
        assert [pull.number for pull in snapshot.pulls] == [661, 660, 658, 648, 657]
        for pull in snapshot.pulls:
            assert {(g.workflow, g.gate): g.conclusion for g in pull.gates} == expected

    def test_missing_pending_and_the_newest_check_run_wins(self) -> None:
        github = FakeGitHub()
        checks = github.answers[MAIN_CHECKS]["check_runs"]
        # DERIVED IN-TEST from the recorded check runs of main's head:
        checks[:] = [check for check in checks if check["name"] != "gitleaks"]
        check_py = next(c for c in checks if c["name"] == "check-py")
        check_py.update(status="in_progress", conclusion=None, completed_at=None)
        integration = next(c for c in checks if c["name"] == "check-integration")
        rerun = {**integration, "id": integration["id"] + 1, "conclusion": "success"}
        older = {**integration, "id": integration["id"] - 1, "conclusion": "cancelled"}
        rerun["started_at"], older["started_at"] = "2026-09-27T06:10:00Z", "2026-09-27T05:00:00Z"
        checks += [rerun, older]
        gates = {g.gate: g.conclusion for g in github.source().read().branch_gates}
        assert (gates["gitleaks"], gates["check-py"]) == ("missing", "pending")
        assert gates["check-integration"] == "success"  # the older cancelled run never wins

    @pytest.mark.parametrize(
        ("rules", "protection", "enforced"),
        [
            (None, None, False),  # the recording: main unprotected, no ruleset
            ([{"type": "required_status_checks", "ruleset_id": 1}], None, True),
            ([{"type": "pull_request", "ruleset_id": 1}], None, False),
            ([], {"enforcement_level": "non_admins", "contexts": ["check-py"]}, True),
            ([], {"enforcement_level": "off", "contexts": ["check-py"]}, False),
            ([], {"enforcement_level": "everyone", "contexts": [], "checks": []}, False),
        ],
    )
    def test_checks_are_enforced_only_by_a_rule_or_protection_requiring_them(
        self, rules: list[Any] | None, protection: dict[str, Any] | None, enforced: bool
    ) -> None:
        github = FakeGitHub()
        # DERIVED IN-TEST (all but the first row): a protected or ruleset-governed main
        if rules is not None:
            github.answers["/rules/branches/main"] = rules
        if protection is not None:
            github.answers["/branches/main"].update(
                protected=True, protection={"enabled": True, "required_status_checks": protection}
            )
        assert github.source().read().checks_enforced is enforced

    def test_only_all_green_gates_are_cached(self) -> None:
        github = FakeGitHub()
        # DERIVED IN-TEST: main's head re-run green; the PR heads stay red
        for check in github.answers[MAIN_CHECKS]["check_runs"]:
            check["conclusion"] = "success"
        github.read_twice()
        checks = [call for call in github.calls if call.endswith("/check-runs")]
        assert MAIN_CHECKS not in checks
        assert len(checks) == 5  # a red gate can be re-run on the same sha: read again


class TestReleases:
    def test_the_recorded_release_is_joined_with_its_tag_and_not_applicable(self) -> None:
        github = FakeGitHub()
        (r,) = github.source().read().releases
        published = datetime(2026, 8, 27, 16, 0, 47, tzinfo=UTC)
        assert (r.tag, r.head_sha, r.published_at) == ("deid-tr-ner-v1", RELEASE_SHA, published)
        assert (r.prerelease, r.signing) == (False, "not_applicable")
        assert SIGN_RUNS not in github.calls

    @pytest.mark.parametrize(
        ("release", "tags"),
        [
            ({"draft": True}, None),
            ({"tag_name": "deid tr ner"}, None),
            ({}, [{"name": "another-tag", "commit": {"sha": RELEASE_SHA}}]),
            ({}, [{"name": "deid-tr-ner-v1", "commit": {"sha": "not-a-sha"}}]),
        ],
    )
    def test_drafts_and_unresolvable_tags_are_dropped(
        self, release: dict[str, Any], tags: list[Any] | None
    ) -> None:
        github = FakeGitHub()
        github.answers["/releases"][0].update(release)  # DERIVED IN-TEST
        if tags is not None:
            github.answers["/tags"] = tags
        assert github.source().read().releases == ()

    @pytest.mark.parametrize(
        ("sign_job", "run_sha", "state"),
        [
            (SIGNED, RELEASE_SHA, "signed"),
            ({"status": "completed", "conclusion": "failure"}, RELEASE_SHA, "sign_failed"),
            ({"status": "completed", "conclusion": "skipped"}, RELEASE_SHA, "sign_failed"),
            ({"status": "in_progress", "conclusion": None}, RELEASE_SHA, "sign_pending"),
            (None, RELEASE_SHA, "not_signed"),  # the run has no sign-and-attest job
            (SIGNED, MAIN_HEAD, "not_signed"),  # a signed run, but of another commit
            (SIGNED, None, "not_signed"),  # the recorded answer: no run on the tag
        ],
    )
    def test_a_v_tag_reads_its_state_from_sign_and_attest_on_its_commit(
        self, sign_job: dict[str, Any] | None, run_sha: str | None, state: str
    ) -> None:
        github = FakeGitHub()
        _v_release(github, sign_job, run_sha)
        (release,) = github.read_twice().releases
        assert (release.tag, release.signing) == ("v1.0.0", state)
        # a final state is cached per tag and commit; a pending or absent one is asked again
        final = state in ("signed", "sign_failed")
        assert github.calls.count(SIGN_RUNS) == (0 if final else 1)


def _no_token() -> str:
    raise CiSourceError("token_unavailable")


class TestRefusals:
    @pytest.mark.parametrize(
        ("path", "answer", "code"),
        [
            (MAIN_CHECKS, httpx.Response(500), "github_http_500"),
            ("/branches/main", httpx.Response(403), "github_http_403"),
            ("/pulls", EgressDenied("api.github.com not allow-listed"), "egress_denied"),
            ("/tags", httpx.ConnectError("down"), "github_unreachable"),
            ("/rules/branches/main", {"not": "a list"}, "github_bad_response"),
            (JOBS_814, httpx.Response(200, text="<"), "github_bad_response"),
            ("token", _no_token, "token_unavailable"),  # OpenBao would not give it
        ],
    )
    def test_any_failing_sub_call_fails_the_whole_read(
        self, path: str, answer: Any, code: str
    ) -> None:
        github = FakeGitHub()
        github.answers[path] = answer
        source = github.source(token=answer) if path == "token" else github.source()
        with pytest.raises(CiSourceError) as refusal:
            source.read()
        assert refusal.value.code == code
        assert TOKEN not in f"{refusal.value!s} {refusal.value!r}"
        # the read stops at the refusal: nothing is asked after it
        assert github.calls[-1:] == ([] if path == "token" else [path])

    def test_a_refused_read_clears_every_series_and_a_later_read_restores_them(self) -> None:
        github = FakeGitHub()
        collector = OpsCollector(cicd=github.source())
        assert collector.configured and collector.collect_once()["cicd"] == "ok"
        assert {name for name, _ in _samples()} >= set(FAMILIES)
        github.answers[MAIN_CHECKS] = httpx.Response(500)
        assert collector.collect_once()["cicd"] == "github_http_500"
        assert [name for name, _ in _samples() if name.startswith("ops_cicd_")] == []
        assert _sample("ops_collector_source_up", source="cicd") == 0.0
        github.answers = recorded()
        assert collector.collect_once()["cicd"] == "ok"
        assert _sample("ops_cicd_branch_checks_enforced", branch="main") == 0.0
        assert _sample("ops_collector_source_up", source="cicd") == 1.0


class TestExport:
    def test_the_snapshot_becomes_the_series_the_console_queries(self) -> None:
        OpsCollector(cicd=FakeGitHub().source()).collect_once()
        key = {"workflow": "ci", "branch": "main", "run_number": "814"}
        state = {"status": "completed", "conclusion": "failure", "head_sha": MAIN_HEAD}
        assert _sample("ops_cicd_run", **key, **state) == 1.0
        assert _sample("ops_cicd_run_duration_seconds", **key) == 1371.0
        updated = datetime(2026, 9, 27, 5, 55, 19, tzinfo=UTC).timestamp()
        assert _sample("ops_cicd_run_updated_seconds", **key) == updated
        assert _sample("ops_cicd_failed_job", **key, job="check-integration") == 1.0
        assert _sample("ops_cicd_failed_jobs", **key) == 1.0
        green = {"workflow": "security", "branch": "main", "run_number": "340"}
        assert _sample("ops_cicd_failed_jobs", **green) is None
        gate = {"workflow": "ci", "gate": "check-integration", "conclusion": "failure"}
        assert _sample("ops_cicd_branch_gate", branch="main", **gate) == 1.0
        assert _sample("ops_cicd_pr_gate", pr="661", **gate) == 1.0
        assert _sample("ops_cicd_release", tag="deid-tr-ner-v1", head_sha=RELEASE_SHA) == 1.0
        published = datetime(2026, 8, 27, 16, 0, 47, tzinfo=UTC).timestamp()
        assert _sample("ops_cicd_release_published_seconds", tag="deid-tr-ner-v1") == published
        assert _sample("ops_cicd_release_signing", tag="deid-tr-ner-v1", state="not_applicable")

    def test_every_family_is_catalogued_and_every_label_value_fits_the_console(self) -> None:
        github = FakeGitHub()
        _v_release(github, SIGNED)
        OpsCollector(cicd=github.source()).collect_once()
        by_name = {m.name: m for m in load_metrics_catalog(CATALOG).metrics}
        exported = {name: sorted(labels) for name, labels in _samples()}
        for name, labels in FAMILIES.items():
            assert by_name[name].labels == labels, f"{name} catalogue drifted (invariant 13)"
            assert by_name[name].type == "gauge" and by_name[name].status == "live"
            assert exported[name] == sorted(labels)
        assert "cicd" in by_name["ops_collector_source_up"].description
        for name, labels in _samples():  # the API's PromSession shapes (ops_prom)
            for label, value in labels.items():
                pattern = BRANCH_LABEL if label in ("branch", "tag") else ID_LABEL
                assert pattern.match(value), (name, label, value)

    def test_free_text_and_people_never_reach_the_snapshot_or_a_label(self) -> None:
        github = FakeGitHub()
        # DERIVED IN-TEST: the personal fields the recordings dropped, put back
        person = {"login": MARK, "name": MARK, "email": f"{MARK}@example.invalid"}
        commit = {"message": MARK, "author": person}
        for run in github.answers["/actions/runs"]["workflow_runs"]:
            run.update(actor=person, triggering_actor=person, display_title=MARK)
            run["head_commit"] = commit
        for pull in github.answers["/pulls"]:
            pull.update(title=MARK, body=MARK, user=person, labels=[{"name": MARK}])
        github.answers["/releases"][0].update(name=MARK, body=MARK, author=person)
        source = github.source()
        OpsCollector(cicd=source).collect_once()
        assert MARK not in repr(source.read())
        assert MARK not in generate_latest(REGISTRY).decode()


class TestFromEnv:
    def test_the_cicd_source_rides_the_ci_source_s_repo_token_and_branch(self) -> None:
        env = {**ENV, "INTAKE_OPS_GITHUB_BRANCH": "release/1"}
        collector = ops_collector_from_env(env, secrets=_secrets)
        ci, cicd = collector.ci, collector.cicd
        assert ci is not None and cicd is not None
        target = (cicd.repo, cicd.branch, cicd.api_base)
        assert target == (ci.repo, ci.branch, ci.api_base)
        assert target == ("ArioMoniri/intake", "release/1", GITHUB_API)
        assert cicd.token is ci.token and cicd.token() == TOKEN
        assert cicd.transport is not None and cicd.transport is not ci.transport
        # the near-miss: no CI source, no CI/CD source — nothing is guessed
        assert ops_collector_from_env({"INTAKE_OPS_GPU_HOST_ID": "gpu-a"}).cicd is None

    def test_the_cicd_calls_go_through_the_egress_guard(self) -> None:
        env = {**ENV, "INTAKE_OPS_GITHUB_API": "https://ghe.invalid"}
        cicd = ops_collector_from_env(env, secrets=_secrets).cicd
        assert cicd is not None
        # an API base the allow-list does not name is refused in process,
        # before any DNS lookup (files/10 §4) — so every CI/CD tile reads unknown
        with pytest.raises(CiSourceError) as refusal:
            cicd.read()
        assert refusal.value.code == "egress_denied"

"""CI/CD and releases for the ops collector (INT-187).

Recent runs per workflow on the watched branch and the jobs that failed in
them, the required gates on the branch head and the open pull requests,
whether GitHub enforces those gates, and releases with their signing state —
read **server-side** like :mod:`.ops_ci`: the read-only token from OpenBao,
through the egress guard (files/10 §4, invariant 14). The console only reads
the series the collector exported.

**Ids and states only (invariant 6).** A failing job keeps its name only when
it is id-shaped (the rest are counted, never named); a pull request keeps its
number and head sha; a release its tag, commit and publish time. Actors, the
head commit, display titles, PR titles/bodies/authors and release names,
bodies and authors are never read into a value.

**Fail closed.** Every sub-call refuses with :mod:`.ops_ci`'s codes and any
one of them fails the whole read, so the collector clears every CI/CD series
rather than painting half a picture (invariant 17).

**Caches hold only what cannot change**, pruned to what the latest read shows:
a completed run attempt's failing jobs; a signing state that is final for its
tag *and* commit; a sha's gates once every one concluded ``success`` — a
failed or cancelled gate can be re-run on the same sha, so it is read again.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any, Final

import httpx

from intake_probes.ops_ci import (
    CI_CONCLUSIONS,
    GITHUB_API,
    REF_RE,
    SHA_RE,
    CiRun,
    CiSourceError,
    check_github_target,
    github_client,
    github_get,
    parse_github_time,
    parse_run,
)
from intake_probes.ops_gpu import OpsConfigError

__all__ = [
    "REQUIRED_GATES",
    "SIGNING_STATES",
    "SIGN_TAG_PREFIX",
    "CicdRun",
    "CicdSnapshot",
    "GateResult",
    "GithubCicdSource",
    "PullGates",
    "Release",
]

#: Workflow file stem -> the jobs that run on EVERY pull request (their check
#: run names). Derived from .github/workflows/ci.yml and security.yml; a job
#: whose ``if:`` restricts it to tags (``sign-and-attest``) is not a gate.
#: tests/observability/test_ops_cicd.py re-derives it from the YAML.
REQUIRED_GATES: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        "ci": ("check-py", "check-ts", "check-integration", "gates"),
        "security": (
            "gitleaks",
            "sast",
            "vulnerabilities",
            "iac",
            "licenses",
            "sbom",
            "phi-scan",
            "claims-scan",
        ),
    }
)
_GATE_NAMES: Final = frozenset(gate for gates in REQUIRED_GATES.values() for gate in gates)

#: The conclusions that make a run (or a job) a failure worth naming.
FAILED_CONCLUSIONS: Final = frozenset({"failure", "timed_out", "startup_failure"})
#: A job name that may become a label: the API's id shape (ops_prom.ID_LABEL).
JOB_NAME: Final = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")
GATE_PENDING: Final = "pending"
GATE_MISSING: Final = "missing"

#: security.yml's ``sign-and-attest`` job runs on ``tags: ["v*"]`` under
#: ``if: startsWith(github.ref, 'refs/tags/v')`` — the only signing path.
SIGN_WORKFLOW_FILE: Final = "security.yml"
SIGN_JOB: Final = "sign-and-attest"
SIGN_TAG_PREFIX: Final = "v"
SIGNING_STATES: Final = frozenset(
    {"signed", "sign_failed", "sign_pending", "not_signed", "not_applicable"}
)
_FINAL_SIGNING: Final = frozenset({"signed", "sign_failed", "not_applicable"})

_PER_PAGE: Final = 100
_RELEASE_PAGE: Final = 10
_SIGN_RUN_PAGE: Final = 5
_MAX_RUNS_PER_WORKFLOW: Final = 20
_MAX_PULLS: Final = 20
#: A check run that has not started yet is the newest there is (a queued re-run).
_NOT_STARTED: Final = datetime.max.replace(tzinfo=UTC)


@dataclass(frozen=True)
class CicdRun(CiRun):
    """A :class:`CiRun` plus what the CI/CD console adds to it."""

    #: Whole seconds from start to last update; completed runs only.
    duration_s: int | None
    #: Id-shaped names of the failing jobs (failure-class runs only).
    failed_jobs: tuple[str, ...]
    #: Every failing job, named or not; ``None`` unless the run failed.
    failed_job_count: int | None


@dataclass(frozen=True)
class GateResult:
    workflow: str
    gate: str
    #: A CI conclusion, ``pending`` (not completed) or ``missing`` (no check run).
    conclusion: str


@dataclass(frozen=True)
class PullGates:
    number: int
    head_sha: str
    gates: tuple[GateResult, ...]


@dataclass(frozen=True)
class Release:
    tag: str
    head_sha: str
    published_at: datetime
    prerelease: bool
    signing: str


@dataclass(frozen=True)
class CicdSnapshot:
    branch: str
    head_sha: str
    runs: tuple[CicdRun, ...]
    branch_gates: tuple[GateResult, ...]
    checks_enforced: bool
    pulls: tuple[PullGates, ...]
    releases: tuple[Release, ...]


def _bad() -> CiSourceError:
    return CiSourceError("github_bad_response")


def _positive_int(raw: object) -> int | None:
    if isinstance(raw, int) and not isinstance(raw, bool) and raw > 0:
        return raw
    return None


def _sha(raw: object) -> str | None:
    return raw if isinstance(raw, str) and SHA_RE.match(raw) else None


def _cache() -> Any:
    """A per-instance dict the frozen source may mutate: not in init, repr or eq."""
    return field(default_factory=dict, init=False, repr=False, compare=False)


def _keep_only[K, V](cache: dict[K, V], live: set[K]) -> None:
    for key in [key for key in cache if key not in live]:
        del cache[key]


@dataclass(frozen=True)
class _Api:
    """One read's client: every call shares the token, the root and the refusals."""

    client: httpx.Client
    token: str
    root: str

    def get(self, path: str, **params: str | int) -> Any:
        return github_get(self.client, f"{self.root}{path}", self.token, params)

    def listing(self, path: str, **params: str | int) -> list[Any]:
        body = self.get(path, **params)
        if not isinstance(body, list):
            raise _bad()
        return body

    def items(self, path: str, key: str, **params: str | int) -> list[Any]:
        body = self.get(path, **params)
        if not isinstance(body, dict) or not isinstance(body.get(key), list):
            raise _bad()
        return list(body[key])


def _check_order(check: Mapping[str, Any]) -> tuple[datetime, int]:
    started = parse_github_time(check.get("started_at")) or _NOT_STARTED
    return started, _positive_int(check.get("id")) or 0


def _gate_conclusion(check: Mapping[str, Any] | None) -> str:
    if check is None:
        return GATE_MISSING
    if check.get("status") != "completed":
        return GATE_PENDING
    conclusion = check.get("conclusion") or "none"
    if not isinstance(conclusion, str) or conclusion not in CI_CONCLUSIONS:
        raise _bad()
    return conclusion


def _protection_enforces_checks(body: Mapping[str, Any]) -> bool:
    protection = body.get("protection")
    if body.get("protected") is not True or not isinstance(protection, Mapping):
        return False
    checks = protection.get("required_status_checks")
    if not isinstance(checks, Mapping) or checks.get("enforcement_level") == "off":
        return False
    return any(isinstance(checks.get(key), list) and checks[key] for key in ("contexts", "checks"))


def _signing_state(job: Mapping[str, Any] | None) -> str:
    if job is None:
        return "not_signed"
    if job.get("status") != "completed":
        return "sign_pending"
    return "signed" if job.get("conclusion") == "success" else "sign_failed"


@dataclass(frozen=True)
class GithubCicdSource:
    """Runs, failing jobs, required gates and releases of ``repo`` on ``branch``."""

    repo: str
    token: Callable[[], str]
    branch: str = "main"
    api_base: str = GITHUB_API
    transport: httpx.BaseTransport | None = field(default=None, repr=False)
    timeout_s: float = 10.0
    runs_per_workflow: int = 5
    pr_limit: int = 5
    # (run id, attempt) -> failing jobs; sha -> all-green gates; (tag, sha) -> final state
    _jobs_cache: dict[tuple[int, int], tuple[tuple[str, ...], int]] = _cache()
    _gates_cache: dict[str, tuple[GateResult, ...]] = _cache()
    _signing_cache: dict[tuple[str, str], str] = _cache()

    def __post_init__(self) -> None:
        check_github_target(self.repo, self.branch, self.api_base)
        if not 1 <= self.runs_per_workflow <= _MAX_RUNS_PER_WORKFLOW:
            raise OpsConfigError(f"runs_per_workflow must be 1..{_MAX_RUNS_PER_WORKFLOW}")
        if not 1 <= self.pr_limit <= _MAX_PULLS:
            raise OpsConfigError(f"pr_limit must be 1..{_MAX_PULLS}")

    def read(self) -> CicdSnapshot:
        """One consistent snapshot, or :class:`CiSourceError` — never a partial one."""
        token = self.token()
        root = f"{self.api_base.rstrip('/')}/repos/{self.repo}"
        with github_client(self.transport, self.timeout_s) as client:
            api = _Api(client=client, token=token, root=root)
            runs, attempts = self._runs(api)
            head_sha, enforced = self._branch(api)
            branch_gates = self._gates(api, head_sha)
            pulls = tuple(
                PullGates(number=number, head_sha=sha, gates=self._gates(api, sha))
                for number, sha in self._pulls(api)
            )
            releases = self._releases(api)
        _keep_only(self._jobs_cache, attempts)
        _keep_only(self._gates_cache, {head_sha, *(pull.head_sha for pull in pulls)})
        _keep_only(self._signing_cache, {(r.tag, r.head_sha) for r in releases})
        return CicdSnapshot(
            branch=self.branch,
            head_sha=head_sha,
            runs=runs,
            branch_gates=branch_gates,
            checks_enforced=enforced,
            pulls=pulls,
            releases=releases,
        )

    # --- runs and their failing jobs -------------------------------------------

    def _runs(self, api: _Api) -> tuple[tuple[CicdRun, ...], set[tuple[int, int]]]:
        entries = api.items(
            "/actions/runs", "workflow_runs", branch=self.branch, per_page=_PER_PAGE
        )
        by_workflow: dict[str, dict[int, tuple[CiRun, Mapping[str, Any]]]] = {}
        for entry in entries:
            if not isinstance(entry, Mapping) or _positive_int(entry.get("id")) is None:
                continue
            run = parse_run(entry, self.branch)
            if run is None:
                continue
            held = by_workflow.setdefault(run.workflow, {})
            prior = held.get(run.run_number)
            if prior is None or run.updated_at > prior[0].updated_at:
                held[run.run_number] = (run, entry)
        runs: list[CicdRun] = []
        attempts: set[tuple[int, int]] = set()
        for workflow in sorted(by_workflow):
            held = by_workflow[workflow]
            for number in sorted(held, reverse=True)[: self.runs_per_workflow]:
                run, entry = held[number]
                runs.append(self._cicd_run(api, run, entry, attempts))
        return tuple(runs), attempts

    def _cicd_run(
        self,
        api: _Api,
        run: CiRun,
        entry: Mapping[str, Any],
        attempts: set[tuple[int, int]],
    ) -> CicdRun:
        duration: int | None = None
        started = parse_github_time(entry.get("run_started_at"))
        if run.status == "completed" and started is not None and started <= run.updated_at:
            duration = int((run.updated_at - started).total_seconds())
        names: tuple[str, ...] = ()
        count: int | None = None
        if run.conclusion in FAILED_CONCLUSIONS:
            key = (int(entry["id"]), _positive_int(entry.get("run_attempt")) or 1)
            attempts.add(key)
            names, count = self._failed_jobs(api, key)
        return CicdRun(
            **asdict(run), duration_s=duration, failed_jobs=names, failed_job_count=count
        )

    def _failed_jobs(self, api: _Api, key: tuple[int, int]) -> tuple[tuple[str, ...], int | None]:
        cached = self._jobs_cache.get(key)
        if cached is not None:
            return cached
        run_id, attempt = key
        listed = api.items(f"/actions/runs/{run_id}/jobs", "jobs", per_page=_PER_PAGE)
        jobs = [job for job in listed if isinstance(job, Mapping)]
        if any(job.get("run_attempt", attempt) != attempt for job in jobs):
            # a re-run started between the two calls: this attempt's jobs are
            # unknown this pass — never a count of zero, never cached
            return (), None
        failing = [job for job in jobs if job.get("conclusion") in FAILED_CONCLUSIONS]
        names = {
            name
            for job in failing
            if isinstance(name := job.get("name"), str) and JOB_NAME.match(name)
        }
        result = (tuple(sorted(names)), len(failing))
        self._jobs_cache[key] = result
        return result

    # --- required gates ----------------------------------------------------------

    def _branch(self, api: _Api) -> tuple[str, bool]:
        body = api.get(f"/branches/{self.branch}")
        if not isinstance(body, dict):
            raise _bad()
        commit = body.get("commit")
        head_sha = _sha(commit.get("sha")) if isinstance(commit, Mapping) else None
        if head_sha is None:
            raise _bad()
        rules = api.listing(f"/rules/branches/{self.branch}", per_page=_PER_PAGE)
        by_ruleset = any(
            isinstance(rule, Mapping) and rule.get("type") == "required_status_checks"
            for rule in rules
        )
        return head_sha, _protection_enforces_checks(body) or by_ruleset

    def _gates(self, api: _Api, sha: str) -> tuple[GateResult, ...]:
        cached = self._gates_cache.get(sha)
        if cached is not None:
            return cached
        checks = api.items(f"/commits/{sha}/check-runs", "check_runs", per_page=_PER_PAGE)
        newest: dict[str, Mapping[str, Any]] = {}
        for check in checks:
            if not isinstance(check, Mapping):
                continue
            name = check.get("name")
            if not isinstance(name, str) or name not in _GATE_NAMES:
                continue
            held = newest.get(name)
            if held is None or _check_order(check) > _check_order(held):
                newest[name] = check
        gates = tuple(
            GateResult(workflow=workflow, gate=gate, conclusion=_gate_conclusion(newest.get(gate)))
            for workflow, names in REQUIRED_GATES.items()
            for gate in names
        )
        if all(gate.conclusion == "success" for gate in gates):
            self._gates_cache[sha] = gates
        return gates

    def _pulls(self, api: _Api) -> list[tuple[int, str]]:
        body = api.listing(
            "/pulls", state="open", sort="updated", direction="desc", per_page=self.pr_limit
        )
        pulls: list[tuple[int, str]] = []
        for pull in body[: self.pr_limit]:
            if not isinstance(pull, Mapping):
                continue
            number = _positive_int(pull.get("number"))
            head = pull.get("head")
            sha = _sha(head.get("sha")) if isinstance(head, Mapping) else None
            if number is not None and sha is not None:
                pulls.append((number, sha))
        return pulls

    # --- releases ------------------------------------------------------------------

    def _releases(self, api: _Api) -> tuple[Release, ...]:
        candidates: list[tuple[str, datetime, bool]] = []
        for entry in api.listing("/releases", per_page=_RELEASE_PAGE):
            if not isinstance(entry, Mapping) or entry.get("draft") is not False:
                continue
            tag = entry.get("tag_name")
            published = parse_github_time(entry.get("published_at"))
            if isinstance(tag, str) and REF_RE.match(tag) and published is not None:
                candidates.append((tag, published, entry.get("prerelease") is True))
        if not candidates:
            return ()
        shas: dict[str, str] = {}
        for entry in api.listing("/tags", per_page=_PER_PAGE):
            commit = entry.get("commit") if isinstance(entry, Mapping) else None
            name = entry.get("name") if isinstance(entry, Mapping) else None
            sha = _sha(commit.get("sha")) if isinstance(commit, Mapping) else None
            if isinstance(name, str) and sha is not None:
                shas.setdefault(name, sha)
        releases: list[Release] = []
        for tag, published, prerelease in candidates:
            sha = shas.get(tag)
            if sha is None or any(release.tag == tag for release in releases):
                continue
            signing = self._signing(api, tag, sha)
            releases.append(Release(tag, sha, published, prerelease, signing))
        return tuple(releases)

    def _signing(self, api: _Api, tag: str, sha: str) -> str:
        if not tag.startswith(SIGN_TAG_PREFIX):
            return "not_applicable"
        cached = self._signing_cache.get((tag, sha))
        if cached is not None:
            return cached
        runs = api.items(
            f"/actions/workflows/{SIGN_WORKFLOW_FILE}/runs",
            "workflow_runs",
            branch=tag,
            event="push",
            per_page=_SIGN_RUN_PAGE,
        )
        # only a run on the commit the tag names now signed this release
        mine: list[tuple[int, int]] = []
        for run in runs:
            if not isinstance(run, Mapping) or run.get("head_sha") != sha:
                continue
            run_id = _positive_int(run.get("id"))
            if run_id is not None:
                mine.append((_positive_int(run.get("run_number")) or 0, run_id))
        state = "not_signed"
        if mine:
            newest_id = max(mine)[1]
            jobs = api.items(f"/actions/runs/{newest_id}/jobs", "jobs", per_page=_PER_PAGE)
            job = next(
                (j for j in jobs if isinstance(j, Mapping) and j.get("name") == SIGN_JOB), None
            )
            state = _signing_state(job)
        if state in _FINAL_SIGNING:
            self._signing_cache[(tag, sha)] = state
        return state

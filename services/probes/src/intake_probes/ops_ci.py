"""CI status for the ops collector: the latest GitHub Actions run per workflow (INT-351).

Server-side only. The collector holds a **read-only** GitHub token that it
reads from OpenBao at collection time (invariant 14 — never an env var, never
a file in the tree), asks the Actions API for the newest runs on one branch,
and keeps the newest run of each workflow. The admin console never sees the
token and never dials GitHub; it reads the series the collector exported.

What survives into a series is ids and states only (invariant 6): the workflow
file's stem (``ci`` for ``.github/workflows/ci.yml``), the branch, the run's
status and conclusion from GitHub's closed vocabularies, the head commit sha
and the run's last update. The actor, the commit message and the commit author
never leave this module — a commit message is free text someone typed, and an
author is a person.

**Refusals carry a code, never the token.** A non-2xx answer is
``github_http_<status>``, an unreachable API is ``github_unreachable``, a
token OpenBao would not give is ``token_unavailable``, and a call the egress
guard refused (files/10 §4) is ``egress_denied``. The collector clears the
CI series on any of them, so the console reads *unknown* rather than the last
green it happened to see (invariant 17).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final

import httpx
from intake_platform.egress import EgressDenied

from intake_probes.ops_gpu import ID_SHAPED, OpsConfigError

__all__ = [
    "CI_CONCLUSIONS",
    "CI_STATUSES",
    "GITHUB_API",
    "CiRun",
    "CiSourceError",
    "GithubActionsSource",
]

#: GitHub's public REST API origin. A GitHub Enterprise deployment overrides
#: it through the collector's env; the egress guard decides either way.
GITHUB_API: Final = "https://api.github.com"
_API_VERSION: Final = "2022-11-28"
_PAGE: Final = 30
_REPO_RE: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}$")
_BRANCH_RE: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,99}$")
_SHA_RE: Final = re.compile(r"^[0-9a-f]{40}$")
_WORKFLOW_PATH_RE: Final = re.compile(r"^\.github/workflows/([^/]+)\.ya?ml$")

#: GitHub's documented run ``status`` and ``conclusion`` vocabularies. A value
#: outside them is dropped with its run rather than exported as a label.
CI_STATUSES: Final = frozenset(
    {"queued", "in_progress", "completed", "waiting", "requested", "pending"}
)
CI_CONCLUSIONS: Final = frozenset(
    {
        "success",
        "failure",
        "cancelled",
        "skipped",
        "timed_out",
        "action_required",
        "neutral",
        "stale",
        "startup_failure",
        "none",
    }
)


class CiSourceError(Exception):
    """The CI read failed. ``code`` is machine-shaped and names no secret."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class CiRun:
    workflow: str
    branch: str
    status: str
    conclusion: str
    head_sha: str
    run_number: int
    updated_at: datetime


def _parse_time(raw: object) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo is not None else None


def _run(entry: Mapping[str, Any], branch: str) -> CiRun | None:
    """One API row as a :class:`CiRun`, or ``None`` if any field is not an id."""
    match = _WORKFLOW_PATH_RE.match(str(entry.get("path", "")))
    workflow = match.group(1) if match else ""
    status = entry.get("status")
    conclusion = entry.get("conclusion") or "none"
    sha = entry.get("head_sha")
    number = entry.get("run_number")
    updated = _parse_time(entry.get("updated_at"))
    if (
        not ID_SHAPED.match(workflow)
        or entry.get("head_branch") != branch
        or status not in CI_STATUSES
        or conclusion not in CI_CONCLUSIONS
        or not isinstance(sha, str)
        or not _SHA_RE.match(sha)
        or not isinstance(number, int)
        or updated is None
    ):
        return None
    return CiRun(
        workflow=workflow,
        branch=branch,
        status=str(status),
        conclusion=str(conclusion),
        head_sha=sha,
        run_number=number,
        updated_at=updated,
    )


@dataclass(frozen=True)
class GithubActionsSource:
    """The newest run of every workflow on ``branch`` of ``repo``."""

    repo: str
    token: Callable[[], str]
    branch: str = "main"
    api_base: str = GITHUB_API
    transport: httpx.BaseTransport | None = field(default=None, repr=False)
    timeout_s: float = 10.0

    def __post_init__(self) -> None:
        if not _REPO_RE.match(self.repo) or ".." in self.repo:
            raise OpsConfigError("the GitHub repository must be owner/name")
        if not _BRANCH_RE.match(self.branch) or ".." in self.branch:
            raise OpsConfigError("the branch must be a plain ref name")
        if not self.api_base.startswith("https://"):
            raise OpsConfigError("the GitHub API base must be https")

    def _fetch(self) -> Mapping[str, Any]:
        token = self.token()
        url = f"{self.api_base.rstrip('/')}/repos/{self.repo}/actions/runs"
        try:
            with httpx.Client(
                transport=self.transport, timeout=self.timeout_s, follow_redirects=False
            ) as client:
                response = client.get(
                    url,
                    params={"branch": self.branch, "per_page": _PAGE},
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": _API_VERSION,
                    },
                )
        except EgressDenied:
            raise CiSourceError("egress_denied") from None
        except httpx.HTTPError:
            raise CiSourceError("github_unreachable") from None
        if response.status_code // 100 != 2:
            raise CiSourceError(f"github_http_{response.status_code}")
        try:
            body = response.json()
        except ValueError:
            raise CiSourceError("github_bad_response") from None
        if not isinstance(body, dict) or not isinstance(body.get("workflow_runs"), list):
            raise CiSourceError("github_bad_response")
        return body

    def read(self) -> tuple[CiRun, ...]:
        """Newest run per workflow, newest first by last update."""
        newest: dict[str, CiRun] = {}
        for entry in self._fetch()["workflow_runs"]:
            if not isinstance(entry, Mapping):
                continue
            run = _run(entry, self.branch)
            if run is None:
                continue
            held = newest.get(run.workflow)
            if held is None or run.run_number > held.run_number:
                newest[run.workflow] = run
        return tuple(
            sorted(newest.values(), key=lambda r: (r.updated_at, r.workflow), reverse=True)
        )

"""INT-511 — the pure parts of the job that keeps the synthetic host on main.

scripts/ci/staging_follow_main.sh is the shell around these decisions.
Everything here is
deterministic and side-effect free, so tests/ci/test_staging_follow_lib.py
tests it rather than trusting it: the config, the trigger, "is it merged",
"is it green", "is it forward", the two parity checks, the SSM bootstrap, the
host's verdict lines, the commit status and the dry-run plan.

It runs under a bare python3 (the laptop, or the intake-aws-ci runner), so it
is stdlib-only. scripts/ci/staging_follow_cli.py is its command line: the
shell calls that once per decision and acts on the answer.

Exit codes the shell uses: 0 deployed or nothing to do, 1 red (the deploy,
the smoke or /version parity failed), 2 a usage or harness error, 3 refused.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
import shlex
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

REPO_SLUG = "ArioMoniri/intake"
# The workflow's job id. GitHub names the job's check run after it, and a
# scheduled run attaches that check run to main's head: the green check must
# never count this job's own runs, or one refused night keeps main red.
OWN_CHECK = "staging-follow-main"
S3_PREFIX = "staging-follow"
# SSM's execution timeout, and how long the shell waits beyond it. Both stay
# inside the one-hour role session the workflow assumes.
SSM_TIMEOUT_S = 2700
WAIT_MARGIN_S = 300
PRESIGN_S = 1800
MAX_DESCRIPTION = 140
HOST_SCRIPT = "scripts/ci/staging_follow_host.sh"
SYNTHETIC_HEADER = "x-intake-environment"
SYNTHETIC_VALUE = "staging-synthetic-only"

TRIGGERS = ("nightly", "green_merge")
PENDING_OWNER = "default-pending-owner"
# A scheduled event deploys under `nightly`, a finished CI run on main under
# `green_merge`; a person (manual, workflow_dispatch) deploys under either.
EVENT_TRIGGER = {"schedule": "nightly", "workflow_run": "green_merge"}
PERSON_EVENTS = ("manual", "workflow_dispatch")
EVENTS = (*EVENT_TRIGGER, *PERSON_EVENTS)

EXIT_OK, EXIT_RED, EXIT_HARNESS, EXIT_REFUSED = 0, 1, 2, 3
GREEN_CONCLUSIONS = frozenset({"success", "neutral", "skipped"})

_SHA = re.compile(r"[0-9a-f]{40}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_RUN_ID = re.compile(r"[a-z0-9-]{1,64}")
_CRON_FIELD = r"[0-9*/,-]+"
_CONF_RULES: dict[str, tuple[str, re.Pattern[str]]] = {
    "FOLLOW_TRIGGER": ("trigger", re.compile("|".join(TRIGGERS))),
    "FOLLOW_TRIGGER_DECIDED_BY": (
        "decided_by",
        re.compile(rf"{PENDING_OWNER}|owner:\d{{4}}-\d{{2}}-\d{{2}}"),
    ),
    "FOLLOW_NIGHTLY_CRON": ("nightly_cron", re.compile(rf"{_CRON_FIELD}(?: {_CRON_FIELD}){{4}}")),
    "FOLLOW_STATUS_CONTEXT": ("status_context", re.compile(r"[a-z][a-z0-9-]{1,63}")),
    "STAGING_INSTANCE": ("instance", re.compile(r"i-[0-9a-f]{17}")),
    "STAGING_REGION": ("region", re.compile(r"[a-z]{2}-[a-z]+-\d")),
    "STAGING_BUCKET": ("bucket", re.compile(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]")),
    "STAGING_HOSTNAME": (
        "hostname",
        re.compile(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}"),
    ),
}
# what the shell needs, under the names it uses
SHELL_FIELDS = {
    "FOLLOW_TRIGGER": "trigger",
    "FOLLOW_STATUS_CONTEXT": "status_context",
    "STAGING_INSTANCE": "instance",
    "STAGING_REGION": "region",
    "STAGING_BUCKET": "bucket",
    "STAGING_HOSTNAME": "hostname",
}


class UsageError(ValueError):
    """A caller error: the job refuses rather than guessing."""


@dataclass(frozen=True, slots=True)
class Conf:
    trigger: str
    decided_by: str
    nightly_cron: str
    status_context: str
    instance: str
    region: str
    bucket: str
    hostname: str

    def as_pairs(self) -> dict[str, str]:
        return {key: str(getattr(self, field)) for key, (field, _) in _CONF_RULES.items()}


def parse_conf(text: str) -> Conf:
    """infra/staging/follow-main.conf: KEY=value lines, read, never sourced."""
    seen: dict[str, str] = {}
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep or key not in _CONF_RULES:
            raise UsageError(f"line {number}: unknown key {key!r}")
        if key in seen:
            raise UsageError(f"line {number}: {key} is set twice")
        _, rule = _CONF_RULES[key]
        if not rule.fullmatch(value):
            raise UsageError(f"line {number}: {key} has a malformed value")
        seen[key] = value
    missing = sorted(set(_CONF_RULES) - set(seen))
    if missing:
        raise UsageError(f"missing keys: {', '.join(missing)}")
    conf = Conf(**{_CONF_RULES[k][0]: v for k, v in seen.items()})
    if conf.trigger != "nightly" and not conf.decided_by.startswith("owner:"):
        # the owner picks the trigger; only nightly is the recorded default
        raise UsageError(
            "a trigger other than nightly needs FOLLOW_TRIGGER_DECIDED_BY=owner:<date>"
        )
    return conf


def conf_assignments(conf: Conf) -> str:
    return "".join(f"{k}={shlex.quote(getattr(conf, f))}\n" for k, f in SHELL_FIELDS.items())


@dataclass(frozen=True, slots=True)
class Request:
    event: str
    ref: str
    dry_run: bool
    post_status: bool
    decide: bool


def parse_args(argv: Sequence[str]) -> Request:
    """--event <event> [--ref <40-hex>] [--dry-run] [--no-status] [--decide]."""
    event, ref = "", ""
    flags = {"--dry-run": False, "--no-status": False, "--decide": False}
    args = list(argv)
    while args:
        arg = args.pop(0)
        if arg in flags:
            flags[arg] = True
        elif arg in ("--event", "--ref"):
            if not args:
                raise UsageError(f"{arg} needs a value")
            value = args.pop(0)
            event, ref = (value, ref) if arg == "--event" else (event, value)
        else:
            raise UsageError(f"unknown argument {arg!r}")
    if event not in EVENTS:
        raise UsageError(f"--event must be one of {', '.join(EVENTS)}")
    if ref and not _SHA.fullmatch(ref):
        # a branch name or a short sha would race: the deploy names one commit
        raise UsageError("--ref takes a full lowercase 40-hex commit sha")
    if event == "schedule" and ref:
        raise UsageError("a scheduled run deploys main's head; it takes no --ref")
    if event == "workflow_run" and not ref:
        raise UsageError("a workflow_run deploys the commit CI finished on; give --ref")
    return Request(event, ref, flags["--dry-run"], not flags["--no-status"], flags["--decide"])


def request_assignments(req: Request) -> str:
    pairs = (
        ("FOLLOW_EVENT", req.event),
        ("FOLLOW_REF", req.ref),
        ("FOLLOW_DRY_RUN", "1" if req.dry_run else "0"),
        ("FOLLOW_POST_STATUS", "1" if req.post_status else "0"),
        ("FOLLOW_DECIDE", "1" if req.decide else "0"),
    )
    return "".join(f"{k}={shlex.quote(v)}\n" for k, v in pairs)


def decide(trigger: str, event: str) -> tuple[bool, str]:
    if event in PERSON_EVENTS:
        return True, f"a {event} run deploys under either trigger"
    wanted = EVENT_TRIGGER[event]
    if trigger == wanted:
        return True, f"the trigger is {trigger}"
    return False, f"the trigger is {trigger}; a {event} event deploys only under {wanted}"


def merged(compare_status: str) -> bool:
    """GitHub compare main...<sha>: the sha is on main when it is behind or identical."""
    return compare_status in ("behind", "identical")


def lineage(body: str) -> str:
    """on_main | off_main | unknown, from GitHub's body for compare main...<host sha>.

    A commit GitHub does not hold (404, 422) cannot be on main. The host ran
    such a commit from 2 Oct 2026 (1785dd58, never pushed), and the deploy
    puts it back on main. Any other failure is no answer, never off main.
    """
    try:
        doc = json.loads(body)
    except ValueError:
        return "unknown"
    status = str(doc.get("status", "")) if isinstance(doc, dict) else ""
    if status in ("behind", "identical"):
        return "on_main"
    if status in ("ahead", "diverged", "404", "422"):
        return "off_main"
    return "unknown"


def direction(compare_status: str) -> str:
    """GitHub compare <target>...<host revision>: where the deploy moves the host."""
    answers = {"behind": "forward", "ahead": "backwards", "diverged": "diverged"}
    if compare_status not in answers:
        raise UsageError(
            f"cannot order the host's revision against the target ({compare_status!r})"
        )
    return answers[compare_status]


def green(doc: Mapping[str, Any]) -> tuple[str, str]:
    """green | pending | red | unknown, from a check-runs page (filter=latest)."""
    runs = [r for r in doc.get("check_runs", []) if r.get("name") != OWN_CHECK]
    listed = len(doc.get("check_runs", []))
    if int(doc.get("total_count", listed)) > listed:
        return "unknown", f"{doc.get('total_count')} check runs, {listed} on the page"
    red = sorted(
        str(r.get("name"))
        for r in runs
        if r.get("status") == "completed" and r.get("conclusion") not in GREEN_CONCLUSIONS
    )
    if red:
        return "red", f"failed: {', '.join(red)}"
    running = sorted(str(r.get("name")) for r in runs if r.get("status") != "completed")
    if running or not runs:
        return "pending", f"still running: {', '.join(running) or 'no check has started'}"
    return "green", f"{len(runs)} checks green"


def _version(body: str) -> dict[str, Any] | None:
    try:
        doc = json.loads(body)
    except ValueError:
        return None
    return doc if isinstance(doc, dict) else None


def host_revision(body: str) -> str | None:
    doc = _version(body)
    sha = str(doc.get("git_sha", "")) if doc else ""
    return sha if _SHA.fullmatch(sha) else None


def version_parity(body: str, sha: str) -> tuple[bool, str]:
    """/version names the deployed commit, a build time and an SBOM digest; never "dev"."""
    doc = _version(body)
    if doc is None:
        return False, "/version is not a JSON object"
    problems = []
    if doc.get("git_sha") != sha:
        problems.append(f"git_sha is {str(doc.get('git_sha'))[:12]}, not {sha[:12]}")
    if doc.get("built_at") in (None, "", "dev"):
        problems.append("built_at is not stamped")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(doc.get("sbom_digest", ""))):
        problems.append("sbom_digest is not stamped")
    if problems:
        return False, "; ".join(problems)
    return True, f"git_sha {sha}, built_at {doc['built_at']}, sbom_digest {doc['sbom_digest']}"


def revision_parity(text: str, sha: str) -> tuple[bool, str]:
    """The archive's infra/staging/REVISION is what /version will report."""
    found = text.strip()
    if found == sha and _SHA.fullmatch(found):
        return True, f"REVISION is {sha}"
    return False, f"REVISION is {found[:44]!r}, not {sha}: /version would not name the commit"


def synthetic(headers: str) -> bool:
    for line in headers.splitlines():
        name, sep, value = line.partition(":")
        if sep and name.strip().lower() == SYNTHETIC_HEADER and value.strip() == SYNTHETIC_VALUE:
            return True
    return False


def run_id(sha: str, now_iso: str) -> str:
    if not _SHA.fullmatch(sha):
        raise UsageError("a run id needs a 40-hex sha")
    stamp = _dt.datetime.strptime(now_iso, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y%m%dt%H%M%Sz")
    return f"{stamp}-{sha[:12]}"


def s3_key(run: str) -> str:
    if not _RUN_ID.fullmatch(run):
        raise UsageError("bad run id")
    return f"{S3_PREFIX}/{run}/release.tgz"


def ssm_parameters(
    *, run_id: str, sha: str, archive_url: str, archive_sha256: str, timeout_s: int
) -> dict[str, list[str]]:
    """AWS-RunShellScript: fetch the release, verify it, hand it to its own host script.

    SSM runs these lines with `sh`, so they are POSIX. Tracing is off before
    the URL appears, and the URL is quoted: it is a bearer credential for as
    long as it lives. The archive is the merged commit itself, so the host
    script it carries is reviewed code.
    """
    if not _RUN_ID.fullmatch(run_id):
        raise UsageError("bad run id")
    if not _SHA.fullmatch(sha):
        raise UsageError("bad sha")
    if not _SHA256.fullmatch(archive_sha256):
        raise UsageError("the archive sha256 is not 64 hex")
    if not archive_url.startswith("https://"):
        raise UsageError("the archive URL must be https")
    if not 0 < timeout_s <= 10800:
        raise UsageError("the timeout must be 1..10800 s")
    q = shlex.quote
    return {
        "commands": [
            "set +x",
            "set -eu",
            "umask 022",
            '[ "$(id -u)" -eq 0 ]',
            'releases="${INTAKE_FOLLOW_RELEASES:-/opt/onvizit-releases}"',
            f'incoming="$releases/.incoming.{run_id}"',
            'mkdir -p "$releases"',
            'mkdir "$incoming"',
            "trap 'rm -rf \"$incoming\"' EXIT",
            f'curl --proto =https -fsS -o "$incoming/release.tgz" {q(archive_url)}',
            f"printf '%s  %s\\n' {archive_sha256} \"$incoming/release.tgz\""
            " | sha256sum -c --quiet -",
            'tar -xzf "$incoming/release.tgz" -C "$incoming"',
            'rm -f "$incoming/release.tgz"',
            f'exec bash "$incoming/intake/{HOST_SCRIPT}" --run-id {run_id} --sha {sha}'
            ' --incoming "$incoming"',
        ],
        "executionTimeout": [str(timeout_s)],
    }


@dataclass(frozen=True, slots=True)
class HostVerdict:
    state: str  # green | red | refused
    reason: str
    passed: int
    failed: int


_VERDICT = re.compile(r"^follow=verdict state=(green|red|refused) reason=([a-z_]+)$")


def parse_host(text: str) -> HostVerdict | None:
    verdict = None
    passed = failed = 0
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("smoke: ") and " PASS " in line:
            passed += 1
        elif line.startswith("smoke: ") and " FAIL " in line:
            failed += 1
        match = _VERDICT.match(line)
        if match:
            verdict = (match.group(1), match.group(2))
    if verdict is None:
        return None
    return HostVerdict(verdict[0], verdict[1], passed, failed)


_RED_WORDS = {
    "smoke_red": "smoke red: {failed} check(s) failed on {sha12}",
    "deploy_failed": "deploy.sh stopped on {sha12}; the previous release keeps serving",
    "init_failed": "init.sh stopped on {sha12}; the previous release keeps serving",
}


def status_payload(
    *,
    sha: str,
    context: str,
    hostname: str,
    verdict: HostVerdict | None,
    parity: tuple[bool, str] | None,
) -> dict[str, str]:
    """The commit status for the deployed sha: the smoke verdict, then /version parity."""
    sha12 = sha[:12]
    target = None
    if verdict is None:
        state, words = "error", f"no verdict from the host for {sha12}; see the job log"
    elif verdict.state == "refused":
        if verdict.reason == "frozen":
            state, words = "error", "refused: deploys are frozen (INT-187); nothing changed"
        else:
            state, words = "error", f"refused on the host ({verdict.reason}); nothing changed"
    elif verdict.state == "red":
        template = _RED_WORDS.get(verdict.reason, "red on the host ({reason}) for {sha12}")
        state = "failure"
        words = template.format(failed=verdict.failed, sha12=sha12, reason=verdict.reason)
    elif parity is None or not parity[0]:
        detail = parity[1] if parity else "not read"
        state, words = "failure", f"smoke green but /version fails parity: {detail}"
    else:
        state = "success"
        words = f"smoke green, {verdict.passed} passed: {sha12} runs on the synthetic host"
        target = f"https://{hostname}/version"
    payload = {"state": state, "context": context, "description": words[:MAX_DESCRIPTION]}
    if target is not None:
        payload["target_url"] = target
    return payload


def exit_code(payload: Mapping[str, str]) -> int:
    return {"success": EXIT_OK, "failure": EXIT_RED}.get(payload["state"], EXIT_REFUSED)


def plan(
    *,
    sha: str,
    run_id: str,
    event: str,
    conf: Conf,
    archive_sha256: str,
    archive_bytes: int,
    host_sha: str,
) -> str:
    """What a run will do, step by step. It names no URL: none exists yet."""
    key = s3_key(run_id)
    return "\n".join(
        [
            f"follow-main plan (run {run_id}, event {event}, trigger {conf.trigger})",
            f"  target       {sha}",
            f"  host runs    {host_sha} (https://{conf.hostname}/version)",
            f"  archive      git archive --prefix=intake/ {sha}: {archive_bytes} bytes,"
            f" sha256 {archive_sha256}",
            f"  1. upload    s3://{conf.bucket}/{key} (presigned GET, {PRESIGN_S // 60} min)",
            f"  2. SSM       AWS-RunShellScript on {conf.instance} ({conf.region}),"
            f" timeout {SSM_TIMEOUT_S} s",
            "  3. host      verify sha256, extract, check REVISION, read the release gate"
            " in the running api",
            "  4. host      point /opt/intake at the release; init.sh, deploy.sh, smoke.sh",
            "  5. verify    the host's verdict, then /version parity from outside",
            f"  6. status    {conf.status_context} on {sha[:12]}",
        ]
    )


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()

"""INT-426 — the pure parts of the `aws-ci` runner (scripts/ci/aws_ci.sh).

Everything here is deterministic and side-effect free, so it is unit-tested
(tests/ci/test_aws_ci.py) rather than trusted: argument parsing, the fork
guard, the run id, the SSM bootstrap, an S3 SigV4 presigner, the gate-results
parser, the commit-status payload and the log redaction.

It runs in three places, so it is stdlib-only at import time:
  - on the laptop under the system python3 (parse-args, pr-head, run-id,
    ssm-params, presign, status-payload);
  - on the AWS host inside the runner container, from the harness copy, with
    the PR tree's virtualenv (redact). Only redaction needs the repository's
    identifier detector, and it imports it lazily and fails closed.

Invariant 6: redaction reports counts by kind and never a matched value.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import hmac
import json
import re
import shlex
import sys
import urllib.parse
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

REPO_SLUG = "ArioMoniri/intake"
REPO_OWNER = "ArioMoniri"
STATUS_CONTEXT = "aws-ci"
GATES: tuple[str, ...] = (
    "edge-plugin",
    "check-py",
    "check-ts",
    "check-integration",
    "safety",
    "security",
)
STATE_DIR = "/var/lib/intake-ci"
# GitHub rejects a commit-status description longer than this.
MAX_DESCRIPTION = 140
# SigV4 query authentication refuses anything longer than seven days.
MAX_PRESIGN_SECONDS = 604800

_SHA = re.compile(r"[0-9a-f]{40}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_PR = re.compile(r"[1-9][0-9]{0,6}")
_RUN_ID = re.compile(r"[a-z0-9-]{1,64}")
# What the runner may be asked to do. `gates` is the CI verdict; a probe is a
# one-off measurement (INT-429: is node-forge in the production bundles?) and
# never posts the gate status.
MODES = ("gates", "expo-export")


class UsageError(ValueError):
    """A caller error: the runner refuses rather than guessing."""


@dataclass(frozen=True, slots=True)
class Target:
    kind: str  # "pr" | "ref"
    value: str
    post_status: bool
    mode: str = "gates"


def parse_args(argv: Sequence[str]) -> Target:
    """Exactly one of --pr <n> or --ref <40-hex sha>; optional --no-status, --probe <name>."""
    kind: str | None = None
    value = ""
    post_status = True
    mode = "gates"
    args = list(argv)
    while args:
        flag = args.pop(0)
        if flag == "--no-status":
            post_status = False
            continue
        if flag == "--probe":
            probe = args.pop(0) if args else ""
            if probe not in MODES[1:]:
                raise UsageError(f"unknown probe {probe!r}; known: {', '.join(MODES[1:])}")
            mode, post_status = probe, False
            continue
        if flag not in ("--pr", "--ref"):
            raise UsageError(f"unknown argument: {flag!r}")
        if kind is not None:
            raise UsageError("give exactly one of --pr or --ref")
        if not args:
            raise UsageError(f"{flag} needs a value")
        kind, value = flag[2:], args.pop(0)
    if kind is None:
        raise UsageError("give exactly one of --pr <n> or --ref <40-hex sha>")
    if kind == "pr" and not _PR.fullmatch(value):
        raise UsageError(f"not a pull request number: {value!r}")
    if kind == "ref" and not _SHA.fullmatch(value):
        # a branch name or a short sha would race: the status lands on a commit
        raise UsageError(f"--ref takes a full lowercase 40-hex commit sha, got {value!r}")
    return Target(kind=kind, value=value, post_status=post_status, mode=mode)


def shell_assignments(target: Target) -> str:
    """KEY=value lines for the shell wrapper, every value shell-quoted."""
    pairs = (
        ("AWS_CI_KIND", target.kind),
        ("AWS_CI_VALUE", target.value),
        ("AWS_CI_POST_STATUS", "1" if target.post_status else "0"),
        ("AWS_CI_MODE", target.mode),
    )
    return "".join(f"{k}={shlex.quote(v)}\n" for k, v in pairs)


def pr_head(pr: Mapping[str, Any]) -> str:
    """The head sha of an open pull request whose branch lives in this repository.

    The runner executes the PR's own code on the host that also serves staging,
    next to a privileged dind. Code from a fork is refused outright.
    """
    owner = (pr.get("headRepositoryOwner") or {}).get("login")
    if pr.get("isCrossRepository") or owner != REPO_OWNER:
        raise UsageError(f"refusing a pull request from outside {REPO_SLUG} (head owner {owner!r})")
    if pr.get("state") != "OPEN":
        raise UsageError(f"pull request is {pr.get('state')!r}, not OPEN")
    sha = str(pr.get("headRefOid", ""))
    if not _SHA.fullmatch(sha):
        raise UsageError("pull request head is not a 40-hex sha")
    return sha


def run_id(sha: str, now_iso: str) -> str:
    """`<UTC timestamp>-<sha12>`, lowercase: a compose project name and an S3 prefix."""
    if not _SHA.fullmatch(sha):
        raise UsageError("run id needs a 40-hex sha")
    stamp = _dt.datetime.strptime(now_iso, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y%m%dt%H%M%Sz")
    return f"{stamp}-{sha[:12]}"


def _https(name: str, url: str, *, optional: bool = False) -> str:
    if optional and url == "":
        return url
    if not url.startswith("https://"):
        raise UsageError(f"{name} must be an https URL")
    return url


def ssm_parameters(
    *,
    run_id: str,
    sha: str,
    harness_url: str,
    harness_sha256: str,
    bundle_url: str,
    bundle_sha256: str,
    deid_url: str,
    deid_sha256: str,
    timeout_s: int,
    mode: str = "gates",
) -> dict[str, list[str]]:
    """The AWS-RunShellScript parameters: fetch the harness, verify it, run it.

    SSM writes the lines to a script and runs it with `sh` (dash), so the
    bootstrap is POSIX and hands over to bash only for the verified harness.
    Tracing is off before any URL is touched, and every value is shell-quoted,
    because the presigned URLs are bearer credentials for as long as they live.
    """
    if not _RUN_ID.fullmatch(run_id):
        raise UsageError("bad run id")
    if not _SHA.fullmatch(sha):
        raise UsageError("bad sha")
    if mode not in MODES:
        raise UsageError(f"unknown mode {mode!r}")
    for name, digest in (
        ("harness", harness_sha256),
        ("bundle", bundle_sha256),
        ("deid", deid_sha256),
    ):
        if not _SHA256.fullmatch(digest):
            raise UsageError(f"{name} sha256 is not 64 hex")
    q = shlex.quote
    run_dir = f"{STATE_DIR}/runs/{run_id}"
    lines = [
        "set +x",
        "set -eu",
        "umask 077",
        f"mkdir -p {q(run_dir)}/harness",
        f"curl --proto =https -fsS -o {q(run_dir)}/harness.tgz "
        f"{q(_https('harness_url', harness_url))}",
        f"echo {q(harness_sha256 + '  ' + run_dir + '/harness.tgz')} | sha256sum -c --quiet -",
        f"tar -xzf {q(run_dir)}/harness.tgz -C {q(run_dir)}/harness",
        f"rm -f {q(run_dir)}/harness.tgz",
        " ".join(
            [
                "bash",
                q(f"{run_dir}/harness/scripts/ci/aws_ci_host.sh"),
                "--run-id",
                q(run_id),
                "--sha",
                q(sha),
                "--bundle-url",
                q(_https("bundle_url", bundle_url)),
                "--bundle-sha256",
                q(bundle_sha256),
                "--deid-url",
                q(_https("deid_url", deid_url, optional=True)),
                "--deid-sha256",
                q(deid_sha256),
                "--mode",
                q(mode),
            ]
        ),
    ]
    return {
        "commands": list(lines),
        "executionTimeout": [str(int(timeout_s))],
    }


def ssm_upload_parameters(*, run_id: str, put_url: str) -> dict[str, list[str]]:
    """Second SSM call: PUT the redacted log to a presigned URL, then clear the run dir.

    The URL is minted only after the run, so a long queue never outlives it.
    """
    if not _RUN_ID.fullmatch(run_id):
        raise UsageError("bad run id")
    q = shlex.quote
    script = f"{STATE_DIR}/runs/{run_id}/harness/scripts/ci/aws_ci_host.sh"
    return {
        "commands": [
            "set +x",
            "set -eu",
            f"bash {q(script)} --upload --run-id {q(run_id)} "
            f"--put-url {q(_https('put_url', put_url))}",
        ],
        "executionTimeout": ["600"],
    }


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def presign(
    *,
    method: str,
    host: str,
    key: str,
    region: str,
    expires: int,
    now: str,
    creds: Mapping[str, str],
) -> str:
    """An S3 SigV4 query-authenticated URL (the AWS CLI presigns GET only).

    `creds` is the `aws configure export-credentials --format process` object;
    a session token, when present, is signed into the URL.
    """
    if not 1 <= expires <= MAX_PRESIGN_SECONDS:
        raise UsageError(f"expiry must be 1..{MAX_PRESIGN_SECONDS} s")
    if method not in ("GET", "PUT"):
        raise UsageError("method must be GET or PUT")
    date = now[:8]
    scope = f"{date}/{region}/s3/aws4_request"
    path = "/" + urllib.parse.quote(key.lstrip("/"), safe="/~")
    query = {
        "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
        "X-Amz-Credential": f"{creds['AccessKeyId']}/{scope}",
        "X-Amz-Date": now,
        "X-Amz-Expires": str(expires),
        "X-Amz-SignedHeaders": "host",
    }
    if creds.get("SessionToken"):
        query["X-Amz-Security-Token"] = creds["SessionToken"]
    canonical_query = "&".join(
        f"{urllib.parse.quote(k, safe='~')}={urllib.parse.quote(v, safe='~')}"
        for k, v in sorted(query.items())
    )
    canonical = "\n".join(
        [method, path, canonical_query, f"host:{host}", "", "host", "UNSIGNED-PAYLOAD"]
    )
    to_sign = "\n".join(
        ["AWS4-HMAC-SHA256", now, scope, hashlib.sha256(canonical.encode("utf-8")).hexdigest()]
    )
    k = _sign(("AWS4" + creds["SecretAccessKey"]).encode("utf-8"), date)
    for part in (region, "s3", "aws4_request"):
        k = _sign(k, part)
    signature = hmac.new(k, to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"https://{host}{path}?{canonical_query}&X-Amz-Signature={signature}"


Results = dict[str, tuple[int | None, int]]

_RESULT_LINE = re.compile(r"^gate=([a-z-]+) rc=(\d+) seconds=(\d+)$")


def parse_results(text: str) -> Results:
    """`gate=<name> rc=<n> seconds=<s>` lines; a gate with no line is missing (rc None)."""
    results: Results = {gate: (None, 0) for gate in GATES}
    for line in text.splitlines():
        m = _RESULT_LINE.match(line.strip())
        if m and m.group(1) in results:
            results[m.group(1)] = (int(m.group(2)), int(m.group(3)))
    return results


def _minutes(seconds: int) -> str:
    return f"{max(1, round(seconds / 60))}m"


def status_payload(
    results: Results, log_url: str | None, log_clean: bool, duration_s: int
) -> dict[str, str]:
    """The `aws-ci` commit status for the head sha.

    success: every gate exited 0 and the log passed the secret/PHI scanners.
    failure: a gate failed. error: a gate never reported, or the log was
    withheld because a scanner still matched after redaction.
    """
    if log_url is not None:
        _https("log_url", log_url)
    missing = [g for g, (rc, _) in results.items() if rc is None]
    failed = [g for g, (rc, _) in results.items() if rc not in (None, 0)]
    passed = len(GATES) - len(missing) - len(failed)
    took = _minutes(duration_s)
    if len(missing) == len(GATES):
        # nothing ran, so there is no log to have withheld
        return {
            "state": "error",
            "context": STATUS_CONTEXT,
            "description": f"harness error: no gate ran ({took}); see the aws-ci run output"[
                :MAX_DESCRIPTION
            ],
        }
    if missing:
        state = "error"
        description = f"no result: {', '.join(missing)}; failed: {', '.join(failed) or 'none'}"
    elif failed:
        state = "failure"
        description = f"failed: {', '.join(failed)}"
    else:
        state = "success"
        description = "all gates green"
    description = f"{description} ({passed}/{len(GATES)} pass, {took})"
    if not log_clean:
        state = "error" if state == "success" else state
        description = f"log withheld (scanner hit); {description}"
    payload = {
        "state": state,
        "context": STATUS_CONTEXT,
        "description": description[:MAX_DESCRIPTION],
    }
    if log_url is not None and log_clean:
        payload["target_url"] = log_url
    return payload


# --- log redaction ---------------------------------------------------------------

_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "private_key",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
        "[REDACTED:private_key]",
    ),
    (
        "presigned_query",
        re.compile(r"(X-Amz-(?:Signature|Credential|Security-Token)=)[^&\s\"'<>]+"),
        r"\1[REDACTED]",
    ),
    (
        "aws_key",
        re.compile(r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA|ANPA|ANVA|AIPA)[A-Z0-9]{16}\b"),
        "[REDACTED:aws_key]",
    ),
    (
        "github_token",
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,255}|github_pat_[A-Za-z0-9_]{22,255})\b"),
        "[REDACTED:github_token]",
    ),
    ("bao_token", re.compile(r"\bhv[sbr]\.[A-Za-z0-9_-]{20,}"), "[REDACTED:bao_token]"),
    (
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
        "[REDACTED:jwt]",
    ),
    (
        "authorization",
        re.compile(r"(?i)(authorization:\s*(?:bearer|basic|token)\s+)\S+"),
        r"\1[REDACTED]",
    ),
    (
        "url_userinfo",
        re.compile(r"([a-z][a-z0-9+.-]*://[^/\s:@]+:)[^@\s/]+@"),
        r"\1[REDACTED]@",
    ),
    (
        "assignment",
        re.compile(
            r"(?i)\b([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|ACCESS_KEY|PRIVATE_KEY)[A-Z0-9_]*)"
            r"(\s*[=:]\s*)(?!\[REDACTED)([^\s\"',;]+)"
        ),
        r"\1\2[REDACTED]",
    ),
)

Detector = Callable[[str], Iterable[Any]]


def _identifier_detector() -> Detector:
    """The repository's one definition of identifier-shaped (INT-206).

    Imported lazily: the laptop-side subcommands run under a bare python3. If
    the PR tree cannot provide it, the caller fails closed and the log is
    withheld rather than uploaded half-scrubbed.
    """
    from intake_platform.ci import find_identifiers

    return find_identifiers


def redact(text: str, detector: Detector | None = None) -> tuple[str, dict[str, int]]:
    """Mask secret shapes, then identifier shapes. Returns (text, counts by kind)."""
    counts: dict[str, int] = {}
    for kind, pattern, replacement in _SECRET_PATTERNS:
        text, n = pattern.subn(replacement, text)
        counts[kind] = n
    find = detector if detector is not None else _identifier_detector()
    hits = sorted(find(text), key=lambda h: h.start, reverse=True)
    for hit in hits:
        kind = str(getattr(hit.kind, "value", hit.kind))
        text = f"{text[: hit.start]}[REDACTED:{kind}:{hit.digest}]{text[hit.end :]}"
        counts[kind] = counts.get(kind, 0) + 1
    return text, counts


# --- CLI ---------------------------------------------------------------------------


def _main(argv: Sequence[str]) -> int:
    if not argv:
        sys.stderr.write("usage: aws_ci_lib.py <subcommand> ...\n")
        return 2
    cmd, rest = argv[0], list(argv[1:])
    try:
        if cmd == "parse-args":
            sys.stdout.write(shell_assignments(parse_args(rest)))
        elif cmd == "pr-head":
            sys.stdout.write(pr_head(json.load(sys.stdin)) + "\n")
        elif cmd == "run-id":
            sys.stdout.write(run_id(rest[0], rest[1]) + "\n")
        elif cmd == "ssm-params":
            spec = json.load(sys.stdin)
            sys.stdout.write(json.dumps(ssm_parameters(**spec)))
        elif cmd == "ssm-upload-params":
            sys.stdout.write(
                json.dumps(ssm_upload_parameters(run_id=rest[0], put_url=sys.stdin.read().strip()))
            )
        elif cmd == "presign":
            method, host, key, region, expires, now = rest
            creds = json.load(sys.stdin)
            url = presign(
                method=method,
                host=host,
                key=key,
                region=region,
                expires=int(expires),
                now=now,
                creds=creds,
            )
            sys.stdout.write(url + "\n")
        elif cmd == "status-payload":
            results_path, log_url, log_clean, duration = rest
            with open(results_path, encoding="utf-8") as fh:
                results = parse_results(fh.read())
            payload = status_payload(results, log_url or None, log_clean == "1", int(duration))
            sys.stdout.write(json.dumps(payload) + "\n")
        elif cmd == "redact":
            out, counts = redact(sys.stdin.read())
            sys.stdout.write(out)
            sys.stderr.write(json.dumps(counts, sort_keys=True) + "\n")
        else:
            sys.stderr.write(f"unknown subcommand: {cmd}\n")
            return 2
    except UsageError as exc:
        sys.stderr.write(f"aws-ci: {exc}\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))

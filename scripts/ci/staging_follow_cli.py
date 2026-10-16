"""INT-511 — the command line of the follow-main job's decisions.

scripts/ci/staging_follow_main.sh calls this once per decision, with the
inputs on argv, stdin or (for the presigned URL, a bearer credential) the
environment, and acts on the output and the exit code. The decisions
themselves live in staging_follow_lib.py and are unit-tested there; this file
only moves bytes. tests/ci/test_staging_follow_driver.py runs it end to end.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from staging_follow_lib import (  # noqa: E402
    EXIT_HARNESS,
    EXIT_OK,
    EXIT_REFUSED,
    PRESIGN_S,
    SSM_TIMEOUT_S,
    WAIT_MARGIN_S,
    UsageError,
    conf_assignments,
    decide,
    direction,
    exit_code,
    green,
    host_revision,
    lineage,
    merged,
    parse_args,
    parse_conf,
    parse_host,
    plan,
    request_assignments,
    revision_parity,
    run_id,
    s3_key,
    sha256_file,
    ssm_parameters,
    status_payload,
    synthetic,
    version_parity,
)


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _check(ok: bool, text: str = "") -> tuple[str, int]:
    return text, EXIT_OK if ok else EXIT_REFUSED


def _cli(cmd: str, a: list[str], stdin: Callable[[], str]) -> tuple[str, int]:
    """(stdout, exit code) of one subcommand."""
    if cmd == "args-shell":
        return request_assignments(parse_args(a)), EXIT_OK
    if cmd == "conf-shell":
        return conf_assignments(parse_conf(_read(a[0]))), EXIT_OK
    if cmd == "decide":
        runs, why = decide(a[0], a[1])
        return f"{'run' if runs else 'skip'} {why}\n", EXIT_OK
    if cmd == "merged":
        return _check(merged(a[0]))
    if cmd == "lineage":
        return f"{lineage(stdin())}\n", EXIT_OK
    if cmd == "direction":
        return f"{direction(a[0])}\n", EXIT_OK
    if cmd == "green":
        return " ".join(green(json.loads(stdin()))) + "\n", EXIT_OK
    if cmd == "host-revision":
        sha = host_revision(stdin())
        return _check(sha is not None, f"{sha}\n")
    if cmd == "synthetic":
        return _check(synthetic(stdin()))
    if cmd in ("version-parity", "revision-parity"):
        check = version_parity if cmd == "version-parity" else revision_parity
        ok, detail = check(stdin(), a[0])
        return _check(ok, f"{detail}\n")
    if cmd == "host-state":
        verdict = parse_host(stdin())
        return f"{verdict.state if verdict else 'none'}\n", EXIT_OK
    if cmd == "run-id":
        return f"{run_id(a[0], a[1])}\n", EXIT_OK
    if cmd == "s3-key":
        return f"{s3_key(a[0])}\n", EXIT_OK
    if cmd == "sha256":
        return f"{sha256_file(a[0])}\n", EXIT_OK
    if cmd == "timeouts":
        return f"{SSM_TIMEOUT_S} {WAIT_MARGIN_S} {PRESIGN_S}\n", EXIT_OK
    if cmd == "ssm-params":
        # the presigned URL arrives through the environment: argv is visible to `ps`
        url = os.environ.get("FOLLOW_ARCHIVE_URL", "")
        params = ssm_parameters(
            run_id=a[0], sha=a[1], archive_url=url, archive_sha256=a[2], timeout_s=SSM_TIMEOUT_S
        )
        return json.dumps(params), EXIT_OK
    if cmd == "plan":
        sha, run, event, conf_path, digest, size, host_sha = a
        conf = parse_conf(_read(conf_path))
        text = plan(
            sha=sha,
            run_id=run,
            event=event,
            conf=conf,
            archive_sha256=digest,
            archive_bytes=int(size),
            host_sha=host_sha,
        )
        return f"{text}\n", EXIT_OK
    if cmd == "status-payload":
        sha, context, hostname, host_out, parity_ok, parity_detail = a
        parity = None if parity_ok == "-" else (parity_ok == "1", parity_detail)
        verdict = parse_host(_read(host_out))
        payload = status_payload(
            sha=sha, context=context, hostname=hostname, verdict=verdict, parity=parity
        )
        return json.dumps(payload) + "\n", exit_code(payload)
    raise UsageError(f"unknown subcommand {cmd!r}")


def _main(argv: Sequence[str]) -> int:
    try:
        text, code = _cli(argv[0] if argv else "", list(argv[1:]), sys.stdin.read)
    except (UsageError, IndexError, KeyError, TypeError, ValueError, OSError) as exc:
        sys.stderr.write(f"staging-follow: {exc}\n")
        return EXIT_HARNESS
    sys.stdout.write(text)
    return code


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))

"""INT-426 — CI on AWS: the pure parts of the `aws-ci` runner.

Acceptance lines under test (docs/backlog/issues.yaml, INT-426):
  - `make ci-aws PR=<n>` ships a PR head to the AWS host over S3 + SSM and runs
    the gate set in an isolated compose project with resource limits;
  - the result is a GitHub commit status `aws-ci` with a log link, and no
    secret or PHI reaches the log;
  - no workflow file is edited.

What is pure is tested here: argument parsing, the fork guard, the run id, the
SSM command, the S3 SigV4 presigner, the commit-status payload and the log
redaction. The shell around them (aws, gh, docker) is exercised by the measured
runs recorded in docs/evidence/INT-426.md.

Secret-shaped and identifier-shaped samples are built at runtime, never written
as literals: this file is scanned by gitleaks and the PHI gate like any other,
and a guard that names what it forbids trips the scanner it guards.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "ci"))

import aws_ci_lib as lib  # noqa: E402

SHA = "0123456789abcdef0123456789abcdef01234567"


# --- argument parsing ------------------------------------------------------------


def test_parse_pr() -> None:
    target = lib.parse_args(["--pr", "669"])
    assert (target.kind, target.value, target.post_status) == ("pr", "669", True)


def test_parse_ref_requires_a_full_lowercase_sha() -> None:
    assert lib.parse_args(["--ref", SHA]).value == SHA
    for bad in ("main", SHA[:12], SHA.upper(), SHA + "0", "origin/main"):
        with pytest.raises(lib.UsageError):
            lib.parse_args(["--ref", bad])


@pytest.mark.parametrize("bad", ["0", "-3", "12a", "", "1e3", "007"])
def test_parse_pr_rejects_a_non_number(bad: str) -> None:
    with pytest.raises(lib.UsageError):
        lib.parse_args(["--pr", bad])


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--pr", "1", "--ref", SHA],
        ["--pr"],
        ["--ref"],
        ["--bogus"],
        ["669"],
        ["--pr", "1", "--pr", "2"],
    ],
)
def test_parse_needs_exactly_one_target(argv: list[str]) -> None:
    with pytest.raises(lib.UsageError):
        lib.parse_args(argv)


def test_no_status_is_a_dry_run_of_the_status_only() -> None:
    assert lib.parse_args(["--pr", "5", "--no-status"]).post_status is False


def test_shell_assignments_are_quoted_and_closed() -> None:
    out = lib.shell_assignments(lib.parse_args(["--ref", SHA]))
    env: dict[str, str] = {}
    for line in out.splitlines():
        key, _, value = line.partition("=")
        env[key] = shlex.split(value)[0] if value else ""
    assert env == {
        "AWS_CI_KIND": "ref",
        "AWS_CI_VALUE": SHA,
        "AWS_CI_POST_STATUS": "1",
        "AWS_CI_MODE": "gates",
    }


def test_a_probe_never_posts_the_gate_status() -> None:
    # INT-429's reachability evidence: export both production bundles and look
    # for node-forge. It is a measurement, never a verdict on the commit.
    target = lib.parse_args(["--pr", "730", "--probe", "expo-export"])
    assert (target.mode, target.post_status) == ("expo-export", False)
    with pytest.raises(lib.UsageError):
        lib.parse_args(["--pr", "730", "--probe", "rm-everything"])


# --- the fork guard ----------------------------------------------------------------


def _pr(**over: object) -> dict[str, object]:
    pr: dict[str, object] = {
        "headRefOid": SHA,
        "isCrossRepository": False,
        "state": "OPEN",
        "headRepositoryOwner": {"login": "ArioMoniri"},
    }
    pr.update(over)
    return pr


def test_pr_head_returns_the_sha_of_an_open_same_repo_pr() -> None:
    assert lib.pr_head(_pr()) == SHA


@pytest.mark.parametrize(
    "over",
    [
        {"isCrossRepository": True},
        {"headRepositoryOwner": {"login": "someone-else"}},
        {"state": "CLOSED"},
        {"state": "MERGED"},
        {"headRefOid": "not-a-sha"},
    ],
)
def test_pr_head_refuses_forks_closed_prs_and_junk(over: dict[str, object]) -> None:
    # The runner executes the PR's code on a host that also serves staging, with
    # a privileged dind beside it. Code from a fork never gets there.
    with pytest.raises(lib.UsageError):
        lib.pr_head(_pr(**over))


# --- the run id ----------------------------------------------------------------------


def test_run_id_is_sortable_and_names_the_sha() -> None:
    rid = lib.run_id(SHA, "2026-10-02T20:15:00Z")
    assert rid == "20261002t201500z-0123456789ab"
    assert re.fullmatch(r"[a-z0-9-]+", rid), "compose project names are [a-z0-9_-]"


def test_run_id_refuses_a_bad_sha() -> None:
    with pytest.raises(lib.UsageError):
        lib.run_id("../../etc", "2026-10-02T20:15:00Z")


# --- the SSM command -------------------------------------------------------------------


def test_ssm_parameters_quote_every_value_and_never_trace() -> None:
    url = "https://b.s3.amazonaws.com/k?X-Amz-Signature=abc&x=1;rm -f /"
    params = lib.ssm_parameters(
        run_id="20261002t201500z-0123456789ab",
        sha=SHA,
        harness_url=url,
        harness_sha256="a" * 64,
        bundle_url=url,
        bundle_sha256="b" * 64,
        deid_url="",
        deid_sha256="c" * 64,
        timeout_s=14400,
    )
    assert params["executionTimeout"] == ["14400"]
    script = "\n".join(params["commands"])
    assert "set -x" not in script and "set +x" in script
    assert shlex.quote(url) in script
    assert ";rm -f /" not in script.replace(shlex.quote(url), "")
    # the bootstrap verifies the harness before it runs any of it
    assert script.index("sha256sum") < script.index("aws_ci_host.sh")
    assert "--mode gates" in script


def test_ssm_parameters_carry_only_a_known_mode() -> None:
    spec = {
        "run_id": "r",
        "sha": SHA,
        "harness_url": "https://h",
        "harness_sha256": "a" * 64,
        "bundle_url": "https://b",
        "bundle_sha256": "b" * 64,
        "deid_url": "",
        "deid_sha256": "c" * 64,
        "timeout_s": 60,
    }
    assert "--mode expo-export" in "\n".join(
        lib.ssm_parameters(**spec, mode="expo-export")["commands"]
    )
    with pytest.raises(lib.UsageError):
        lib.ssm_parameters(**spec, mode="bash -c id")


def test_ssm_parameters_refuse_a_non_https_url() -> None:
    with pytest.raises(lib.UsageError):
        lib.ssm_parameters(
            run_id="r",
            sha=SHA,
            harness_url="http://x/y",
            harness_sha256="a" * 64,
            bundle_url="https://x/y",
            bundle_sha256="b" * 64,
            deid_url="",
            deid_sha256="c" * 64,
            timeout_s=60,
        )


def test_ssm_upload_parameters_quote_the_url_and_target_the_run() -> None:
    url = "https://b.s3.amazonaws.com/k?X-Amz-Signature=abc&y=$(id)"
    params = lib.ssm_upload_parameters(run_id="20261002t201500z-0123456789ab", put_url=url)
    line = params["commands"][-1]
    assert shlex.quote(url) in line and "--upload" in line
    assert "/var/lib/intake-ci/runs/20261002t201500z-0123456789ab/harness/" in line
    with pytest.raises(lib.UsageError):
        lib.ssm_upload_parameters(run_id="../x", put_url=url)


# --- the S3 presigner (SigV4 query auth) -------------------------------------------


def test_presign_matches_the_aws_documented_example() -> None:
    # AWS S3 docs, "Authenticating Requests: Using Query Parameters (AWS
    # Signature Version 4)", GET example. The documentation key pair is
    # assembled here so no key-shaped literal sits in the tree.
    access = "AKIA" + "IOSFODNN7" + "EXAMPLE"
    # chunks under ten characters: gitleaks' generic-api-key rule matched the
    # first form of this line (measured on the branch's history, 3 Oct 2026)
    doc_sk = "".join(["wJalrXUtn", "FEMI/K7MD", "ENG/bPxRf", "iCYEXAMPL", "EKEY"])
    url = lib.presign(
        method="GET",
        host="examplebucket.s3.amazonaws.com",
        key="test.txt",
        region="us-east-1",
        expires=86400,
        now="20130524T000000Z",
        creds={"AccessKeyId": access, "SecretAccessKey": doc_sk},
    )
    assert url.endswith(
        "X-Amz-Signature=aeeed9bbccd4d02ee5c0109b86d86835f995330da4c265957d157751f604d404"
    )
    assert url.startswith(
        "https://examplebucket.s3.amazonaws.com/test.txt?X-Amz-Algorithm=AWS4-HMAC-SHA256"
    )


def test_presign_carries_the_session_token_and_caps_expiry() -> None:
    url = lib.presign(
        method="PUT",
        host="b.s3.us-east-1.amazonaws.com",
        key="ci/logs/r/aws-ci.log",
        region="us-east-1",
        expires=3600,
        now="20261002T201500Z",
        creds={"AccessKeyId": "A", "SecretAccessKey": "S", "SessionToken": "T/+="},
    )
    assert "X-Amz-Security-Token=T%2F%2B%3D" in url
    with pytest.raises(lib.UsageError):
        lib.presign(
            method="PUT",
            host="b",
            key="k",
            region="us-east-1",
            expires=604801,
            now="20261002T201500Z",
            creds={"AccessKeyId": "A", "SecretAccessKey": "S"},
        )


# --- results and the status payload ---------------------------------------------------


RESULTS_ALL_GREEN = "".join(f"gate={g} rc=0 seconds=60\n" for g in lib.GATES)


def test_the_gate_set_is_the_acceptance_list_in_order() -> None:
    assert lib.GATES == (
        "edge-plugin",
        "check-py",
        "check-ts",
        "check-integration",
        "safety",
        "security",
    )


def test_parse_results_reads_every_gate_and_marks_the_missing() -> None:
    text = "gate=edge-plugin rc=0 seconds=3\ngate=check-py rc=2 seconds=900\nnoise\n"
    results = lib.parse_results(text)
    assert results["edge-plugin"] == (0, 3)
    assert results["check-py"] == (2, 900)
    assert results["security"] == (None, 0)


def test_status_success_needs_every_gate_green_and_a_clean_log() -> None:
    payload = lib.status_payload(lib.parse_results(RESULTS_ALL_GREEN), "https://log", True, 2460)
    assert payload["state"] == "success"
    assert payload["context"] == "aws-ci"
    assert payload["target_url"] == "https://log"
    assert "6/6" in payload["description"] and "41m" in payload["description"]


def test_status_failure_names_the_failed_gates() -> None:
    text = RESULTS_ALL_GREEN.replace("check-integration rc=0", "check-integration rc=2")
    payload = lib.status_payload(lib.parse_results(text), "https://log", True, 600)
    assert payload["state"] == "failure"
    assert "check-integration" in payload["description"]


def test_status_error_when_a_gate_never_reported() -> None:
    text = "".join(f"gate={g} rc=0 seconds=1\n" for g in lib.GATES[:-1])
    payload = lib.status_payload(lib.parse_results(text), None, True, 60)
    assert payload["state"] == "error"
    assert "security" in payload["description"]
    assert "target_url" not in payload


def test_status_error_and_no_link_when_the_log_was_withheld() -> None:
    payload = lib.status_payload(lib.parse_results(RESULTS_ALL_GREEN), "https://log", False, 60)
    assert payload["state"] == "error"
    assert "withheld" in payload["description"]
    assert "target_url" not in payload


def test_status_says_harness_error_when_no_gate_ran() -> None:
    # No gate ran, so there is no log to withhold: "scanner hit" would be a lie.
    payload = lib.status_payload(lib.parse_results(""), None, False, 60)
    assert payload["state"] == "error"
    assert payload["description"].startswith("harness error: no gate ran")
    assert "withheld" not in payload["description"]


def test_status_description_fits_githubs_limit() -> None:
    text = "".join(f"gate={g} rc=1 seconds=1\n" for g in lib.GATES)
    payload = lib.status_payload(lib.parse_results(text), None, False, 99999)
    assert len(payload["description"]) <= 140


def test_status_refuses_a_non_https_link() -> None:
    with pytest.raises(lib.UsageError):
        lib.status_payload(lib.parse_results(RESULTS_ALL_GREEN), "http://log", True, 1)


# --- log redaction ------------------------------------------------------------------------


def _tckn() -> str:
    """A checksum-valid TCKN, computed so no identifier sits in the tree."""
    d = [1, 2, 3, 4, 5, 6, 7, 8, 9]
    d10 = ((d[0] + d[2] + d[4] + d[6] + d[8]) * 7 - (d[1] + d[3] + d[5] + d[7])) % 10
    d11 = (sum(d) + d10) % 10
    return "".join(map(str, [*d, d10, d11]))


SECRETS = {
    "aws_key": "AK" + "IA" + "Q" * 16,
    "github_token": "gh" + "p_" + "a1B2" * 9,
    "bao_token": "hv" + "s." + "x" * 24,
    "jwt": "ey" + "J" + "a" * 12 + "." + "b" * 12 + "." + "c" * 12,
}


@pytest.mark.parametrize(("kind", "value"), sorted(SECRETS.items()))
def test_redact_masks_secret_shapes(kind: str, value: str) -> None:
    out, counts = lib.redact(f"line one\nfound {value} here\n", detector=lambda _t: ())
    assert value not in out
    assert sum(counts.values()) >= 1


def test_redact_masks_presigned_query_and_assignments_and_userinfo() -> None:
    text = (
        "GET https://b.s3.amazonaws.com/k?X-Amz-Credential=AK%2Fx&X-Amz-Signature=deadbeef&X-Amz-Security-Token=tok\n"
        "OPENBAO_TOKEN=intake-dev-root\n"
        "db: postgresql://intake:hunter2@127.0.0.1:5432/intake\n"
        "Authorization: Bearer abc.def\n"
    )
    out, _ = lib.redact(text, detector=lambda _t: ())
    for leaked in ("deadbeef", "tok\n", "intake-dev-root", "hunter2", "abc.def", "AK%2Fx"):
        assert leaked not in out
    # the shape survives, so the log still reads
    assert "OPENBAO_TOKEN=[REDACTED" in out and "127.0.0.1:5432" in out


def test_redact_masks_a_private_key_block() -> None:
    begin = "-----BEGIN " + "RSA PRIVATE KEY-----"
    end = "-----END " + "RSA PRIVATE KEY-----"
    out, counts = lib.redact(f"a\n{begin}\nMIIabc\nxyz\n{end}\nb\n", detector=lambda _t: ())
    assert "MIIabc" not in out and counts["private_key"] == 1


def test_redact_masks_identifiers_through_the_shared_detector() -> None:
    tckn = _tckn()
    out, counts = lib.redact(f"patient {tckn} seen\n")
    assert tckn not in out
    assert counts.get("TCKN") == 1
    assert "[REDACTED:TCKN:" in out


def test_redact_leaves_an_ordinary_log_alone() -> None:
    text = "=== 412 passed, 3 deselected in 81.2s ===\nmake: *** [check-py] Error 2\n"
    out, counts = lib.redact(text, detector=lambda _t: ())
    assert out == text and not any(counts.values())


def test_redact_cli_reports_counts_on_stderr_never_values(tmp_path: Path) -> None:
    secret = SECRETS["github_token"]
    proc = subprocess.run(
        [sys.executable, str(REPO / "scripts/ci/aws_ci_lib.py"), "redact"],
        input=f"x {secret}\n",
        capture_output=True,
        text=True,
        check=True,
    )
    assert secret not in proc.stdout and secret not in proc.stderr
    assert json.loads(proc.stderr.strip().splitlines()[-1])["github_token"] == 1


# --- the harness: isolation and pins, read statically -----------------------------------


COMPOSE = REPO / "infra/ci/compose.yaml"
DOCKERFILE = REPO / "infra/ci/Dockerfile.runner"


def test_every_service_is_resource_limited_and_publishes_nothing() -> None:
    services = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]
    assert set(services) == {"prep", "dind", "runner"}
    for name, svc in services.items():
        assert "ports" not in svc, f"{name} publishes a host port"
        assert svc.get("cpus") and svc.get("mem_limit") and svc.get("pids_limit"), name
        assert svc.get("cpu_shares", 1024) < 1024, f"{name} would compete with the live stack"
        assert svc.get("oom_score_adj", 0) > 0, (
            f"{name} is not the first thing the OOM killer takes"
        )


def test_the_harness_never_names_the_live_stack() -> None:
    for path in (COMPOSE, REPO / "scripts/ci/aws_ci_host.sh", REPO / "scripts/ci/aws_ci_gates.sh"):
        body = path.read_text(encoding="utf-8")
        assert "intake-staging" not in body, f"{path.name} reaches into the live stack"
        assert "/var/run/docker.sock:" not in body, f"{path.name} mounts the host docker socket"


def test_only_dind_is_privileged_and_its_api_is_loopback_only() -> None:
    services = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]
    assert [n for n, s in services.items() if s.get("privileged")] == ["dind"]
    command = services["dind"]["command"]
    assert "--host=tcp://127.0.0.1:2375" in command
    # bare flags make the dind entrypoint add tcp://0.0.0.0:2375 (measured, run 1)
    assert command[0] == "dockerd"
    tcp = [arg for arg in command if arg.startswith("--host=tcp://")]
    assert tcp == ["--host=tcp://127.0.0.1:2375"], "the API listens on loopback and nowhere else"
    assert services["runner"]["network_mode"] == "service:dind"


def test_every_downloaded_tool_is_version_and_digest_pinned() -> None:
    body = DOCKERFILE.read_text(encoding="utf-8")
    for line in body.splitlines():
        if line.startswith("FROM "):
            assert "@sha256:" in line, line
    pins = dict(re.findall(r"^ARG (\w+_VERSION)=(\S+)$", body, re.M))
    # the versions CI runs (docs/ci/aws-ci.md, "Pinned tools")
    assert pins == {
        "UV_VERSION": "0.12.19",
        "NODE_VERSION": "22.23.2",
        "PNPM_VERSION": "9.15.9",
        "TRIVY_VERSION": "0.70.0",
        "GITLEAKS_VERSION": "8.24.3",
        "OSV_SCANNER_VERSION": "2.5.1",
        "SYFT_VERSION": "1.51.1",
    }
    assert len(re.findall(r"^ARG \w+_SHA256=[0-9a-f]{64}$", body, re.M)) == 6
    assert re.search(r"^USER \d+:\d+$", body, re.M), "the runner must not run as root"


def test_pins_agree_with_the_repo_sources_of_truth() -> None:
    body = DOCKERFILE.read_text(encoding="utf-8")
    pnpm = json.loads((REPO / "package.json").read_text(encoding="utf-8"))["packageManager"]
    assert f"PNPM_VERSION={pnpm.split('@')[1]}" in body
    lib_sh = (REPO / "infra/staging/lib.sh").read_text(encoding="utf-8")
    assert "anchore/syft:v1.51.1@" in lib_sh and "SYFT_VERSION=1.51.1" in body


def test_make_ci_aws_requires_a_target() -> None:
    proc = subprocess.run(
        ["make", "-s", "ci-aws"], cwd=REPO, capture_output=True, text=True, check=False
    )
    assert proc.returncode == 2
    assert "usage: make ci-aws PR=<n> | REF=<40-hex sha>" in proc.stdout


def test_scripts_parse() -> None:
    for name in ("aws_ci.sh", "aws_ci_host.sh", "aws_ci_gates.sh"):
        subprocess.run(["bash", "-n", str(REPO / "scripts/ci" / name)], check=True)

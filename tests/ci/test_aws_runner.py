"""INT-463 — every CI job runs on the AWS self-hosted runner `intake-aws-ci`.

Acceptance lines under test (docs/backlog/issues.yaml, INT-463):
  - a GitHub Actions self-hosted runner runs on the AWS host with the labels
    self-hosted, linux, intake-aws-ci, as a dedicated unprivileged user with no
    read access to /opt/intake, the OpenBao tokens or any staging secret;
    ephemeral and re-registered by a systemd unit, with a disk guard and a
    workspace wipe after every job; Docker for that user is rootless only;
  - every job in .github/workflows runs on [self-hosted, linux, intake-aws-ci];
    no job targets a GitHub-hosted label or the GPU runner, and the pool is
    declared in infra/ci/runners.yaml;
  - on the PR, every job is picked up by intake-aws-ci and none runs on a
    GitHub-hosted runner (measured, docs/evidence/INT-463.md).

The workflows are read as data. The host install (infra/ci/aws-runner) is read
statically: what each unit and script promises is pinned here, and the
isolation it produces on the host was measured as the runner user and is
recorded in the evidence file.
"""

from __future__ import annotations

import configparser
import re
import shlex
import subprocess
from pathlib import Path

import pytest
import yaml
from intake_platform.ci import GITHUB_HOSTED_LABELS, RunsOnKind, load_runner_pools, resolve_runs_on

REPO = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO / ".github" / "workflows"
POOLS_FILE = REPO / "infra" / "ci" / "runners.yaml"
HOST = REPO / "infra" / "ci" / "aws-runner"
OPERATOR = REPO / "scripts" / "ci" / "aws_runner.sh"

POOL_LABEL = "intake-aws-ci"
RUNS_ON = ["self-hosted", "linux", POOL_LABEL]
GPU_LABEL = "intake-gpu"

# GitHub-hosted runner names, beyond the closed set intake_platform.ci knows:
# every hosted image is named for its OS, and the moving aliases end in -latest.
HOSTED_NAME = re.compile(r"^(ubuntu|macos|windows)(-|$)|-latest$", re.I)


def _jobs() -> list[tuple[str, str, object]]:
    jobs: list[tuple[str, str, object]] = []
    for path in sorted(WORKFLOW_DIR.glob("*.y*ml")):
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        for name, job in workflow["jobs"].items():
            jobs.append((path.name, name, job.get("runs-on")))
    return jobs


def _labels(runs_on: object) -> list[str]:
    if isinstance(runs_on, str):
        return [runs_on]
    if isinstance(runs_on, list):
        return [str(label) for label in runs_on]
    if isinstance(runs_on, dict):
        return _labels(runs_on.get("labels"))
    return []


def _conf() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (HOST / "runner.conf").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            out[key] = value.strip('"')
    return out


def _unit(name: str) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(strict=False, interpolation=None, comment_prefixes=("#",))
    parser.optionxform = str  # type: ignore[assignment,method-assign]
    parser.read_string((HOST / name).read_text(encoding="utf-8"))
    return parser


def _unit_lines(name: str) -> list[str]:
    return [
        line.strip()
        for line in (HOST / name).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def _values(name: str, key: str) -> list[str]:
    return [line.split("=", 1)[1] for line in _unit_lines(name) if line.startswith(f"{key}=")]


def _script(name: str) -> str:
    return (HOST / name).read_text(encoding="utf-8")


def _code(text: str) -> str:
    """The script without its comment lines, so prose cannot satisfy a check."""
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


# --- the workflows ---------------------------------------------------------------------


def test_the_workflows_have_jobs() -> None:
    jobs = _jobs()
    assert {path for path, _, _ in jobs} == {"ci.yml", "security.yml"}
    assert len(jobs) == 13, "a new job must be added to this count and to the AWS runner"


@pytest.mark.parametrize(("path", "job", "runs_on"), _jobs())
def test_every_job_runs_on_the_aws_runner(path: str, job: str, runs_on: object) -> None:
    assert _labels(runs_on) == RUNS_ON, f"{path}:{job} runs-on {runs_on!r}, not {RUNS_ON}"


@pytest.mark.parametrize(("path", "job", "runs_on"), _jobs())
def test_no_job_targets_a_github_hosted_label(path: str, job: str, runs_on: object) -> None:
    for label in _labels(runs_on):
        assert label not in GITHUB_HOSTED_LABELS, f"{path}:{job} selects GitHub-hosted {label}"
        assert not HOSTED_NAME.search(label), f"{path}:{job} selects GitHub-hosted {label}"


@pytest.mark.parametrize(("path", "job", "runs_on"), _jobs())
def test_no_job_targets_the_gpu_runner(path: str, job: str, runs_on: object) -> None:
    assert GPU_LABEL not in _labels(runs_on), f"{path}:{job} would queue on the GPU box"


@pytest.mark.parametrize(("path", "job", "runs_on"), _jobs())
def test_every_job_resolves_to_the_declared_pool(path: str, job: str, runs_on: object) -> None:
    resolution = resolve_runs_on(_labels(runs_on), load_runner_pools(POOLS_FILE))
    assert resolution.kind is RunsOnKind.SELF_HOSTED, f"{path}:{job}: {resolution.reason}"
    assert resolution.pool is not None and resolution.pool.label == POOL_LABEL


def test_the_hosted_name_check_catches_hosted_labels() -> None:
    """Near-miss control for the regex: every hosted alias is caught, and the
    pool's own labels are not."""
    for hosted in ("ubuntu-latest", "ubuntu-24.04-arm", "macos-15-xlarge", "windows-2025"):
        assert HOSTED_NAME.search(hosted), hosted
    for ours in RUNS_ON:
        assert not HOSTED_NAME.search(ours), ours


# --- the pool --------------------------------------------------------------------------


def test_the_pool_is_declared_ephemeral_and_off_the_phi_path() -> None:
    pool = load_runner_pools(POOLS_FILE).get(POOL_LABEL)
    assert pool is not None, "intake-aws-ci is not declared in infra/ci/runners.yaml"
    assert pool.ephemeral is True
    assert pool.phi_path is False
    assert "i-0e489e48739f5de98" in pool.location
    assert "Türkiye" in pool.location, "the location must say it is not the TR-DC pool"


def test_the_runner_registers_with_the_pool_label() -> None:
    conf = _conf()
    assert conf["RUNNER_LABELS"] == POOL_LABEL
    assert GPU_LABEL not in conf["RUNNER_LABELS"]


# --- the dedicated user and what it may not read ----------------------------------------


def test_the_runner_user_is_dedicated_and_unprivileged() -> None:
    conf = _conf()
    assert conf["RUNNER_USER"] == "ghrunner"
    install = _code(_script("install.sh"))
    assert "useradd --system" in install
    assert "--shell /usr/sbin/nologin" in install
    assert 'passwd -l "$RUNNER_USER"' in install
    assert 'gpasswd -d "$RUNNER_USER" "$group"' in install
    for group in ("sudo", "docker", "adm"):
        assert group in install.split("for group in", 1)[1].split(";", 1)[0]
    assert "usermod -aG" not in install and "usermod -G" not in install


@pytest.mark.parametrize("path", ["/opt/intake", "/opt/onvizit-releases", "/etc/intake-staging"])
def test_the_staging_paths_are_denied(path: str) -> None:
    assert path in _conf()["SENSITIVE_PATHS"].split()


def test_the_access_guard_denies_then_proves_the_denial_as_the_runner_user() -> None:
    guard = _code(_script("guard.sh"))
    assert 'setfacl -m "u:$RUNNER_USER:---" "$path"' in guard
    assert 'as_runner test -r "$path"' in guard
    assert 'as_runner test -x "$path"' in guard
    assert "/var/run/docker.sock" in guard


def test_the_net_guard_blocks_metadata_staging_networks_and_private_ranges() -> None:
    guard = _code(_script("guard.sh"))
    for cidr in (
        "169.254.0.0/16",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "fd00:ec2::/32",
    ):
        assert cidr in guard, cidr
    assert "root_docker_subnets" in guard
    assert '--uid-owner "$RUNNER_USER"' in guard
    assert "runner_can_connect 169.254.169.254 80" in guard


@pytest.mark.parametrize("unit", ["intake-aws-ci-job.service", "intake-aws-ci-dockerd.service"])
def test_the_sandboxed_units_hide_staging_and_the_root_disk(unit: str) -> None:
    lines = _unit_lines(unit)
    assert "User=ghrunner" in lines
    assert "ProtectSystem=strict" in lines
    assert "ProtectHome=yes" in lines
    assert "TemporaryFileSystem=/opt:ro" in lines
    hidden = " ".join(_values(unit, "InaccessiblePaths"))
    for path in ("/etc/intake-staging", "/etc/intake-aws-ci-runner", "/var/lib/docker"):
        assert f"-{path}" in hidden, f"{unit} does not hide {path}"
    assert all(
        not v.startswith(("+", "!"))
        for k in ("ExecStart", "ExecStartPre", "ExecStopPost")
        for v in _values(unit, k)
    ), f"{unit} runs a command with elevated privileges"


def test_job_code_never_gains_privileges() -> None:
    lines = _unit_lines("intake-aws-ci-job.service")
    assert "NoNewPrivileges=yes" in lines
    assert "-/run/docker.sock" in " ".join(
        _values("intake-aws-ci-job.service", "InaccessiblePaths")
    )


# --- ephemeral, re-registered by systemd, workspace wiped ------------------------------


def test_the_supervisor_unit_loops_the_ephemeral_cycle() -> None:
    unit = _unit("intake-aws-ci-runner.service")
    assert unit["Service"]["ExecStart"] == "/usr/local/lib/intake-aws-ci-runner/bin/cycle.sh"
    assert unit["Service"]["Restart"] == "always"
    assert unit["Install"]["WantedBy"] == "multi-user.target"


def test_registration_is_ephemeral_and_pinned() -> None:
    cycle = _code(_script("cycle.sh"))
    config = cycle.split("./config.sh", 1)[1].split(">/dev/null", 1)[0]
    for flag in ("--unattended", "--ephemeral", "--replace", "--disableupdate"):
        assert flag in config, flag
    assert '--labels "$RUNNER_LABELS"' in config
    assert 'systemctl start --wait "$JOB_UNIT"' in cycle


def test_the_token_never_reaches_a_command_line_or_a_log() -> None:
    cycle = _code(_script("cycle.sh"))
    assert 'ACTIONS_RUNNER_INPUT_TOKEN="$token"' in cycle
    assert "--token" not in cycle
    for name in ("cycle.sh", "guard.sh", "fetch-credential.sh", "install.sh"):
        code = _code(_script(name))
        assert "set +x" in code, name
        assert "set -x" not in code, name
        assert not re.search(r"echo[^\n]*\$\{?(token|value)\b", code), name


def test_every_job_ends_with_a_wipe() -> None:
    cycle = _code(_script("cycle.sh"))
    loop = cycle.split("while :; do", 1)[1]
    assert loop.index('systemctl start --wait "$JOB_UNIT"') < loop.index("cleanup")
    cleanup = cycle.split("cleanup() {", 1)[1].split("\n}", 1)[0]
    for step in (
        "rm -f -v",
        "volume prune -af",
        "network prune -f",
        "builder prune -af",
        "kill_strays",
        "wipe_job_state",
    ):
        assert step in cleanup, step
    wipe = _code(_script("guard.sh")).split("wipe_job_state() {", 1)[1].split("\n}", 1)[0]
    for directory in ("runner", "work", "home"):
        assert directory in wipe
    assert '"${CI_ROOT:?}/tmp"' in wipe


def test_the_workspace_lives_on_the_nvme_volume_only() -> None:
    conf = _conf()
    assert conf["CI_ROOT"].startswith(conf["NVME_MOUNT"] + "/")
    job = _unit_lines("intake-aws-ci-job.service")
    assert f"BindPaths={conf['CI_ROOT']}/work" in job
    # The job's temp directory is a bind of the NVMe tree, never the host's.
    temp = str(Path("/") / "tmp")
    assert f"BindPaths={Path(conf['CI_ROOT']) / 'tmp'}:{temp}" in job


# --- the disk guard --------------------------------------------------------------------


def test_the_disk_guard_has_floors_and_a_watchdog() -> None:
    conf = _conf()
    for key in ("MIN_FREE_CI_GB", "MIN_FREE_ROOT_GB", "WATCH_FLOOR_CI_GB", "WATCH_FLOOR_ROOT_GB"):
        assert int(conf[key]) > 0, key
    assert int(conf["WATCH_FLOOR_CI_GB"]) < int(conf["MIN_FREE_CI_GB"])
    guard = _code(_script("guard.sh"))
    assert 'systemctl kill --kill-whom=all "$JOB_UNIT"' in guard
    timer = _unit("intake-aws-ci-diskwatch.timer")
    assert timer["Timer"]["OnUnitActiveSec"] == "1min"
    install = _code(_script("install.sh"))
    assert '[ "$root_free" -ge 20 ]' in install


def test_the_slice_caps_ci_below_staging() -> None:
    slice_ = _unit("intake-aws-ci.slice")["Slice"]
    assert int(slice_["CPUWeight"]) < 100
    assert int(slice_["IOWeight"]) < 100
    assert slice_["MemoryMax"].endswith("G")
    assert slice_["CPUQuota"].endswith("%")
    for unit in ("intake-aws-ci-job.service", "intake-aws-ci-dockerd.service"):
        assert "Slice=intake-aws-ci.slice" in _unit_lines(unit)
        assert "OOMScoreAdjust=500" in _unit_lines(unit)


# --- rootless Docker only ---------------------------------------------------------------


def test_docker_is_rootless_and_started_only_after_the_guards() -> None:
    unit = _unit("intake-aws-ci-dockerd.service")
    assert unit["Service"]["ExecStart"].startswith("/usr/bin/dockerd-rootless.sh ")
    assert unit["Service"]["User"] == "ghrunner"
    assert not unit.has_section("Install"), (
        "rootless Docker must not start at boot, before the guards"
    )
    cycle = _code(_script("cycle.sh"))
    prepare = cycle.split("prepare() {", 1)[1].split("\n}", 1)[0]
    assert prepare.index("guard_net") < prepare.index("wait_for_docker")


# --- pinned binaries ---------------------------------------------------------------------


def test_the_runner_and_gh_are_pinned_by_sha256() -> None:
    conf = _conf()
    assert re.fullmatch(r"\d+\.\d+\.\d+", conf["RUNNER_VERSION"])
    assert re.fullmatch(r"[0-9a-f]{64}", conf["RUNNER_SHA256"])
    assert re.fullmatch(r"\d+\.\d+\.\d+", conf["GH_VERSION"])
    assert re.fullmatch(r"[0-9a-f]{64}", conf["GH_SHA256"])
    install = _code(_script("install.sh"))
    assert 'echo "$RUNNER_SHA256  $stage/$tarball" | sha256sum -c --quiet' in install
    assert 'echo "$GH_SHA256  $stage/$tarball" | sha256sum -c --quiet' in install


# --- the operator script --------------------------------------------------------------


def test_the_operator_script_never_puts_a_credential_on_a_command_line() -> None:
    code = _code(OPERATOR.read_text(encoding="utf-8"))
    assert (
        'gh api -X POST "repos/$REPO_SLUG/actions/runners/registration-token"'
        " --jq .token | hand_over registration" in code
    )
    assert "--type SecureString" not in code, "the value would have to sit on argv"
    assert '"Type": "SecureString"' in code
    assert 'aws ssm delete-parameter --region "$REGION" --name "$name"' in code
    assert 'ssm_run "$LIB_DIR/bin/fetch-credential.sh $kind $name"' in code


def test_the_scripts_pass_shellcheck() -> None:
    scripts = [str(p) for p in sorted(HOST.glob("*.sh"))] + [str(OPERATOR)]
    try:
        result = subprocess.run(
            ["shellcheck", "-x", "-P", str(HOST), *scripts],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        pytest.fail(
            "shellcheck is not installed; it is on GitHub's ubuntu image and on the AWS host"
        )
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_scripts_parse() -> None:
    for script in [*sorted(HOST.glob("*.sh")), OPERATOR]:
        result = subprocess.run(
            ["bash", "-n", str(script)], capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, f"{script.name}: {result.stderr}"
        assert shlex.split(script.read_text(encoding="utf-8").splitlines()[0]) == [
            "#!/usr/bin/env",
            "bash",
        ]

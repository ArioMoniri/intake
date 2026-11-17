"""INT-467 — a pool of ephemeral intake-aws-ci runners, each isolated as runner 1 is.

Acceptance lines under test (docs/backlog/issues.yaml, INT-467):
  - ephemeral runners intake-aws-ci-1..5 (INT-544 added 4-5) on the AWS host, from templated
    units intake-aws-ci-{runner,job,dockerd,diskwatch}@N, each with its own
    unprivileged user ghrunnerN, a subordinate id range that overlaps no other,
    its own CI root, rootless Docker daemon and owner-match egress chain, all
    under the one intake-aws-ci.slice ceiling; the registrar mints a token
    before every registration of every runner;
  - each runner's job runs in its rootless daemon's network namespace as its
    own uid; the port driver is none, so a published port never reaches the
    host loopback and two concurrent check-integration jobs do not collide; a
    runner's post-job wipe touches only its own daemon, processes and tree;
  - each runner's isolation is measured as INT-463's was, plus every other
    runner's tree, socket and published port (docs/evidence/INT-467.md).

tests/ci/test_aws_runner.py keeps pinning the INT-463 contract on the unit
templates. This file pins what the pool adds. Where a shell function decides
something (an instance's identity, the peer paths it is denied, the sandbox the
probe copies), the function is run, not read.
"""

from __future__ import annotations

import configparser
import os
import re
import shlex
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
HOST = REPO / "infra" / "ci" / "aws-runner"
OPERATOR = REPO / "scripts" / "ci" / "aws_runner.sh"

INSTANCES = ["1", "2", "3", "4", "5"]
FIELDS = (
    "INSTANCE",
    "RUNNER_USER",
    "RUNNER_NAME",
    "CI_ROOT",
    "DOCKER_RUN_DIR",
    "NET_CHAIN",
    "NETNS",
    "SUBID_START",
    "JOB_UNIT",
    "DOCKERD_UNIT",
)
TEMPLATES = (
    "intake-aws-ci-runner@.service",
    "intake-aws-ci-job@.service",
    "intake-aws-ci-dockerd@.service",
    "intake-aws-ci-diskwatch@.service",
    "intake-aws-ci-diskwatch@.timer",
)
# The probe's transient unit takes every [Service] line of the job unit except these.
PROBE_DROPS = {"ExecStart", "Type", "Restart", "WorkingDirectory", "TimeoutStopSec"}
# ubuntu's subordinate range, read from /etc/subuid on the host on 3 Oct 2026.
UBUNTU_SUBIDS = (100000, 65536)


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


def _service_lines(name: str) -> list[str]:
    lines: list[str] = []
    section = ""
    for raw in (HOST / name).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            section = line
            continue
        if section == "[Service]":
            lines.append(line)
    return lines


def _values(name: str, key: str, instance: str = "%i") -> list[str]:
    return [
        line.split("=", 1)[1].replace("%i", instance)
        for line in _service_lines(name)
        if line.startswith(f"{key}=")
    ]


def _code(name: str) -> str:
    text = (OPERATOR if name == "aws_runner.sh" else HOST / name).read_text(encoding="utf-8")
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def _body(name: str, function: str) -> str:
    return _code(name).split(f"{function}() {{", 1)[1].split("\n}", 1)[0]


def _bash(script: str, conf: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "INTAKE_AWS_CI_CONF": str(conf or HOST / "runner.conf")}
    return subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, check=False, env=env, cwd=HOST
    )


def _instance(n: str) -> dict[str, str]:
    show = f'for v in {" ".join(FIELDS)}; do printf "%s=%s\\n" "$v" "${{!v}}"; done'
    result = _bash(f". ./guard.sh && instance_env {shlex.quote(n)} && {show}")
    assert result.returncode == 0, result.stdout + result.stderr
    return dict(line.split("=", 1) for line in result.stdout.splitlines())


# --- the pool and each instance's identity --------------------------------------------


def test_the_pool_is_five_instances() -> None:
    assert _conf()["POOL_INSTANCES"].split() == INSTANCES


@pytest.mark.parametrize("n", INSTANCES)
def test_each_instance_derives_its_own_identity(n: str) -> None:
    env = _instance(n)
    assert env == {
        "INSTANCE": n,
        "RUNNER_USER": f"ghrunner{n}",
        "RUNNER_NAME": f"intake-aws-ci-{n}",
        "CI_ROOT": f"/opt/dlami/nvme/intake-aws-ci-{n}",
        "DOCKER_RUN_DIR": f"/run/intake-aws-ci-{n}",
        "NET_CHAIN": f"INTAKE-AWS-CI-OUT-{n}",
        "NETNS": f"intake-aws-ci-{n}",
        "SUBID_START": str(165536 + (int(n) - 1) * 65536),
        "JOB_UNIT": f"intake-aws-ci-job@{n}.service",
        "DOCKERD_UNIT": f"intake-aws-ci-dockerd@{n}.service",
    }
    assert len(env["NET_CHAIN"]) <= 28, "iptables chain names are at most 28 characters"


@pytest.mark.parametrize("bad", ["", "0", "6", "01", "a", "1 2", "1;true", "../1"])
def test_an_unknown_instance_is_refused(bad: str) -> None:
    """Near-miss controls: a neighbour of a valid number, a list, an injection."""
    result = _bash(f". ./guard.sh && instance_env {shlex.quote(bad)}")
    assert result.returncode != 0, bad
    assert "FAIL" in result.stdout + result.stderr


def test_the_subordinate_ranges_never_overlap() -> None:
    count = int(_conf()["SUBID_COUNT"])
    ranges = [(int(_instance(n)["SUBID_START"]), count) for n in INSTANCES] + [UBUNTU_SUBIDS]
    for i, (a, a_len) in enumerate(ranges):
        for b, b_len in ranges[i + 1 :]:
            assert a + a_len <= b or b + b_len <= a, (a, b)
    # Instance 1 takes the range the INT-463 single runner held, which is why
    # install.sh removes that user before it creates ghrunner1.
    assert ranges[0][0] == int(_conf()["SUBID_BASE"]) == 165536


@pytest.mark.parametrize("n", INSTANCES)
def test_the_units_and_the_scripts_agree_on_every_path(n: str) -> None:
    env = _instance(n)
    job = "intake-aws-ci-job@.service"
    dockerd = "intake-aws-ci-dockerd@.service"
    assert _values(job, "User", n) == [env["RUNNER_USER"]]
    assert f"HOME={env['CI_ROOT']}/home" in _values(job, "Environment", n)
    assert f"DOCKER_HOST=unix://{env['DOCKER_RUN_DIR']}/docker.sock" in _values(
        job, "Environment", n
    )
    assert _values(job, "NetworkNamespacePath", n) == [f"/run/netns/{env['NETNS']}"]
    assert _values(dockerd, "User", n) == [env["RUNNER_USER"]]
    assert f"XDG_RUNTIME_DIR={env['DOCKER_RUN_DIR']}" in _values(dockerd, "Environment", n)
    assert _values(dockerd, "RuntimeDirectory", n) == [Path(env["DOCKER_RUN_DIR"]).name]
    assert f"--data-root={env['CI_ROOT']}/docker" in _values(dockerd, "ExecStart", n)[0]


def test_the_units_are_templates_and_the_single_runner_units_are_gone() -> None:
    units = {p.name for p in HOST.glob("intake-aws-ci*") if p.suffix in {".service", ".timer"}}
    assert units == set(TEMPLATES)
    assert (HOST / "intake-aws-ci.slice").exists(), "the one ceiling every instance shares"


@pytest.mark.parametrize("unit", TEMPLATES)
def test_every_per_runner_path_in_a_unit_carries_the_instance(unit: str) -> None:
    text = "\n".join(_service_lines(unit) + _unit(unit)["Unit"].get("After", "").split())
    for prefix in (
        "/opt/dlami/nvme/intake-aws-ci",
        "/run/intake-aws-ci",
        "/run/netns/intake-aws-ci",
    ):
        for match in re.finditer(re.escape(prefix) + r"(\S*)", text):
            assert match.group(1).startswith("-%i"), f"{unit}: {match.group(0)} is shared"
    for line in _service_lines(unit):
        if line.startswith(("User=", "Group=")):
            assert line.endswith("ghrunner%i"), line


# --- the network namespace --------------------------------------------------------------


def test_the_job_runs_in_its_runners_network_namespace() -> None:
    job = _unit("intake-aws-ci-job@.service")["Service"]
    assert job["NetworkNamespacePath"] == "/run/netns/intake-aws-ci-%i"
    assert "/usr/local/lib/intake-aws-ci-runner/resolv.conf:/etc/resolv.conf" in _values(
        "intake-aws-ci-job@.service", "BindReadOnlyPaths"
    )
    resolv = [
        line
        for line in (HOST / "resolv.conf").read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    ]
    assert resolv == ["nameserver 10.0.2.3"], "slirp4netns's forwarder, inside the namespace"
    # The daemon stays in the host namespace: its uplink (slirp4netns) and its
    # pulls are host sockets of the runner's uid, so the owner-match chain sees them.
    dockerd = _unit("intake-aws-ci-dockerd@.service")["Service"]
    assert "NetworkNamespacePath" not in dockerd
    assert "PrivateNetwork" not in dockerd


def test_a_published_port_never_reaches_the_host() -> None:
    env = _values("intake-aws-ci-dockerd@.service", "Environment")
    for setting in (
        "DOCKERD_ROOTLESS_ROOTLESSKIT_NET=slirp4netns",
        "DOCKERD_ROOTLESS_ROOTLESSKIT_DETACH_NETNS=true",
        "DOCKERD_ROOTLESS_ROOTLESSKIT_PORT_DRIVER=none",
        "DOCKERD_ROOTLESS_ROOTLESSKIT_DISABLE_HOST_LOOPBACK=true",
    ):
        assert setting in env, setting


def test_the_namespace_is_proved_before_the_runner_registers() -> None:
    prepare = _body("cycle.sh", "prepare")
    assert prepare.index("wait_for_docker") < prepare.index("guard_netns")
    assert prepare.index("guard_netns") < prepare.index("registration_token")
    netns = _body("guard.sh", "guard_netns")
    assert "attach_netns" in netns
    for flag in ("--port-driver=none", "--disable-host-loopback", "--detach-netns"):
        assert flag in netns, flag
    assert "netns_can_connect 169.254.169.254 80" in netns
    assert "netns_can_connect 10.0.2.2" in netns, "the host loopback through slirp4netns"
    assert "host_listeners_of_runner" in netns


def test_only_the_daemons_detached_namespace_is_attached() -> None:
    attach = _body("guard.sh", "attach_netns")
    assert '"$DOCKER_RUN_DIR/dockerd-rootless/child_pid"' in attach
    assert '"$(readlink /proc/1/ns/net)"' in attach, "never the host's own namespace"
    assert "root$DOCKER_RUN_DIR/dockerd-rootless/netns" in attach
    assert '!= "$RUNNER_USER"' in attach, "the child must belong to this runner's user"
    assert attach.index('ip netns delete "$NETNS"') < attach.index('ip netns attach "$NETNS"')


# --- peers ------------------------------------------------------------------------------


def test_each_runner_is_denied_every_other_runners_tree(tmp_path: Path) -> None:
    peer_line = next(
        line
        for line in (HOST / "runner.conf").read_text(encoding="utf-8").splitlines()
        if line.startswith("PEER_PATHS=")
    )
    for directory in ("staging", "ci", "ci-1", "ci-2", "ci-3", "run-1", "run-2", "run-3"):
        (tmp_path / directory).mkdir()
    conf = tmp_path / "runner.conf"
    conf.write_text(
        (HOST / "runner.conf").read_text(encoding="utf-8")
        + f"\nCI_ROOT_BASE={tmp_path}/ci\nDOCKER_RUN_BASE={tmp_path}/run\n"
        + f'SENSITIVE_PATHS="{tmp_path}/staging"\n{peer_line}\n',
        encoding="utf-8",
    )
    result = _bash(". ./guard.sh && instance_env 2 && sensitive_paths", conf)
    assert result.returncode == 0, result.stderr
    names = {Path(p).name for p in result.stdout.split()}
    assert names == {"staging", "ci", "ci-1", "ci-3", "run-1", "run-3"}


def test_the_peer_paths_cover_every_runner_tree_and_socket_dir() -> None:
    peers = _conf()["PEER_PATHS"].split()
    for path in ("$CI_ROOT_BASE", "$CI_ROOT_BASE-*", "$DOCKER_RUN_BASE", "$DOCKER_RUN_BASE-*"):
        assert path in peers, path
    access = _body("guard.sh", "guard_access")
    assert "sensitive_paths" in access


def test_the_wipe_touches_only_its_own_runner() -> None:
    cleanup = _body("cycle.sh", "cleanup")
    for line in cleanup.splitlines():
        if re.search(r"\bdocker\b", line):
            assert "docker_as_runner" in line or "docker_up" in line, line
    assert 'pgrep -u "$RUNNER_USER"' in _body("cycle.sh", "kill_strays")
    assert '*"$DOCKERD_UNIT"*' in _body("cycle.sh", "kill_strays")
    guard = _code("guard.sh")
    assert 'DOCKER_HOST="unix://$DOCKER_RUN_DIR/docker.sock"' in _body(
        "guard.sh", "docker_as_runner"
    )
    assert '"${CI_ROOT:?}/$d"' in _body("guard.sh", "wipe_job_state")
    assert "pkill" not in guard and "pkill" not in _code("cycle.sh")


def test_each_runner_has_its_own_egress_chain() -> None:
    reset = _body("guard.sh", "reset_chain")
    assert '--uid-owner "$RUNNER_USER" -j "$NET_CHAIN"' in reset
    assert "NET_CHAIN=INTAKE" not in _code("guard.sh"), "the chain comes from instance_env"


# --- the supervisor, the hook and the watchdog -----------------------------------------


def test_every_unit_passes_its_instance_to_the_scripts() -> None:
    assert _values("intake-aws-ci-runner@.service", "ExecStart") == [
        "/usr/local/lib/intake-aws-ci-runner/bin/cycle.sh %i"
    ]
    assert _values("intake-aws-ci-diskwatch@.service", "ExecStart") == [
        "/usr/local/lib/intake-aws-ci-runner/bin/guard.sh %i watch"
    ]
    assert 'instance_env "${1:-}" || exit 2' in _code("cycle.sh")
    started = _code("job-started.sh")
    assert 'instance_env "${me#"$RUNNER_USER_PREFIX"}"' in started
    assert "$NETNS" in started


# --- install: the migration and the drain ------------------------------------------------


def test_install_removes_the_single_runner_layout_before_instance_one() -> None:
    install = _code("install.sh")
    legacy = _body("install.sh", "remove_legacy")
    assert install.index("remove_legacy\n") < install.index("useradd --system")
    for step in (
        '--uid-owner "$uid" -j "$LEGACY_NET_CHAIN"',
        '-X "$LEGACY_NET_CHAIN"',
        'setfacl -x "u:$LEGACY_RUNNER_USER"',
        'userdel "$LEGACY_RUNNER_USER"',
        "/etc/subuid /etc/subgid",
        'rm -rf --one-file-system "${LEGACY_CI_ROOT:?}"',
    ):
        assert step in legacy, step
    conf = _conf()
    assert conf["LEGACY_RUNNER_USER"] == "ghrunner"
    assert conf["LEGACY_CI_ROOT"] == conf["CI_ROOT_BASE"]


def test_install_stops_each_supervisor_before_replacing_its_scripts() -> None:
    """bash reads a running script by offset; a script replaced under a live
    supervisor runs a mix of two versions."""
    install = _code("install.sh")
    assert install.index("drain ") < install.index('install -m 0755 -o root -g root "$SRC/$script"')
    drain = _body("install.sh", "drain")
    assert 'pgrep -u "$user" -f Runner.Worker' in drain
    assert "DRAIN_TIMEOUT_S" in drain


# --- the isolation probe ------------------------------------------------------------------


@pytest.mark.parametrize("n", INSTANCES)
def test_the_probe_runs_in_the_job_units_own_sandbox(n: str) -> None:
    unit = HOST / "intake-aws-ci-job@.service"
    result = _bash(f"export PROBE_JOB_UNIT={shlex.quote(str(unit))}; . ./probe.sh && job_props {n}")
    assert result.returncode == 0, result.stderr
    expected = [
        line.replace("%i", n)
        for line in _service_lines("intake-aws-ci-job@.service")
        if line.split("=", 1)[0] not in PROBE_DROPS
    ]
    assert result.stdout.splitlines() == expected
    for line in (f"User=ghrunner{n}", f"NetworkNamespacePath=/run/netns/intake-aws-ci-{n}"):
        assert line in expected


def test_the_probe_checks_every_isolation_property() -> None:
    inside = _body("probe.sh", "probe_inside")
    for check in (
        "169.254.169.254",
        "/var/run/docker.sock",
        "STAGING_TCP",
        "SECRET_FILES",
        "/usr/local",
        "/var/log",
        "10.0.2.2",
        '"$CI_ROOT_BASE-$m"',
        '"$DOCKER_RUN_BASE-$m/docker.sock"',
        "$PROBE_PORT",
        "api.github.com",
        "rootless",
        "CapEff",
        "/:/host",
    ):
        assert check in inside, check
    assert re.fullmatch(r"\S+@sha256:[0-9a-f]{64}", _conf()["PROBE_IMAGE"])


def test_the_operator_probes_and_reports_every_runner() -> None:
    operator = _code("aws_runner.sh")
    assert "probe) cmd_probe" in operator
    assert "^[1-9]$" in _body("aws_runner.sh", "instances_arg")
    status = _body("aws_runner.sh", "cmd_status")
    assert "$POOL_INSTANCES" in status
    assert "intake-aws-ci-runner@" in status

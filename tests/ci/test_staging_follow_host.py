"""INT-511 — the host half of the follow-main job, run against a fake host.

scripts/ci/staging_follow_host.sh is what SSM runs as root on the synthetic
host, from the release archive it just verified. Here it runs as the test user
against a temporary tree laid out like the host:

  <root>/opt/onvizit-releases/<sha>-<epoch>/   one directory per release
  <root>/opt/intake -> the release that runs   (a symlink, checklist §1)
  <root>/var/lib/intake-staging-follow/        the follower's own state

docker and flock are shims on PATH: docker answers the release gate with a
chosen exit code and records every image removal. init.sh, deploy.sh and
smoke.sh inside the fake release record their order and exit as told. Nothing
here needs root, docker or AWS.

Each refusal sits next to its near miss: a frozen gate refuses and an allowed
one deploys; a red smoke is not recorded and a green one is.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
HOST_SCRIPT = REPO / "scripts" / "ci" / "staging_follow_host.sh"

SHA = "0123456789abcdef0123456789abcdef01234567"
OLD = "fedcba9876543210fedcba9876543210fedcba98"
RUN_ID = "20261016t021700z-0123456789ab"
FREEZE_LINE = "deploys are frozen or the freeze cannot be read"

DOCKER_SHIM = """#!/usr/bin/env bash
# INT-511 test shim: the host's docker, as the follower calls it
case "$1" in
  ps) if [ -n "${FAKE_API_IDS:-}" ]; then printf '%s\\n' $FAKE_API_IDS; fi ;;
  exec)
    printf '%s\\n' "$*" >>"$FAKE_MARKS/docker"
    printf '%s\\n' "${FAKE_GATE_LINE:-release gate: allowed}"
    exit "${FAKE_GATE_RC:-0}"
    ;;
  image) printf '%s\\n' "$*" >>"$FAKE_MARKS/images" ;;
  *) exit 64 ;;
esac
"""

FLOCK_SHIM = """#!/usr/bin/env bash
exit "${FAKE_FLOCK_RC:-0}"
"""

STEP = """#!/usr/bin/env bash
# INT-511 test fake of infra/staging/{name}
printf '%s %s\\n' {name} "$(cat "$(dirname "$0")/REVISION")" >>"$FAKE_MARKS/order"
{body}
exit "${{FAKE_{upper}_RC:-0}}"
"""


@dataclass
class Host:
    releases: Path
    current: Path
    state: Path
    marks: Path
    bin: Path

    def env(self, **fake: str) -> dict[str, str]:
        env = {
            "PATH": f"{self.bin}:{os.environ.get('PATH', '/usr/bin:/bin')}",
            "HOME": str(self.marks),
            "INTAKE_FOLLOW_RELEASES": str(self.releases),
            "INTAKE_FOLLOW_CURRENT": str(self.current),
            "INTAKE_FOLLOW_STATE": str(self.state),
            "FAKE_MARKS": str(self.marks),
            "FAKE_API_IDS": "abc123",
        }
        env.update(fake)
        return env

    def order(self) -> list[str]:
        path = self.marks / "order"
        return path.read_text(encoding="utf-8").splitlines() if path.exists() else []

    def running(self) -> str:
        return (self.current / "infra" / "staging" / "REVISION").read_text(encoding="utf-8").strip()


def _release_tree(base: Path, sha: str) -> None:
    staging = base / "infra" / "staging"
    staging.mkdir(parents=True)
    (staging / "REVISION").write_text(sha + "\n", encoding="utf-8")
    smoke_body = (
        "echo '[intake-staging] PASS https://h/healthz -> 200' >&2\n"
        'if [ "${FAKE_SMOKE_RC:-0}" != 0 ]; then echo "[intake-staging] FAIL /version" >&2; fi'
    )
    deploy_body = 'if [ -n "${FAKE_DEPLOY_SAYS:-}" ]; then echo "$FAKE_DEPLOY_SAYS" >&2; fi'
    for name, body in (("init.sh", ""), ("deploy.sh", deploy_body), ("smoke.sh", smoke_body)):
        upper = name.split(".")[0].upper()
        (staging / name).write_text(
            STEP.format(name=name, body=body, upper=upper), encoding="utf-8"
        )


@pytest.fixture
def host(tmp_path: Path) -> Host:
    releases = tmp_path / "opt" / "onvizit-releases"
    old = releases / f"{OLD}-1000"
    _release_tree(old, OLD)
    current = tmp_path / "opt" / "intake"
    current.symlink_to(old)
    state = tmp_path / "var" / "lib" / "intake-staging-follow"
    marks = tmp_path / "marks"
    marks.mkdir()
    shims = tmp_path / "bin"
    shims.mkdir()
    for name, body in (("docker", DOCKER_SHIM), ("flock", FLOCK_SHIM)):
        (shims / name).write_text(body, encoding="utf-8")
        (shims / name).chmod(0o755)
    return Host(releases=releases, current=current, state=state, marks=marks, bin=shims)


def _incoming(host: Host, revision: str = SHA) -> Path:
    incoming = host.releases / f".incoming.{RUN_ID}"
    _release_tree(incoming / "intake", revision)
    return incoming


def _run(
    host: Host, *, incoming: Path | None = None, sha: str = SHA, **fake: str
) -> subprocess.CompletedProcess[str]:
    incoming = incoming if incoming is not None else _incoming(host)
    argv = ["bash", str(HOST_SCRIPT), "--run-id", RUN_ID, "--sha", sha, "--incoming", str(incoming)]
    return subprocess.run(argv, capture_output=True, text=True, env=host.env(**fake), check=False)


def _verdict(result: subprocess.CompletedProcess[str]) -> str:
    lines = [line for line in result.stdout.splitlines() if line.startswith("follow=verdict ")]
    assert lines, result.stdout + result.stderr
    return lines[-1]


# --- the green path -----------------------------------------------------------------------


def test_a_green_run_leaves_the_host_on_the_sha(host: Host) -> None:
    result = _run(host)
    assert result.returncode == 0, result.stdout + result.stderr
    assert _verdict(result) == "follow=verdict state=green reason=smoke_green"
    assert host.running() == SHA, "the host revision equals the sha after a run"
    assert (host.state / "revision").read_text(encoding="utf-8").strip() == SHA
    target = Path(os.readlink(host.current))
    assert target.parent == host.releases and target.name.startswith(SHA + "-")
    assert host.order() == [f"init.sh {SHA}", f"deploy.sh {SHA}", f"smoke.sh {SHA}"]
    assert f"follow=revision sha={SHA}" in result.stdout
    assert "smoke: [intake-staging] PASS" in result.stdout
    assert not (host.releases / f".incoming.{RUN_ID}").exists()


def test_the_freeze_is_read_from_the_running_api_before_anything_changes(host: Host) -> None:
    result = _run(host)
    calls = (host.marks / "docker").read_text(encoding="utf-8").splitlines()
    # no -i: the gate reads nothing on stdin
    assert calls == ["exec abc123 python -m intake_api.admin.release_gate"]
    assert "gate: release gate: allowed" in result.stdout


def test_a_second_run_of_the_same_sha_is_a_new_release_and_stays_green(host: Host) -> None:
    assert _run(host).returncode == 0
    assert _run(host).returncode == 0
    assert host.running() == SHA


# --- refusals: nothing changes ----------------------------------------------------------------


def _unchanged(host: Host) -> None:
    assert host.running() == OLD, "the previous release still runs"
    assert not (host.state / "revision").exists()
    assert host.order() == [], "init, deploy and smoke never ran"
    assert not (host.releases / f".incoming.{RUN_ID}").exists(), "the incoming tree is removed"


def test_a_frozen_state_is_refused_before_the_host_changes(host: Host) -> None:
    result = _run(
        host, FAKE_GATE_RC="3", FAKE_GATE_LINE="release gate: refused deploy_freeze_engaged"
    )
    assert result.returncode == 3
    assert _verdict(result) == "follow=verdict state=refused reason=frozen"
    assert "gate: release gate: refused deploy_freeze_engaged" in result.stdout
    _unchanged(host)


@pytest.mark.parametrize("rc", ["1", "2", "125", "137"])
def test_a_gate_that_could_not_run_refuses_too(host: Host, rc: str) -> None:
    result = _run(host, FAKE_GATE_RC=rc)
    assert result.returncode == 3
    assert _verdict(result) == "follow=verdict state=refused reason=gate_unavailable"
    _unchanged(host)


@pytest.mark.parametrize("ids", ["", "abc123 def456"])
def test_the_freeze_needs_exactly_one_running_api(host: Host, ids: str) -> None:
    result = _run(host, FAKE_API_IDS=ids)
    assert result.returncode == 3
    assert _verdict(result) == "follow=verdict state=refused reason=gate_unavailable"
    _unchanged(host)


@pytest.mark.parametrize("revision", [OLD, "$Format:%H$", SHA[:12]])
def test_an_archive_whose_revision_is_not_the_sha_is_refused(host: Host, revision: str) -> None:
    result = _run(host, incoming=_incoming(host, revision))
    assert result.returncode == 3
    assert _verdict(result) == "follow=verdict state=refused reason=revision_mismatch"
    assert not (host.marks / "docker").exists(), "parity is checked before the freeze is read"
    _unchanged(host)


def test_a_held_lock_refuses_a_concurrent_run(host: Host) -> None:
    result = _run(host, FAKE_FLOCK_RC="1")
    assert result.returncode == 3
    assert _verdict(result) == "follow=verdict state=refused reason=lock_busy"
    _unchanged(host)


def test_a_current_tree_that_is_not_a_symlink_is_refused(host: Host) -> None:
    host.current.unlink()
    (host.current / "infra" / "staging").mkdir(parents=True)
    (host.current / "infra" / "staging" / "REVISION").write_text(OLD + "\n", encoding="utf-8")
    result = _run(host)
    assert result.returncode == 3
    assert _verdict(result) == "follow=verdict state=refused reason=layout"
    _unchanged(host)


def test_an_incoming_tree_outside_the_releases_dir_is_refused(host: Host, tmp_path: Path) -> None:
    stray = tmp_path / "elsewhere" / f".incoming.{RUN_ID}"
    _release_tree(stray / "intake", SHA)
    result = _run(host, incoming=stray)
    assert result.returncode == 2
    assert stray.exists(), "a path it was not given authority over is left alone"
    assert host.running() == OLD


@pytest.mark.parametrize(
    "argv",
    [
        ["--run-id", "Bad Id", "--sha", SHA],
        ["--run-id", RUN_ID, "--sha", SHA[:12]],
        ["--run-id", RUN_ID, "--sha", SHA, "--bogus", "x"],
    ],
)
def test_bad_arguments_stop_the_script(host: Host, argv: list[str]) -> None:
    incoming = _incoming(host)
    full = ["bash", str(HOST_SCRIPT), *argv, "--incoming", str(incoming)]
    result = subprocess.run(full, capture_output=True, text=True, env=host.env(), check=False)
    assert result.returncode == 2
    assert host.running() == OLD


# --- red: the deploy or the smoke failed ---------------------------------------------------------


def test_a_red_smoke_is_not_recorded_as_the_host_revision(host: Host) -> None:
    result = _run(host, FAKE_SMOKE_RC="1")
    assert result.returncode == 1
    assert _verdict(result) == "follow=verdict state=red reason=smoke_red"
    assert "smoke: [intake-staging] FAIL /version" in result.stdout
    assert not (host.state / "revision").exists(), "a red smoke never becomes the followed revision"
    assert host.running() == SHA, "deploy.sh restarted onto it, so the pointer names what runs"


def test_a_failed_deploy_points_back_at_the_previous_release(host: Host) -> None:
    result = _run(
        host, FAKE_DEPLOY_RC="1", FAKE_DEPLOY_SAYS="[intake-staging] ERROR: syft wrote no SBOM"
    )
    assert result.returncode == 1
    assert _verdict(result) == "follow=verdict state=red reason=deploy_failed"
    assert "[intake-staging] ERROR: syft wrote no SBOM" in result.stdout
    assert host.running() == OLD
    assert host.order() == [f"init.sh {SHA}", f"deploy.sh {SHA}"], "no smoke after a failed deploy"
    assert not (host.state / "revision").exists()


def test_deploy_s_own_release_gate_refusal_is_a_freeze(host: Host) -> None:
    says = f"[intake-staging] ERROR: {FREEZE_LINE}: nothing was restarted"
    result = _run(host, FAKE_DEPLOY_RC="1", FAKE_DEPLOY_SAYS=says)
    assert result.returncode == 3
    assert _verdict(result) == "follow=verdict state=refused reason=frozen"
    assert host.running() == OLD


def test_a_failed_init_points_back_and_deploys_nothing(host: Host) -> None:
    result = _run(host, FAKE_INIT_RC="1")
    assert result.returncode == 1
    assert _verdict(result) == "follow=verdict state=red reason=init_failed"
    assert host.order() == [f"init.sh {SHA}"]
    assert host.running() == OLD


# --- pruning ------------------------------------------------------------------------------------


def test_a_green_run_keeps_the_newest_releases_and_the_previous_one(host: Host) -> None:
    shas = [f"{i:x}" * 40 for i in range(1, 7)]
    for epoch, sha in enumerate(shas, start=2000):
        _release_tree(host.releases / f"{sha}-{epoch}", sha)
    (host.releases / "hand-made").mkdir()
    previous = Path(os.readlink(host.current))
    assert _run(host).returncode == 0
    left = sorted(p.name for p in host.releases.iterdir())
    kept = {f"{shas[5]}-2005", f"{shas[4]}-2004", previous.name, "hand-made"}
    assert set(left) - {n for n in left if n.startswith(SHA + "-")} == kept
    removed = (host.marks / "images").read_text(encoding="utf-8")
    for sha in shas[:4]:
        for image in ("api", "admin-web", "keycloak"):
            assert f"intake-staging/{image}:{sha}" in removed
    for sha in (shas[4], shas[5], OLD, SHA):
        assert sha not in removed, "a kept release keeps its images"
    assert "-f" not in removed.split(), "an image a container still uses is never forced out"


def test_a_red_run_prunes_nothing(host: Host) -> None:
    sha = "1" * 40
    _release_tree(host.releases / f"{sha}-900", sha)
    assert _run(host, FAKE_SMOKE_RC="1").returncode == 1
    assert (host.releases / f"{sha}-900").exists()


# --- what it never touches -----------------------------------------------------------------------


def _code() -> str:
    return "\n".join(
        line
        for line in HOST_SCRIPT.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def test_it_never_reads_the_host_s_secrets_or_traces() -> None:
    code = _code()
    for needle in ("/etc/intake-staging", "env_get", "printenv", "set -x", "openbao-init", ".env"):
        assert needle not in code, needle
    assert "set +x" in code


def test_it_runs_the_checklist_steps_from_the_release_it_switched_to() -> None:
    code = _code()
    assert '(cd "$CURRENT/infra/staging" && bash "./$name.sh")' in code
    calls = [code.index(f"if ! step {name}; then") for name in ("init", "deploy", "smoke")]
    assert calls == sorted(calls), "init, then deploy, then smoke"
    assert code.index("\nfreeze_preflight\n") < code.index('point_at "$RELEASE"') < calls[0]

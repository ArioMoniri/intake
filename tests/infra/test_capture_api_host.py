"""INT-502: the throwaway capture API on the synthetic host, and its teardown.

``infra/staging/capture_api_host.sh`` runs a second API container beside the public one for one
App Store capture session. The tests run it alone, as SSM would, against the fakes of
``tests/infra/capture_api_fakes.py``. They pin:

- **only the capture instance is in dev.** Its env file carries the dev flags, its own
  database, Redis index 7 and a fresh tokenization key. None of the public API's vendor, vault
  or attestation settings is in it, so the dev delivery adapter is the SMS: a mock, nothing sent;
- **it is reachable from the host only.** The publish is ``127.0.0.1:<port>`` and its second
  network has no masquerade;
- **no secret is ever in an argv,** and the env file is gone once the container is created;
- **refusals:** a bad or busy port, an unpinned image, an image without the synthetic data
  class, missing secrets, already up, a same-named container that is not ours;
- **down** removes only what up made (the labelled container, its network, ``intake_capture``,
  Redis index 7), and is safe to repeat.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
HOST_SCRIPT = REPO / "infra" / "staging" / "capture_api_host.sh"
LAPTOP_SCRIPT = REPO / "scripts" / "store" / "capture_api.sh"
FAKES = Path(__file__).with_name("capture_api_fakes.py")
SHA = "0123456789abcdef0123456789abcdef01234567"
IMAGE = f"intake-staging/api:{SHA}"
SECRETS = {
    "POSTGRES_PASSWORD": "1" * 64,
    "PG_APP_RW_PASSWORD": "2" * 64,
    "PG_AUDIT_WRITER_PASSWORD": "3" * 64,
    "REDIS_PASSWORD": "4" * 64,
    "INTAKE_TOKENIZATION_KEY": "5" * 64,
    "OPENBAO_TOKEN": "s.publicapitoken",
}
PUBLIC_ONLY = (
    "OPENBAO",
    "INTAKE_SMS_EGRESS_PROXY_URL",
    "INTAKE_EGRESS_PROXY_URL",
    "INTAKE_ALLOW_PHI_EGRESS",
    "INTAKE_APP_ATTEST",
    "INTAKE_HOSTED_TTS",
    "MINIO_ROOT",
)


def _world(tmp_path: Path, **overrides: Any) -> dict[str, Any]:
    state = tmp_path / "state"
    state.mkdir()
    world = {
        "image": IMAGE,
        "image_env": ["PATH=/app/.venv/bin", "INTAKE_DEPLOYMENT_DATA_CLASS=synthetic"],
        "container": None,
        "network": False,
        "port_busy": False,
        "healthy": True,
        **overrides,
    }
    (state / "world.json").write_text(json.dumps(world), encoding="utf-8")
    env_file = tmp_path / "env"
    env_file.write_text("".join(f"{k}={v}\n" for k, v in SECRETS.items()), encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in ("docker", "ss", "openssl", "curl", "sleep"):
        wrapper = bin_dir / tool
        wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKES}" {tool} "$@"\n')
        wrapper.chmod(0o755)
    return {"state": state, "env_file": env_file, "bin": bin_dir, "run": tmp_path / "run"}


def _host(world: dict[str, Any], *args: str) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": f"{world['bin']}:{os.environ['PATH']}",
        "FAKE_STATE": str(world["state"]),
        "INTAKE_STAGING_ENV_FILE": str(world["env_file"]),
        "INTAKE_CAPTURE_RUN_DIR": str(world["run"]),
        "INTAKE_CAPTURE_TEST": "1",
    }
    script = HOST_SCRIPT.read_text(encoding="utf-8")
    return subprocess.run(  # noqa: S603 — fixed argv, repo script
        ["bash", "-c", script, "capture_api_host", *args],  # noqa: S607
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _calls(world: dict[str, Any]) -> list[dict[str, Any]]:
    path = world["state"] / "calls.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _docker(world: dict[str, Any], verb: str) -> list[dict[str, Any]]:
    return [c for c in _calls(world) if c["tool"] == "docker" and c["argv"][0] == verb]


def _env_lines(text: str) -> dict[str, str]:
    return dict(line.split("=", 1) for line in text.splitlines() if line)


# --- up --------------------------------------------------------------------------------------


def test_up_starts_a_dev_instance_on_its_own_database_reachable_from_loopback_only(
    tmp_path: Path,
) -> None:
    world = _world(tmp_path)
    result = _host(world, "up", "18502")
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == f"capture_api: up 127.0.0.1:18502 {IMAGE}"
    (create,) = _docker(world, "create")
    argv = create["argv"]
    assert argv[argv.index("-p") + 1] == "127.0.0.1:18502:8000"
    assert argv[argv.index("--network") + 1] == "intake-staging_backend"
    assert argv[-1] == IMAGE
    env = _env_lines(create["envfile"])
    assert env["INTAKE_ENV"] == "dev"
    assert env["INTAKE_API_KEK_MODE"] == "file-dev"
    assert env["INTAKE_DEV_ALLOW_UNATTESTED"] == "explicit-yes"
    assert env["INTAKE_DEV_OTP_PEEK"] == "explicit-yes"
    for key in ("INTAKE_API_DB_URL", "INTAKE_API_AUDIT_DB_URL", "INTAKE_API_BOOTSTRAP_DB_URL"):
        assert env[key].endswith("@postgres:5432/intake_capture"), key
    assert env["INTAKE_REDIS_URL"].endswith("@redis:6379/7")
    assert env["INTAKE_TOKENIZATION_KEY"] != SECRETS["INTAKE_TOKENIZATION_KEY"]
    assert env["INTAKE_API_TRIAGE_TENANT_KIND"] == "synthetic"
    assert not [key for key in env if key.startswith(PUBLIC_ONLY)]


def test_up_migrates_before_the_api_starts_and_isolates_its_network(tmp_path: Path) -> None:
    world = _world(tmp_path)
    assert _host(world, "up", "18502").returncode == 0
    verbs = [c["argv"][0] for c in _calls(world) if c["tool"] == "docker"]
    assert verbs.index("run") < verbs.index("create") < verbs.index("start")
    (run,) = _docker(world, "run")
    assert "alembic upgrade head" in run["argv"][-1]
    assert "--rm" in run["argv"]
    created = [c for c in _docker(world, "network") if c["argv"][1] == "create"]
    assert "com.docker.network.bridge.enable_ip_masquerade=false" in created[0]["argv"]
    psql = [c for c in _docker(world, "exec") if "psql" in c["argv"]]
    assert len(psql) == 1 and "CREATE DATABASE intake_capture" in psql[0]["stdin"]


def test_no_secret_is_ever_in_an_argv_and_the_env_file_is_gone(tmp_path: Path) -> None:
    world = _world(tmp_path)
    assert _host(world, "up", "18502").returncode == 0
    argvs = " ".join(" ".join(c["argv"]) for c in _calls(world))
    for value in SECRETS.values():
        assert value not in argvs
    assert "ab" * 32 not in argvs
    assert not (world["run"] / "capture.env").exists()


def test_up_never_touches_the_public_stack(tmp_path: Path) -> None:
    world = _world(tmp_path)
    assert _host(world, "up", "18502").returncode == 0
    for call in _calls(world):
        argv = call["argv"]
        assert "compose" not in argv
        assert argv[0] not in {"stop", "restart", "kill", "rm", "update"}, argv
        if argv[0] == "exec":
            assert argv[2] in {"intake-staging-postgres-1", "intake-staging-redis-1"}


@pytest.mark.parametrize(
    ("args", "world", "needle"),
    [
        (("up", "80"), {}, "port must be"),
        (("up", "99999"), {}, "port must be"),
        (("up", "18502;id"), {}, "port must be"),
        (("up", "18502"), {"port_busy": True}, "in use"),
        (("up", "18502"), {"image": None}, "not running"),
        (("up", "18502"), {"image": "intake-staging/api:latest"}, "pinned release"),
        (("up", "18502"), {"image_env": ["PATH=/app"]}, "synthetic data class"),
        (("up", "18502"), {"container": "INT-502"}, "already up"),
        (("up", "18502"), {"container": "someone-else"}, "without label"),
        (("up", "18502"), {"healthy": False}, "healthz"),
        (("sideways",), {}, "mode must be"),
    ],
)
def test_up_refuses(
    tmp_path: Path, args: tuple[str, ...], world: dict[str, Any], needle: str
) -> None:
    built = _world(tmp_path, **world)
    result = _host(built, *args)
    assert result.returncode == 3
    assert result.stdout.startswith("capture_api: refused: ") and needle in result.stdout
    if needle != "healthz":
        assert not _docker(built, "create")


def test_up_refuses_an_env_file_without_the_generated_secrets(tmp_path: Path) -> None:
    world = _world(tmp_path)
    world["env_file"].write_text("POSTGRES_PASSWORD=short\n", encoding="utf-8")
    result = _host(world, "up", "18502")
    assert result.returncode == 3 and "generated database or Redis secret" in result.stdout
    assert not _docker(world, "exec")


# --- down and status ---------------------------------------------------------------------------


def test_down_removes_only_what_up_made(tmp_path: Path) -> None:
    world = _world(tmp_path)
    assert _host(world, "up", "18502").returncode == 0
    result = _host(world, "down")
    assert result.returncode == 0 and result.stdout.strip() == "capture_api: down"
    removed = [c["argv"] for c in _docker(world, "rm")]
    assert removed == [["rm", "-f", "intake-capture-api"]]
    execs = _docker(world, "exec")
    drop = [c for c in execs if "DROP DATABASE" in c["stdin"]]
    assert len(drop) == 1 and "DROP DATABASE IF EXISTS intake_capture" in drop[0]["stdin"]
    flush = [c for c in execs if "intake-staging-redis-1" in c["argv"]]
    assert len(flush) == 1
    assert flush[0]["argv"][-2:] == ["7", "FLUSHDB"]
    assert flush[0]["stdin"] == SECRETS["REDIS_PASSWORD"]
    assert _host(world, "status").stdout.strip() == "capture_api: absent"


def test_down_is_safe_to_repeat_and_leaves_a_foreign_container_alone(tmp_path: Path) -> None:
    world = _world(tmp_path)
    assert _host(world, "down").returncode == 0
    assert not _docker(world, "rm")
    (tmp_path / "other").mkdir()
    foreign = _world(tmp_path / "other", container="someone-else")
    result = _host(foreign, "down")
    assert result.returncode == 3 and "without label" in result.stdout
    assert not _docker(foreign, "rm")


def test_status_reports_running(tmp_path: Path) -> None:
    world = _world(tmp_path, container="INT-502")
    assert _host(world, "status").stdout.strip() == "capture_api: running"


# --- the laptop half and hygiene ----------------------------------------------------------------


@pytest.mark.parametrize("args", [("up",), ("up", "80"), ("forward", "x"), ("delete",)])
def test_the_laptop_script_refuses_before_calling_aws(
    tmp_path: Path, args: tuple[str, ...]
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    marker = tmp_path / "aws-called"
    (bin_dir / "aws").write_text(f"#!/bin/sh\ntouch {marker}\n")
    (bin_dir / "aws").chmod(0o755)
    result = subprocess.run(  # noqa: S603 — fixed argv, repo script
        ["bash", str(LAPTOP_SCRIPT), *args],  # noqa: S607
        env={"PATH": f"{bin_dir}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert not marker.exists()


def test_both_scripts_are_shellcheck_clean() -> None:
    try:
        result = subprocess.run(  # noqa: S603
            ["shellcheck", str(HOST_SCRIPT), str(LAPTOP_SCRIPT)],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        pytest.fail("shellcheck is not installed; it is on GitHub's ubuntu image and the AWS host")
    assert result.returncode == 0, result.stdout + result.stderr

"""INT-560 — the probes service on the synthetic AWS host, validated statically.

No container runtime exists where this suite runs, so nothing here boots one.
What is decidable without booting anything:

- the service runs the API's own image (one SBOM describes both) as the probes
  app, which mounts the monitoring contract (invariant 15);
- it joins the two internal networks its targets sit on and nothing else: no
  route off the host, no leg on the API's ``outbound`` network (INT-442), no
  published port;
- it writes its sweep to a volume the API mounts read-only, at the path the
  API's console reads, and the image creates that mount point for the service
  user;
- its two credentials are host-generated secrets, least-privilege at the
  other end: a Postgres role with LOGIN and CONNECT and nothing else, and a
  Redis user that may run PING and nothing else. A host initialised before
  this issue gets both from deploy.sh, with no init re-run;
- the runbook says all of this.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml
from intake_probes.host_sweep import ENV_POSTGRES_PASSWORD, ENV_REDIS_PASSWORD, ENV_TLS_SERVER_NAME
from intake_probes.inventory import ENV_HOST_INVENTORY, load_host_inventory
from intake_probes.registry import load_registry

REPO = Path(__file__).resolve().parents[2]
STAGING = REPO / "infra" / "staging"
COMPOSE = STAGING / "compose.yaml"
DOCKERFILE = STAGING / "Dockerfile.api"
LIB = STAGING / "lib.sh"
DEPLOY = STAGING / "deploy.sh"
ENV_TEMPLATE = STAGING / "staging.env.template"
INVENTORY = STAGING / "inventory.yaml"
RUNBOOK = REPO / "docs" / "runbooks" / "staging.md"

RESULTS_DIR = "/var/lib/intake/probe-results"
RESULTS_PATH = f"{RESULTS_DIR}/sweep.json"
INVENTORY_IN_IMAGE = "/app/infra/staging/inventory.yaml"
PROBE_KEYS = ("PG_PROBE_PASSWORD", "REDIS_PROBE_PASSWORD")
REQUIRED = re.compile(r"^\$\{([A-Z_][A-Z0-9_]*):\?[^}]+\}$")


def _compose() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    return loaded


def _service(name: str) -> dict[str, Any]:
    service: dict[str, Any] = _compose()["services"][name]
    return service


def _env(name: str) -> dict[str, str]:
    raw = _service(name).get("environment", {})
    return {str(k): str(v) for k, v in raw.items()}


def _code(path: Path) -> str:
    return "\n".join(
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )


def _shim(path: Path, body: str) -> None:
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(0o755)


def _lib(tmp_path: Path, script: str) -> subprocess.CompletedProcess[str]:
    """lib.sh with a scratch env file and a docker that records argv and stdin."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    _shim(
        bin_dir / "docker",
        f'printf "%s\\n" "$*" >>"{tmp_path}/docker.log"\ncat >>"{tmp_path}/stdin.log"\n',
    )
    return subprocess.run(
        ["bash", "-c", f'source "{LIB}"; ENV_FILE="{tmp_path}/.env"; {script}', "lib-test"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={
            "PATH": f"{bin_dir}:{os.environ.get('PATH', '/usr/bin:/bin')}",
            "HOME": str(tmp_path),
            "INTAKE_STAGING_STATE_DIR": str(tmp_path),
        },
        check=False,
    )


# --- the service ------------------------------------------------------------------------


def test_it_runs_the_api_image_as_the_probes_app() -> None:
    probes = _service("probes")
    assert probes["image"] == _service("api")["image"], "one image, one SBOM"
    assert "build" not in probes, "deploy.sh builds the api image once"
    command = probes["command"]
    assert command[:3] == ["uvicorn", "intake_probes.app:create_app", "--factory"]
    # the image's HEALTHCHECK dials 127.0.0.1:8000/healthz, which the probes
    # app answers through the shared monitoring contract
    assert command[command.index("--port") + 1] == "8000"


def test_it_carries_the_release_stamp_for_version() -> None:
    match = REQUIRED.match(_env("probes")["INTAKE_SBOM_DIGEST"])
    assert match and match.group(1) == "INTAKE_SBOM_DIGEST"


def test_it_joins_only_the_internal_networks_its_targets_sit_on() -> None:
    compose = _compose()
    networks = compose["networks"]
    joined = set(_service("probes")["networks"])
    assert joined == {"backend", "edge"}
    for network in joined:
        assert networks[network].get("internal") is True, network
    # near miss: `outbound` is internal too, but it is the API's road to the
    # egress proxy and the vendors behind it; the probes stay off it
    assert "outbound" not in joined and "vendor" not in joined and "public" not in joined


def test_every_probe_address_resolves_on_a_network_the_service_joins() -> None:
    compose = _compose()
    joined = set(_service("probes")["networks"])
    registry = load_registry(REPO / "observability" / "registry.yaml")
    inventory = load_host_inventory(
        INVENTORY, registry=registry, env={"INTAKE_DEPLOYMENT_DATA_CLASS": "synthetic"}
    )
    for service in inventory.services.values():
        for placement in service.components:
            if placement.probe_at is None:
                continue
            host = placement.dial_host()
            assert set(compose["services"][host]["networks"]) & joined, placement.probe_at
    # near miss: the one deployed component it cannot reach is declared unprobed
    proxy = inventory.placement("egress-proxy")
    assert proxy is not None and proxy.probe_at is None
    assert not set(compose["services"]["egress-proxy"]["networks"]) & joined


def test_it_publishes_nothing_and_runs_hardened() -> None:
    probes = _service("probes")
    assert "ports" not in probes and "expose" not in probes
    assert probes["read_only"] is True
    assert probes["cap_drop"] == ["ALL"]
    assert "cap_add" not in probes
    assert "no-new-privileges:true" in probes["security_opt"]
    assert probes["ulimits"]["core"] == 0
    assert "user" not in probes, "the image's non-root service user"


def test_it_reads_the_inventory_and_writes_the_sweep_the_api_reads() -> None:
    probes, api = _env("probes"), _env("api")
    assert probes[ENV_HOST_INVENTORY] == api[ENV_HOST_INVENTORY] == INVENTORY_IN_IMAGE
    assert probes["INTAKE_PROBE_RESULTS_PATH"] == api["INTAKE_PROBE_RESULTS_PATH"] == RESULTS_PATH
    assert f"probe-results:{RESULTS_DIR}" in _service("probes")["volumes"]
    assert f"probe-results:{RESULTS_DIR}:ro" in _service("api")["volumes"]
    assert "probe-results" in _compose()["volumes"]


def test_no_other_service_mounts_the_sweep() -> None:
    for name, service in _compose()["services"].items():
        if name in {"api", "probes"}:
            continue
        assert not [v for v in service.get("volumes", []) if "probe-results" in str(v)], name


def test_the_image_creates_the_results_mount_point_for_the_service_user() -> None:
    text = _code(DOCKERFILE)
    match = re.search(r"install -d -o 10001 -g 10001 -m 0750 ([^\\\n&]+)", text)
    assert match, "the runtime stage creates the service user's directories"
    assert RESULTS_DIR in match.group(1).split()


# --- credentials: least privilege at the other end ----------------------------------------


def test_the_two_credentials_are_required_host_secrets() -> None:
    probes = _env("probes")
    for variable, key in (
        (ENV_POSTGRES_PASSWORD, "PG_PROBE_PASSWORD"),
        (ENV_REDIS_PASSWORD, "REDIS_PROBE_PASSWORD"),
    ):
        match = REQUIRED.match(probes[variable])
        assert match and match.group(1) == key, variable
    match = REQUIRED.match(probes[ENV_TLS_SERVER_NAME])
    assert match and match.group(1) == "STAGING_HOSTNAME"


def test_the_api_never_holds_a_probe_credential() -> None:
    api = " ".join(_env("api").values())
    for key in PROBE_KEYS:
        assert key not in api, key


def test_the_template_lists_both_keys_empty() -> None:
    lines = ENV_TEMPLATE.read_text(encoding="utf-8").splitlines()
    for key in PROBE_KEYS:
        assert f"{key}=" in lines, key


def test_redis_admits_the_probe_user_for_ping_and_nothing_else() -> None:
    redis = _service("redis")
    script = "\n".join(redis["command"])
    assert (
        # `$$` is compose's escape: the shell inside the container expands it
        "user intake-probe on >$$REDIS_PROBE_PASSWORD resetkeys resetchannels -@all +ping" in script
    )
    # the password reaches redis-server on stdin (the heredoc), never argv
    assert "exec redis-server - <<EOF" in script
    env = {str(k): str(v) for k, v in redis["environment"].items()}
    match = REQUIRED.match(env["REDIS_PROBE_PASSWORD"])
    assert match and match.group(1) == "REDIS_PROBE_PASSWORD"


def test_the_inventory_names_the_same_user_and_role_the_host_creates() -> None:
    text = INVENTORY.read_text(encoding="utf-8")
    assert "redis://intake-probe@redis:6379/0" in text
    assert "postgres://svc_probe@postgres:5432/intake" in text
    assert "PROBE_DB_ROLE=svc_probe" in LIB.read_text(encoding="utf-8")


def test_the_probe_role_gets_login_and_connect_only(tmp_path: Path) -> None:
    secret = "ab" * 32
    (tmp_path / ".env").write_text(f"PG_PROBE_PASSWORD={secret}\n", encoding="utf-8")
    result = _lib(tmp_path, "ensure_probe_role")
    assert result.returncode == 0, result.stderr
    sql = (tmp_path / "stdin.log").read_text(encoding="utf-8")
    assert "SET log_statement = 'none'" in sql
    assert "CREATE ROLE svc_probe LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT" in sql
    assert f"ALTER ROLE svc_probe PASSWORD '{secret}'" in sql
    grants = re.findall(r"GRANT [^;]+;", sql)
    assert grants == ["GRANT CONNECT ON DATABASE intake TO svc_probe;"]
    # the password travels on stdin, never in docker's argv
    assert secret not in (tmp_path / "docker.log").read_text(encoding="utf-8")


def test_the_probe_role_refuses_a_password_that_was_not_generated(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "PG_PROBE_PASSWORD=hunter2'; DROP ROLE x; --\n", encoding="utf-8"
    )
    result = _lib(tmp_path, "ensure_probe_role")
    assert result.returncode != 0
    assert not (tmp_path / "stdin.log").exists(), "nothing reached psql"
    assert "hunter2" not in result.stderr


def test_deploy_fills_a_missing_probe_credential_and_keeps_an_existing_one(tmp_path: Path) -> None:
    kept = "cd" * 32
    (tmp_path / ".env").write_text(
        f"POSTGRES_PASSWORD=x\nREDIS_PROBE_PASSWORD={kept}\n", encoding="utf-8"
    )
    result = _lib(tmp_path, "ensure_probe_secrets")
    assert result.returncode == 0, result.stderr
    env = dict(
        line.split("=", 1) for line in (tmp_path / ".env").read_text(encoding="utf-8").splitlines()
    )
    assert re.fullmatch(r"[0-9a-f]{64}", env["PG_PROBE_PASSWORD"])
    assert env["REDIS_PROBE_PASSWORD"] == kept
    assert env["POSTGRES_PASSWORD"] == "x", "nothing else is touched"
    assert env["PG_PROBE_PASSWORD"] not in result.stderr


def test_deploy_without_an_env_file_still_points_at_init(tmp_path: Path) -> None:
    result = _lib(tmp_path, "ensure_probe_secrets")
    assert result.returncode != 0
    assert "init.sh" in result.stderr


def test_deploy_orders_the_probe_steps() -> None:
    code = _code(DEPLOY)
    steps = [
        "ensure_probe_secrets",
        "load_env",
        "compose up -d postgres redis openbao",
        "run_migrations",
        "ensure_probe_role",
        "compose up -d --no-build --wait --remove-orphans",
    ]
    positions = [code.index(step) for step in steps]
    assert positions == sorted(positions), list(zip(steps, positions, strict=True))
    assert code.index("require_root") < code.index("ensure_probe_secrets")


# --- the runbook ---------------------------------------------------------------------------


def test_the_runbook_says_what_the_probes_service_does() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "## Probes and the registry page" in text
    section = text.split("## Probes and the registry page", 1)[1].split("\n## ", 1)[0]
    for needle in (
        "inventory.yaml",
        "svc_probe",
        "intake-probe",
        "PG_PROBE_PASSWORD",
        "REDIS_PROBE_PASSWORD",
        "not deployed on synthetic-aws",
        "blocking",
    ):
        assert needle in section, needle

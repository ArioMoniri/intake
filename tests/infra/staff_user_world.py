"""INT-538: the world tests/infra/test_staff_user.py runs scripts/ops/staff_user.sh in.

``world()`` lays out a temporary directory with the fakes of ``staff_user_fakes.py`` on
``PATH``, a realm, a parameter store, the host's env file and the realm config, and returns the
environment both halves run with. ``World`` reads back what the fakes recorded.
"""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "ops" / "staff_user.sh"
HOST_SCRIPT = REPO / "infra" / "staging" / "staff_user_host.sh"
FAKES = Path(__file__).resolve().parent / "staff_user_fakes.py"

#: Test-only values, valid for nothing. Derived, so no literal secret sits in the tree.
TEMP_PASSWORD = hashlib.sha256(b"INT-538 temporary password, test only").hexdigest()
BOOTSTRAP = hashlib.sha256(b"INT-538 bootstrap admin password, test only").hexdigest()
FIRST_ORG = "org:int538-test"
OWNER_ORG = "org:int538-owner"
USERNAME = "ada.owner"
EMAIL = "ada.owner@example.org"
PARAM = f"/intake/staging/staff_tmp/{USERNAME}"
PROMPTS = "username: email: role (platform_owner|qms_owner): "
REVEAL = (
    f"aws ssm get-parameter --region us-east-1 --name {PARAM} --with-decryption"
    f" --query Parameter.Value --output text"
    f" && aws ssm delete-parameter --region us-east-1 --name {PARAM}"
)
#: The laptop half runs under /bin/bash: macOS ships bash 3.2 there, Linux a current one.
BASH = "/bin/bash"


@dataclass
class World:
    root: Path
    env: dict[str, str]

    @property
    def state(self) -> Path:
        return self.root / "state"

    def calls(self, tool: str | None = None) -> list[dict[str, Any]]:
        path = self.state / "calls.jsonl"
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        calls = [json.loads(line) for line in lines]
        return [c for c in calls if tool is None or c["tool"] == tool]

    def params(self) -> dict[str, dict[str, str]]:
        return self._json("params.json", {})

    def realm(self) -> dict[str, Any]:
        return self._json("keycloak.json", {})

    def invocations(self) -> dict[str, dict[str, Any]]:
        return self._json("invocations.json", {})

    def user(self, username: str) -> dict[str, Any] | None:
        return next((u for u in self.realm()["users"] if u["username"] == username), None)

    def container_tmp(self) -> list[Path]:
        return sorted((self.state / "container" / "tmp").iterdir())

    def _json(self, name: str, default: Any) -> Any:
        path = self.state / name
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def world(
    tmp_path: Path,
    *,
    users: list[dict[str, Any]] | None = None,
    first_org: str | None = None,
    params: dict[str, dict[str, str]] | None = None,
    env_password: str | None = BOOTSTRAP,
    fail: str | None = None,
    **extra_env: str,
) -> World:
    bin_dir = tmp_path / "bin"
    state = tmp_path / "state"
    (state / "container" / "tmp").mkdir(parents=True)
    bin_dir.mkdir()
    python = f"{shlex.quote(sys.executable)} -I -S {shlex.quote(str(FAKES))}"
    wrappers = {tool: f'exec {python} {tool} "$@"' for tool in ("aws", "docker", "openssl")}
    # sleep only logs, in the same shape, without starting a Python
    wrappers["sleep"] = (
        """printf '{"tool": "sleep", "argv": ["%s"], "stdin": ""}\\n' "$1" """
        """>>"$FAKE_STATE/calls.jsonl\""""
    )
    for tool, body in wrappers.items():
        wrapper = bin_dir / tool
        wrapper.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
        wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
    realm: dict[str, Any] = {"users": users or [], "bootstrap_password": BOOTSTRAP}
    if fail:
        realm["fail"] = fail
    (state / "keycloak.json").write_text(json.dumps(realm), encoding="utf-8")
    (state / "params.json").write_text(json.dumps(params or {}), encoding="utf-8")
    env_file = tmp_path / "host-env"
    lines = ["STAGING_HOSTNAME=3-211-2-143.sslip.io"]
    if env_password is not None:
        lines.append(f"KEYCLOAK_ADMIN_PASSWORD={env_password}")
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    realm_config = tmp_path / "intake-realm.json"
    config: dict[str, Any] = {"realm": "intake"}
    if first_org is not None:
        config["attributes"] = {"intake.first_staff_org": first_org}
    realm_config.write_text(json.dumps(config), encoding="utf-8")
    laptop_tmp = tmp_path / "laptop-tmp"
    laptop_tmp.mkdir()
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "TMPDIR": str(laptop_tmp),
        "FAKE_STATE": str(state),
        "FAKE_OPENSSL_VALUE": TEMP_PASSWORD,
        "INTAKE_STAGING_ENV_FILE": str(env_file),
        "INTAKE_STAFF_REALM_FILE": str(realm_config),
        **extra_env,
    }
    return World(root=tmp_path, env=env)


def run_laptop(world: World, answers: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [BASH, str(SCRIPT), *args],
        input=answers,
        env=world.env,
        capture_output=True,
        text=True,
        check=False,
    )


def answers(username: str = USERNAME, email: str = EMAIL, role: str = "platform_owner") -> str:
    return f"{username}\n{email}\n{role}\n"


def owner(
    org: str = OWNER_ORG, *, username: str = "first.owner", uid: str = "1111"
) -> dict[str, Any]:
    return {
        "id": uid,
        "username": username,
        "email": f"{username}@example.org",
        "attributes": {"org": [org]},
        "roles": ["platform_owner"],
    }


def assert_no_secret_escaped(world: World, result: subprocess.CompletedProcess[str]) -> None:
    for secret in (TEMP_PASSWORD, BOOTSTRAP):
        assert secret not in result.stdout + result.stderr
        for call in world.calls():
            assert secret not in " ".join(call["argv"]), call["tool"]
        for record in world.invocations().values():
            assert secret not in json.dumps(record["parameters"])
            assert secret not in record["stdout"] + record["stderr"]
    # nothing of the laptop's private request directory is left
    assert list(Path(world.env["TMPDIR"]).iterdir()) == []


def assert_kcadm_config_deleted(world: World) -> None:
    assert world.container_tmp() == [], "the throwaway kcadm config is gone"
    docker = [c["argv"] for c in world.calls("docker")]
    made = [argv[-1] for argv in docker if "mkdir" in argv]
    removed = [argv[-1] for argv in docker if "rm" in argv]
    assert len(made) == 1 and removed == made

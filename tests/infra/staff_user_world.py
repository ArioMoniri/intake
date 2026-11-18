"""INT-538: the world tests/infra/test_staff_user.py runs scripts/ops/staff_user.sh in.

``world()`` lays out a temporary directory with the fakes of ``staff_user_fakes.py`` on
``PATH``, a realm, a parameter store and the host's env file, and returns the environment both
halves run with. ``World`` reads back what the fakes recorded.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
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
#: the slug typed for the very first user, and an existing platform_owner's org
FIRST_ORG = "int538-test"
OWNER_ORG = "org:int538-owner"
USERNAME = "ada.owner"
EMAIL = "ada.owner@example.org"
PARAM = f"/intake/staging/staff_tmp/{USERNAME}"
PROMPTS = "username: email: role (platform_owner|qms_owner): "
ORG_PROMPT = "organisation id: "


def reveal_for(param: str) -> str:
    """The one command that shows the temporary password once, then deletes it.

    The value is printed alone on its line, with nothing after it, and then a line with its
    length, so the owner can see a short or long paste before signing in.
    """
    return (
        f"v=$(aws ssm get-parameter --region us-east-1 --name {param} --with-decryption"
        " --query Parameter.Value --output text)"
        ' && printf \'%s\\npaste exactly; %s characters\\n\' "$v" "${#v}"'
        f" && aws ssm delete-parameter --region us-east-1 --name {param}; unset v"
    )


REVEAL = reveal_for(PARAM)


def revealed(value: str) -> str:
    """What the reveal command prints for a value."""
    return f"{value}\npaste exactly; {len(value)} characters\n"


#: The laptop half runs under /bin/bash: macOS ships bash 3.2 there, Linux a current one.
BASH = "/bin/bash"
RUNBOOK = REPO / "docs" / "runbooks" / "second-admin.md"
COMMAND_SHAPE = re.compile(
    r"^bash -c \"\$\(printf %s '([A-Za-z0-9+/=]+)' \| base64 -d\)\" staff_user_host"
    r"((?: '[^']*')+)$"
)


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
    laptop_tmp = tmp_path / "laptop-tmp"
    laptop_tmp.mkdir()
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "TMPDIR": str(laptop_tmp),
        "FAKE_STATE": str(state),
        "FAKE_OPENSSL_VALUE": TEMP_PASSWORD,
        "INTAKE_STAGING_ENV_FILE": str(env_file),
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


def run_host(world: World, *args: str) -> subprocess.CompletedProcess[str]:
    """The host half alone, as SSM would run it, against the same fakes."""
    return subprocess.run(
        ["bash", str(HOST_SCRIPT), *args],
        env=world.env,
        capture_output=True,
        text=True,
        check=False,
    )


def answers(
    username: str = USERNAME,
    email: str = EMAIL,
    role: str = "platform_owner",
    org: str | None = FIRST_ORG,
) -> str:
    """The typed answers; the org line only matters when no platform_owner exists."""
    typed = f"{username}\n{email}\n{role}\n"
    return typed if org is None else f"{typed}{org}\n"


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


def seeded(tmp_path: Path, **kwargs: Any) -> World:
    """A world where the laptop already put the temporary password (for host-only runs)."""
    return world(
        tmp_path, params={PARAM: {"Type": "SecureString", "Value": TEMP_PASSWORD}}, **kwargs
    )


def host_commands(world: World) -> list[list[str]]:
    """Each send-command's host arguments, after checking it is the committed script."""
    commands = []
    for record in world.invocations().values():
        assert record["document"] == "AWS-RunShellScript"
        assert record["instance"] == "i-0e489e48739f5de98"
        assert set(record["parameters"]) == {"commands"}
        (command,) = record["parameters"]["commands"]
        match = COMMAND_SHAPE.fullmatch(command)
        assert match, command
        assert base64.b64decode(match.group(1)) == HOST_SCRIPT.read_bytes()
        commands.append(shlex.split(match.group(2)))
    return commands


def assert_nothing_generated(world: World) -> None:
    assert world.calls("openssl") == [], "no temporary password was made"
    assert world.params() == {}
    assert len(world.invocations()) <= 1, "at most the probe ran"


def assert_kcadm_config_deleted(world: World, sessions: int = 1) -> None:
    """Every kcadm session made a fresh directory, and every one of them is gone."""
    assert world.container_tmp() == [], "the throwaway kcadm config is gone"
    docker = [c["argv"] for c in world.calls("docker")]
    made = [argv[-1] for argv in docker if "mkdir" in argv]
    removed = [argv[-1] for argv in docker if "rm" in argv]
    assert len(made) == sessions == len(set(made))
    assert removed == made

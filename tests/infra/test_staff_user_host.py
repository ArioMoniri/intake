"""INT-538: the host half of the staff-user command, and both scripts as files.

``infra/staging/staff_user_host.sh`` runs on the synthetic host in two modes. ``probe`` only
reads: it names the platform_owners' org, or says none exists. ``create`` makes the user. These
tests run it alone, as SSM would, against the fakes of ``tests/infra/staff_user_fakes.py``, and
pin what crosses to the host, the argument re-checks, the org rule, the IAM refusal, and the
scripts' own hygiene (shellcheck, shared shapes, where the secret variables may appear). The
end-to-end flows from the laptop live in ``tests/infra/test_staff_user.py``.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest
from staff_user_world import (
    BASH,
    EMAIL,
    FIRST_ORG,
    HOST_SCRIPT,
    ORG_PROMPT,
    OWNER_ORG,
    PARAM,
    RUNBOOK,
    SCRIPT,
    USERNAME,
)
from staff_user_world import answers as _answers
from staff_user_world import assert_kcadm_config_deleted as _assert_kcadm_config_deleted
from staff_user_world import assert_nothing_generated as _nothing_generated
from staff_user_world import host_commands as _host_commands
from staff_user_world import owner as _owner
from staff_user_world import run_host as _host
from staff_user_world import run_laptop as _run
from staff_user_world import seeded as _seeded
from staff_user_world import world as _world

IAM_REFUSAL = (
    "the instance role intake-staging-host may not read /intake/staging/staff_tmp/*: add"
    ' {"Effect":"Allow","Action":"ssm:GetParameter",'
    '"Resource":"arn:aws:ssm:us-east-1:123456789012:parameter/intake/staging/staff_tmp/*"}'
    " to its policy"
)


# --- what crosses to the host --------------------------------------------------------------------


class TestTheHostCommands:
    def test_a_probe_then_a_create_each_the_committed_script_and_plain_values(
        self, tmp_path: Path
    ) -> None:
        world = _world(tmp_path)
        _run(world, _answers())
        assert _host_commands(world) == [
            ["probe", PARAM, "us-east-1"],
            ["create", USERNAME, EMAIL, "platform_owner", PARAM, "us-east-1", FIRST_ORG],
        ]

    def test_the_probe_only_reads(self, tmp_path: Path) -> None:
        world = _world(tmp_path, users=[_owner()])
        result = _host(world, "probe", PARAM, "us-east-1")
        assert result.stdout == f"staff_user: owner-org {OWNER_ORG}\n"
        assert world.realm()["users"] == [_owner()] and world.params() == {}
        kcadm = "/opt/keycloak/bin/kcadm.sh"
        verbs = [
            c["argv"][c["argv"].index(kcadm) + 1]
            for c in world.calls("docker")
            if kcadm in c["argv"]
        ]
        assert verbs and set(verbs) == {"get"}
        _assert_kcadm_config_deleted(world)

    def test_the_probe_reports_no_owner(self, tmp_path: Path) -> None:
        world = _world(tmp_path)
        assert _host(world, "probe", PARAM, "us-east-1").stdout == "staff_user: no-owner\n"

    def test_the_host_runs_with_no_new_deploy(self) -> None:
        # it is delivered whole; it reads nothing from the release directory
        host = HOST_SCRIPT.read_text(encoding="utf-8")
        assert "source " not in host and "lib.sh" not in host and "/opt/intake" not in host


# --- the host re-checks every argument -----------------------------------------------------------


class TestHostRechecks:
    @pytest.mark.parametrize(
        ("index", "value"),
        [
            pytest.param(0, "delete", id="mode"),
            pytest.param(3, "platform-owner", id="role"),
            pytest.param(2, "ada@example", id="email"),
            pytest.param(1, "Ada", id="username"),
            pytest.param(4, "/intake/staging/staff_tmp/someone.else", id="parameter-of-another"),
            pytest.param(4, "/intake/staging/openai_api_key", id="parameter-outside-staff-tmp"),
            pytest.param(5, "us-east-1;id", id="region"),
            pytest.param(6, "org:intake", id="org-not-a-slug"),
            pytest.param(6, "", id="org-empty"),
        ],
    )
    def test_the_host_rechecks_every_create_argument(
        self, tmp_path: Path, index: int, value: str
    ) -> None:
        world = _world(tmp_path)
        args = ["create", USERNAME, EMAIL, "platform_owner", PARAM, "us-east-1", FIRST_ORG]
        args[index] = value
        result = _host(world, *args)
        assert result.returncode == 3
        assert result.stdout.startswith("staff_user: refused: ")
        assert world.calls() == [], "refused before the env file, docker or SSM"

    @pytest.mark.parametrize(
        "args",
        [
            pytest.param(["probe", "/intake/staging/openai_api_key", "us-east-1"], id="parameter"),
            pytest.param(["probe", PARAM, "us-east-1;id"], id="region"),
            pytest.param(["probe", PARAM], id="missing-region"),
        ],
    )
    def test_the_host_rechecks_every_probe_argument(self, tmp_path: Path, args: list[str]) -> None:
        world = _world(tmp_path)
        result = _host(world, *args)
        assert result.returncode == 3 and result.stdout.startswith("staff_user: refused: ")
        assert world.calls() == []


# --- the org rule --------------------------------------------------------------------------------


class TestTheOrgRule:
    def test_an_org_that_differs_from_the_owners_is_refused(self, tmp_path: Path) -> None:
        world = _seeded(tmp_path, users=[_owner()])
        result = _host(world, "create", USERNAME, EMAIL, "qms_owner", PARAM, "us-east-1", "other")
        assert result.stdout == (
            "staff_user: refused: a platform_owner exists and the org given differs from theirs\n"
        )
        assert world.user(USERNAME) is None
        _assert_kcadm_config_deleted(world)

    def test_near_miss_an_org_equal_to_the_owners_is_accepted(self, tmp_path: Path) -> None:
        world = _seeded(tmp_path, users=[_owner("int538-owner")])
        result = _host(
            world, "create", USERNAME, EMAIL, "qms_owner", PARAM, "us-east-1", "int538-owner"
        )
        assert result.stdout == "staff_user: created\n"
        user = world.user(USERNAME)
        assert user is not None and user["attributes"] == {"org": ["int538-owner"]}

    def test_no_org_is_invented_for_the_first_user(self, tmp_path: Path) -> None:
        world = _seeded(tmp_path)
        result = _host(world, "create", USERNAME, EMAIL, "platform_owner", PARAM, "us-east-1", "-")
        assert result.stdout == (
            "staff_user: refused: no platform_owner exists and no org was given for the first one\n"
        )
        assert world.realm()["users"] == []
        _assert_kcadm_config_deleted(world)

    def test_the_first_user_must_be_the_platform_owner_on_the_host(self, tmp_path: Path) -> None:
        world = _seeded(tmp_path)
        result = _host(world, "create", USERNAME, EMAIL, "qms_owner", PARAM, "us-east-1", FIRST_ORG)
        assert result.stdout.startswith("staff_user: refused: no platform_owner exists yet")
        assert world.realm()["users"] == []

    def test_the_first_user_must_be_the_platform_owner_on_the_laptop(self, tmp_path: Path) -> None:
        world = _world(tmp_path)
        result = _run(world, _answers(role="qms_owner"))
        assert result.returncode == 3
        assert result.stdout == (
            "refused: no platform_owner exists yet: create the platform_owner first;"
            " the second approver joins their org\n"
        )
        assert ORG_PROMPT not in result.stderr
        _nothing_generated(world)


# --- IAM -----------------------------------------------------------------------------------------


class TestIam:
    def test_a_role_that_may_not_read_staff_tmp_is_named_before_anything_is_made(
        self, tmp_path: Path
    ) -> None:
        world = _world(tmp_path, FAKE_ROLE_DENY="1")
        result = _run(world, _answers())
        assert result.returncode == 3
        assert result.stdout == f"refused: {IAM_REFUSAL}\n"
        _nothing_generated(world)
        assert world.calls("docker") == [], "named before Keycloak is touched"

    def test_the_create_step_names_it_too(self, tmp_path: Path) -> None:
        world = _seeded(tmp_path, FAKE_ROLE_DENY="1")
        result = _host(
            world, "create", USERNAME, EMAIL, "platform_owner", PARAM, "us-east-1", FIRST_ORG
        )
        assert result.stdout == f"staff_user: refused: {IAM_REFUSAL}\n"
        assert world.realm()["users"] == [] and world.calls("docker") == []

    def test_near_miss_a_parameter_not_there_yet_proves_the_permission(
        self, tmp_path: Path
    ) -> None:
        world = _world(tmp_path)  # the probe looks before the laptop puts anything
        result = _host(world, "probe", PARAM, "us-east-1")
        assert result.stdout == "staff_user: no-owner\n"


# --- the scripts themselves ----------------------------------------------------------------------


def _shape(script: Path, name: str) -> str:
    text = script.read_text(encoding="utf-8")
    (line,) = [ln for ln in text.splitlines() if ln.startswith(f"{name}=")]
    return line


class TestScripts:
    def test_both_are_executable_parse_and_use_env_bash(self) -> None:
        for script in (SCRIPT, HOST_SCRIPT):
            assert os.access(script, os.X_OK), script
            assert script.read_text(encoding="utf-8").splitlines()[0] == "#!/usr/bin/env bash"
            parsed = subprocess.run(
                [BASH, "-n", str(script)], capture_output=True, text=True, check=False
            )
            assert parsed.returncode == 0, parsed.stderr

    def test_both_are_shellcheck_clean(self) -> None:
        try:
            result = subprocess.run(
                ["shellcheck", str(SCRIPT), str(HOST_SCRIPT)],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            pytest.fail(
                "shellcheck is not installed; it is on GitHub's ubuntu image and on the AWS host"
            )
        assert result.returncode == 0, result.stdout + result.stderr

    @pytest.mark.parametrize("name", ["USERNAME_SHAPE", "EMAIL_SHAPE", "ROLE_SHAPE", "ORG_SLUG"])
    def test_laptop_and_host_check_the_same_shapes(self, name: str) -> None:
        assert _shape(SCRIPT, name) == _shape(HOST_SCRIPT, name)

    def test_the_realm_config_route_is_gone(self) -> None:
        for script in (SCRIPT, HOST_SCRIPT):
            text = script.read_text(encoding="utf-8")
            assert "first_staff_org" not in text and "REALM_FILE" not in text
        assert "first_staff_org" not in RUNBOOK.read_text(encoding="utf-8")

    def test_a_secret_variable_is_only_tested_piped_or_unset(self) -> None:
        # the secret variables may be assigned from a command's stdout, tested against a shape,
        # written by the printf builtin into a 0600 file or a pipe, or unset; never an argument
        allowed = {
            SCRIPT: ("pw=$(openssl rand -hex 32)", "[[ $pw =~", 'printf \'{"Name":"%s","Type"'),
            HOST_SCRIPT: (
                "admin_pw=$(awk ",
                "[[ $admin_pw =~",
                "printf '%s\\n' \"$admin_pw\" | docker exec -i ",
                "tmp_pw=$(aws ssm get-parameter ",
                "[[ $tmp_pw =~",
                'printf \'{"type":"password","temporary":true,"value":"%s"}\' "$tmp_pw" |',
                "unset ",
            ),
        }
        secret = re.compile(r"\$\{?(pw|admin_pw|tmp_pw)\b|\b(pw|admin_pw|tmp_pw)=")
        for script, shapes in allowed.items():
            for line in script.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("#") or not secret.search(stripped):
                    continue
                assert stripped.startswith(shapes), f"{script.name}: {stripped}"

    def test_the_put_is_a_secure_string_from_a_file_never_a_pipe(self) -> None:
        laptop = SCRIPT.read_text(encoding="utf-8")
        assert '--cli-input-json "file://$private/put.json"' in laptop
        assert "file:///dev/stdin" not in laptop and "--value" not in laptop
        assert '"Overwrite"' not in laptop, "a waiting password is never overwritten"

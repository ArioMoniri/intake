"""INT-538: one laptop command creates a staff user on the synthetic staging host.

``scripts/ops/staff_user.sh`` runs on the owner's laptop. It prompts for a username, an email
and a role (``platform_owner`` or ``qms_owner``, nothing else), generates a temporary password
straight into an SSM SecureString, and sends ``infra/staging/staff_user_host.sh``
base64-wrapped to the host over SSM. On the host, that script logs kcadm in with a throwaway
``--config`` file, creates the user in the realm's org, grants the role, sets the password from
SSM as temporary, and deletes the kcadm config whatever the outcome.

Every test here drives the real scripts end to end against fakes on ``PATH``
(``tests/infra/staff_user_fakes.py``): ``aws`` keeps a parameter store and runs the
send-command text with ``sh``, ``docker`` plays the Keycloak container with kcadm in it,
``openssl`` returns a known value, ``sleep`` returns at once. Nothing reaches AWS or Docker.

What is held:

- **Prompts and validation.** Three prompts in order. A role typo, a bad email, an empty or
  unsafe username are refused before any call, and the host re-checks every argument.
- **Secrets.** The temporary password and the bootstrap admin password never appear in any
  argv, in the send-command parameters, or in any output. The temporary password reaches
  Keycloak on stdin, marked temporary.
- **The org rule.** A new user joins the platform_owner's org. With no platform_owner, the
  org is the realm config's ``attributes."intake.first_staff_org"``, and with none the
  script refuses: no org is invented.
- **Refusals.** An existing username or email, a waiting temporary password, platform_owners
  that disagree, a failed step (rolled back) all refuse, and nothing is left behind.
- **The reveal command** shows the password once and deletes the parameter.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

import pytest
from staff_user_world import (
    BASH,
    BOOTSTRAP,
    EMAIL,
    FIRST_ORG,
    HOST_SCRIPT,
    OWNER_ORG,
    PARAM,
    PROMPTS,
    REPO,
    REVEAL,
    SCRIPT,
    TEMP_PASSWORD,
    USERNAME,
    World,
)
from staff_user_world import answers as _answers
from staff_user_world import assert_kcadm_config_deleted as _assert_kcadm_config_deleted
from staff_user_world import assert_no_secret_escaped as _assert_no_secret_escaped
from staff_user_world import owner as _owner
from staff_user_world import run_laptop as _run
from staff_user_world import world as _world

RUNBOOK = REPO / "docs" / "runbooks" / "second-admin.md"
COMMAND_SHAPE = re.compile(
    r"^bash -c \"\$\(printf %s '([A-Za-z0-9+/=]+)' \| base64 -d\)\" staff_user_host"
    r" '([^']*)' '([^']*)' '([^']*)' '([^']*)' '([^']*)'$"
)


# --- the happy path ------------------------------------------------------------------------------


class TestCreated:
    def test_the_first_platform_owner_is_created_in_the_realm_configs_org(
        self, tmp_path: Path
    ) -> None:
        world = _world(tmp_path, first_org=FIRST_ORG)
        result = _run(world, _answers())
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.stdout == f"created\n{REVEAL}\n"
        assert result.stderr == PROMPTS
        user = world.user(USERNAME)
        assert user is not None
        assert user["email"] == EMAIL
        assert user["enabled"] is True and user["emailVerified"] is True
        assert user["attributes"] == {"org": [FIRST_ORG]}
        assert user["requiredActions"] == ["webauthn-register", "UPDATE_PASSWORD"]
        assert user["roles"] == ["platform_owner"]
        assert user["credential"] == {"type": "password", "temporary": True, "value": TEMP_PASSWORD}
        # the password waits in SSM as a SecureString for the one reveal
        assert world.params() == {PARAM: {"Type": "SecureString", "Value": TEMP_PASSWORD}}
        _assert_no_secret_escaped(world, result)
        _assert_kcadm_config_deleted(world)

    def test_the_second_approver_joins_the_platform_owners_org(self, tmp_path: Path) -> None:
        # the realm config names another org: once a platform_owner exists, theirs wins
        world = _world(tmp_path, users=[_owner()], first_org=FIRST_ORG)
        result = _run(world, _answers("qa.approver", "qa.approver@example.org", "qms_owner"))
        assert result.returncode == 0, result.stdout + result.stderr
        user = world.user("qa.approver")
        assert user is not None
        assert user["attributes"] == {"org": [OWNER_ORG]}
        assert user["roles"] == ["qms_owner"]
        _assert_no_secret_escaped(world, result)
        _assert_kcadm_config_deleted(world)

    def test_the_email_is_stored_lower_case_and_never_printed(self, tmp_path: Path) -> None:
        world = _world(tmp_path, first_org=FIRST_ORG)
        result = _run(world, _answers(email="Ada.Owner@Example.ORG"))
        assert result.returncode == 0, result.stdout + result.stderr
        user = world.user(USERNAME)
        assert user is not None and user["email"] == EMAIL
        assert "ada.owner@" not in result.stdout.lower() + result.stderr.lower()
        for record in world.invocations().values():
            assert EMAIL not in record["stdout"] + record["stderr"]

    def test_secrets_travel_on_stdin_only(self, tmp_path: Path) -> None:
        world = _world(tmp_path, first_org=FIRST_ORG)
        _run(world, _answers())
        # the bootstrap password reaches the kcadm login, and the temporary password reaches
        # reset-password, each on docker exec's stdin and nowhere else
        with_bootstrap = [c["argv"] for c in world.calls("docker") if BOOTSTRAP in c["stdin"]]
        with_temporary = [c["argv"] for c in world.calls("docker") if TEMP_PASSWORD in c["stdin"]]
        assert len(with_bootstrap) == 1 and with_bootstrap[0][3:5] == ["bash", "-c"]
        assert "config credentials" in with_bootstrap[0][5]
        assert len(with_temporary) == 1 and with_temporary[0][4] == "update"
        assert with_temporary[0][5].endswith("/reset-password")
        assert [c["argv"] for c in world.calls("openssl")] == [["rand", "-hex", "32"]]


# --- the reveal command --------------------------------------------------------------------------


class TestReveal:
    def test_it_shows_the_password_once_and_deletes_the_parameter(self, tmp_path: Path) -> None:
        world = _world(tmp_path, first_org=FIRST_ORG)
        reveal = _run(world, _answers()).stdout.splitlines()[1]
        assert reveal == REVEAL
        first = subprocess.run(
            [BASH, "-c", reveal], env=world.env, capture_output=True, text=True, check=False
        )
        assert first.returncode == 0 and first.stdout == f"{TEMP_PASSWORD}\n"
        assert world.params() == {}
        again = subprocess.run(
            [BASH, "-c", reveal], env=world.env, capture_output=True, text=True, check=False
        )
        assert again.returncode != 0 and TEMP_PASSWORD not in again.stdout


# --- what crosses to the host --------------------------------------------------------------------


class TestTheHostCommand:
    def test_it_is_the_committed_host_script_and_the_four_plain_values(
        self, tmp_path: Path
    ) -> None:
        world = _world(tmp_path, first_org=FIRST_ORG)
        _run(world, _answers())
        (record,) = world.invocations().values()
        assert record["document"] == "AWS-RunShellScript"
        assert record["instance"] == "i-0e489e48739f5de98"
        (command,) = record["parameters"]["commands"]
        assert set(record["parameters"]) == {"commands"}
        match = COMMAND_SHAPE.fullmatch(command)
        assert match, command
        assert base64.b64decode(match.group(1)) == HOST_SCRIPT.read_bytes()
        assert list(match.groups()[1:]) == [USERNAME, EMAIL, "platform_owner", PARAM, "us-east-1"]

    def test_the_host_runs_with_no_new_deploy(self) -> None:
        # it is delivered whole; it sources nothing from the release directory
        host = HOST_SCRIPT.read_text(encoding="utf-8")
        assert "source " not in host and "lib.sh" not in host


# --- prompts and validation near misses ----------------------------------------------------------


NEAR_MISSES = [
    pytest.param(_answers(role="platform-owner"), "role", id="role-typo-hyphen"),
    pytest.param(_answers(role="qms_owners"), "role", id="role-typo-plural"),
    pytest.param(_answers(role="Platform_owner"), "role", id="role-capitalised"),
    pytest.param(_answers(role="platform_admin"), "role", id="role-real-but-not-offered"),
    pytest.param(_answers(role=""), "role", id="role-empty"),
    pytest.param(_answers(email="ada.owner@example"), "email", id="email-no-tld"),
    pytest.param(_answers(email="ada.owner.example.org"), "email", id="email-no-at"),
    pytest.param(_answers(email="ada@@example.org"), "email", id="email-double-at"),
    pytest.param(_answers(email="ada owner@example.org"), "email", id="email-space"),
    pytest.param(_answers(email="ada..owner@example.org"), "email", id="email-double-dot"),
    pytest.param(_answers(email="ada'@example.org"), "email", id="email-quote"),
    pytest.param(_answers(email=""), "email", id="email-empty"),
    pytest.param(_answers(username=""), "username", id="username-empty"),
    pytest.param("", "username", id="no-input-at-all"),
    pytest.param(_answers(username="Ada"), "username", id="username-capital"),
    pytest.param(_answers(username="ad"), "username", id="username-too-short"),
    pytest.param(_answers(username="1ada"), "username", id="username-leading-digit"),
    pytest.param(_answers(username="ada/../root"), "username", id="username-path"),
    pytest.param(_answers(username="ada owner"), "username", id="username-space"),
    pytest.param(_answers(username="a" * 65), "username", id="username-too-long"),
]


class TestValidation:
    @pytest.mark.parametrize(("answers", "field"), NEAR_MISSES)
    def test_a_near_miss_is_refused_before_any_call(
        self, tmp_path: Path, answers: str, field: str
    ) -> None:
        world = _world(tmp_path, first_org=FIRST_ORG)
        result = _run(world, answers)
        assert result.returncode == 2, result.stdout + result.stderr
        assert result.stdout == ""
        assert f"staff_user: the {field}" in result.stderr
        assert world.calls() == [], "nothing generated, nothing sent"
        assert world.realm()["users"] == []

    def test_the_prompts_come_in_order_and_stop_at_the_first_bad_answer(
        self, tmp_path: Path
    ) -> None:
        world = _world(tmp_path, first_org=FIRST_ORG)
        result = _run(world, _answers(username="Ada"))
        assert result.stderr.startswith("username: staff_user: the username")
        assert "email: " not in result.stderr

    def test_arguments_are_refused(self, tmp_path: Path) -> None:
        world = _world(tmp_path, first_org=FIRST_ORG)
        result = _run(world, _answers(), USERNAME)
        assert result.returncode == 2 and world.calls() == []

    @pytest.mark.parametrize(
        "override",
        [{"AWS_REGION": "us-east-1'"}, {"INTAKE_HOST_INSTANCE_ID": "i-0e489e48;id"}],
        ids=["region", "instance"],
    )
    def test_a_target_that_would_break_the_command_is_refused(
        self, tmp_path: Path, override: dict[str, str]
    ) -> None:
        world = _world(tmp_path, first_org=FIRST_ORG, **override)
        result = _run(world, _answers())
        assert result.returncode == 2 and result.stderr.startswith("staff_user: ")
        assert world.calls() == []

    @pytest.mark.parametrize(
        ("index", "value"),
        [
            pytest.param(2, "platform-owner", id="role"),
            pytest.param(1, "ada@example", id="email"),
            pytest.param(0, "Ada", id="username"),
            pytest.param(
                3, "/intake/staging/staff_tmp/someone.else", id="parameter-of-another-user"
            ),
            pytest.param(3, "/intake/staging/openai_api_key", id="parameter-outside-staff-tmp"),
            pytest.param(4, "us-east-1;id", id="region"),
        ],
    )
    def test_the_host_rechecks_every_argument(self, tmp_path: Path, index: int, value: str) -> None:
        world = _world(tmp_path, first_org=FIRST_ORG)
        args = [USERNAME, EMAIL, "platform_owner", PARAM, "us-east-1"]
        args[index] = value
        result = subprocess.run(
            ["bash", str(HOST_SCRIPT), *args],
            env=world.env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 3
        assert result.stdout.startswith("staff_user: refused: ")
        assert world.calls() == [], "refused before the env file, docker or SSM"


# --- refusals ------------------------------------------------------------------------------------


def _refused(world: World, answers: str = _answers()) -> str:
    result = _run(world, answers)
    assert result.returncode == 3, result.stdout + result.stderr
    assert result.stdout.startswith("refused: ")
    _assert_no_secret_escaped(world, result)
    return result.stdout


class TestRefusals:
    def test_an_existing_username_is_refused(self, tmp_path: Path) -> None:
        existing = _owner(username=USERNAME, uid="2222")
        world = _world(tmp_path, users=[existing], first_org=FIRST_ORG)
        out = _refused(world)
        assert out == f"refused: the username {USERNAME} already exists in realm intake\n"
        assert world.realm()["users"] == [existing], "nothing created or changed"
        assert world.params() == {}, "the unused temporary password is deleted"
        _assert_kcadm_config_deleted(world)

    def test_an_existing_email_is_refused(self, tmp_path: Path) -> None:
        existing = _owner(username="other.person", uid="2222")
        existing["email"] = EMAIL
        world = _world(tmp_path, users=[existing], first_org=FIRST_ORG)
        assert _refused(world) == "refused: that email already belongs to a user in realm intake\n"
        assert world.realm()["users"] == [existing] and world.params() == {}
        _assert_kcadm_config_deleted(world)

    def test_no_org_is_invented_for_the_first_user(self, tmp_path: Path) -> None:
        world = _world(tmp_path)  # no platform_owner, and the realm config names no org
        out = _refused(world)
        assert "no platform_owner exists" in out
        assert "intake.first_staff_org" in out and "intake-realm.json" in out
        assert world.realm()["users"] == [] and world.params() == {}
        _assert_kcadm_config_deleted(world)

    @pytest.mark.parametrize("bad", ["", " org", "org with space", "-org", "o" * 129])
    def test_near_miss_a_realm_config_org_that_is_not_org_shaped(
        self, tmp_path: Path, bad: str
    ) -> None:
        world = _world(tmp_path, first_org=bad)
        assert "org" in _refused(world)
        assert world.realm()["users"] == []

    @pytest.mark.parametrize(
        "content", [None, "{not json", "[]"], ids=["missing", "not-json", "not-an-object"]
    )
    def test_an_unreadable_realm_config_names_no_org(
        self, tmp_path: Path, content: str | None
    ) -> None:
        world = _world(tmp_path)
        realm_config = Path(world.env["INTAKE_STAFF_REALM_FILE"])
        if content is None:
            realm_config.unlink()
        else:
            realm_config.write_text(content, encoding="utf-8")
        assert "no platform_owner exists" in _refused(world)
        assert world.realm()["users"] == [] and world.params() == {}

    def test_platform_owners_in_two_orgs_are_refused(self, tmp_path: Path) -> None:
        owners = [_owner(), _owner("org:another", username="second.owner", uid="3333")]
        world = _world(tmp_path, users=owners, first_org=FIRST_ORG)
        assert _refused(world) == "refused: the platform_owners do not share one org\n"
        assert world.realm()["users"] == owners

    def test_a_platform_owner_without_an_org_is_refused(self, tmp_path: Path) -> None:
        owner = _owner()
        owner["attributes"] = {}
        world = _world(tmp_path, users=[owner], first_org=FIRST_ORG)
        assert _refused(world) == "refused: a platform_owner has no org attribute\n"

    def test_a_waiting_temporary_password_is_never_overwritten(self, tmp_path: Path) -> None:
        waiting = {PARAM: {"Type": "SecureString", "Value": "earlier-value-not-revealed"}}
        world = _world(tmp_path, first_org=FIRST_ORG, params=waiting)
        result = _run(world, _answers())
        assert result.returncode == 3
        assert result.stdout == (
            f"refused: a temporary password for {USERNAME} is still waiting in SSM;"
            f" reveal it (which deletes it) first:\n{REVEAL}\n"
        )
        assert world.params() == waiting
        assert world.invocations() == {} and world.calls("docker") == []

    @pytest.mark.parametrize("step", ["add-roles", "update"])
    def test_a_failed_step_after_creation_is_rolled_back(self, tmp_path: Path, step: str) -> None:
        world = _world(tmp_path, first_org=FIRST_ORG, fail=step)
        out = _refused(world)
        assert out.endswith("; the user was removed again\n")
        assert world.realm()["users"] == [] and world.params() == {}
        _assert_kcadm_config_deleted(world)

    def test_keycloak_refusing_the_create_is_refused(self, tmp_path: Path) -> None:
        world = _world(tmp_path, first_org=FIRST_ORG, fail="create")
        assert _refused(world) == "refused: Keycloak did not create the user\n"
        _assert_kcadm_config_deleted(world)

    def test_a_wrong_bootstrap_password_is_refused_and_its_config_deleted(
        self, tmp_path: Path
    ) -> None:
        wrong = hashlib.sha256(b"INT-538 some other value, test only").hexdigest()
        world = _world(tmp_path, first_org=FIRST_ORG, env_password=wrong)
        assert _refused(world) == "refused: kcadm could not log in as the bootstrap admin\n"
        assert wrong not in json.dumps([c["argv"] for c in world.calls()])
        _assert_kcadm_config_deleted(world)

    @pytest.mark.parametrize(
        "value",
        [None, "", "not-generated", BOOTSTRAP[:-1]],
        ids=["absent", "empty", "not-generated", "one-hex-short"],
    )
    def test_an_unreadable_bootstrap_password_stops_before_docker(
        self, tmp_path: Path, value: str | None
    ) -> None:
        world = _world(tmp_path, first_org=FIRST_ORG, env_password=value)
        assert _refused(world) == (
            "refused: KEYCLOAK_ADMIN_PASSWORD is not readable in the host's env file\n"
        )
        assert world.calls("docker") == []

    def test_a_stopped_keycloak_container_is_refused(self, tmp_path: Path) -> None:
        world = _world(tmp_path, first_org=FIRST_ORG, FAKE_CONTAINER_NAME="another-container")
        assert _refused(world) == (
            "refused: the Keycloak container intake-staging-keycloak-1 is not running\n"
        )


# --- outcomes the laptop cannot read -------------------------------------------------------------


class TestUnclearOutcomes:
    @pytest.mark.parametrize("status", ["InProgress", "Failed"])
    def test_an_unanswered_host_keeps_the_parameter_and_says_so(
        self, tmp_path: Path, status: str
    ) -> None:
        world = _world(tmp_path, first_org=FIRST_ORG, FAKE_HOST=status)
        result = _run(world, _answers())
        assert result.returncode == 1
        assert result.stdout == (
            f"unknown: host command cmd-0001 ended {status} without a result line;"
            f" if the user exists, this reveals its temporary password once and deletes it:\n"
            f"{REVEAL}\n"
        )
        assert PARAM in world.params()
        _assert_no_secret_escaped(world, result)
        if status == "InProgress":
            assert len(world.calls("sleep")) == 60, "it waits two minutes, then gives up"

    def test_ssm_refusing_the_put_sends_nothing(self, tmp_path: Path) -> None:
        world = _world(tmp_path, first_org=FIRST_ORG, FAKE_AWS_DENY="put-parameter")
        result = _run(world, _answers())
        assert result.returncode == 1
        assert result.stdout == ""
        assert "SSM did not store the temporary password" in result.stderr
        assert world.invocations() == {} and world.params() == {}
        _assert_no_secret_escaped(world, result)


# --- the scripts themselves ----------------------------------------------------------------------


def _shape(script: Path, name: str) -> str:
    (line,) = [
        ln for ln in script.read_text(encoding="utf-8").splitlines() if ln.startswith(f"{name}=")
    ]
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

    @pytest.mark.parametrize("name", ["USERNAME_SHAPE", "EMAIL_SHAPE", "ROLE_SHAPE"])
    def test_laptop_and_host_check_the_same_shapes(self, name: str) -> None:
        assert _shape(SCRIPT, name) == _shape(HOST_SCRIPT, name)

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
        for script, shapes in allowed.items():
            for line in script.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("#") or not re.search(
                    r"\$\{?(pw|admin_pw|tmp_pw)\b|\b(pw|admin_pw|tmp_pw)=", stripped
                ):
                    continue
                assert stripped.startswith(shapes), f"{script.name}: {stripped}"

    def test_the_put_is_a_secure_string_from_a_file_never_a_pipe(self) -> None:
        laptop = SCRIPT.read_text(encoding="utf-8")
        assert '--cli-input-json "file://$private/put.json"' in laptop
        assert "file:///dev/stdin" not in laptop and "--value" not in laptop
        assert '"Overwrite"' not in laptop, "a waiting password is never overwritten"


class TestRunbook:
    def test_it_points_to_the_one_command_and_keeps_the_manual_fallback(self) -> None:
        text = RUNBOOK.read_text(encoding="utf-8")
        assert "`scripts/ops/staff_user.sh`" in text
        assert "INT-538" in text
        assert "manual fallback" in text
        assert "kc create users" in text, "the manual steps stay"

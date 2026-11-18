"""INT-538: one laptop command creates a staff user on the synthetic staging host.

``scripts/ops/staff_user.sh`` runs on the owner's laptop. It prompts for a username, an email
and a role (``platform_owner`` or ``qms_owner``, nothing else). A read-only probe then asks the
host whether a platform_owner exists; only when none does is the user asked, once, for the
organisation id (a slug). It generates a temporary password straight into an SSM SecureString
and sends ``infra/staging/staff_user_host.sh`` base64-wrapped to the host over SSM. There, the
script logs kcadm in with a throwaway ``--config`` file, creates the user in the org, grants the
role, sets the password from SSM as temporary, and deletes the kcadm config whatever the outcome.

Every test here drives the real scripts against fakes on ``PATH``
(``tests/infra/staff_user_fakes.py``): ``aws`` keeps a parameter store and runs the
send-command text with ``sh``, ``docker`` plays the Keycloak container with kcadm in it,
``openssl`` returns a known value, ``sleep`` returns at once. Nothing reaches AWS or Docker.

What is held:

- **Prompts and validation.** Three prompts in order, a fourth only for the very first user. A
  role typo, a bad email, an empty or unsafe username, an org that is not a slug are refused
  before anything is generated, and the host re-checks every argument.
- **Secrets.** The temporary password and the bootstrap admin password never appear in any
  argv, in the send-command parameters, or in any output. Each reaches Keycloak on stdin.
- **The org rule.** A new user joins the platform_owner's org, is never asked for one, and an
  org argument that differs is refused. With no platform_owner, the first user must be the
  platform_owner, and the org is the slug typed once. No org is invented.
- **IAM.** A host that may not read the staff_tmp parameters refuses in one line that names the
  IAM statement to add, before anything is generated.
- **Refusals.** An existing username or email, a waiting temporary password, platform_owners
  that disagree, a failed step (rolled back) all refuse, and nothing is left behind.
- **The reveal command** shows the password once and deletes the parameter.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from staff_user_world import (
    BASH,
    BOOTSTRAP,
    EMAIL,
    FIRST_ORG,
    ORG_PROMPT,
    OWNER_ORG,
    PARAM,
    PROMPTS,
    REVEAL,
    RUNBOOK,
    TEMP_PASSWORD,
    USERNAME,
    World,
)
from staff_user_world import answers as _answers
from staff_user_world import assert_kcadm_config_deleted as _assert_kcadm_config_deleted
from staff_user_world import assert_no_secret_escaped as _assert_no_secret_escaped
from staff_user_world import assert_nothing_generated as _nothing_generated
from staff_user_world import host_commands as _host_commands
from staff_user_world import owner as _owner
from staff_user_world import run_laptop as _run
from staff_user_world import world as _world

# --- the happy path ------------------------------------------------------------------------------


class TestCreated:
    def test_the_first_platform_owner_is_created_in_the_org_typed_once(
        self, tmp_path: Path
    ) -> None:
        world = _world(tmp_path)
        result = _run(world, _answers())
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.stdout == f"created\n{REVEAL}\n"
        assert result.stderr == PROMPTS + ORG_PROMPT
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
        _assert_kcadm_config_deleted(world, sessions=2)

    def test_the_second_approver_joins_the_owners_org_and_is_never_asked(
        self, tmp_path: Path
    ) -> None:
        world = _world(tmp_path, users=[_owner()])
        # an org line typed anyway is never read
        result = _run(world, _answers("qa.approver", "qa.approver@example.org", "qms_owner"))
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.stderr == PROMPTS, "no org prompt once a platform_owner exists"
        user = world.user("qa.approver")
        assert user is not None
        assert user["attributes"] == {"org": [OWNER_ORG]}
        assert user["roles"] == ["qms_owner"]
        assert _host_commands(world)[1][-1] == "-", "no org travels"
        _assert_no_secret_escaped(world, result)
        _assert_kcadm_config_deleted(world, sessions=2)

    def test_the_email_is_stored_lower_case_and_never_printed(self, tmp_path: Path) -> None:
        world = _world(tmp_path)
        result = _run(world, _answers(email="Ada.Owner@Example.ORG"))
        assert result.returncode == 0, result.stdout + result.stderr
        user = world.user(USERNAME)
        assert user is not None and user["email"] == EMAIL
        assert "ada.owner@" not in result.stdout.lower() + result.stderr.lower()
        for record in world.invocations().values():
            assert EMAIL not in record["stdout"] + record["stderr"]

    def test_secrets_travel_on_stdin_only(self, tmp_path: Path) -> None:
        world = _world(tmp_path)
        _run(world, _answers())
        # the bootstrap password reaches each kcadm login (probe and create), and the temporary
        # password reaches reset-password, each on docker exec's stdin and nowhere else
        with_bootstrap = [c["argv"] for c in world.calls("docker") if BOOTSTRAP in c["stdin"]]
        with_temporary = [c["argv"] for c in world.calls("docker") if TEMP_PASSWORD in c["stdin"]]
        assert len(with_bootstrap) == 2
        for argv in with_bootstrap:
            assert argv[3:5] == ["bash", "-c"] and "config credentials" in argv[5]
        assert len(with_temporary) == 1 and with_temporary[0][4] == "update"
        assert with_temporary[0][5].endswith("/reset-password")
        assert [c["argv"] for c in world.calls("openssl")] == [["rand", "-hex", "32"]]


# --- the reveal command --------------------------------------------------------------------------


class TestReveal:
    # The owner pastes the reveal command into their own shell: zsh on macOS, bash or sh
    # elsewhere. It uses only POSIX sh, so bash and sh stand in for all three here.
    @pytest.mark.parametrize("shell", [BASH, "sh"])
    def test_it_shows_the_password_once_with_its_length_and_deletes_it(
        self, tmp_path: Path, shell: str
    ) -> None:
        world = _world(tmp_path)
        reveal = _run(world, _answers()).stdout.splitlines()[1]
        assert reveal == REVEAL
        first = subprocess.run(
            [shell, "-c", reveal], env=world.env, capture_output=True, text=True, check=False
        )
        assert first.returncode == 0, first.stderr
        assert first.stdout == f"{TEMP_PASSWORD}\npaste exactly; 64 characters\n"
        assert world.params() == {}
        again = subprocess.run(
            [shell, "-c", reveal], env=world.env, capture_output=True, text=True, check=False
        )
        assert again.stdout == "", "nothing to show twice"
        assert "ParameterNotFound" in again.stderr

    def test_the_revealed_line_is_exactly_what_keycloak_stored(self, tmp_path: Path) -> None:
        # INT-538 round 3: the owner's first sign-in failed. The value typed at the console
        # must be byte-for-byte the stored credential: no newline, no space, nothing else.
        world = _world(tmp_path)
        reveal = _run(world, _answers()).stdout.splitlines()[1]
        shown = subprocess.run(
            [BASH, "-c", reveal], env=world.env, capture_output=True, text=True, check=False
        ).stdout
        value, length_line, rest = shown.split("\n", 2)
        user = world.user(USERNAME)
        assert user is not None
        assert value == user["credential"]["value"]
        assert value == value.strip() and len(value) == 64
        assert length_line == "paste exactly; 64 characters" and rest == ""
        assert user["credential"]["temporary"] is True

    def test_near_miss_a_value_of_another_length_says_its_real_length(self, tmp_path: Path) -> None:
        world = _world(tmp_path, params={PARAM: {"Type": "SecureString", "Value": "abc"}})
        shown = subprocess.run(
            [BASH, "-c", REVEAL], env=world.env, capture_output=True, text=True, check=False
        )
        assert shown.stdout == "abc\npaste exactly; 3 characters\n"


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

ORG_NEAR_MISSES = [
    pytest.param("", id="empty"),
    pytest.param("i", id="one-character"),
    pytest.param("o" * 41, id="forty-one-characters"),
    pytest.param("Intake-Ops", id="capitals"),
    pytest.param("org:intake", id="colon"),
    pytest.param("intake_ops", id="underscore"),
    pytest.param("intake.ops", id="dot"),
    pytest.param("intake ops", id="space"),
    pytest.param("-intake", id="leading-hyphen"),
    pytest.param("intake-", id="trailing-hyphen"),
    pytest.param("intåke", id="non-ascii"),
    pytest.param("intake'", id="quote"),
]


class TestValidation:
    @pytest.mark.parametrize(("answers", "field"), NEAR_MISSES)
    def test_a_near_miss_is_refused_before_any_call(
        self, tmp_path: Path, answers: str, field: str
    ) -> None:
        world = _world(tmp_path)
        result = _run(world, answers)
        assert result.returncode == 2, result.stdout + result.stderr
        assert result.stdout == ""
        assert f"staff_user: the {field}" in result.stderr
        assert world.calls() == [], "nothing generated, nothing sent"
        assert world.realm()["users"] == []

    @pytest.mark.parametrize("org", ORG_NEAR_MISSES)
    def test_an_org_that_is_not_a_slug_is_refused_before_anything_is_made(
        self, tmp_path: Path, org: str
    ) -> None:
        world = _world(tmp_path)
        result = _run(world, _answers(org=org))
        assert result.returncode == 2, result.stdout + result.stderr
        assert result.stdout == ""
        assert result.stderr.startswith(PROMPTS + ORG_PROMPT + "staff_user: the organisation id")
        _nothing_generated(world)
        assert world.realm()["users"] == []

    @pytest.mark.parametrize("org", ["ab", "o" * 40, "intake-ops-2"], ids=["two", "forty", "mixed"])
    def test_near_miss_a_slug_at_the_edges_is_accepted(self, tmp_path: Path, org: str) -> None:
        world = _world(tmp_path)
        assert _run(world, _answers(org=org)).returncode == 0
        user = world.user(USERNAME)
        assert user is not None and user["attributes"] == {"org": [org]}

    def test_the_prompts_come_in_order_and_stop_at_the_first_bad_answer(
        self, tmp_path: Path
    ) -> None:
        world = _world(tmp_path)
        result = _run(world, _answers(username="Ada"))
        assert result.stderr.startswith("username: staff_user: the username")
        assert "email: " not in result.stderr

    def test_arguments_are_refused(self, tmp_path: Path) -> None:
        world = _world(tmp_path)
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
        world = _world(tmp_path, **override)
        result = _run(world, _answers())
        assert result.returncode == 2 and result.stderr.startswith("staff_user: ")
        assert world.calls() == []


# --- refusals ------------------------------------------------------------------------------------


def _refused(world: World, answers: str) -> str:
    result = _run(world, answers)
    assert result.returncode == 3, result.stdout + result.stderr
    assert result.stdout.startswith("refused: ")
    _assert_no_secret_escaped(world, result)
    return result.stdout


class TestRefusals:
    def test_an_existing_username_is_refused(self, tmp_path: Path) -> None:
        existing = _owner(username=USERNAME, uid="2222")
        world = _world(tmp_path, users=[existing])
        out = _refused(world, _answers(org=None))
        assert out == (
            f"refused: the username {USERNAME} already exists in realm intake;"
            f" to issue a new temporary password, use --reset {USERNAME}\n"
        )
        assert world.realm()["users"] == [existing], "nothing created or changed"
        assert world.params() == {}, "the unused temporary password is deleted"
        _assert_kcadm_config_deleted(world, sessions=2)

    def test_an_existing_email_is_refused(self, tmp_path: Path) -> None:
        existing = _owner(username="other.person", uid="2222")
        existing["email"] = EMAIL
        world = _world(tmp_path, users=[existing])
        out = _refused(world, _answers(org=None))
        assert out == "refused: that email already belongs to a user in realm intake\n"
        assert world.realm()["users"] == [existing] and world.params() == {}
        _assert_kcadm_config_deleted(world, sessions=2)

    def test_platform_owners_in_two_orgs_are_refused_by_the_probe(self, tmp_path: Path) -> None:
        owners = [_owner(), _owner("org:another", username="second.owner", uid="3333")]
        world = _world(tmp_path, users=owners)
        out = _refused(world, _answers(org=None))
        assert out == "refused: the platform_owners do not share one org\n"
        assert world.realm()["users"] == owners
        _nothing_generated(world)

    def test_a_platform_owner_without_an_org_is_refused(self, tmp_path: Path) -> None:
        owner = _owner()
        owner["attributes"] = {}
        world = _world(tmp_path, users=[owner])
        assert _refused(world, _answers(org=None)) == (
            "refused: a platform_owner has no org attribute\n"
        )
        _nothing_generated(world)

    def test_a_waiting_temporary_password_is_never_overwritten(self, tmp_path: Path) -> None:
        waiting = {PARAM: {"Type": "SecureString", "Value": "earlier-value-not-revealed"}}
        world = _world(tmp_path, params=waiting)
        result = _run(world, _answers())
        assert result.returncode == 3
        assert result.stdout == (
            f"refused: a temporary password for {USERNAME} is still waiting in SSM;"
            f" reveal it (which deletes it) first:\n{REVEAL}\n"
        )
        assert world.params() == waiting
        assert len(world.invocations()) == 1, "only the probe ran"
        assert world.realm()["users"] == []

    @pytest.mark.parametrize("step", ["add-roles", "update"])
    def test_a_failed_step_after_creation_is_rolled_back(self, tmp_path: Path, step: str) -> None:
        world = _world(tmp_path, fail=step)
        out = _refused(world, _answers())
        assert out.endswith("; the user was removed again\n")
        assert world.realm()["users"] == [] and world.params() == {}
        _assert_kcadm_config_deleted(world, sessions=2)

    def test_keycloak_refusing_the_create_is_refused(self, tmp_path: Path) -> None:
        world = _world(tmp_path, fail="create")
        assert _refused(world, _answers()) == "refused: Keycloak did not create the user\n"
        _assert_kcadm_config_deleted(world, sessions=2)

    def test_a_wrong_bootstrap_password_is_refused_and_its_config_deleted(
        self, tmp_path: Path
    ) -> None:
        wrong = hashlib.sha256(b"INT-538 some other value, test only").hexdigest()
        world = _world(tmp_path, env_password=wrong)
        assert _refused(world, _answers()) == (
            "refused: kcadm could not log in as the bootstrap admin\n"
        )
        assert wrong not in json.dumps([c["argv"] for c in world.calls()])
        _nothing_generated(world)
        _assert_kcadm_config_deleted(world)

    @pytest.mark.parametrize(
        "value",
        [None, "", "not-generated", BOOTSTRAP[:-1]],
        ids=["absent", "empty", "not-generated", "one-hex-short"],
    )
    def test_an_unreadable_bootstrap_password_stops_before_docker(
        self, tmp_path: Path, value: str | None
    ) -> None:
        world = _world(tmp_path, env_password=value)
        assert _refused(world, _answers()) == (
            "refused: KEYCLOAK_ADMIN_PASSWORD is not readable in the host's env file\n"
        )
        assert world.calls("docker") == []
        _nothing_generated(world)

    def test_a_stopped_keycloak_container_is_refused(self, tmp_path: Path) -> None:
        world = _world(tmp_path, FAKE_CONTAINER_NAME="another-container")
        assert _refused(world, _answers()) == (
            "refused: the Keycloak container intake-staging-keycloak-1 is not running\n"
        )
        _nothing_generated(world)


# --- outcomes the laptop cannot read -------------------------------------------------------------


class TestUnclearOutcomes:
    @pytest.mark.parametrize("status", ["InProgress", "Failed"])
    def test_an_unanswered_create_keeps_the_parameter_and_says_so(
        self, tmp_path: Path, status: str
    ) -> None:
        world = _world(tmp_path, FAKE_HOST=f"run,{status}")
        result = _run(world, _answers())
        assert result.returncode == 1
        assert result.stdout == (
            f"unknown: host command cmd-0002 ended {status} without a result line;"
            f" if the user exists, this reveals its temporary password once and deletes it:\n"
            f"{REVEAL}\n"
        )
        assert PARAM in world.params()
        _assert_no_secret_escaped(world, result)
        if status == "InProgress":
            assert len(world.calls("sleep")) == 60, "it waits two minutes, then gives up"

    def test_an_unanswered_probe_makes_nothing(self, tmp_path: Path) -> None:
        world = _world(tmp_path, FAKE_HOST="InProgress")
        result = _run(world, _answers())
        assert result.returncode == 1
        assert result.stdout == (
            "unknown: probe command cmd-0001 ended InProgress without a result line;"
            " nothing was created\n"
        )
        _nothing_generated(world)

    def test_ssm_refusing_the_put_sends_no_create(self, tmp_path: Path) -> None:
        world = _world(tmp_path, FAKE_AWS_DENY="put-parameter")
        result = _run(world, _answers())
        assert result.returncode == 1
        assert result.stdout == ""
        assert "SSM did not store the temporary password" in result.stderr
        assert len(world.invocations()) == 1 and world.params() == {}
        _assert_no_secret_escaped(world, result)


class TestRunbook:
    def test_it_points_to_the_one_command_and_keeps_the_manual_fallback(self) -> None:
        text = RUNBOOK.read_text(encoding="utf-8")
        assert "`scripts/ops/staff_user.sh`" in text
        assert "INT-538" in text
        assert "organisation id" in text
        assert "manual fallback" in text
        assert "kc create users" in text, "the manual steps stay"

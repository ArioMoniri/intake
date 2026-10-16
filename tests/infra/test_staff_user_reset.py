"""INT-538 round 3: `scripts/ops/staff_user.sh --reset <username>`.

The owner's first sign-in failed after the temporary password had been revealed, and so
deleted, and the create path refuses an existing username. ``--reset`` re-issues: it puts a new
temporary password into ``/intake/staging/staff_tmp/<username>`` under the create path's rules
(never an argv, never echoed, never overwriting a waiting one). On the host it sets the
password from stdin with ``temporary=true`` and the required actions ``webauthn-register`` and
``UPDATE_PASSWORD`` again. It refuses an unknown user and changes nothing else about the
account. It prints only ``reset`` and the one-time reveal command.

The tests run against the fakes of ``tests/infra/staff_user_fakes.py``, as in
``test_staff_user.py``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
from staff_user_world import (
    BASH,
    PARAM,
    REVEAL,
    TEMP_PASSWORD,
    USERNAME,
    World,
    revealed,
)
from staff_user_world import assert_kcadm_config_deleted as _assert_kcadm_config_deleted
from staff_user_world import assert_no_secret_escaped as _assert_no_secret_escaped
from staff_user_world import host_commands as _host_commands
from staff_user_world import owner as _owner
from staff_user_world import run_host as _host
from staff_user_world import run_laptop as _run
from staff_user_world import seeded as _seeded
from staff_user_world import world as _world

OLD_CREDENTIAL = {"type": "password", "temporary": True, "value": "an-earlier-value-test-only"}
IAM_REFUSAL_START = "refused: the instance role intake-staging-host may not read"


def _existing() -> dict[str, Any]:
    """The owner's account as round 2 created it: an org, the role, a password, no key yet."""
    user = _owner(username=USERNAME, uid="2222")
    user.update(
        enabled=True,
        emailVerified=True,
        requiredActions=[],
        credential=OLD_CREDENTIAL,
    )
    return user


def _reset(world: World, *args: str) -> subprocess.CompletedProcess[str]:
    # stdin carries an answer that must never be read: --reset never prompts
    return _run(world, "should-never-be-read\n", "--reset", *(args or (USERNAME,)))


class TestReset:
    def test_it_issues_a_new_temporary_password_and_the_two_required_actions(
        self, tmp_path: Path
    ) -> None:
        world = _world(tmp_path, users=[_existing()])
        result = _reset(world)
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.stdout == f"reset\n{REVEAL}\n"
        assert result.stderr == "", "no prompt"
        user = world.user(USERNAME)
        assert user is not None
        assert user["credential"] == {"type": "password", "temporary": True, "value": TEMP_PASSWORD}
        assert user["requiredActions"] == ["webauthn-register", "UPDATE_PASSWORD"]
        # nothing else about the account changes
        unchanged = {
            k: v for k, v in _existing().items() if k not in ("credential", "requiredActions")
        }
        assert {k: user[k] for k in unchanged} == unchanged
        assert world.params() == {PARAM: {"Type": "SecureString", "Value": TEMP_PASSWORD}}
        assert _host_commands(world) == [["reset", USERNAME, PARAM, "us-east-1"]]
        _assert_no_secret_escaped(world, result)
        _assert_kcadm_config_deleted(world)

    @pytest.mark.parametrize("shell", [BASH, "sh"])
    def test_the_reveal_shows_exactly_the_stored_value_once(
        self, tmp_path: Path, shell: str
    ) -> None:
        world = _world(tmp_path, users=[_existing()])
        reveal = _reset(world).stdout.splitlines()[1]
        shown = subprocess.run(
            [shell, "-c", reveal], env=world.env, capture_output=True, text=True, check=False
        )
        user = world.user(USERNAME)
        assert user is not None
        assert shown.stdout == revealed(user["credential"]["value"])
        assert world.params() == {}

    def test_the_new_password_travels_on_stdin_only(self, tmp_path: Path) -> None:
        world = _world(tmp_path, users=[_existing()])
        _reset(world)
        carrying = [c["argv"] for c in world.calls("docker") if TEMP_PASSWORD in c["stdin"]]
        assert len(carrying) == 1 and carrying[0][5] == "users/2222/reset-password"
        assert [c["argv"] for c in world.calls("openssl")] == [["rand", "-hex", "32"]]


class TestResetRefusals:
    def test_an_unknown_user_is_refused_and_the_parameter_deleted(self, tmp_path: Path) -> None:
        other = _owner(username="someone.else", uid="3333")
        world = _world(tmp_path, users=[other])
        result = _reset(world)
        assert result.returncode == 3
        assert result.stdout == f"refused: no user named {USERNAME} in realm intake\n"
        assert world.realm()["users"] == [other], "nobody is created by a reset"
        assert world.params() == {}
        _assert_no_secret_escaped(world, result)
        _assert_kcadm_config_deleted(world)

    @pytest.mark.parametrize(
        "args",
        [
            pytest.param([], id="no-username"),
            pytest.param(["Ada.Owner"], id="capitals"),
            pytest.param(["ada owner"], id="space"),
            pytest.param(["ad"], id="too-short"),
            pytest.param(["ada.owner", "second.user"], id="two-usernames"),
            pytest.param(["--reset"], id="flag-twice"),
        ],
    )
    def test_a_malformed_reset_is_refused_before_any_call(
        self, tmp_path: Path, args: list[str]
    ) -> None:
        world = _world(tmp_path, users=[_existing()])
        result = _run(world, "", "--reset", *args)
        assert result.returncode == 2 and result.stdout == ""
        assert result.stderr.startswith("staff_user: ")
        assert world.calls() == []

    @pytest.mark.parametrize("flag", ["--rest", "-reset", "reset", "--RESET"])
    def test_near_miss_a_mistyped_flag_is_refused_before_any_call(
        self, tmp_path: Path, flag: str
    ) -> None:
        world = _world(tmp_path, users=[_existing()])
        result = _run(world, "", flag, USERNAME)
        assert result.returncode == 2 and world.calls() == []

    def test_a_waiting_temporary_password_is_never_overwritten(self, tmp_path: Path) -> None:
        waiting = {PARAM: {"Type": "SecureString", "Value": "earlier-value-not-revealed"}}
        world = _world(tmp_path, users=[_existing()], params=waiting)
        result = _reset(world)
        assert result.returncode == 3
        assert result.stdout == (
            f"refused: a temporary password for {USERNAME} is still waiting in SSM;"
            f" reveal it (which deletes it) first:\n{REVEAL}\n"
        )
        assert world.params() == waiting and world.invocations() == {}
        user = world.user(USERNAME)
        assert user is not None and user["credential"] == OLD_CREDENTIAL

    def test_a_failed_required_action_update_leaves_the_old_password(self, tmp_path: Path) -> None:
        world = _world(tmp_path, users=[_existing()], fail="update")
        result = _reset(world)
        assert result.stdout == (
            "refused: the required actions could not be set; the password was not changed\n"
        )
        user = world.user(USERNAME)
        assert user is not None and user["credential"] == OLD_CREDENTIAL
        assert world.params() == {}
        _assert_kcadm_config_deleted(world)

    def test_a_failed_password_set_says_the_old_one_stands(self, tmp_path: Path) -> None:
        world = _world(tmp_path, users=[_existing()], fail="reset-password")
        result = _reset(world)
        assert result.stdout == (
            "refused: the temporary password could not be set; the old password still stands\n"
        )
        user = world.user(USERNAME)
        assert user is not None and user["credential"] == OLD_CREDENTIAL
        assert world.params() == {}
        _assert_no_secret_escaped(world, result)

    def test_an_instance_role_without_the_read_is_named(self, tmp_path: Path) -> None:
        world = _world(tmp_path, users=[_existing()], FAKE_ROLE_DENY="1")
        result = _reset(world)
        assert result.returncode == 3 and result.stdout.startswith(IAM_REFUSAL_START)
        assert world.params() == {} and world.calls("docker") == []
        user = world.user(USERNAME)
        assert user is not None and user["credential"] == OLD_CREDENTIAL

    def test_an_unanswered_reset_keeps_the_parameter_and_says_so(self, tmp_path: Path) -> None:
        world = _world(tmp_path, users=[_existing()], FAKE_HOST="Failed")
        result = _reset(world)
        assert result.returncode == 1
        assert result.stdout == (
            "unknown: host command cmd-0001 ended Failed without a result line;"
            " if the user exists, this reveals its temporary password once and deletes it:\n"
            f"{REVEAL}\n"
        )
        assert PARAM in world.params()


class TestHostReset:
    @pytest.mark.parametrize(
        "args",
        [
            pytest.param(
                ["reset", "Ada", f"/intake/staging/staff_tmp/{USERNAME}", "us-east-1"],
                id="username",
            ),
            pytest.param(
                ["reset", USERNAME, "/intake/staging/staff_tmp/someone.else", "us-east-1"],
                id="parameter-of-another",
            ),
            pytest.param(["reset", USERNAME, PARAM, "us-east-1;id"], id="region"),
            pytest.param(["reset", USERNAME, PARAM], id="missing-region"),
        ],
    )
    def test_the_host_rechecks_every_reset_argument(self, tmp_path: Path, args: list[str]) -> None:
        world = _world(tmp_path, users=[_existing()])
        result = _host(world, *args)
        assert result.returncode == 3 and result.stdout.startswith("staff_user: refused: ")
        assert world.calls() == []

    def test_the_host_reset_alone(self, tmp_path: Path) -> None:
        world = _seeded(tmp_path, users=[_existing()])
        result = _host(world, "reset", USERNAME, PARAM, "us-east-1")
        assert result.stdout == "staff_user: reset\n"
        user = world.user(USERNAME)
        assert user is not None and user["credential"]["value"] == TEMP_PASSWORD
        _assert_kcadm_config_deleted(world)

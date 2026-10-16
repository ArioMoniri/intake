"""INT-460: a second admin approver on the synthetic staging host.

The owner asked for a real second person who can approve model-lane switches.
``docs/runbooks/second-admin.md`` answers with a second Keycloak user, not a
second dev bearer. These tests hold the facts that answer rests on:

- **The dev tier is not the route.** ``/admin`` admits only a verified
  Keycloak token (INT-180), and a dev bearer is not one. Outside dev, any
  ``INTAKE_DEV_*`` variable refuses the boot (INT-325), a second admin token
  included, so adding one to the staging env stops the API instead of
  admitting anybody.
- **Four eyes holds with two staff in one organisation.** Two principals that
  differ in ``sub``, WebAuthn credential and session approve each other's
  tier-2 request, and neither approves their own. The ceremony used is the
  deploy-freeze lift, which is on this tree and has the model-lane
  ceremonies' shape: same requesters, same-organisation approval allowed.
- **The runbook stays honest.** It is at most 15 lines and names the INT-378
  provider (#643) as the prerequisite. Without that provider the console
  refuses every staff token, which ``test_realm_claim_mappers.py`` holds. It
  grants only roles that stand as a second key, names no dev variable, and
  creates, hands over and deletes the one-time password under one parameter.
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Iterator, Mapping
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from admin_harness import build_admin_harness, recorded_claims
from api_harness import ADMIN_TOKEN, ApiHarness
from intake_api.settings import (
    DEV_FLAG_PREFIX,
    NON_DEV_REQUIRED_CREDENTIALS,
    DevConfigRefusedError,
    refuse_dev_config_outside_dev,
)
from intake_platform.admin.actions import DANGEROUS_ACTIONS, DEPLOY_FREEZE_LIFT, ActionTier
from intake_platform.admin.four_eyes import FourEyesService, Justification, SelfApproval
from intake_platform.admin.principal import AdminPrincipal, principal_from_claims
from intake_platform.admin.roles import AdminRole

REPO = Path(__file__).resolve().parents[2]
RUNBOOK = REPO / "docs" / "runbooks" / "second-admin.md"
SOURCE_IP = "192.0.2.10"
#: A second admin token, as the rejected design would have named it.
SECOND_DEV_ADMIN = DEV_FLAG_PREFIX + "TOKEN_ADMIN_2"


@pytest.fixture
def admin_harness(tmp_path: Path) -> Iterator[ApiHarness]:
    yield from build_admin_harness(tmp_path)


def _principal(account: str, **overrides: str) -> AdminPrincipal:
    claims: Mapping[str, Any] = {**recorded_claims()[account], **overrides}
    return principal_from_claims(claims, source_ip=SOURCE_IP)


def _owner() -> AdminPrincipal:
    return _principal("kc:platform_owner")


def _second_owner() -> AdminPrincipal:
    """The second person: their own subject, WebAuthn credential and session."""
    return _principal(
        "kc:platform_owner",
        sub="kc-sub-platform-owner-2",
        sid="sid-platform-owner-2",
        credential_id="cred-platform-owner-0002",
    )


def _request(service: FourEyesService, requester: AdminPrincipal) -> str:
    pending = service.open(
        action=DEPLOY_FREEZE_LIFT,
        actor=requester.actor_block(AdminRole.PLATFORM_OWNER),
        target_ref="release:int460",
        justification=Justification(
            reason_class="release_ready", free_text="", controller_instruction_ref=None
        ),
        evidence={"release": "int460"},
        ttl=timedelta(minutes=15),
    )
    return pending.id


def _runbook() -> str:
    return RUNBOOK.read_text(encoding="utf-8")


class TestTheDevTierIsNotTheRoute:
    def test_a_dev_bearer_does_not_open_the_console(self, admin_harness: ApiHarness) -> None:
        response = admin_harness.client.get(
            "/admin/whoami", headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}
        )
        assert response.status_code == 401

    @pytest.mark.parametrize("environment", ["staging", "production"])
    def test_a_second_dev_admin_token_refuses_a_non_dev_boot(self, environment: str) -> None:
        value = secrets.token_hex(32)
        environ = {name: "set" for name in NON_DEV_REQUIRED_CREDENTIALS}
        environ |= {"INTAKE_ENV": environment, SECOND_DEV_ADMIN: value}
        with pytest.raises(DevConfigRefusedError) as refused:
            refuse_dev_config_outside_dev(environ)
        assert SECOND_DEV_ADMIN in str(refused.value)
        assert value not in str(refused.value)

    def test_near_miss_without_the_dev_variable_the_staging_boot_proceeds(self) -> None:
        environ = {name: "set" for name in NON_DEV_REQUIRED_CREDENTIALS}
        environ |= {"INTAKE_ENV": "staging"}
        refuse_dev_config_outside_dev(environ)


class TestFourEyesWithTwoStaffInOneOrganisation:
    def test_the_two_staff_share_one_organisation(self) -> None:
        assert _owner().org == _second_owner().org
        assert DEPLOY_FREEZE_LIFT.approver_must_differ_org is False

    def test_each_approves_the_others_request(self) -> None:
        service = FourEyesService()
        owner, second = _owner(), _second_owner()
        first = service.approve(
            _request(service, owner),
            approver=second.actor_block(AdminRole.PLATFORM_OWNER),
            assertion_id="assert-int460-1",
        )
        reverse = service.approve(
            _request(service, second),
            approver=owner.actor_block(AdminRole.PLATFORM_OWNER),
            assertion_id="assert-int460-2",
        )
        assert first.approver is not None and first.approver.subject == second.subject
        assert reverse.approver is not None and reverse.approver.subject == owner.subject

    def test_a_qms_owner_approves_the_owners_request(self) -> None:
        service = FourEyesService()
        qms = _principal("kc:qms_owner")
        approved = service.approve(
            _request(service, _owner()),
            approver=qms.actor_block(AdminRole.QMS_OWNER),
            assertion_id="assert-int460-3",
        )
        assert approved.approver is not None and approved.approver.subject == qms.subject

    @pytest.mark.parametrize("person", [_owner, _second_owner])
    def test_nobody_approves_their_own_request(self, person: Any) -> None:
        service = FourEyesService()
        principal: AdminPrincipal = person()
        action_id = _request(service, principal)
        with pytest.raises(SelfApproval):
            service.approve(
                action_id,
                approver=principal.actor_block(AdminRole.PLATFORM_OWNER),
                assertion_id="assert-int460-4",
            )


class TestTheRunbook:
    def test_it_fits_in_fifteen_lines(self) -> None:
        assert len(_runbook().splitlines()) <= 15

    def test_it_names_the_provider_prerequisite(self) -> None:
        text = _runbook()
        assert "INT-378" in text
        assert "#643" in text

    def test_every_role_it_grants_stands_as_a_second_key(self) -> None:
        granted = re.findall(r"--rolename (\w+)", _runbook())
        second_keys = {
            role
            for action in DANGEROUS_ACTIONS.values()
            if action.tier is ActionTier.T2
            for role in action.approver_roles
        }
        assert granted
        for name in granted:
            assert AdminRole(name) in second_keys

    def test_it_names_no_dev_variable(self) -> None:
        assert DEV_FLAG_PREFIX not in _runbook()

    def test_the_one_time_password_lives_under_one_parameter(self) -> None:
        text = _runbook()
        names = set(re.findall(r"--name (/intake/staging/\S+)", text))
        assert len(names) == 1
        (name,) = names
        for verb in ("put-parameter", "get-parameter", "delete-parameter"):
            assert re.search(rf"aws ssm {verb} --name {re.escape(name)}", text), verb

    def test_the_password_is_generated_never_typed(self) -> None:
        put = next(line for line in _runbook().splitlines() if "put-parameter" in line)
        assert "--type SecureString" in put
        assert '--value "$(openssl rand -hex 32)"' in put

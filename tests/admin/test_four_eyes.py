"""INT-180 — the four-eyes primitives, the break-glass ceremony, the IP gate.

What four-eyes covers is a property, not a screen, and this suite states both
halves of it. It **covers**: a distinct account, a distinct WebAuthn
credential, a distinct browser session, a fresh single-use assertion, an
eligible approver role, a distinct organisation at tier 3, and an expiry. It
**does not cover** two accounts held by one person — the last test in
:class:`TestWhatFourEyesDoesNotCover` asserts that the mechanism accepts it,
because writing the limit down as a passing test is the only way it stays
visible when someone later reads the ceremony as proof of two humans.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from intake_platform.admin import (
    ActionDirection,
    ActionTier,
    ActorBlock,
    BreakGlassReason,
    DangerousAction,
    Deployment,
    FourEyesService,
    IpAllowList,
)
from intake_platform.admin.actions import BREAK_GLASS_OPEN
from intake_platform.admin.break_glass import (
    BREAK_GLASS_GRANT_TTL,
    MIN_JUSTIFICATION_CHARS,
    BreakGlassRefused,
    build_break_glass_justification,
)
from intake_platform.admin.four_eyes import (
    ApproverRoleIneligible,
    AssertionReused,
    FourEyesRefused,
    PendingActionDecided,
    PendingActionExpired,
    SelfApproval,
    SharedCredential,
    SharedOrganisation,
    SharedSession,
    UnknownPendingAction,
)
from intake_platform.admin.roles import AdminRole

T0 = datetime(2026, 9, 3, 9, 0, tzinfo=UTC)

ACTOR = ActorBlock(
    subject="kc-sub-clinical-lead",
    role=AdminRole.CLINICAL_LEAD,
    org="org:intake",
    authenticator_aaguid="00000000-0000-0000-0000-000000000000",
    credential_id="cred-clinical-lead-1",
    session_id="sid-clinical-lead-1",
)
APPROVER = ActorBlock(
    subject="kc-sub-qms-owner",
    role=AdminRole.QMS_OWNER,
    org="org:intake",
    authenticator_aaguid="00000000-0000-0000-0000-000000000000",
    credential_id="cred-qms-owner-1",
    session_id="sid-qms-owner-1",
)
JUSTIFICATION = build_break_glass_justification(
    reason_class=BreakGlassReason.PATIENT_SUPPORT_REQUEST,
    free_text="Patient opened a support ticket about a missing note.",
    controller_instruction_ref="ci:tenant-a:2026-09-03:01",
    deployment=Deployment.PROCESSOR,
)

#: A tier-3 action built here, not registered: files/08 §8.2's tier-3 rows all
#: belong to surfaces this issue does not route, and a registry row with no
#: code behind it would be a fabricated control (invariant 17).
TIER3 = DangerousAction(
    id="admin.test.tier3",
    tier=ActionTier.T3,
    direction=ActionDirection.DANGEROUS,
    actor_roles=frozenset({AdminRole.PLATFORM_OWNER}),
    approver_roles=frozenset({AdminRole.QMS_OWNER}),
    approver_must_differ_org=True,
    runbook="docs/runbooks/break-glass.md",
    alert_metric="admin.four_eyes_self_approval_attempt_total",
)


class Clock:
    def __init__(self, now: datetime = T0) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def service(clock: Clock | None = None) -> FourEyesService:
    return FourEyesService(clock=clock if clock is not None else Clock())


def opened(svc: FourEyesService, action: DangerousAction = BREAK_GLASS_OPEN):  # type: ignore[no-untyped-def]
    return svc.open(
        action=action,
        actor=ACTOR if action is BREAK_GLASS_OPEN else ACTOR.replace_role(AdminRole.PLATFORM_OWNER),
        target_ref="session:0f8a1c2d-4b5e-4a6f-9c31-2d4e6f8a1c2d",
        justification=JUSTIFICATION,
        evidence={"tenant": "tenant-a"},
        ttl=BREAK_GLASS_GRANT_TTL,
    )


class TestApprovalBrief:
    def test_the_brief_carries_enough_to_disagree(self) -> None:
        svc = service()
        pending = opened(svc)
        brief = svc.brief(pending.id)
        assert brief.action_id == pending.id
        assert brief.dangerous_action_id == BREAK_GLASS_OPEN.id
        assert brief.tier is ActionTier.T2
        assert brief.requested_by == ACTOR
        assert brief.target_ref == "session:0f8a1c2d-4b5e-4a6f-9c31-2d4e6f8a1c2d"
        assert brief.reason_class is BreakGlassReason.PATIENT_SUPPORT_REQUEST
        # the free text is the whole point: an approver shown only "Approve?"
        # cannot disagree with anything
        assert brief.free_text == JUSTIFICATION.free_text
        assert brief.controller_instruction_ref == "ci:tenant-a:2026-09-03:01"
        assert brief.evidence == {"tenant": "tenant-a"}
        assert brief.expires_at > brief.created_at
        assert brief.approver_rule

    def test_an_unknown_action_has_no_brief(self) -> None:
        with pytest.raises(UnknownPendingAction):
            service().brief("0" * 32)


class TestDistinctness:
    def test_self_approval_is_refused(self) -> None:
        svc = service()
        pending = opened(svc)
        with pytest.raises(SelfApproval) as caught:
            svc.approve(pending.id, approver=ACTOR, assertion_id="assn-1")
        assert caught.value.code == "four_eyes_self_approval"

    def test_a_shared_credential_is_refused(self) -> None:
        svc = service()
        pending = opened(svc)
        twin = APPROVER.replace_credential(ACTOR.credential_id)
        with pytest.raises(SharedCredential):
            svc.approve(pending.id, approver=twin, assertion_id="assn-1")

    def test_a_shared_session_is_refused(self) -> None:
        svc = service()
        pending = opened(svc)
        twin = APPROVER.replace_session(ACTOR.session_id)
        with pytest.raises(SharedSession):
            svc.approve(pending.id, approver=twin, assertion_id="assn-1")

    def test_a_shared_authenticator_model_is_not_a_refusal(self) -> None:
        # two people may hold the same MODEL of security key; the AAGUID is a
        # vendor id, so only the credential id distinguishes the authenticator
        svc = service()
        pending = opened(svc)
        assert APPROVER.authenticator_aaguid == ACTOR.authenticator_aaguid
        assert svc.approve(pending.id, approver=APPROVER, assertion_id="assn-1").approver

    def test_an_ineligible_approver_role_is_refused(self) -> None:
        svc = service()
        pending = opened(svc)
        outsider = APPROVER.replace_role(AdminRole.RESEARCHER)
        with pytest.raises(ApproverRoleIneligible):
            svc.approve(pending.id, approver=outsider, assertion_id="assn-1")

    def test_tier3_demands_a_different_organisation_and_tier2_does_not(self) -> None:
        svc = service()
        tier3 = opened(svc, TIER3)
        with pytest.raises(SharedOrganisation):
            svc.approve(tier3.id, approver=APPROVER, assertion_id="assn-1")
        external = APPROVER.replace_org("org:notified-body")
        assert svc.approve(tier3.id, approver=external, assertion_id="assn-2").approver == external


class TestSingleUseAndExpiry:
    def test_an_assertion_is_single_use_across_the_service(self) -> None:
        svc = service()
        first = opened(svc)
        second = opened(svc)
        svc.approve(first.id, approver=APPROVER, assertion_id="assn-1")
        with pytest.raises(AssertionReused):
            svc.approve(second.id, approver=APPROVER, assertion_id="assn-1")

    def test_an_approved_action_cannot_be_approved_again(self) -> None:
        svc = service()
        pending = opened(svc)
        svc.approve(pending.id, approver=APPROVER, assertion_id="assn-1")
        with pytest.raises(PendingActionDecided):
            svc.approve(pending.id, approver=APPROVER, assertion_id="assn-2")

    def test_an_expired_action_cannot_be_approved(self) -> None:
        clock = Clock()
        svc = service(clock)
        pending = opened(svc)
        clock.now = T0 + BREAK_GLASS_GRANT_TTL + timedelta(seconds=1)
        with pytest.raises(PendingActionExpired):
            svc.approve(pending.id, approver=APPROVER, assertion_id="assn-1")

    def test_expire_due_sweeps_and_counts(self) -> None:
        clock = Clock()
        svc = service(clock)
        opened(svc)
        opened(svc)
        assert svc.expire_due() == 0
        clock.now = T0 + BREAK_GLASS_GRANT_TTL + timedelta(seconds=1)
        assert svc.expire_due() == 2
        assert svc.expire_due() == 0


class TestWhatFourEyesDoesNotCover:
    def test_two_accounts_held_by_one_person_are_accepted(self) -> None:
        """The honest limit, asserted rather than implied.

        Distinct sub, distinct credential, distinct session — every check the
        ceremony can make passes, and nothing in an OIDC claim set says the
        two accounts are two people. Closing this needs an out-of-band
        control (HR identity proofing, or an approver pool the actor cannot
        enrol into), not another field.
        """
        svc = service()
        pending = opened(svc)
        alter_ego = ActorBlock(
            subject="kc-sub-clinical-lead-alt",
            role=AdminRole.CLINICAL_LEAD,
            org=ACTOR.org,
            authenticator_aaguid=ACTOR.authenticator_aaguid,
            credential_id="cred-clinical-lead-2",
            session_id="sid-clinical-lead-2",
        )
        assert svc.approve(pending.id, approver=alter_ego, assertion_id="assn-1").approver


class TestBreakGlassJustification:
    def test_a_reason_outside_the_closed_set_is_not_constructible(self) -> None:
        with pytest.raises(ValueError):
            BreakGlassReason("curiosity")

    def test_free_text_below_the_floor_is_refused(self) -> None:
        with pytest.raises(BreakGlassRefused) as caught:
            build_break_glass_justification(
                reason_class=BreakGlassReason.SECURITY_INCIDENT,
                free_text="x" * (MIN_JUSTIFICATION_CHARS - 1),
                controller_instruction_ref="ci:tenant-a:2026-09-03:01",
                deployment=Deployment.PROCESSOR,
            )
        assert caught.value.code == "justification_too_short"

    def test_a_processor_tenant_needs_a_controller_instruction(self) -> None:
        with pytest.raises(BreakGlassRefused) as caught:
            build_break_glass_justification(
                reason_class=BreakGlassReason.SECURITY_INCIDENT,
                free_text="Suspected credential stuffing against one account.",
                controller_instruction_ref=None,
                deployment=Deployment.PROCESSOR,
            )
        assert caught.value.code == "controller_instruction_required"

    def test_a_controller_deployment_has_no_lawful_basis_yet(self) -> None:
        # files/08 §2.6 + HUMAN_BLOCKERS HB-L6: post-7499 the health regime
        # aligns to Art. 9, m.6/3 runs to persons under an obligation of
        # secrecy, and files/06 §2 enumerates no staff-access purpose. There
        # is no scope to check, so invariant 4 refuses rather than proceeds.
        with pytest.raises(BreakGlassRefused) as caught:
            build_break_glass_justification(
                reason_class=BreakGlassReason.PATIENT_SUPPORT_REQUEST,
                free_text="Patient asked support to look at a missing note.",
                controller_instruction_ref="ci:consumer:2026-09-03:01",
                deployment=Deployment.CONTROLLER,
            )
        assert caught.value.code == "no_lawful_basis"

    def test_the_grant_ttl_is_the_spec_ceiling(self) -> None:
        assert BREAK_GLASS_GRANT_TTL == timedelta(minutes=60)


class TestIpAllowList:
    def test_an_empty_list_admits_nobody(self) -> None:
        empty = IpAllowList.from_spec("")
        assert empty.networks == ()
        assert not empty.permits("192.0.2.10")

    def test_a_listed_address_is_admitted_and_a_neighbour_is_not(self) -> None:
        allow = IpAllowList.from_spec("192.0.2.0/24, 2001:db8::/32")
        assert allow.permits("192.0.2.10")
        assert allow.permits("2001:db8::1")
        assert not allow.permits("198.51.100.7")

    def test_a_non_address_client_is_refused(self) -> None:
        allow = IpAllowList.from_spec("192.0.2.0/24")
        assert not allow.permits("testclient")
        assert not allow.permits("")

    def test_a_malformed_entry_is_a_configuration_error(self) -> None:
        with pytest.raises(ValueError):
            IpAllowList.from_spec("192.0.2.0/24, not-a-network")


class TestRefusalsCarryCodesNotNarrative:
    def test_every_four_eyes_refusal_has_a_stable_code(self) -> None:
        codes = {
            cls.code
            for cls in (
                SelfApproval,
                SharedCredential,
                SharedSession,
                SharedOrganisation,
                ApproverRoleIneligible,
                AssertionReused,
                PendingActionExpired,
                PendingActionDecided,
                UnknownPendingAction,
            )
        }
        assert len(codes) == 9
        assert all(issubclass(cls, FourEyesRefused) for cls in (SelfApproval, AssertionReused))
        assert all(code.startswith("four_eyes_") for code in codes)

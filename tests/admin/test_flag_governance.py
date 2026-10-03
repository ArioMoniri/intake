"""INT-188 — flag governance: mandatory change reasons + four-eyes on safety flags.

Acceptance, verbatim: *"change reasons mandatory; safety flags list incl.
device_functions, s2s, learning-apply"*.

The one-line acceptance predates the 25 Aug admin-console security audit, which
tightened it in two directions this suite pins:

- **Safety switches do not live in the generic flag store at all** (invariant
  34, `device_flag_gate_guard`'s flag-store scan half; files/08 §0b F1/F2, §3,
  §8.2). Unleash API tokens flip flags with no audit row and CI runners hold
  them, so a safety key in that store is a governance hole regardless of its
  value. ``scan_generic_store``/``guard_generic_flag_write`` are that scan, and
  ``set_operational`` refuses a safety key rather than writing one.
- **A "safety" flag governs rollout/exposure, never clinical semantics**
  (invariant 12). A flag can never modify red-flag levels, instruments, consent
  texts, the Talker tool list, PolicyGuard or profile routing — so those
  surfaces are not even nameable as flag keys (``guard_flag_key``), and the
  governed set is disjoint from them.

The near-miss the whole file turns on: **a safety flag ENABLED by one person is
refused** — the dangerous direction takes two keys (a distinct human, credential
and session, a fresh single-use assertion, and at tier 3 a distinct
organisation). Its mirror is the asymmetry finding F17: pulling a safety flag to
its *safe* state takes one key, because a second approver on the safe direction
is an availability control on a safety control.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from intake_platform.admin import (
    DANGEROUS_ACTIONS,
    ActionDirection,
    ActionTier,
    ActorBlock,
)
from intake_platform.admin.flag_governance import (
    CLINICAL_SEMANTIC_SURFACES,
    MIN_CHANGE_REASON_CHARS,
    SAFETY_FLAG_DISABLE_ROLES,
    SAFETY_FLAG_ENABLE,
    SAFETY_FLAG_KEYS,
    ChangeReasonMissing,
    ChangeReasonTooShort,
    ClinicalSemanticSurface,
    DeviceFunctionsPreconditionUnmet,
    FlagChangeReason,
    FlagGovernanceRefused,
    FlagGovernor,
    GenericRedPrecondition,
    NotASafetyFlag,
    SafetyKeyInGenericStore,
    build_flag_change_justification,
    guard_flag_key,
    guard_generic_flag_write,
    is_safety_flag,
    scan_generic_store,
)
from intake_platform.admin.four_eyes import (
    FourEyesService,
    SelfApproval,
    SharedCredential,
    SharedSession,
)
from intake_platform.admin.roles import AdminRole
from intake_platform.flags import SAFETY_FLAG_DEFAULTS
from protocols.generic_red import generic_red_refusals, load_generic_red

T0 = datetime(2026, 9, 4, 9, 0, tzinfo=UTC)
CHANGE_TTL = timedelta(minutes=15)

# A real, on-topic reason of >= MIN_CHANGE_REASON_CHARS.
REASON_TEXT = "Enabling learning-apply for the pilot tenant after eval-gate green."

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
    org="org:notified-body",  # tier-3 demands a different organisation
    authenticator_aaguid="00000000-0000-0000-0000-000000000000",
    credential_id="cred-qms-owner-1",
    session_id="sid-qms-owner-1",
)


class Clock:
    def __init__(self, now: datetime = T0) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def justification(text: str = REASON_TEXT) -> object:
    return build_flag_change_justification(
        reason_class=FlagChangeReason.ROLLOUT_EXPANSION,
        free_text=text,
    )


def governor(clock: Clock | None = None) -> FlagGovernor:
    return FlagGovernor(FourEyesService(clock=clock if clock is not None else Clock()))


class TestSafetyFlagList:
    def test_the_acceptance_flags_are_in_the_list(self) -> None:
        # "safety flags list incl. device_functions, s2s, learning-apply"
        assert {"device_functions", "s2s", "learning_apply"} <= SAFETY_FLAG_KEYS

    def test_the_list_is_the_read_side_source_of_truth(self) -> None:
        # one source: the write-side governance and the read-side facade must
        # never disagree on what "safety" means.
        assert SAFETY_FLAG_KEYS == frozenset(SAFETY_FLAG_DEFAULTS)

    def test_is_safety_flag_discriminates(self) -> None:
        assert is_safety_flag("device_functions") is True
        assert is_safety_flag("learning_apply") is True
        assert is_safety_flag("greeting_v2") is False


class TestChangeReasonMandatory:
    def test_a_reason_outside_the_closed_set_is_not_constructible(self) -> None:
        with pytest.raises(ValueError):
            FlagChangeReason("curiosity")

    def test_empty_free_text_is_refused(self) -> None:
        with pytest.raises(ChangeReasonMissing) as caught:
            build_flag_change_justification(
                reason_class=FlagChangeReason.ROLLOUT_ROLLBACK,
                free_text="   ",
            )
        assert caught.value.code == "flag_change_reason_missing"

    def test_free_text_below_the_floor_is_refused(self) -> None:
        with pytest.raises(ChangeReasonTooShort) as caught:
            build_flag_change_justification(
                reason_class=FlagChangeReason.ROLLOUT_ROLLBACK,
                free_text="x" * (MIN_CHANGE_REASON_CHARS - 1),
            )
        assert caught.value.code == "flag_change_reason_too_short"

    def test_a_refusal_never_echoes_the_submitted_text(self) -> None:
        secret = "y" * (MIN_CHANGE_REASON_CHARS - 1)
        with pytest.raises(ChangeReasonTooShort) as caught:
            build_flag_change_justification(
                reason_class=FlagChangeReason.CONFIG_CORRECTION,
                free_text=secret,
            )
        assert secret not in str(caught.value)

    def test_the_governor_rejects_a_blank_justification_at_the_write(self) -> None:
        # mandatory at the WRITE, not only at the builder: a hand-built blank
        # Justification cannot slip a reasonless change past the governor.
        from intake_platform.admin.four_eyes import Justification

        gov = governor()
        blank = Justification(
            reason_class=FlagChangeReason.CONFIG_CORRECTION,
            free_text="   ",
            controller_instruction_ref=None,
        )
        with pytest.raises(ChangeReasonMissing):
            gov.set_operational("greeting_v2", True, justification=blank)

    def test_a_valid_reason_builds_a_justification(self) -> None:
        just = build_flag_change_justification(
            reason_class=FlagChangeReason.ROLLOUT_EXPANSION,
            free_text=f"  {REASON_TEXT}  ",
        )
        assert just.reason_class is FlagChangeReason.ROLLOUT_EXPANSION
        assert just.free_text == REASON_TEXT  # stripped
        # a flag change is not a processor break-glass: no controller instruction
        assert just.controller_instruction_ref is None


class TestInvariant34GenericStoreHoldsNoSafetyKey:
    def test_setting_a_safety_key_operationally_is_refused(self) -> None:
        gov = governor()
        with pytest.raises(SafetyKeyInGenericStore) as caught:
            gov.set_operational("device_functions", True, justification=justification())
        assert caught.value.code == "flag_safety_key_in_generic_store"

    @pytest.mark.parametrize("key", sorted(SAFETY_FLAG_KEYS))
    def test_guard_generic_flag_write_rejects_every_safety_key(self, key: str) -> None:
        with pytest.raises(SafetyKeyInGenericStore):
            guard_generic_flag_write(key)

    def test_scan_finds_a_safety_key_planted_in_a_store(self) -> None:
        assert scan_generic_store({"greeting_v2": True, "s2s": True}) == frozenset({"s2s"})

    def test_scan_is_clean_for_an_operational_only_store(self) -> None:
        assert scan_generic_store({"greeting_v2": True, "backchannels_ab": False}) == frozenset()

    def test_a_governor_refuses_to_be_seeded_with_a_safety_key(self) -> None:
        with pytest.raises(SafetyKeyInGenericStore):
            FlagGovernor(FourEyesService(), store={"s2s": True})

    def test_an_operational_flag_writes_and_reads_back(self) -> None:
        gov = governor()
        assert gov.set_operational("greeting_v2", True, justification=justification()) is True
        assert gov.effective_operational("greeting_v2") is True
        # and the generic store still has no safety key
        assert scan_generic_store(gov.generic_store()) == frozenset()


class TestInvariant12ExposureNotClinicalSemantics:
    def test_the_forbidden_surfaces_are_named(self) -> None:
        assert CLINICAL_SEMANTIC_SURFACES == frozenset(
            {
                "red_flag_levels",
                "instruments",
                "consent_texts",
                "talker_tool_list",
                "policyguard",
                "profile_routing",
            }
        )

    @pytest.mark.parametrize("surface", sorted(CLINICAL_SEMANTIC_SURFACES))
    def test_a_clinical_surface_is_not_a_nameable_flag(self, surface: str) -> None:
        with pytest.raises(ClinicalSemanticSurface) as caught:
            guard_flag_key(surface)
        assert caught.value.code == "flag_clinical_semantic_surface"

    def test_the_governor_refuses_to_set_a_clinical_surface(self) -> None:
        gov = governor()
        with pytest.raises(ClinicalSemanticSurface):
            gov.set_operational("policyguard", True, justification=justification())

    def test_safety_flags_are_disjoint_from_clinical_surfaces(self) -> None:
        # a safety flag governs rollout/exposure; it is never a lever over
        # clinical semantics — the two sets cannot overlap.
        assert SAFETY_FLAG_KEYS & CLINICAL_SEMANTIC_SURFACES == frozenset()


class TestSafetyEnableTakesTwoKeys:
    def test_the_enable_action_is_a_registered_tier3_dangerous_action(self) -> None:
        assert SAFETY_FLAG_ENABLE.id in DANGEROUS_ACTIONS
        assert SAFETY_FLAG_ENABLE.tier is ActionTier.T3
        assert SAFETY_FLAG_ENABLE.direction is ActionDirection.DANGEROUS
        assert SAFETY_FLAG_ENABLE.approver_must_differ_org is True

    def test_opening_an_enable_does_not_flip_the_flag(self) -> None:
        gov = governor()
        gov.open_enable(
            key="learning_apply", actor=ACTOR, justification=justification(), ttl=CHANGE_TTL
        )
        # write-ahead: nothing takes effect until a second key approves
        assert gov.effective_safety("learning_apply") is False

    def test_one_person_cannot_enable_a_safety_flag(self) -> None:
        # THE near-miss: a self-approval on the enable ceremony is refused, and
        # the flag stays in its safe state.
        gov = governor()
        pending = gov.open_enable(
            key="learning_apply", actor=ACTOR, justification=justification(), ttl=CHANGE_TTL
        )
        with pytest.raises(SelfApproval):
            gov.approve_enable(pending.id, approver=ACTOR, assertion_id="assn-1")
        assert gov.effective_safety("learning_apply") is False

    def test_a_shared_credential_cannot_enable(self) -> None:
        gov = governor()
        pending = gov.open_enable(
            key="learning_apply", actor=ACTOR, justification=justification(), ttl=CHANGE_TTL
        )
        twin = APPROVER.replace_credential(ACTOR.credential_id)
        with pytest.raises(SharedCredential):
            gov.approve_enable(pending.id, approver=twin, assertion_id="assn-1")
        assert gov.effective_safety("learning_apply") is False

    def test_a_shared_session_cannot_enable(self) -> None:
        gov = governor()
        pending = gov.open_enable(
            key="learning_apply", actor=ACTOR, justification=justification(), ttl=CHANGE_TTL
        )
        twin = APPROVER.replace_session(ACTOR.session_id)
        with pytest.raises(SharedSession):
            gov.approve_enable(pending.id, approver=twin, assertion_id="assn-1")

    def test_two_distinct_people_complete_the_enable(self) -> None:
        gov = governor()
        pending = gov.open_enable(
            key="learning_apply", actor=ACTOR, justification=justification(), ttl=CHANGE_TTL
        )
        assert gov.approve_enable(pending.id, approver=APPROVER, assertion_id="assn-1") is True
        assert gov.effective_safety("learning_apply") is True

    def test_enable_of_an_operational_key_is_refused(self) -> None:
        gov = governor()
        with pytest.raises(NotASafetyFlag) as caught:
            gov.open_enable(
                key="greeting_v2", actor=ACTOR, justification=justification(), ttl=CHANGE_TTL
            )
        assert caught.value.code == "flag_not_a_safety_flag"

    def test_the_enable_ceremony_carries_only_id_shaped_evidence(self) -> None:
        # invariant 6: the pending action a second pair of eyes reads carries
        # the flag key and the target value — never the free-text reason.
        gov = governor()
        pending = gov.open_enable(
            key="learning_apply", actor=ACTOR, justification=justification(), ttl=CHANGE_TTL
        )
        assert pending.evidence == {"flag": "learning_apply", "enabled": "true"}
        assert REASON_TEXT not in " ".join(pending.evidence.values())


class TestSafetyDisableTakesOneKey:
    """F17 / asymmetric authority: the safe direction is one key."""

    def test_the_disable_roles_are_the_incident_roles(self) -> None:
        assert AdminRole.SRE_ONCALL in SAFETY_FLAG_DISABLE_ROLES
        assert AdminRole.CLINICAL_LEAD in SAFETY_FLAG_DISABLE_ROLES

    def test_one_eligible_key_disables_a_safety_flag(self) -> None:
        gov = governor()
        # first bring it up through the full ceremony
        pending = gov.open_enable(
            key="learning_apply", actor=ACTOR, justification=justification(), ttl=CHANGE_TTL
        )
        gov.approve_enable(pending.id, approver=APPROVER, assertion_id="assn-1")
        assert gov.effective_safety("learning_apply") is True
        # a single eligible operator pulls it back to safe — no second approver
        assert (
            gov.disable(
                "learning_apply", actor_role=AdminRole.SRE_ONCALL, justification=justification()
            )
            is False
        )
        assert gov.effective_safety("learning_apply") is False

    def test_disable_by_an_ineligible_role_is_refused(self) -> None:
        gov = governor()
        with pytest.raises(FlagGovernanceRefused):
            gov.disable(
                "learning_apply", actor_role=AdminRole.SUPPORT, justification=justification()
            )

    def test_disable_still_needs_a_reason(self) -> None:
        with pytest.raises(ChangeReasonMissing):
            build_flag_change_justification(
                reason_class=FlagChangeReason.INCIDENT_MITIGATION, free_text=""
            )

    def test_disable_of_an_operational_key_is_refused(self) -> None:
        gov = governor()
        with pytest.raises(NotASafetyFlag):
            gov.disable(
                "greeting_v2", actor_role=AdminRole.SRE_ONCALL, justification=justification()
            )


class TestRefusalsCarryStableCodes:
    def test_every_refusal_has_a_flag_prefixed_code(self) -> None:
        codes = {
            cls.code
            for cls in (
                ChangeReasonMissing,
                ChangeReasonTooShort,
                SafetyKeyInGenericStore,
                ClinicalSemanticSurface,
                NotASafetyFlag,
            )
        }
        assert len(codes) == 5
        assert all(code.startswith("flag_") for code in codes)
        assert all(issubclass(cls, FlagGovernanceRefused) for cls in (SafetyKeyInGenericStore,))


class TestDeviceFunctionsNeedsAServableGenericRed:
    """INT-453: device_functions shows RED on the patient's device, and a RED
    whose own script is missing is shown as the generic escalation. While that
    copy is absent or draft_needs_source (CD-24), the flag cannot be enabled,
    so a blank generic never reaches a live tenant."""

    REPO = Path(__file__).resolve().parents[2]
    COMMITTED = REPO / "packages" / "protocols" / "generic" / "generic_red.yaml"

    @classmethod
    def draft(cls, tmp_path: Path) -> Path:
        """The committed CD-24 copy, set back to draft_needs_source (INT-465)."""
        doc = yaml.safe_load(cls.COMMITTED.read_text(encoding="utf-8"))
        doc["status"] = "draft_needs_source"
        doc["source_gap"] = "sentetik: the register row is withdrawn"
        path = tmp_path / "generic_draft.yaml"
        path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
        return path

    @staticmethod
    def precondition(path: Path) -> GenericRedPrecondition:
        return lambda: generic_red_refusals(load_generic_red(path))

    def _open(self, gov: FlagGovernor, key: str = "device_functions") -> object:
        return gov.open_enable(key=key, actor=ACTOR, justification=justification(), ttl=CHANGE_TTL)

    def test_nothing_wired_refuses(self) -> None:
        gov = governor()
        with pytest.raises(DeviceFunctionsPreconditionUnmet) as caught:
            self._open(gov)
        assert caught.value.code == "flag_device_functions_generic_red_unservable"
        assert gov.effective_safety("device_functions") is False

    def test_a_draft_generic_copy_refuses(self, tmp_path: Path) -> None:
        gov = FlagGovernor(
            FourEyesService(clock=Clock()),
            generic_red_precondition=self.precondition(self.draft(tmp_path)),
        )
        with pytest.raises(DeviceFunctionsPreconditionUnmet):
            self._open(gov)

    def test_a_servable_generic_lets_the_two_key_ceremony_complete(self) -> None:
        """Near miss: the same ceremony with the active CD-24 copy (INT-465) succeeds."""
        gov = FlagGovernor(
            FourEyesService(clock=Clock()),
            generic_red_precondition=self.precondition(self.COMMITTED),
        )
        pending = gov.open_enable(
            key="device_functions", actor=ACTOR, justification=justification(), ttl=CHANGE_TTL
        )
        assert gov.approve_enable(pending.id, approver=APPROVER, assertion_id="assn-1") is True
        assert gov.effective_safety("device_functions") is True

    def test_copy_withdrawn_between_the_two_keys_refuses_the_flip(self) -> None:
        servable = {"now": True}
        gov = FlagGovernor(
            FourEyesService(clock=Clock()),
            generic_red_precondition=lambda: () if servable["now"] else ("generic_red_absent",),
        )
        pending = gov.open_enable(
            key="device_functions", actor=ACTOR, justification=justification(), ttl=CHANGE_TTL
        )
        servable["now"] = False
        with pytest.raises(DeviceFunctionsPreconditionUnmet):
            gov.approve_enable(pending.id, approver=APPROVER, assertion_id="assn-1")
        assert gov.effective_safety("device_functions") is False

    def test_other_safety_flags_do_not_read_the_generic_red(self) -> None:
        gov = governor()  # nothing wired; learning_apply is unaffected
        pending = gov.open_enable(
            key="learning_apply", actor=ACTOR, justification=justification(), ttl=CHANGE_TTL
        )
        assert gov.approve_enable(pending.id, approver=APPROVER, assertion_id="assn-1") is True

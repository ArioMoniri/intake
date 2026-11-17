"""INT-187 — the deploy freeze: its record, its store, its governor and its verdict.

files/08 §8.2 puts **deploy freeze** on the tier-1 row: one ``sre_oncall`` or
``clinical_lead``, audited, no approver — the safe direction takes one key.
Lifting a freeze is the direction that lets changes reach patients again, so
it takes two (a tier-2 four-eyes ceremony). ``test_cicd_console.py`` drives
both through ``/admin/cicd/*``; this file pins what they rest on, each with its
near-miss:

- **The record cannot hold an impossible state** — engaged with a lift as its
  last change, a lift with no approver, an engage with one, a written record
  with no author, a staff subject shaped like prose.
- **The store fails closed and loudly** — unreachable and malformed are codes,
  never "not frozen"; a record that was never written reads as not frozen
  (the normal state, not a failure); a write moves the revision by exactly
  one and refuses a record that moved under it; the store is named by one
  environment variable or not at all.
- **The governor is asymmetric** — engage is one eligible key and idempotent;
  lift only opens a ceremony, needs a distinct second human, and refuses an
  approval once the freeze moved since the request.
- **The verdict is the one rule both the console and the deploy path read** —
  frozen, exhausted or unreadable refuses; a tier that declares no error-budget
  source is noted, not refused.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import fakeredis
import pytest
import redis
from intake_platform.admin import DANGEROUS_ACTIONS, FourEyesService
from intake_platform.admin.actions import (
    CICD_CEREMONIES,
    DEPLOY_FREEZE_ENGAGE,
    DEPLOY_FREEZE_LIFT,
    VOICE_CANARY_SET,
    ActionDirection,
    ActionTier,
)
from intake_platform.admin.flag_governance import (
    ChangeReasonMissing,
    FlagChangeReason,
    build_flag_change_justification,
)
from intake_platform.admin.four_eyes import ActorBlock, Justification, SelfApproval
from intake_platform.admin.freeze_governance import (
    DeployFreezeGovernor,
    FreezeActionMismatch,
    FreezeChanged,
    FreezeNotEngaged,
    FreezeRoleIneligible,
)
from intake_platform.admin.roles import AdminRole
from intake_platform.release_freeze import (
    ENV_RELEASE_FREEZE_REDIS_URL,
    FREEZE_KEY,
    DeployFreeze,
    DeployFreezeChange,
    ErrorBudget,
    RedisReleaseFreezeStore,
    ReleaseFreezeConflict,
    ReleaseFreezeUnavailable,
    release_freeze_store_from_env,
    release_verdict,
)
from intake_platform.slo import load_metrics_catalog
from pydantic import ValidationError

REPO = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 9, 27, 9, 0, tzinfo=UTC)
REASON = build_flag_change_justification(
    reason_class=FlagChangeReason.INCIDENT_MITIGATION,
    free_text="Error budget burning on the api; hold every deploy.",
)
BLANK = Justification(
    reason_class=FlagChangeReason.INCIDENT_MITIGATION,
    free_text="  ",
    controller_instruction_ref=None,
)


def _actor(role: AdminRole, n: int = 1) -> ActorBlock:
    return ActorBlock(
        subject=f"kc-sub-{role.value}-{n}",
        role=role,
        org="org:intake",
        authenticator_aaguid=f"aaguid-{n}",
        credential_id=f"cred-{role.value}-{n}",
        session_id=f"sid-{role.value}-{n}",
    )


def _store() -> RedisReleaseFreezeStore:
    return RedisReleaseFreezeStore(fakeredis.FakeRedis())


def _governor(store: Any = None) -> DeployFreezeGovernor:
    return DeployFreezeGovernor(
        FourEyesService(clock=lambda: NOW), store or _store(), clock=lambda: NOW
    )


def _engaged(revision: int = 1) -> DeployFreeze:
    return DeployFreeze(
        engaged=True,
        revision=revision,
        changed_at=NOW,
        changed_by="kc-sub-sre-oncall-1",
        last_change=DeployFreezeChange.ENGAGE,
        reason_class="incident_mitigation",
    )


# =====================================================================================
# the registry: one key toward frozen, two toward shipping
# =====================================================================================


class TestRegistry:
    def test_engaging_is_tier_1_the_safe_direction_with_no_approver(self) -> None:
        assert DEPLOY_FREEZE_ENGAGE.tier is ActionTier.T1
        assert DEPLOY_FREEZE_ENGAGE.direction is ActionDirection.SAFE
        assert DEPLOY_FREEZE_ENGAGE.approver_roles == frozenset()
        # files/08 §8.2's T1 row names sre_oncall and clinical_lead
        assert {AdminRole.SRE_ONCALL, AdminRole.CLINICAL_LEAD} <= DEPLOY_FREEZE_ENGAGE.actor_roles

    def test_lifting_is_tier_2_the_dangerous_direction_with_a_second_key(self) -> None:
        assert DEPLOY_FREEZE_LIFT.tier is ActionTier.T2
        assert DEPLOY_FREEZE_LIFT.direction is ActionDirection.DANGEROUS
        assert DEPLOY_FREEZE_LIFT.approver_roles
        # sre_oncall's §2.1 scope is T1 safe-direction actions: neither side of T2
        assert AdminRole.SRE_ONCALL not in (
            DEPLOY_FREEZE_LIFT.actor_roles | DEPLOY_FREEZE_LIFT.approver_roles
        )
        assert CICD_CEREMONIES == (DEPLOY_FREEZE_LIFT,)

    def test_both_are_registered_with_a_runbook_on_disk_and_a_catalogued_alert(self) -> None:
        catalog = load_metrics_catalog(REPO / "observability" / "metrics_catalog.yaml")
        spec_ids = {metric.spec_id for metric in catalog.metrics}
        for action in (DEPLOY_FREEZE_ENGAGE, DEPLOY_FREEZE_LIFT):
            assert DANGEROUS_ACTIONS[action.id] is action
            assert (REPO / action.runbook).is_file(), action.runbook
            assert action.alert_metric in spec_ids, action.alert_metric


# =====================================================================================
# the record
# =====================================================================================


class TestRecord:
    def test_a_record_never_written_is_not_frozen_and_carries_no_author(self) -> None:
        blank = DeployFreeze.unconfigured()
        assert (blank.engaged, blank.revision, blank.configured) == (False, 0, False)
        assert blank.changed_by is None and blank.last_change is None

    @pytest.mark.parametrize(
        "fields",
        [
            # engaged, but the last change was a lift
            {"engaged": True, "last_change": "freeze_lift", "approved_by": "kc-sub-qms-1"},
            # not engaged, but the last change was an engage
            {"engaged": False, "last_change": "freeze_engage"},
            # a lift with no second key
            {"engaged": False, "last_change": "freeze_lift"},
            # an engage that names an approver: tier 1 has none
            {"engaged": True, "last_change": "freeze_engage", "approved_by": "kc-sub-qms-1"},
            # a written record with no author
            {"engaged": True, "last_change": "freeze_engage", "changed_by": None},
            # a staff subject shaped like prose
            {"engaged": True, "last_change": "freeze_engage", "changed_by": "Dr. Ayşe Yılmaz"},
            # a reason class that is not a code
            {"engaged": True, "last_change": "freeze_engage", "reason_class": "because I said"},
            # revision 0 that claims a state
            {"engaged": True, "last_change": "freeze_engage", "revision": 0},
        ],
    )
    def test_an_impossible_record_is_not_constructible(self, fields: dict[str, object]) -> None:
        row: dict[str, object] = {
            "revision": 2,
            "changed_at": NOW,
            "changed_by": "kc-sub-sre-oncall-1",
            "reason_class": "incident_mitigation",
            **fields,
        }
        with pytest.raises(ValidationError):
            DeployFreeze.model_validate(row)

    def test_a_coherent_engage_and_a_coherent_lift_are(self) -> None:
        assert _engaged().engaged is True
        lifted = DeployFreeze(
            engaged=False,
            revision=2,
            changed_at=NOW,
            changed_by="kc-sub-platform-admin-1",
            approved_by="kc-sub-qms-owner-1",
            last_change=DeployFreezeChange.LIFT,
            reason_class="incident_mitigation",
        )
        assert lifted.engaged is False and lifted.configured is True


# =====================================================================================
# the store
# =====================================================================================


class TestStore:
    def test_an_empty_store_reads_not_frozen(self) -> None:
        assert _store().read() == DeployFreeze.unconfigured()

    def test_a_write_moves_the_revision_by_exactly_one(self) -> None:
        store = _store()
        with pytest.raises(ValueError, match="exactly one"):
            store.write(_engaged(revision=2), expected_revision=0)
        written = store.write(_engaged(revision=1), expected_revision=0)
        assert store.read() == written

    def test_a_write_over_a_record_that_moved_is_a_conflict(self) -> None:
        store = _store()
        store.write(_engaged(revision=1), expected_revision=0)
        with pytest.raises(ReleaseFreezeConflict):
            store.write(_engaged(revision=1), expected_revision=0)

    def test_a_record_that_is_not_the_model_is_malformed_never_not_frozen(self) -> None:
        client = fakeredis.FakeRedis()
        store = RedisReleaseFreezeStore(client)
        for raw in (b"{not json", b'{"engaged": "yes"}', b'{"engaged": true, "revision": 1}'):
            client.set(FREEZE_KEY, raw)
            with pytest.raises(ReleaseFreezeUnavailable) as refused:
                store.read()
            assert refused.value.code == "release_freeze_malformed"

    def test_an_unreachable_server_is_unavailable_on_every_operation(self) -> None:
        store = RedisReleaseFreezeStore(
            redis.Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.05)
        )
        for operation in (store.read, lambda: store.write(_engaged(), expected_revision=0)):
            with pytest.raises(ReleaseFreezeUnavailable) as refused:
                operation()
            assert refused.value.code == "release_freeze_unreachable"

    def test_the_store_is_named_by_one_variable_or_not_at_all(self) -> None:
        assert release_freeze_store_from_env({}) is None
        assert release_freeze_store_from_env({ENV_RELEASE_FREEZE_REDIS_URL: " "}) is None
        with pytest.raises(ValueError, match="redis") as refused:
            release_freeze_store_from_env(
                {ENV_RELEASE_FREEZE_REDIS_URL: "http://:hunter2@redis:6379"}
            )
        assert "hunter2" not in str(refused.value), "the URL carries the password"
        built = release_freeze_store_from_env(
            {ENV_RELEASE_FREEZE_REDIS_URL: "redis://127.0.0.1:6399/5"}
        )
        assert isinstance(built, RedisReleaseFreezeStore)


# =====================================================================================
# the governor
# =====================================================================================


class _AlwaysConflicting:
    def read(self) -> DeployFreeze:
        return DeployFreeze.unconfigured()

    def write(self, freeze: DeployFreeze, *, expected_revision: int) -> DeployFreeze:
        raise ReleaseFreezeConflict("always")


class TestGovernor:
    def test_one_sre_engages_alone_and_again_changes_nothing(self) -> None:
        store = _store()
        governor = _governor(store)
        first = governor.engage(actor=_actor(AdminRole.SRE_ONCALL), justification=REASON)
        assert first.changed is True and first.freeze.engaged is True
        assert first.freeze.changed_by == "kc-sub-sre_oncall-1"
        assert first.freeze.reason_class == "incident_mitigation"
        assert first.freeze.approved_by is None
        again = governor.engage(actor=_actor(AdminRole.CLINICAL_LEAD), justification=REASON)
        assert again.changed is False and again.freeze == first.freeze == store.read()

    def test_a_role_outside_the_t1_set_cannot_engage(self) -> None:
        with pytest.raises(FreezeRoleIneligible):
            _governor().engage(actor=_actor(AdminRole.AUDITOR), justification=REASON)

    def test_a_blank_reason_is_refused_on_both_directions(self) -> None:
        governor = _governor()
        with pytest.raises(ChangeReasonMissing):
            governor.engage(actor=_actor(AdminRole.SRE_ONCALL), justification=BLANK)
        governor.engage(actor=_actor(AdminRole.SRE_ONCALL), justification=REASON)
        with pytest.raises(ChangeReasonMissing):
            governor.open_lift(actor=_actor(AdminRole.PLATFORM_ADMIN), justification=BLANK)

    def test_the_safe_direction_retries_a_lost_race_and_then_says_so(self) -> None:
        with pytest.raises(FreezeChanged):
            _governor(_AlwaysConflicting()).engage(
                actor=_actor(AdminRole.SRE_ONCALL), justification=REASON
            )

    def test_there_is_nothing_to_lift_when_nothing_is_frozen(self) -> None:
        with pytest.raises(FreezeNotEngaged):
            _governor().open_lift(actor=_actor(AdminRole.PLATFORM_ADMIN), justification=REASON)

    def test_a_lift_request_changes_nothing_until_a_second_human_approves(self) -> None:
        store = _store()
        governor = _governor(store)
        governor.engage(actor=_actor(AdminRole.SRE_ONCALL), justification=REASON)
        pending = governor.open_lift(actor=_actor(AdminRole.PLATFORM_ADMIN), justification=REASON)
        assert store.read().engaged is True, "a request is not a lift"
        assert pending.action is DEPLOY_FREEZE_LIFT
        assert pending.evidence == {"control": "freeze_lift", "base_revision": "1"}
        assert governor.pending() == (pending,)
        lifted = governor.approve_lift(
            pending.id, approver=_actor(AdminRole.QMS_OWNER), assertion_id="assn-1"
        )
        assert lifted.engaged is False and store.read() == lifted
        assert (lifted.changed_by, lifted.approved_by) == (
            "kc-sub-platform_admin-1",
            "kc-sub-qms_owner-1",
        )
        assert lifted.last_change is DeployFreezeChange.LIFT
        assert governor.pending() == ()

    def test_one_person_cannot_lift_their_own_request(self) -> None:
        store = _store()
        governor = _governor(store)
        governor.engage(actor=_actor(AdminRole.SRE_ONCALL), justification=REASON)
        owner = _actor(AdminRole.PLATFORM_OWNER)
        pending = governor.open_lift(actor=owner, justification=REASON)
        with pytest.raises(SelfApproval):
            governor.approve_lift(pending.id, approver=owner, assertion_id="assn-2")
        assert store.read().engaged is True

    def test_an_approval_after_the_freeze_moved_is_refused_without_spending_it(self) -> None:
        store = _store()
        governor = _governor(store)
        governor.engage(actor=_actor(AdminRole.SRE_ONCALL), justification=REASON)
        pending = governor.open_lift(actor=_actor(AdminRole.PLATFORM_ADMIN), justification=REASON)
        # the freeze is lifted by another ceremony and engaged again in between
        other = governor.open_lift(actor=_actor(AdminRole.PLATFORM_OWNER), justification=REASON)
        governor.approve_lift(other.id, approver=_actor(AdminRole.QMS_OWNER), assertion_id="a3")
        governor.engage(actor=_actor(AdminRole.SRE_ONCALL), justification=REASON)
        with pytest.raises(FreezeChanged):
            governor.approve_lift(
                pending.id, approver=_actor(AdminRole.QMS_OWNER, 2), assertion_id="a4"
            )
        assert store.read().engaged is True
        assert pending in governor.pending(), "the refused approval spent nothing"

    def test_another_modules_ceremony_cannot_be_approved_here(self) -> None:
        four_eyes = FourEyesService(clock=lambda: NOW)
        governor = DeployFreezeGovernor(four_eyes, _store(), clock=lambda: NOW)
        voice = four_eyes.open(
            action=VOICE_CANARY_SET,
            actor=_actor(AdminRole.CLINICAL_LEAD),
            target_ref="voice:tenant-a",
            justification=REASON,
            evidence={"tenant": "tenant-a", "base_revision": "0"},
            ttl=timedelta(minutes=15),
        )
        with pytest.raises(FreezeActionMismatch):
            governor.approve_lift(voice.id, approver=_actor(AdminRole.QMS_OWNER), assertion_id="a5")
        assert governor.pending() == ()


# =====================================================================================
# the verdict — one rule for the console and for deploy.sh
# =====================================================================================


class TestVerdict:
    MEASURED = ErrorBudget.measured(exhausted=(), unmeasured=())

    def test_not_frozen_and_within_budget_is_allowed(self) -> None:
        verdict = release_verdict(
            freeze=DeployFreeze.unconfigured(), freeze_failure=None, budget=self.MEASURED
        )
        assert (verdict.allowed, verdict.refusals, verdict.notes) == (True, (), ())

    def test_an_engaged_freeze_refuses(self) -> None:
        verdict = release_verdict(freeze=_engaged(), freeze_failure=None, budget=self.MEASURED)
        assert (verdict.allowed, verdict.refusals) == (False, ("deploy_freeze_engaged",))

    @pytest.mark.parametrize(
        "code",
        ["release_freeze_unconfigured", "release_freeze_unreachable", "release_freeze_malformed"],
    )
    def test_a_freeze_nobody_can_read_refuses_rather_than_reading_as_open(self, code: str) -> None:
        verdict = release_verdict(freeze=None, freeze_failure=code, budget=self.MEASURED)
        assert (verdict.allowed, verdict.refusals) == (False, (code,))

    def test_an_exhausted_budget_freezes_deploys_on_its_own(self) -> None:
        budget = ErrorBudget.measured(exhausted=("api/availability",), unmeasured=())
        verdict = release_verdict(
            freeze=DeployFreeze.unconfigured(), freeze_failure=None, budget=budget
        )
        assert (verdict.allowed, verdict.refusals) == (False, ("error_budget_exhausted",))

    def test_a_declared_budget_source_that_cannot_answer_refuses(self) -> None:
        verdict = release_verdict(
            freeze=DeployFreeze.unconfigured(),
            freeze_failure=None,
            budget=ErrorBudget.failed("prometheus_unreachable"),
        )
        assert (verdict.allowed, verdict.refusals) == (False, ("error_budget_unreadable",))

    def test_a_tier_without_a_budget_source_is_noted_not_refused(self) -> None:
        verdict = release_verdict(
            freeze=DeployFreeze.unconfigured(),
            freeze_failure=None,
            budget=ErrorBudget.not_configured(),
        )
        assert verdict.allowed is True
        assert verdict.notes == ("error_budget_not_configured",)

    def test_an_slo_nothing_measured_is_noted_not_counted_as_within_budget(self) -> None:
        budget = ErrorBudget.measured(exhausted=(), unmeasured=("voice-runtime/turn_success",))
        verdict = release_verdict(
            freeze=DeployFreeze.unconfigured(), freeze_failure=None, budget=budget
        )
        assert verdict.allowed is True
        assert verdict.notes == ("error_budget_unmeasured",)

    def test_every_refusal_is_listed_not_only_the_first(self) -> None:
        budget = ErrorBudget.measured(exhausted=("api/availability",), unmeasured=())
        verdict = release_verdict(freeze=_engaged(), freeze_failure=None, budget=budget)
        assert verdict.refusals == ("deploy_freeze_engaged", "error_budget_exhausted")

    def test_a_missing_freeze_needs_its_reason(self) -> None:
        with pytest.raises(ValueError):
            release_verdict(freeze=None, freeze_failure=None, budget=self.MEASURED)

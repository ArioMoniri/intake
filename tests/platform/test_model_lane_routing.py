"""INT-428 / ADR-035 — the routing decision table and its type-level floors.

- **The table.** Every row of :func:`decide_route`'s docstring table, for the
  configured route, the self-hosted health and each hosted block, in order.
- **Hosted is unrepresentable for real PHI** (medical review, finding 12;
  AI/ML review): no guard admits it, no permit or assignment can be built for
  it, and ``mock`` is no route at all. Near miss: the same objects build for a
  synthetic deployment.
- **The synthetic flag is immutable**: bound by the first write, refused by
  both stores when a later write moves it, read as ``real_phi`` when the
  declaration disagrees. Near miss: the same class is copied write after write.
"""

from __future__ import annotations

import fakeredis
import pytest
from intake_platform.egress import DataClass
from intake_platform.model_lanes import (
    HostedLaneRefused,
    HostedPermit,
    InMemoryModelLanesStore,
    Lane,
    LaneRoute,
    LaneSetting,
    ModelAssignment,
    ModelLanesControl,
    ModelLanesRefused,
    ModelRole,
    ProviderId,
    RedisModelLanesStore,
    RouteKind,
    TenantDataClass,
    check_hosted_permitted,
    decide_route,
    deployment_data_class,
    effective_data_class,
    parse_role,
    parse_route,
)

LLM = ModelRole.of(Lane.LLM)
SYN = TenantDataClass.SYNTHETIC
PHI = TenantDataClass.REAL_PHI


def _control(**lanes: LaneSetting) -> ModelLanesControl:
    settings = {lane: LaneSetting() for lane in Lane}
    settings.update({Lane(name): setting for name, setting in lanes.items()})
    return ModelLanesControl(lanes=settings)


def _decide(
    control: ModelLanesControl,
    *,
    data_class: TenantDataClass = SYN,
    healthy: bool = True,
    block: str | None = None,
    kill: bool = False,
    role: ModelRole = LLM,
):  # type: ignore[no-untyped-def]
    return decide_route(
        role,
        control,
        data_class=data_class,
        self_hosted_healthy=healthy,
        provider_block=lambda _provider: block,
        tenant_kill_switch=kill,
    )


HOSTED = LaneSetting(route="hosted:openai")
SELF_WITH_FALLBACK = LaneSetting(route="self_hosted", fallback=ProviderId.OPENAI)


class TestTheDecisionTable:
    def test_self_hosted_healthy_serves_self_hosted(self) -> None:
        decision = _decide(_control())
        assert decision.serving == LaneRoute.self_hosted()
        assert decision.reason == "configured"

    def test_self_hosted_unhealthy_without_fallback_refuses(self) -> None:
        decision = _decide(_control(), healthy=False)
        assert decision.serving is None
        assert decision.reason == "self_hosted_unhealthy"

    def test_self_hosted_unhealthy_with_an_admitted_fallback_falls_back(self) -> None:
        decision = _decide(_control(llm=SELF_WITH_FALLBACK), healthy=False)
        assert decision.serving == LaneRoute.hosted(ProviderId.OPENAI)
        assert decision.fallback
        assert decision.egress_data_class is DataClass.NON_PERSONAL

    def test_near_miss_a_healthy_gpu_never_falls_back(self) -> None:
        decision = _decide(_control(llm=SELF_WITH_FALLBACK), healthy=True)
        assert decision.serving == LaneRoute.self_hosted()
        assert not decision.fallback

    def test_a_blocked_fallback_refuses_with_the_block(self) -> None:
        decision = _decide(
            _control(llm=SELF_WITH_FALLBACK), healthy=False, block="hosted_key_not_set"
        )
        assert decision.serving is None
        assert decision.reason == "hosted_key_not_set"

    def test_hosted_admitted_serves_hosted(self) -> None:
        decision = _decide(_control(llm=HOSTED), healthy=False)
        assert decision.serving == LaneRoute.hosted(ProviderId.OPENAI)
        assert decision.reason == "configured"

    def test_hosted_blocked_switches_over_to_a_healthy_gpu(self) -> None:
        decision = _decide(_control(llm=HOSTED), block="hosted_egress_not_listed")
        assert decision.serving == LaneRoute.self_hosted()
        assert decision.reason == "hosted_blocked_self_hosted"

    def test_hosted_blocked_and_no_gpu_refuses_with_the_block(self) -> None:
        decision = _decide(_control(llm=HOSTED), healthy=False, block="hosted_egress_not_listed")
        assert decision.serving is None
        assert decision.reason == "hosted_egress_not_listed"

    @pytest.mark.parametrize(
        ("control", "kill", "expected"),
        [
            (
                _control(llm=HOSTED).model_copy(update={"hosted_disabled": True}),
                False,
                "hosted_disabled",
            ),
            (_control(llm=HOSTED), True, "kill_switch_engaged"),
        ],
    )
    def test_both_kill_switches_stop_hosted_instantly(
        self, control: ModelLanesControl, kill: bool, expected: str
    ) -> None:
        decision = _decide(control, healthy=False, kill=kill)
        assert decision.serving is None
        assert decision.reason == expected

    def test_the_blocks_are_checked_in_order(self) -> None:
        disabled = _control(llm=HOSTED).model_copy(update={"hosted_disabled": True})
        # the lanes' own kill switch outranks every later reason
        decision = _decide(disabled, healthy=False, kill=True, data_class=PHI, block="x")
        assert decision.reason == "hosted_disabled"

    def test_a_role_inherits_its_lane_until_it_has_its_own_setting(self) -> None:
        role = parse_role("llm.council.chair")
        inherited = _decide(_control(llm=HOSTED), healthy=False, role=role)
        assert inherited.serving == LaneRoute.hosted(ProviderId.OPENAI)
        own = _control(llm=HOSTED).model_copy(update={"roles": {role.id: LaneSetting()}})
        assert _decide(own, healthy=True, role=role).serving == LaneRoute.self_hosted()


class TestHostedIsUnrepresentableForRealPhi:
    def test_mock_hosted_unrepresentable_for_phi_tenant(self) -> None:
        # the guard: no transfer basis, no DPA branch — refused, full stop
        with pytest.raises(HostedLaneRefused, match="hosted_lane_real_phi_refused"):
            check_hosted_permitted(data_class=PHI, provider=ProviderId.OPENAI)
        # the decision: a configured hosted route and a fallback both refuse
        assert _decide(_control(llm=HOSTED), healthy=False, data_class=PHI).reason == (
            "hosted_lane_real_phi_refused"
        )
        assert (
            _decide(_control(llm=SELF_WITH_FALLBACK), healthy=False, data_class=PHI).serving is None
        )
        # the objects: neither a permit nor an assignment can be constructed
        with pytest.raises(TypeError):
            HostedPermit(provider=ProviderId.OPENAI, tenant=PHI)
        with pytest.raises(TypeError):
            ModelAssignment(
                LLM,
                True,
                "configured",
                LaneRoute.hosted(ProviderId.OPENAI),
                None,
                PHI,
                egress_data_class=DataClass.NON_PERSONAL,
            )
        # and `mock` is not a route anyone can name
        with pytest.raises(ModelLanesRefused):
            parse_route("mock")
        assert {kind.value for kind in RouteKind} == {"self_hosted", "hosted"}

    def test_near_miss_the_same_objects_build_for_a_synthetic_deployment(self) -> None:
        permit = check_hosted_permitted(data_class=SYN, provider=ProviderId.OPENAI)
        assert permit.egress_data_class is DataClass.NON_PERSONAL
        assignment = ModelAssignment(
            LLM,
            True,
            "configured",
            LaneRoute.hosted(ProviderId.OPENAI),
            None,
            SYN,
            egress_data_class=DataClass.NON_PERSONAL,
        )
        assert assignment.available and not assignment.clinical_evidence

    def test_a_hosted_assignment_never_carries_personal_data(self) -> None:
        with pytest.raises(TypeError):
            ModelAssignment(
                LLM,
                True,
                "configured",
                LaneRoute.hosted(ProviderId.OPENAI),
                None,
                SYN,
                egress_data_class=DataClass.PHI,
            )

    def test_a_real_phi_switch_over_still_serves_the_gpu(self) -> None:
        decision = _decide(_control(llm=HOSTED), healthy=True, data_class=PHI)
        assert decision.serving == LaneRoute.self_hosted()


class TestTheSyntheticFlagIsImmutable:
    def test_synthetic_flag_immutable(self) -> None:
        bound = ModelLanesControl(data_class=PHI, revision=1)
        moved = bound.model_copy(update={"data_class": SYN, "revision": 2})
        # both stores refuse a write that moves a bound class
        memory = InMemoryModelLanesStore(bound)
        with pytest.raises(ModelLanesRefused, match="model_lanes_data_class_bound"):
            memory.write(moved, expected_revision=1)
        redis_store = RedisModelLanesStore(fakeredis.FakeRedis())
        redis_store.write(ModelLanesControl(data_class=PHI, revision=1), expected_revision=0)
        with pytest.raises(ModelLanesRefused, match="model_lanes_data_class_bound"):
            redis_store.write(moved, expected_revision=1)
        # a declaration that disagrees with the bound class reads as real PHI,
        # whichever way round — no redeploy turns real patients synthetic
        assert effective_data_class(SYN, PHI) is PHI
        assert effective_data_class(PHI, SYN) is PHI
        # the declaration admits a hosted lane only for the exact literal
        for raw in ("", "Synthetic", "synthetic ", "real_phi", "test", "dev"):
            assert deployment_data_class({"INTAKE_DEPLOYMENT_DATA_CLASS": raw}) is PHI
        assert deployment_data_class({}) is PHI

    def test_near_miss_the_same_class_is_copied_write_after_write(self) -> None:
        memory = InMemoryModelLanesStore()
        first = ModelLanesControl(data_class=SYN, revision=1)
        memory.write(first, expected_revision=0)  # binding from unbound is allowed
        memory.write(first.model_copy(update={"revision": 2}), expected_revision=1)
        assert memory.read().data_class is SYN
        assert effective_data_class(SYN, SYN) is SYN
        assert effective_data_class(SYN, None) is SYN
        assert deployment_data_class({"INTAKE_DEPLOYMENT_DATA_CLASS": "synthetic"}) is SYN

    def test_the_control_record_has_no_way_to_carry_a_second_class(self) -> None:
        with pytest.raises(ValueError):
            ModelLanesControl.model_validate({"data_class": "synthetic", "tenant_class": "x"})


class TestTheVocabulary:
    @pytest.mark.parametrize("raw", ["llm", "asr", "tts", "llm.council.chair", "llm.a.b.c"])
    def test_roles_parse(self, raw: str) -> None:
        assert parse_role(raw).id == raw

    @pytest.mark.parametrize(
        "raw", ["", "LLM", "vision", "llm.", "llm.Council", "llm.a.b.c.d", "llm..x", 3]
    )
    def test_anything_else_is_refused(self, raw: object) -> None:
        with pytest.raises(ModelLanesRefused):
            parse_role(raw)

    def test_a_fallback_lives_only_behind_self_hosted(self) -> None:
        with pytest.raises(ValueError):
            LaneSetting(route="hosted:openai", fallback=ProviderId.OPENAI)
        with pytest.raises(ValueError):
            LaneSetting(route="self_hosted", fallback_model="gpt-4o-mini")

    def test_a_lane_setting_never_lives_under_roles(self) -> None:
        with pytest.raises(ValueError):
            ModelLanesControl(roles={"llm": LaneSetting()})

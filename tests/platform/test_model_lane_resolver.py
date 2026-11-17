"""INT-428 — the resolver (``role → (provider, model)``), identity, sessions, dispatch.

- **Attested components only.** A self-hosted lane is healthy only when its
  endpoint *says* it serves the attested registry model — an address that
  answers is not enough (the loopback-tunnel loophole). In a real-PHI
  deployment only ``jurisdiction: TR`` + ``phi_path`` rows are selectable.
- **Hosted models are dated snapshots** and resolve from the allow-list only.
- **The per-call model check** refuses an answer from another model and
  quarantines a self-hosted lane.
- **The model pin is frozen per session** (medical review, finding 12): a
  console switch or a recovered GPU changes the next session, never this one.
- **Fallback** to hosted when the self-hosted call fails — synthetic only,
  never inside a session.
- **Synthetic or hosted runs never count as clinical evidence.**
"""

from __future__ import annotations

from typing import Any

import pytest
from intake_platform.egress import DataClass
from intake_platform.model_lanes import (
    HostedModel,
    Lane,
    LaneIdentityMismatch,
    LaneRefused,
    LaneResult,
    LaneRoute,
    LaneSetting,
    ModelAssignment,
    ModelLanesControl,
    ModelResolver,
    ProviderId,
    QualificationRegistry,
    RouteKind,
    SessionLanes,
    TenantDataClass,
    dispatch,
    verify_served_model,
)
from model_lanes_kit import (
    LLM_SNAPSHOT,
    OTHER_REVISION,
    build_lanes,
    green,
    self_hosted_row,
)
from prometheus_client import REGISTRY

SYN = TenantDataClass.SYNTHETIC
PHI = TenantDataClass.REAL_PHI


def _control(**lanes: LaneSetting) -> ModelLanesControl:
    settings = {lane: LaneSetting() for lane in Lane}
    settings.update({Lane(name): setting for name, setting in lanes.items()})
    return ModelLanesControl(lanes=settings)


HOSTED_LLM = LaneSetting(route="hosted:openai", model="gpt-4o-mini")


class TestTheResolverInterface:
    def test_the_router_is_a_model_resolver(self) -> None:
        lanes = build_lanes()
        resolver: ModelResolver = lanes.router
        assignment = resolver.resolve("llm.council.chair", tenant_id=None)
        assert assignment.role.id == "llm.council.chair"
        assert assignment.lane is Lane.LLM
        assert assignment.provider == "self_hosted"
        assert assignment.model is not None and assignment.model.component == "gpu-llm"

    def test_an_unknown_role_is_refused_not_guessed(self) -> None:
        with pytest.raises(LaneRefused, match="model_role_unknown"):
            build_lanes().router.resolve("vision", tenant_id=None)

    def test_a_hosted_role_resolves_to_the_dated_snapshot(self) -> None:
        lanes = build_lanes(control=_control(llm=HOSTED_LLM))
        assignment = lanes.router.resolve("llm", tenant_id=None)
        assert assignment.provider == "openai"
        assert assignment.model is not None
        assert assignment.model.wire == "gpt-4o-mini-2024-07-18"
        assert assignment.model.version == "2024-07-18"
        assert assignment.egress_data_class is DataClass.NON_PERSONAL

    def test_a_configured_model_off_the_allow_list_stops_serving(self) -> None:
        lanes = build_lanes(control=_control(llm=LaneSetting(route="hosted:openai", model="gpt-x")))
        assignment = lanes.router.resolve("llm", tenant_id=None)
        assert not assignment.available
        assert assignment.reason == "model_not_allowed"

    def test_an_alias_is_not_a_snapshot(self) -> None:
        with pytest.raises(ValueError):
            HostedModel(id="gpt-4o-mini", version="latest", wire="gpt-4o-mini", lanes=(Lane.LLM,))
        with pytest.raises(ValueError):
            HostedModel(
                id="gpt-4o-mini",
                version="2024-08-06",
                wire="gpt-4o-mini-2024-07-18",
                lanes=(Lane.LLM,),
            )

    def test_hosted_needs_the_image_the_row_and_the_key(self) -> None:
        cases: list[tuple[dict[str, Any], str]] = [
            ({"in_image": False}, "hosted_not_in_deployment"),
            ({"listed": False}, "hosted_egress_not_listed"),
            ({"key_set": False}, "hosted_key_not_set"),
        ]
        for kwargs, code in cases:
            lanes = build_lanes(control=_control(llm=HOSTED_LLM), served=False, **kwargs)
            assignment = lanes.router.resolve("llm", tenant_id=None)
            assert (assignment.available, assignment.reason) == (False, code), kwargs


class TestIdentityNotAddress:
    def test_an_endpoint_that_answers_as_another_model_is_not_healthy(self) -> None:
        lanes = build_lanes()
        # the tunnel answers — but as a different revision of the model
        wrong = self_hosted_row(Lane.LLM, revision=OTHER_REVISION)
        from model_lanes_kit import identity_of

        lanes.identities[Lane.LLM] = identity_of(wrong)
        lanes.router.health._seen.clear()
        assignment = lanes.router.resolve("llm", tenant_id=None)
        assert not assignment.available
        assert assignment.reason == "self_hosted_unhealthy"
        expected = lanes.rows[Lane.LLM].ref()
        assert lanes.router.health.state(Lane.LLM, expected) == "identity_mismatch"

    def test_near_miss_the_attested_identity_is_healthy(self) -> None:
        lanes = build_lanes()
        expected = lanes.rows[Lane.LLM].ref()
        assert lanes.router.health.state(Lane.LLM, expected) == "healthy"

    def test_an_endpoint_that_does_not_say_who_it_is_is_unreachable(self) -> None:
        lanes = build_lanes(served=False)
        assert lanes.router.health.state(Lane.LLM, lanes.rows[Lane.LLM].ref()) == "unreachable"

    def test_a_phi_deployment_lists_only_tr_attested_phi_path_rows(self) -> None:
        lanes = build_lanes(declared=PHI)
        foreign = self_hosted_row(Lane.LLM, jurisdiction="US")
        not_phi = self_hosted_row(Lane.LLM, phi_path=False)
        unpinned = self_hosted_row(Lane.LLM, weights={})
        assert not foreign.attested_for(PHI)
        assert not not_phi.attested_for(PHI)
        assert not unpinned.attested_for(PHI) and not unpinned.attested_for(SYN)
        assert foreign.attested_for(SYN)  # near miss: synthetic needs only the pin
        assert lanes.rows[Lane.LLM].attested_for(PHI)

    def test_the_per_call_model_check(self) -> None:
        lanes = build_lanes(control=_control(llm=HOSTED_LLM))
        assignment = lanes.router.resolve("llm", tenant_id=None)
        verify_served_model(assignment, "gpt-4o-mini-2024-07-18")  # near miss passes
        verify_served_model(assignment, None)  # no model field: the probe's job
        with pytest.raises(LaneIdentityMismatch):
            verify_served_model(assignment, "gpt-4o-2024-08-06")


class TestQualificationAtRuntime:
    def test_a_real_phi_lane_runs_only_a_qualified_model_version(self) -> None:
        lanes = build_lanes(declared=PHI)
        assignment = lanes.router.resolve("llm", tenant_id=None)
        assert (assignment.available, assignment.reason) == (False, "model_not_qualified")

    def test_near_miss_a_green_row_for_that_exact_version_serves(self) -> None:
        lanes = build_lanes(declared=PHI)
        ref = lanes.rows[Lane.LLM].ref()
        assert ref is not None
        lanes.router.qualifications = QualificationRegistry(
            gated_lanes=frozenset({Lane.LLM, Lane.ASR}), rows=(green(Lane.LLM, ref),)
        )
        assignment = lanes.router.resolve("llm", tenant_id=None)
        assert assignment.available and assignment.qualified
        assert assignment.clinical_evidence  # the only case that can count

    def test_a_row_for_another_version_does_not_qualify(self) -> None:
        lanes = build_lanes(declared=PHI)
        other = self_hosted_row(Lane.LLM, revision=OTHER_REVISION).ref()
        assert other is not None
        lanes.router.qualifications = QualificationRegistry(
            gated_lanes=frozenset({Lane.LLM}), rows=(green(Lane.LLM, other),)
        )
        assert lanes.router.resolve("llm", tenant_id=None).reason == "model_not_qualified"

    def test_synthetic_or_hosted_runs_never_count_as_clinical_evidence(self) -> None:
        lanes = build_lanes(control=_control(llm=HOSTED_LLM))
        hosted = lanes.router.resolve("llm", tenant_id=None)
        ref = LLM_SNAPSHOT.ref(ProviderId.OPENAI)
        lanes.router.qualifications = QualificationRegistry(
            gated_lanes=frozenset({Lane.LLM}), rows=(green(Lane.LLM, ref),)
        )
        assert hosted.available and not hosted.clinical_evidence
        synthetic_gpu = build_lanes().router.resolve("llm", tenant_id=None)
        assert synthetic_gpu.available and not synthetic_gpu.clinical_evidence


class TestFrozenPerSession:
    def test_model_pin_frozen_in_session(self) -> None:
        lanes = build_lanes(control=_control(llm=HOSTED_LLM))
        session = SessionLanes(lanes.router, tenant_id="tenant-a")
        first = session.resolve("llm")
        assert first.provider == "openai"
        # the console switches the lane to the GPU mid-session ...
        lanes.store.write(
            lanes.store.read().model_copy(
                update={
                    "lanes": {**lanes.store.read().lanes, Lane.LLM: LaneSetting()},
                    "revision": 1,
                }
            ),
            expected_revision=0,
        )
        # ... and the running session keeps its pin, model version included
        again = session.resolve("llm")
        assert again == first
        assert again.model is not None and again.model.version == "2024-07-18"

    def test_near_miss_a_new_session_picks_up_the_switch(self) -> None:
        lanes = build_lanes(control=_control(llm=HOSTED_LLM))
        SessionLanes(lanes.router, tenant_id="tenant-a").resolve("llm")
        lanes.store.write(
            lanes.store.read().model_copy(
                update={
                    "lanes": {**lanes.store.read().lanes, Lane.LLM: LaneSetting()},
                    "revision": 1,
                }
            ),
            expected_revision=0,
        )
        fresh = SessionLanes(lanes.router, tenant_id="tenant-a").resolve("llm")
        assert fresh.provider == "self_hosted"

    def test_a_frozen_pin_that_stops_being_admissible_refuses_never_switches(self) -> None:
        lanes = build_lanes(control=_control(llm=HOSTED_LLM))
        session = SessionLanes(lanes.router, tenant_id="tenant-a")
        assert session.resolve("llm").provider == "openai"
        killed = lanes.store.read().model_copy(update={"hosted_disabled": True, "revision": 1})
        lanes.store.write(killed, expected_revision=0)
        refused = session.resolve("llm")
        assert not refused.available
        assert refused.reason == "hosted_disabled"
        # the GPU is healthy, and the session still does not flap onto it
        assert lanes.router.resolve("llm", tenant_id=None).provider == "self_hosted"

    def test_an_unavailable_first_answer_is_the_sessions_answer(self) -> None:
        lanes = build_lanes(served=False)
        session = SessionLanes(lanes.router, tenant_id=None)
        assert not session.resolve("llm").available
        lanes.identities[Lane.LLM] = None
        from model_lanes_kit import identity_of

        lanes.identities[Lane.LLM] = identity_of(lanes.rows[Lane.LLM])
        lanes.router.health._seen.clear()
        assert not session.resolve("llm").available  # typed mode for the session


def _llm_call(log: list[str]) -> Any:
    def call(assignment: ModelAssignment) -> LaneResult[str]:
        assert assignment.route is not None
        log.append(assignment.route.wire)
        if assignment.route.kind is RouteKind.SELF_HOSTED:
            raise ConnectionError("gpu down")
        return LaneResult("ok")

    return call


class TestDispatchAndFallback:
    def test_a_failed_self_hosted_call_falls_back_once_for_synthetic(self) -> None:
        lanes = build_lanes(
            control=_control(llm=LaneSetting(route="self_hosted", fallback=ProviderId.OPENAI))
        )
        before = (
            REGISTRY.get_sample_value(
                "model_lane_fallback_total", {"lane": "llm", "provider": "openai"}
            )
            or 0.0
        )
        log: list[str] = []
        result = dispatch(
            lanes.router, "llm", tenant_id=None, call=_llm_call(log), failures=(ConnectionError,)
        )
        assert result == "ok"
        assert log == ["self_hosted", "hosted:openai"]
        after = REGISTRY.get_sample_value(
            "model_lane_fallback_total", {"lane": "llm", "provider": "openai"}
        )
        assert after == before + 1

    def test_near_miss_inside_a_session_there_is_no_fallback(self) -> None:
        lanes = build_lanes(
            control=_control(llm=LaneSetting(route="self_hosted", fallback=ProviderId.OPENAI))
        )
        session = SessionLanes(lanes.router, tenant_id=None)
        log: list[str] = []
        with pytest.raises(LaneRefused, match="self_hosted_failed"):
            dispatch(
                lanes.router,
                "llm",
                tenant_id=None,
                call=_llm_call(log),
                failures=(ConnectionError,),
                session=session,
            )
        assert log == ["self_hosted"]

    def test_a_real_phi_deployment_never_falls_back(self) -> None:
        lanes = build_lanes(
            declared=PHI,
            control=_control(llm=LaneSetting(route="self_hosted", fallback=ProviderId.OPENAI)),
        )
        ref = lanes.rows[Lane.LLM].ref()
        assert ref is not None
        lanes.router.qualifications = QualificationRegistry(
            gated_lanes=frozenset({Lane.LLM}), rows=(green(Lane.LLM, ref),)
        )
        log: list[str] = []
        with pytest.raises(LaneRefused, match="self_hosted_failed"):
            dispatch(
                lanes.router,
                "llm",
                tenant_id=None,
                call=_llm_call(log),
                failures=(ConnectionError,),
            )
        assert log == ["self_hosted"]

    def test_the_tenant_kill_switch_disables_hosted_instantly(self) -> None:
        engaged: dict[str, bool] = {"tenant-a": False}
        lanes = build_lanes(
            control=_control(llm=HOSTED_LLM), served=False, kill_switch=lambda t: engaged[t]
        )
        assert lanes.router.resolve("llm", tenant_id="tenant-a").provider == "openai"
        engaged["tenant-a"] = True
        refused = lanes.router.resolve("llm", tenant_id="tenant-a")
        assert (refused.available, refused.reason) == (False, "kill_switch_engaged")

    def test_an_unreadable_kill_switch_reads_as_engaged(self) -> None:
        def broken(_tenant: str) -> bool:
            raise ConnectionError("redis down")

        lanes = build_lanes(control=_control(llm=HOSTED_LLM), served=False, kill_switch=broken)
        assert lanes.router.resolve("llm", tenant_id="tenant-a").reason == "kill_switch_engaged"

    def test_an_identity_mismatch_quarantines_the_self_hosted_lane(self) -> None:
        lanes = build_lanes()

        def call(assignment: ModelAssignment) -> LaneResult[str]:
            verify_served_model(assignment, "someone/else")
            return LaneResult("never")

        with pytest.raises(LaneRefused, match="model_identity_mismatch"):
            dispatch(lanes.router, "llm", tenant_id=None, call=call)
        assert lanes.router.health.state(Lane.LLM, lanes.rows[Lane.LLM].ref()) == "quarantined"

    def test_a_parser_refusal_is_not_an_outage(self) -> None:
        lanes = build_lanes()

        def call(_assignment: ModelAssignment) -> LaneResult[str]:
            raise ValueError("the parser refused the completion")

        with pytest.raises(ValueError):
            dispatch(lanes.router, "llm", tenant_id=None, call=call, failures=(ConnectionError,))

    def test_an_unreadable_control_reads_as_all_self_hosted(self) -> None:
        from intake_platform.model_lanes import ModelLanesUnavailable

        lanes = build_lanes(control=_control(llm=HOSTED_LLM))

        class Down:
            def read(self) -> ModelLanesControl:
                raise ModelLanesUnavailable("model_lanes_unreachable")

        lanes.router.store = Down()
        assert lanes.router.resolve("llm", tenant_id=None).provider == "self_hosted"
        assert lanes.router.decide(Lane.LLM, tenant_id=None).serving == LaneRoute.self_hosted()

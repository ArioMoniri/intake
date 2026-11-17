"""INT-430 — members, lanes, bindings, payload parity and replay (ADR-036).

The AI/ML and medical reviews' lane must-haves, as far as they reach the
verifier: mock and hosted members are unrepresentable on a real-PHI
deployment, a pin is frozen per session, a policy binds by hash, the payload
is one shape for self-hosted and hosted, and replay reads recordings and
refuses a recording made on another lane. Each has a near-miss control.
"""

from __future__ import annotations

import asyncio
import datetime
import json
from pathlib import Path

import pytest
from council_harness import (
    BELIRTI,
    SLOT_TYPES,
    TENANT,
    TableResolver,
    assignment,
    binding_digest,
    member,
    policy,
    scope,
)
from intake_voice_runtime.clinical_agent.council.lanes import (
    DeploymentDataClass,
    HostedSyntheticMember,
    MemberRefused,
    RefusalCode,
    SelfHostedMember,
    SessionPins,
    deployment_data_class,
    pin_member,
)
from intake_voice_runtime.clinical_agent.council.policy import (
    MemberSpec,
    StudyEvidence,
    VerifierMode,
    VerifierPolicy,
)
from intake_voice_runtime.clinical_agent.council.readings import (
    VERIFIER_PROMPT_VERSION,
    Reading,
    build_verifier_instructions,
    parse_member_output,
    verifier_output_schema,
)
from intake_voice_runtime.clinical_agent.council.transport import (
    MemberCall,
    RecordedMemberTransport,
    RecordedVerificationMismatch,
    RecordedVerificationMissing,
    render_member_payload,
)
from intake_voice_runtime.extraction.boundary import PatientData

RECORDED = Path(__file__).resolve().parents[1] / "fixtures" / "council" / "recorded"
RECORDED_TEXT = "Sentetik belirtim yok, bazen var gibi."
ROLE = "llm.council.dogrulayici"


def _call(pinned: SelfHostedMember | HostedSyntheticMember, *, salt: str = "0" * 32) -> MemberCall:
    schema = verifier_output_schema(scope().ordered)
    return MemberCall(
        member=pinned,
        sample=0,
        instructions=build_verifier_instructions(schema),
        data=PatientData(text=RECORDED_TEXT),
        json_schema=schema,
        temperature="0.7",
        cache_salt=salt,
    )


class TestDeploymentGuard:
    @pytest.mark.parametrize("route", ["mock", "MOCK", "", "openai"])
    def test_mock_hosted_unrepresentable_for_phi_tenant(self, route: str) -> None:
        with pytest.raises(MemberRefused) as caught:
            pin_member(
                "m1", assignment(ROLE, route_kind=route), deployment=DeploymentDataClass.REAL_PHI
            )
        assert caught.value.code is RefusalCode.UNKNOWN_ROUTE

    def test_a_hosted_member_on_a_phi_deployment_is_refused_with_no_escape_hatch(self) -> None:
        with pytest.raises(MemberRefused) as caught:
            pin_member(
                "m1", assignment(ROLE, route_kind="hosted"), deployment=DeploymentDataClass.REAL_PHI
            )
        assert caught.value.code is RefusalCode.HOSTED_ON_PHI_DEPLOYMENT

    def test_near_miss_hosted_on_a_synthetic_deployment_pins(self) -> None:
        pinned = pin_member(
            "m1", assignment(ROLE, route_kind="hosted"), deployment=DeploymentDataClass.SYNTHETIC
        )
        assert isinstance(pinned, HostedSyntheticMember)
        assert pinned.deployment is DeploymentDataClass.SYNTHETIC

    def test_near_miss_self_hosted_on_a_phi_deployment_pins(self) -> None:
        pinned = pin_member("m1", assignment(ROLE), deployment=DeploymentDataClass.REAL_PHI)
        assert isinstance(pinned, SelfHostedMember)

    @pytest.mark.parametrize(
        ("env", "expected"),
        [
            ({}, DeploymentDataClass.REAL_PHI),
            ({"INTAKE_DEPLOYMENT_DATA_CLASS": "Synthetic"}, DeploymentDataClass.REAL_PHI),
            ({"INTAKE_DEPLOYMENT_DATA_CLASS": "real_phi"}, DeploymentDataClass.REAL_PHI),
            ({"INTAKE_DEPLOYMENT_DATA_CLASS": "synthetic"}, DeploymentDataClass.SYNTHETIC),
        ],
    )
    def test_the_data_class_fails_closed(
        self, env: dict[str, str], expected: DeploymentDataClass
    ) -> None:
        assert deployment_data_class(env) is expected

    def test_an_unavailable_or_unpinned_lane_is_refused(self) -> None:
        with pytest.raises(MemberRefused) as off:
            pin_member(
                "m1", assignment(ROLE, available=False), deployment=DeploymentDataClass.REAL_PHI
            )
        assert off.value.code is RefusalCode.UNAVAILABLE
        with pytest.raises(MemberRefused) as unpinned:
            pin_member("m1", assignment(ROLE, revision=""), deployment=DeploymentDataClass.REAL_PHI)
        assert unpinned.value.code is RefusalCode.UNPINNED_MODEL


class TestPins:
    def _capture(self, resolver: TableResolver, slot_types: tuple[str, ...] = SLOT_TYPES) -> object:
        return SessionPins.capture(
            policy(),
            resolver,
            tenant_id=TENANT,
            deployment=DeploymentDataClass.REAL_PHI,
            prompt_version=VERIFIER_PROMPT_VERSION,
            slot_types=slot_types,
        )

    def test_model_pin_frozen_in_session(self) -> None:
        resolver = TableResolver({ROLE: assignment(ROLE)})
        pins = self._capture(resolver)
        assert isinstance(pins, SessionPins)
        resolver.answers[ROLE] = assignment(ROLE, revision="r2")
        with pytest.raises(MemberRefused) as caught:
            pins.confirm_unchanged(resolver, policy(), deployment=DeploymentDataClass.REAL_PHI)
        assert caught.value.code is RefusalCode.PIN_DRIFT

    def test_near_miss_an_unchanged_router_answer_is_not_drift(self) -> None:
        resolver = TableResolver({ROLE: assignment(ROLE)})
        pins = self._capture(resolver)
        assert isinstance(pins, SessionPins)
        pins.confirm_unchanged(resolver, policy(), deployment=DeploymentDataClass.REAL_PHI)
        assert resolver.asked == [ROLE, ROLE]

    def test_a_binding_calibrated_for_another_lane_refuses(self) -> None:
        resolver = TableResolver({ROLE: assignment(ROLE)})
        with pytest.raises(MemberRefused) as caught:
            self._capture(resolver, slot_types=("boolean", "decimal"))
        assert caught.value.code is RefusalCode.BINDING_MISMATCH

    def test_near_miss_the_calibrated_binding_matches(self) -> None:
        assert binding_digest() == policy().bindings["dogrulayici"]


class TestPolicy:
    STUDY = StudyEvidence(
        path="docs/evidence/INT-430-independence.md",
        measured_on=datetime.date(2026, 10, 2),
        corpus="sentetik-korpus",
    )

    def _multi(self, **extra: object) -> VerifierPolicy:
        return VerifierPolicy.model_validate(
            {
                "mode": VerifierMode.MULTI_MEMBER,
                "members": [MemberSpec(member_id="m1"), MemberSpec(member_id="m2")],
                "samples": 1,
                "temperature": "0",
                "deadline_ms": 4000,
                "bindings": {"m1": "a" * 64, "m2": "b" * 64},
                **extra,
            }
        )

    def test_multi_member_mode_is_off_without_its_studies(self) -> None:
        with pytest.raises(ValueError, match="error-independence"):
            self._multi()

    def test_near_miss_multi_member_mode_with_both_studies_validates(self) -> None:
        enabled = self._multi(independence_study=self.STUDY, calibration_study=self.STUDY)
        assert enabled.draws == (("m1", 0), ("m2", 0))

    def test_self_consistency_draws_one_member_k_times(self) -> None:
        assert policy(samples=3).draws == (
            ("dogrulayici", 0),
            ("dogrulayici", 1),
            ("dogrulayici", 2),
        )

    @pytest.mark.parametrize(
        "bindings",
        [{}, {"dogrulayici": "z" * 64}, {"dogrulayici": "a" * 64, "baska": "b" * 64}],
    )
    def test_every_member_needs_exactly_its_own_calibrated_binding(
        self, bindings: dict[str, str]
    ) -> None:
        with pytest.raises(ValueError):
            VerifierPolicy(
                mode=VerifierMode.SELF_CONSISTENCY,
                members=(MemberSpec(member_id="dogrulayici"),),
                samples=3,
                temperature="0.7",
                deadline_ms=4000,
                bindings=bindings,
            )

    def test_member_ids_are_role_segments(self) -> None:
        with pytest.raises(ValueError):
            MemberSpec(member_id="Model/GPT")
        assert MemberSpec(member_id="dogrulayici").role_id == ROLE


class TestParityAndReplay:
    def test_one_payload_for_self_hosted_and_hosted(self) -> None:
        local = member()
        hosted = HostedSyntheticMember(
            member_id=local.member_id,
            provider=local.provider,
            model_id=local.model_id,
            revision=local.revision,
            weights_sha256=local.weights_sha256,
            deployment=DeploymentDataClass.SYNTHETIC,
        )
        assert render_member_payload(_call(local)) == render_member_payload(_call(hosted))

    def test_the_data_travels_only_inside_the_fence(self) -> None:
        payload = render_member_payload(_call(member()))
        system, user = payload["messages"]
        assert RECORDED_TEXT not in system["content"]
        assert RECORDED_TEXT in user["content"]
        assert user["content"].startswith("<intake:patient_data nonce=")

    def test_cache_salt_rides_the_payload_but_not_the_recording_key(self) -> None:
        one, two = _call(member(), salt="1" * 32), _call(member(), salt="2" * 32)
        assert render_member_payload(one)["cache_salt"] != render_member_payload(two)["cache_salt"]
        assert one.recording_key == two.recording_key

    def test_replay_reads_the_recorded_output(self) -> None:
        completion = asyncio.run(RecordedMemberTransport(RECORDED).complete(_call(member())))
        parsed = parse_member_output(
            completion.text, transcript=PatientData(text=RECORDED_TEXT), scope=scope()
        )
        assert [(r.ref, r.reading) for r in parsed.readings] == [
            (BELIRTI, Reading.QUALIFIED_PRESENT)
        ]

    def test_wrong_lane_replay_fails(self) -> None:
        other = SelfHostedMember(
            member_id="dogrulayici",
            provider="vllm-tr",
            model_id="sentetik/verifier",
            revision="r2",
            weights_sha256="d" * 64,
        )
        with pytest.raises(RecordedVerificationMissing):
            asyncio.run(RecordedMemberTransport(RECORDED).complete(_call(other)))

    def test_a_recording_relabelled_for_another_lane_is_a_mismatch(self, tmp_path: Path) -> None:
        call = _call(member())
        body = json.loads((RECORDED / f"{call.recording_key}.json").read_text(encoding="utf-8"))
        body["model"] = "sentetik/verifier@r9"
        (tmp_path / f"{call.recording_key}.json").write_text(json.dumps(body), encoding="utf-8")
        with pytest.raises(RecordedVerificationMismatch):
            asyncio.run(RecordedMemberTransport(tmp_path).complete(call))

"""INT-428 / ADR-035 — the Model lanes module through ``/admin/model-lanes/*``.

On the services/api unit-lane app (the INT-180 gate: recorded Keycloak claims,
the IP allow-list, the role matrix, the write-ahead hash-chained audit):

- **Narrowing is one key:** disabling hosted lanes and the one-click switch to
  GPU — the latter refused unless the self-hosted identity is healthy.
- **Widening is two:** a route-and-model switch and a provider key each open
  a ceremony that changes nothing until a distinct human approves; the
  requester cannot approve their own; every step is an audit row and the
  chain verifies.
- **The approval binds to the config hash:** a qualification withdrawn while
  the ceremony waited refuses the approval.
- **The swap gate:** a gated lane cannot be switched to a model version with
  no green red-flag extraction goldens and negation-set runs.
- **The key is never echoed:** not in a response, a brief, an audit row or a
  log line; the console shows the last four characters.
- **No mock, and no hosted lane for real PHI.**
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from admin_harness import bearer, build_admin_harness, build_admin_wiring
from api_harness import ApiHarness
from intake_platform.audit import verify_entries
from intake_platform.model_lanes import (
    Lane,
    ProviderId,
    QualificationRegistry,
    TenantDataClass,
)
from intake_platform.model_lanes.wiring import ModelLanesWiring
from model_lanes_kit import LLM_SNAPSHOT, TEST_KEY, Lanes, build_lanes, green
from prometheus_client import REGISTRY

REASON = {
    "reason_class": "incident_mitigation",
    "justification": "The GPU lane is down; route the synthetic stress run elsewhere.",
}


def _assertion() -> str:
    return f"assn-{uuid.uuid4().hex}"


def _changes(control: str, outcome: str) -> float:
    return (
        REGISTRY.get_sample_value(
            "admin_model_lane_changes_total", {"control": control, "outcome": outcome}
        )
        or 0.0
    )


@pytest.fixture()
def lanes() -> Lanes:
    return build_lanes(served=False)


@pytest.fixture()
def harness(tmp_path: Path, lanes: Lanes) -> Iterator[ApiHarness]:
    wiring = build_admin_wiring()
    wiring.model_lanes = ModelLanesWiring(store=lanes.store, router=lanes.router)
    yield from build_admin_harness(tmp_path, admin=wiring)


def _switch(client: Any, role: str, body: dict[str, Any], who: str = "platform_admin") -> Any:
    return client.put(
        f"/admin/model-lanes/route/{role}", json={**REASON, **body}, headers=bearer(who)
    )


def _approve(client: Any, path: str, action_id: str, who: str = "qms_owner") -> Any:
    return client.post(
        f"/admin/model-lanes/{path}/{action_id}/approve",
        json={"assertion_id": _assertion()},
        headers=bearer(who),
    )


class TestTheComposite:
    def test_the_read_shows_lanes_models_providers_and_the_deployment(
        self, harness: ApiHarness
    ) -> None:
        response = harness.client.get("/admin/model-lanes", headers=bearer("sre_oncall"))
        assert response.status_code == 200, response.json()
        body = response.json()
        assert body["schema"] == "intake.admin.model_lanes.v1"
        assert [lane["lane"] for lane in body["lanes"]] == ["llm", "asr", "tts"]
        assert body["deployment"]["effective"] == "synthetic"
        assert body["providers"][0]["key"] == {"state": "set", "last4": "WXYZ", "set_at": "t"}
        assert body["models"]["llm"]["gated"] is True
        assert body["models"]["tts"]["gated"] is False
        assert TEST_KEY not in response.text

    def test_an_unwired_module_is_unknown_and_its_writes_are_503(self, tmp_path: Path) -> None:
        for harness in build_admin_harness(tmp_path, admin=build_admin_wiring()):
            read = harness.client.get("/admin/model-lanes", headers=bearer("sre_oncall"))
            assert read.json()["state"] == "unknown"
            write = harness.client.post(
                "/admin/model-lanes/hosted/disable", json=REASON, headers=bearer("sre_oncall")
            )
            assert write.status_code == 503
            assert write.json()["error"] == "model_lanes_unconfigured"


class TestNarrowingIsOneKey:
    def test_disabling_hosted_lanes_is_one_key_and_audited(
        self, harness: ApiHarness, lanes: Lanes
    ) -> None:
        before = _changes("hosted_disable", "applied")
        response = harness.client.post(
            "/admin/model-lanes/hosted/disable", json=REASON, headers=bearer("sre_oncall")
        )
        assert response.status_code == 200, response.json()
        assert lanes.store.read().hosted_disabled
        assert lanes.store.read().data_class is TenantDataClass.SYNTHETIC  # bound on first write
        assert _changes("hosted_disable", "applied") == before + 1
        actions = [entry.action for entry in harness.audit_store.entries()]
        assert actions[-2:] == [
            "admin.model_lanes.hosted.disable.intent",
            "admin.model_lanes.hosted.disable.success",
        ]

    def test_the_switch_to_gpu_refuses_unless_the_identity_is_healthy(
        self, harness: ApiHarness
    ) -> None:
        response = harness.client.post(
            "/admin/model-lanes/self-hosted",
            json={**REASON, "lanes": ["tts"]},
            headers=bearer("sre_oncall"),
        )
        assert response.status_code == 409
        assert response.json()["error"] == "model_lanes_self_hosted_not_healthy"

    def test_near_miss_a_healthy_identity_switches_in_one_click(
        self, harness: ApiHarness, lanes: Lanes
    ) -> None:
        from model_lanes_kit import identity_of

        lanes.identities[Lane.TTS] = identity_of(lanes.rows[Lane.TTS])
        # put tts on hosted first (tts is ungated), approved by a second human
        opened = _switch(harness.client, "tts", {"route": "hosted:openai"})
        assert opened.status_code == 200, opened.json()
        assert (
            _approve(harness.client, "route/pending", opened.json()["action_id"]).status_code == 200
        )
        assert lanes.store.read().setting(Lane.TTS).route == "hosted:openai"
        response = harness.client.post(
            "/admin/model-lanes/self-hosted",
            json={**REASON, "lanes": ["tts"]},
            headers=bearer("sre_oncall"),
        )
        assert response.status_code == 200, response.json()
        assert response.json()["changed"] is True
        assert lanes.store.read().setting(Lane.TTS).route == "self_hosted"


class TestWideningIsFourEyes:
    def test_a_route_switch_changes_nothing_until_a_second_human_approves(
        self, harness: ApiHarness, lanes: Lanes
    ) -> None:
        opened = _switch(
            harness.client, "tts", {"route": "hosted:openai", "model": "gpt-4o-mini-tts"}
        )
        assert opened.status_code == 200, opened.json()
        assert lanes.store.read().setting(Lane.TTS).route == "self_hosted"
        brief = harness.client.get(
            f"/admin/model-lanes/pending/{opened.json()['action_id']}", headers=bearer("auditor")
        ).json()
        assert brief["evidence"]["model_version"] == "2025-12-15"
        assert len(brief["evidence"]["config_hash"]) == 64
        approved = _approve(harness.client, "route/pending", opened.json()["action_id"])
        assert approved.status_code == 200, approved.json()
        setting = lanes.store.read().setting(Lane.TTS)
        assert (setting.route, setting.model) == ("hosted:openai", "gpt-4o-mini-tts")
        assert lanes.store.read().approved_by is not None
        entries = tuple(harness.audit_store.entries())
        actions = [entry.action for entry in entries]
        assert "admin.model_lanes.route.switch.success" in actions
        assert "admin.model_lanes.route.switch.approve.success" in actions
        assert verify_entries(entries).ok

    def test_the_requester_cannot_approve_their_own_switch(self, harness: ApiHarness) -> None:
        opened = _switch(harness.client, "tts", {"route": "hosted:openai"}, who="platform_owner")
        assert opened.status_code == 200, opened.json()
        refused = _approve(
            harness.client, "route/pending", opened.json()["action_id"], who="platform_owner"
        )
        assert refused.status_code == 409
        assert refused.json()["error"].startswith("four_eyes")

    def test_a_role_gets_its_own_provider_and_model(
        self, harness: ApiHarness, lanes: Lanes
    ) -> None:
        opened = _switch(harness.client, "tts.council.voice", {"route": "hosted:openai"})
        assert (
            _approve(harness.client, "route/pending", opened.json()["action_id"]).status_code == 200
        )
        assert lanes.store.read().roles["tts.council.voice"].route == "hosted:openai"
        assert lanes.store.read().setting(Lane.TTS).route == "self_hosted"

    @pytest.mark.parametrize(
        ("body", "status", "code"),
        [
            ({"route": "mock"}, 422, "model_lanes_route_unknown"),
            ({"route": "hosted:openai", "model": "gpt-4o-mini"}, 409, "model_not_allowed"),
            ({"route": "hosted:openai", "temperature": 1}, 422, "model_lanes_unexpected_field"),
        ],
    )
    def test_closed_bodies_and_closed_values(
        self, harness: ApiHarness, body: dict[str, Any], status: int, code: str
    ) -> None:
        response = _switch(harness.client, "tts", body)
        assert (response.status_code, response.json()["error"]) == (status, code)


class TestTheSwapGate:
    def test_lane_swap_requires_green_rf_extraction_goldens(
        self, harness: ApiHarness, lanes: Lanes
    ) -> None:
        response = _switch(harness.client, "llm", {"route": "hosted:openai"})
        assert response.status_code == 409
        assert response.json()["error"] == "model_not_qualified"
        assert lanes.store.read().setting(Lane.LLM).route == "self_hosted"

    def test_near_miss_a_green_row_for_that_exact_snapshot_opens_the_ceremony(
        self, harness: ApiHarness, lanes: Lanes
    ) -> None:
        ref = LLM_SNAPSHOT.ref(ProviderId.OPENAI)
        lanes.router.qualifications = QualificationRegistry(
            gated_lanes=frozenset({Lane.LLM, Lane.ASR}), rows=(green(Lane.LLM, ref),)
        )
        response = _switch(harness.client, "llm", {"route": "hosted:openai"})
        assert response.status_code == 200, response.json()
        brief = harness.client.get(
            f"/admin/model-lanes/pending/{response.json()['action_id']}", headers=bearer("auditor")
        ).json()
        assert brief["evidence"]["model_eval_runs"] == "rf-goldens-run-1+rf-goldens-run-1-neg"

    def test_the_approval_binds_to_the_config_hash(self, harness: ApiHarness, lanes: Lanes) -> None:
        ref = LLM_SNAPSHOT.ref(ProviderId.OPENAI)
        lanes.router.qualifications = QualificationRegistry(
            gated_lanes=frozenset({Lane.LLM}), rows=(green(Lane.LLM, ref),)
        )
        opened = _switch(harness.client, "llm", {"route": "hosted:openai"})
        assert opened.status_code == 200
        # the qualification is withdrawn while the ceremony waits
        lanes.router.qualifications = QualificationRegistry.gating(Lane.LLM)
        refused = _approve(harness.client, "route/pending", opened.json()["action_id"])
        assert refused.status_code == 409
        assert refused.json()["error"] == "model_not_qualified"
        # re-qualified under another eval run: a different decision, refused too
        lanes.router.qualifications = QualificationRegistry(
            gated_lanes=frozenset({Lane.LLM}), rows=(green(Lane.LLM, ref, run="rerun-2"),)
        )
        refused = _approve(harness.client, "route/pending", opened.json()["action_id"])
        assert refused.json()["error"] == "model_lanes_config_changed"
        assert lanes.store.read().setting(Lane.LLM).route == "self_hosted"


class TestTheKeyIsNeverEchoed:
    def test_the_key_set_ceremony_never_echoes_the_key(
        self, harness: ApiHarness, lanes: Lanes, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG)
        fresh = "sk-test-fresh-unit-lane-" + "q" * 20 + "ABCD"
        opened = harness.client.put(
            "/admin/model-lanes/keys/openai",
            json={**REASON, "api_key": fresh},
            headers=bearer("platform_admin"),
        )
        assert opened.status_code == 200, opened.json()
        assert opened.json()["key"] == {"state": "staged", "last4": "ABCD"}
        action_id = opened.json()["action_id"]
        brief = harness.client.get(
            f"/admin/model-lanes/pending/{action_id}", headers=bearer("auditor")
        )
        approved = _approve(harness.client, "keys/pending", action_id)
        assert approved.status_code == 200, approved.json()
        assert approved.json()["key"]["last4"] == "ABCD"
        read = harness.client.get("/admin/model-lanes", headers=bearer("sre_oncall"))
        for text in (opened.text, brief.text, approved.text, read.text, caplog.text):
            assert fresh not in text
        for entry in harness.audit_store.entries():
            assert fresh not in " ".join(
                (entry.actor, entry.action, entry.resource_ref, entry.consent_scope_ref)
            )
        # the key lives in OpenBao only, and the staged copy is destroyed
        assert lanes.kv.data["model-lanes/providers/openai"]["api_key"] == fresh
        assert not any(path.startswith("model-lanes/staged/") for path in lanes.kv.data)

    def test_a_malformed_key_is_refused_by_rule_not_by_value(self, harness: ApiHarness) -> None:
        bad = "not a key with spaces " + "x" * 10
        response = harness.client.put(
            "/admin/model-lanes/keys/openai",
            json={**REASON, "api_key": bad},
            headers=bearer("platform_admin"),
        )
        assert response.status_code == 422
        assert response.json()["error"] == "model_lanes_key_malformed"
        assert bad not in response.text


class TestRealPhiDeployment:
    @pytest.fixture()
    def lanes(self) -> Lanes:
        return build_lanes(declared=TenantDataClass.REAL_PHI, served=False)

    def test_a_hosted_switch_and_a_key_never_open(self, harness: ApiHarness) -> None:
        switch = _switch(harness.client, "tts", {"route": "hosted:openai"})
        assert (switch.status_code, switch.json()["error"]) == (409, "hosted_lane_real_phi_refused")
        fallback = _switch(harness.client, "tts", {"route": "self_hosted", "fallback": "openai"})
        assert fallback.json()["error"] == "hosted_lane_real_phi_refused"
        key = harness.client.put(
            "/admin/model-lanes/keys/openai",
            json={**REASON, "api_key": TEST_KEY},
            headers=bearer("platform_admin"),
        )
        assert (key.status_code, key.json()["error"]) == (409, "hosted_lane_real_phi_refused")

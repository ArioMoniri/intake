"""INT-182 — the voice kill switch flips a tenant to typed without a deploy.

Acceptance, verbatim (docs/backlog/issues.yaml, INT-182):
  *"per-profile metrics; kill switch flips tenant to typed without deploy (test)"*

The "without deploy" half is proven end to end and on the real path: the
admin route writes the tenant's control through ``/admin/voice/*`` (audited,
role-guarded), and the runtime's own session-start path —
:class:`~intake_voice_runtime.session_router.VoiceSessionRouter` over the
shipped ``build_residency_tr_session`` / ``build_typed_session`` — reads it on
a router that is never rebuilt. The two sides share a store the way two
processes share Redis: two clients on one (fake) server, in tests only.

**Asymmetric authority, as files/08 §0c F17 and §8.2 decided it.** Engaging
the kill switch moves a tenant to the *safer* transport and is tier 1 — one
``sre_oncall``, ``clinical_lead`` or ``platform_owner``, audited, no second
approver, because a second key at 03:00 on the safe direction is an
availability control on a safety control. Everything that moves a tenant
*toward* voice — releasing the switch, switching the default profile,
setting a canary weight — is tier 2, and **one person cannot do it**: the
self-approval, the second tab on the same credential, and the wrong role are
each refused, and the control does not move.

**Only profiles that exist** (CLAUDE.md invariant 19): ``residency_tr`` and
``typed``. Anything else is refused before a ceremony opens. Canary weights
are integers in 0..100, default 0.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import fakeredis
import pytest
from admin_harness import bearer, build_admin_harness, build_admin_wiring
from api_harness import ApiHarness
from intake_platform.admin import (
    DANGEROUS_ACTIONS,
    ActionDirection,
    ActionTier,
    AdminRole,
)
from intake_platform.admin.actions import (
    VOICE_CANARY_SET,
    VOICE_KILL_SWITCH_ENGAGE,
    VOICE_KILL_SWITCH_RELEASE,
    VOICE_PROFILE_SWITCH,
)
from intake_platform.slo import load_metrics_catalog
from intake_platform.voice_control import RedisVoiceControlStore, VoiceControlProfile
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.resilience import TYPED_FALLBACK_DEADLINE_MS
from intake_voice_runtime.session_router import RouteReason, VoiceSessionRouter
from intake_voice_runtime.typed import LaneSwitchReason
from prometheus_client import REGISTRY
from session_harness import builders
from step_up_fakes import StepUpHarness
from talker_harness import FakeClock

TENANT = "tenant-a"
OTHER_TENANT = "tenant-c"
INCIDENT = {
    "reason_class": "incident_mitigation",
    "justification": "TTS lane degraded on the bridge; moving this tenant to the keyboard.",
}
ROLLOUT = {
    "reason_class": "rollout_expansion",
    "justification": "Pilot clinic signed off the voice lane after the dry run.",
}


#: INT-563: approvals go through the step-up, the console's own sequence.
STEP_UP = StepUpHarness.build()


def _sample(name: str, labels: dict[str, str] | None = None) -> float:
    return REGISTRY.get_sample_value(name, labels or {}) or 0.0


@pytest.fixture()
def server() -> fakeredis.FakeServer:
    return fakeredis.FakeServer()


def _store(server: fakeredis.FakeServer) -> RedisVoiceControlStore:
    """One process's client on the shared store."""
    return RedisVoiceControlStore(fakeredis.FakeRedis(server=server))


@pytest.fixture()
def harness(tmp_path: Path, server: fakeredis.FakeServer) -> Iterator[ApiHarness]:
    yield from build_admin_harness(
        tmp_path,
        admin=build_admin_wiring(voice_controls=_store(server), step_up=STEP_UP.service),
    )


def _engage(client: Any, role: str = "sre_oncall", tenant: str = TENANT) -> Any:
    return client.post(
        "/admin/voice/kill-switch", json={"tenant": tenant, **INCIDENT}, headers=bearer(role)
    )


def _approve(client: Any, route: str, action_id: str, role: str) -> Any:
    return STEP_UP.approve(client, f"{route}/{action_id}/approve", action_id, role)


def _enable_voice(client: Any, tenant: str = TENANT) -> None:
    """Put a tenant on residency_tr: requested by one human, approved by another."""
    opened = client.put(
        f"/admin/voice/profile/{tenant}",
        json={"profile": "residency_tr", **ROLLOUT},
        headers=bearer("clinical_lead"),
    )
    assert opened.status_code == 200, opened.json()
    approved = _approve(
        client, "/admin/voice/profile/pending", opened.json()["action_id"], "qms_owner"
    )
    assert approved.status_code == 200, approved.json()


def _start(router: VoiceSessionRouter, clock: FakeClock, session_id: str, tenant: str = TENANT):  # type: ignore[no-untyped-def]
    return router.start(
        tenant_id=tenant,
        session_id=session_id,
        builders=builders(tenant_id=tenant, session_id=session_id, clock=clock),
    )


# =====================================================================================
# 1 · Without a deploy: the runtime reads the control at every session start
# =====================================================================================


class TestKillSwitchWithoutDeploy:
    def test_the_next_session_after_the_switch_is_typed_on_the_same_router(
        self, harness: ApiHarness, server: fakeredis.FakeServer
    ) -> None:
        client = harness.client
        _enable_voice(client)
        clock = FakeClock()
        router = VoiceSessionRouter(controls=_store(server), clock=clock)

        before = _start(router, clock, "sess-before")
        assert before.stack.profile is VoiceProfile.RESIDENCY_TR

        engaged = _engage(client)
        assert engaged.status_code == 200, engaged.json()
        assert engaged.json()["control"]["kill_switch"] is True

        after = _start(router, clock, "sess-after")
        assert after.stack.profile is VoiceProfile.TYPED
        assert after.decision.reason is RouteReason.KILL_SWITCH

    def test_another_tenant_is_untouched(
        self, harness: ApiHarness, server: fakeredis.FakeServer
    ) -> None:
        client = harness.client
        _enable_voice(client, TENANT)
        _enable_voice(client, OTHER_TENANT)
        assert _engage(client, tenant=TENANT).status_code == 200
        clock = FakeClock()
        router = VoiceSessionRouter(controls=_store(server), clock=clock)
        assert _start(router, clock, "s-a").stack.profile is VoiceProfile.TYPED
        assert (
            _start(router, clock, "s-c", tenant=OTHER_TENANT).stack.profile
            is VoiceProfile.RESIDENCY_TR
        )

    def test_an_in_flight_voice_session_goes_typed_inside_the_2s_budget(
        self, harness: ApiHarness, server: fakeredis.FakeServer
    ) -> None:
        """In-flight sessions take INT-096/INT-100's switch path — the same
        ``fall_back_to_typed`` the failover ladder uses, with the operator
        reason — and the flip lands within one poll of the write."""
        client = harness.client
        _enable_voice(client)
        clock = FakeClock()
        router = VoiceSessionRouter(controls=_store(server), clock=clock)
        live = _start(router, clock, "sess-live")
        assert live.stack.profile is VoiceProfile.RESIDENCY_TR
        engaged_at: list[float] = []

        async def main() -> None:
            watcher = asyncio.ensure_future(router.watch())
            await clock.sleep(0.4)
            assert _engage(client).status_code == 200
            engaged_at.append(clock.now_ms())
            await clock.sleep(TYPED_FALLBACK_DEADLINE_MS / 1000.0)
            watcher.cancel()

        clock.run(main())
        session = live.stack.session
        assert live.stack.profile is VoiceProfile.TYPED
        assert session.modality_switch is not None
        assert session.modality_switch.reason is LaneSwitchReason.OPERATOR_KILL_SWITCH
        assert session.modality_switch.at_ms - engaged_at[0] <= TYPED_FALLBACK_DEADLINE_MS

    def test_the_route_count_reflects_the_kill_switch(
        self, harness: ApiHarness, server: fakeredis.FakeServer
    ) -> None:
        client = harness.client
        _enable_voice(client)
        assert _engage(client).status_code == 200
        labels = {"tenant": TENANT, "profile": "typed", "reason": "kill_switch"}
        before = _sample("voice_session_routes_total", labels)
        clock = FakeClock()
        _start(VoiceSessionRouter(controls=_store(server), clock=clock), clock, "s-count")
        assert _sample("voice_session_routes_total", labels) == before + 1


# =====================================================================================
# 2 · The dangerous direction takes two distinct humans
# =====================================================================================


class TestOnePersonCannotMoveTowardVoice:
    def _release(self, client: Any, role: str = "clinical_lead") -> Any:
        return client.post(
            "/admin/voice/kill-switch/release",
            json={"tenant": TENANT, **ROLLOUT},
            headers=bearer(role),
        )

    def test_the_requester_cannot_approve_their_own_release(
        self, harness: ApiHarness, server: fakeredis.FakeServer
    ) -> None:
        client = harness.client
        _enable_voice(client)
        assert _engage(client).status_code == 200
        opened = self._release(client)
        assert opened.status_code == 200, opened.json()
        attempts = _sample("admin_four_eyes_self_approval_attempt_total")
        refused = _approve(
            client, "/admin/voice/kill-switch/release", opened.json()["action_id"], "clinical_lead"
        )
        assert refused.status_code == 409
        assert refused.json()["error"] == "four_eyes_self_approval"
        assert _sample("admin_four_eyes_self_approval_attempt_total") == attempts + 1
        assert _store(server).read(TENANT).kill_switch is True

    def test_a_second_tab_on_the_same_credential_is_not_a_second_human(
        self, harness: ApiHarness, server: fakeredis.FakeServer
    ) -> None:
        client = harness.client
        _enable_voice(client)
        assert _engage(client).status_code == 200
        opened = self._release(client)
        refused = _approve(
            client,
            "/admin/voice/kill-switch/release",
            opened.json()["action_id"],
            "clinical_lead_second_tab",
        )
        # the same subject on the same credential in another session: the
        # ceremony names it for what it is — the requester approving themself
        assert refused.status_code == 409
        assert refused.json()["error"] == "four_eyes_self_approval"
        assert _store(server).read(TENANT).kill_switch is True

    def test_a_distinct_second_human_releases_it_and_voice_resumes(
        self, harness: ApiHarness, server: fakeredis.FakeServer
    ) -> None:
        client = harness.client
        _enable_voice(client)
        assert _engage(client).status_code == 200
        opened = self._release(client)
        approved = _approve(
            client, "/admin/voice/kill-switch/release", opened.json()["action_id"], "qms_owner"
        )
        assert approved.status_code == 200, approved.json()
        control = approved.json()["control"]
        assert control["kill_switch"] is False
        assert control["approved_by"] != control["changed_by"]
        clock = FakeClock()
        router = VoiceSessionRouter(controls=_store(server), clock=clock)
        assert _start(router, clock, "s-resumed").stack.profile is VoiceProfile.RESIDENCY_TR

    def test_sre_oncall_may_pull_the_switch_but_not_request_its_release(
        self, harness: ApiHarness
    ) -> None:
        client = harness.client
        assert _engage(client, role="sre_oncall").status_code == 200
        refused = self._release(client, role="sre_oncall")
        assert refused.status_code == 403
        assert refused.json()["error"] == "forbidden"

    def test_release_of_a_switch_that_is_not_engaged_is_refused(self, harness: ApiHarness) -> None:
        refused = self._release(harness.client)
        assert refused.status_code == 409
        assert refused.json()["error"] == "voice_kill_switch_not_engaged"

    def test_one_person_cannot_switch_the_default_profile(
        self, harness: ApiHarness, server: fakeredis.FakeServer
    ) -> None:
        client = harness.client
        opened = client.put(
            f"/admin/voice/profile/{TENANT}",
            json={"profile": "residency_tr", **ROLLOUT},
            headers=bearer("clinical_lead"),
        )
        refused = _approve(
            client, "/admin/voice/profile/pending", opened.json()["action_id"], "clinical_lead"
        )
        assert refused.json()["error"] == "four_eyes_self_approval"
        assert _store(server).read(TENANT).default_profile is VoiceControlProfile.TYPED

    def test_one_person_cannot_set_a_canary_weight(
        self, harness: ApiHarness, server: fakeredis.FakeServer
    ) -> None:
        client = harness.client
        opened = client.put(
            f"/admin/voice/canary/{TENANT}",
            json={"profile": "residency_tr", "weight": 10, **ROLLOUT},
            headers=bearer("platform_owner"),
        )
        assert opened.status_code == 200, opened.json()
        refused = _approve(
            client, "/admin/voice/canary/pending", opened.json()["action_id"], "platform_owner"
        )
        assert refused.json()["error"] == "four_eyes_self_approval"
        assert _store(server).read(TENANT).canary_weight == 0

    def test_a_distinct_approver_sets_the_canary_and_the_runtime_honours_it(
        self, harness: ApiHarness, server: fakeredis.FakeServer
    ) -> None:
        client = harness.client
        opened = client.put(
            f"/admin/voice/canary/{TENANT}",
            json={"profile": "residency_tr", "weight": 100, **ROLLOUT},
            headers=bearer("platform_owner"),
        )
        approved = _approve(
            client, "/admin/voice/canary/pending", opened.json()["action_id"], "clinical_lead"
        )
        assert approved.status_code == 200, approved.json()
        clock = FakeClock()
        routed = _start(VoiceSessionRouter(controls=_store(server), clock=clock), clock, "s-can")
        assert routed.decision.reason is RouteReason.CANARY
        assert routed.stack.profile is VoiceProfile.RESIDENCY_TR

    def test_an_approval_through_another_actions_route_is_refused(
        self, harness: ApiHarness, server: fakeredis.FakeServer
    ) -> None:
        client = harness.client
        opened = client.put(
            f"/admin/voice/canary/{TENANT}",
            json={"profile": "residency_tr", "weight": 10, **ROLLOUT},
            headers=bearer("clinical_lead"),
        )
        crossed = _approve(
            client, "/admin/voice/profile/pending", opened.json()["action_id"], "qms_owner"
        )
        assert crossed.status_code == 409
        assert crossed.json()["error"] == "voice_action_mismatch"
        # the ceremony was not consumed by the wrong route
        approved = _approve(
            client, "/admin/voice/canary/pending", opened.json()["action_id"], "qms_owner"
        )
        assert approved.status_code == 200
        assert _store(server).read(TENANT).canary_weight == 10

    def test_an_approval_after_the_control_moved_is_refused(
        self, harness: ApiHarness, server: fakeredis.FakeServer
    ) -> None:
        """The approver approves what the brief showed them. A kill switch
        pulled after the request moves the revision, and the approval of the
        now-stale request is refused rather than applied over it."""
        client = harness.client
        opened = client.put(
            f"/admin/voice/profile/{TENANT}",
            json={"profile": "residency_tr", **ROLLOUT},
            headers=bearer("clinical_lead"),
        )
        assert _engage(client).status_code == 200
        stale = _approve(
            client, "/admin/voice/profile/pending", opened.json()["action_id"], "qms_owner"
        )
        assert stale.status_code == 409
        assert stale.json()["error"] == "voice_control_changed"
        assert _store(server).read(TENANT).default_profile is VoiceControlProfile.TYPED


# =====================================================================================
# 3 · The safe direction takes one key
# =====================================================================================


class TestAsymmetricAuthority:
    def test_the_registry_declares_engage_t1_safe_and_the_rest_t2_dangerous(self) -> None:
        assert VOICE_KILL_SWITCH_ENGAGE.tier is ActionTier.T1
        assert VOICE_KILL_SWITCH_ENGAGE.direction is ActionDirection.SAFE
        assert VOICE_KILL_SWITCH_ENGAGE.approver_roles == frozenset()
        for action in (VOICE_KILL_SWITCH_RELEASE, VOICE_PROFILE_SWITCH, VOICE_CANARY_SET):
            assert action.tier is ActionTier.T2
            assert action.direction is ActionDirection.DANGEROUS
            assert action.id in DANGEROUS_ACTIONS

    def test_the_roles_are_the_ones_files_08_names(self) -> None:
        """§8.2 T1: one sre_oncall or clinical_lead (platform_owner is the
        platform authority above both — the INT-188 precedent). T2 requesters
        and approvers are all-tenant roles; sre_oncall's scope is T1 only."""
        assert VOICE_KILL_SWITCH_ENGAGE.actor_roles == {
            AdminRole.SRE_ONCALL,
            AdminRole.CLINICAL_LEAD,
            AdminRole.PLATFORM_OWNER,
        }
        for action in (VOICE_KILL_SWITCH_RELEASE, VOICE_PROFILE_SWITCH, VOICE_CANARY_SET):
            assert action.actor_roles == {AdminRole.PLATFORM_OWNER, AdminRole.CLINICAL_LEAD}
            assert action.approver_roles == {
                AdminRole.PLATFORM_OWNER,
                AdminRole.CLINICAL_LEAD,
                AdminRole.QMS_OWNER,
            }
            assert AdminRole.SRE_ONCALL not in action.actor_roles | action.approver_roles

    def test_every_voice_action_links_a_runbook_that_exists_and_a_catalogued_alert(
        self,
    ) -> None:
        """files/08 §8.2: "a registry entry without a runbook link and an
        alert" fails CI. The link must resolve and the alert must be a
        catalogued series, or the page nobody can answer is still a page."""
        repo = Path(__file__).resolve().parents[2]
        catalog = load_metrics_catalog(repo / "observability" / "metrics_catalog.yaml")
        spec_ids = {metric.spec_id for metric in catalog.metrics}
        for action in (
            VOICE_KILL_SWITCH_ENGAGE,
            VOICE_KILL_SWITCH_RELEASE,
            VOICE_PROFILE_SWITCH,
            VOICE_CANARY_SET,
        ):
            assert (repo / action.runbook).is_file(), action.runbook
            assert action.alert_metric in spec_ids, action.alert_metric

    def test_one_sre_pulls_it_alone_and_no_ceremony_opens(
        self, harness: ApiHarness, server: fakeredis.FakeServer
    ) -> None:
        engaged = _engage(harness.client, role="sre_oncall")
        assert engaged.status_code == 200
        body = engaged.json()
        assert body["changed"] is True
        assert "action_id" not in body
        control = _store(server).read(TENANT)
        assert control.kill_switch is True
        assert control.approved_by is None

    def test_pulling_it_twice_changes_nothing_the_second_time(
        self, harness: ApiHarness, server: fakeredis.FakeServer
    ) -> None:
        assert _engage(harness.client).json()["changed"] is True
        revision = _store(server).read(TENANT).revision
        again = _engage(harness.client, role="clinical_lead")
        assert again.status_code == 200
        assert again.json()["changed"] is False
        assert _store(server).read(TENANT).revision == revision

    @pytest.mark.parametrize("role", ["researcher", "auditor", "tenant_admin", "qms_owner"])
    def test_a_role_outside_the_t1_set_cannot_pull_it(
        self, harness: ApiHarness, server: fakeredis.FakeServer, role: str
    ) -> None:
        refused = _engage(harness.client, role=role)
        assert refused.status_code == 403
        assert _store(server).read(TENANT).kill_switch is False

    def test_a_reason_is_mandatory_even_on_the_safe_direction(self, harness: ApiHarness) -> None:
        refused = harness.client.post(
            "/admin/voice/kill-switch",
            json={"tenant": TENANT, "reason_class": "incident_mitigation", "justification": " "},
            headers=bearer("sre_oncall"),
        )
        assert refused.status_code == 422
        assert refused.json()["error"] == "flag_change_reason_missing"


# =====================================================================================
# 4 · Only profiles that exist; weights in bounds
# =====================================================================================


class TestOnlyProfilesThatExist:
    @pytest.mark.parametrize(
        "profile", ["cloud_realtime", "TYPED", "residency_tr ", "", "speech_to_speech"]
    )
    def test_a_profile_switch_to_a_profile_that_does_not_exist_is_refused(
        self, harness: ApiHarness, profile: str
    ) -> None:
        refused = harness.client.put(
            f"/admin/voice/profile/{TENANT}",
            json={"profile": profile, **ROLLOUT},
            headers=bearer("clinical_lead"),
        )
        assert refused.status_code == 422
        assert refused.json()["error"] == "voice_profile_unknown"
        assert (
            harness.client.get("/admin/voice", headers=bearer("sre_oncall")).json()["tiles"][
                "pending"
            ]["actions"]
            == []
        )

    def test_a_canary_of_a_profile_that_does_not_exist_is_refused(
        self, harness: ApiHarness
    ) -> None:
        refused = harness.client.put(
            f"/admin/voice/canary/{TENANT}",
            json={"profile": "cloud_realtime", "weight": 5, **ROLLOUT},
            headers=bearer("clinical_lead"),
        )
        assert refused.status_code == 422
        assert refused.json()["error"] == "voice_profile_unknown"

    @pytest.mark.parametrize("weight", [-1, 101, 50.5, "50", True, None])
    def test_a_weight_outside_zero_to_one_hundred_is_refused(
        self, harness: ApiHarness, weight: object
    ) -> None:
        refused = harness.client.put(
            f"/admin/voice/canary/{TENANT}",
            json={"profile": "residency_tr", "weight": weight, **ROLLOUT},
            headers=bearer("clinical_lead"),
        )
        assert refused.status_code == 422
        assert refused.json()["error"] == "voice_canary_weight_out_of_bounds"

    @pytest.mark.parametrize("weight", [0, 1, 100])
    def test_the_bounds_themselves_are_accepted(self, harness: ApiHarness, weight: int) -> None:
        opened = harness.client.put(
            f"/admin/voice/canary/{TENANT}",
            json={"profile": "residency_tr", "weight": weight, **ROLLOUT},
            headers=bearer("clinical_lead"),
        )
        assert opened.status_code == 200, opened.json()

    def test_a_canary_of_the_default_profile_is_refused(self, harness: ApiHarness) -> None:
        refused = harness.client.put(
            f"/admin/voice/canary/{TENANT}",
            json={"profile": "typed", "weight": 10, **ROLLOUT},
            headers=bearer("clinical_lead"),
        )
        assert refused.status_code == 409
        assert refused.json()["error"] == "voice_canary_is_default"

    def test_a_switch_to_the_profile_already_in_force_is_refused(self, harness: ApiHarness) -> None:
        refused = harness.client.put(
            f"/admin/voice/profile/{TENANT}",
            json={"profile": "typed", **ROLLOUT},
            headers=bearer("clinical_lead"),
        )
        assert refused.status_code == 409
        assert refused.json()["error"] == "voice_profile_unchanged"

    def test_a_body_with_an_unexpected_field_is_refused_by_name(self, harness: ApiHarness) -> None:
        refused = harness.client.post(
            "/admin/voice/kill-switch",
            json={"tenant": TENANT, **INCIDENT, "note": "Ayşe Yılmaz"},
            headers=bearer("sre_oncall"),
        )
        assert refused.status_code == 422
        assert refused.json()["error"] == "voice_unexpected_field"
        assert "Ayşe" not in refused.text

    @pytest.mark.parametrize(
        ("content", "code"),
        [
            (b"not json", "voice_body_not_json"),
            (b'["tenant-a"]', "voice_body_not_an_object"),
            (
                b'{"tenant": "tenant-a", "reason_class": "because", "justification": "x"}',
                "voice_reason_class_unknown",
            ),
        ],
    )
    def test_a_body_that_is_not_the_closed_shape_is_refused(
        self, harness: ApiHarness, content: bytes, code: str
    ) -> None:
        refused = harness.client.post(
            "/admin/voice/kill-switch",
            content=content,
            headers={**bearer("sre_oncall"), "content-type": "application/json"},
        )
        assert refused.status_code == 422
        assert refused.json()["error"] == code

    @pytest.mark.parametrize("tenant", ["Hastane A", "tenant a", "", "../tenant-b"])
    def test_a_tenant_that_is_not_id_shaped_is_refused(
        self, harness: ApiHarness, tenant: str
    ) -> None:
        refused = harness.client.post(
            "/admin/voice/kill-switch",
            json={"tenant": tenant, **INCIDENT},
            headers=bearer("sre_oncall"),
        )
        assert refused.status_code == 422
        assert refused.json()["error"] == "voice_tenant_invalid"


# =====================================================================================
# 5 · Fail closed, audited, no PHI
# =====================================================================================


class TestFailClosedAndAudited:
    def test_the_mutations_answer_503_when_no_store_is_wired(self, tmp_path: Path) -> None:
        for built in build_admin_harness(tmp_path):
            refused = _engage(built.client)
            assert refused.status_code == 503
            assert refused.json()["error"] == "voice_control_unconfigured"

    def test_an_unreachable_store_refuses_rather_than_pretending(
        self, harness: ApiHarness, server: fakeredis.FakeServer
    ) -> None:
        server.connected = False
        refused = _engage(harness.client)
        assert refused.status_code == 503
        assert refused.json()["error"] == "voice_control_unreachable"

    def test_every_voice_mutation_is_audited_write_ahead(self, harness: ApiHarness) -> None:
        assert _engage(harness.client).status_code == 200
        entries = [entry.action for entry in harness.audit_store.entries()]
        assert entries[-2:] == [
            "admin.voice.kill_switch.engage.intent",
            "admin.voice.kill_switch.engage.success",
        ]

    def test_justification_text_reaches_neither_the_chain_nor_the_store(
        self, harness: ApiHarness, server: fakeredis.FakeServer
    ) -> None:
        assert _engage(harness.client).status_code == 200
        raw = b"".join(
            value
            for key in fakeredis.FakeRedis(server=server).keys("*")
            for value in [fakeredis.FakeRedis(server=server).get(key) or b""]
        )
        assert b"degraded" not in raw
        for entry in harness.audit_store.entries():
            assert "degraded" not in " ".join(
                (entry.actor, entry.action, entry.resource_ref, entry.consent_scope_ref)
            )

    def test_the_applied_change_is_counted(self, harness: ApiHarness) -> None:
        labels = {"control": "kill_switch_engage", "outcome": "applied"}
        before = _sample("admin_voice_control_changes_total", labels)
        assert _engage(harness.client).status_code == 200
        assert _sample("admin_voice_control_changes_total", labels) == before + 1

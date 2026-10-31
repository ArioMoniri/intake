"""INT-563 (ADR-043) — the step-up at the API: two routes, one redemption,
and no other way to present a second key.

The ceremony runs the console's own sequence against the unit-lane app
(``step_up_fakes.StepUpHarness``): begin, re-authenticate at the recorded
Keycloak, complete, present the grant. Break-glass is the route under test
here because the API alone carries it end to end; the Voice, CI/CD, Model
lanes and access-review suites approve through the same harness.

The near misses that matter most are the ones that used to pass: an approval
carrying an unused string (the pre-INT-563 ``assertion_id``) is refused, by a
closed body when it uses the old field and by the redemption when it puts the
same string in the new one — and the action stays pending either way.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest
from admin_harness import (
    BREAK_GLASS_BODY,
    bearer,
    build_admin_harness,
    build_admin_wiring,
    recorded_claims,
    token_for,
)
from api_harness import ApiHarness
from intake_platform.admin import ADMIN_ROUTES, DANGEROUS_ACTIONS, ActionDirection, ActionTier
from intake_platform.admin.actions import FOUR_EYES_STEP_UP
from intake_platform.audit import AuditEntry, verify_entries
from intake_platform.slo import load_metrics_catalog
from prometheus_client import REGISTRY
from step_up_fakes import Login, StepUpHarness, login_for

REPO = Path(__file__).resolve().parents[2]
STEP_UP = StepUpHarness.build()


@pytest.fixture()
def harness(tmp_path: Path) -> Iterator[ApiHarness]:
    yield from build_admin_harness(tmp_path, admin=build_admin_wiring(step_up=STEP_UP.service))


def _chain(harness: ApiHarness) -> Sequence[AuditEntry]:
    return harness.audit_store.entries()


def _steps(stage: str, outcome: str) -> float:
    labels = {"stage": stage, "outcome": outcome}
    return REGISTRY.get_sample_value("admin_step_up_total", labels) or 0.0


def _open(client: Any, role: str = "clinical_lead") -> str:
    opened = client.post("/admin/break-glass", json=BREAK_GLASS_BODY, headers=bearer(role))
    assert opened.status_code == 200, opened.json()
    action_id: str = opened.json()["action_id"]
    return action_id


def _approve_url(action_id: str) -> str:
    return f"/admin/break-glass/{action_id}/approve"


def _state(client: Any, action_id: str) -> str:
    brief = client.get(f"/admin/break-glass/{action_id}", headers=bearer("auditor"))
    state: str = brief.json()["state"]
    return state


class TestAnApprovalThroughTheStepUp:
    def test_the_second_key_is_the_one_just_asserted(self, harness: ApiHarness) -> None:
        client = harness.client
        action_id = _open(client)
        before = _steps("redeem", "ok")
        approved = STEP_UP.approve(client, _approve_url(action_id), action_id, "qms_owner")
        assert approved.status_code == 200, approved.json()
        assert approved.json()["state"] == "approved"
        assert _steps("redeem", "ok") == before + 1
        assert _state(client, action_id) == "approved"

    def test_grant_and_use_are_on_the_chain_by_ids_only(self, harness: ApiHarness) -> None:
        client = harness.client
        action_id = _open(client)
        done = STEP_UP.grant(client, "qms_owner", action_id)
        assert done.status_code == 200, done.json()
        grant = done.json()["grant"]
        assert done.json()["action"] == "admin.break_glass.open"
        response = client.post(
            _approve_url(action_id), json={"step_up_grant": grant}, headers=bearer("qms_owner")
        )
        assert response.status_code == 200, response.json()
        rows = [e for e in _chain(harness) if e.action.startswith("admin.four_eyes.step_up.")]
        named = {e.action: e for e in rows if e.action.endswith((".granted", ".redeemed"))}
        assert set(named) == {"admin.four_eyes.step_up.granted", "admin.four_eyes.step_up.redeemed"}
        granted, redeemed = named.values()
        assert granted.actor == redeemed.actor == "kc-sub-qms-owner"
        assert granted.resource_ref == redeemed.resource_ref
        assert granted.resource_ref.startswith(f"four_eyes:{action_id}:stepup:")
        # write-ahead: the use is recorded before the approval's outcome
        outcome = next(
            e for e in _chain(harness) if e.action == "admin.break_glass.approve.success"
        )
        assert redeemed.seq < outcome.seq
        # ids only: neither the bearer grant nor either credential reaches the chain
        account = recorded_claims()[token_for("qms_owner")]
        credentials = (account["credential_id"], login_for(account).credential_id)
        for entry in _chain(harness):
            rendered = " ".join(
                (entry.actor, entry.action, entry.resource_ref, entry.consent_scope_ref)
            )
            assert grant not in rendered
            assert not any(credential in rendered for credential in credentials)
        assert verify_entries(_chain(harness)).ok


class TestTheOldPathIsGone:
    def test_an_unused_string_in_the_old_field_is_refused(self, harness: ApiHarness) -> None:
        client = harness.client
        action_id = _open(client)
        refused = client.post(
            _approve_url(action_id),
            json={"assertion_id": "assert-fresh-1"},
            headers=bearer("qms_owner"),
        )
        assert refused.status_code == 422
        assert refused.json()["error"] == "step_up_grant_required"
        assert _state(client, action_id) == "pending"

    def test_the_same_string_in_the_new_field_is_refused(self, harness: ApiHarness) -> None:
        client = harness.client
        action_id = _open(client)
        before = _steps("redeem", "step_up_unknown")
        refused = client.post(
            _approve_url(action_id),
            json={"step_up_grant": "assert-fresh-1"},
            headers=bearer("qms_owner"),
        )
        assert refused.status_code == 403
        assert refused.json()["error"] == "step_up_unknown"
        assert _steps("redeem", "step_up_unknown") == before + 1
        assert _state(client, action_id) == "pending"

    def test_both_fields_together_are_refused(self, harness: ApiHarness) -> None:
        client = harness.client
        action_id = _open(client)
        grant = STEP_UP.grant(client, "qms_owner", action_id).json()["grant"]
        refused = client.post(
            _approve_url(action_id),
            json={"step_up_grant": grant, "assertion_id": "assert-fresh-1"},
            headers=bearer("qms_owner"),
        )
        assert refused.status_code == 422
        assert _state(client, action_id) == "pending"

    def test_no_step_up_wired_means_no_approval_at_all(self, tmp_path: Path) -> None:
        for harness in build_admin_harness(tmp_path):
            action_id = _open(harness.client)
            refused = harness.client.post(
                _approve_url(action_id),
                json={"step_up_grant": "sug_" + "0" * 32},
                headers=bearer("qms_owner"),
            )
            assert refused.status_code == 503
            assert refused.json()["error"] == "step_up_unconfigured"
            begun = harness.client.post(
                "/admin/step-up", json={"action_id": action_id}, headers=bearer("qms_owner")
            )
            assert begun.status_code == 503
            assert _state(harness.client, action_id) == "pending"


class TestAGrantIsBound:
    def test_it_is_spent_once(self, harness: ApiHarness) -> None:
        client = harness.client
        action_id = _open(client)
        grant = STEP_UP.grant(client, "qms_owner", action_id).json()["grant"]
        url = _approve_url(action_id)
        assert (
            client.post(url, json={"step_up_grant": grant}, headers=bearer("qms_owner")).status_code
            == 200
        )
        again = client.post(url, json={"step_up_grant": grant}, headers=bearer("qms_owner"))
        assert (again.status_code, again.json()["error"]) == (403, "step_up_unknown")

    def test_to_its_action(self, harness: ApiHarness) -> None:
        client = harness.client
        first, second = _open(client), _open(client)
        grant = STEP_UP.grant(client, "qms_owner", first).json()["grant"]
        crossed = client.post(
            _approve_url(second), json={"step_up_grant": grant}, headers=bearer("qms_owner")
        )
        assert (crossed.status_code, crossed.json()["error"]) == (403, "step_up_unknown")
        assert _state(client, second) == "pending"
        # and it was not burnt by the crossed attempt
        own = client.post(
            _approve_url(first), json={"step_up_grant": grant}, headers=bearer("qms_owner")
        )
        assert own.status_code == 200

    def test_to_its_caller(self, harness: ApiHarness) -> None:
        client = harness.client
        action_id = _open(client)
        grant = STEP_UP.grant(client, "qms_owner", action_id).json()["grant"]
        stolen = client.post(
            _approve_url(action_id),
            json={"step_up_grant": grant},
            headers=bearer("compliance_officer"),
        )
        assert (stolen.status_code, stolen.json()["error"]) == (403, "step_up_unknown")
        assert _state(client, action_id) == "pending"


class TestBeginRefusesWhatCouldNeverPass:
    def test_the_requester_is_refused_and_counted(self, harness: ApiHarness) -> None:
        client = harness.client
        action_id = _open(client)
        before = REGISTRY.get_sample_value("admin_four_eyes_self_approval_attempt_total") or 0.0
        refused = STEP_UP.grant(client, "clinical_lead", action_id)
        assert (refused.status_code, refused.json()["error"]) == (409, "four_eyes_self_approval")
        after = REGISTRY.get_sample_value("admin_four_eyes_self_approval_attempt_total")
        assert after == before + 1

    def test_the_requester_in_a_second_tab_is_the_requester(self, harness: ApiHarness) -> None:
        action_id = _open(harness.client)
        refused = STEP_UP.grant(harness.client, "clinical_lead_second_tab", action_id)
        assert (refused.status_code, refused.json()["error"]) == (409, "four_eyes_self_approval")

    def test_a_role_that_is_no_second_key_for_this_action(self, harness: ApiHarness) -> None:
        # platform_owner may step up for other ceremonies, not for break-glass
        action_id = _open(harness.client)
        refused = STEP_UP.grant(harness.client, "platform_owner", action_id)
        assert (refused.status_code, refused.json()["error"]) == (409, "four_eyes_approver_role")

    @pytest.mark.parametrize("action_id", ["0" * 32, "not-an-action", "A" * 32])
    def test_an_action_nothing_minted(self, harness: ApiHarness, action_id: str) -> None:
        refused = harness.client.post(
            "/admin/step-up", json={"action_id": action_id}, headers=bearer("qms_owner")
        )
        assert refused.status_code == 404

    @pytest.mark.parametrize(
        "body", [{}, {"action_id": 7}, {"action_id": "a" * 32, "role": "platform_owner"}]
    )
    def test_a_body_that_is_not_exactly_the_action(
        self, harness: ApiHarness, body: dict[str, Any]
    ) -> None:
        refused = harness.client.post("/admin/step-up", json=body, headers=bearer("qms_owner"))
        assert (refused.status_code, refused.json()["error"]) == (422, "step_up_body_refused")

    def test_a_role_with_no_second_key_anywhere_never_reaches_it(self, harness: ApiHarness) -> None:
        action_id = _open(harness.client)
        refused = harness.client.post(
            "/admin/step-up", json={"action_id": action_id}, headers=bearer("sre_oncall")
        )
        assert (refused.status_code, refused.json()["error"]) == (403, "forbidden")


class TestComplete:
    def test_another_callers_ceremony_is_unknown_to_them(self, harness: ApiHarness) -> None:
        client = harness.client
        action_id = _open(client)
        begun = client.post(
            "/admin/step-up", json={"action_id": action_id}, headers=bearer("qms_owner")
        )
        login = {"subject": "kc-sub-qms-owner", "session_id": "sid-qms-owner-1"}
        state, code = STEP_UP.keycloak.authorize(
            begun.json()["authorize_url"], Login(credential_id="Y3JlZC1zdGVwLXVwLTAwMDE", **login)
        )
        hijacked = client.post(
            "/admin/step-up/complete",
            json={"state": state, "code": code},
            headers=bearer("compliance_officer"),
        )
        assert (hijacked.status_code, hijacked.json()["error"]) == (403, "step_up_unknown")

    def test_a_login_without_the_webauthn_step_is_refused(self, harness: ApiHarness) -> None:
        action_id = _open(harness.client)
        before = _steps("complete", "step_up_without_webauthn")
        refused = STEP_UP.grant(harness.client, "qms_owner", action_id, amr=("pwd",))
        assert (refused.status_code, refused.json()["error"]) == (403, "step_up_without_webauthn")
        assert _steps("complete", "step_up_without_webauthn") == before + 1

    def test_a_remembered_login_is_refused(self, harness: ApiHarness) -> None:
        action_id = _open(harness.client)
        refused = STEP_UP.grant(harness.client, "qms_owner", action_id, auth_offset_s=-600)
        assert (refused.status_code, refused.json()["error"]) == (403, "step_up_not_fresh")


class TestRegistration:
    def test_the_step_up_is_a_tier_one_safe_action(self) -> None:
        assert DANGEROUS_ACTIONS[FOUR_EYES_STEP_UP.id] is FOUR_EYES_STEP_UP
        assert FOUR_EYES_STEP_UP.tier is ActionTier.T1
        assert FOUR_EYES_STEP_UP.direction is ActionDirection.SAFE
        assert (REPO / FOUR_EYES_STEP_UP.runbook).is_file()

    def test_its_actors_are_every_second_key_and_nobody_else(self) -> None:
        # derived from the routes, not the registry: whoever can reach an
        # approve or countersign route, and nobody who cannot
        second_keys = {
            role
            for route in ADMIN_ROUTES
            if route.path.endswith(("/approve", "/countersign"))
            for role in route.permitted_roles
        }
        assert FOUR_EYES_STEP_UP.actor_roles == second_keys

    def test_its_metric_is_catalogued(self) -> None:
        catalog = load_metrics_catalog(REPO / "observability" / "metrics_catalog.yaml")
        (spec,) = [m for m in catalog.metrics if m.spec_id == FOUR_EYES_STEP_UP.alert_metric]
        assert spec.name == "admin_step_up_total"
        assert spec.labels == ["stage", "outcome"]

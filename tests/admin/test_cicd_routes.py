"""INT-187 — the CI/CD module's routes and the deploy path's release gate.

Through ``/admin/cicd/*`` on the services/api unit-lane app (the INT-180 gate:
recorded Keycloak claims, the IP allow-list, the role matrix, the write-ahead
audit), and through ``python -m intake_api.admin.release_gate`` — the command
``infra/staging/deploy.sh`` runs before it touches the host:

- **Freeze is one key.** One ``sre_oncall`` engages it; nobody approves.
- **Lift is two.** A request changes nothing; a different human approves; the
  requester cannot approve their own request, and the attempt is metered as the
  intrusion signal files/08 §5 names.
- **Bodies are closed and refusals are codes** — no submitted value is echoed.
- **The gate reads the same store and the same rule as the console**, exits
  non-zero on a freeze, an exhausted budget or anything it cannot read, and
  never prints the store's URL, which carries the Redis password.
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import fakeredis
import pytest
import redis
from admin_harness import bearer, build_admin_harness, build_admin_wiring
from api_harness import ApiHarness
from intake_api.admin.release_gate import main, run_gate
from intake_api.admin.reliability_console import load_slo_files
from intake_platform.admin import AdminWiring
from intake_platform.release_freeze import (
    ENV_RELEASE_FREEZE_REDIS_URL,
    ErrorBudget,
    RedisReleaseFreezeStore,
)
from prometheus_client import REGISTRY
from step_up_fakes import StepUpHarness

REPO = Path(__file__).resolve().parents[2]
REASON = {
    "reason_class": "incident_mitigation",
    "justification": "Error budget burning on the api; hold every deploy.",
}
LIFT_REASON = {
    "reason_class": "incident_mitigation",
    "justification": "The api fix is verified on staging; budget recovered.",
}


#: INT-563: approvals go through the step-up, the console's own sequence.
STEP_UP = StepUpHarness.build()


def _changes(control: str, outcome: str) -> float:
    return (
        REGISTRY.get_sample_value(
            "admin_deploy_freeze_changes_total", {"control": control, "outcome": outcome}
        )
        or 0.0
    )


@pytest.fixture()
def client_redis() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis()


@pytest.fixture()
def harness(tmp_path: Path, client_redis: fakeredis.FakeRedis) -> Iterator[ApiHarness]:
    wiring = build_admin_wiring(
        release_freeze=RedisReleaseFreezeStore(client_redis), step_up=STEP_UP.service
    )
    yield from build_admin_harness(tmp_path, admin=wiring)


def _engage(client: Any, role: str = "sre_oncall", body: dict[str, Any] | None = None) -> Any:
    return client.post("/admin/cicd/freeze", json=body or REASON, headers=bearer(role))


def _lift(client: Any, role: str = "platform_admin") -> Any:
    return client.post("/admin/cicd/freeze/lift", json=LIFT_REASON, headers=bearer(role))


def _approve(client: Any, action_id: str, role: str = "qms_owner") -> Any:
    return STEP_UP.approve(client, f"/admin/cicd/freeze/lift/{action_id}/approve", action_id, role)


class TestRoutes:
    def test_the_page_reads_the_composite(self, harness: ApiHarness) -> None:
        response = harness.client.get("/admin/cicd", headers=bearer("sre_oncall"))
        assert response.status_code == 200, response.json()
        doc = response.json()
        assert doc["schema"] == "intake.admin.cicd.v1"
        assert doc["tiles"]["freeze"]["engaged"] is False
        assert [row["control"] for row in doc["control_catalogue"]] == [
            "freeze_engage",
            "freeze_lift",
        ]

    def test_one_sre_freezes_alone_and_again_changes_nothing(
        self, harness: ApiHarness, client_redis: fakeredis.FakeRedis
    ) -> None:
        applied = _changes("freeze_engage", "applied")
        first = _engage(harness.client)
        assert first.status_code == 200, first.json()
        assert first.json()["changed"] is True
        assert first.json()["freeze"]["engaged"] is True
        assert first.json()["freeze"]["approved_by"] is None
        assert _changes("freeze_engage", "applied") == applied + 1
        second = _engage(harness.client, role="clinical_lead")
        assert second.status_code == 200 and second.json()["changed"] is False
        assert RedisReleaseFreezeStore(client_redis).read().revision == 1

    def test_a_role_outside_tier_1_cannot_freeze(self, harness: ApiHarness) -> None:
        assert _engage(harness.client, role="auditor").status_code == 403

    def test_a_lift_is_a_request_until_a_different_human_approves(
        self, harness: ApiHarness, client_redis: fakeredis.FakeRedis
    ) -> None:
        _engage(harness.client)
        opened = _lift(harness.client)
        assert opened.status_code == 200, opened.json()
        assert opened.json()["tier"] == 2 and opened.json()["state"] == "pending"
        assert RedisReleaseFreezeStore(client_redis).read().engaged is True
        page = harness.client.get("/admin/cicd", headers=bearer("sre_oncall")).json()
        assert [a["action_id"] for a in page["tiles"]["pending"]["actions"]] == [
            opened.json()["action_id"]
        ]
        approved = _approve(harness.client, opened.json()["action_id"])
        assert approved.status_code == 200, approved.json()
        assert approved.json()["freeze"]["engaged"] is False
        assert approved.json()["freeze"]["approved_by"] == "kc-sub-qms-owner"
        assert RedisReleaseFreezeStore(client_redis).read().engaged is False

    def test_the_requester_cannot_approve_their_own_lift(
        self, harness: ApiHarness, client_redis: fakeredis.FakeRedis
    ) -> None:
        _engage(harness.client)
        opened = _lift(harness.client, role="platform_owner")
        before = REGISTRY.get_sample_value("admin_four_eyes_self_approval_attempt_total") or 0.0
        refused = _approve(harness.client, opened.json()["action_id"], role="platform_owner")
        assert refused.status_code == 409
        assert refused.json()["error"] == "four_eyes_self_approval"
        after = REGISTRY.get_sample_value("admin_four_eyes_self_approval_attempt_total")
        assert after == before + 1
        assert RedisReleaseFreezeStore(client_redis).read().engaged is True

    def test_there_is_nothing_to_lift_when_nothing_is_frozen(self, harness: ApiHarness) -> None:
        refused = _lift(harness.client)
        assert refused.status_code == 409
        assert refused.json()["error"] == "release_freeze_not_engaged"

    def test_bodies_are_closed_and_refusals_echo_nothing(self, harness: ApiHarness) -> None:
        planted = "Patient Ayşe Yılmaz asked"
        refused = _engage(harness.client, body={**REASON, "note": planted})
        assert refused.status_code == 422
        assert refused.json()["error"] == "release_freeze_unexpected_field"
        assert planted not in refused.text
        short = _engage(harness.client, body={**REASON, "justification": "hold"})
        assert short.json()["error"] == "flag_change_reason_too_short"
        unknown = _engage(harness.client, body={**REASON, "reason_class": "because"})
        assert unknown.json()["error"] == "release_freeze_reason_class_unknown"

    def test_an_unwired_store_answers_503_and_writes_nowhere(self, tmp_path: Path) -> None:
        wiring: AdminWiring = build_admin_wiring()
        for harness in build_admin_harness(tmp_path, admin=wiring):
            refused = _engage(harness.client)
            assert refused.status_code == 503
            assert refused.json()["error"] == "release_freeze_unconfigured"
            page = harness.client.get("/admin/cicd", headers=bearer("sre_oncall")).json()
            assert page["tiles"]["freeze"]["reason"] == "release_freeze_unconfigured"
            assert page["tiles"]["deploy_gate"]["allowed"] is False

    def test_a_store_that_does_not_answer_is_503_and_counted_refused(self, tmp_path: Path) -> None:
        down = RedisReleaseFreezeStore(
            redis.Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.05)
        )
        refused_before = _changes("freeze_engage", "refused")
        for harness in build_admin_harness(tmp_path, admin=build_admin_wiring(release_freeze=down)):
            refused = _engage(harness.client)
            assert refused.status_code == 503
            assert refused.json()["error"] == "release_freeze_unreachable"
            assert _changes("freeze_engage", "refused") == refused_before + 1

    def test_a_body_that_is_not_an_object_is_refused_by_code(self, harness: ApiHarness) -> None:
        for raw in (b"{not json", b"[1, 2]"):
            refused = harness.client.post(
                "/admin/cicd/freeze",
                content=raw,
                headers={**bearer("sre_oncall"), "content-type": "application/json"},
            )
            assert refused.status_code == 422
            assert refused.json()["error"] in {
                "release_freeze_body_not_json",
                "release_freeze_body_not_an_object",
            }

    def test_approving_an_id_nobody_minted_is_not_found(self, harness: ApiHarness) -> None:
        _engage(harness.client)
        assert _approve(harness.client, "01jbq0nothinghere").status_code == 404

    def test_the_brief_is_readable_and_another_modules_ceremony_is_not(
        self, harness: ApiHarness
    ) -> None:
        _engage(harness.client)
        opened = _lift(harness.client).json()
        brief = harness.client.get(
            f"/admin/cicd/pending/{opened['action_id']}", headers=bearer("auditor")
        )
        assert brief.status_code == 200
        assert brief.json()["justification"] == LIFT_REASON["justification"]
        absent = harness.client.get("/admin/cicd/pending/nope", headers=bearer("auditor"))
        assert absent.status_code == 404


# =====================================================================================
# the release gate deploy.sh runs
# =====================================================================================


class TestReleaseGate:
    SLOS = load_slo_files(REPO / "docs" / "slo")

    def _run(self, store: Any, *, failure: str | None = None) -> tuple[int, str]:
        out = io.StringIO()
        code = run_gate(
            store=store,
            store_failure=failure,
            prom=None,
            prom_misconfigured=False,
            slo_files=self.SLOS,
            out=out,
        )
        return code, out.getvalue()

    def test_an_open_tier_with_no_budget_source_is_allowed_and_says_why(self) -> None:
        code, text = self._run(RedisReleaseFreezeStore(fakeredis.FakeRedis()))
        assert code == 0
        assert "allowed" in text and "error_budget_not_configured" in text

    def test_an_engaged_freeze_exits_non_zero_and_names_who_and_why(self) -> None:
        client = fakeredis.FakeRedis()
        store = RedisReleaseFreezeStore(client)
        wiring = build_admin_wiring()
        from intake_platform.admin.flag_governance import (
            FlagChangeReason,
            build_flag_change_justification,
        )
        from intake_platform.admin.four_eyes import ActorBlock
        from intake_platform.admin.freeze_governance import DeployFreezeGovernor
        from intake_platform.admin.roles import AdminRole

        DeployFreezeGovernor(wiring.four_eyes, store).engage(
            actor=ActorBlock(
                subject="kc-sub-sre-oncall",
                role=AdminRole.SRE_ONCALL,
                org="org:intake",
                authenticator_aaguid="aaguid-1",
                credential_id="cred-1",
                session_id="sid-1",
            ),
            justification=build_flag_change_justification(
                reason_class=FlagChangeReason.INCIDENT_MITIGATION,
                free_text="Error budget burning; hold every deploy.",
            ),
        )
        code, text = self._run(store)
        assert code == 3
        assert "refused" in text and "deploy_freeze_engaged" in text
        assert "kc-sub-sre-oncall" in text and "incident_mitigation" in text
        assert "hold every deploy" not in text, "free text stays on the audit chain"

    def test_a_store_it_cannot_read_refuses(self) -> None:
        code, text = self._run(None, failure="release_freeze_unreachable")
        assert code == 3 and "release_freeze_unreachable" in text

    @pytest.mark.parametrize(
        ("env", "reason"),
        [
            ({}, "release_freeze_unconfigured"),
            ({ENV_RELEASE_FREEZE_REDIS_URL: "http://:s3cr3t-pw@redis:6379/0"}, "misconfigured"),
            (
                {ENV_RELEASE_FREEZE_REDIS_URL: "redis://:s3cr3t-pw@127.0.0.1:1/0"},
                "release_freeze_unreachable",
            ),
        ],
    )
    def test_main_fails_closed_and_never_prints_the_store_url(
        self, env: dict[str, str], reason: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main([], env=env) == 3
        captured = capsys.readouterr()
        assert reason in captured.out
        assert "s3cr3t-pw" not in captured.out + captured.err

    def test_a_declared_budget_source_that_fails_refuses(self) -> None:
        out = io.StringIO()
        code = run_gate(
            store=RedisReleaseFreezeStore(fakeredis.FakeRedis()),
            store_failure=None,
            prom=None,
            prom_misconfigured=True,
            slo_files=self.SLOS,
            out=out,
        )
        assert code == 3 and "error_budget_unreadable" in out.getvalue()

    def test_the_budget_the_gate_reads_is_the_console_s(self) -> None:
        """One rule: the gate and the console's deploy_gate tile call the same
        budget function, so they cannot disagree about a deploy."""
        from intake_api.admin import cicd_console, release_gate

        assert release_gate.error_budget is cicd_console.error_budget
        assert isinstance(release_gate.error_budget(None, self.SLOS, False)[0], ErrorBudget)

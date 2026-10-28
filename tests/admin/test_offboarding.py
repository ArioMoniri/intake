"""INT-366 — one-action offboarding and the 60-day auto-disable (files/08 §2.4).

Acceptance, verbatim (GitHub #593):
  "one disable revokes the person's Keycloak sessions, OpenBao leases and every
   other console account together (files/08 §2.4), and an account with no
   login for 60 days is disabled automatically; both are audited"

sec_row: admin-console · legal: 2018-10 (measure 2d, gap ``one-action-offboarding``).

What is pinned here:
- **One action, every system.** ``POST /admin/access/offboard`` disables the
  Keycloak account, then ends its sessions, then disables the person's OpenBao
  identity and revokes every token (and with it every lease) that identity
  holds — and lists every other console account from
  ``infra/admin/console-accounts.yaml``. A system that cannot be revoked by
  code is a **manual step**: it is listed, it keeps the offboarding
  incomplete, and it is closed only by a confirmation that is itself audited.
  Nothing is silently skipped, and a step that fails is reported failed while
  the others still run.
- **Tier 1, the safe direction** (files/08 §8.2: "token revoke" is T1): one key,
  no approver, audited, and it pages through its own counter. A departed
  person's pending four-eyes requests expire (§2.4).
- **Sixty days without a login disables the account**, through the same
  pipeline, from a scheduled job (``python -m intake_platform.access_hygiene``,
  ``make access-hygiene``). The job refuses — disabling nobody — when the realm
  does not keep sixty days of login history: an account whose last login was
  forgotten is not an account that never logged in.
- Ids only on the chain and in the job's output (invariant 6).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from access_fakes import (
    CONSOLE_ACCOUNTS,
    FakeKeycloak,
    FakeOpenBao,
    committed_systems,
    identity_wiring,
)
from admin_harness import bearer, build_admin_harness, build_admin_wiring
from api_harness import ApiHarness
from intake_platform.access_hygiene import HYGIENE_ACTOR, run_auto_disable
from intake_platform.access_hygiene.cli import EXIT_FAILED, EXIT_OK, EXIT_REFUSED, main
from intake_platform.admin import DANGEROUS_ACTIONS, ActionDirection, ActionTier, AdminRole
from intake_platform.admin.access import (
    ConsoleSystemsRefused,
    DirectoryUnavailable,
    IdentityWiring,
    LoginHistoryUnavailable,
    OpenBaoLeaseRevoker,
    Revocation,
    RevocationFailed,
    load_console_systems,
)
from intake_platform.admin.access.config import (
    ENV_KEYCLOAK_REALM,
    ENV_KEYCLOAK_URL,
    ENV_OPENBAO_MOUNT,
    KEYCLOAK_CLIENT_KV_PATH,
    IdentityUnconfigured,
    identity_from_env,
)
from intake_platform.admin.access.offboarding import (
    DORMANT_AFTER_DAYS,
    OffboardingReason,
    StepOutcome,
    dormant_users,
    offboardings_from,
)
from intake_platform.admin.actions import OFFBOARD
from intake_platform.audit import AuditEntry
from intake_platform.slo import load_metrics_catalog
from step_up_fakes import StepUpHarness

REPO = Path(__file__).resolve().parents[2]
SPEC = REPO / "files" / "08_ADMIN_CONSOLE_AND_OBSERVABILITY.md"
CATALOG = REPO / "observability" / "metrics_catalog.yaml"
RULES = REPO / "infra" / "observability" / "security-rules.yaml"
REALM = REPO / "infra" / "keycloak" / "dev-realm.json"
MAKEFILE = REPO / "Makefile"
RUNBOOK = REPO / "docs" / "runbooks" / "access-review.md"

T0 = datetime(2026, 9, 27, tzinfo=UTC)
DAY = timedelta(days=1)
MANUAL = ("grafana", "langfuse", "unleash")
#: INT-563: approvals go through the step-up, the console's own sequence.
STEP_UP = StepUpHarness.build()


class MemorySink:
    """An append-only recorder in the AdminAuditSink shape, for the job tests."""

    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []

    async def record(
        self, *, actor: str, action: str, resource_ref: str, consent_scope: str
    ) -> None:
        self.rows.append((actor, action, resource_ref))

    def entries(self) -> list[AuditEntry]:
        return [
            AuditEntry(
                seq=index,
                timestamp_utc=T0.isoformat(),
                actor=actor,
                action=action,
                resource_ref=ref,
                consent_scope_ref="basis:KVKK-12",
                prev_hash="0" * 64,
                entry_hash="0" * 64,
            )
            for index, (actor, action, ref) in enumerate(self.rows, start=1)
        ]


@pytest.fixture()
def keycloak() -> FakeKeycloak:
    return FakeKeycloak(datetime.now(UTC))


@pytest.fixture()
def openbao() -> FakeOpenBao:
    return FakeOpenBao()


@pytest.fixture()
def harness(tmp_path: Path, keycloak: FakeKeycloak, openbao: FakeOpenBao) -> Iterator[ApiHarness]:
    yield from build_admin_harness(
        tmp_path,
        admin=build_admin_wiring(
            identity=identity_wiring(keycloak, openbao), step_up=STEP_UP.service
        ),
    )


def _offboard(
    harness: ApiHarness, subject: str, role: str = "compliance_officer", reason: str = "departure"
) -> Any:
    return harness.client.post(
        "/admin/access/offboard",
        json={"subject": subject, "reason_class": reason},
        headers=bearer(role),
    )


def _confirm(
    harness: ApiHarness, offboarding_id: str, system: str, role: str = "sre_oncall"
) -> Any:
    return harness.client.post(
        f"/admin/access/offboard/{offboarding_id}/confirm",
        json={"system": system},
        headers=bearer(role),
    )


_LINK = "    runbook: docs/runbooks/access-review.md#grafana\n"


def _config(systems: str) -> str:
    return f"schema_version: 1\nsystems:\n{systems}"


def _outcomes(body: dict[str, Any]) -> dict[str, str]:
    return {step["system"]: step["outcome"] for step in body["steps"]}


# --- the registry and the configuration ----------------------------------------------


class TestTierAndConfiguration:
    def test_offboarding_is_tier_one_on_the_safe_direction(self) -> None:
        action = DANGEROUS_ACTIONS[OFFBOARD.id]
        assert action.tier is ActionTier.T1
        assert action.direction is ActionDirection.SAFE
        assert action.approver_roles == frozenset()
        assert action.actor_roles == frozenset(
            {AdminRole.SRE_ONCALL, AdminRole.COMPLIANCE_OFFICER, AdminRole.PLATFORM_OWNER}
        )
        assert action.runbook == "docs/runbooks/access-review.md"
        assert action.alert_metric == "admin.offboarding_total"

    def test_the_spec_names_token_revoke_as_tier_one(self) -> None:
        text = SPEC.read_text(encoding="utf-8")
        section = text[text.index("### 8.2 ") : text.index("## 9. ")]
        tier1 = next(line for line in section.splitlines() if line.startswith("| **T1"))
        assert "token revoke" in tier1

    def test_the_committed_systems_are_exactly_the_ones_files_08_names(self) -> None:
        section = SPEC.read_text(encoding="utf-8").split("### 2.4 ", 1)[1].split("### 2.5 ", 1)[0]
        named = re.search(r"the ([A-Z][a-z]+) / ([A-Z][a-z]+) / ([A-Z][a-z]+) accounts", section)
        assert named is not None
        assert tuple(system.id for system in committed_systems()) == tuple(
            name.lower() for name in named.groups()
        )

    def test_every_manual_system_links_a_runbook_section_that_exists(self) -> None:
        runbook = RUNBOOK.read_text(encoding="utf-8")
        for system in committed_systems():
            assert system.revocation is Revocation.MANUAL
            path, _, anchor = system.runbook.partition("#")
            assert path == "docs/runbooks/access-review.md"
            assert f"\n### {anchor}\n" in runbook.lower()

    @pytest.mark.parametrize(
        "body",
        [
            _config("  - id: grafana\n    revocation: programmatic\n" + _LINK),
            _config("  - id: grafana\n    revocation: manual\n"),
            _config("  - id: Grafana UI\n    revocation: manual\n" + _LINK),
            _config("  - id: grafana\n    revocation: manual\n" + _LINK + "    note: skip\n"),
            _config("  - id: keycloak_account\n    revocation: manual\n" + _LINK),
            "schema_version: 1\nsystems: []\n",
            _config("  - id: grafana\n    revocation: manual\n" + _LINK).replace(": 1", ": 2", 1),
        ],
        ids=[
            "programmatic-without-adapter",
            "no-runbook",
            "prose-id",
            "unknown-key",
            "built-in-id",
            "empty",
            "schema",
        ],
    )
    def test_a_configuration_that_would_skip_a_system_is_refused(
        self, tmp_path: Path, body: str
    ) -> None:
        path = tmp_path / "console-accounts.yaml"
        path.write_text(body, encoding="utf-8")
        with pytest.raises(ConsoleSystemsRefused):
            load_console_systems(path)

    def test_the_committed_configuration_loads(self) -> None:
        assert load_console_systems(CONSOLE_ACCOUNTS)


# --- one action, every system ----------------------------------------------------------


class TestOneActionOffboarding:
    def test_every_system_is_revoked_or_listed_in_one_call(
        self, harness: ApiHarness, keycloak: FakeKeycloak, openbao: FakeOpenBao
    ) -> None:
        response = _offboard(harness, "kc-sub-platform-owner")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["subject"] == "kc-sub-platform-owner"
        assert body["reason_class"] == "departure"
        assert _outcomes(body) == {
            "keycloak_account": "revoked",
            "keycloak_sessions": "revoked",
            "openbao_leases": "revoked",
            **{system: "manual_pending" for system in MANUAL},
        }
        assert body["complete"] is False
        assert keycloak.users["kc-sub-platform-owner"]["enabled"] is False
        assert keycloak.sessions["kc-sub-platform-owner"] == 0
        assert openbao.disabled_entities == {"ent-platform-owner"}
        assert sorted(openbao.revoked) == ["acc-po-1", "acc-po-2"]
        assert "acc-other" in openbao.accessors

    def test_the_account_is_disabled_before_its_sessions_are_ended(
        self, harness: ApiHarness, keycloak: FakeKeycloak
    ) -> None:
        assert _offboard(harness, "kc-sub-tenant-admin").status_code == 200
        writes = [
            call for call in keycloak.calls if call[0] in {"PUT", "POST"} and "/users/" in call[1]
        ]
        assert writes == [
            ("PUT", "/admin/realms/intake-dev/users/kc-sub-tenant-admin"),
            ("POST", "/admin/realms/intake-dev/users/kc-sub-tenant-admin/logout"),
        ]

    def test_every_step_is_audited_write_ahead_with_ids_only(self, harness: ApiHarness) -> None:
        before = len(harness.audit_store.entries())
        body = _offboard(harness, "kc-sub-platform-owner").json()
        appended = harness.audit_store.entries()[before:]
        actions = [entry.action for entry in appended]
        assert actions[0] == "admin.access.offboard.intent"
        assert actions[-1] == "admin.access.offboard.success"
        assert "admin.offboarding.opened.departure" in actions
        for system in ("keycloak_account", "keycloak_sessions", "openbao_leases"):
            intent = actions.index(f"admin.offboarding.{system}.intent")
            assert actions[intent + 1] == f"admin.offboarding.{system}.revoked"
        for system in MANUAL:
            assert f"admin.offboarding.{system}.manual_pending" in actions
        step_refs = {e.resource_ref for e in appended if e.action.startswith("admin.offboarding.")}
        assert step_refs == {f"offboarding:{body['offboarding_id']}:kc-sub-platform-owner"}
        for entry in appended:
            assert entry.actor == "kc-sub-compliance-officer"
        # the step rows carry the offboarding id and the subject id, nothing else
        for ref in step_refs:
            assert re.fullmatch(r"offboarding:[0-9a-f]{32}:kc-sub-platform-owner", ref)

    def test_manual_steps_close_only_by_audited_confirmation(self, harness: ApiHarness) -> None:
        body = _offboard(harness, "kc-sub-platform-owner").json()
        offboarding_id = body["offboarding_id"]
        for index, system in enumerate(MANUAL):
            confirmed = _confirm(harness, offboarding_id, system)
            assert confirmed.status_code == 200, confirmed.text
            assert confirmed.json()["complete"] is (index == len(MANUAL) - 1)
        actions = [e.action for e in harness.audit_store.entries()]
        for system in MANUAL:
            assert f"admin.offboarding.{system}.manual_confirmed" in actions

    @pytest.mark.parametrize(
        ("system", "error"),
        [
            ("keycloak_account", "offboarding_step_not_manual"),
            ("argocd", "offboarding_system_unknown"),
        ],
    )
    def test_only_a_listed_manual_step_can_be_confirmed(
        self, harness: ApiHarness, system: str, error: str
    ) -> None:
        offboarding_id = _offboard(harness, "kc-sub-platform-owner").json()["offboarding_id"]
        response = _confirm(harness, offboarding_id, system)
        assert response.status_code == 409
        assert response.json()["error"] == error

    def test_an_unknown_offboarding_is_not_found(self, harness: ApiHarness) -> None:
        assert _confirm(harness, "0" * 32, "grafana").status_code == 404

    def test_a_failed_step_is_reported_and_the_others_still_run(
        self, harness: ApiHarness, keycloak: FakeKeycloak, openbao: FakeOpenBao
    ) -> None:
        keycloak.fail.add("logout")
        body = _offboard(harness, "kc-sub-platform-owner").json()
        outcomes = _outcomes(body)
        assert outcomes["keycloak_account"] == "revoked"
        assert outcomes["keycloak_sessions"] == "failed"
        assert outcomes["openbao_leases"] == "revoked"
        assert body["complete"] is False
        assert "admin.offboarding.keycloak_sessions.failed" in [
            e.action for e in harness.audit_store.entries()
        ]
        # confirming every manual step does not complete an offboarding with a failed step
        for system in MANUAL:
            last = _confirm(harness, body["offboarding_id"], system).json()
        assert last["complete"] is False

    def test_an_unreachable_openbao_is_a_failed_step_not_a_skipped_one(
        self, harness: ApiHarness, openbao: FakeOpenBao
    ) -> None:
        openbao.fail.add("all")
        assert (
            _outcomes(_offboard(harness, "kc-sub-platform-owner").json())["openbao_leases"]
            == "failed"
        )

    def test_a_person_with_no_openbao_identity_has_nothing_to_revoke(
        self, harness: ApiHarness, openbao: FakeOpenBao
    ) -> None:
        body = _offboard(harness, "kc-sub-tenant-admin").json()
        assert _outcomes(body)["openbao_leases"] == "revoked"
        assert openbao.revoked == []

    def test_an_unknown_subject_is_refused_before_any_step(self, harness: ApiHarness) -> None:
        before = len(harness.audit_store.entries())
        response = _offboard(harness, "kc-sub-nobody")
        assert response.status_code == 404
        appended = [e.action for e in harness.audit_store.entries()[before:]]
        assert appended == ["admin.access.offboard.intent", "admin.access.offboard.failure"]

    @pytest.mark.parametrize(
        "body",
        [
            {"subject": "kc-sub-platform-owner"},
            {"subject": "kc-sub-platform-owner", "reason_class": "dormant_60d"},
            {"subject": "kc-sub-platform-owner", "reason_class": "left the company"},
            {"subject": "../../users", "reason_class": "departure"},
            {"subject": "kc-sub-platform-owner", "reason_class": "departure", "note": "x"},
        ],
        ids=["no-reason", "job-only-reason", "prose-reason", "path-traversal", "extra-field"],
    )
    def test_a_malformed_request_is_refused(
        self, harness: ApiHarness, body: dict[str, str]
    ) -> None:
        response = harness.client.post(
            "/admin/access/offboard", json=body, headers=bearer("sre_oncall")
        )
        assert response.status_code == 422
        assert "left the company" not in response.text

    def test_a_departed_persons_pending_requests_expire(self, harness: ApiHarness) -> None:
        opened = harness.client.post(
            "/admin/break-glass",
            json={
                "session_ref": "session:0f8a1c2d-4b5e-4a6f-9c31-2d4e6f8a1c2d",
                "reason_class": "patient_support_request",
                "justification": "Synthetic unit-lane support request for a missing record.",
                "controller_instruction_ref": "ci:tenant-a:2026-09-03:01",
            },
            headers=bearer("clinical_lead"),
        )
        assert opened.status_code == 200
        body = _offboard(harness, "kc-sub-clinical-lead").json()
        assert body["expired_pending_actions"] == 1
        action_id = opened.json()["action_id"]
        approve = STEP_UP.approve(
            harness.client, f"/admin/break-glass/{action_id}/approve", action_id, "qms_owner"
        )
        assert approve.status_code == 409
        assert approve.json()["error"] == "four_eyes_already_decided"

    def test_pending_offboardings_appear_in_the_review(self, harness: ApiHarness) -> None:
        offboarding_id = _offboard(harness, "kc-sub-platform-owner").json()["offboarding_id"]
        review = harness.client.get(
            "/admin/access/review", headers=bearer("compliance_officer")
        ).json()
        pending = {item["offboarding_id"]: item for item in review["pending_offboardings"]}
        assert pending[offboarding_id]["pending_systems"] == list(MANUAL)
        for system in MANUAL:
            _confirm(harness, offboarding_id, system)
        review = harness.client.get(
            "/admin/access/review", headers=bearer("compliance_officer")
        ).json()
        assert offboarding_id not in {
            item["offboarding_id"] for item in review["pending_offboardings"]
        }

    def test_unconfigured_identity_refuses_rather_than_pretending(self, tmp_path: Path) -> None:
        for built in build_admin_harness(tmp_path):
            response = _offboard(built, "kc-sub-platform-owner")
            assert response.status_code == 503
            assert response.json()["error"] == "access_review_unconfigured"


# --- sixty days without a login --------------------------------------------------------


def _job_identity(keycloak: FakeKeycloak, openbao: FakeOpenBao) -> IdentityWiring:
    return identity_wiring(keycloak, openbao)


def _run(identity: IdentityWiring, sink: MemorySink, **kwargs: Any) -> Any:
    import asyncio

    return asyncio.run(run_auto_disable(identity, sink, now=T0, **kwargs))


class TestSixtyDayAutoDisable:
    def test_the_threshold_is_the_spec_value(self) -> None:
        section = SPEC.read_text(encoding="utf-8").split("### 2.4 ", 1)[1].split("### 2.5 ", 1)[0]
        assert "60-day auto-disable on no login" in section
        assert DORMANT_AFTER_DAYS == 60

    def test_dormant_accounts_are_disabled_and_nobody_else(self) -> None:
        keycloak, openbao, sink = FakeKeycloak(T0), FakeOpenBao(), MemorySink()
        report = _run(_job_identity(keycloak, openbao), sink)
        assert sorted(report.disabled) == [
            "kc-sub-clinician-dormant",
            "kc-sub-clinician-sixty",
            "kc-sub-sre-oncall",
        ]
        for subject in report.disabled:
            assert keycloak.users[subject]["enabled"] is False
        for untouched in (
            "kc-sub-clinician-fifty-nine",  # 59 days: the near miss
            "kc-sub-auditor",  # never logged in, created 17 days ago
            "kc-sub-no-staff-role",  # holds no staff role
            "kc-sub-platform-owner",
        ):
            assert keycloak.users[untouched]["enabled"] is True
        # already disabled: not disabled again
        assert ("PUT", "/admin/realms/intake-dev/users/kc-sub-clinical-lead") not in keycloak.calls
        assert openbao.disabled_entities == {"ent-clinician-dormant", "ent-sre-oncall"}
        assert "acc-dormant" in openbao.revoked

    def test_one_second_short_of_sixty_days_is_not_dormant(self) -> None:
        users = FakeKeycloak(T0).directory().staff_users()
        sixty = next(u for u in users if u.subject == "kc-sub-clinician-sixty")
        assert sixty in dormant_users(users, now=T0)
        assert sixty not in dormant_users(users, now=T0 - timedelta(seconds=1))

    def test_the_job_is_audited_under_its_own_id_with_the_dormant_reason(self) -> None:
        keycloak, openbao, sink = FakeKeycloak(T0), FakeOpenBao(), MemorySink()
        _run(_job_identity(keycloak, openbao), sink)
        assert {actor for actor, _, _ in sink.rows} == {HYGIENE_ACTOR}
        opened = [
            ref for _, action, ref in sink.rows if action == "admin.offboarding.opened.dormant_60d"
        ]
        assert len(opened) == 3
        offboardings = offboardings_from(sink.entries())
        assert {o.reason for o in offboardings.values()} == {OffboardingReason.DORMANT}
        for offboarding in offboardings.values():
            manual = [s for s in offboarding.steps if s.system in MANUAL]
            assert {s.outcome for s in manual} == {StepOutcome.PENDING_CONFIRMATION}

    @pytest.mark.parametrize(
        "config",
        [
            {"eventsEnabled": False, "eventsExpiration": 5184000, "enabledEventTypes": ["LOGIN"]},
            {"eventsEnabled": True, "eventsExpiration": 5184000, "enabledEventTypes": ["LOGOUT"]},
            {"eventsEnabled": True, "eventsExpiration": 5183999, "enabledEventTypes": ["LOGIN"]},
        ],
        ids=["events-off", "login-not-kept", "one-second-short"],
    )
    def test_without_sixty_days_of_login_history_nobody_is_disabled(
        self, config: dict[str, Any]
    ) -> None:
        keycloak, openbao, sink = FakeKeycloak(T0), FakeOpenBao(), MemorySink()
        keycloak.events_config = config
        with pytest.raises(LoginHistoryUnavailable):
            _run(_job_identity(keycloak, openbao), sink)
        assert all(
            user["enabled"] for s, user in keycloak.users.items() if s != "kc-sub-clinical-lead"
        )
        assert sink.rows == []

    def test_events_that_never_expire_are_enough(self) -> None:
        keycloak, openbao, sink = FakeKeycloak(T0), FakeOpenBao(), MemorySink()
        keycloak.events_config = {"eventsEnabled": True, "enabledEventTypes": ["LOGIN"]}
        assert len(_run(_job_identity(keycloak, openbao), sink).disabled) == 3

    def test_a_dry_run_lists_and_touches_nothing(self) -> None:
        keycloak, openbao, sink = FakeKeycloak(T0), FakeOpenBao(), MemorySink()
        report = _run(_job_identity(keycloak, openbao), sink, dry_run=True)
        assert len(report.disabled) == 3
        assert sink.rows == []
        assert all(call[0] == "GET" or call[1].endswith("/token") for call in keycloak.calls)

    def test_the_committed_dev_realm_keeps_sixty_days_of_logins(self) -> None:
        realm = json.loads(REALM.read_text(encoding="utf-8"))
        assert realm["eventsEnabled"] is True
        assert realm["enabledEventTypes"] == ["LOGIN"]
        assert realm["eventsExpiration"] >= DORMANT_AFTER_DAYS * 86_400


class _Secrets:
    """The two members of SecretsProvider the identity wiring touches."""

    def __init__(self, kv: dict[str, dict[str, str]]) -> None:
        self._kv = kv
        self._client = httpx.Client(base_url="https://openbao.test")

    def get_kv(self, path: str) -> dict[str, str]:
        if path not in self._kv:
            raise httpx.HTTPStatusError(
                "404", request=httpx.Request("GET", path), response=httpx.Response(404)
            )
        return self._kv[path]


_ENV = {
    ENV_KEYCLOAK_URL: "https://keycloak.test",
    ENV_KEYCLOAK_REALM: "intake-dev",
    ENV_OPENBAO_MOUNT: "auth_jwt_4f0c1a2b",
}
_CLIENT = {KEYCLOAK_CLIENT_KV_PATH: {"client_id": "intake-access-admin", "client_secret": "x"}}


class TestAdaptersFailClosed:
    """An answer the adapters cannot read is a refusal, never an empty one."""

    @pytest.mark.parametrize("failing", ["token", "events", "users", "events_config"])
    def test_an_unreadable_keycloak_is_unavailable(self, failing: str) -> None:
        keycloak = FakeKeycloak(T0)
        keycloak.fail.add(failing)
        directory = keycloak.directory()
        with pytest.raises(DirectoryUnavailable):
            directory.staff_users()
            directory.login_history_days()

    def test_an_expired_admin_token_is_renewed_once(self) -> None:
        keycloak = FakeKeycloak(T0)
        directory = keycloak.directory()
        assert directory.user("kc-sub-auditor") is not None
        keycloak.tokens.clear()  # the short-lived token lapsed
        assert directory.user("kc-sub-auditor") is not None
        token_calls = [call for call in keycloak.calls if call[1].endswith("/token")]
        assert len(token_calls) == 2

    def test_a_subject_that_could_leave_the_users_path_is_never_sent(self) -> None:
        keycloak = FakeKeycloak(T0)
        directory = keycloak.directory()
        assert directory.user("../roles") is None
        with pytest.raises(RevocationFailed):
            directory.disable("../roles")
        with pytest.raises(RevocationFailed):
            directory.revoke_sessions("a/b")
        with pytest.raises(RevocationFailed):
            FakeOpenBao().revoker().revoke_for("../../sys")
        assert all("/roles" not in path and "/sys" not in path for _, path in keycloak.calls)

    def test_a_failed_keycloak_write_is_a_failed_revocation(self) -> None:
        keycloak = FakeKeycloak(T0)
        keycloak.fail.add("disable")
        with pytest.raises(RevocationFailed):
            keycloak.directory().disable("kc-sub-auditor")

    def test_a_refused_token_revocation_fails_the_step(self) -> None:
        openbao = FakeOpenBao()
        openbao.fail.add("revoke")
        with pytest.raises(RevocationFailed):
            openbao.revoker().revoke_for("kc-sub-platform-owner")

    def test_a_wrong_openbao_token_fails_the_step(self) -> None:
        openbao = FakeOpenBao()
        client = httpx.Client(
            base_url="https://openbao.test",
            headers={"X-Vault-Token": "another-token"},
            transport=httpx.MockTransport(openbao.handler),
        )
        revoker = OpenBaoLeaseRevoker(client, alias_mount_accessor=openbao.mount_accessor)
        with pytest.raises(RevocationFailed):
            revoker.revoke_for("kc-sub-platform-owner")


class TestDeploymentWiring:
    def test_every_fact_present_builds_the_wiring_from_the_committed_systems(self) -> None:
        wiring = identity_from_env(_ENV, _Secrets(_CLIENT))  # type: ignore[arg-type]
        assert tuple(system.id for system in wiring.systems) == MANUAL

    @pytest.mark.parametrize("missing", sorted(_ENV))
    def test_a_missing_fact_leaves_it_unconfigured(self, missing: str) -> None:
        env = {key: value for key, value in _ENV.items() if key != missing}
        with pytest.raises(IdentityUnconfigured):
            identity_from_env(env, _Secrets(_CLIENT))  # type: ignore[arg-type]

    def test_near_miss_a_plain_http_keycloak_is_refused(self) -> None:
        env = {**_ENV, ENV_KEYCLOAK_URL: "http://keycloak.test"}
        with pytest.raises(IdentityUnconfigured):
            identity_from_env(env, _Secrets(_CLIENT))  # type: ignore[arg-type]

    def test_the_admin_client_comes_from_openbao_or_nowhere(self) -> None:
        with pytest.raises(IdentityUnconfigured):
            identity_from_env(_ENV, _Secrets({}))  # type: ignore[arg-type]
        with pytest.raises(IdentityUnconfigured):
            identity_from_env(
                _ENV,
                _Secrets({KEYCLOAK_CLIENT_KV_PATH: {"client_id": "intake-access-admin"}}),  # type: ignore[arg-type]
            )


class TestHygieneCli:
    def _main(self, identity: IdentityWiring | None, sink: MemorySink, *argv: str) -> int:
        return main(list(argv), identity=identity, sink=sink, clock=lambda: T0)

    def test_a_clean_run_exits_zero_and_prints_ids_only(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        sink = MemorySink()
        assert self._main(_job_identity(FakeKeycloak(T0), FakeOpenBao()), sink) == EXIT_OK
        out = capsys.readouterr().out
        assert "kc-sub-clinician-dormant" in out
        for forbidden in ("Synthetic", "invalid", "synthetic-clinician"):
            assert forbidden not in out

    def test_a_failed_step_exits_two(self) -> None:
        keycloak = FakeKeycloak(T0)
        keycloak.fail.add("logout")
        assert self._main(_job_identity(keycloak, FakeOpenBao()), MemorySink()) == EXIT_FAILED

    def test_no_login_history_exits_four(self) -> None:
        keycloak = FakeKeycloak(T0)
        keycloak.events_config = {"eventsEnabled": False}
        assert self._main(_job_identity(keycloak, FakeOpenBao()), MemorySink()) == EXIT_REFUSED

    def test_an_unreachable_directory_exits_four(self) -> None:
        keycloak = FakeKeycloak(T0)
        keycloak.fail.add("users")
        assert self._main(_job_identity(keycloak, FakeOpenBao()), MemorySink()) == EXIT_REFUSED

    def test_no_configuration_exits_four(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for name in ("INTAKE_ADMIN_KEYCLOAK_URL", "INTAKE_ADMIN_KEYCLOAK_REALM", "OPENBAO_TOKEN"):
            monkeypatch.delenv(name, raising=False)
        assert main([], clock=lambda: T0) == EXIT_REFUSED

    def test_the_make_target_runs_the_module(self) -> None:
        text = MAKEFILE.read_text(encoding="utf-8")
        assert re.search(
            r"^access-hygiene:\n\tuv run python -m intake_platform.access_hygiene$", text, re.M
        )


# --- the signal ------------------------------------------------------------------------


class TestSignal:
    def test_the_offboarding_counter_is_catalogued_live(self) -> None:
        catalog = load_metrics_catalog(CATALOG)
        entry = next(m for m in catalog.metrics if m.name == "admin_offboarding_total")
        assert entry.status == "live"
        assert entry.labels == ["trigger", "complete"]

    def test_an_incomplete_offboarding_raises_a_ticket(self) -> None:
        rules = yaml.safe_load(RULES.read_text(encoding="utf-8"))
        alerts = {rule["alert"]: rule for group in rules["groups"] for rule in group["rules"]}
        rule = alerts["OffboardingIncomplete"]
        assert 'complete="false"' in rule["expr"]
        assert rule["annotations"]["runbook"].startswith("docs/runbooks/access-review.md")

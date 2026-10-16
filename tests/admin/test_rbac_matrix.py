"""INT-180 — the role × tenant contract over ``/admin/*`` (files/08 §2, §8).

Four properties, in the order they matter:

1. **The role set is the spec's role set.** ``ADMIN_ROLES`` is held against the
   §2.1 table parsed out of files/08 itself, and against the committed Keycloak
   realm export. A role added to the spec, or declared in Keycloak and nowhere
   else, fails here — the registry cannot quietly diverge from either.
2. **Every reachable route is in the matrix.** The route list is read off
   FastAPI's own table, never written down, so a new ``/admin`` route fails
   this suite until its row exists.
3. **The matrix is driven, not declared.** Each (route, role) pair is a real
   request: allowed roles must not see 403, denied roles must see exactly 403.
4. **Tenant scope comes from the claim** (files/08 §8 rule a): ``?tenant=`` is
   refused for every role except ``platform_owner``, on every route.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from admin_harness import (
    ROUTE_DRIVES,
    build_admin_harness,
    build_admin_wiring,
    call,
    drives_by_route,
    reachable_admin_routes,
    token_for,
)
from api_harness import ApiHarness, build_harness
from intake_platform.admin import ADMIN_ROLES, AdminRole, role_spec
from intake_platform.admin.roles import PatientContentPath

REPO = Path(__file__).resolve().parents[2]
SPEC = REPO / "files" / "08_ADMIN_CONSOLE_AND_OBSERVABILITY.md"
REALM = REPO / "infra" / "keycloak" / "dev-realm.json"

ALL_ROLES = frozenset(ADMIN_ROLES)

#: files/08 §2.1: the three roles whose row reads "only via break-glass".
BREAK_GLASS_OPENERS = frozenset(
    {AdminRole.PLATFORM_OWNER, AdminRole.CLINICAL_LEAD, AdminRole.COMPLIANCE_OFFICER}
)
#: files/08 §8.2 tier-3 approver pool, narrowed to the roles that may stand as
#: the second key on a break-glass ceremony.
BREAK_GLASS_APPROVERS = frozenset(
    {AdminRole.CLINICAL_LEAD, AdminRole.COMPLIANCE_OFFICER, AdminRole.QMS_OWNER}
)
#: The brief is what the approver reads before deciding, so it is readable by
#: the openers, the approvers, and `auditor` (read-only evidence, §2.1).
BREAK_GLASS_BRIEF_READERS = BREAK_GLASS_OPENERS | BREAK_GLASS_APPROVERS | {AdminRole.AUDITOR}

#: INT-183. The self-hosting registry is a platform-wide statement, so it is
#: readable by the roles whose scope is the platform or all tenants and by
#: nobody scoped to one tenant, one study or one patient grant (files/08 §2.1
#: scope column). Written out here rather than derived, on purpose: this file
#: is the second opinion that catches a mistake in the derivation.
PLATFORM_SCOPE_ROLES = frozenset(
    {
        AdminRole.PLATFORM_OWNER,
        AdminRole.PLATFORM_ADMIN,
        AdminRole.CLINICAL_LEAD,
        AdminRole.QMS_OWNER,
        AdminRole.AUDITOR,
        AdminRole.SRE_ONCALL,
        AdminRole.COMPLIANCE_OFFICER,
        AdminRole.RESEARCHER,
    }
)
#: files/08 §8.2 `admin.models.benchmark.run` actor set — the roles that
#: answer for capacity on a host that serves the PHI path.
BENCHMARK_ACTORS = frozenset(
    {AdminRole.PLATFORM_OWNER, AdminRole.PLATFORM_ADMIN, AdminRole.SRE_ONCALL}
)
#: INT-189 — the Compliance module reads (files/08 §2.1): `compliance_officer`
#: (consent, DSAR, transfer register), `auditor` (read-only evidence export)
#: and `platform_owner` (all tenants). No other role reaches them; written out
#: here as the second opinion against the wiring's `_COMPLIANCE_READERS`.
COMPLIANCE_READERS = frozenset(
    {AdminRole.COMPLIANCE_OFFICER, AdminRole.AUDITOR, AdminRole.PLATFORM_OWNER}
)
#: INT-366 — files/08 §2.7. The review's signers (`compliance_officer`, and a
#: tenant's `tenant_clinical_responsible` for its clinician accounts), its
#: countersigners (`compliance_officer`, `qms_owner`), `auditor` and
#: `platform_owner` read it; written out as the second opinion against the
#: wiring's derivation from the registry.
ACCESS_REVIEW_SIGNERS = frozenset(
    {AdminRole.COMPLIANCE_OFFICER, AdminRole.TENANT_CLINICAL_RESPONSIBLE}
)
ACCESS_REVIEW_COUNTERSIGNERS = frozenset({AdminRole.COMPLIANCE_OFFICER, AdminRole.QMS_OWNER})
ACCESS_REVIEW_READERS = (
    ACCESS_REVIEW_SIGNERS
    | ACCESS_REVIEW_COUNTERSIGNERS
    | {AdminRole.AUDITOR, AdminRole.PLATFORM_OWNER}
)
#: files/08 §8.2 T1 ("token revoke") and §2.1: `sre_oncall` revokes alone, the
#: `compliance_officer` acts on the review's findings, `platform_owner` is all.
OFFBOARDERS = frozenset(
    {AdminRole.SRE_ONCALL, AdminRole.COMPLIANCE_OFFICER, AdminRole.PLATFORM_OWNER}
)

#: INT-182 — the Voice module (files/08 §8.2). Tier 1, the safe direction:
#: one `sre_oncall` or `clinical_lead` (and `platform_owner`, the platform
#: authority above both — INT-188's precedent). Tier 2, toward voice: requested
#: by an all-tenant role accountable for the clinical channel, approved by a
#: second from the same pool or `qms_owner` (device change control).
VOICE_KILL_SWITCH_ACTORS = frozenset(
    {AdminRole.SRE_ONCALL, AdminRole.CLINICAL_LEAD, AdminRole.PLATFORM_OWNER}
)
VOICE_REQUESTERS = frozenset({AdminRole.PLATFORM_OWNER, AdminRole.CLINICAL_LEAD})
VOICE_APPROVERS = frozenset(
    {AdminRole.PLATFORM_OWNER, AdminRole.CLINICAL_LEAD, AdminRole.QMS_OWNER}
)
VOICE_BRIEF_READERS = (
    VOICE_KILL_SWITCH_ACTORS | VOICE_REQUESTERS | VOICE_APPROVERS | {AdminRole.AUDITOR}
)

#: INT-187 — the CI/CD module (files/08 §8.2). Tier 1, the safe direction: the
#: T1 row's `sre_oncall` or `clinical_lead`, and `platform_owner` above both.
#: Tier 2, lifting a freeze: requested by the infrastructure roles that own a
#: deploy (`platform_owner`, `platform_admin`), approved by `platform_owner` or
#: `qms_owner` — a release is IEC 62304 change control (§2.1, §9).
FREEZE_ACTORS = frozenset({AdminRole.SRE_ONCALL, AdminRole.CLINICAL_LEAD, AdminRole.PLATFORM_OWNER})
FREEZE_LIFT_REQUESTERS = frozenset({AdminRole.PLATFORM_OWNER, AdminRole.PLATFORM_ADMIN})
FREEZE_LIFT_APPROVERS = frozenset({AdminRole.PLATFORM_OWNER, AdminRole.QMS_OWNER})
FREEZE_BRIEF_READERS = (
    FREEZE_ACTORS | FREEZE_LIFT_REQUESTERS | FREEZE_LIFT_APPROVERS | {AdminRole.AUDITOR}
)

#: INT-406 — the Safety queue (files/08 §3: "acknowledge
#: (`tenant_clinical_responsible`)"). Read by the acknowledger, the all-tenant
#: clinical lead, the platform owner and the auditor (read-only evidence).
SAFETY_QUEUE_ACKNOWLEDGERS = frozenset({AdminRole.TENANT_CLINICAL_RESPONSIBLE})
SAFETY_QUEUE_READERS = SAFETY_QUEUE_ACKNOWLEDGERS | {
    AdminRole.CLINICAL_LEAD,
    AdminRole.PLATFORM_OWNER,
    AdminRole.AUDITOR,
}

#: INT-428 (ADR-035): narrowing is one key, widening is two.
LANES_SAFE_ACTORS = frozenset(
    {
        AdminRole.SRE_ONCALL,
        AdminRole.CLINICAL_LEAD,
        AdminRole.PLATFORM_OWNER,
        AdminRole.PLATFORM_ADMIN,
    }
)
LANES_REQUESTERS = frozenset({AdminRole.PLATFORM_OWNER, AdminRole.PLATFORM_ADMIN})
LANES_APPROVERS = frozenset(
    {AdminRole.PLATFORM_OWNER, AdminRole.QMS_OWNER, AdminRole.COMPLIANCE_OFFICER}
)
LANES_BRIEF_READERS = LANES_SAFE_ACTORS | LANES_REQUESTERS | LANES_APPROVERS | {AdminRole.AUDITOR}

EXPECTED_MATRIX: dict[tuple[str, str], frozenset[AdminRole]] = {
    ("GET", "/admin/whoami"): ALL_ROLES,
    ("GET", "/admin/access/roles"): ALL_ROLES,
    ("GET", "/admin/actions"): ALL_ROLES,
    ("GET", "/admin/models"): PLATFORM_SCOPE_ROLES,
    ("GET", "/admin/ops"): PLATFORM_SCOPE_ROLES,
    ("GET", "/admin/reliability"): PLATFORM_SCOPE_ROLES,
    ("GET", "/admin/alerts"): PLATFORM_SCOPE_ROLES,
    ("POST", "/admin/models/{component}/benchmark"): BENCHMARK_ACTORS,
    ("POST", "/admin/break-glass"): BREAK_GLASS_OPENERS,
    ("GET", "/admin/break-glass/{action_id}"): frozenset(BREAK_GLASS_BRIEF_READERS),
    ("POST", "/admin/break-glass/{action_id}/approve"): BREAK_GLASS_APPROVERS,
    ("GET", "/admin/compliance/vendor-register"): COMPLIANCE_READERS,
    ("GET", "/admin/compliance/consents"): COMPLIANCE_READERS,
    ("GET", "/admin/compliance/audit-search"): COMPLIANCE_READERS,
    ("GET", "/admin/compliance/dsar"): COMPLIANCE_READERS,
    ("GET", "/admin/compliance/evidence-export"): COMPLIANCE_READERS,
    ("GET", "/admin/voice"): PLATFORM_SCOPE_ROLES,
    ("POST", "/admin/voice/kill-switch"): VOICE_KILL_SWITCH_ACTORS,
    ("POST", "/admin/voice/kill-switch/release"): VOICE_REQUESTERS,
    ("POST", "/admin/voice/kill-switch/release/{action_id}/approve"): VOICE_APPROVERS,
    ("PUT", "/admin/voice/profile/{tenant}"): VOICE_REQUESTERS,
    ("POST", "/admin/voice/profile/pending/{action_id}/approve"): VOICE_APPROVERS,
    ("PUT", "/admin/voice/canary/{tenant}"): VOICE_REQUESTERS,
    ("POST", "/admin/voice/canary/pending/{action_id}/approve"): VOICE_APPROVERS,
    ("GET", "/admin/voice/pending/{action_id}"): frozenset(VOICE_BRIEF_READERS),
    ("GET", "/admin/cicd"): PLATFORM_SCOPE_ROLES,
    ("POST", "/admin/cicd/freeze"): FREEZE_ACTORS,
    ("POST", "/admin/cicd/freeze/lift"): FREEZE_LIFT_REQUESTERS,
    ("POST", "/admin/cicd/freeze/lift/{action_id}/approve"): FREEZE_LIFT_APPROVERS,
    ("GET", "/admin/cicd/pending/{action_id}"): frozenset(FREEZE_BRIEF_READERS),
    ("GET", "/admin/model-lanes"): PLATFORM_SCOPE_ROLES,
    ("POST", "/admin/model-lanes/hosted/disable"): LANES_SAFE_ACTORS,
    ("POST", "/admin/model-lanes/self-hosted"): LANES_SAFE_ACTORS,
    ("POST", "/admin/model-lanes/hosted/release"): LANES_REQUESTERS,
    ("POST", "/admin/model-lanes/hosted/release/{action_id}/approve"): LANES_APPROVERS,
    ("PUT", "/admin/model-lanes/route/{role}"): LANES_REQUESTERS,
    ("POST", "/admin/model-lanes/route/pending/{action_id}/approve"): LANES_APPROVERS,
    ("PUT", "/admin/model-lanes/keys/{provider}"): LANES_REQUESTERS,
    ("POST", "/admin/model-lanes/keys/pending/{action_id}/approve"): LANES_APPROVERS,
    ("GET", "/admin/model-lanes/pending/{action_id}"): frozenset(LANES_BRIEF_READERS),
    ("GET", "/admin/access/review"): frozenset(ACCESS_REVIEW_READERS),
    ("POST", "/admin/access/review/sign"): ACCESS_REVIEW_SIGNERS,
    ("POST", "/admin/access/review/sign/{action_id}/countersign"): ACCESS_REVIEW_COUNTERSIGNERS,
    ("POST", "/admin/access/offboard"): OFFBOARDERS,
    ("POST", "/admin/access/offboard/{offboarding_id}/confirm"): OFFBOARDERS,
    ("GET", "/admin/safety-queue"): SAFETY_QUEUE_READERS,
    ("POST", "/admin/safety-queue/{entry_id}/acknowledge"): SAFETY_QUEUE_ACKNOWLEDGERS,
}


@pytest.fixture()
def admin_harness(tmp_path: Path) -> Iterator[ApiHarness]:
    yield from build_admin_harness(tmp_path)


def spec_role_names() -> set[str]:
    """Role names parsed out of the files/08 §2.1 table, first column only."""
    text = SPEC.read_text(encoding="utf-8")
    section = text[text.index("### 2.1 Role set") : text.index("### 2.2 ")]
    names: set[str] = set()
    for line in section.splitlines():
        if not line.startswith("|"):
            continue
        first = line.split("|")[1]
        match = re.search(r"`([a-z_]+)`", first)
        if match:
            names.add(match.group(1))
    return names


class TestRoleRegistry:
    def test_registry_is_exactly_the_spec_table(self) -> None:
        assert {role.value for role in ADMIN_ROLES} == spec_role_names()

    def test_dev_realm_declares_every_console_role(self) -> None:
        realm = json.loads(REALM.read_text(encoding="utf-8"))
        declared = {role["name"] for role in realm["roles"]["realm"]}
        assert {role.value for role in ADMIN_ROLES} <= declared

    def test_recorded_claims_use_only_declared_realm_roles(self) -> None:
        realm = json.loads(REALM.read_text(encoding="utf-8"))
        declared = {role["name"] for role in realm["roles"]["realm"]}
        fixture = json.loads(
            (Path(__file__).parent / "fixtures" / "keycloak_claims.json").read_text("utf-8")
        )
        for token, claims in fixture["accounts"].items():
            roles = set(claims["realm_access"]["roles"]) - {"offline_access"}
            assert roles <= declared, token

    def test_platform_admin_reaches_no_patient_content(self) -> None:
        # files/08 §2.1: "narrowed" — infrastructure only, and no INSERT,
        # UPDATE or DELETE grant on the audit table.
        spec = role_spec(AdminRole.PLATFORM_ADMIN)
        assert spec.patient_content is PatientContentPath.NONE
        assert not spec.may_approve_tier3

    def test_only_break_glass_roles_carry_the_break_glass_path(self) -> None:
        via_break_glass = {
            role
            for role in ADMIN_ROLES
            if role_spec(role).patient_content is PatientContentPath.BREAK_GLASS
        }
        assert via_break_glass == set(BREAK_GLASS_OPENERS)


class TestRouteMatrix:
    def test_every_reachable_route_has_a_matrix_row_and_a_drive(
        self, admin_harness: ApiHarness
    ) -> None:
        reachable = reachable_admin_routes(admin_harness.client.app)
        assert reachable == set(EXPECTED_MATRIX), (
            "an /admin route exists with no role-matrix row: add it to "
            "EXPECTED_MATRIX and to admin_harness.ROUTE_DRIVES"
        )
        assert reachable == set(drives_by_route())

    @pytest.mark.parametrize("drive", ROUTE_DRIVES, ids=lambda d: f"{d.method} {d.path_template}")
    def test_matrix_is_driven_for_every_role(self, admin_harness: ApiHarness, drive) -> None:  # type: ignore[no-untyped-def]
        allowed = EXPECTED_MATRIX[(drive.method, drive.path_template)]
        for role in ADMIN_ROLES:
            response = call(admin_harness.client, drive, role=role.value)
            if role in allowed:
                assert response.status_code != 403, (role.value, drive.path_template)
            else:
                assert response.status_code == 403, (role.value, drive.path_template)
                assert response.json()["error"] == "forbidden"

    @pytest.mark.parametrize("drive", ROUTE_DRIVES, ids=lambda d: f"{d.method} {d.path_template}")
    def test_tenant_query_parameter_is_refused_below_platform_owner(
        self, admin_harness: ApiHarness, drive
    ) -> None:  # type: ignore[no-untyped-def]
        for role in ADMIN_ROLES:
            response = call(admin_harness.client, drive, role=role.value, query="?tenant=tenant-b")
            error = response.json().get("error") if response.status_code == 403 else None
            if role is AdminRole.PLATFORM_OWNER:
                # it may still be refused for holding no role this route
                # admits — what it must never be refused for is naming a
                # tenant, which is the one thing this role may do
                assert error != "tenant_scope_refused"
            else:
                assert response.status_code == 403, role.value
                assert error == "tenant_scope_refused"

    def test_token_without_a_console_role_is_refused(self, admin_harness: ApiHarness) -> None:
        response = admin_harness.client.get(
            "/admin/whoami", headers={"Authorization": f"Bearer {token_for('no_console_role')}"}
        )
        assert response.status_code == 403

    def test_unknown_token_is_unauthorized(self, admin_harness: ApiHarness) -> None:
        response = admin_harness.client.get(
            "/admin/whoami", headers={"Authorization": "Bearer not-a-recorded-token"}
        )
        assert response.status_code == 401

    def test_whoami_reports_the_claim_tenant_and_the_roles(self, admin_harness: ApiHarness) -> None:
        body = admin_harness.client.get(
            "/admin/whoami", headers={"Authorization": f"Bearer {token_for('clinical_lead')}"}
        ).json()
        assert body["roles"] == ["clinical_lead"]
        assert body["tenant"] == "tenant-a"
        assert body["subject"] == "kc-sub-clinical-lead"


class TestFailClosed:
    def test_admin_surface_is_503_when_no_verifier_is_wired(self, tmp_path: Path) -> None:
        # The shipping default: no OIDC verifier, no console. A surface that
        # answered anything else would be authenticating nobody.
        harness_iter = build_harness(
            tmp_path,
            token_patient="p",
            token_admin="a",
            admin=None,
            client_addr=("192.0.2.10", 51000),
        )
        harness = next(harness_iter)
        try:
            response = harness.client.get("/admin/whoami", headers={"Authorization": "Bearer x"})
            assert response.status_code == 503
            assert response.json()["error"] == "admin_console_unconfigured"
        finally:
            harness_iter.close()

    def test_empty_ip_allowlist_admits_nobody(self, tmp_path: Path) -> None:
        harness_iter = build_admin_harness(tmp_path, admin=build_admin_wiring(allowlist=""))
        harness = next(harness_iter)
        try:
            response = harness.client.get(
                "/admin/whoami", headers={"Authorization": f"Bearer {token_for('platform_owner')}"}
            )
            assert response.status_code == 403
            assert response.json()["error"] == "source_ip_refused"
        finally:
            harness_iter.close()

    def test_address_outside_the_allowlist_is_refused(self, tmp_path: Path) -> None:
        harness_iter = build_admin_harness(tmp_path, client_addr=("198.51.100.7", 51000))
        harness = next(harness_iter)
        try:
            response = harness.client.get(
                "/admin/whoami", headers={"Authorization": f"Bearer {token_for('platform_owner')}"}
            )
            assert response.status_code == 403
            assert response.json()["error"] == "source_ip_refused"
        finally:
            harness_iter.close()

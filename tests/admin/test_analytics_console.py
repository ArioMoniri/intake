"""INT-490 — ``GET /admin/analytics``: the Analytics page's one read.

What the route promises, each with its near miss:

- **role-checked and audited (invariant 4).** Built from the INT-180
  descriptor table, so every call writes intent and outcome to the chain; only
  the all-tenant roles files/08 §2.1 gives aggregates to are admitted —
  ``researcher`` reads, ``tenant_admin`` and ``sre_oncall`` are refused, and the
  refusal is on the chain too;
- **no free-form filter (LD-06 across_views).** One parameter, ``period``, an
  ISO week that has closed; any other parameter, a malformed week or a week
  still filling is refused, and ``platform_owner``'s ``?tenant=`` is refused
  because the release is platform-wide, never a tenant cut of it;
- **computed server-side from what is stored**, counting a person once, with
  the Loop-2 opt-out honoured and a processor tenant without a DPA
  authorisation left out (LD-06);
- **nothing kept**: ``Cache-Control: no-store``, and the payload passes the
  same scan the route runs before it answers.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from admin_harness import bearer, build_admin_harness
from api_harness import ApiHarness, run
from intake_api.dev_fixture import DEV_TENANT_ID
from intake_platform.admin.roles import ROLE_SPECS, RoleScope
from intake_platform.admin.wiring import ADMIN_ROUTES
from intake_platform.analytics import K_ANONYMITY_FLOOR
from intake_platform.analytics.research import (
    ENV_AGGREGATE_RETENTION_DAYS,
    Period,
    assert_payload_safe,
)
from intake_platform.analytics.research.admission import (
    ENV_TENANT_REGISTRY,
)
from intake_platform.db.models import (
    Consent,
    IntakeSession,
    KvkkRole,
    Note,
    Patient,
    Share,
    Tenant,
)
from sqlalchemy.ext.asyncio import AsyncSession

PATH = "/admin/analytics"
WEEK = Period(2026, 30)
PROTOCOL = "int490.dev"
PROCESSOR_TENANT = uuid.UUID("5d0c3a71-8e2f-4b6a-9d14-7c2e9f0b3a55")


@pytest.fixture()
def admin_harness(tmp_path: Path) -> Iterator[ApiHarness]:
    yield from build_admin_harness(tmp_path)


def _registry(tmp_path: Path, *tenants: uuid.UUID) -> Path:
    lines = ["tenants:"] + [
        f"  - tenant_id: {tenant}\n    dpa_authorisation_ref: null" for tenant in tenants
    ]
    path = tmp_path / "analytics-tenants.yaml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


async def _seed(harness: ApiHarness) -> None:
    """Twelve people shared, ten opened only, one opted out, in WEEK — plus a
    processor tenant's twelve, which must not be counted."""
    at = WEEK.start + timedelta(days=2)
    async with AsyncSession(harness.engine) as session, session.begin():
        session.add(
            Tenant(id=PROCESSOR_TENANT, display_name="Processor", kvkk_role=KvkkRole.PROCESSOR)
        )
        await session.flush()
        for tenant, count, shared in (
            (DEV_TENANT_ID, 12, True),
            (DEV_TENANT_ID, 10, False),
            (PROCESSOR_TENANT, 12, True),
        ):
            for _ in range(count):
                patient = Patient(id=uuid.uuid4(), tenant_id=tenant, pseudonym=uuid.uuid4().hex)
                visit = IntakeSession(
                    id=uuid.uuid4(),
                    tenant_id=tenant,
                    patient_id=patient.id,
                    protocol_id=PROTOCOL,
                    protocol_version="v1",
                    created_at=at,
                )
                session.add_all([patient, visit])
                if shared:
                    note = Note(
                        id=uuid.uuid4(),
                        tenant_id=tenant,
                        session_id=visit.id,
                        patient_id=patient.id,
                        payload={"envelope": "opaque"},
                        created_at=at,
                    )
                    session.add(note)
                    session.add(
                        Share(
                            tenant_id=tenant,
                            note_id=note.id,
                            scope_sections={"section_ids": []},
                            expires_at=at + timedelta(hours=72),
                            created_at=at,
                        )
                    )
        opted_out = Patient(id=uuid.uuid4(), tenant_id=DEV_TENANT_ID, pseudonym="optout")
        session.add(opted_out)
        session.add(
            IntakeSession(
                tenant_id=DEV_TENANT_ID,
                patient_id=opted_out.id,
                protocol_id=PROTOCOL,
                protocol_version="v1",
                created_at=at,
            )
        )
        session.add(
            Consent(
                tenant_id=DEV_TENANT_ID,
                patient_id=opted_out.id,
                scope="learning:service_improvement",
                version="v1",
                granted_at=at - timedelta(days=30),
                revoked_at=at - timedelta(days=1),
            )
        )


def _get(harness: ApiHarness, role: str, query: str = f"?period={WEEK.id}"):  # type: ignore[no-untyped-def]
    return harness.client.get(f"{PATH}{query}", headers=bearer(role))


def test_the_readers_are_exactly_the_all_tenant_aggregate_roles() -> None:
    route = next(r for r in ADMIN_ROUTES if r.path == PATH)
    assert {role.value for role in route.permitted_roles} == {
        "researcher",
        "clinical_lead",
        "qms_owner",
        "platform_owner",
        "auditor",
    }
    assert all(ROLE_SPECS[role].scope is RoleScope.ALL_TENANTS for role in route.permitted_roles)
    assert route.dangerous_action_id is None  # a read; nothing to register


def test_a_researcher_reads_the_release(
    admin_harness: ApiHarness, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        ENV_TENANT_REGISTRY, str(_registry(tmp_path, DEV_TENANT_ID, PROCESSOR_TENANT))
    )
    run(_seed(admin_harness))
    response = _get(admin_harness, "researcher")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    payload = response.json()
    assert_payload_safe(payload, k=K_ANONYMITY_FLOOR)
    assert payload["period"]["id"] == WEEK.id
    assert payload["tenants"] == {"state": "configured", "admitted": 1, "refused": 1}
    funnel = next(
        v
        for v in payload["views"]
        if v["kind"] == "funnel" and v["dimensions"]["protocol"] == PROTOCOL
    )
    assert funnel["state"] == "shown"
    # 12 shared + 10 opened; the opted-out person and the processor tenant's
    # twelve are not in it
    assert {c["value"]: c["subjects"] for c in funnel["cells"]} == {
        "invited": 10,
        "started": 0,
        "finished": 0,
        "shared": 12,
    }
    kinds = {item["kind"]: item["reason"] for item in payload["not_collected"]}
    assert kinds["triage"] == "triage_level_not_recorded"
    assert kinds["question_outcome"] == "raw_telemetry_retention_undecided"
    assert payload["retention"]["aggregates"] == {"state": "undecided"}


@pytest.mark.parametrize("role", ["tenant_admin", "sre_oncall", "compliance_officer", "support"])
def test_roles_without_aggregate_access_are_refused_and_audited(
    admin_harness: ApiHarness, role: str
) -> None:
    before = len(tuple(admin_harness.audit_store.entries()))
    response = _get(admin_harness, role)
    assert response.status_code == 403
    actions = [e.action for e in tuple(admin_harness.audit_store.entries())[before:]]
    assert actions == ["admin.analytics.read.intent", "admin.analytics.read.failure"]


def test_a_successful_read_is_audited(admin_harness: ApiHarness) -> None:
    before = len(tuple(admin_harness.audit_store.entries()))
    assert _get(admin_harness, "auditor").status_code == 200
    actions = [e.action for e in tuple(admin_harness.audit_store.entries())[before:]]
    assert actions == ["admin.analytics.read.intent", "admin.analytics.read.success"]


@pytest.mark.parametrize(
    ("query", "code"),
    [
        (f"?period={WEEK.id}&protocol=x", "unexpected_parameter"),
        ("?week=2026-W30", "unexpected_parameter"),
        ("?period=2026-30", "period_malformed"),
        ("?period=2026-W60", "period_malformed"),
        ("?period=2099-W01", "period_not_closed"),
    ],
)
def test_no_free_form_filter_and_only_closed_weeks(
    admin_harness: ApiHarness, query: str, code: str
) -> None:
    response = _get(admin_harness, "researcher", query)
    assert response.status_code == 400
    assert response.json()["error"] == code


def test_the_week_still_filling_is_refused(admin_harness: ApiHarness) -> None:
    current = Period.containing(datetime.now(UTC))
    response = _get(admin_harness, "researcher", f"?period={current.id}")
    assert response.json()["error"] == "period_not_closed"


def test_without_a_period_the_latest_closed_week_is_served(admin_harness: ApiHarness) -> None:
    response = _get(admin_harness, "researcher", "")
    assert response.status_code == 200
    assert response.json()["period"]["id"] == Period.latest_closed(datetime.now(UTC)).id


def test_platform_owner_may_not_cut_the_release_by_tenant(admin_harness: ApiHarness) -> None:
    response = _get(admin_harness, "platform_owner", f"?period={WEEK.id}&tenant={DEV_TENANT_ID}")
    assert response.status_code == 400
    assert response.json()["error"] == "analytics_not_tenant_scoped"


def test_an_unconfigured_registry_admits_no_tenant(admin_harness: ApiHarness) -> None:
    run(_seed(admin_harness))
    payload = _get(admin_harness, "researcher").json()
    assert payload["tenants"] == {"state": "unconfigured"}
    assert payload["views"] == []


def test_a_malformed_retention_value_refuses_rather_than_reads_as_unset(
    admin_harness: ApiHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV_AGGREGATE_RETENTION_DAYS, "thirty")
    response = _get(admin_harness, "researcher")
    assert response.status_code == 503
    assert response.json()["error"] == "retention_config_refused"


def test_a_malformed_registry_refuses(
    admin_harness: ApiHarness, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("tenants: nope\n", encoding="utf-8")
    monkeypatch.setenv(ENV_TENANT_REGISTRY, str(path))
    response = _get(admin_harness, "researcher")
    assert response.status_code == 503
    assert response.json()["error"] == "tenant_registry_refused"

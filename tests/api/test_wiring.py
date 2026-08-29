"""INT-197 — env wiring, lifespan bootstrap, and the refusal branches.

Covers the paths the happy-path suites cannot reach through TestClient
alone: settings read from the environment (tokens have no default), the
env-built wiring, bootstrap-on-startup (including a database that is not
there yet), the audit-store readiness failure, and the consent-refusal
branches on the share scope.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest
from api_harness import ApiHarness, run, sqlite_ddl_clone
from fastapi.testclient import TestClient
from intake_api.app import ApiWiring, _documents_from_env, create_app, wiring_from_env
from intake_api.dev_fixture import DEV_PATIENT_ID, DEV_TENANT_ID, ensure_dev_fixture
from intake_api.settings import ApiSettings
from intake_platform.audit import AuditEntry
from intake_platform.db.models import Consent, Patient, Share, Tenant
from intake_platform.documents import DevNullScanner
from intake_platform.uploads import ClamAvScanner
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

VISIT_BODY = {
    "hospital": "Ankara Şehir Hastanesi",
    "department": "İç Hastalıkları",
    "date": "2026-09-03",
}

NOTE_BODY = {
    "sections": [{"id": "chief_complaint", "title": "Başvuru nedeni", "lines": ["Ağrı"]}],
    "scopes": {},
    "status": "sent",
}


# --- settings ----------------------------------------------------------------------


def test_settings_tokens_come_from_env_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INTAKE_DEV_TOKEN_PATIENT", raising=False)
    monkeypatch.delenv("INTAKE_DEV_TOKEN_ADMIN", raising=False)
    settings = ApiSettings.from_env()
    assert settings.token_patient is None
    assert settings.token_admin is None
    assert not settings.dev_auth_configured

    monkeypatch.setenv("INTAKE_DEV_TOKEN_PATIENT", "p-token")
    monkeypatch.setenv("INTAKE_DEV_TOKEN_ADMIN", "a-token")
    settings = ApiSettings.from_env()
    assert settings.dev_auth_configured
    assert settings.kek_mode == "transit"  # the durable default; file-dev is opt-in


def test_settings_default_urls_target_the_dev_compose_roles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "INTAKE_API_DB_URL",
        "INTAKE_API_AUDIT_DB_URL",
        "INTAKE_API_BOOTSTRAP_DB_URL",
        "PGHOST",
        "PGPORT",
        "POSTGRES_DB",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("INTAKE_API_KEK_MODE", "file-dev")
    settings = ApiSettings.from_env()
    assert settings.app_db_url.startswith("postgresql+psycopg://app_rw:")
    assert settings.audit_db_url.startswith("postgresql+psycopg://svc_audit_writer:")
    assert settings.kek_mode == "file-dev"


# --- env wiring + lifespan bootstrap --------------------------------------------------


def _env_for_sqlite(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("INTAKE_DEV_TOKEN_PATIENT", "p-token")
    monkeypatch.setenv("INTAKE_DEV_TOKEN_ADMIN", "a-token")
    monkeypatch.setenv("INTAKE_API_DB_URL", f"sqlite+aiosqlite:///{tmp_path}/app.db")
    monkeypatch.setenv("INTAKE_API_AUDIT_DB_URL", f"sqlite+pysqlite:///{tmp_path}/audit.db")
    monkeypatch.setenv("INTAKE_API_BOOTSTRAP_DB_URL", f"sqlite+aiosqlite:///{tmp_path}/app.db")
    monkeypatch.setenv("INTAKE_API_KEK_MODE", "file-dev")


def test_wiring_from_env_builds_the_dev_stack(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env_for_sqlite(monkeypatch, tmp_path)
    wiring = wiring_from_env()
    assert wiring.bootstrap is True
    assert wiring.bootstrap_engine is not None
    assert wiring.settings.dev_auth_configured
    run(wiring.engine.dispose())
    run(wiring.bootstrap_engine.dispose())


def test_documents_wiring_uses_clamav_when_clamd_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """INT-238 — the compose dev tier runs clamd and INT-120 already built
    the client, so a configured endpoint MUST produce the real scanner.
    Leaving the slot empty is what made every upload answer 503
    scan_not_configured while a healthy ClamAV sat on 3310."""
    monkeypatch.setenv("INTAKE_CLAMD_HOST", "127.0.0.1")
    monkeypatch.delenv("INTAKE_DEV_ALLOW_UNSCANNED", raising=False)
    config = _documents_from_env()
    assert isinstance(config.scanner, ClamAvScanner)


def test_documents_wiring_prefers_clamav_over_the_dev_stub(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The dev "everything is clean" stub must never shadow a real scanner:
    with both configured the AV verdict is the one that counts."""
    monkeypatch.setenv("INTAKE_CLAMD_HOST", "127.0.0.1")
    monkeypatch.setenv("INTAKE_DEV_ALLOW_UNSCANNED", "explicit-yes")
    config = _documents_from_env()
    assert isinstance(config.scanner, ClamAvScanner)


def test_documents_wiring_falls_back_to_the_dev_stub_under_the_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("INTAKE_CLAMD_HOST", raising=False)
    monkeypatch.delenv("INTAKE_CLAMD_UNIX_SOCKET", raising=False)
    monkeypatch.setenv("INTAKE_DEV_ALLOW_UNSCANNED", "explicit-yes")
    config = _documents_from_env()
    assert isinstance(config.scanner, DevNullScanner)


def test_documents_wiring_stays_empty_with_nothing_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail closed: no clamd and no dev opt-in means no scanner at all, and
    ingest refuses rather than serving unscanned bytes (INT-034 posture)."""
    monkeypatch.delenv("INTAKE_CLAMD_HOST", raising=False)
    monkeypatch.delenv("INTAKE_CLAMD_UNIX_SOCKET", raising=False)
    monkeypatch.delenv("INTAKE_DEV_ALLOW_UNSCANNED", raising=False)
    config = _documents_from_env()
    assert config.scanner is None


def test_env_app_lifespan_bootstraps_a_ready_service(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The env-built app seeds the two synthetic accounts on startup once the
    schema is there, and comes up ready with dev auth configured."""
    _env_for_sqlite(monkeypatch, tmp_path)
    for db_file in ("app.db", "audit.db"):
        ddl_engine = create_engine(f"sqlite+pysqlite:///{tmp_path}/{db_file}")
        sqlite_ddl_clone().create_all(ddl_engine)
        ddl_engine.dispose()

    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        ready = client.get("/readyz")
        assert ready.status_code == 200, ready.text
        listed = client.get("/v1/visits", headers={"Authorization": "Bearer p-token"})
        assert listed.status_code == 200
        assert listed.json() == []


def test_seed_is_idempotent(harness: ApiHarness) -> None:
    """A second seed run changes nothing (fixed UUIDv5 identities)."""

    async def _counts() -> tuple[int, int, int]:
        async with AsyncSession(harness.engine) as session:
            tenants = len((await session.scalars(select(Tenant.id))).all())
            patients = len((await session.scalars(select(Patient.id))).all())
            consents = len((await session.scalars(select(Consent.id))).all())
            return tenants, patients, consents

    before = run(_counts())
    run(ensure_dev_fixture(harness.engine))  # second run — must be a no-op
    assert run(_counts()) == before
    assert before[1] >= 1 and before[2] >= 3


def test_bootstrap_survives_a_database_that_is_not_there_yet(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env_for_sqlite(monkeypatch, tmp_path)
    # a directory as the "database file" makes every connection fail
    monkeypatch.setenv("INTAKE_API_DB_URL", f"sqlite+aiosqlite:///{tmp_path}")
    monkeypatch.setenv("INTAKE_API_BOOTSTRAP_DB_URL", f"sqlite+aiosqlite:///{tmp_path}")
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        # the app is up (healthz) but not ready (db check fails) — fail
        # closed without crashing the process, so probes can see the state
        assert client.get("/healthz").status_code == 200
        ready = client.get("/readyz")
        assert ready.status_code == 503
        assert ready.json()["checks"]["db"] == "error"


class _BrokenStore:
    """AuditStore whose backend is gone — readiness must report, not raise."""

    def append(self, entry: AuditEntry) -> None:
        raise ConnectionError("audit backend unavailable")

    def last(self) -> AuditEntry | None:
        raise ConnectionError("audit backend unavailable")

    def entries(self) -> Sequence[AuditEntry]:
        raise ConnectionError("audit backend unavailable")


def test_broken_audit_store_flips_readiness(harness: ApiHarness) -> None:
    app = create_app(
        ApiWiring(
            settings=harness.settings,
            engine=harness.engine,
            audit_store=_BrokenStore(),
            cipher=harness.cipher,
            bootstrap=False,
        )
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        ready = client.get("/readyz")
        assert ready.status_code == 503
        assert ready.json()["checks"]["audit_store"] == "error"


# --- consent refusals on the share scope ------------------------------------------------


def _revoke_share_scope(harness: ApiHarness) -> None:
    async def _revoke() -> None:
        async with AsyncSession(harness.engine) as session, session.begin():
            rows = (
                await session.scalars(
                    select(Consent).where(
                        Consent.tenant_id == DEV_TENANT_ID,
                        Consent.patient_id == DEV_PATIENT_ID,
                        Consent.scope == "share:previsit_note",
                    )
                )
            ).all()
            for row in rows:
                row.revoked_at = datetime.now(UTC)

    run(_revoke())


def test_sending_requires_the_share_consent(harness: ApiHarness) -> None:
    created = harness.client.post("/v1/visits", json=VISIT_BODY, headers=harness.patient())
    visit_id = created.json()["id"]
    _revoke_share_scope(harness)
    response = harness.client.put(
        f"/v1/visits/{visit_id}/note", json=NOTE_BODY, headers=harness.patient()
    )
    assert response.status_code == 403
    assert response.json() == {"error": "consent_required", "scope": "share:previsit_note"}


def test_admin_read_requires_the_share_consent_even_with_a_live_share(
    harness: ApiHarness,
) -> None:
    created = harness.client.post("/v1/visits", json=VISIT_BODY, headers=harness.patient())
    visit_id = created.json()["id"]
    sent = harness.client.put(
        f"/v1/visits/{visit_id}/note", json=NOTE_BODY, headers=harness.patient()
    )
    assert sent.status_code == 200
    _revoke_share_scope(harness)
    response = harness.client.get(f"/v1/visits/{visit_id}/note", headers=harness.admin())
    assert response.status_code == 403
    assert response.json() == {"error": "consent_required", "scope": "share:previsit_note"}


def test_duplicate_section_ids_are_rejected(harness: ApiHarness) -> None:
    created = harness.client.post("/v1/visits", json=VISIT_BODY, headers=harness.patient())
    visit_id = created.json()["id"]
    section = {"id": "hpi", "title": "x", "lines": ["y"]}
    response = harness.client.put(
        f"/v1/visits/{visit_id}/note",
        json={"sections": [section, section], "scopes": {}, "status": "draft"},
        headers=harness.patient(),
    )
    assert response.status_code == 422


def test_malformed_share_scope_sections_disclose_nothing(harness: ApiHarness) -> None:
    created = harness.client.post("/v1/visits", json=VISIT_BODY, headers=harness.patient())
    visit_id = created.json()["id"]
    harness.client.put(f"/v1/visits/{visit_id}/note", json=NOTE_BODY, headers=harness.patient())

    async def _corrupt() -> None:
        async with AsyncSession(harness.engine) as session, session.begin():
            share = (await session.scalars(select(Share))).one()
            share.scope_sections = {"section_ids": "not-a-list"}
            flag_modified(share, "scope_sections")

    run(_corrupt())
    response = harness.client.get(f"/v1/visits/{visit_id}/note", headers=harness.admin())
    assert response.status_code == 200
    assert response.json()["sections"] == []


def test_uuid_identity_is_stable() -> None:
    # the seed is idempotent because these never change between processes
    assert DEV_TENANT_ID == uuid.uuid5(uuid.NAMESPACE_URL, "https://intake.dev/tenants/dev-clinic")
    assert DEV_PATIENT_ID == uuid.uuid5(
        uuid.NAMESPACE_URL, "https://intake.dev/patients/dev-patient"
    )

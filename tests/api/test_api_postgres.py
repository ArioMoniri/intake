"""INT-197 — the API slice against the live compose tier (integration).

What only this lane can prove:
- the whole stack runs on real postgres: JSONB slots, ``gen_random_uuid``
  defaults, and the ``app.tenant_id`` GUC branch of tenant_session — with
  FORCE RLS deciding row visibility instead of the unit lane's predicates;
- the audit chain lands in ``audit_chain`` through the least-privilege
  ``svc_audit_writer`` role and verifies end to end;
- the lifespan bootstrap seeds the two synthetic accounts idempotently
  against the migrated schema;
- documents run against real MinIO: presigned upload slot, the ingest
  pipeline (quarantine → clean), and a download URL that actually serves
  the bytes back.

Runs via ``make check-integration`` (postgres + openbao + minio). Cleanup
removes the rows this run created; the dev tenant/patient/consents are the
persistent dev fixture and stay.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import httpx
import psycopg
import pytest
from api_harness import CleanScanner
from fastapi.testclient import TestClient
from intake_api.app import ApiWiring, create_app
from intake_api.dev_fixture import DEV_TENANT_ID
from intake_api.documents import DocumentsConfig
from intake_api.settings import ApiSettings
from intake_platform.audit import verify_entries
from intake_platform.db.audit_store import SqlAlchemyAuditStore
from intake_platform.documents import as_object_storage
from intake_platform.envelope import EnvelopeCipher, FileKekProvider
from minio import Minio
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]

HOST = os.environ.get("PGHOST", "127.0.0.1")
PORT = int(os.environ.get("PGPORT", "5432"))
DBNAME = os.environ.get("POSTGRES_DB", "intake")
SUPERUSER = os.environ.get("POSTGRES_USER", "intake")
SUPERPASS = os.environ.get("POSTGRES_PASSWORD", "intake-dev-only")

PATIENT_TOKEN = "int197-integration-patient"
ADMIN_TOKEN = "int197-integration-admin"

PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n%%EOF\n"
PDF_SHA = hashlib.sha256(PDF_BYTES).hexdigest()

VISIT_BODY = {
    "hospital": "Ankara Şehir Hastanesi",
    "department": "İç Hastalıkları",
    "date": "2026-09-03",
}

NOTE_BODY = {
    "sections": [
        {"id": "chief_complaint", "title": "Başvuru nedeni", "lines": ["Göğüs ağrısı"]},
        {"id": "medications", "title": "Kullandığı ilaçlar", "lines": ["Metoprolol"]},
    ],
    "scopes": {"medications": False},
    "status": "sent",
}


def _url(user: str, password: str) -> str:
    return f"postgresql+psycopg://{user}:{password}@{HOST}:{PORT}/{DBNAME}"


@pytest.fixture(scope="module")
def migrated() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(REPO / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO / "migrations"))
    cfg.set_main_option("sqlalchemy.url", _url(SUPERUSER, SUPERPASS))
    command.upgrade(cfg, "head")


@pytest.fixture(scope="module")
def minio_client() -> Minio:
    return Minio(
        os.environ.get("MINIO_ENDPOINT", "127.0.0.1:9000"),
        access_key=os.environ.get("MINIO_ROOT_USER", "intake-dev"),
        secret_key=os.environ.get("MINIO_ROOT_PASSWORD", "intake-dev-only"),
        secure=False,
    )


@pytest.fixture(scope="module")
def client(migrated: None, minio_client: Minio) -> Iterator[TestClient]:
    run_id = uuid.uuid4().hex[:8]
    engine = create_async_engine(_url("app_rw", "app-rw-dev-only"), poolclass=NullPool)
    bootstrap_engine = create_async_engine(_url(SUPERUSER, SUPERPASS), poolclass=NullPool)
    audit_engine = create_engine(_url("svc_audit_writer", "svc-audit-writer-dev-only"))
    settings = ApiSettings(
        token_patient=PATIENT_TOKEN,
        token_admin=ADMIN_TOKEN,
        app_db_url=_url("app_rw", "app-rw-dev-only"),
        audit_db_url=_url("svc_audit_writer", "svc-audit-writer-dev-only"),
        bootstrap_db_url=_url(SUPERUSER, SUPERPASS),
        kek_mode="file-dev",
    )
    app = create_app(
        ApiWiring(
            settings=settings,
            engine=engine,
            audit_store=SqlAlchemyAuditStore(audit_engine),
            # FileKek here on purpose: this lane proves RLS + roles + MinIO;
            # the Transit KEK path has its own coverage (INT-014/INT-017)
            cipher=EnvelopeCipher(FileKekProvider()),
            bootstrap=True,
            bootstrap_engine=bootstrap_engine,
            documents=DocumentsConfig(
                client=as_object_storage(minio_client),
                bucket_docs=f"int197-docs-{run_id}",
                bucket_audit=f"int197-audit-{run_id}",
                scanner=CleanScanner(),
            ),
        )
    )
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client

    # teardown: the run's record rows go; the dev fixture rows stay
    with psycopg.connect(
        host=HOST, port=PORT, dbname=DBNAME, user=SUPERUSER, password=SUPERPASS
    ) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            for table in ("shares", "notes", "documents", "slots", "events"):
                cur.execute(
                    f"DELETE FROM {table} WHERE tenant_id = %s",  # noqa: S608 — fixed names
                    (DEV_TENANT_ID,),
                )
            cur.execute("DELETE FROM sessions WHERE tenant_id = %s", (DEV_TENANT_ID,))
    for obj in minio_client.list_objects(f"int197-docs-{run_id}", recursive=True):
        if obj.object_name is not None:
            minio_client.remove_object(f"int197-docs-{run_id}", obj.object_name)
    minio_client.remove_bucket(f"int197-docs-{run_id}")
    # the audit bucket is WORM by design and cannot be drained before its
    # retention expires — same accepted residue as the INT-034 lane


def _patient() -> dict[str, str]:
    return {"Authorization": f"Bearer {PATIENT_TOKEN}"}


def _admin() -> dict[str, str]:
    return {"Authorization": f"Bearer {ADMIN_TOKEN}"}


def test_service_is_ready_after_lifespan_bootstrap(client: TestClient) -> None:
    ready = client.get("/readyz")
    assert ready.status_code == 200, ready.text
    assert ready.json()["checks"] == {"db": "ok", "audit_store": "ok", "dev_auth": "ok"}


def test_full_visit_and_note_flow_under_rls(client: TestClient) -> None:
    created = client.post("/v1/visits", json=VISIT_BODY, headers=_patient())
    assert created.status_code == 201, created.text
    visit_id = created.json()["id"]

    listed = client.get("/v1/visits", headers=_patient())
    assert visit_id in {v["id"] for v in listed.json()}

    saved = client.put(f"/v1/visits/{visit_id}/note", json=NOTE_BODY, headers=_patient())
    assert saved.status_code == 200, saved.text
    assert saved.json()["status"] == "sent"

    admin_view = client.get(f"/v1/visits/{visit_id}/note", headers=_admin())
    assert admin_view.status_code == 200
    assert [s["id"] for s in admin_view.json()["sections"]] == ["chief_complaint"]

    # note payload at rest is an envelope, read straight off postgres
    with (
        psycopg.connect(
            host=HOST, port=PORT, dbname=DBNAME, user=SUPERUSER, password=SUPERPASS
        ) as conn,
        conn.cursor() as cur,
    ):
        cur.execute("SELECT payload FROM notes WHERE session_id = %s", (visit_id,))
        row = cur.fetchone()
        assert row is not None
        assert set(row[0]) == {"key_version", "wrapped_dek", "nonce", "ciphertext"}


def test_foreign_tenant_rows_stay_invisible_under_force_rls(client: TestClient) -> None:
    foreign_tenant = uuid.uuid4()
    foreign_patient = uuid.uuid4()
    foreign_session = uuid.uuid4()
    with psycopg.connect(
        host=HOST, port=PORT, dbname=DBNAME, user=SUPERUSER, password=SUPERPASS
    ) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO tenants (id, display_name, kvkk_role) VALUES (%s, %s, %s)",
                (foreign_tenant, "int197-foreign", "controller"),
            )
            cur.execute(
                "INSERT INTO patients (id, tenant_id, pseudonym) VALUES (%s, %s, %s)",
                (foreign_patient, foreign_tenant, f"v1.{uuid.uuid4().hex}{uuid.uuid4().hex}"),
            )
            cur.execute(
                "INSERT INTO sessions (id, tenant_id, patient_id, protocol_id, "
                "protocol_version, status) VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    foreign_session,
                    foreign_tenant,
                    foreign_patient,
                    "previsit.dev.visit",
                    "int197-dev",
                    "created",
                ),
            )
    try:
        assert client.get(f"/v1/visits/{foreign_session}", headers=_patient()).status_code == 404
        assert client.get(f"/v1/visits/{foreign_session}", headers=_admin()).status_code == 404
    finally:
        with psycopg.connect(
            host=HOST, port=PORT, dbname=DBNAME, user=SUPERUSER, password=SUPERPASS
        ) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("DELETE FROM sessions WHERE id = %s", (foreign_session,))
                cur.execute("DELETE FROM patients WHERE id = %s", (foreign_patient,))
                cur.execute("DELETE FROM tenants WHERE id = %s", (foreign_tenant,))


def test_audit_chain_written_via_writer_role_and_verifies(client: TestClient) -> None:
    client.get("/v1/visits", headers=_patient())
    store = SqlAlchemyAuditStore(
        create_engine(_url("svc_audit_writer", "svc-audit-writer-dev-only"))
    )
    entries = store.entries()
    assert any(e.action == "api.visit.list" and e.actor == "dev-patient" for e in entries)
    assert verify_entries(entries).ok


def test_documents_roundtrip_against_real_minio(client: TestClient) -> None:
    created = client.post("/v1/visits", json=VISIT_BODY, headers=_patient())
    visit_id = created.json()["id"]
    minted = client.post(
        f"/v1/visits/{visit_id}/documents",
        json={"content_type": "application/pdf", "sha256": PDF_SHA},
        headers=_patient(),
    )
    assert minted.status_code == 201, minted.text
    doc_id = minted.json()["id"]

    ingested = client.put(
        f"/v1/visits/{visit_id}/documents/{doc_id}/content",
        content=PDF_BYTES,
        headers={**_patient(), "Content-Type": "application/pdf"},
    )
    assert ingested.status_code == 200, ingested.text
    assert ingested.json()["state"] == "clean"

    url = client.get(f"/v1/visits/{visit_id}/documents/{doc_id}/url", headers=_patient())
    assert url.status_code == 200
    fetched = httpx.get(url.json()["url"])
    assert fetched.status_code == 200
    assert fetched.content == PDF_BYTES

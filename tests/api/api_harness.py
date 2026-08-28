"""Unit-lane harness for services/api (INT-197 — owner-directive dev-tier slice).

The API is exercised through FastAPI's TestClient over the real INT-030
models. SQLite carries the schema for the unit lane the same way
tests/data/test_audit_store.py already carries ``audit_chain`` on SQLite:
the postgres-only surface (JSONB, ``gen_random_uuid()``/``now()`` server
defaults, BigInteger identity) is swapped for dialect-neutral equivalents in
a **DDL clone only** — the ORM statements the service issues are identical,
and the live DDL + RLS remain proven by the integration lane
(tests/api/test_api_postgres.py, tests/data/test_rls.py).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Coroutine, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from intake_api.app import ApiWiring, create_app
from intake_api.dev_fixture import ensure_dev_fixture
from intake_api.settings import ApiSettings
from intake_platform.db.audit_store import SqlAlchemyAuditStore
from intake_platform.db.models import (
    Base,
    IntakeSession,
    KvkkRole,
    Patient,
    SessionStatus,
    Slot,
    SlotSensitivity,
    Tenant,
)
from intake_platform.envelope import EnvelopeCipher, FileKekProvider
from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    DefaultClause,
    Integer,
    MetaData,
    create_engine,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

PATIENT_TOKEN = "unit-lane-patient-token"
ADMIN_TOKEN = "unit-lane-admin-token"


def run(coro: Coroutine[Any, Any, Any]) -> Any:
    """Drive an awaitable from a sync test (NullPool keeps connections
    loop-local, so mixing this with the TestClient's portal loop is safe)."""
    return asyncio.run(coro)


def sqlite_ddl_clone() -> MetaData:
    """Dialect-neutral copy of the INT-030 metadata for CREATE TABLE only."""
    clone = MetaData()
    for table in Base.metadata.sorted_tables:
        copied = table.to_metadata(clone)
        for column in copied.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()
            if column.primary_key and isinstance(column.type, BigInteger):
                column.type = Integer()
            if column.server_default is not None:
                if isinstance(column.type, DateTime):
                    column.server_default = DefaultClause(text("CURRENT_TIMESTAMP"))
                else:
                    column.server_default = None
    return clone


@dataclass
class ApiHarness:
    client: TestClient
    engine: AsyncEngine
    audit_store: SqlAlchemyAuditStore
    cipher: EnvelopeCipher
    settings: ApiSettings

    def patient(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {PATIENT_TOKEN}"}

    def admin(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {ADMIN_TOKEN}"}


def build_harness(
    tmp_path: Path, *, token_patient: str | None, token_admin: str | None
) -> Iterator[ApiHarness]:
    app_db = tmp_path / "api.db"
    audit_db = tmp_path / "audit.db"

    ddl_engine = create_engine(f"sqlite+pysqlite:///{app_db}")
    sqlite_ddl_clone().create_all(ddl_engine)
    ddl_engine.dispose()

    audit_engine = create_engine(f"sqlite+pysqlite:///{audit_db}")
    sqlite_ddl_clone().create_all(audit_engine)

    engine = create_async_engine(f"sqlite+aiosqlite:///{app_db}", poolclass=NullPool)
    settings = ApiSettings(
        token_patient=token_patient,
        token_admin=token_admin,
        app_db_url=f"sqlite+aiosqlite:///{app_db}",
        audit_db_url=f"sqlite+pysqlite:///{audit_db}",
        bootstrap_db_url=f"sqlite+aiosqlite:///{app_db}",
        kek_mode="file-dev",
    )
    cipher = EnvelopeCipher(FileKekProvider())
    audit_store = SqlAlchemyAuditStore(audit_engine)
    run(ensure_dev_fixture(engine))
    app = create_app(
        ApiWiring(
            settings=settings,
            engine=engine,
            audit_store=audit_store,
            cipher=cipher,
            bootstrap=False,
        )
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        yield ApiHarness(
            client=client,
            engine=engine,
            audit_store=audit_store,
            cipher=cipher,
            settings=settings,
        )
    run(engine.dispose())
    audit_engine.dispose()


async def _seed_foreign_visit(engine: AsyncEngine) -> uuid.UUID:
    """A visit belonging to a DIFFERENT tenant, written straight to the DB —
    the API must never surface it (query-level isolation in the unit lane;
    RLS proves the same live in the integration lane)."""
    foreign_tenant = uuid.uuid4()
    foreign_patient = uuid.uuid4()
    session_id = uuid.uuid4()
    async with AsyncSession(engine, expire_on_commit=False) as session, session.begin():
        session.add(
            Tenant(
                id=foreign_tenant,
                display_name="rls-foreign-unit",
                kvkk_role=KvkkRole.CONTROLLER,
            )
        )
        session.add(
            Patient(
                id=foreign_patient,
                tenant_id=foreign_tenant,
                pseudonym="dev." + uuid.uuid4().hex + uuid.uuid4().hex,
            )
        )
        session.add(
            IntakeSession(
                id=session_id,
                tenant_id=foreign_tenant,
                patient_id=foreign_patient,
                protocol_id="previsit.dev.visit",
                protocol_version="int197-dev",
                status=SessionStatus.CREATED,
                started_at=datetime.now(UTC),
            )
        )
        for slot_id, value in (
            ("visit.hospital", {"text": "Foreign Hospital"}),
            ("visit.department", {"text": "Foreign Department"}),
            ("visit.date", {"date": "2026-09-09"}),
        ):
            session.add(
                Slot(
                    tenant_id=foreign_tenant,
                    session_id=session_id,
                    slot_id=slot_id,
                    sensitivity=SlotSensitivity.PLAIN,
                    value=value,
                )
            )
    return session_id


def seed_foreign_visit(harness: ApiHarness) -> uuid.UUID:
    result: uuid.UUID = run(_seed_foreign_visit(harness.engine))
    return result
